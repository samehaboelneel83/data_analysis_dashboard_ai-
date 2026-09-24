"""The semantic veto, backend half (MASTER_PLAN Phase 0, constitution rule 3).

A column can be numeric without being a quantity. Summing, averaging,
correlating or trending a latitude, an identifier or a year returns a number
every time, with no error, and the number means nothing -- the suggestion
engine SAS ships proposes summed latitudes for exactly this reason.

Classified by NAME, the way these columns are actually named. Mirrors
frontend/src/lib/semanticGuard.ts; `tests/test_semantic_guard.py` pins the two
to the same examples so they cannot drift. Pure: no pandas, no FastAPI.
"""
from __future__ import annotations

import re

_ID_NAME = re.compile(r"(^id$|_id$|_key$|_uuid$|^uuid$|_code$)", re.I)
_COORD_WORDS = ("lat", "latitude", "lon", "lng", "long", "longitude")
_YEAR_WORDS = ("year", "yr", "fiscal_year")


def _word(name: str, words) -> bool:
    low = str(name).lower()
    return any(low == w or low.endswith("_" + w) or low.startswith(w + "_")
               or ("_" + w + "_") in low for w in words)


def non_additive_kind(column: str | None) -> str | None:
    """'coordinate' | 'identifier' | 'year' | None."""
    if not column:
        return None
    if _word(column, _COORD_WORDS):
        return "coordinate"
    if _ID_NAME.search(str(column)):
        return "identifier"
    if _word(column, _YEAR_WORDS):
        return "year"
    return None


def is_quantity(column: str | None) -> bool:
    """False for a column that must never enter a measure pool."""
    return non_additive_kind(column) is None


# Aggregations that do arithmetic on the values -- meaningless for each kind.
# Mirrors ARITHMETIC in frontend/src/lib/semanticGuard.ts.
ARITHMETIC: dict[str, frozenset[str]] = {
    "coordinate": frozenset({"sum"}),
    "identifier": frozenset({"sum", "avg", "mean", "average", "median", "stddev", "variance"}),
    "year": frozenset({"sum", "avg", "mean", "average"}),
}

#: The aggregation that DOES mean something for each kind: the one-click fix.
SAFE_AGGREGATION: dict[str, str] = {"coordinate": "avg", "identifier": "countd", "year": "max"}
_SAFE_WORD = {"avg": "Average", "countd": "Distinct count", "max": "Maximum"}


def aggregation_refusal(column: str | None, aggregation: str | None) -> str | None:
    """Why (column, aggregation) is refused, or None when it means something.

    The same sentences the builder shows as a warning, so a reader of a
    refused widget and its author read one explanation."""
    kind = non_additive_kind(column)
    agg = str(aggregation or "").lower()
    if not kind or agg not in ARITHMETIC[kind]:
        return None
    what = "Summing" if agg == "sum" else "Averaging"
    fix = (f"Use {_SAFE_WORD[SAFE_AGGREGATION[kind]]} instead, or -- if {column} really is "
           f"a quantity -- mark it as a measure in the field list.")
    if kind == "coordinate":
        return f"{what} {column} adds up map coordinates -- the result is not a place. {fix}"
    if kind == "identifier":
        return f"{what} {column} does arithmetic on identifiers -- the result means nothing. {fix}"
    return f"{what} {column} adds up years -- the result is not a year. {fix}"


def config_refusal(config: dict, column_meta: dict | None, *,
                   sums_by_default: bool) -> dict | None:
    """The first measure in a widget config that is aggregated meaninglessly.

    Returns {"column", "aggregation", "safe", "message"} or None. A column the
    author marked as a measure (column_meta role) is their explicit statement
    that it IS a quantity, and passes. `sums_by_default` is whether this widget
    type sums a measure that names no aggregation (a bar does; a histogram
    plots raw values and does not)."""
    meta = column_meta or {}
    roles = config.get("roles") if isinstance(config.get("roles"), dict) else {}
    pairs = [
        (config.get("measure") or roles.get("measure"),
         config.get("aggregation") or config.get("agg")),
        (config.get("measure2") or roles.get("measure2"),
         config.get("aggregation2") or config.get("aggregation") or config.get("agg")),
    ]
    for column, agg in pairs:
        if not isinstance(column, str) or not column:
            continue
        if agg is None and not sums_by_default:
            continue
        agg = agg or "sum"
        if (meta.get(column) or {}).get("role") == "measure":
            continue
        message = aggregation_refusal(column, agg)
        if message:
            kind = non_additive_kind(column)
            return {"column": column, "aggregation": str(agg).lower(),
                    "safe": SAFE_AGGREGATION[kind], "message": message}
    return None
