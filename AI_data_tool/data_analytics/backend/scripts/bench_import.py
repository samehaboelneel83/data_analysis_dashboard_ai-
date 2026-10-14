"""How large an import this host can hold: a reproducible baseline.

    python scripts/bench_import.py                       # 250k, 1M, 2M, 4M rows
    python scripts/bench_import.py --rows 500000,2000000 --readers 4 --max-load-s 8 --json out.json

For each size, in a FRESH process (so one size's memory is not counted in the
next), on a seeded made-up table of about twenty columns (scripts/bench_common):

  * what an upload costs: parsing the CSV, and writing the parquet copy that
    every later read uses;
  * what a READER costs afterwards: loading the dataset cold (the parquet
    copy), the frame's size in memory, and the most memory the process held;
  * the first things a person does with it: the platform's type detection,
    the stored profile, and one chart.

From those it works out the largest size tested that this host carries
SAFELY, by two rules you can change:

  --readers N       people reading large datasets at the same moment (default 3)
  --memory-share F  share of the machine's memory imports may take (default 0.5)
  --max-load-s S    longest acceptable cold load of a dataset (default 10)

and prints it beside the current limit (settings.import_row_cap), which an
administrator changes under Admin -> Settings -> Data import and limits.
This script changes nothing: it writes its files to a temporary folder and
removes them.

Reproducible: the table is seeded; every time is the best of `--repeat` runs.
The numbers describe THIS machine -- run it on the host that will carry the
data before trusting its recommendation there.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _memory_total_mb() -> float:
    """What this process may use: the container's limit when it has one, else the machine's memory."""
    try:
        raw = open("/sys/fs/cgroup/memory.max").read().strip()
        if raw.isdigit():
            return int(raw) / 1e6
    except OSError:
        pass
    for line in open("/proc/meminfo"):
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) / 1e3
    return 0.0


def _best(fn, repeat: int) -> float:
    best = float("inf")
    for _ in range(max(repeat, 1)):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return round(best, 3)


def widen(df, extra_numbers: int, extra_text: int, text_chars: int):
    """The seeded table made WIDER: more number columns, and columns of long
    text that differs on every row -- the two things that move memory per row
    most. The added values are seeded too."""
    import numpy as np
    rng = np.random.default_rng(7)
    for i in range(extra_numbers):
        df[f"extra_number_{i + 1}"] = rng.normal(100.0, 25.0, len(df)).round(3)
    if extra_text:
        alphabet = np.array(list("abcdefghijklmnopqrstuvwxyz "))
        for i in range(extra_text):
            letters = rng.integers(0, len(alphabet), size=(len(df), max(1, text_chars)))
            df[f"extra_text_{i + 1}"] = ["".join(row) for row in alphabet[letters]]
    return df


def one_size(rows: int, workdir: str, repeat: int, extra_numbers: int = 0, extra_text: int = 0,
             text_chars: int = 80) -> dict:
    """Run in a child process: everything for one size, then its peak memory."""
    from scripts.bench_common import seed_frame
    from app.services import analytics
    from app.services.analytics import load_file
    from app.services.discovery import profile as store
    from app.services.frame_cache import clear_frame_cache, remove_parquet_sidecar, write_parquet_sidecar
    from app.services.widget_data import clear_widget_data_cache, get_widget_data

    path = os.path.join(workdir, f"import_{rows}.csv")
    widen(seed_frame(rows), extra_numbers, extra_text, text_chars).to_csv(path, index=False)
    out: dict = {"rows": rows, "csv_mb": round(os.path.getsize(path) / 1e6, 1)}

    def parse_csv():
        remove_parquet_sidecar(path)
        clear_frame_cache()
        load_file(path)
    out["parse_csv_s"] = _best(parse_csv, repeat)
    out["write_copy_s"] = _best(lambda: write_parquet_sidecar(path), 1)

    def load_cold():
        clear_frame_cache()
        return load_file(path)
    out["load_cold_s"] = _best(load_cold, repeat)
    df = load_cold()
    out["columns"] = int(df.shape[1])
    out["frame_mb"] = round(float(df.memory_usage(deep=True).sum()) / 1e6, 1)
    types = analytics.detect_types(df)
    out["detect_types_s"] = _best(lambda: analytics.detect_types(df), 1)
    out["profile_s"] = _best(lambda: store.compute(df, types), 1)

    def first_chart():
        clear_widget_data_cache()
        clear_frame_cache()
        get_widget_data(path, widget_type="bar", use_cache=True,
                        config={"dimension": "region", "measure": "revenue", "aggregation": "sum"})
    out["first_chart_cold_s"] = _best(first_chart, repeat)
    # Linux reports the peak in kilobytes.
    out["peak_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3, 1)
    return out


def recommend(results: list[dict], memory_mb: float, readers: int, share: float, max_load_s: float) -> dict:
    """The largest size tested that fits both rules, and why the next one does not."""
    budget = memory_mb * share
    safe, why = None, None
    for r in sorted(results, key=lambda x: x["rows"]):
        need = r["peak_mb"] * readers
        if need > budget:
            why = (f"{r['rows']:,} rows: {readers} readers would hold about {need:,.0f} MB, "
                   f"more than the {budget:,.0f} MB allowed")
            break
        if r["load_cold_s"] > max_load_s:
            why = f"{r['rows']:,} rows: a cold load takes {r['load_cold_s']} s, over the {max_load_s:g} s allowed"
            break
        safe = r["rows"]
    return {"safe_rows": safe, "stopped_by": why, "memory_mb": round(memory_mb), "budget_mb": round(budget),
            "readers": readers, "memory_share": share, "max_load_s": max_load_s,
            "largest_tested": max(r["rows"] for r in results)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows", default="250000,1000000,2000000,4000000")
    ap.add_argument("--readers", type=int, default=3)
    ap.add_argument("--memory-share", type=float, default=0.5)
    ap.add_argument("--max-load-s", type=float, default=10.0)
    ap.add_argument("--memory-mb", type=float, default=0.0, help="override the detected memory")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--json", default="")
    ap.add_argument("--workdir", default="")
    ap.add_argument("--extra-numbers", type=int, default=0, help="number columns added to the 20-column table")
    ap.add_argument("--extra-text", type=int, default=0, help="long-text columns added (distinct on every row)")
    ap.add_argument("--text-chars", type=int, default=80, help="characters in each added text value")
    ap.add_argument("--one", type=int, default=0, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.one:                                             # the child: one size, as JSON on the last line
        print("RESULT " + json.dumps(one_size(args.one, args.workdir, args.repeat, args.extra_numbers,
                                              args.extra_text, args.text_chars)))
        return

    sizes = sorted(int(x) for x in args.rows.split(",") if x.strip())
    workdir = args.workdir or tempfile.mkdtemp(prefix="bench_import_")
    os.makedirs(workdir, exist_ok=True)
    results = []
    try:
        for n in sizes:
            print(f"-- {n:,} rows ...", flush=True)
            child = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", str(n), "--workdir", workdir,
                                    "--repeat", str(args.repeat), "--extra-numbers", str(args.extra_numbers),
                                    "--extra-text", str(args.extra_text), "--text-chars", str(args.text_chars)], capture_output=True, text=True)
            line = next((l for l in child.stdout.splitlines() if l.startswith("RESULT ")), None)
            if child.returncode != 0 or line is None:
                # Running out of memory IS a result: this size is past what the host carries.
                results.append({"rows": n, "failed": (child.stderr.strip().splitlines() or ["killed"])[-1][:200]})
                print(f"   did not finish: {results[-1]['failed']}", flush=True)
                break
            results.append(json.loads(line[len("RESULT "):]))
            for f in os.listdir(workdir):                    # one size on disk at a time
                os.remove(os.path.join(workdir, f))
    finally:
        if not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    done = [r for r in results if "failed" not in r]
    memory = args.memory_mb or _memory_total_mb()
    advice = recommend(done, memory, args.readers, args.memory_share, args.max_load_s) if done else {}
    try:
        from app.core.config import settings
        current = int(settings.import_row_cap or 0)
    except Exception:                                        # noqa: BLE001
        current = None

    cols = [("rows", "rows"), ("csv_mb", "file MB"), ("parse_csv_s", "parse CSV s"), ("write_copy_s", "write copy s"),
            ("load_cold_s", "cold load s"), ("frame_mb", "in memory MB"), ("peak_mb", "peak MB"),
            ("detect_types_s", "types s"), ("profile_s", "profile s"), ("first_chart_cold_s", "first chart s")]
    print("\n| " + " | ".join(h for _, h in cols) + " |")
    print("|" + "---:|" * len(cols))
    for r in done:
        print("| " + " | ".join(f"{r[k]:,}" if k == "rows" else str(r[k]) for k, _ in cols) + " |")
    for r in results:
        if "failed" in r:
            print(f"\n{r['rows']:,} rows did not finish: {r['failed']}")
    if advice:
        print(f"\nThis host: {advice['memory_mb']:,} MB; imports may take {advice['memory_share']:.0%} of it "
              f"({advice['budget_mb']:,} MB) for {advice['readers']} readers at once; a cold load may take "
              f"{advice['max_load_s']:g} s.")
        if advice["safe_rows"] is None:
            print("Safe import limit: below the smallest size tested.")
        elif advice["stopped_by"] is None:
            print(f"Safe import limit: at least {advice['safe_rows']:,} rows (the largest size tested fits both rules).")
        else:
            print(f"Safe import limit: {advice['safe_rows']:,} rows. Next size up -- {advice['stopped_by']}.")
        if current is not None:
            print(f"The limit now (IMPORT_ROW_CAP): {current:,}" + (" (no limit)" if current == 0 else "") + ".")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"results": results, "advice": advice, "current_limit": current}, f, indent=1)


if __name__ == "__main__":
    main()
