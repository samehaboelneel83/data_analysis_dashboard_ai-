"""Full-HTTP-path concurrency benchmark against the live stack.

Uploads the synthetic CSV as a real dataset, fires the widget battery as 28
concurrent POSTs (the demo-page shape), and — the headline metric — measures
the latency of a trivial request issued WHILE the storm runs. On a blocked
event loop that trivial request stalls behind every CSV parse; after the
to_thread offload it must stay fast.

Run from the host (talks to http://localhost:8000):
    python backend/scripts/bench_http.py --email e2e@sandbox.local --password e2e-sandbox-pw
Or inside the container with --base http://localhost:8000.
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


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", default=os.environ.get("BENCH_EMAIL", "e2e@sandbox.local"))
    ap.add_argument("--password", default=os.environ.get("BENCH_PASSWORD", ""))
    ap.add_argument("--rows", type=int, default=400_000)  # 100MB upload cap; ~77MB at 400k
    ap.add_argument("--widgets", type=int, default=28)
    ap.add_argument("--keep", action="store_true", help="keep the uploaded dataset")
    args = ap.parse_args()

    csv_path = os.path.join(tempfile.gettempdir(), f"bench_http_{args.rows}.csv")
    if not os.path.exists(csv_path):
        print(f"seeding {args.rows:,} rows -> {csv_path}", file=sys.stderr)
        seed_csv(csv_path, args.rows)

    async with httpx.AsyncClient(base_url=args.base, timeout=600) as client:
        r = await client.post("/api/v1/auth/login",
                              json={"email": args.email, "password": args.password})
        r.raise_for_status()
        client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

        with open(csv_path, "rb") as f:
            r = await client.post("/api/v1/datasets",
                                  files={"file": ("bench_http.csv", f, "text/csv")},
                                  data={"name": "bench-http-synthetic"})
        r.raise_for_status()
        ds_id = r.json()["id"]
        print(f"dataset {ds_id} uploaded ({os.path.getsize(csv_path):,} bytes)", file=sys.stderr)

        cases = [c for c in battery() if "prep_steps" not in c and "rls_filter_expr" not in c
                 and "drop_columns" not in c]
        bodies = []
        for i in range(args.widgets):
            case = cases[i % len(cases)]
            body = {"widget_type": case["widget_type"], "config": dict(case["config"])}
            if "calculated_columns" in case:
                body["calculated_columns"] = case["calculated_columns"]
            # unique limit per slot so requests don't collapse into one cache entry
            body["config"]["limit"] = 40 + i
            bodies.append(body)

        async def post_widget(body: dict) -> float:
            t0 = time.perf_counter()
            resp = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", json=body)
            resp.raise_for_status()
            return time.perf_counter() - t0

        trivial_lat: list[float] = []
        storm_done = asyncio.Event()

        async def trivial_probe() -> None:
            while not storm_done.is_set():
                t0 = time.perf_counter()
                resp = await client.get("/api/v1/datasets")
                resp.raise_for_status()
                trivial_lat.append(time.perf_counter() - t0)
                await asyncio.sleep(0.2)

        probe = asyncio.create_task(trivial_probe())
        t0 = time.perf_counter()
        lats = await asyncio.gather(*[post_widget(b) for b in bodies])
        wall = time.perf_counter() - t0
        storm_done.set()
        await probe

        lats_s = sorted(lats)
        result = {
            "widgets": args.widgets, "rows": args.rows,
            "storm_wall_s": round(wall, 3),
            "widget_p50_s": round(statistics.median(lats_s), 3),
            "widget_p95_s": round(lats_s[int(len(lats_s) * 0.95) - 1], 3),
            "trivial_probe_n": len(trivial_lat),
            "trivial_p50_ms": round(statistics.median(trivial_lat) * 1000, 1) if trivial_lat else None,
            "trivial_max_ms": round(max(trivial_lat) * 1000, 1) if trivial_lat else None,
        }
        print(json.dumps(result, indent=2))

        if not args.keep:
            await client.delete(f"/api/v1/datasets/{ds_id}")
            print(f"dataset {ds_id} deleted", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
