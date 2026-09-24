"""Execution-accuracy evaluation (spec: 'results, not strings').

The report is broken down BY INTENT because a model change that helps
lookups and breaks trends is invisible in an average.
"""
from __future__ import annotations


def _normalise(rows: list[dict]) -> list[tuple]:
    def norm(v):
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    return sorted(tuple(norm(v) for v in row.values()) for row in rows)


def rows_equal(a: list[dict], b: list[dict]) -> bool:
    """Order-insensitive, alias-insensitive, type-tolerant equality — the
    answer is the VALUES, not the labels or the row order."""
    return _normalise(a) == _normalise(b)


def evaluate(pairs: list[dict], execute) -> dict:
    by_intent: dict[str, dict] = {}
    correct = 0
    for pair in pairs:
        intent = pair.get("intent") or "unknown"
        slot = by_intent.setdefault(intent, {"total": 0, "correct": 0})
        slot["total"] += 1
        try:
            golden = execute(pair["golden_sql"])
            generated = execute(pair["generated_sql"])
            ok = rows_equal(golden, generated)
        except Exception:
            ok = False
        if ok:
            correct += 1
            slot["correct"] += 1
    total = len(pairs)
    return {"total": total, "correct": correct,
            "accuracy": (correct / total) if total else 0.0,
            "by_intent": by_intent}
