"""Ask AI's answer when no model may be called, or none answers.

Ask AI stays on the menu without a model (owner's decision, 2026-10-10,
docs/discovery/PLAN.md): a question then gets what the platform can work out
by itself -- which of the columns in scope the question's own words point at,
and which calculations and analyses the data's shape supports -- instead of
"the model endpoint could not classify the question".

Nothing here guesses a query. It reads the catalog already in hand
(`SchemaContext`) and the analysis catalogue (`analysis/registry.py`); the
wording says plainly that no AI was used.
"""
from __future__ import annotations

import re

from ..analysis import registry

#: What a catalogue analysis needs of the data, by the kind of result it
#: returns -- shape only (a date, a number, a text), never a subject.
_NEEDS = {
    "forecast": ("date", "number"), "forecast_goal": ("date", "number"), "forecast_scenario": ("date", "number"),
    "anomaly": ("number",), "segment": ("number", "number"), "goal_seek": ("number", "number"),
    "statistical_test": ("number",), "explanation": ("number",), "key_influencers": ("category",),
    "decision_tree": ("number",), "automated_prediction": ("number",), "association_rules": ("category", "category"),
    "text_topics": ("text",), "text_sentiment": ("text",), "full_profile": (),
}
#: The same analyses in plain words, for a reader who never chose a method.
_PLAIN = {
    "full_profile": "Summarise every column: its range, its usual values and what is missing.",
    "statistical_test": "Check whether a difference between groups is real or could be chance.",
    "explanation": "Rank which columns move a number the most.",
    "key_influencers": "Find what goes together with an outcome.",
    "segment": "Group the rows that resemble each other.",
    "association_rules": "Find values that tend to appear together.",
    "anomaly": "Find the values that sit far from the usual.",
    "forecast": "Project a number into the coming periods, with a likely range.",
    "forecast_goal": "Estimate when a number will reach a target.",
    "forecast_scenario": "See how the projection changes if something else changes.",
    "goal_seek": "Work out what one number must be for another to reach a target.",
    "decision_tree": "Find the simple rules that separate one outcome from another.",
    "automated_prediction": "Test how well one column can be predicted from the others.",
    "text_topics": "Find the subjects a column of text talks about.",
    "text_sentiment": "Read whether a column of text is positive or negative.",
}
_NUMBER = re.compile(r"int|float|double|decimal|numeric|number|real|money", re.I)
_DATE = re.compile(r"date|time", re.I)
_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
MAX_LISTED = 10


def _kind(dtype: str | None) -> str:
    text = str(dtype or "")
    return "number" if _NUMBER.search(text) else "date" if _DATE.search(text) else "category"


def _mentioned(question: str, ctx) -> list[tuple[str, str, str]]:
    """(table, column, kind) for the columns the question's words point at."""
    words = {w.casefold() for w in _WORD.findall(question or "")}
    found: list[tuple[str, str, str]] = []
    for table, obj in (getattr(ctx, "objects", None) or {}).items():
        for column, dtype in (obj.columns or {}).items():
            parts = {p.casefold() for p in _WORD.findall(str(column))}
            # A word of the question that IS a word of the column's name, or
            # the start of one (plural and singular meet at four letters).
            if parts & words or any(len(w) >= 4 and any(p.startswith(w[:4]) for p in parts) for w in words):
                found.append((table, str(column), _kind(dtype)))
    return found[:MAX_LISTED]


def _have(ctx) -> dict[str, int]:
    have = {"number": 0, "date": 0, "category": 0, "text": 0}
    for obj in (getattr(ctx, "objects", None) or {}).values():
        for dtype in (obj.columns or {}).values():
            have[_kind(dtype)] += 1
    have["text"] = have["category"]            # a text analysis needs a text column; the catalog does not tell them apart
    return have


def answer(question: str, ctx, reason: str | None = None) -> str:
    """Plain words: what can be computed for this question without AI."""
    why = (reason or "").strip()
    lines = ["I could not use the AI model for this question"
             + (f" ({why})" if why else "") + ", so no query was written. "
             "Here is what the platform can compute from this data without AI."]

    hits = _mentioned(question, ctx)
    if hits:
        lines.append("")
        lines.append("Columns your question points at:")
        for table, column, kind in hits:
            how = {"number": "can be counted, totalled or averaged, and compared across groups",
                   "date": "can be used to see how things change over time",
                   "category": "can be used to split and compare groups"}[kind]
            lines.append(f"- {column} (in {table}): a {kind}; {how}.")
    else:
        lines.append("")
        lines.append("None of the question's words matched a column name in this data, "
                     "so try the name of a column or table as it is written.")

    have = _have(ctx)
    usable = []
    for spec in registry.all_analyses():
        needs = _NEEDS.get(spec.result_kind)
        if needs is None:
            continue
        wanted: dict[str, int] = {}
        for n in needs:
            wanted[n] = wanted.get(n, 0) + 1
        if all(have.get(k, 0) >= v for k, v in wanted.items()):
            usable.append(spec)
    if usable:
        lines.append("")
        lines.append("Analyses this data supports (run them from the dataset's Analysis tab):")
        seen: set[str] = set()
        for spec in usable:
            first = _PLAIN.get(spec.result_kind) or registry._opening_sentence(spec.description)
            if first in seen:
                continue
            seen.add(first)
            lines.append(f"- {first}")
            if len(seen) >= MAX_LISTED:
                break
    lines.append("")
    lines.append("Charts of these columns, with what each one shows, are in the dashboard builder under Suggest.")
    return "\n".join(lines)
