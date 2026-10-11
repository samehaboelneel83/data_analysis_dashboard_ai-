"""The page copilot's answer when no model may be called, or none answers.

The copilot changes a page from a sentence, and reading a sentence needs a
model. With "Allow AI" off for the data (services/ai_policy.py) it used to
refuse outright (409). It now says what the platform can do by itself for
what was typed (docs/discovery/PLAN.md §AW): which columns the words point
at, and which charts the platform has ALREADY built and checked on this data
for those columns -- each of them can be added from Suggest, no AI involved.

Nothing here guesses an edit: the page is not changed.
"""
from __future__ import annotations

from types import SimpleNamespace

from .agent.without_model import _mentioned

MAX_CHARTS = 5


def _columns_of(config: dict) -> set[str]:
    out: set[str] = set()
    for key in ("dimension", "dimension2", "measure", "measure2", "date_column", "target", "x", "y"):
        v = (config or {}).get(key)
        if isinstance(v, str) and v:
            out.add(v.casefold())
    for key in ("columns", "factors", "predictors"):
        for v in (config or {}).get(key) or []:
            if isinstance(v, str):
                out.add(v.casefold())
    return out


def answer(message: str, columns_by_table: dict[str, dict[str, str]], cards: list[dict] | None,
           reason: str | None = None) -> dict:
    """{"reply": plain words, "suggestions": charts ready to add}."""
    why = (reason or "").strip()
    lines = ["I could not use the AI model for this" + (f" ({why})" if why else "")
             + ", so the page was not changed. Here is what can be done without AI."]
    ctx = SimpleNamespace(objects={t: SimpleNamespace(columns=cols) for t, cols in (columns_by_table or {}).items()})
    hits = _mentioned(message, ctx)
    named = {c.casefold() for _t, c, _k in hits}
    if hits:
        lines += ["", "Columns your words point at: " + ", ".join(c for _t, c, _k in hits) + "."]
    else:
        lines += ["", "None of your words matched a column name in this data; "
                      "try the name of a column as it is written."]

    ready = []
    for card in cards or []:
        action = card.get("action") or {}
        if action.get("kind") != "add_widget" or not isinstance(action.get("config"), dict):
            continue
        used = _columns_of(action["config"])
        if named and not (used & named):
            continue
        ready.append({"title": str(card.get("title") or ""), "sentence": str(card.get("sentence") or ""),
                      "widget_type": action.get("widget_type"), "config": action["config"]})
        if len(ready) >= MAX_CHARTS:
            break
    if ready:
        lines += ["", "Charts the platform has already built and checked on this data"
                      + (" for those columns" if named else "") + ":"]
        lines += [f"- {r['title']}" + (f": {r['sentence']}" if r["sentence"] else "") for r in ready]
        lines += ["", "Add any of them from Suggest in the builder, or drag the columns onto the page from Fields."]
    else:
        lines += ["", "Drag the columns onto the page from Fields, or open Suggest for charts built from this data."]
    return {"reply": "\n".join(lines), "suggestions": ready}
