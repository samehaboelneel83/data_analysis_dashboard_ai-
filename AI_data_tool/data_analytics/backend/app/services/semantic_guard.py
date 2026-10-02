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

_ID_NAME = re.compile(r"(^id$|_id$|_key$|_uuid$|^uuid$|_code$"
                      # Numbers that name something (A_NUMBER, phone_number, invoice_no) and the
                      # telecom identifiers a call record carries (live QA 2026-09-28: IMEI
                      # summed to 1.1e17 and "66% of A_NUMBER" led the insights).
                      r"|^number$|_number$|_no$|(^|_)(imei|imsi|msisdn|iccid|lac)$)", re.I)
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


def marked_measure(meta: dict | None) -> bool:
    """Whether a PERSON (or the catalog) said this column is a quantity.

    The metadata automation also writes roles, marked `role_source:
    "inferred"`; it called `hire_year` a measure, and that guess then
    overrode the veto, so "Total hire year" was summed on the workforce
    dashboard (five-dataset review, 2026-10-02). A guess does not get to
    override the rule; only an authored role does."""
    meta = meta if isinstance(meta, dict) else {}
    return meta.get("role") == "measure" and meta.get("role_source") != "inferred"


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
        if marked_measure(meta.get(column)):
            continue
        message = aggregation_refusal(column, agg)
        if message:
            kind = non_additive_kind(column)
            return {"column": column, "aggregation": str(agg).lower(),
                    "safe": SAFE_AGGREGATION[kind], "message": message}
    return None


# ── Default summary: what a measure MEANS when it is rolled up ───────────────
# HR evaluation, blocker 5: every engine summed salary. "M has 60% of salary",
# "salary in 1999-12 ran 98% below its monthly average" and a KPI of
# 17,291,866,123 are all head-counts in disguise. A salary, a price, a rate or
# an age is an INTENSIVE quantity: its total over a group means nothing to a
# reader, its average does. Additive quantities (amount, revenue, cost, units,
# minutes) keep summing.
_INTENSIVE_WORDS = (
    "salary", "salaries", "wage", "wages", "pay", "price", "unit_price",
    "unit_cost", "rate", "ratio", "percent", "percentage", "pct", "share",
    "avg", "average", "mean", "median", "age", "score", "grade", "rating",
    "temperature", "temp", "speed", "margin", "probability", "prob", "index",
    "level", "gpa", "bmi", "tenure_years",
)
_INTENSIVE_INFIX = re.compile(r"(^|_)per(_|$)", re.I)
#: A distinct count already taken per row -- a DAILY count of unique customers
#: or active sellers. Summed over days it counts the same customer once per
#: day: "Active sellers in 2018-08 ran 62% above its monthly average" was a sum
#: of daily seller counts (five-dataset gap review, 2026-10-02). Averaged, it is
#: the typical day.
_DISTINCT_SNAPSHOT = re.compile(
    r"(^|_)(unique|distinct|dau|mau|wau)(_|$)|"
    r"(^|_)active_(users|customers|sellers|members|accounts|subscribers|clients|visitors|devices)$",
    re.I)

#: The values ColumnMeta.aggregation may carry that set a default summary.
_SUMMARY_ALIASES = {"sum": "sum", "avg": "avg", "mean": "avg", "average": "avg",
                    "median": "median", "count": "count", "countd": "countd",
                    "distinct": "countd", "nunique": "countd", "min": "min",
                    "max": "max", "none": "none", "raw": "none"}


def is_intensive(column: str | None) -> bool:
    """True for a quantity whose SUM over a group is meaningless (salary,
    price, rate, age, score...). Classified by name, like the veto above."""
    if not column:
        return False
    low = str(column).lower()
    return (_word(low, _INTENSIVE_WORDS) or bool(_INTENSIVE_INFIX.search(low))
            or bool(_DISTINCT_SNAPSHOT.search(low)))


def default_summary(column: str | None, column_meta: dict | None = None) -> str:
    """How `column` should be rolled up when nobody said: 'sum' | 'avg' |
    'countd' | 'median' | 'min' | 'max' | 'count' | 'none'.

    Precedence: the author's recorded aggregation, then the recorded role
    (an identifier is counted, never summed), then the name."""
    meta = (column_meta or {}).get(column) if column else None
    meta = meta if isinstance(meta, dict) else {}
    agg = str(meta.get("aggregation") or "").strip().lower()
    if agg in _SUMMARY_ALIASES:
        return _SUMMARY_ALIASES[agg]
    if meta.get("role") == "identifier":
        return "countd"
    kind = non_additive_kind(column)
    if kind and not marked_measure(meta):
        return SAFE_AGGREGATION[kind]
    return "avg" if is_intensive(column) else "sum"


def is_identifier(column: str | None, column_meta: dict | None = None) -> bool:
    """A recorded identifier, or one named like one and not marked a measure."""
    meta = (column_meta or {}).get(column) if column else None
    meta = meta if isinstance(meta, dict) else {}
    if meta.get("role") == "identifier":
        return True
    if marked_measure(meta):
        return False
    return non_additive_kind(column) == "identifier"
