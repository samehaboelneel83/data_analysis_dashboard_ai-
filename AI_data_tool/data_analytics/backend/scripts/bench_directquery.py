"""DirectQuery at scale: does row count reach the application at all?

The import path's cost grows with the data, which is why it carries a row cap
(`settings.import_row_cap`, 2M) and a DuckDB pre-aggregation step. DirectQuery
is the opposite bet: the source database does the aggregation and this process
receives the small result.

MEASURED 2026-09-12 on an unindexed table, and half the bet did not hold:

    rows    aggregated   5,000 groups   raw (10k cap)
     1M        0.12s         0.34s          0.36s
    10M        1.21s         1.57s          2.75s

Memory here IS flat -- twelve rows come back whatever the table holds, so
nothing grows in this process. Latency is NOT: a GROUP BY over an unindexed
table is a sequential scan, so ten times the rows costs ten times the time,
and it is the SOURCE paying it. "DirectQuery is flat" is true about our
memory and false about the clock, and an index on the grouped column is the
customer-side lever, not anything in this codebase.

What the comparison is really for: the import path cannot answer 10M rows at
all -- `settings.import_row_cap` is 2M and a bigger frame is refused with a
413 -- while DirectQuery answers the same chart in about a second.

Two shapes, because they are bounded differently:

  AGGREGATED (bar: category -> sum(measure)) -- the source returns one row per
  group, so what crosses the wire is a handful of rows regardless of table size.

  RAW ROWS (table widget) -- bounded by `direct_query.DEFAULT_ROW_CAP` (10,000)
  and randomly sampled beyond it, with true column totals computed in SQL. So
  this is flat too, but for a different reason, and the sampling is what makes
  it flat.

Run inside the backend container:

    python scripts/bench_directquery.py --rows 1000000,10000000

The table is built as `bench_scale_orders`, its on-disk size is
printed, and it is DROPPED in a finally -- including on Ctrl-C. Nothing here
touches application tables; pass --keep only if you intend to inspect it and
drop it yourself.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.direct_query import DEFAULT_ROW_CAP, run_direct_query  # noqa: E402

# A prefixed table in `public`, not its own schema: `_quote` wraps a
# source_table in ONE pair of quotes, so "bench_scale.orders" addresses a
# single relation whose name contains a dot. The connector offers a Schema
# field but nothing in the application reads it, so a schema-qualified table
# is not reachable through this path at all -- and a benchmark should measure
# the path the product actually has.
TABLE = "bench_scale_orders"

#: Set by --schema. Empty means the default search path, which is what every
#: run did before the Schema field was wired through; passing one proves that
#: wiring against a real server, not just in unit tests.
SCHEMA = ""

#: Set by --index: create indexes on the grouped and filtered columns before
#: timing. Off by default because the unindexed number is the one a customer
#: sees first.
INDEX = False


class FakeDataset:
    """What `run_direct_query` reads off a dataset -- and nothing else.

    Deliberately not an ORM row: this script measures the SQL path, and
    inserting real Dataset/DataSource rows into the application's tables to
    time a query would leave application state behind for a benchmark.
    """

    def __init__(self, columns: list[str]):
        # None, not 0: every query is logged to `query_runs`, whose
        # dataset_id and data_source_id are real foreign keys. A made-up 0
        # fails the insert and takes the measurement down with it.
        self.id = None
        self.source_table = TABLE
        self.source_query = None
        self.data_source_id = None
        self.columns = [type("C", (), {"name": c, "dtype": d})()
                        for c, d in columns]


def sync_url() -> str:
    """The app's own database, as a plain sync URL. Sync because the
    DirectQuery path is sync -- it runs in a worker thread, not the loop."""
    return settings.database_url.replace("+asyncpg", "").replace(
        "postgresql://", "postgresql+psycopg2://")


def source_cfg_from_settings() -> dict:
    """A DataSource config dict pointing at this same Postgres.

    Parsed from the configured URL rather than typed out, so no credential is
    written down here.
    """
    from urllib.parse import urlparse

    u = urlparse(settings.database_url.replace("+asyncpg", ""))
    return {"type": "postgresql", "host": u.hostname, "port": u.port or 5432,
            "database": (u.path or "/").lstrip("/"),
            "username": u.username, "password": u.password,
            # The Schema field, which now reaches the connection as a
            # search_path. --schema is how this bench verifies that end to
            # end against a real server rather than only in unit tests.
            **({"schema": SCHEMA} if SCHEMA else {})}


def build_table(engine, rows: int) -> dict:
    """Generate the table server-side. generate_series keeps this a Postgres
    operation -- no rows cross the wire, so building 10M takes seconds."""
    qualified = f"{SCHEMA}.{TABLE}" if SCHEMA else TABLE
    index_s = 0.0
    with engine.begin() as c:
        if SCHEMA:
            c.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        c.execute(text(f"DROP TABLE IF EXISTS {qualified}"))
        t0 = time.perf_counter()
        c.execute(text(f"""
            CREATE TABLE {qualified} AS
            SELECT
              g                                            AS id,
              'R' || mod(g, 12)                            AS region,
              'C' || mod(g, 5000)                          AS customer,
              (date '2024-01-01' + mod(g, 720))            AS order_date,
              mod(g::bigint * 7919, 100000) / 100.0        AS amount,
              mod(g::bigint * 104729, 997)                 AS units
            FROM generate_series(1, :n) AS g
        """), {"n": rows})
        build_s = time.perf_counter() - t0
        if INDEX:
            # The lever this codebase cannot pull for the customer: an index
            # on the grouped / filtered column. Measured so the
            # recommendation (sub-project 5) can quote a number.
            t1 = time.perf_counter()
            c.execute(text(f"CREATE INDEX ON {qualified} (region)"))
            c.execute(text(f"CREATE INDEX ON {qualified} (customer)"))
            c.execute(text(f"ANALYZE {qualified}"))
            index_s = time.perf_counter() - t1
        size = c.execute(text(
            f"SELECT pg_size_pretty(pg_total_relation_size('{qualified}'))"
        )).scalar()
    return {"build_s": round(build_s, 2), "on_disk": size,
            "indexed": INDEX, "index_s": round(index_s, 2) if INDEX else None}


def timeit(fn, repeat: int = 3) -> float:
    fn()                                     # discard: fills the source's own cache
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return round(best, 4)


def bench(rows: int, engine, cfg: dict) -> dict:
    out: dict = {"rows": rows}
    out.update(build_table(engine, rows))

    ds = FakeDataset([("id", "numeric"), ("region", "categorical"),
                      ("customer", "categorical"), ("order_date", "date"),
                      ("amount", "numeric"), ("units", "numeric")])

    # cache_ttl_seconds=0 everywhere: a cached answer would time the cache.
    def aggregated():
        return run_direct_query(
            cfg, ds, {"dimension": "region", "measure": "amount",
                      "aggregation": "sum"},
            widget_type="bar", cache_ttl_seconds=0)

    def high_cardinality():
        # 5,000 groups rather than 12, so the result itself is no longer
        # trivial and this separates "the source is fast" from "the answer
        # was tiny". `limit` is explicit because the path defaults to 50
        # (direct_query.py: `int(config.get("limit") or 50)`) -- without it
        # this measured the same handful of rows as the low-cardinality case
        # and would have looked flat for the wrong reason.
        return run_direct_query(
            cfg, ds, {"dimension": "customer", "measure": "amount",
                      "aggregation": "sum", "limit": 5000},
            widget_type="bar", cache_ttl_seconds=0)

    def raw_rows():
        # Ask for more than DEFAULT_ROW_CAP so the cap is what bounds the
        # answer. The default limit of 50 would otherwise make this the
        # cheapest query in the file and prove nothing about the cap.
        return run_direct_query(
            cfg, ds, {"columns": ["id", "region", "amount", "units"],
                      "limit": DEFAULT_ROW_CAP * 3},
            widget_type="table", cache_ttl_seconds=0)

    r = aggregated()
    out["aggregated_groups"] = len(r.get("rows") or [])
    out["aggregated_s"] = timeit(aggregated)

    r = high_cardinality()
    out["high_card_groups"] = len(r.get("rows") or [])
    out["high_card_s"] = timeit(high_cardinality)

    def governed():
        # RLS on DirectQuery is a SQL predicate in its own subquery. This
        # is the SEC-PERF row: the same aggregation, one tenant's rows.
        return run_direct_query(
            cfg, ds, {"dimension": "customer", "measure": "amount",
                      "aggregation": "sum", "limit": 5000},
            widget_type="bar", rls_filter_expr="region == 'R3'",
            cache_ttl_seconds=0)

    r = governed()
    out["governed_groups"] = len(r.get("rows") or [])
    out["governed_s"] = timeit(governed)

    r = raw_rows()
    out["raw_rows_returned"] = len(r.get("rows") or [])
    out["raw_row_cap"] = DEFAULT_ROW_CAP
    out["raw_rows_s"] = timeit(raw_rows)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="1000000,10000000",
                    help="comma-separated row counts")
    ap.add_argument("--keep", action="store_true",
                    help="leave the bench schema in place (you must drop it)")
    ap.add_argument("--schema", default="",
                    help="build the table in this schema and configure the "
                         "source to use it (exercises the Schema field)")
    ap.add_argument("--index", action="store_true",
                    help="index the grouped/filtered columns first")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    global SCHEMA, INDEX
    SCHEMA = args.schema.strip()
    INDEX = args.index

    engine = create_engine(sync_url(), pool_pre_ping=True)
    cfg = source_cfg_from_settings()
    results = []
    try:
        for rows in [int(r) for r in args.rows.split(",") if r.strip()]:
            res = bench(rows, engine, cfg)
            results.append(res)
            print(json.dumps(res), flush=True)
    finally:
        if not args.keep:
            # In a finally so an error or a Ctrl-C still leaves the database as
            # it was found. A benchmark that litters is a benchmark nobody runs
            # twice.
            with engine.begin() as c:
                q = f"{SCHEMA}.{TABLE}" if SCHEMA else TABLE
                c.execute(text(f"DROP TABLE IF EXISTS {q}"))
                if SCHEMA:
                    c.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            print(f"dropped {SCHEMA or 'public'}.{TABLE}", flush=True)
        engine.dispose()

    blob = json.dumps(results, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(blob)


if __name__ == "__main__":
    main()
