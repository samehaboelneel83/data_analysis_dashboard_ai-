"""A whole dashboard, cold then warm, alone then with ten people on it.

`bench_widget_data.py` times one widget at a time in-process. A dashboard is
eleven widgets at once through HTTP, sharing one parsed frame, bounded by the
worker's `Semaphore(widget_work_max_concurrency)` -- and the targets in
docs/superpowers/specs/2026-09-12-scale-plan-design.md are written about THAT:

    simple dashboard, cold   < 3s
    simple dashboard, warm   < 1s
    ...with 10 users on one dashboard

So this measures exactly those, and prints pass/fail against them, because a
target nobody measures is a wish.

  cold   the page's first render after upload: the frame memo is empty and the
         widget-result cache is empty, so every widget pays what a first
         visitor pays. The page is "done" when its slowest widget returns.
  warm   the same page again.
  users  N concurrent copies of the warm page; each user's wall is their
         slowest widget, and p95 across users is what the target is about.

Run from the host against the live stack:

    python backend/scripts/bench_dashboard.py --email ... --password ... --users 10

The uploaded dataset is deleted at the end unless --keep.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.bench_common import battery, seed_csv  # noqa: E402

TARGETS = {"cold_s": 3.0, "warm_s": 1.0, "users_p95_s": 1.0}


def page_bodies() -> list[dict]:
    """The battery as one page. Cases needing server-side objects (prep steps,
    RLS rules, column rules) cannot be expressed in a widget body; the in-process
    bench and test_duck_agg_governed.py cover those."""
    cases = [c for c in battery() if "prep_steps" not in c
             and "rls_filter_expr" not in c and "drop_columns" not in c]
    bodies = []
    for c in cases:
        # `_name` is carried for the report and stripped before sending.
        body = {"_name": c["name"], "widget_type": c["widget_type"],
                "config": dict(c["config"])}
        if "calculated_columns" in c:
            body["calculated_columns"] = c["calculated_columns"]
        bodies.append(body)
    return bodies


async def render_page(client: httpx.AsyncClient, ds_id: int, bodies: list[dict],
                      salt: int = 0) -> tuple[float, list[tuple[str, float]]]:
    """One user opening the page: every widget at once. Returns the page wall
    (slowest widget) and each widget's latency. `salt` nudges `limit` per user
    so ten users are ten renders, not one cache entry served ten times -- that
    would measure the cache, not the dashboard. `limit` specifically, because
    it is on the DuckDB allowlist: an unknown key would push every user's
    render onto the pandas path and silently measure the wrong engine."""
    async def one(body: dict) -> tuple[str, float]:
        base_limit = int(body["config"].get("limit") or 50)
        b = {k: v for k, v in body.items() if k != "_name"}
        b["config"] = {**body["config"], "limit": base_limit + salt}
        t0 = time.perf_counter()
        r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", json=b)
        r.raise_for_status()
        return body["_name"], time.perf_counter() - t0
    t0 = time.perf_counter()
    lats = await asyncio.gather(*[one(b) for b in bodies])
    return time.perf_counter() - t0, list(lats)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", default=os.environ.get("BENCH_EMAIL", ""))
    ap.add_argument("--password", default=os.environ.get("BENCH_PASSWORD", ""))
    ap.add_argument("--rows", type=int, default=400_000,
                    help="upload cap is 100 MB; 400k rows is ~77 MB")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--distinct", action="store_true",
                    help="each user gets their own configs: ten dashboards, not one")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    csv_path = os.path.join(tempfile.gettempdir(), f"bench_dash_{args.rows}.csv")
    if not os.path.exists(csv_path):
        print(f"seeding {args.rows:,} rows", file=sys.stderr)
        seed_csv(csv_path, args.rows)

    async with httpx.AsyncClient(base_url=args.base, timeout=600) as client:
        r = await client.post("/api/v1/auth/login",
                              json={"email": args.email, "password": args.password})
        r.raise_for_status()
        client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

        with open(csv_path, "rb") as f:
            r = await client.post("/api/v1/datasets",
                                  files={"file": ("bench_dash.csv", f, "text/csv")},
                                  data={"name": "bench-dashboard-synthetic"})
        r.raise_for_status()
        ds_id = r.json()["id"]
        print(f"dataset {ds_id} uploaded", file=sys.stderr)

        bodies = page_bodies()
        result: dict = {"rows": args.rows, "widgets": len(bodies), "users": args.users}
        try:
            # Cold: nothing about this file is in any cache yet.
            cold_wall, cold_lats = await render_page(client, ds_id, bodies)
            result["cold_s"] = round(cold_wall, 3)
            # Named, not just timed: "the page is slow" has no next step;
            # "line_month is 5s" does.
            slowest_name, slowest_s = max(cold_lats, key=lambda nl: nl[1])
            result["cold_slowest_widget"] = slowest_name
            result["cold_slowest_widget_s"] = round(slowest_s, 3)

            warm_wall, _ = await render_page(client, ds_id, bodies)
            result["warm_s"] = round(warm_wall, 3)

            # Ten people. On ONE dashboard (the target's wording) they send
            # identical configs and the widget-result cache answers most of
            # them; --distinct gives each user their own configs, which is ten
            # dashboards and a much harder number. Both are reported when
            # --distinct is set, because the gap between them IS the cache.
            walls = await asyncio.gather(*[
                render_page(client, ds_id, bodies, salt=(u + 1) if args.distinct else 0)
                for u in range(args.users)])
            per_user = sorted(w for w, _ in walls)
            result["users_p50_s"] = round(statistics.median(per_user), 3)
            result["users_p95_s"] = round(per_user[max(0, int(len(per_user) * 0.95) - 1)], 3)
            result["users_max_s"] = round(per_user[-1], 3)
        finally:
            if not args.keep:
                await client.delete(f"/api/v1/datasets/{ds_id}")
                print(f"dataset {ds_id} deleted", file=sys.stderr)

    result["verdict"] = {k: ("pass" if result[k] <= v else "FAIL")
                         for k, v in TARGETS.items() if k in result}
    print(json.dumps(result, indent=2))
    if args.out:
        with open(args.out, "w") as f:
            f.write(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
