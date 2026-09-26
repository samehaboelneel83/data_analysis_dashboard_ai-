"""Simulated users against a running stack: latency at 1, 10 and 50 (E14).

Each virtual user signs in and repeats what a person reading dashboards does:
list the dashboards, open one (the report, then every widget's data, as the
page does), list the datasets and preview one, then reads for a few seconds.
Each virtual user is a separate account (made for the run with the admin's
role and deleted after), because limits are per person: one account shared
by fifty simulated people measures the rate limiter, not the product. For each concurrency level it
runs for a fixed time and reports, per request kind, the count, errors and
the 50th / 95th / 99th percentile latency; and, the fairness measure, the
latency of a trivial request (`/health/live`) issued alongside, which stays
fast only if heavy work is off the event loop.

    python backend/scripts/bench_users.py --base http://localhost:8000 \
        --email admin@datalytics.local --password demo-password \
        --users 1,10,50 --seconds 60 --out perf.json

Read-only: it opens dashboards and previews, it changes nothing. The numbers
are the machine's, not the product's: compare runs on the same hardware, and
see docs/PERFORMANCE.md for the targets and a recorded baseline.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from collections import defaultdict

import httpx


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return round(s[k], 1)


STATUSES: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))


def summarise(samples: dict[str, list[tuple[float, bool]]]) -> dict:
    out = {}
    for kind, rows in sorted(samples.items()):
        ok = [ms for ms, good in rows if good]
        out[kind] = {"count": len(rows), "errors": sum(1 for _, good in rows if not good),
                     "error_statuses": dict(STATUSES.get(kind, {})),
                     "p50_ms": pct(ok, 50), "p95_ms": pct(ok, 95), "p99_ms": pct(ok, 99),
                     "mean_ms": round(statistics.fmean(ok), 1) if ok else None}
    return out


async def _timed(samples, kind, coro):
    t0 = time.perf_counter()
    good = False
    try:
        r = await coro
        good = r.status_code < 400
        if not good:
            STATUSES[kind][r.status_code] += 1
        return r if good else None
    except Exception:  # noqa: BLE001 - counted as an error
        STATUSES[kind][0] += 1
        return None
    finally:
        samples[kind].append(((time.perf_counter() - t0) * 1000, good))


async def one_user(base: str, token: str, until: float, samples, rng: random.Random) -> None:
    headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=120) as c:
        while time.perf_counter() < until:
            reports = await _timed(samples, "list dashboards", c.get("/api/v1/reports"))
            if reports is not None and reports.json():
                rep = rng.choice(reports.json())
                full = await _timed(samples, "open dashboard", c.get(f"/api/v1/reports/{rep['id']}"))
                if full is not None:
                    body = full.json()
                    page = (body.get("pages") or [{}])[0]
                    t0 = time.perf_counter()
                    calls = []
                    for w in page.get("widgets") or []:
                        ds = (w.get("config") or {}).get("dataset_id") or body.get("dataset_id")
                        if not ds or w.get("widget_type") in ("text", "image", "shape", "button"):
                            continue
                        calls.append(_timed(samples, "widget data", c.post(
                            f"/api/v1/datasets/{ds}/widget-data",
                            json={"widget_type": w["widget_type"], "config": w.get("config") or {},
                                  "report_id": rep["id"]})))
                    if calls:
                        await asyncio.gather(*calls)
                        samples["whole page (all widgets)"].append(((time.perf_counter() - t0) * 1000, True))
            datasets = await _timed(samples, "list datasets", c.get("/api/v1/datasets"))
            if datasets is not None and datasets.json():
                d = rng.choice([x for x in datasets.json() if x.get("mode") != "directquery"] or datasets.json())
                await _timed(samples, "dataset preview", c.post(f"/api/v1/datasets/{d['id']}/data-preview", json={}))
            await asyncio.sleep(rng.uniform(2.0, 5.0))     # a person reads


async def probe(base: str, until: float, samples) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:
        while time.perf_counter() < until:
            await _timed(samples, "trivial request during load", c.get("/health/live"))
            await asyncio.sleep(0.25)


async def level(base: str, tokens: list[str], users: int, seconds: int) -> dict:
    samples: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    STATUSES.clear()
    until = time.perf_counter() + seconds
    rng = random.Random(users)
    await asyncio.gather(probe(base, until, samples),
                         *[one_user(base, tokens[i], until, samples, random.Random(rng.random()))
                           for i in range(users)])
    return {"users": users, "seconds": seconds, "requests": summarise(samples)}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--users", default="1,10,50")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    levels = [int(x) for x in args.users.split(",")]
    made: list[int] = []
    tokens: list[str] = []
    async with httpx.AsyncClient(base_url=args.base, timeout=30,
                                 headers={"X-Requested-With": "XMLHttpRequest"}) as c:
        r = await c.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
        r.raise_for_status()
        admin = {"Authorization": f"Bearer {r.json()['access_token']}"}
        roles = (await c.get("/api/v1/admin/roles", headers=admin)).json()
        role_id = next(x["id"] for x in roles if x.get("is_org_admin"))
        stamp = int(time.time()) % 100000
        try:
            for i in range(max(levels)):
                email, pw = f"bench{stamp}-{i}@bench.example", f"Bench-{stamp}-pw!"
                u = await c.post("/api/v1/admin/users", headers=admin,
                                 json={"email": email, "password": pw, "role_id": role_id})
                u.raise_for_status()
                made.append(u.json()["id"])
                t = await c.post("/api/v1/auth/login", json={"email": email, "password": pw})
                t.raise_for_status()
                tokens.append(t.json()["access_token"])
            results = await run_levels(args, tokens, levels)
        finally:
            for uid in made:
                await c.delete(f"/api/v1/admin/users/{uid}", headers=admin)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


async def run_levels(args, tokens: list[str], levels: list[int]) -> list[dict]:
    results = []
    for n in levels:
        print(f"{n} user(s) for {args.seconds}s …", file=sys.stderr)
        res = await level(args.base, tokens, n, args.seconds)
        results.append(res)
        for kind, s in res["requests"].items():
            print(f"  {kind:32} n={s['count']:5} err={s['errors']:3} p50={s['p50_ms']} p95={s['p95_ms']} p99={s['p99_ms']}"
                  f"{' ' + str(s['error_statuses']) if s['error_statuses'] else ''}", file=sys.stderr)
    return results


if __name__ == "__main__":
    asyncio.run(main())
