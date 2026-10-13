"""The persona benchmark's scoring and release gate (persona test Phase 4.1-4.2).

docs/persona-test/benchmark.json holds, per connection, a persona and the true
answers to their questions. A finished guided-setup analysis is scored by
reading what its dashboard SAYS (the answer text on its pages): each question
counts when every check holds -- the true number is stated (within a
tolerance), the right member is named, the change goes the right way, and no
known wrong answer is stated. Half a point when some checks hold.

The gate: a release may not lower any connection's score against the kept
baseline; the lowest-scoring connection is named as the next to work on.
Nothing here knows any database: the benchmark file carries the truths.
"""
from __future__ import annotations

import re

#: Compact suffixes a figure may carry ("1.18M", "45T").
_SCALE = {"k": 1e3, "m": 1e6, "mn": 1e6, "b": 1e9, "bn": 1e9, "t": 1e12}
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
_FIGURE = re.compile(r"(?<![\w.])([-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+−]?\d+(?:\.\d+)?)"
                     r"\s*(%|(?:k|m|mn|b|bn|t)\b)?", re.I)

UP_WORDS = re.compile(r"\b(rose|risen|rise|up|increas\w*|grew|grow\w*|higher|gain\w*|climb\w*)\b|"
                      r"ارتفع|ارتفاع|زاد|زيادة|صعد|نما|نمو", re.I)
DOWN_WORDS = re.compile(r"\b(fell|fall\w*|down|decreas\w*|drop\w*|lower|declin\w*|shrank|shrink\w*)\b|"
                        r"انخفض|انخفاض|تراجع|نقص|هبط", re.I)


def figures(text: str) -> list[tuple[float, bool]]:
    """Every figure in a text as (value, is_percent), suffixes applied."""
    out = []
    for m in _FIGURE.finditer((text or "").translate(_ARABIC_DIGITS)):
        raw, unit = m.group(1).replace(",", "").replace("−", "-"), (m.group(2) or "").lower()
        try:
            v = float(raw)
        except ValueError:
            continue
        out.append((v * _SCALE.get(unit, 1.0), unit == "%"))
    return out


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?؟。])\s+|\n+", text or "") if s.strip()]


def _near(v: float, want: float, rel_tol: float) -> bool:
    return abs(v - want) <= abs(want) * rel_tol if want else abs(v) <= rel_tol


def _states_number(text: str, check: dict) -> bool:
    want, tol, pct = float(check["value"]), float(check.get("rel_tol", 0.05)), bool(check.get("percent"))
    return any(_near(abs(v) if pct else v, abs(want) if pct else want, tol) and (is_pct or not pct)
               for v, is_pct in figures(text))


def check_holds(check: dict, text: str, right: list[str] | None = None) -> bool:
    kind = check.get("type")
    if kind == "number":
        return _states_number(text, check)
    if kind == "name":
        low = (text or "").casefold()
        return any(str(n).casefold() in low for n in check.get("any_of") or [])
    if kind == "direction":
        want = check.get("value")
        for s in sentences(text):
            up, down = bool(UP_WORDS.search(s)), bool(DOWN_WORDS.search(s))
            if up != down and (up if want == "up" else down):
                return True
        return False
    if kind == "none_of":
        for bad in check.get("values") or []:
            if isinstance(bad, (int, float)):
                if _states_number(text, {"value": bad, "rel_tol": 0.005}):
                    return False
                continue
            # A wrong NAME counts when a sentence gives it a figure (stated as
            # an answer) -- not when a note says it was left out. Digits inside
            # the name itself ("EGX 30") are not its figure.
            low = str(bad).casefold()
            if figures(str(bad)) and not re.search(r"[^\W\d_]", str(bad)):
                if low in (text or "").casefold():          # a figure written as text: "+83%", "0.992"
                    return False
                continue
            for s in sentences(text):
                # A sentence that also names the right answer compares or lists
                # them ("Harbour leads ... Airfield with 4"): not a wrong answer.
                if any(str(r).casefold() in s.casefold() for r in right or []):
                    continue
                rest = re.sub(r"“[^”]*”|\"[^\"]*\"|«[^»]*»", " ", re.sub(re.escape(str(bad)), " ", s, flags=re.I))
                if low in s.casefold() and figures(rest):         # quoted text is a name, not a figure
                    return False
        return True
    raise ValueError(f"unknown check type {kind!r}")


def score_question(question: dict, text: str) -> float:
    """1 when every check holds, 0.5 when some do (and no wrong answer is
    stated), else 0."""
    checks = question.get("checks") or []
    if not checks:
        return 0.0
    right = [n for c in checks if c.get("type") == "name" for n in c.get("any_of") or []]
    held = [check_holds(c, text, right) for c in checks]
    if all(held):
        return 1.0
    wrong = any(c.get("type") == "none_of" and not h for c, h in zip(checks, held))
    stated = [h for c, h in zip(checks, held) if c.get("type") != "none_of"]
    if wrong and stated and all(stated):
        # The right answer is stated, and a wrong name also appears with a
        # figure elsewhere -- possibly about another question ("Siwa: fewest
        # late, 2"); wording cannot tell which in every language: half a point.
        return 0.5
    return 0.5 if any(h for c, h in zip(checks, held) if c.get("type") != "none_of") and not wrong else 0.0


def score_scenario(scenario: dict, text: str) -> dict:
    per = {q["id"]: score_question(q, text) for q in scenario.get("questions") or []}
    return {"id": scenario["id"], "connection": scenario.get("connection"), "score": sum(per.values()),
            "out_of": float(len(per)), "questions": per}


def average(runs: list[dict[str, dict]]) -> dict[str, dict]:
    """The mean of several scored runs of the same version, per scenario and
    per question. The model designs differently each time (the same rules
    scored Olist 0.5, 2 and 0.5 in three runs), so one run cannot judge a
    change; the mean of several can."""
    out: dict[str, dict] = {}
    for sid in sorted({k for r in runs for k in r}):
        have = [r[sid] for r in runs if sid in r]
        qs = sorted({q for h in have for q in h["questions"]})
        per = {q: sum(h["questions"].get(q, 0.0) for h in have) / len(have) for q in qs}
        out[sid] = {"id": sid, "connection": have[0].get("connection"), "score": sum(per.values()),
                    "out_of": have[0]["out_of"], "questions": per, "runs": len(have),
                    "spread": max(h["score"] for h in have) - min(h["score"] for h in have)}
    return out


#: How far a scenario's mean may fall below its baseline before the gate
#: fails: a run-to-run swing of the model, not a change in the platform.
GATE_MARGIN = 0.5


def gate(scores: dict[str, dict], baseline: dict[str, dict], margin: float = 0.0) -> dict:
    """{"ok", "lowered": [ids whose score fell by more than `margin`], "lowest": id,
    "total", "out_of"}. Use a margin only with averaged runs (`average`)."""
    lowered = [sid for sid, s in scores.items()
               if sid in baseline and s["score"] < float(baseline[sid]["score"]) - margin - 1e-9]
    share = {sid: s["score"] / s["out_of"] for sid, s in scores.items() if s.get("out_of")}
    return {"ok": not lowered, "lowered": sorted(lowered),
            "lowest": min(share, key=lambda k: (share[k], k)) if share else None,
            "total": sum(s["score"] for s in scores.values()),
            "out_of": sum(s["out_of"] for s in scores.values())}
