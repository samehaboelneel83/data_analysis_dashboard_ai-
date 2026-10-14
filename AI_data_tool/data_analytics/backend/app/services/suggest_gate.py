"""One gate for every suggested chart (docs/suggestions/PLAN.md, phase 3).

Five features suggest charts, and each had its own idea of when a chart is
worth offering. Three of them only asked "does it draw?". A chart can draw
and say nothing: one bar, the same value in every group, a headline of zero,
a ranking of "unknown". The checks that refuse those were written for the
guided setup; here they are the common gate, called by the dataset designer
and by the builder's suggestions as well, so a fix reaches every door.

Pure functions over a widget's config and its drawn result -- no model, no
database.
"""
from __future__ import annotations

REASONS = {
    "empty": "it has nothing to show",
    "single": "it has only one group to show",
    "flat": "it shows the same value everywhere",
    "zero": "its number is exactly zero",
    "tied": "its top values are all the same",
    "unknown": "most of it is 'unknown'",
}


def date_columns(profile: dict) -> set[str]:
    return {c["name"] for c in (profile or {}).get("columns", []) if c.get("role") == "datetime"}


def says_nothing(widget: dict, result: dict, dates: set[str] | None = None) -> str | None:
    """Why this DRAWN chart is not worth offering, in words -- or None when it
    shows something. `dates`: the dataset's date columns (a line over time is
    judged as a line, not as a ranking)."""
    from .guided_setup.answer import worth
    try:
        why = worth(widget, result or {}, dates or set())
    except Exception:                                           # noqa: BLE001 -- a check never blocks a chart by failing
        return None
    return REASONS.get(why, why) if why else None
