"""Render an `evaluate()` results dict as a table, and gate on a minimum accuracy.

T9 (all-layers pass): `evals/run_eval.py` was a library, not a gate — nothing turned
its output into a pass/fail signal a human (or a script) could act on. This module is
that missing piece: a pure-stdlib formatter (`build_report`) plus a CLI (`main`) that
exits non-zero when accuracy drops below a threshold.

    python -m evals.report results.json --min-accuracy 0.5

`results.json` is `evaluate()`'s own output shape (see run_eval.py):
    {"total": int, "correct": int, "accuracy": float,
     "by_intent": {intent: {"total": int, "correct": int}, ...}}
"""
from __future__ import annotations

import argparse
import json
import sys


def build_report(results: dict) -> str:
    """Render the per-intent breakdown plus an overall row as a plain-text table."""
    by_intent = results.get("by_intent") or {}
    header = f"{'Intent':<20}{'Correct':>10}{'Total':>10}{'Accuracy':>12}"
    rule = "-" * len(header)
    lines = [header, rule]
    for intent in sorted(by_intent):
        slot = by_intent[intent] or {}
        total = slot.get("total", 0)
        correct = slot.get("correct", 0)
        acc = (correct / total) if total else 0.0
        lines.append(f"{intent:<20}{correct:>10}{total:>10}{acc:>11.1%}")
    lines.append(rule)
    overall_total = results.get("total", 0)
    overall_correct = results.get("correct", 0)
    overall_acc = results.get("accuracy", 0.0) or 0.0
    lines.append(f"{'OVERALL':<20}{overall_correct:>10}{overall_total:>10}{overall_acc:>11.1%}")
    return "\n".join(lines)


def _load_results(path: str) -> dict:
    """Read and minimally validate a results JSON file. Raises ValueError with a
    human-readable message on anything malformed, so `main` can turn it into a clean
    exit 2 instead of a traceback."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ValueError(f"could not read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict) or "accuracy" not in data:
        raise ValueError(
            f"{path} does not look like an evaluate() results file "
            "(expected an object with an 'accuracy' key)"
        )
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.report",
        description="Print an evaluate() results table and gate on a minimum accuracy.",
    )
    parser.add_argument("results_json", help="Path to a results JSON file (evaluate()'s output shape)")
    parser.add_argument("--min-accuracy", type=float, default=0.0,
                        help="Exit 1 if overall accuracy is below this threshold (default: 0.0)")
    args = parser.parse_args(argv)

    try:
        results = _load_results(args.results_json)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(build_report(results))
    accuracy = results.get("accuracy", 0.0) or 0.0
    return 0 if accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
