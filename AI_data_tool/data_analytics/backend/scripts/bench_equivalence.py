"""The semantic gate: run the config battery through get_widget_data twice —
once per side of a toggled lever — and require byte-identical JSON.

Phase 0 ships with the trivial toggle (use_cache on/off) to validate the
harness; later phases register their levers here. Any diff exits non-zero,
naming the case. This script is the reason a perf lever can land at all.

Run inside the backend container:
    python scripts/bench_equivalence.py --toggle use-cache --rows 100000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.bench_common import battery, seed_csv, seed_frame  # noqa: E402

from app.services.widget_data import clear_widget_data_cache, get_widget_data  # noqa: E402


def canon(result: dict) -> str:
    return json.dumps(result, sort_keys=True, default=str)


def run_battery(csv_path: str, aux, **overrides) -> dict[str, str]:
    out = {}
    for case in battery(aux_path="yes"):
        kwargs = {k: v for k, v in case.items() if k not in ("name", "aux_key")}
        if "aux_key" in case:
            kwargs["prep_aux_frames"] = {case["aux_key"]: aux}
        kwargs.update(overrides)
        clear_widget_data_cache()
        out[case["name"]] = canon(get_widget_data(csv_path, **kwargs))
    return out


# Each toggle: (kwargs for side A, kwargs for side B, setup(csv_path) -> teardown or None).
# Later phases append here: "frame-cache" flips settings.frame_cache_enabled,
# "sidecar" writes/removes the parquet sidecar between sides.
def toggle_use_cache(csv_path: str):
    return {"use_cache": True}, {"use_cache": False}, None


def toggle_frame_cache(csv_path: str):
    from app.core.config import settings
    from app.services import frame_cache

    def set_enabled(v: bool):
        settings.frame_cache_enabled = v
        frame_cache.clear_frame_cache()

    return ({}, {}, ("frame_cache_enabled", set_enabled))


def toggle_sidecar(csv_path: str):
    from app.services import frame_cache

    def set_enabled(v: bool):
        if v:
            frame_cache.write_parquet_sidecar(csv_path)
        else:
            sidecar = csv_path + ".parquet"
            if os.path.exists(sidecar):
                os.remove(sidecar)
        frame_cache.clear_frame_cache()

    return ({}, {}, ("sidecar", set_enabled))


TOGGLES = {
    "use-cache": toggle_use_cache,
    "frame-cache": toggle_frame_cache,
    "sidecar": toggle_sidecar,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--toggle", choices=sorted(TOGGLES), default="use-cache")
    ap.add_argument("--rows", type=int, default=100_000)
    ap.add_argument("--workdir", default="")
    args = ap.parse_args()

    workdir = args.workdir or tempfile.mkdtemp(prefix="bench_eq_")
    csv_path = os.path.join(workdir, f"bench_{args.rows}.csv")
    if not os.path.exists(csv_path):
        seed_csv(csv_path, args.rows)
    aux = seed_frame(max(args.rows // 10, 1000))[["region", "weight"]].drop_duplicates("region")

    kwargs_a, kwargs_b, env = TOGGLES[args.toggle](csv_path)
    if env is None:
        side_a = run_battery(csv_path, aux, **kwargs_a)
        side_b = run_battery(csv_path, aux, **kwargs_b)
    else:
        _, set_state = env
        set_state(True)
        side_a = run_battery(csv_path, aux, **kwargs_a)
        set_state(False)
        side_b = run_battery(csv_path, aux, **kwargs_b)

    diffs = [name for name in side_a if side_a[name] != side_b[name]]
    if diffs:
        print(f"EQUIVALENCE FAILED [{args.toggle}] — differing cases: {diffs}")
        for name in diffs[:2]:
            print(f"--- {name} A: {side_a[name][:400]}")
            print(f"--- {name} B: {side_b[name][:400]}")
        sys.exit(1)
    print(f"equivalence OK [{args.toggle}]: {len(side_a)} cases byte-identical at {args.rows} rows")


if __name__ == "__main__":
    main()
