"""What a very large dataset costs -- charts drawn WITHOUT loading it.

    python scripts/bench_large.py --rows 50000000,200000000 --workdir /app/uploads/_bench

For each size: a made-up table is written straight to a parquet file by DuckDB
(no row ever passes through pandas), then the charts every dashboard starts
with are drawn through the app's own entry point (`get_widget_data`) with a
cold cache, timed, with this process's peak memory. It also says what the
memory guard would do with a chart that DOES need every row in memory
(services/memory_guard.py): how much it would take against what is free.

The table: an id, a timestamp over three years, three categories (20, 5 and 8
values), a yes/no, an amount and a count -- eight columns. Nothing here is
about any business; the names say what kind of column each is.

The file is removed afterwards unless --keep.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build(path: str, rows: int, threads: int) -> float:
    import duckdb
    con = duckdb.connect()
    con.execute(f"SET threads TO {threads}")
    started = time.monotonic()
    con.execute(f"""
        COPY (SELECT i AS id,
                     TIMESTAMP '2023-01-01' + to_seconds(CAST(i % 94608000 AS BIGINT)) AS happened_at,
                     'group ' || CAST(1 + (hash(i) % 20) AS VARCHAR) AS grp,
                     'kind ' || CAST(1 + (hash(i * 7) % 5) AS VARCHAR) AS kind,
                     'place ' || CAST(1 + (hash(i * 13) % 8) AS VARCHAR) AS place,
                     (hash(i * 3) % 10) < 3 AS flag,
                     round(10 + (hash(i * 17) % 100000) / 100.0, 2) AS amount,
                     CAST(1 + (hash(i * 29) % 9) AS INTEGER) AS units
              FROM range({rows}) t(i))
        TO '{path}' (FORMAT parquet, ROW_GROUP_SIZE 1000000)""")
    con.close()
    return time.monotonic() - started


CHARTS = [
    ("headline: total",            "kpi",  {"measure": "amount", "aggregation": "sum"}),
    ("headline: how many",         "kpi",  {"measure": "id", "aggregation": "count"}),
    ("headline: average",          "kpi",  {"measure": "amount", "aggregation": "avg"}),
    ("total by group (20)",        "bar",  {"dimension": "grp", "measure": "amount", "aggregation": "sum"}),
    ("rows by kind (5)",           "bar",  {"dimension": "kind", "aggregation": "count"}),
    ("total by month",             "line", {"dimension": "happened_at", "dimension_granularity": "month",
                                            "measure": "amount", "aggregation": "sum"}),
    ("total by group, one place",  "bar",  {"dimension": "grp", "measure": "amount", "aggregation": "sum",
                                            "filters": [{"column": "place", "op": "eq", "value": "place 3"}]}),
    ("median by place (8)",        "bar",  {"dimension": "place", "measure": "amount", "aggregation": "median"}),
]
#: A chart the no-load path does not cover: it needs the rows in memory.
NEEDS_ROWS = ("spread (std) by group", "bar", {"dimension": "grp", "measure": "amount", "aggregation": "std"})


def one(rows: int, workdir: str, threads: int, keep: bool) -> dict:
    from app.core.config import settings
    from app.services import memory_guard, widget_data as wd
    os.makedirs(workdir, exist_ok=True)
    path = os.path.join(workdir, f"bench_{rows}.parquet")
    out: dict = {"rows": rows}
    if not os.path.exists(path):
        out["write_s"] = round(build(path, rows, threads), 1)
    out["file_mb"] = round(os.path.getsize(path) / 1e6, 1)
    settings.widget_duckdb_pushdown = True
    charts = []
    for name, kind, config in CHARTS:
        wd.clear_widget_data_cache()
        started = time.monotonic()
        got = wd.get_widget_data(path, config, widget_type=kind, use_cache=False)
        charts.append({"chart": name, "seconds": round(time.monotonic() - started, 2),
                       "answered": got.get("type") not in ("error", "empty"), "points": len(got.get("rows") or [])})
    out["charts"] = charts
    out["peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    needed, _rows = memory_guard.estimate(path)
    free = memory_guard.free_bytes() or 0
    out["full_load_gb"] = round(needed / 1e9, 1)
    out["free_gb"] = round(free / 1e9, 1)
    # What the guard WOULD say to a chart that needs the rows -- asked, not
    # tried: trying it at this size is the very thing the guard is there for.
    try:
        memory_guard.check(path)
        out["needs_rows"] = "would be loaded (it fits in the allowed share of free memory)"
    except memory_guard.TooLargeToLoad as exc:
        out["needs_rows"] = "refused: " + str(exc)[:170]
    if not keep:
        os.remove(path)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="10000000,50000000")
    ap.add_argument("--workdir", default="/tmp/bench_large")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    results = []
    for n in [int(x) for x in args.rows.split(",") if x.strip()]:
        got = one(n, args.workdir, args.threads, args.keep)
        results.append(got)
        print(f"\n{n:,} rows -- file {got['file_mb']:,} MB" + (f", written in {got['write_s']} s" if "write_s" in got else ""))
        for c in got["charts"]:
            print(f"  {c['seconds']:>7.2f} s  {c['chart']:<28} {'ok' if c['answered'] else 'NOT ANSWERED'} ({c['points']} points)")
        print(f"  peak memory of this process: {got['peak_mb']:,} MB")
        print(f"  a full load would take about {got['full_load_gb']} GB; free now {got['free_gb']} GB")
        print(f"  a chart that needs the rows -> {got['needs_rows']}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=1)


if __name__ == "__main__":
    main()
