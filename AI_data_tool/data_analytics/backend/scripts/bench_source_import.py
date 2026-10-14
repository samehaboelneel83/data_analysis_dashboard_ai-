"""What importing from a DATABASE costs, and what a refresh costs.

    python scripts/bench_source_import.py --rows 250000,1000000,2000000

The rows come over a real connection (the app's own PostgreSQL) from a query
that makes them up on the server -- `generate_series`, no table is created,
read or changed. Each size runs in a fresh process and goes through the steps
an import takes (services/connections._capped_read, then the file and its
parquet copy), and then once more, which is what a full refresh is:

    fetch      the rows over the wire, in chunks, joined into one table
    write      the dataset's file
    copy       its parquet copy (what every later load reads)
    refresh    all three again over the same connection

with the process's peak memory. Eight columns: an id, a timestamp, three
categories, a yes/no, an amount and a 32-character code that differs on every
row.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUERY = """
SELECT g AS id,
       TIMESTAMP '2023-01-01' + (g % 94608000) * INTERVAL '1 second' AS happened_at,
       'group ' || (1 + g % 20) AS grp, 'kind ' || (1 + (g * 7) % 5) AS kind, 'place ' || (1 + (g * 13) % 8) AS place,
       (g * 3) % 10 < 3 AS flag, round((10 + ((g * 17) % 100000) / 100.0)::numeric, 2)::float8 AS amount,
       md5(g::text) AS code
FROM generate_series(1, {rows}) AS g
"""


def _engine():
    import sqlalchemy as sa
    from app.core.config import settings
    url = str(settings.database_url).replace("+asyncpg", "+psycopg2")
    return sa.create_engine(url)


def one(rows: int, workdir: str) -> dict:
    from app.services import connections
    from app.services.frame_cache import write_parquet_sidecar
    engine = _engine()
    path = os.path.join(workdir, f"source_{rows}.csv")
    out: dict = {"rows": rows}

    def once(prefix: str) -> None:
        t = time.monotonic()
        df = connections._capped_read(QUERY.format(rows=rows), engine, None, 0)
        out[f"{prefix}fetch_s"] = round(time.monotonic() - t, 2)
        t = time.monotonic()
        df.to_csv(path, index=False)
        out[f"{prefix}write_s"] = round(time.monotonic() - t, 2)
        t = time.monotonic()
        write_parquet_sidecar(path)
        out[f"{prefix}copy_s"] = round(time.monotonic() - t, 2)
        out["columns"] = int(df.shape[1])

    once("")
    out["import_s"] = round(out["fetch_s"] + out["write_s"] + out["copy_s"], 2)
    once("refresh_")
    out["refresh_s"] = round(out["refresh_fetch_s"] + out["refresh_write_s"] + out["refresh_copy_s"], 2)
    out["csv_mb"] = round(os.path.getsize(path) / 1e6, 1)
    out["peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3, 1)
    engine.dispose()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="250000,1000000,2000000")
    ap.add_argument("--json", default="")
    ap.add_argument("--one", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--workdir", default="")
    args = ap.parse_args()
    if args.one:
        print("RESULT " + json.dumps(one(args.one, args.workdir)))
        return
    results = []
    with tempfile.TemporaryDirectory(prefix="bench_source_") as workdir:
        for n in [int(x) for x in args.rows.split(",") if x.strip()]:
            child = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", str(n), "--workdir", workdir],
                                   capture_output=True, text=True)
            line = next((l for l in child.stdout.splitlines() if l.startswith("RESULT ")), None)
            if line is None:
                results.append({"rows": n, "failed": (child.stderr.strip().splitlines() or ["killed"])[-1][:240]})
                print(f"{n:,} rows: did not finish -- {results[-1]['failed']}")
                break
            r = json.loads(line[7:])
            results.append(r)
            print(f"{n:>11,} rows | fetch {r['fetch_s']:>6} s | write {r['write_s']:>6} s | copy {r['copy_s']:>6} s | "
                  f"import {r['import_s']:>6} s | refresh {r['refresh_s']:>6} s | file {r['csv_mb']:>7} MB | "
                  f"peak {r['peak_mb']:>8} MB")
            for f in os.listdir(workdir):
                os.remove(os.path.join(workdir, f))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=1)


if __name__ == "__main__":
    main()
