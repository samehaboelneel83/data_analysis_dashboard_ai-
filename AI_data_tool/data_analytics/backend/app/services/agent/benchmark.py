"""Scoring Ask AI against a held-out, bilingual benchmark (E11).

A case is a question in English or Arabic with what a right answer must do:

- ``number``: state the expected value. The expected value is not written in
  the benchmark; the runner computes it from the data through the widget-data
  path, so the benchmark stays right when the data changes. A stated number
  counts when it agrees to the precision it was written at (the evidence
  tracer's rule: "2.2 million" agrees with 2,221,091.66) or within 0.5 %.
- ``mentions``: name every one of the given strings (a region, a month).
- ``refuse``: decline, or ask to clarify, and state no number -- an edit Ask AI
  must not make, a figure the data does not hold.

Every answered case is also checked for **grounding**: each number it states
traced to the query results by the evidence tracer (services/agent/
evidence.py). An answer that is right but carries an untraced number is
reported as ungrounded.

Pure: the runner (scripts/bench_ask.py) calls the API and hands the response
here.
"""
from __future__ import annotations

import re

from .evidence import _NUMBER, _NOT_CLAIMS, _normalize, _parse

_REFUSAL_CUES = re.compile(
    r"can(?:no|')t|unable|not (?:able|available|in the data|possible)|don't have|do not have|"
    r"no (?:column|data|field|information)|which .* do you mean|did you mean|clarify|"
    r"لا يمكن|لا أستطيع|لا أملك|لا تتوفر|غير متوفر|غير متاح|لا توجد|هل تقصد|يرجى التوضيح",
    re.IGNORECASE)


def stated_numbers(answer: str) -> list[dict]:
    text = _normalize(answer or "")
    skip = [(m.start(), m.end()) for m in _NOT_CLAIMS.finditer(text)]
    out = []
    for m in _NUMBER.finditer(text):
        if any(a <= m.start() < b for a, b in skip):
            continue
        out.append(_parse(m))
    return out


def _agrees(claim: dict, expected: float) -> bool:
    value = claim["value"] / 100 if claim["pct"] and abs(expected) <= 1.5 else claim["value"]
    tol = claim["tol"] / 100 if claim["pct"] and abs(expected) <= 1.5 else claim["tol"]
    return abs(value - expected) <= tol or abs(value - expected) <= abs(expected) * 0.005


def grounded(response: dict) -> bool | None:
    """True when every number the answer states was traced; None when the
    response carries no evidence at all (nothing was queried)."""
    ev = response.get("evidence")
    if not isinstance(ev, dict):
        return None
    return int(ev.get("untraced") or 0) == 0


def score(case: dict, response: dict, expected: float | None = None) -> dict:
    status = response.get("status")
    answer = response.get("answer") or ""
    numbers = stated_numbers(answer)
    kind = case["expect"]["kind"]
    if kind == "refuse":
        ok = status == "needs_clarification" or (not numbers and bool(_REFUSAL_CUES.search(answer)))
        why = None if ok else ("stated a number" if numbers else "did not decline")
    elif status != "ok":
        ok, why = False, f"status {status}: {response.get('error') or ''}".strip()
    elif kind == "number":
        ok = expected is not None and any(_agrees(c, expected) for c in numbers)
        why = None if ok else f"expected {expected:,.4g}; stated {[round(c['value'], 4) for c in numbers] or 'no number'}"
    elif kind == "mentions":
        missing = [w for w in case["expect"]["all"] if w.casefold() not in answer.casefold()]
        ok, why = not missing, (f"did not name {missing}" if missing else None)
    else:
        raise ValueError(f"unknown expectation {kind!r}")
    g = grounded(response) if kind != "refuse" and status == "ok" else None
    return {"id": case["id"], "lang": case["lang"], "kind": kind, "correct": ok,
            "grounded": g, "why": why, "ms": response.get("ms")}


def summarise(results: list[dict]) -> dict:
    out: dict = {}
    for lang in sorted({r["lang"] for r in results}):
        rs = [r for r in results if r["lang"] == lang]
        answered = [r for r in rs if r["kind"] != "refuse"]
        refusals = [r for r in rs if r["kind"] == "refuse"]
        out[lang] = {
            "cases": len(rs),
            "correct": sum(r["correct"] for r in answered),
            "answer_accuracy": round(sum(r["correct"] for r in answered) / len(answered), 3) if answered else None,
            "refusals_correct": f"{sum(r['correct'] for r in refusals)}/{len(refusals)}",
            "ungrounded": sum(1 for r in answered if r["grounded"] is False),
        }
    return out
