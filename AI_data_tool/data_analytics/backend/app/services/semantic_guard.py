"""The semantic veto, backend half (MASTER_PLAN Phase 0, constitution rule 3).

A column can be numeric without being a quantity. Summing, averaging,
correlating or trending a latitude, an identifier or a year returns a number
every time, with no error, and the number means nothing -- the suggestion
engine SAS ships proposes summed latitudes for exactly this reason.

A column's STORED classification (column_meta: number / level / order /
direction / outcome -- see below) is read first; its NAME is the fallback for
a column nobody classified. Mirrors frontend/src/lib/semanticGuard.ts;
`tests/test_semantic_guard.py` pins the two to the same examples so they
cannot drift. Pure: no pandas, no FastAPI.
"""
from __future__ import annotations

import re

# THE VOCABULARY HERE IS NEUTRAL ON PURPOSE. Datalytics is a general-purpose
# platform: these lists hold only words about MEASUREMENT and STRUCTURE (an
# id, a year, a rate, an average, a price) that mean the same in every kind of
# organisation, in English and Arabic. No word of one business area (a
# salary, a seller, an IMEI, a mileage) belongs here: what such a column is
# comes from its VALUES and from the classification stored once per column
# (services/column_classes.py -- measured, asked of the model, or set by the
# author), never from a built-in list of one industry's nouns.
_ID_NAME = re.compile(r"(^id$|_id$|_ref$|_key$|_uuid$|^uuid$|_code$"
                      # Numbers that name something (A_NUMBER, serial_no).
                      r"|^number$|_number$|_no$"
                      r"|^(رقم|كود|معرف|مسلسل)(_|$)|(^|_)(رقم|كود|معرف)$)", re.I)
_COORD_WORDS = ("lat", "latitude", "lon", "lng", "long", "longitude", "خط_العرض", "خط_الطول")
_YEAR_WORDS = ("year", "yr", "fiscal_year", "سنة", "السنة", "عام")


def _word(name: str, words) -> bool:
    low = re.sub(r"[\s\-.]+", "_", str(name).strip().lower())
    return any(low == w or low.endswith("_" + w) or low.startswith(w + "_")
               or ("_" + w + "_") in low for w in words)


# ── The stored classification: what the column IS, read before its name ──────
# docs/suggestions/PLAN.md, phase 1. A column's classification is decided once
# (services/column_classes.py: measured on the rows, named by the model,
# corrected by the author) and kept in `column_meta`. Every function below
# takes that map and lets it outrank the name: `val2` recorded as a score is
# averaged, `number` recorded as an amount is summed. The name is the fallback
# for a column nobody classified yet -- which is what it was always good for.
NUMBER_KINDS = ("amount", "count", "level", "duration", "score", "share", "code")
#: Kinds whose TOTAL over many rows means something.
ADDITIVE_KINDS = frozenset({"amount", "count"})
#: Kinds that are averaged and never totalled.
INTENSIVE_KINDS = frozenset({"level", "duration", "score", "share"})
DIRECTIONS = ("higher_better", "higher_worse", "neither")
LEVELS = ("nominal", "ordinal", "interval", "ratio")
GEO_LEVELS = ("country", "region", "city", "postcode", "latitude", "longitude")


def _entry(column: str | None, column_meta: dict | None) -> dict:
    meta = (column_meta or {}).get(column) if column else None
    return meta if isinstance(meta, dict) else {}


def meta_of(profile: dict | None) -> dict:
    """The stored classification as a `column_meta`-shaped map, read back out
    of a dataset profile -- for the steps that are handed a profile and not
    the dataset (the designers' repair and polish passes)."""
    out: dict = {}
    for c in (profile or {}).get("columns") or []:
        if isinstance(c, dict) and c.get("number") in NUMBER_KINDS:
            out[c["name"]] = {"number": c["number"], "class_source": "confirmed"}
    return out


def recorded_number(column: str | None, column_meta: dict | None) -> str | None:
    """The kind of number this column was classified as, or None when nobody
    classified it. A person's authored role still wins over a GUESSED kind:
    a column they marked a measure is not a code because detection said so."""
    meta = _entry(column, column_meta)
    kind = meta.get("number")
    if kind not in NUMBER_KINDS:
        return None
    if kind == "code" and marked_measure(meta) and meta.get("class_source") != "confirmed":
        return None
    return kind


def direction_of(column: str | None, column_meta: dict | None) -> str:
    """higher_better | higher_worse | neither -- which way 'best' points."""
    d = _entry(column, column_meta).get("direction")
    return d if d in DIRECTIONS else "neither"


TARGET_PERIODS = ("month", "quarter", "year")


