"""In-process widget-data benchmark: times load_file cold and the config
battery cold/warm against a seeded synthetic CSV.

Run inside the backend container:
    python scripts/bench_widget_data.py --rows 1000000 --out /tmp/bench.json

Every number is min-of-3 (after one discarded warm-up) via perf_counter.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.bench_common import battery, seed_csv, seed_frame, timeit  # noqa: E402

from app.services.analytics import load_file  # noqa: E402
from app.services.frame_cache import (clear_frame_cache,  # noqa: E402
                                      remove_parquet_sidecar,
                                      write_parquet_sidecar)

NO_SIDECAR = False
from app.services.widget_data import clear_widget_data_cache, get_widget_data  # noqa: E402


def bench_rows(rows: int, workdir: str) -> dict:
    csv_path = os.path.join(workdir, f"bench_{rows}.csv")
    if not os.path.exists(csv_path):
        seed_csv(csv_path, rows)
    # What an upload does. Without the sidecar the cold number (5.6s at 1M
    # rows, measured 2026-09-12) describes a CSV parse that no real dataset
    # pays after upload; with it, the same render is ~1s. `--no-sidecar`
    # keeps the old measurement available for exactly that comparison.
    if NO_SIDECAR:
        remove_parquet_sidecar(csv_path)
    else:
        write_parquet_sidecar(csv_path)
    aux_rows = max(rows // 10, 1000)
    aux = seed_frame(aux_rows)[["region", "weight"]].drop_duplicates("region")

    out: dict = {"rows": rows, "csv_bytes": os.path.getsize(csv_path)}
    # Both caches, every call. load_file is memoised per process and timeit
    # discards its first call, so without this the metric timed a memo copy
    # rather than a parse -- 0.1s for a 193 MB CSV, which is the tell.
    def load_cold():
        clear_frame_cache()
        load_file(csv_path)
    out["load_file_cold_s"] = timeit(load_cold)

    def run(case: dict, use_cache: bool) -> dict:
        kwargs = {k: v for k, v in case.items() if k not in ("name", "aux_key")}
        if "aux_key" in case:
            kwargs["prep_aux_frames"] = {case["aux_key"]: aux}
        return get_widget_data(csv_path, use_cache=use_cache, **kwargs)

    cold, warm = {}, {}
    for case in battery(aux_path="yes"):
        def cold_once(case=case):
            # The result cache AND the parsed frame. Clearing only the
            # former measured aggregation on a frame already in memory,
            # which is a warm render wearing a cold label.
            clear_widget_data_cache()
            clear_frame_cache()
            run(case, use_cache=True)
        cold[case["name"]] = timeit(cold_once)

        run(case, use_cache=True)  # prime
        warm[case["name"]] = timeit(lambda case=case: run(case, use_cache=True))

    out["cold_s"] = cold
    out["warm_s"] = warm
    out["cold_total_s"] = round(sum(cold.values()), 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--midrows", type=int, default=100_000)
    ap.add_argument("--out", default="")
    ap.add_argument("--workdir", default="")
    ap.add_argument("--no-sidecar", action="store_true",
                    help="time the raw CSV parse instead of the sidecar an upload writes")
    args = ap.parse_args()
    global NO_SIDECAR
    NO_SIDECAR = args.no_sidecar

    workdir = args.workdir or tempfile.mkdtemp(prefix="bench_")
    os.makedirs(workdir, exist_ok=True)
    results = {"workdir": workdir,
               "full": bench_rows(args.rows, workdir),
               "mid": bench_rows(args.midrows, workdir)}
    blob = json.dumps(results, indent=2)
    print(blob)
    if args.out:
        with open(args.out, "w") as f:
            f.write(blob)


if __name__ == "__main__":
    main()