def target_of(column: str | None, column_meta: dict | None) -> tuple[float, str | None] | None:
    """(value, period) of the target the AUTHOR stored for this column, or
    None. `period` is month | quarter | year, or None for a target on the
    whole of what is shown. Never inferred: a column with none has none."""
    meta = _entry(column, column_meta)
    try:
        value = float(meta.get("target"))
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    period = meta.get("target_period")
    return value, (period if period in TARGET_PERIODS else None)


def value_order(column: str | None, column_meta: dict | None) -> list[str] | None:
    """The values of an ordinal column in their real order, or None."""
    meta = _entry(column, column_meta)
    order = meta.get("order")
    return [str(v) for v in order] if meta.get("level") == "ordinal" and isinstance(order, list) and order else None


def is_outcome(column: str | None, column_meta: dict | None) -> bool:
    """A column that says what became of a row (late, returned, resolved)."""
    return _entry(column, column_meta).get("outcome") is True


def non_additive_kind(column: str | None, column_meta: dict | None = None) -> str | None:
    """'coordinate' | 'identifier' | 'year' | None."""
    if not column:
        return None
    # A stored latitude or longitude is a coordinate whatever kind of number
    # it was also given: averaged for a centre, never added up.
    if _entry(column, column_meta).get("geo_level") in ("latitude", "longitude"):
        return "coordinate"
    kind = recorded_number(column, column_meta)
    if kind is not None:
        # Classified: a code is never calculated; anything else IS a quantity,
        # whatever its name looks like.
        return "identifier" if kind == "code" else None
    if _word(column, _COORD_WORDS):
        return "coordinate"
    if _ID_NAME.search(str(column)):
        return "identifier"
    if _word(column, _YEAR_WORDS):
        return "year"
    return None


def is_quantity(column: str | None, column_meta: dict | None = None) -> bool:
    """False for a column that must never enter a measure pool: an identifier
    (by its stored role, or named like one), a coordinate, a year."""
    meta = _entry(column, column_meta)
    if meta.get("role") == "identifier":
        # The person's own word for the column: it was left to the name alone,
        # so a key they had marked still joined every correlation.
        return False
    return non_additive_kind(column, column_meta) is None


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


def aggregation_refusal(column: str | None, aggregation: str | None,
                        column_meta: dict | None = None) -> str | None:
    """Why (column, aggregation) is refused, or None when it means something.

    The same sentences the builder shows as a warning, so a reader of a
    refused widget and its author read one explanation."""
    kind = non_additive_kind(column, column_meta)
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
        message = aggregation_refusal(column, agg, meta)
        if message:
            kind = non_additive_kind(column, meta)
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
    # How a number is MEASURED, not what business it belongs to.
    "price", "unit_price", "unit_cost", "rate", "ratio", "percent", "percentage", "pct", "share",
    "avg", "average", "mean", "median", "age", "score", "grade", "rating",
    "temperature", "temp", "speed", "margin", "probability", "prob", "index", "level",
    "سعر", "السعر", "نسبة", "النسبة", "معدل", "المعدل", "متوسط", "المتوسط", "عمر", "العمر",
    "درجة", "الدرجة", "تقييم", "التقييم",
)
_INTENSIVE_INFIX = re.compile(r"(^|_)per(_|$)", re.I)
#: A distinct count already taken per row -- a DAILY count of unique customers
#: or active sellers. Summed over days it counts the same customer once per
#: day: "Active sellers in 2018-08 ran 62% above its monthly average" was a sum
#: of daily seller counts (five-dataset gap review, 2026-10-02). Averaged, it is
#: the typical day.
_DISTINCT_SNAPSHOT = re.compile(
    r"(^|_)(unique|distinct|dau|mau|wau)(_|$)|"
    r"(^|_)active_(users|accounts|members|clients|visitors|devices|sessions)$",
    re.I)

#: The values ColumnMeta.aggregation may carry that set a default summary.
_SUMMARY_ALIASES = {"sum": "sum", "avg": "avg", "mean": "avg", "average": "avg",
                    "median": "median", "count": "count", "countd": "countd",
                    "distinct": "countd", "nunique": "countd", "min": "min",
                    "max": "max", "none": "none", "raw": "none"}


def is_intensive(column: str | None, column_meta: dict | None = None) -> bool:
    """True for a quantity whose SUM over a group is meaningless (salary,
    price, rate, age, score...). The stored classification first; the name
    for a column nobody classified."""
    if not column:
        return False
    kind = recorded_number(column, column_meta)
    if kind is not None:
        return kind in INTENSIVE_KINDS
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
    recorded = recorded_number(column, column_meta)
    if recorded is not None:
        # The stored classification: a code is counted, an amount or a count
        # is added up, a level / duration / score / share is averaged.
        return "countd" if recorded == "code" else "sum" if recorded in ADDITIVE_KINDS else "avg"
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
    return non_additive_kind(column, column_meta) == "identifier"
