"""
Widget Data Service
===================
Executes aggregation queries on dataset files and returns chart-ready JSON.

Supported aggregations
----------------------
  Numeric measures:
    sum          → total sum
    avg / mean   → arithmetic mean
    min          → minimum value
    max          → maximum value
    median       → 50th percentile
    count        → row count (non-null)
    countd       → distinct value count
    std          → standard deviation
    variance     → variance
    range        → max − min
    p25          → 25th percentile
    p75          → 75th percentile
    p90          → 90th percentile
    p95          → 95th percentile

  Categorical / all columns:
    frequency    → count of occurrences per group (same as count)
    pct          → percentage share per group
    cumulative   → cumulative sum

  Running metrics (applied after groupby):
    running_sum  → cumulative sum over ordered result
    running_avg  → cumulative mean over ordered result

  Date / time intelligence:
    year         → extract year from datetime
    quarter      → extract quarter from datetime
    month        → extract month from datetime
    day          → extract day from datetime
    datetrunc    → truncate datetime to specified unit (year/quarter/month/week/day)
    ytd          → year-to-date cumulative sum, resetting at year boundary
    sameperiodlastyear  → sum from same month one year prior (for YoY comparison)
    yoy_growth   → year-over-year percentage growth
"""

import copy
import datetime as _dt
import json
import os
import re
import threading
import time
from collections import OrderedDict
import pandas as pd
import numpy as np
from typing import Callable
from .ingest import load_file, detect_types
from . import measure_eval as _measure_eval
from .query_log import log_query_run_sync
from .cache_backend import InProcessCache, ValkeyCache
from ..core import telemetry
from ..core.config import settings


# `_safe` moved to widget_shaping.py so direct_query.py stops importing a
# private name across module boundaries. Re-exported here under its original
# name: routers/datasets.py and others import it from this module.
from .widget_shaping import safe as _safe  # noqa: E402


# Zero-padded date-like labels: 2024-07, 2024-07-15, 2024/07/15 10:00, 2025-Q1,
# 2025-W07. Each sorts chronologically as a plain string, which is what makes it
# safe to order a text column by name. "2024-7" does not qualify: as text it
# sorts after "2024-10", and a wrong time order is worse than a value order.
_TIME_TEXT = re.compile(r"^\d{4}(?:[-/]\d{2}(?:[-/]\d{2}(?:[ T][\d:.]+)?)?|-Q[1-4]|-W\d{2})$")


def _looks_like_time_text(s: pd.Series) -> bool:
    """True when a text column's values are (almost all) date-like labels."""
    if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return False
    vals = s.dropna().astype(str).head(200)
    if vals.empty:
        return False
    return bool(vals.str.match(_TIME_TEXT).mean() >= 0.9)


class ImportRowCapExceeded(Exception):
    """The source frame is larger than `settings.import_row_cap`.

    DirectQuery has always been bounded (`direct_query.DEFAULT_ROW_CAP`); the
    import/pandas path was not, so one widget could materialise an entire
    dataset to answer a five-row question. Measured 2026-08-28: a 406 MB,
    2M-row, 30-column CSV costs ~1.8 GB of RSS on this path, and each
    concurrent render holds its own frame.

    This FAILS rather than truncating. A truncated frame would return totals
    computed over an arbitrary subset with no way to say so in the result --
    a confident wrong number, which is worse than an error. The message names
    the cap so an operator can raise it deliberately.
    """


def _record_widget_metrics(executor: str, cache_hit: bool, duration_ms: int) -> None:
    """Emit the widget-query metrics for one render.

    One helper rather than three inline call sites, because there are three
    return paths through `get_widget_data` (cache hit, DuckDB, pandas) and a
    metric that is missing from one of them silently skews every rate computed
    from it.

    `telemetry.*` is looked up on the module, never imported by name: the
    instruments are reassigned when otel is enabled, and a `from` import would
    freeze the disabled no-op. When otel is off these are no-op objects, so this
    costs an attribute lookup and a discarded call.
    """
    attrs = {"executor": executor, "cache_hit": str(cache_hit).lower()}
    telemetry.widget_query_total.add(1, attrs)
    telemetry.widget_query_duration.record(duration_ms, attrs)
    telemetry.cache_operations.add(1, {"result": "hit" if cache_hit else "miss"})


def load_file_columns(file_path: str) -> list[str]:
    """The dataset's column names, without materialising the frame.

    Used by the DuckDB pushdown gate to validate identifiers before they reach
    SQL. Reading the whole file to learn its column names would defeat the point
    of not reading the whole file, so this reads the header only.
    """
    from pathlib import Path

    p = Path(file_path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return list(pd.read_csv(p, nrows=0).columns)
    if suffix == ".parquet":
        # Schema from the footer, not a read: pd.read_parquet(...).head(0) would
        # load every row group first.
        import pyarrow.parquet as pq

        return list(pq.read_schema(p).names)
    # Other formats have no cheap header read; the caller falls back to pandas,
    # which is the correct-but-slower path anyway.
    return []


def _enforce_import_row_cap(df, file_path: str) -> None:
    """Reject a source frame above the configured ceiling.

    No-op when the cap is 0, which an operator with the memory to spare can
    still set. It is NOT the default: that became 2,000,000 on 2026-08-29,
    because uncapped, one oversized upload exhausts the container for every
    tenant on it and the failure arrives as an OOM kill with no attribution.
    """
    cap = settings.import_row_cap
    if cap and len(df) > cap:
        raise ImportRowCapExceeded(
            f"Dataset has {len(df):,} rows, above the import row cap of {cap:,}. "
            "Raise `import_row_cap`, or use a DirectQuery data source, which "
            "pushes aggregation into SQL instead of loading the whole table."
        )


# ── Aggregation function map ──────────────────────────────────────────────────
#: Every aggregation name the pandas engine implements -- the scalar path
#: (`_agg_series`) and the grouped path (`_pandas_agg_fn`) alike, which
#: tests/test_widget_contract.py pins. Both paths fall back to SUM for a name
#: they do not know, so an unknown name is not an error at read time: it is a
#: silently different number. `widget_roles.validate_widget_payload` refuses
#: such a name when a widget is SAVED, which is the only place it can be told.
AGGREGATION_NAMES = frozenset({
    "sum", "none", "raw", "first", "avg", "mean", "average", "min", "minimum",
    "max", "maximum", "median", "count", "frequency", "countd", "distinct",
    "std", "stdev", "variance", "var", "range", "p25", "p75", "p90", "p95",
    "stderr", "sem", "standard_error", "skewness", "skew", "kurtosis", "kurt",
    "cv", "coefficient_of_variation", "uss", "uncorrected_sum_of_squares",
    "css", "corrected_sum_of_squares", "tstat", "t_statistic", "pvalue", "p_value",
})


def _agg_series(series: pd.Series, agg: str) -> float | None:
    """Apply a named aggregation to a pandas Series."""
    s = series.dropna()
    if len(s) == 0:
        return None
    agg = agg.lower()
    if agg in ("sum",):                  return _safe(s.sum())
    if agg in ("none", "raw", "first"):  return _safe(s.iloc[0])
    if agg in ("avg", "mean", "average"): return _safe(s.mean())
    if agg in ("min", "minimum"):        return _safe(s.min())
    if agg in ("max", "maximum"):        return _safe(s.max())
    if agg in ("median",):               return _safe(s.median())
    if agg in ("count", "frequency"):    return int(s.count())
    if agg in ("countd", "distinct"):    return int(s.nunique())
    if agg in ("std", "stdev"):          return _safe(s.std())
    if agg in ("variance", "var"):       return _safe(s.var())
    if agg in ("range",):                return _safe(s.max() - s.min())
    if agg in ("p25",):                  return _safe(s.quantile(.25))
    if agg in ("p75",):                  return _safe(s.quantile(.75))
    if agg in ("p90",):                  return _safe(s.quantile(.90))
    if agg in ("p95",):                  return _safe(s.quantile(.95))

    # The statistical half of SAS's aggregation menu. Each returns None when
    # the sample cannot support it -- skewness of two points and a t statistic
    # of one are artefacts of the formula, and a dashboard that draws them is
    # stating something the data cannot.
    if agg in ("stderr", "sem", "standard_error"):
        return _safe(s.sem()) if len(s) > 1 else None
    if agg in ("skewness", "skew"):
        return _safe(s.skew()) if len(s) > 2 else None
    if agg in ("kurtosis", "kurt"):
        return _safe(s.kurt()) if len(s) > 3 else None
    if agg in ("cv", "coefficient_of_variation"):
        mean = s.mean()
        # A mean of zero has no coefficient of variation -- the ratio is not
        # large, it is undefined, and returning a huge number would read as
        # "extremely variable" rather than "not a question".
        return _safe(s.std() / mean * 100) if mean != 0 else None
    if agg in ("uss", "uncorrected_sum_of_squares"):
        return _safe((s ** 2).sum())
    if agg in ("css", "corrected_sum_of_squares"):
        return _safe(((s - s.mean()) ** 2).sum())
    if agg in ("tstat", "t_statistic"):
        return _safe(s.mean() / s.sem()) if len(s) > 1 and s.sem() else None
    if agg in ("pvalue", "p_value"):
        if len(s) < 2:
            return None
        from scipy import stats as _stats
        return _safe(float(_stats.ttest_1samp(s, 0.0).pvalue))
    return _safe(s.sum())   # default fallback


def _p_value_of_mean(x):
    """Two-sided p-value for "this group's mean is zero".

    A named function rather than a lambda so the scipy import stays inside it:
    `widget_data` is on the app-import path and scipy is not something every
    request should pay for.
    """
    values = x.dropna()
    if len(values) < 2:
        return None
    from scipy import stats as _stats
    return float(_stats.ttest_1samp(values, 0.0).pvalue)


def _pandas_agg_fn(agg: str):
    """Return a pandas-compatible aggregation string or lambda."""
    agg = agg.lower()
    mapping = {
        "sum": "sum", "avg": "mean", "mean": "mean", "average": "mean",
        "none": "first", "raw": "first", "first": "first",
        "min": "min", "minimum": "min", "max": "max", "maximum": "max",
        "median": "median", "count": "count", "frequency": "count",
        "countd": "nunique", "distinct": "nunique",
        "std": "std", "stdev": "std", "variance": "var", "var": "var",
        "range": lambda x: x.max() - x.min(),
        "p25": lambda x: x.quantile(.25),
        "p75": lambda x: x.quantile(.75),
        "p90": lambda x: x.quantile(.90),
        "p95": lambda x: x.quantile(.95),
        # Same statistics as the scalar path above, and deliberately the same
        # guards: a KPI and a bar chart disagreeing about one number is worse
        # than neither offering it.
        "stderr": lambda x: x.sem() if x.count() > 1 else None,
        "sem": lambda x: x.sem() if x.count() > 1 else None,
        "skewness": lambda x: x.skew() if x.count() > 2 else None,
        "skew": lambda x: x.skew() if x.count() > 2 else None,
        "kurtosis": lambda x: x.kurt() if x.count() > 3 else None,
        "kurt": lambda x: x.kurt() if x.count() > 3 else None,
        "cv": lambda x: (x.std() / x.mean() * 100) if x.mean() != 0 else None,
        "uss": lambda x: (x ** 2).sum(),
        "css": lambda x: ((x - x.mean()) ** 2).sum(),
        "tstat": lambda x: (x.mean() / x.sem()) if x.count() > 1 and x.sem() else None,
        "pvalue": _p_value_of_mean,
    }
    # The long spellings the scalar path has always accepted. Missing here, a
    # KPI on "standard_error" showed the standard error while a bar chart with
    # the same config silently showed a SUM -- the fallback below.
    for long, short in (("standard_error", "stderr"), ("coefficient_of_variation", "cv"),
                        ("uncorrected_sum_of_squares", "uss"),
                        ("corrected_sum_of_squares", "css"),
                        ("t_statistic", "tstat"), ("p_value", "pvalue")):
        mapping[long] = mapping[short]
    return mapping.get(agg, "sum")


def _total_over_rows(df: pd.DataFrame, keys: list[str], meas: str | None, agg_fn):
    """A total or subtotal, aggregated from the SOURCE rows at its own grain.

    Never an aggregate of the displayed cells: for avg, median, countd or any
    non-additive aggregation, the average of group averages is not the average,
    and the sum of per-group distinct counts is not the distinct count. `agg_fn`
    is the one the cells used (`_pandas_agg_fn`), so a total and its cells are
    always the same statistic. `keys=[]` is the grand total, returned as a scalar;
    otherwise a Series indexed by the key values. No measure means a row count,
    matching the shaper's own no-measure branches.
    """
    grand = not keys
    if grand:
        df = df.assign(__grand__=0)
        keys = ["__grand__"]
    grouped = df.groupby(keys)
    series = grouped[meas].agg(agg_fn) if meas else grouped.size()
    if grand:
        return series.iloc[0] if len(series) else None
    return series


#: Quick calcs whose values are not in the measure's units: a raw-row total beside
#: a column of differences or ranks would be a different quantity wearing a
#: "Total" label, so these withhold the total and say why.
_QUICK_CALCS_WITHOUT_TOTAL = frozenset({"difference", "percent_change", "rank"})


def _series_totals(df, dim, dim_key, grouped, meas, agg, agg_fn, measure_def,
                   suppressed_keys, other_index, other_keys, quick_calc, pct_base) -> dict:
    """The grand total of a grouped table, on two bases, from the source rows.

    - "all": every row that reached grouping, whatever HAVING, rank or `limit` then
      kept on screen -- minus the rows of suppressed groups, which must never be
      recoverable as (total - visible cells).
    - "shown": only the rows of the groups actually displayed (the All Other
      bucket counts as displayed, standing for the rows it absorbed). Emitted
      only when it differs from "all".

    Both are the configured aggregation applied to rows, so an avg total is the
    average of every row -- not the sum, or the mean, of the group averages.
    Returns {"all", "shown"?, "basis"} or {"unavailable": reason}.
    """
    if quick_calc in _QUICK_CALCS_WITHOUT_TOTAL:
        return {"unavailable": "quick_calc"}

    # groupby drops rows whose key is missing, so they are in no displayed group.
    rows_all = df[df[dim].notna()]
    if suppressed_keys:
        rows_all = rows_all[~rows_all[dim].isin(suppressed_keys)]
    shown_keys = [k for i, k in zip(grouped.index, grouped[dim_key]) if i != other_index]
    if other_index is not None and other_index in grouped.index:
        shown_keys += other_keys
    rows_shown = rows_all[rows_all[dim].isin(shown_keys)]
    src_meas = meas if meas and meas in df.columns else None

    def total(rows):
        if quick_calc == "percent_of_total":
            # Shares of the surviving categories: the whole is 100 by construction,
            # and shares are additive, so the page's total is the sum of its rows.
            return 100.0 if rows is rows_all else _safe(grouped["value"].sum())
        if agg == "pct":
            # Each group's share of the grand base; a set of rows' share is its own
            # aggregate over that same base.
            part = _total_over_rows(rows, [], src_meas, agg_fn)
            return _safe(round(float(part) / float(pct_base) * 100, 2)) if part is not None and pct_base else None
        if measure_def is not None:
            return _safe(_measure_eval.evaluate_measure(measure_def["expression"], rows, []))
        return _safe(_total_over_rows(rows, [], src_meas, agg_fn))

    truncated = len(rows_shown) < len(rows_all)
    out = {
        "all": total(rows_all),
        "basis": {"unit": "groups", "shown": len(grouped), "of": int(rows_all[dim].nunique()),
                  "truncated": truncated, "suppressed_excluded": bool(suppressed_keys)},
    }
    if truncated:
        out["shown"] = total(rows_shown)
    return out


#: Mirrors infer_semantic.classify_role's name check (metadata/infer_semantic.py:111)
#: for the same reason a bubble's "color" role needs it: an id-like numeric column
#: (state_id, student_id, ...) is a category wearing a numeric dtype, not a measure,
#: and summing/ramping it is meaningless. A tiny mirror rather than an import — this
#: module runs per-request against a loaded (and possibly already filtered) dataframe,
#: not against the metadata plane's whole-column statistics, so classify_role's OTHER
#: signal — near-uniqueness of distinct/row counts — is deliberately not replicated
#: here: a filtered slice of a few dozen rows makes an ordinary continuous measure
#: (revenue, temperature, ...) look "near-unique" by chance, which would misclassify
#: it as an identifier. The name check alone is the reliable part of the heuristic at
#: this layer.
_ID_NAME_PATTERN = re.compile(r"(^id$|_id$|_key$|_uuid$|^uuid$|_code$)", re.I)


def _is_id_like_column(col: str) -> bool:
    """True when `col`'s name matches the identifier pattern (id, state_id, ...)."""
    return bool(_ID_NAME_PATTERN.search(col))


def _dimension_granularity_label(series: pd.Series, granularity: str) -> pd.Series:
    """Truncates a datetime series to a stable label per bucket for grouping/drilling.
    Distinct from the calc-column formula language's DATETRUNC, which returns a real
    datetime (period start) for date arithmetic -- this returns a display/filter label."""
    dt = series if pd.api.types.is_datetime64_any_dtype(series) else pd.to_datetime(series, errors="coerce")
    granularity = (granularity or "").lower()
    if granularity == "year":
        # Whole numbers, not `dt.dt.year` as it comes: one missing date turns
        # that int64 column into float64 and every label with it. Plain ints
        # with NaN for the missing row -- the same missing value strftime
        # leaves for month and day, and `.where` leaves for quarter and week
        # -- rather than a nullable-int column, whose gap stringifies as the
        # text "<NA>" (see the note below). The row builder in shape_series
        # has to keep them whole too; see its zip() over the columns.
        return dt.dt.year.astype("Int64").astype(object).where(dt.notna())
    # Quarter and week are built by string concatenation over nullable ints,
    # and `Int64.astype(str)` renders a missing value as the text "<NA>" --
    # so a null date used to become the LABEL "<NA>-Q<NA>", a garbage bar on
    # any chart with one missing date, and one that defeated the no-dates-here
    # guard in _bucket_dimension because a string is never NA. Masked back to
    # missing, which is what strftime already does for month and day.
    if granularity == "quarter":
        label = dt.dt.year.astype("Int64").astype(str) + "-Q" + dt.dt.quarter.astype("Int64").astype(str)
        return label.where(dt.notna())
    if granularity == "month":
        return dt.dt.strftime("%Y-%m")
    if granularity == "week":
        # ISO year-week, not `%Y-%W`. The ISO year is what keeps the last days of
        # December with the week they actually belong to: 2025-12-29 is ISO
        # 2026-W01, and pairing it with calendar year 2025 would split one week
        # across two labels. Zero-padded so the axis sorts as text, which is how
        # every chart here orders its categories.
        iso = dt.dt.isocalendar()
        label = iso["year"].astype("Int64").astype(str) + "-W" + \
            iso["week"].astype("Int64").astype(str).str.zfill(2)
        return label.where(dt.notna())
    if granularity == "day":
        return dt.dt.strftime("%Y-%m-%d")
    if granularity in ("hijri_month", "hijri_year"):
        # Phase 7.5: the tabular Hijri calendar, labelled 1448-03 / 1448.
        from .hijri import hijri_label
        return hijri_label(dt.dt.tz_localize(None) if getattr(dt.dt, "tz", None) is not None else dt, granularity)
    raise ValueError(f"Unsupported granularity: {granularity}")


def _bucket_dimension(series: pd.Series, granularity: str) -> pd.Series:
    """Bucket a dimension by `granularity`, or hand it back untouched.

    `dimension_granularity` is written by the config panel for whatever widget is
    selected, so it can arrive attached to a column that holds no dates at all --
    a department name, say, left over from switching the dimension. Labelling that
    coerces every value to NaT and the widget renders one empty category where it
    used to render the data.

    Text dates must still bucket: a CSV column of "2025-01-05" is not
    datetime64, parses cleanly, and authors group it by month all the time. So the
    test is the outcome rather than the dtype -- if nothing parsed, there were no
    dates here and the instruction did not apply.
    """
    labels = _dimension_granularity_label(series, granularity)
    return series if labels.isna().all() else labels


def _apply_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    # Relative date filters ("last 30 days") resolve against the frame as it
    # arrives -- before any other filter narrows it -- so a data_max anchor is
    # the data's coverage. Usually already resolved by get_widget_data_from_df;
    # this catches the callers that filter without going through it.
    from .relative_dates import apply_date_range, has_relative, resolve_filters
    if has_relative(filters):
        filters, _ = resolve_filters(df, filters)
    for f in filters:
        col, op, val = f.get("column"), f.get("op"), f.get("value")
        if op == "date_range":
            df = apply_date_range(df, f)
            continue
        if not col or col not in df.columns:
            continue
        try:
            if op == "eq":
                granularity = f.get("granularity")
                if granularity:
                    truncated = _dimension_granularity_label(df[col], granularity)
                    df = df[truncated.astype(str) == str(val)]
                else:
                    df = df[df[col].astype(str) == str(val)] if df[col].dtype == object else df[df[col] == val]
            elif op == "neq":  df = df[df[col] != val]
            elif op == "gt":   df = df[df[col] > val]
            elif op == "lt":   df = df[df[col] < val]
            elif op == "gte":  df = df[df[col] >= val]
            elif op == "lte":  df = df[df[col] <= val]
            elif op == "in":   df = df[df[col].isin(val if isinstance(val, list) else [val])]
            elif op == "like": df = df[df[col].astype(str).str.contains(str(val), case=False, na=False)]
        except Exception:
            pass
    return df


def shape_series(df: pd.DataFrame, config: dict) -> dict:
    """
    Main query entry point.  config keys:
      dimension    str    – grouping / X-axis column
      dimension2   str    – second grouping (crosstab pivot)
      measure      str    – numeric column to aggregate
      aggregation  str    – aggregation name (see module docstring)
      filters      list   – [{column, op, value}, …]
      limit        int    – max result rows (default 50)
      sort         str    – 'asc' | 'desc'
      sort_by      str    – 'value' | 'name' (default 'value', but
                            'name' ascending when the dimension is a date)
      sort_col     str    – any dataset column; when set, overrides sort_by
      columns      list   – explicit column list for table/list widgets
      running      str    – 'sum' | 'avg'  apply running metric to result
    """
    filters     = config.get("filters", [])
    dim         = config.get("dimension") or None
    dim2        = config.get("dimension2") or None
    # Hierarchy EXPAND (Power BI's "expand all down one level"): group by several
    # hierarchy levels at once, the label carrying the whole path. Implemented as
    # a synthesised label column so everything downstream -- aggregation, HAVING,
    # rank, quick calcs, sort, suppression -- works on it unchanged.
    levels = config.get("dimension_levels")
    if isinstance(levels, list) and len(levels) >= 2             and all(isinstance(c, str) and c in df.columns for c in levels):
        df = df.assign(__hlabel__=df[levels[0]].astype(str))
        for extra in levels[1:]:
            df["__hlabel__"] = df["__hlabel__"] + " › " + df[extra].astype(str)
        dim = "__hlabel__" 
    meas        = config.get("measure") or None
    agg         = (config.get("aggregation") or config.get("agg") or "sum")
    agg         = agg.lower() if isinstance(agg, str) else "sum"
    limit       = int(config.get("limit") or 50)
    # measure_defs is injected server-side by get_widget_data_from_df — never trusted
    # from the request body. A measure name shadows nothing: a real column always wins.
    measure_def = None
    if meas and meas not in df.columns:
        measure_def = _measure_eval.resolve_measure(meas, config.get("measure_defs"))
    sort        = (config.get("sort") or "desc").lower()
    sort_by     = (config.get("sort_by") or "value").lower()
    sort_col    = config.get("sort_col") or None
    running     = (config.get("running") or "").lower()
    explicit_cols = config.get("columns") or []

    # 1. Apply filters
    df = _apply_filters(df, filters)
    if df.empty:
        return {"type": "empty", "rows": [], "total": 0}

    dim_granularity = config.get("dimension_granularity") or None

    # A time axis defaults to time order, not to rank order.
    #
    # `sort_by=value` is the right default for a ranking -- the ten costliest
    # departments -- and the wrong one for a series whose meaning IS the order of
    # its axis. A monthly arrivals chart defaulting to value order draws December
    # before January: every number correct, the picture meaningless.
    #
    # Decided here because this is the last moment the column's real dtype is
    # visible; the granularity relabel two lines down turns it into strings. Those
    # labels (2025-01, 2025-Q1, 2025-W07) are built to sort lexically in date
    # order, so the plain name sort below is chronological for both branches.
    #
    # Only the *unstated* case moves. An author who wrote `sort_by` gets exactly
    # what they asked for, `value` on a date included -- "which month was busiest"
    # is a real question and still has an answer.
    #
    # Two extensions, both found by building a line over a `month` column in the
    # browser: (1) a CSV-loaded month arrives as TEXT ("2024-07"), not a pandas
    # datetime, so only a text check sees it -- zero-padded ISO-like labels sort
    # chronologically as plain strings, so they qualify and nothing else does;
    # (2) the settings panel stamps `sort: "desc"` on every widget it saves, so a
    # stated direction without a stated `sort_by` is the panel's default, not the
    # author's choice, and would draw the series back to front.
    if "sort_by" not in config and dim and dim in df.columns:
        if (dim_granularity or pd.api.types.is_datetime64_any_dtype(df[dim])
                or _looks_like_time_text(df[dim])):
            sort_by = "name"
            sort = "asc"

    if dim_granularity and dim and dim in df.columns:
        df = df.copy()
        df[dim] = _bucket_dimension(df[dim], dim_granularity)

    # 2. Raw table / list — no grouping requested. aggregation=none (or raw)
    # is the same intent with a measure set: list the column's row values
    # instead of collapsing them to one Sum. Live: a SUM() calculated column
    # copied the same total onto every row; Sum then multiplied it by the
    # row count, and "removing aggregation" still defaulted back to Sum.
    if not dim and not meas:
        cols = [c for c in (explicit_cols or list(df.columns)) if c in df.columns]
    elif agg in ("none", "raw") and not dim:
        cols = [meas] if meas in df.columns else [
            c for c in (explicit_cols or list(df.columns)) if c in df.columns]
    else:
        cols = None
    if cols is not None:
        # Multi-column sort: an ordered priority list [{col, dir}], first key primary.
        # It supersedes the single sort_col when present. Unknown columns are dropped
        # rather than raising, so a config referencing a column since removed from the
        # dataset still renders. mergesort is stable, so rows equal on every key keep
        # their source order -- what "then by" tie-breaking means to a reader.
        sort_keys = [
            (k["col"], (k.get("dir") or "asc").lower() == "asc")
            for k in (config.get("sort_keys") or [])
            if isinstance(k, dict) and k.get("col") in df.columns
        ]
        if sort_keys:
            df = df.sort_values([c for c, _ in sort_keys],
                                ascending=[asc for _, asc in sort_keys], kind="mergesort")
        elif sort_col and sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=(sort == "asc"))
        sub  = df[cols].head(limit)
        result = {
            "type": "table",
            "columns": cols,
            "rows": [[_safe(v) for v in row] for row in sub.itertuples(index=False)],
            "total": len(df),
            "truncation": {"applied": len(sub) < len(df), "shown": len(sub), "of": len(df),
                           "limit": limit, "reason": "limit", "unit": "rows"},
        }
        if config.get("show_totals"):
            # Computed from df, NOT sub: sub is already truncated by `limit`, and a
            # total describing only the visible page is worse than no total at all.
            result["totals"] = [
                _safe(df[c].sum()) if pd.api.types.is_numeric_dtype(df[c]) else None
                for c in cols
            ]
            # The page's own total too, so the client can offer "Total (N shown)"
            # as well as the all-rows one -- same columns, only the rows on screen.
            truncated = len(sub) < len(df)
            if truncated:
                result["totals_shown"] = [
                    _safe(sub[c].sum()) if pd.api.types.is_numeric_dtype(sub[c]) else None
                    for c in cols
                ]
            result["totals_basis"] = {"unit": "rows", "shown": len(sub), "of": len(df),
                                      "truncated": truncated, "suppressed_excluded": False}
        return result

    agg_fn = _pandas_agg_fn(agg)

    # 3. Crosstab (dim + dim2)
    if dim and dim2 and dim in df.columns and dim2 in df.columns:
        # Ranking (Top/Bottom N, All Other) on the ROWS: each row ranked by its
        # own aggregate over its raw rows -- the number its subtotal shows --
        # through the shared helper, so ties, percent mode and bottom-N are the
        # bar chart's. The panel offered this on crosstabs and matrices while
        # this branch had no ranking at all: a control that saved and did
        # nothing. The heatmap's crosstab-shaped path is the model here.
        # Totals stay over EVERY source row (`full_df`); the pivot is built from
        # the kept rows, and the Other row from the excluded raw rows below.
        full_df = df
        src_meas = meas if meas in df.columns else None
        if measure_def is not None:
            row_rank_vals = _measure_eval.evaluate_measure(measure_def["expression"], df, [dim])
        else:
            row_rank_vals = _total_over_rows(df, [dim], src_meas, agg_fn)
        groups_of = int(len(row_rank_vals))
        rank_keep = _rank_selection(row_rank_vals, config)
        other_raw = None
        if rank_keep is not None:
            kept_labels = row_rank_vals.index[rank_keep]
            excluded_raw = df[~df[dim].isin(kept_labels)]
            df = df[df[dim].isin(kept_labels)]
            if (config.get("rank") or {}).get("other") and len(excluded_raw) > 0:
                other_raw = excluded_raw

        if measure_def is not None:
            # Post-aggregation measure at the INTERSECTION grain: evaluated per
            # (dim, dim2) cell, which is exactly what SAS's per-crossing
            # evaluation means. Missing intersections read 0, matching the
            # column path's fill_value.
            values = _measure_eval.evaluate_measure(measure_def["expression"], df, [dim, dim2])
            pivot = values.unstack(fill_value=0).reset_index()
        elif meas and meas in df.columns:
            pivot = df.groupby([dim, dim2])[meas].agg(agg_fn).unstack(fill_value=0).reset_index()
        else:
            pivot = df.groupby([dim, dim2]).size().unstack(fill_value=0).reset_index()

        # Row subtotals default ON: this column shipped unconditionally before it was
        # ever configurable, so defaulting it off would silently remove a column from
        # every existing crosstab. An author can turn it off; nobody loses one by upgrading.
        if config.get("show_subtotals", True):
            if measure_def is not None:
                # A measure's row subtotal is the measure RE-EVALUATED at the row
                # grain -- summing its per-cell values across columns is wrong for
                # any non-additive expression (a ratio's row total is not the sum
                # of its cell ratios).
                row_vals = _measure_eval.evaluate_measure(measure_def["expression"], df, [dim])
                pivot["__total__"] = pivot[dim].map(row_vals).fillna(0)
            else:
                # Each row's subtotal aggregated from that row's SOURCE rows, never
                # summed across its cells: for avg the row's cells are averages of
                # different-sized slices, and for countd a value present in two
                # columns would be counted twice.
                row_vals = _total_over_rows(df, [dim], meas if meas in df.columns else None, agg_fn)
                pivot["__total__"] = pivot[dim].map(row_vals).fillna(0)

        if other_raw is not None:
            # Every cell of the Other row is the same kind of number as every
            # other cell: re-aggregated (or, for a measure, re-evaluated) from
            # the excluded rows' RAW data per column, and its subtotal at no
            # column grain -- never a sum of the cells it replaces, which for
            # avg, countd or a ratio would be a different number.
            if measure_def is not None:
                other_cells = _measure_eval.evaluate_measure(measure_def["expression"], other_raw, [dim2])
                other_sub = _measure_eval.evaluate_measure(measure_def["expression"], other_raw, [])
            else:
                other_cells = _total_over_rows(other_raw, [dim2], src_meas, agg_fn)
                other_sub = _total_over_rows(other_raw, [], src_meas, agg_fn)
            other_row = {c: (other_sub if c == "__total__" else other_cells.get(c, 0))
                         for c in pivot.columns if c != dim}
            other_row[dim] = "All Other"
            pivot = pd.concat([pivot, pd.DataFrame([other_row])[list(pivot.columns)]],
                              ignore_index=True)

        col_names = [str(c) for c in pivot.columns]
        result = {
            "type": "crosstab",
            "columns": col_names,
            "rows": [[_safe(v) for v in row] for row in pivot.itertuples(index=False)],
            "total": len(pivot),
            # `total` here counts the grid's rows (the renderer's contract); the
            # POPULATION the grid describes is the rows scanned, like every other
            # widget -- a crosstab beside a bar must not read "4" against "2,000".
            "rows_scanned": int(len(full_df)),
            "truncation": {"applied": False, "shown": int(len(pivot)), "of": int(len(pivot)),
                           "limit": None, "reason": "none", "unit": "rows"},
        }
        if config.get("show_totals"):
            def _cross_totals(frame: pd.DataFrame) -> list:
                # Column totals at the column grain and the grand total at no
                # grain, each aggregated (or, for a measure, re-evaluated) from
                # the source rows -- the same non-additivity rule as the row
                # subtotals above.
                if measure_def is not None:
                    col_vals = _measure_eval.evaluate_measure(measure_def["expression"], frame, [dim2])
                    grand = _measure_eval.evaluate_measure(measure_def["expression"], frame, [])
                    missing = 0
                else:
                    col_vals = _total_over_rows(frame, [dim2], src_meas, agg_fn)
                    grand = _total_over_rows(frame, [], src_meas, agg_fn)
                    missing = None
                return [None if c == dim
                        else _safe(grand) if c == "__total__"
                        else _safe(col_vals.get(c, missing))
                        for c in pivot.columns]

            # Over every source row: with an Other row the grid shows them all.
            result["totals"] = _cross_totals(full_df)
            # Rows a rank hid WITHOUT a bucket are not on the grid; say so, and
            # give the visible rows' own totals as well -- the series path's
            # contract (`totals_shown` / `totals_basis`).
            hidden = rank_keep is not None and other_raw is None
            if hidden:
                result["totals_shown"] = _cross_totals(df)
            result["totals_basis"] = {"unit": "groups", "shown": len(pivot), "of": groups_of,
                                      "truncated": hidden, "suppressed_excluded": False}
        return result

    # 4. Grouped series
    if dim and dim in df.columns:
        # A dimension literally called "value" collides with this shaper's own
        # output column -- `reset_index` refuses with "cannot insert value,
        # already exists" -- so a column named `value`, which is the norm in
        # long-format data, could not be charted AT ALL, by any aggregation.
        # Inside this block it travels under an internal name and is emitted
        # under its real one.
        dim_key = dim if dim != "value" else "__dim__"
        # Rows whose category is missing are DROPPED by every groupby below
        # (pandas' default; DuckDB and DirectQuery add `IS NOT NULL` to match).
        # So a chart and its Total exclude them while a KPI of the same measure
        # counts them -- 800 beside 840 on one dashboard, with nothing saying
        # why. Counted here, on the filtered frame, and disclosed on the result
        # like `truncation`: an exclusion is never silent. The two pushdown
        # engines hand this shaper a frame with the rows already gone, so they
        # measure it in SQL and overwrite the 0 computed here.
        missing_rows = int(df[dim].isna().sum())
        if measure_def is not None:
            # Post-aggregation measure: one value per group, computed at this grain.
            values = _measure_eval.evaluate_measure(measure_def["expression"], df, [dim])
            # Built column-by-column rather than via reset_index(): pandas names
            # the result Series after the column the expression aggregated, so
            # `COUNT(region)/TOTAL(COUNT(region))` grouped BY region produced a
            # Series called `region` indexed by `region`, and reset_index refused
            # with "cannot insert region, already exists". That is the natural
            # shape of a share-of-rows measure, and it could not be charted.
            grouped = pd.DataFrame({dim_key: list(values.index), "value": list(values)})
        elif meas and meas in df.columns:
            grouped = (df.groupby(dim)[meas].agg(agg_fn).rename("value").rename_axis(dim_key).reset_index())
        elif agg in ("count", "frequency"):
            grouped = (df.groupby(dim).size().rename("value").rename_axis(dim_key).reset_index())
        else:
            grouped = (df.groupby(dim).size().rename("value").rename_axis(dim_key).reset_index())

        # Percentage aggregation
        pct_base = None
        if agg == "pct":
            total = grouped["value"].sum()
            pct_base = total
            grouped["value"] = (grouped["value"] / total * 100).round(2)

        # Sort — sort_col (any dataset column) takes priority over sort_by
        if sort_col and sort_col in df.columns and sort_col != dim:
            if pd.api.types.is_numeric_dtype(df[sort_col]):
                sort_vals = (df.groupby(dim)[sort_col].mean().rename_axis(dim_key).reset_index().rename(columns={sort_col: "_sv"}))
            else:
                sort_vals = (df.groupby(dim)[sort_col].first().rename_axis(dim_key).reset_index().rename(columns={sort_col: "_sv"}))
            grouped = grouped.merge(sort_vals, on=dim_key, how="left")
            grouped = grouped.sort_values(["_sv", dim_key], ascending=[sort == "asc", True])
            grouped = grouped.drop(columns=["_sv"])
        elif sort_by == "name":
            grouped = grouped.sort_values(dim_key, ascending=(sort == "asc"))
        else:
            # Ties broken by the dimension, ascending. pandas' default sort is
            # quicksort -- not stable -- so without an explicit second key two groups
            # with equal values came out in an arbitrary order that also disagreed
            # with the DirectQuery pushdown's. Deterministic here and there is what
            # lets the two engines be compared row for row.
            grouped = grouped.sort_values(["value", dim], ascending=[sort == "asc", True])
        # Post-aggregate filters (HAVING): applied to the GROUPED values, after
        # aggregation and before sort/limit -- "regions whose total exceeds X", which
        # a row-level filter cannot express because no single row carries the total.
        for h in (config.get("having") or []):
            try:
                op, val = h.get("op"), float(h.get("value"))
            except (TypeError, ValueError):
                continue
            if op == "gt":   grouped = grouped[grouped["value"] > val]
            elif op == "lt": grouped = grouped[grouped["value"] < val]
            elif op == "gte": grouped = grouped[grouped["value"] >= val]
            elif op == "lte": grouped = grouped[grouped["value"] <= val]
            elif op == "eq": grouped = grouped[grouped["value"] == val]

        # Confidentiality suppression: hide aggregates computed from fewer than N
        # source rows -- small-cell suppression, so "sum of salaries in a one-person
        # department" never renders. With `suppress_complement`, the smallest
        # surviving group is hidden too whenever anything was suppressed, so the
        # suppressed value cannot be back-computed from a visible total (SAS's
        # withComplement).
        suppress_n = config.get("suppress_below")
        # Keys of every group suppression hid. A total computed from the source rows
        # must leave their rows out too: an all-rows total over a suppressed cell
        # would hand back the hidden value as (total - visible cells).
        suppressed_keys: list = []
        if suppress_n:
            try:
                n = int(suppress_n)
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                counts = df.groupby(dim).size()
                keep = grouped[dim_key].map(counts).fillna(0) >= n
                suppressed_any = bool((~keep).any())
                suppressed_keys.extend(grouped.loc[~keep, dim_key].tolist())
                grouped = grouped[keep]
                if suppressed_any and config.get("suppress_complement") and len(grouped) > 0                         and pd.api.types.is_numeric_dtype(grouped["value"]):
                    smallest = grouped["value"].astype(float).abs().idxmin()
                    suppressed_keys.append(grouped.loc[smallest, dim_key])
                    grouped = grouped.drop(index=smallest)

        # Rank selection: keep the top or bottom N categories BY AGGREGATED VALUE,
        # independent of the display sort -- "bottom 5, shown alphabetically" is
        # two different orderings, which is why this cannot be the sort+limit pair.
        # Ties at the boundary are kept (SAS keeps them), so "top 3" can show 4 rows.
        # `percent: true` reads n as a percentage of the category count (SAS's
        # "top N percent"); `other: true` collapses the excluded categories into
        # one "All Other" row whose value is the SAME aggregation applied to the
        # excluded categories' RAW rows -- an aggregate of aggregates would be
        # wrong for avg/median/min/max, so it is computed from the source frame.
        rank_cfg = config.get("rank") or {}
        other_index, other_keys = None, []
        # Selection shared via _rank_selection (one tie/percent/bottom
        # semantics for every ranking shaper); the Other bucket below stays
        # here because an honest residual is shape-specific.
        _rank_keep = _rank_selection(grouped["value"], config)
        if _rank_keep is not None:
                excluded = grouped[~_rank_keep]
                grouped = grouped[_rank_keep]
                if rank_cfg.get("other") and len(excluded) > 0:
                    other_val = None
                    if agg == "pct":
                        # pct space is additive by construction: the excluded shares
                        # sum to exactly what "the rest" holds.
                        other_val = float(excluded["value"].sum())
                    elif measure_def is not None:
                        # A measure expression cannot be honestly re-evaluated as an
                        # aggregate of aggregates; no bucket rather than a wrong one.
                        other_val = None
                    else:
                        raw_other = df[df[dim].isin(excluded[dim])]
                        if meas and meas in df.columns:
                            try:
                                other_val = _safe(raw_other[meas].agg(agg_fn))
                            except Exception:
                                other_val = None
                        else:
                            other_val = int(len(raw_other))
                    if other_val is not None:
                        grouped = pd.concat([grouped, pd.DataFrame(
                            [{dim: "All Other", "value": other_val}])], ignore_index=True)
                        # Remembered so a "shown rows" total can count the rows this
                        # bucket stands for, if it survives `limit`.
                        other_index = grouped.index[-1]
                        other_keys = excluded[dim_key].tolist()

        # Quick calculation: a one-click transform of the aggregated value, applied
        # over the visual's surviving categories (after HAVING/suppression, before
        # `limit` truncates the page -- percent-of-total over only the visible top-N
        # would silently re-base). `difference`/`percent_change` read the current
        # sort order, which is what "change from previous" means on screen.
        qc = config.get("quick_calc")
        if qc and pd.api.types.is_numeric_dtype(grouped["value"]):
            v = grouped["value"].astype(float)
            if qc == "percent_of_total":
                total = v.sum()
                grouped["value"] = (v / total * 100).round(2) if total else 0.0
            elif qc == "difference":
                grouped["value"] = v.diff()
            elif qc == "percent_change":
                grouped["value"] = (v.pct_change() * 100).round(2)
            elif qc == "rank":
                grouped["value"] = v.rank(ascending=False, method="min").astype(int)

        # Custom category order: an explicit list beats any computed sort. Categories
        # not in the list keep their computed order after the listed ones -- dropping
        # them would make a typo in the list silently hide data.
        custom_order = config.get("sort_custom")
        if isinstance(custom_order, list) and custom_order:
            rank = {str(v): i for i, v in enumerate(custom_order)}
            grouped = grouped.assign(
                __rank__=grouped[dim_key].map(lambda v: rank.get(str(v), len(rank)))
            ).sort_values(["__rank__", dim_key]).drop(columns="__rank__")

        # How many groups existed before the page was cut -- the reader must be
        # told when a chart shows 20 of 213 (constitution rule 4: truncation is a
        # first-class state, never a silent head()).
        groups_before_limit = len(grouped)
        grouped = grouped.head(limit)
        # Totals come from the SOURCE rows at their own grain (see _series_totals),
        # never from the grouped values -- and are worked out now, while `grouped`
        # still has its plain index for telling a real group from the Other bucket.
        series_totals = (
            _series_totals(df, dim, dim_key, grouped, meas, agg, agg_fn, measure_def,
                           suppressed_keys, other_index, other_keys, qc, pct_base)
            if config.get("show_totals") else None
        )

        # A bound target column rides along per group, aggregated the same way as the
        # measure so the two are comparable: a summed measure against an averaged
        # target answers a question nobody asked. Read via resolve_roles so both the
        # roles form and the flat panel form work -- the Card lesson.
        target_col = resolve_roles(config).get("target")
        if target_col and target_col in df.columns and pd.api.types.is_numeric_dtype(df[target_col]):
            target_fn = agg_fn if agg in ("sum", "mean", "avg", "median", "min", "max") else "sum"
            targets = df.groupby(dim)[target_col].agg(target_fn)
            grouped = grouped.merge(targets.rename("__target__"), left_on=dim_key, right_index=True, how="left")
            # Column by column, not iterrows(): a row Series mixing an int name
            # with a float value is upcast to float, which turned every year
            # label into "2024.0" on the axis.
            rows = [{"name": _safe(n), "value": _safe(v), "target": _safe(t)}
                    for n, v, t in zip(grouped[dim_key], grouped["value"], grouped["__target__"])]
        else:
            rows = [{"name": _safe(n), "value": _safe(v)}
                    for n, v in zip(grouped[dim_key], grouped["value"])]

        # Running aggregations (applied to already-grouped rows)
        if running == "sum":
            cumsum = 0
            for r in rows:
                cumsum += (r["value"] or 0)
                r["running_sum"] = round(cumsum, 4)
        elif running == "avg":
            vals = [r["value"] or 0 for r in rows]
            for i, r in enumerate(rows):
                r["running_avg"] = round(sum(vals[:i+1]) / (i+1), 4)

        result = {
            "type": "series",
            "dimension": dim,
            "measure": meas or "count",
            "aggregation": agg,
            "rows": rows,
            "total": len(df),
            # Always present, like `truncation`: rows this chart left out
            # because their category is missing (see the count above).
            "missing_category": {"rows": missing_rows},
            # Always present, so a client never has to infer a cut from a count.
            "truncation": {
                "applied": groups_before_limit > len(rows),
                "shown": len(rows),
                "of": groups_before_limit,
                "limit": limit,
                "reason": "limit",
            },
        }
        # A table/crosstab/matrix widget with a Dimension set (the configuration
        # ROLE_SPECS marks `category: required`, i.e. the one the Fields pane steers
        # every author into) shapes HERE, not in the raw-table branch above — so this
        # is where "Show totals" has to be honoured for it to be a live control at
        # all. The renderer builds a table's columns from the row object's own keys
        # (WidgetRenderer.tsx: `Object.keys(rawRows[0])`), so `totals` is aligned to
        # those keys positionally: the dimension column carries the label instead of a
        # number, and a running_sum/running_avg column has no meaningful total (it is
        # derived from the visible page only), so both emit None.
        if series_totals is not None:
            if "unavailable" in series_totals:
                result["totals_unavailable"] = series_totals["unavailable"]
            else:
                keys = list(rows[0].keys()) if rows else ["name", "value"]
                result["totals"] = [series_totals["all"] if k == "value" else None for k in keys]
                if "shown" in series_totals:
                    result["totals_shown"] = [series_totals["shown"] if k == "value" else None
                                              for k in keys]
                result["totals_basis"] = series_totals["basis"]
        return result

    # 5. Single aggregate scalar (no dimension — KPI use case)
    if measure_def is not None:
        val = _measure_eval.evaluate_measure(measure_def["expression"], df, [])
        return {
            "type": "scalar",
            "measure": meas,
            "aggregation": agg,
            "rows": [{"name": meas, "value": _safe(val)}],
            "total": len(df),
        }
    if meas and meas in df.columns:
        val = _agg_series(df[meas], agg)
        return {
            "type": "scalar",
            "measure": meas,
            "aggregation": agg,
            "rows": [{"name": meas, "value": val}],
            "total": len(df),
        }

    return {"type": "empty", "rows": [], "total": 0}


def shape_histogram(df: pd.DataFrame, config: dict) -> dict:
    """config keys: measure (required), bins (int, default 10), filters."""
    filters = config.get("filters", [])
    meas = config.get("measure") or None
    bins = int(config.get("bins") or 10)
    df = _apply_filters(df, filters)
    if df.empty or not meas or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    s = df[meas].dropna()
    if len(s) == 0:
        return {"type": "empty", "rows": [], "total": 0}
    counts, edges = np.histogram(s, bins=bins)
    rows = []
    for i in range(len(counts)):
        lo, hi = float(edges[i]), float(edges[i + 1])
        rows.append({
            "name": f"{lo:.2f}–{hi:.2f}",
            "value": int(counts[i]),
            "bin_start": _safe(lo),
            "bin_end": _safe(hi),
        })
    return {"type": "series", "measure": meas, "rows": rows, "total": len(s)}


#: Marks a composed graph can draw. An unknown one falls back to a bar rather
#: than failing: marks arrive from stored config, which outlives any list the
#: renderer knows, and a chart that refuses to draw teaches nobody anything.
GRAPH_MARKS = ("bar", "line", "area", "scatter")


def shape_slicer(df: pd.DataFrame, config: dict) -> dict:
    """The slicer's values -- unless the control does not want any.

    A slicer over `Customer ID` is the case every list control gets wrong.
    With hundreds of thousands of distinct values the list is unreadable, but
    the expensive part is not the rendering: it is that the server groups the
    whole column to build a list nobody can use. SAS offers a TEXT INPUT for
    exactly this, where the reader types the value they already know.

    So `slicer_mode: "text"` returns early, before any grouping. That is the
    whole point of the mode -- a control that skipped the list and still paid
    for it would be the same cost wearing a smaller widget.

    `auto` never resolves to text. A reader who CAN see their options should
    be shown them, and a control that silently stopped listing would read as
    broken rather than deliberate.
    """
    if str(config.get("slicer_mode") or "").lower() == "text":
        roles = resolve_roles(config)
        column = roles.get("category") or config.get("dimension")
        return {"type": "slicer_text", "rows": [], "total": 0, "column": column}
    return shape_series(df, config)


def shape_custom_graph(df: pd.DataFrame, config: dict) -> dict:
    """A chart composed from PLOT LAYERS -- what SAS calls Graph Builder.

    The catalogue already had three fixed combinations (dual-axis bar, line,
    bar-line). The capability being added is not more combinations: it is that
    the author decides what the combination IS -- how many layers, which mark
    each draws, which axis each belongs to -- and can then save the result as
    an object template and use it anywhere.

    Two rules carried over from `shape_dual_series`, generalised:

      * EACH LAYER AGGREGATES IN ITS OWN RIGHT. The numbers on a multi-layer
        chart are not the same kind of number -- that is why it has two axes --
        so "encounters counted, wait averaged" must be expressible per layer.

      * LAYERS ARE KEYED BY POSITION, never by measure name. One column read
        two ways ("total cost" and "average cost") is a common and legitimate
        pair, and keying output by column name collapses it into one series --
        drawing a single line where the author asked for two.
    """
    roles = resolve_roles(config)
    cat = roles.get("category") or config.get("dimension")
    layers_in = config.get("layers") or []
    limit = int(config.get("limit") or 50)

    df = _apply_filters(df, config.get("filters", []))
    if df.empty or not cat or cat not in df.columns or not layers_in:
        return {"type": "empty", "rows": [], "total": 0}

    granularity = config.get("dimension_granularity") or None
    if granularity:
        df = df.copy()
        df[cat] = _bucket_dimension(df[cat], granularity)

    plan: list[dict] = []
    skipped: list[str] = []
    for i, raw in enumerate(layers_in):
        if not isinstance(raw, dict):
            continue
        measure = raw.get("measure")
        if not measure or measure not in df.columns:
            # Named rather than dropped in silence: an author looking for a
            # series that is simply absent has nothing to go on.
            if measure:
                skipped.append(str(measure))
            continue
        agg = str(raw.get("aggregation") or config.get("aggregation") or "sum").lower()
        mark = str(raw.get("mark") or "bar").lower()
        plan.append({
            "key": f"s{i}",
            "measure": measure,
            "aggregation": agg,
            "mark": mark if mark in GRAPH_MARKS else "bar",
            "axis": "right" if str(raw.get("axis")) == "right" else "left",
            # The legend has to tell two readings of one column apart, so the
            # aggregation is part of the name rather than decoration.
            "label": str(raw.get("label") or f"{agg} of {measure}"),
        })

    if not plan:
        return {"type": "empty", "rows": [], "total": 0,
                **({"skipped": skipped} if skipped else {})}

    grouped = df.groupby(cat, dropna=False)
    series = {}
    for layer in plan:
        series[layer["key"]] = grouped[layer["measure"]].agg(
            _pandas_agg_fn(layer["aggregation"]))

    frame = pd.DataFrame(series)
    # Ordered by the FIRST layer, which is the one the author put first and so
    # the one the chart is about; ties keep pandas' grouping order.
    frame = frame.sort_values(plan[0]["key"], ascending=False).head(limit)

    rows = []
    for name, values in frame.iterrows():
        row = {"name": _safe(name)}
        for layer in plan:
            row[layer["key"]] = _safe(values[layer["key"]])
        rows.append(row)

    return {
        "type": "custom_graph",
        "rows": rows,
        "total": len(rows),
        "layers": [{k: lyr[k] for k in ("key", "label", "mark", "axis", "measure", "aggregation")}
                   for lyr in plan],
        **({"skipped": skipped} if skipped else {}),
    }



def _cut(frame, limit: int, unit: str):
    """`frame.head(limit)` plus the disclosure of what it dropped (rule 4:
    truncation is a first-class state -- a cut is never silent)."""
    out = frame.head(limit)
    return out, {"applied": len(out) < len(frame), "shown": int(len(out)), "of": int(len(frame)),
                 "limit": int(limit), "reason": "limit", "unit": unit}


def shape_dual_series(df: pd.DataFrame, config: dict) -> dict:
    """config roles: category OR start (grouping column), measure, measure2.
    At least one of measure/measure2 must be set. Used by dual-axis and
    comparative time-series chart types, which differ only in rendering."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category") or roles.get("start")
    meas = roles.get("measure")
    meas2 = roles.get("measure2")
    agg = (config.get("aggregation") or "sum").lower()
    limit = int(config.get("limit") or 50)
    df = _apply_filters(df, filters)
    if df.empty or not cat or cat not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}

    # The config panel offers dimension_granularity for these widget types too, and
    # shape_series honours it -- this shaper did not, so "group by month" on a
    # dual-axis or comparative chart silently plotted one point per raw row. Offered
    # and ignored is the same failure as a control wired to nothing.
    dim_granularity = config.get("dimension_granularity") or None
    if dim_granularity:
        df = df.copy()
        df[cat] = _bucket_dimension(df[cat], dim_granularity)

    # Each axis aggregates in its own right. The two numbers on a dual-axis chart
    # are not the same KIND of number -- that is why it has two axes -- so
    # "encounters counted, wait averaged" has to be expressible. `aggregation2`
    # falls back to `aggregation`, which is what every chart saved before this
    # existed relies on.
    agg2 = (config.get("aggregation2") or agg).lower()
    agg_fn = _pandas_agg_fn(agg)
    agg_fn2 = _pandas_agg_fn(agg2)

    # Each output column, in order, as (column name, source column, function).
    # The second measure is aliased when it names the SAME column as the first:
    # "total and average cost" is one column read two ways, and a plain dedupe
    # would collapse it to one number.
    _plan = []
    if meas and meas in df.columns:
        _plan.append((meas, meas, agg_fn))
    if meas2 and meas2 in df.columns:
        _alias = meas2 if meas2 != meas else meas2 + "__2"
        if meas2 != meas or agg2 != agg:
            _plan.append((_alias, meas2, agg_fn2))
    if not _plan:
        return {"type": "empty", "rows": [], "total": 0}

    # The same column at the same aggregation is ONE computation feeding both
    # series -- a chart configured that way has always drawn two identical lines,
    # and dropping the second here would silently remove one.
    _col1 = _plan[0][0] if meas and meas in df.columns else None
    _col2 = None
    if meas2 and meas2 in df.columns:
        _col2 = _plan[1][0] if len(_plan) == 2 else _plan[0][0]
    agg_cols = [c for c, _src, _fn in _plan]

    _g = df.groupby(cat)
    grouped = pd.DataFrame({c: _g[src].agg(fn) for c, src, fn in _plan}).reset_index()

    # Ranking: the same capability shape_series has, via the same selection
    # helper -- ties, percent mode and bottom-N behave identically. Selection
    # ranks by the PRIMARY measure (the left axis is the chart's subject); the
    # Other bucket re-aggregates BOTH measures from the excluded categories'
    # RAW rows, which stays honest for any aggregation -- it is never an
    # aggregate of aggregates.
    _rank_col = _col1 or agg_cols[0]
    _keep = _rank_selection(grouped[_rank_col], config)
    if _keep is not None:
        _rank_cfg = config.get("rank") or {}
        _excluded_labels = grouped.loc[~_keep, cat]
        grouped = grouped[_keep]
        if _rank_cfg.get("other") and len(_excluded_labels) > 0:
            _raw_other = df[df[cat].isin(_excluded_labels)]
            _other_row = {cat: "All Other"}
            for _c, _src, _fn in _plan:
                try:
                    _other_row[_c] = _raw_other[_src].agg(_fn)
                except Exception:  # noqa: BLE001 -- no bucket beats a wrong one
                    _other_row[_c] = None
            grouped = pd.concat([grouped, pd.DataFrame([_other_row])],
                                ignore_index=True)

    grouped, _truncation = _cut(grouped.sort_values(cat), limit, "categories")
    rows = []
    for _, row in grouped.iterrows():
        r = {"name": _safe(row[cat])}
        if _col1:
            r["value"] = _safe(row[_col1])
        if _col2:
            r["value2"] = _safe(row[_col2])
        rows.append(r)
    return {"truncation": _truncation, "type": "dual_series", "category": cat, "measure": meas, "measure2": meas2, "rows": rows, "total": len(df)}


def shape_xy_numeric(df: pd.DataFrame, config: dict) -> dict:
    """config roles: measure (x), measure2 (y). Row-level, no aggregation."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    x = roles.get("measure")
    y = roles.get("measure2")
    limit = int(config.get("limit") or 500)
    df = _apply_filters(df, filters)
    if df.empty or not x or not y or x not in df.columns or y not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    if x == y:
        sub, _truncation = _cut(df[[x]].dropna().sort_values(x), limit, "points")
        rows = [{"x": _safe(r[x]), "y": _safe(r[x])} for _, r in sub.iterrows()]
        return {"type": "xy_series", "x": x, "y": y, "rows": rows, "total": len(df), "truncation": _truncation}
    sub, _truncation = _cut(df[[x, y]].dropna().sort_values(x), limit, "points")
    rows = [{"x": _safe(r[x]), "y": _safe(r[y])} for _, r in sub.iterrows()]
    return {"type": "xy_series", "x": x, "y": y, "rows": rows, "total": len(df), "truncation": _truncation}


def shape_bubble(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (required), measure(x)/measure2(y)/size (all required),
    color (optional numeric, aggregated), group (optional categorical, via first())."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    x = roles.get("measure")
    y = roles.get("measure2")
    size = roles.get("size")
    color = roles.get("color")
    group = roles.get("group")
    agg = (config.get("aggregation") or "sum").lower()
    limit = int(config.get("limit") or 100)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not x or not y or not size:
        return {"type": "empty", "rows": [], "total": 0}
    if cat not in df.columns or x not in df.columns or y not in df.columns or size not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)

    # An id-like or non-numeric color column is a category wearing a color role,
    # not a measure: SUM-ing student_id (or averaging a text column, which pandas
    # can't do at all) is meaningless. Take it via first() alongside `group`
    # instead of folding it into the aggregated measures.
    color_is_category = bool(color) and color in df.columns and (
        not pd.api.types.is_numeric_dtype(df[color]) or _is_id_like_column(color)
    )

    if color_is_category:
        num_cols = list(dict.fromkeys([c for c in (x, y, size) if c and c in df.columns]))
    else:
        num_cols = list(dict.fromkeys([c for c in (x, y, size, color) if c and c in df.columns]))
    if cat in num_cols or (group and group == cat) or (color_is_category and color == cat):
        # cat colliding with an aggregated/merge column makes reset_index()/merge
        # try to insert a column that already exists (ValueError: cannot insert ...)
        return {"type": "empty", "rows": [], "total": 0}
    if color_is_category and color in num_cols:
        # color duplicating x/y/size while also being category-shaped -- same
        # reset_index/merge collision as above, just via a different pair of roles.
        return {"truncation": _truncation, "type": "empty", "rows": [], "total": 0}
    grouped = df.groupby(cat)[num_cols].agg(agg_fn).reset_index()
    if group and group in df.columns:
        grp_vals = df.groupby(cat)[group].first().reset_index()
        grouped = grouped.merge(grp_vals, on=cat, how="left")
    if color_is_category and color not in grouped.columns:
        color_vals = df.groupby(cat)[color].first().reset_index()
        grouped = grouped.merge(color_vals, on=cat, how="left")
    grouped, _truncation = _cut(grouped.sort_values(cat), limit, "categories")
    rows = []
    for _, row in grouped.iterrows():
        r = {"name": _safe(row[cat]), "x": _safe(row[x]), "y": _safe(row[y]), "size": _safe(row[size])}
        if color and color in grouped.columns:
            r["color"] = _safe(row[color])
        if group and group in grouped.columns:
            r["group"] = _safe(row[group])
        rows.append(r)
    result = {"type": "bubble_series", "x": x, "y": y, "size": size, "color": color, "rows": rows, "total": len(df)}
    if color:
        result["color_kind"] = "category" if color_is_category else "measure"
    fit_kind = config.get("fit_line")
    if fit_kind:
        fit_points = compute_fit_line([r["x"] for r in rows], [r["y"] for r in rows], fit_kind)
        if fit_points:
            result["fit_line"] = fit_points
    return result


def shape_bubble_animated(df: pd.DataFrame, config: dict) -> dict:
    """Same as shape_bubble but groups by (category, animation) — one bubble per
    category per animation frame, powering a client-side play/pause/scrub UI."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    x = roles.get("measure")
    y = roles.get("measure2")
    size = roles.get("size")
    color = roles.get("color")
    anim = roles.get("animation")
    agg = (config.get("aggregation") or "sum").lower()
    limit = int(config.get("limit") or 500)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not x or not y or not size or not anim:
        return {"type": "empty", "rows": [], "total": 0}
    if any(c not in df.columns for c in (cat, x, y, size, anim)):
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)

    # Same reasoning as shape_bubble: an id-like or non-numeric color is a category,
    # taken via first() alongside (category, animation) rather than aggregated.
    color_is_category = bool(color) and color in df.columns and (
        not pd.api.types.is_numeric_dtype(df[color]) or _is_id_like_column(color)
    )

    if color_is_category:
        num_cols = list(dict.fromkeys([c for c in (x, y, size) if c and c in df.columns]))
    else:
        num_cols = list(dict.fromkeys([c for c in (x, y, size, color) if c and c in df.columns]))
    if cat in num_cols or anim == cat or anim in num_cols or (color_is_category and color in (cat, anim)):
        # cat or anim colliding with cat/an aggregated/merge column makes reset_index()
        # try to insert a column that already exists (ValueError: cannot insert ...)
        return {"type": "empty", "rows": [], "total": 0}
    if color_is_category and color in num_cols:
        return {"truncation": _truncation, "type": "empty", "rows": [], "total": 0}
    grouped = df.groupby([cat, anim])[num_cols].agg(agg_fn).reset_index()
    if color_is_category:
        color_vals = df.groupby([cat, anim])[color].first().reset_index()
        grouped = grouped.merge(color_vals, on=[cat, anim], how="left")
    grouped, _truncation = _cut(grouped.sort_values([anim, cat]), limit, "points")
    frames = sorted(df[anim].dropna().unique().tolist())
    rows = []
    for _, row in grouped.iterrows():
        r = {"name": _safe(row[cat]), "frame": _safe(row[anim]), "x": _safe(row[x]), "y": _safe(row[y]), "size": _safe(row[size])}
        if color and color in grouped.columns:
            r["color"] = _safe(row[color])
        rows.append(r)
    result = {"type": "bubble_animated_series", "x": x, "y": y, "size": size, "color": color,
              "frames": [_safe(f) for f in frames], "rows": rows, "total": len(df)}
    if color:
        result["color_kind"] = "category" if color_is_category else "measure"
    return result


_FIT_DEGREES = {"linear": 1, "quadratic": 2, "cubic": 3}


def _r_squared(xs: np.ndarray, ys: np.ndarray, coeffs: np.ndarray) -> float:
    fitted = np.polyval(coeffs, xs)
    ss_res = np.sum((ys - fitted) ** 2)
    ss_tot = np.sum((ys - ys.mean()) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else 0.0


def compute_fit_line(xs: list, ys: list, kind: str) -> list[dict] | None:
    """Fit linear/quadratic/cubic (numpy.polyfit) or best_fit (highest R^2 among the three)
    and return 20 evenly-spaced {x, y} points across the observed x-range. None if it can't fit."""
    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)
    if len(xs_arr) < 2 or len(set(xs_arr.tolist())) < 2:
        return None

    def _fit(degree: int):
        if len(set(xs_arr.tolist())) < degree + 1:
            return None
        return np.polyfit(xs_arr, ys_arr, degree)

    if kind in _FIT_DEGREES:
        coeffs = _fit(_FIT_DEGREES[kind])
        if coeffs is None:
            return None
    elif kind == "best_fit":
        candidates = [(deg, _fit(deg)) for deg in (1, 2, 3)]
        candidates = [(deg, c) for deg, c in candidates if c is not None]
        if not candidates:
            return None
        _, coeffs = max(candidates, key=lambda dc: _r_squared(xs_arr, ys_arr, dc[1]))
    else:
        return None

    x_min, x_max = float(xs_arr.min()), float(xs_arr.max())
    if x_min == x_max:
        return None
    step = (x_max - x_min) / 19
    points = []
    for i in range(20):
        x = x_min + i * step
        y = float(np.polyval(coeffs, x))
        points.append({"x": _safe(x), "y": _safe(y)})
    return points


def shape_correlation_matrix(df: pd.DataFrame, config: dict) -> dict:
    """config keys: measures (list[str], the multi-select role — not resolved via resolve_roles,
    since it's a plain multi-value list emitted directly by WidgetConfigPanel), filters."""
    filters = config.get("filters", [])
    measures = list(dict.fromkeys(config.get("measures") or []))
    df = _apply_filters(df, filters)
    measures = [m for m in measures if m in df.columns]
    if df.empty or len(measures) < 2:
        return {"type": "empty", "rows": [], "total": 0}
    corr = df[measures].corr(method="pearson")
    matrix = [[_safe(corr.loc[m1, m2]) for m2 in measures] for m1 in measures]
    return {"type": "matrix", "measures": measures, "matrix": matrix, "total": len(df)}


def _rank_selection(values: "pd.Series", config: dict) -> "pd.Series | None":
    """The shared half of the Ranking capability: WHICH categories survive.

    Returns a boolean keep-mask over `values` (each entry one category's
    aggregated value), or None when ranking is not active. Extracted from
    shape_series so every shaper that ranks shares ONE semantics for the
    subtle parts -- ties at the boundary are KEPT (SAS keeps them, so "top 3"
    can show 4 rows), `percent: true` reads n as a percentage of the category
    count, and `mode: "bottom"` flips the boundary. Two implementations of
    tie handling would disagree on exactly the datasets where it matters.

    The "Other" bucket deliberately stays PER SHAPER: what an honest residual
    is depends on the shape (a series re-aggregates excluded raw rows; a
    heatmap re-aggregates them per column), and a helper that guessed would
    be wrong somewhere silently.
    """
    rank_cfg = config.get("rank") or {}
    if not (isinstance(rank_cfg, dict) and rank_cfg.get("n")
            and pd.api.types.is_numeric_dtype(values)):
        return None
    try:
        rank_n = int(rank_cfg["n"])
    except (TypeError, ValueError):
        return None
    if rank_n <= 0:
        return None
    if rank_cfg.get("percent"):
        import math
        rank_n = max(1, math.ceil(len(values) * min(rank_n, 100) / 100))
    if len(values) <= rank_n:
        return None
    bottom = rank_cfg.get("mode") == "bottom"
    v = values.astype(float)
    boundary = v.nsmallest(rank_n).max() if bottom else v.nlargest(rank_n).min()
    return v <= boundary if bottom else v >= boundary


def shape_heatmap(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (rows), category2 (columns), measure (cell value, aggregated)."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    cat2 = roles.get("category2")
    meas = roles.get("measure")
    agg = (config.get("aggregation") or "sum").lower()
    df = _apply_filters(df, filters)
    if df.empty or not cat or not cat2 or not meas:
        return {"type": "empty", "rows": [], "total": 0}
    if cat not in df.columns or cat2 not in df.columns or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    if cat == cat2:
        return {"type": "empty", "rows": [], "total": 0}

    # Same omission the dual-axis shapers had: the config panel writes
    # dimension_granularity for whichever widget is selected, and this shaper --
    # which serves the heatmap AND the ribbon -- ignored it. A ribbon of triage
    # mix "by quarter" grouped by raw arrival minute: 120,000 row-axis entries,
    # megabytes for one tile, unreadable. Applied before the ranking below so the
    # top-N is computed over the buckets the reader actually sees, not over the
    # raw stamps.
    dim_granularity = config.get("dimension_granularity") or None
    if dim_granularity:
        df = df.copy()
        df[cat] = _bucket_dimension(df[cat], dim_granularity)

    agg_fn = _pandas_agg_fn(agg)

    # Ranking: keep the top/bottom N ROW categories, ranked by each row's own
    # aggregate over its raw rows (same agg as the cells), through the shared
    # selection helper -- one tie/percent/bottom semantics with shape_series.
    # The Other bucket collapses the excluded rows into one "All Other" row
    # re-aggregated from raw PER COLUMN, so every cell in it is the same kind
    # of number as every other cell.
    _row_vals = df.groupby(cat)[meas].agg(agg_fn)
    _keep = _rank_selection(_row_vals, config)
    _other_frame = None
    if _keep is not None:
        _rank_cfg = config.get("rank") or {}
        _kept_labels = _row_vals.index[_keep]
        _excluded_raw = df[~df[cat].isin(_kept_labels)]
        df = df[df[cat].isin(_kept_labels)]
        if _rank_cfg.get("other") and len(_excluded_raw) > 0:
            _other_frame = _excluded_raw.groupby(cat2)[meas].agg(agg_fn)

    pivot = df.groupby([cat, cat2])[meas].agg(agg_fn).unstack(cat2)
    if _other_frame is not None:
        pivot.loc["All Other"] = _other_frame.reindex(pivot.columns)
    rows_axis = [str(v) for v in pivot.index.tolist()]
    cols_axis = [str(v) for v in pivot.columns.tolist()]
    cells = [[_safe(v) if pd.notna(v) else None for v in row] for row in pivot.values]
    flat_vals = [v for row in cells for v in row if v is not None]
    return {
        "type": "heatmap", "rows_axis": rows_axis, "cols_axis": cols_axis, "cells": cells,
        "min": min(flat_vals) if flat_vals else 0, "max": max(flat_vals) if flat_vals else 0,
        "total": len(df),
    }


def shape_parallel_coordinates(df: pd.DataFrame, config: dict) -> dict:
    """config keys: measures (list[str], ordered, multi-select — plain list, not a resolve_roles
    role), limit (default 200, this is detail-level, not aggregated), filters."""
    filters = config.get("filters", [])
    measures = list(dict.fromkeys(config.get("measures") or []))
    limit = int(config.get("limit") or 200)
    df = _apply_filters(df, filters)
    measures = [m for m in measures if m in df.columns]
    if df.empty or len(measures) < 2:
        return {"type": "empty", "rows": [], "total": 0}
    sub = df[measures].dropna().head(limit)
    axes = []
    bounds = {}
    for m in measures:
        lo, hi = float(sub[m].min()), float(sub[m].max())
        axes.append({"name": m, "min": _safe(lo), "max": _safe(hi)})
        bounds[m] = (lo, hi)
    lines = []
    for _, row in sub.iterrows():
        line = []
        for m in measures:
            lo, hi = bounds[m]
            norm = 0.5 if hi == lo else (float(row[m]) - lo) / (hi - lo)
            line.append(round(norm, 4))
        lines.append(line)
    return {"type": "parallel_coordinates", "axes": axes, "lines": lines, "total": len(df)}


def shape_box_plot(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (required), measure (required). Computes per-category
    quartile summary (min, q1, median, q3, max) and outliers (values beyond
    1.5*IQR from q1/q3), the standard box-and-whisker statistics. min/max
    exclude outliers (fall back to q1/q3 when every value in a category is
    flagged as an outlier, so the whisker endpoints are never missing)."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    meas = roles.get("measure")
    limit = int(config.get("limit") or 50)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not meas or cat not in df.columns or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    rows = []
    for name, sub in df.groupby(cat):
        vals = sub[meas].dropna()
        if len(vals) == 0:
            continue
        q1, med, q3 = float(vals.quantile(.25)), float(vals.median()), float(vals.quantile(.75))
        iqr = q3 - q1
        lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        inliers = vals[(vals >= lo_fence) & (vals <= hi_fence)]
        outliers = vals[(vals < lo_fence) | (vals > hi_fence)]
        rows.append({
            "name": _safe(name),
            "min": _safe(float(inliers.min())) if len(inliers) else _safe(q1),
            "q1": _safe(q1), "median": _safe(med), "q3": _safe(q3),
            "max": _safe(float(inliers.max())) if len(inliers) else _safe(q3),
            "outliers": [_safe(v) for v in outliers.tolist()],
        })
    rows.sort(key=lambda r: r["name"])
    _truncation = {"applied": len(rows) > limit, "shown": min(len(rows), limit), "of": len(rows),
                   "limit": limit, "reason": "limit", "unit": "categories"}
    rows = rows[:limit]
    return {"truncation": _truncation, "type": "box_plot", "category": cat, "measure": meas, "rows": rows, "total": len(df)}


def shape_waterfall(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (required), measure (required, the delta per category).
    Computes a running total across categories in groupby-sorted order,
    returning start/delta/end per bar for the classic waterfall
    transparent-base stacked-bar rendering trick."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    meas = roles.get("measure")
    agg = (config.get("aggregation") or "sum").lower()
    limit = int(config.get("limit") or 50)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not meas or cat not in df.columns or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)
    grouped, _truncation = _cut(df.groupby(cat)[meas].agg(agg_fn).sort_index(), limit, "categories")
    running = 0.0
    bars = []
    for name, delta in grouped.items():
        delta = float(delta)
        bars.append({"name": _safe(name), "start": _safe(running), "delta": _safe(delta), "end": _safe(running + delta)})
        running += delta
    return {"truncation": _truncation, "type": "waterfall", "category": cat, "measure": meas, "bars": bars, "grand_total": _safe(running), "total": len(df)}


def shape_gauge(df: pd.DataFrame, config: dict) -> dict:
    """roles: measure (required, aggregated to a single value), target
    (optional column, aggregated the same way). config may also set a literal
    target_value (a plain number), used only when the target role isn't set —
    covers goals with no natural target column (e.g. a fixed KPI threshold)."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    meas = roles.get("measure")
    target_col = roles.get("target")
    agg = (config.get("aggregation") or "sum").lower()
    df = _apply_filters(df, filters)
    if df.empty or not meas or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    value = _agg_series(df[meas], agg)
    target = None
    if target_col and target_col in df.columns:
        try:
            target = _agg_series(df[target_col], agg)
        except Exception:
            target = None
    elif config.get("target_value") is not None:
        try:
            target = _safe(float(config["target_value"]))
        except (TypeError, ValueError):
            target = None
    return {"type": "gauge", "measure": meas, "value": value, "target": target, "total": len(df)}


def shape_script(df: pd.DataFrame, config: dict) -> dict:
    """A tile that runs server-side Python over the widget's frame.

    SAS's Job content object. The frame arriving here is already secured --
    column rules, RLS and the dataset filter were applied upstream, and the
    widget's own filters are applied below -- so a script sees exactly the rows
    the requesting user may see, and honours the slicers on the page.

    Errors come back IN the payload rather than as an exception: the person
    looking at a script tile is usually the person who wrote it, and the
    message is the whole point. Everything else about the execution model,
    including what it does NOT protect against, is in services/script_tile.py.
    """
    from .script_tile import ScriptError, run_script
    df = _apply_filters(df, config.get("filters", []))
    empty = {"type": "script", "kind": "script", "columns": [], "rows": [],
             "stdout": "", "truncated": False, "total": 0}
    try:
        out = run_script(df, config.get("code") or "",
                         timeout=config.get("timeout_seconds") or 0)
    except ScriptError as e:
        return {**empty, "error": str(e)}
    return {**out, "type": "script", "error": None, "total": out.get("row_count", 0)}


def shape_card(df: pd.DataFrame, config: dict) -> dict:
    """roles: measures (multi, required) -- each aggregated independently to a
    single value using the widget's configured aggregation. Powers the Card /
    Multi-row card widget: one row per measure, same {name, value} shape the
    list widget already uses. A name that is not a column resolves against the
    dataset's post-aggregation measures and evaluates at no grain -- a card of
    `revenue` next to `SUM(sales)/TOTAL(SUM(sales))*100` just works."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    measures = roles.get("measures") or []
    agg = (config.get("aggregation") or "sum").lower()
    df = _apply_filters(df, filters)
    if df.empty or not measures:
        return {"rows": [], "total": 0}
    rows = []
    for m in measures:
        if m in df.columns:
            rows.append({"name": m, "value": _agg_series(df[m], agg)})
            continue
        md = _measure_eval.resolve_measure(m, config.get("measure_defs"))
        if md is not None:
            # Surfacing the error beats skipping: a card silently missing one
            # of its measures reads as a data bug, not the config bug it is.
            rows.append({"name": m, "value": _safe(
                _measure_eval.evaluate_measure(md["expression"], df, []))})
    return {"rows": rows, "total": len(df)}


def shape_gantt(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (task label, required), start (required), end
    (required), group (optional, for color-coding). Row-level detail, no
    aggregation -- each source row becomes one task bar spanning start..end."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    start = roles.get("start")
    end = roles.get("end")
    group = roles.get("group")
    limit = int(config.get("limit") or 100)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not start or not end:
        return {"type": "empty", "rows": [], "total": 0}
    if any(c not in df.columns for c in (cat, start, end)):
        return {"type": "empty", "rows": [], "total": 0}
    cols = list(dict.fromkeys([cat, start, end] + ([group] if group and group in df.columns else [])))
    sub = df[cols].dropna(subset=list(dict.fromkeys([cat, start, end]))).head(limit)
    rows = []
    for _, row in sub.iterrows():
        r = {"name": _safe(row[cat]), "start": _safe(row[start]), "end": _safe(row[end])}
        if group and group in cols:
            r["group"] = _safe(row[group])
        rows.append(r)
    return {"type": "gantt", "category": cat, "start": start, "end": end, "rows": rows, "total": len(df)}


def shape_vector_plot(df: pd.DataFrame, config: dict) -> dict:
    """roles: measure (x), measure2 (y), size (magnitude/length), direction
    (angle in degrees, 0 = pointing right/east, counter-clockwise -- standard
    math convention). Row-level detail -- each source row becomes one arrow,
    no aggregation."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    x = roles.get("measure")
    y = roles.get("measure2")
    size = roles.get("size")
    direction = roles.get("direction")
    limit = int(config.get("limit") or 300)
    df = _apply_filters(df, filters)
    if df.empty or not x or not y or not size or not direction:
        return {"type": "empty", "rows": [], "total": 0}
    cols = list(dict.fromkeys([x, y, size, direction]))
    if any(c not in df.columns for c in cols):
        return {"type": "empty", "rows": [], "total": 0}
    sub = df[cols].dropna().head(limit)
    rows = []
    for _, row in sub.iterrows():
        rows.append({
            "x": _safe(row[x]), "y": _safe(row[y]),
            "size": _safe(row[size]), "direction": _safe(row[direction]),
        })
    return {"type": "vector_plot", "x": x, "y": y, "size": size, "direction": direction, "rows": rows, "total": len(df)}


def shape_geo_points(df: pd.DataFrame, config: dict) -> dict:
    """Rows for a point/bubble map.

    Two modes, decided by what the author assigned:
      * lat + lon roles -> coordinate rows {lat, lon, name?, value?}, capped by limit.
        Rows whose coordinates are missing or out of range are dropped and counted --
        a marker at (NaN, NaN) is a crash and a marker at (999, 999) is a lie.
      * otherwise -> ordinary grouped series ({name, value} keyed by country); the
        renderer plots those at country centroids, which is what makes the map widgets
        usable on data that has no coordinate columns.
    """
    roles = resolve_roles(config)
    lat, lon = roles.get("lat"), roles.get("lon")
    if not (lat and lon and lat in df.columns and lon in df.columns):
        return shape_series(df, config)

    filters = config.get("filters", [])
    df = _apply_filters(df, filters)
    name_col = roles.get("category")
    meas = roles.get("measure")
    limit = int(config.get("limit") or 1000)

    lat_v = pd.to_numeric(df[lat], errors="coerce")
    lon_v = pd.to_numeric(df[lon], errors="coerce")
    valid = lat_v.between(-90, 90) & lon_v.between(-180, 180)
    dropped = int((~valid).sum())
    sub = df[valid].head(limit)

    rows = []
    for _, row in sub.iterrows():
        r: dict = {"lat": float(row[lat]), "lon": float(row[lon])}
        if name_col and name_col in df.columns: r["name"] = _safe(row[name_col])
        if meas and meas in df.columns: r["value"] = _safe(row[meas])
        rows.append(r)
    return {"type": "geo_points", "rows": rows, "dropped": dropped, "total": len(df)}


def shape_geo_lines(df: pd.DataFrame, config: dict) -> dict:
    """Origin-to-destination lines: lat/lon and lat2/lon2 roles, optional measure
    for line weight. Pairs with an invalid endpoint are dropped and counted, same
    contract as the point map."""
    roles = resolve_roles(config)
    cols = [roles.get(k) for k in ("lat", "lon", "lat2", "lon2")]
    if not all(c and c in df.columns for c in cols):
        return {"type": "empty", "rows": [], "total": 0}
    df = _apply_filters(df, config.get("filters", []))
    meas = roles.get("measure")
    name_col = roles.get("category")
    limit = int(config.get("limit") or 500)

    nums = [pd.to_numeric(df[c], errors="coerce") for c in cols]
    valid = (nums[0].between(-90, 90) & nums[2].between(-90, 90)
             & nums[1].between(-180, 180) & nums[3].between(-180, 180))
    dropped = int((~valid).sum())
    sub = df[valid].head(limit)

    rows = []
    for _, row in sub.iterrows():
        r = {"lat": float(row[cols[0]]), "lon": float(row[cols[1]]),
             "lat2": float(row[cols[2]]), "lon2": float(row[cols[3]])}
        if name_col and name_col in df.columns:
            r["name"] = _safe(row[name_col])
        if meas and meas in df.columns:
            r["value"] = _safe(row[meas])
        rows.append(r)
    return {"type": "geo_lines", "rows": rows, "dropped": dropped, "total": len(df)}


def shape_geo_clusters(df: pd.DataFrame, config: dict) -> dict:
    """Grid clustering for dense point data: points snap to a lat/lon grid and
    each occupied cell becomes one marker carrying its point count (and summed
    measure). The cell size is degrees; the default trades detail for legibility
    at world scale. Clustering is what keeps ten thousand rows from rendering as
    ten thousand overlapping dots."""
    roles = resolve_roles(config)
    lat, lon = roles.get("lat"), roles.get("lon")
    if not (lat and lat in df.columns and lon and lon in df.columns):
        return {"type": "empty", "rows": [], "total": 0}
    df = _apply_filters(df, config.get("filters", []))
    meas = roles.get("measure")
    try:
        cell = float(config.get("cluster_cell_degrees") or 5.0)
    except (TypeError, ValueError):
        cell = 5.0
    cell = min(max(cell, 0.1), 45.0)

    lat_v = pd.to_numeric(df[lat], errors="coerce")
    lon_v = pd.to_numeric(df[lon], errors="coerce")
    valid = lat_v.between(-90, 90) & lon_v.between(-180, 180)
    dropped = int((~valid).sum())
    sub = pd.DataFrame({"lat": lat_v[valid], "lon": lon_v[valid]})
    if meas and meas in df.columns:
        sub["value"] = pd.to_numeric(df[meas][valid], errors="coerce")

    sub["cell_lat"] = (sub["lat"] / cell).round() * cell
    sub["cell_lon"] = (sub["lon"] / cell).round() * cell
    agg = {"lat": ("lat", "mean"), "lon": ("lon", "mean"), "count": ("lat", "size")}
    if "value" in sub.columns:
        agg["value"] = ("value", "sum")
    grouped = sub.groupby(["cell_lat", "cell_lon"], dropna=False).agg(**agg).reset_index(drop=True)
    grouped = grouped.sort_values("count", ascending=False).head(int(config.get("limit") or 500))
    rows = [{k: _safe(v) for k, v in row.items()} for row in grouped.to_dict("records")]
    return {"type": "geo_clusters", "rows": rows, "dropped": dropped,
            "cell_degrees": cell, "total": len(df)}


def shape_geo_pies(df: pd.DataFrame, config: dict) -> dict:
    """A pie at each location: composition of `category2` within each `category`
    (country), sized by the measure. Locations are capped by total value -- a pie
    the size of a pixel communicates nothing -- and slices beyond the top 6 fold
    into 'Other' so every pie stays readable at map scale."""
    roles = resolve_roles(config)
    loc, slc = roles.get("category"), roles.get("category2")
    meas = roles.get("measure")
    if not (loc and slc and loc in df.columns and slc in df.columns):
        return {"type": "empty", "rows": [], "total": 0}
    df = _apply_filters(df, config.get("filters", []))
    limit = min(int(config.get("limit") or 12), 30)

    if meas and meas in df.columns:
        g = df.groupby([loc, slc])[meas].sum().reset_index(name="v")
    else:
        g = df.groupby([loc, slc]).size().reset_index(name="v")

    rows = []
    totals = g.groupby(loc)["v"].sum().sort_values(ascending=False).head(limit)
    for name, total in totals.items():
        part = g[g[loc] == name].sort_values("v", ascending=False)
        slices = [{"label": _safe(r[slc]), "value": _safe(r["v"])} for _, r in part.head(6).iterrows()]
        rest = float(part["v"][6:].sum())
        if rest > 0:
            slices.append({"label": "Other", "value": _safe(rest)})
        rows.append({"name": _safe(name), "total": _safe(total), "slices": slices})
    return {"type": "geo_pies", "rows": rows, "total": len(df)}


#: A map is read, not studied: past this many layers nobody can tell them apart.
MAX_MAP_LAYERS = 6
_LAYER_NEEDS = {
    "regions": (("category", "Region"),),
    "bubbles": (("category", "Region"),),
    "points": (("lat", "Latitude"), ("lon", "Longitude")),
    "lines": (("lat", "From latitude"), ("lon", "From longitude"),
              ("lat2", "To latitude"), ("lon2", "To longitude")),
}


def _geo_layer(df: pd.DataFrame, layer: dict, default_limit: int) -> dict:
    """One layer of a layer stack, or the reason it cannot be drawn.

    An incompatible layer is NAMED in the result, never dropped: a map that
    silently shows three of its four layers reads as "there is nothing there"."""
    kind = layer.get("kind")
    # A legend line needs a name a reader understands, not the layer's type.
    default_title = ({"regions": "{m} by {c}", "bubbles": "{m} by {c} (bubbles)"}.get(kind, "")
                     .format(m=layer.get("measure") or "count", c=layer.get("category") or "region")
                     or {"points": "Points", "lines": "Lines"}.get(kind, str(kind)))
    out = {"id": layer.get("id"), "kind": kind, "title": (layer.get("title") or "").strip() or default_title,
           "boundary_set_id": layer.get("boundary_set_id"), "color": layer.get("color")}
    if kind not in _LAYER_NEEDS:
        return {**out, "error": f"unknown layer type '{kind}'"}
    missing = [label for role, label in _LAYER_NEEDS[kind] if not layer.get(role)]
    if missing:
        return {**out, "error": "needs " + " and ".join(missing)}
    absent = [layer[role] for role, _ in _LAYER_NEEDS[kind] if layer[role] not in df.columns]
    meas = layer.get("measure")
    if meas and meas not in df.columns:
        absent.append(meas)
    if absent:
        return {**out, "error": "column " + ", ".join(f"'{c}'" for c in absent) + " is not in this dataset"}

    if kind in ("regions", "bubbles"):
        loc = layer["category"]
        agg = layer.get("aggregation") or ("sum" if meas else "count")
        if meas:
            vals = pd.to_numeric(df[meas], errors="coerce")
            grouped = vals.groupby(df[loc])
            g = (grouped.mean() if agg == "avg" else grouped.max() if agg == "max"
                 else grouped.min() if agg == "min" else grouped.sum())
        else:
            g = df.groupby(loc).size()
        return {**out, "measure": meas or "count",
                "regions": [{"name": _safe(k), "value": _safe(v)} for k, v in g.items()]}

    lat_v = pd.to_numeric(df[layer["lat"]], errors="coerce")
    lon_v = pd.to_numeric(df[layer["lon"]], errors="coerce")
    valid = lat_v.between(-90, 90) & lon_v.between(-180, 180)
    if kind == "lines":
        lat2 = pd.to_numeric(df[layer["lat2"]], errors="coerce")
        lon2 = pd.to_numeric(df[layer["lon2"]], errors="coerce")
        valid &= lat2.between(-90, 90) & lon2.between(-180, 180)
    limit = min(int(layer.get("limit") or default_limit), 2000)
    idx = df.index[valid.to_numpy()]
    shown = idx[:limit]
    size = pd.to_numeric(df[meas], errors="coerce") if meas else None
    items = []
    for i in shown:
        item = {"lat": float(lat_v[i]), "lon": float(lon_v[i])}
        if kind == "lines":
            item.update({"lat2": float(lat2[i]), "lon2": float(lon2[i])})
        if size is not None:
            item["value"] = _safe(size[i])
        items.append(item)
    return {**out, "measure": meas, ("lines" if kind == "lines" else "points"): items,
            "dropped": int((~valid).sum()),
            # Disclosed like every other cap (constitution rule 2).
            "truncation": {"applied": len(idx) > limit, "shown": len(shown), "of": int(len(idx)),
                           "limit": limit, "reason": "limit", "unit": "rows"}}


def shape_geo_layers(df: pd.DataFrame, config: dict) -> dict:
    """Two layers from one dataset: a region layer (category+measure, like the
    choropleth) and a point layer (lat/lon, sized by measure2). Either layer may
    be absent -- a widget with only regions is a choropleth, only points a point
    map; both together is what this row is for.

    With `config.layers` (MASTER_PLAN Phase 4 item 3) it is a real layer STACK:
    an ordered list, bottom first, of regions / bubbles / points / lines, each
    with its own roles and boundary set."""
    roles = resolve_roles(config)
    df = _apply_filters(df, config.get("filters", []))

    stack = config.get("layers")
    if isinstance(stack, list) and stack:
        layers = [_geo_layer(df, dict(l), int(config.get("limit") or 500))
                  for l in stack[:MAX_MAP_LAYERS] if isinstance(l, dict)]
        if len(stack) > MAX_MAP_LAYERS:
            layers.append({"id": None, "kind": None, "title": f"{len(stack) - MAX_MAP_LAYERS} more",
                           "error": f"a map draws at most {MAX_MAP_LAYERS} layers"})
        return {"type": "geo_layers", "layers": layers, "total": len(df),
                "regions": [], "points": [], "dropped": 0}

    regions = []
    loc, meas = roles.get("category"), roles.get("measure")
    if loc and loc in df.columns:
        if meas and meas in df.columns:
            g = df.groupby(loc)[meas].sum().reset_index(name="value")
        else:
            g = df.groupby(loc).size().reset_index(name="value")
        regions = [{"name": _safe(r[loc]), "value": _safe(r["value"])} for _, r in g.iterrows()]

    points, dropped = [], 0
    lat, lon = roles.get("lat"), roles.get("lon")
    if lat and lon and lat in df.columns and lon in df.columns:
        m2 = roles.get("measure2")
        lat_v = pd.to_numeric(df[lat], errors="coerce")
        lon_v = pd.to_numeric(df[lon], errors="coerce")
        valid = lat_v.between(-90, 90) & lon_v.between(-180, 180)
        dropped = int((~valid).sum())
        sub = df[valid].head(int(config.get("limit") or 500))
        for _, row in sub.iterrows():
            r = {"lat": float(row[lat]), "lon": float(row[lon])}
            if m2 and m2 in df.columns:
                r["value"] = _safe(row[m2])
            points.append(r)
    return {"type": "geo_layers", "regions": regions, "points": points,
            "dropped": dropped, "total": len(df)}


#: The contour grid. Enough cells for smooth isolines at tile size, few
#: enough that every render evaluates the density cheaply.
CONTOUR_NX, CONTOUR_NY = 72, 54
CONTOUR_SAMPLE = 20_000
CONTOUR_LEVELS = (0.1, 0.25, 0.4, 0.55, 0.7, 0.85)


def shape_geo_contour(df: pd.DataFrame, config: dict) -> dict:
    """A density SURFACE from coordinates (MASTER_PLAN Phase 4 item 5).

    A Gaussian kernel density over the points (optionally weighted by the
    measure), evaluated on a grid spanning the data; the renderer shades the
    surface and draws its isolines. Unlike the density map's square cells it
    does not depend on where a grid line happens to fall. The population is
    disclosed: rows used, rows without usable coordinates, and whether the
    estimate ran on a sample."""
    import numpy as np
    from scipy.stats import gaussian_kde

    roles = resolve_roles(config)
    lat, lon = roles.get("lat"), roles.get("lon")
    if not (lat and lon and lat in df.columns and lon in df.columns):
        return {"type": "empty", "rows": [], "total": 0}
    df = _apply_filters(df, config.get("filters", []))
    la = pd.to_numeric(df[lat], errors="coerce")
    lo = pd.to_numeric(df[lon], errors="coerce")
    valid = la.between(-90, 90) & lo.between(-180, 180)
    meas = roles.get("measure")
    weights = None
    if meas and meas in df.columns:
        w = pd.to_numeric(df[meas], errors="coerce")
        valid &= w.notna() & (w > 0)
        weights = w
    n_valid = int(valid.sum())
    base = {"type": "geo_contour", "total": int(len(df)), "points_used": n_valid,
            "dropped": int(len(df) - n_valid), "weighted_by": meas if weights is not None else None}
    if n_valid < 3:
        return {**base, "grid": None,
                "reason": f"A density surface needs at least 3 located rows; {n_valid} have usable coordinates."}
    xs, ys = lo[valid].to_numpy(dtype=float), la[valid].to_numpy(dtype=float)
    ws = weights[valid].to_numpy(dtype=float) if weights is not None else None
    sampled = None
    if len(xs) > CONTOUR_SAMPLE:
        # Deterministic, so the surface does not shimmer between renders.
        idx = np.random.default_rng(7).choice(len(xs), CONTOUR_SAMPLE, replace=False)
        xs, ys = xs[idx], ys[idx]
        ws = ws[idx] if ws is not None else None
        sampled = int(CONTOUR_SAMPLE)
    if np.ptp(xs) == 0 and np.ptp(ys) == 0:
        return {**base, "grid": None, "reason": "Every located row is at the same place; there is no surface to draw."}
    pad_x = max(np.ptp(xs) * 0.12, 0.5)
    pad_y = max(np.ptp(ys) * 0.12, 0.5)
    west, east = max(-180.0, xs.min() - pad_x), min(180.0, xs.max() + pad_x)
    south, north = max(-85.0, ys.min() - pad_y), min(85.0, ys.max() + pad_y)
    gx = np.linspace(west, east, CONTOUR_NX)
    gy = np.linspace(south, north, CONTOUR_NY)
    mx, my = np.meshgrid(gx, gy)
    try:
        # A tiny jitter keeps a column of identical longitudes (a road, a
        # grid survey) from making the covariance singular.
        jitter = np.random.default_rng(11).normal(0, 1e-6, size=(2, len(xs)))
        kde = gaussian_kde(np.vstack([xs, ys]) + jitter, weights=ws)
        z = kde(np.vstack([mx.ravel(), my.ravel()]))
    except (np.linalg.LinAlgError, ValueError) as e:
        return {**base, "grid": None, "reason": f"The density could not be estimated: {e}"}
    peak = float(z.max()) or 1.0
    values = [round(float(v) / peak, 4) for v in z]
    return {**base, "sampled_from": sampled,
            "grid": {"west": float(west), "east": float(east), "south": float(south), "north": float(north),
                     "nx": CONTOUR_NX, "ny": CONTOUR_NY, "values": values},
            "levels": list(CONTOUR_LEVELS), "bandwidth": float(kde.factor)}


def shape_geo_network(df: pd.DataFrame, config: dict) -> dict:
    """A network ON the map: named nodes anchored at real coordinates, links
    between them. Roles: category/category2 name the endpoints, lat/lon and
    lat2/lon2 place them, measure weighs the link. Node positions are the mean
    of every coordinate observed for that name (jittered source points average
    back to the hub), and node size carries degree -- the geographic reading of
    the same structure the network widget lays out abstractly."""
    import collections

    roles = resolve_roles(config)
    src, dst = roles.get("category"), roles.get("category2")
    need = [src, dst, roles.get("lat"), roles.get("lon"), roles.get("lat2"), roles.get("lon2")]
    if not all(c and c in df.columns for c in need):
        return {"type": "empty", "rows": [], "total": 0}
    df = _apply_filters(df, config.get("filters", []))
    meas = roles.get("measure")
    max_links = min(int(config.get("limit") or 200), 500)

    lat1 = pd.to_numeric(df[need[2]], errors="coerce")
    lon1 = pd.to_numeric(df[need[3]], errors="coerce")
    lat2 = pd.to_numeric(df[need[4]], errors="coerce")
    lon2 = pd.to_numeric(df[need[5]], errors="coerce")
    valid = (lat1.between(-90, 90) & lat2.between(-90, 90)
             & lon1.between(-180, 180) & lon2.between(-180, 180))
    dropped = int((~valid).sum())
    sub = df[valid]

    w = pd.to_numeric(sub[meas], errors="coerce").fillna(1.0) if meas and meas in df.columns         else pd.Series(1.0, index=sub.index)
    frame = pd.DataFrame({
        "s": sub[src].astype(str), "t": sub[dst].astype(str), "w": w,
        "slat": lat1[valid], "slon": lon1[valid], "tlat": lat2[valid], "tlon": lon2[valid],
    })
    frame = frame[frame["s"] != frame["t"]]
    if frame.empty:
        return {"type": "geo_network", "nodes": [], "links": [], "dropped": dropped, "total": len(df)}

    links = frame.groupby(["s", "t"])["w"].sum().reset_index()
    links = links.sort_values("w", ascending=False).head(max_links)
    keep = set(links["s"]) | set(links["t"])

    coords: dict = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for _, r in frame.iterrows():
        for name, la, lo in ((r["s"], r["slat"], r["slon"]), (r["t"], r["tlat"], r["tlon"])):
            if name in keep:
                c = coords[name]
                c[0] += la; c[1] += lo; c[2] += 1
    degree = collections.Counter(links["s"]) + collections.Counter(links["t"])

    nodes = [{"id": name, "lat": c[0] / c[2], "lon": c[1] / c[2],
              "degree": degree.get(name, 0)}
             for name, c in coords.items() if c[2]]
    return {"type": "geo_network", "nodes": nodes,
            "links": [{"source": r["s"], "target": r["t"], "value": _safe(r["w"])}
                      for _, r in links.iterrows()],
            "dropped": dropped, "total": len(df)}


def _label_propagation(adj: dict, nodes: list) -> dict:
    """Community detection: which nodes form a cluster.

    Answers "who groups together" -- the question the centralities here cannot.
    Betweenness finds the broker BETWEEN groups but never names the groups.

    **Greedy modularity, not plain label propagation.** Label propagation was
    tried first and collapsed: two triangles joined by a single bridge edge came
    back as ONE community, because every node eventually sees the majority label
    through the bridge. On a graph a reader can see is two clusters, reporting
    one is worse than reporting none. This instead moves each node to the
    neighbouring community that most increases modularity (Newman's Q), which
    weighs a group's internal edges against what chance would predict -- so a
    single bridge between two dense triangles is correctly read as sparse.

    Deterministic: nodes are visited in sorted order and ties break on the lower
    community id, so the same graph always yields the same grouping. A network
    that renamed its clusters on every refresh could not be compared across
    refreshes -- the same reason the layout is seeded.
    """
    deg = {v: len(adj.get(v) or ()) for v in nodes}
    two_m = sum(deg.values()) or 1          # 2 * |E|
    comm = {v: i for i, v in enumerate(nodes)}
    # Total degree of each community, for the modularity null term.
    tot = {i: deg[v] for i, v in enumerate(nodes)}

    for _ in range(20):
        moved = False
        for v in sorted(nodes):
            own = comm[v]
            neighbours = adj.get(v) or ()
            if not neighbours:
                continue
            # Edges from v into each candidate community.
            links: dict[int, int] = {}
            for u in neighbours:
                links[comm[u]] = links.get(comm[u], 0) + 1
            tot[own] -= deg[v]              # remove v before scoring

            best, best_gain = own, None
            for cand, shared in sorted(links.items()):
                # Modularity gain of placing v in `cand`: observed internal
                # edges minus the expectation under a degree-preserving random
                # graph. The null term is what stops everything merging.
                gain = shared - (tot.get(cand, 0) * deg[v]) / two_m
                if best_gain is None or gain > best_gain:
                    best, best_gain = cand, gain
            # Staying put must beat moving on a tie, or nodes churn forever.
            stay = links.get(own, 0) - (tot.get(own, 0) * deg[v]) / two_m
            if best_gain is None or stay >= best_gain:
                best = own

            tot[best] = tot.get(best, 0) + deg[v]
            if best != own:
                comm[v] = best
                moved = True
        if not moved:
            break

    # Renumber densest-first, so "community 0" is the biggest group rather than
    # whichever node happened to be first.
    sizes: dict[int, int] = {}
    for c in comm.values():
        sizes[c] = sizes.get(c, 0) + 1
    ranked = sorted(sizes, key=lambda c: (-sizes[c], c))
    renum = {c: i for i, c in enumerate(ranked)}
    return {v: renum[comm[v]] for v in nodes}


def _predicted_links(adj: dict, nodes: list, limit: int = 10) -> list[dict]:
    """Links that are notably absent: pairs sharing many neighbours but no edge.

    Adamic-Adar over the common neighbours of each unconnected pair. A shared
    neighbour that is itself highly connected says little (a hub is everyone's
    neighbour), so each is weighted by 1/log(degree) -- which is what separates
    this from a plain common-neighbour count.

    Reported as SUGGESTIONS, never drawn as edges. An inferred link rendered
    the same as an observed one would be the chart stating something the data
    does not contain.
    """
    import math

    scores: list[tuple[float, str, str]] = []
    for i, a in enumerate(nodes):
        na = adj.get(a) or set()
        for b in nodes[i + 1:]:
            nb = adj.get(b) or set()
            if b in na:
                continue                      # already connected
            shared = na & nb
            if not shared:
                continue
            score = sum(1.0 / math.log(len(adj.get(c) or ()) + 1e-9)
                        for c in shared if len(adj.get(c) or ()) > 1)
            if score > 0:
                scores.append((score, a, b))
    scores.sort(key=lambda t: (-t[0], t[1], t[2]))
    return [{"source": a, "target": b, "score": round(sc, 4),
             "shared_neighbours": len((adj.get(a) or set()) & (adj.get(b) or set()))}
            for sc, a, b in scores[:limit]]


def _brandes_betweenness(adj: dict, nodes: list) -> dict:
    """Unweighted betweenness (Brandes 2001). Fine at this widget's node cap."""
    import collections
    bc = {v: 0.0 for v in nodes}
    for source in nodes:
        stack = []
        preds = {v: [] for v in nodes}
        sigma = {v: 0 for v in nodes}
        sigma[source] = 1
        dist = {v: -1 for v in nodes}
        dist[source] = 0
        queue = collections.deque([source])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj.get(v, ()):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = {v: 0.0 for v in nodes}
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != source:
                bc[w] += delta[w]
    n = len(nodes)
    norm = (n - 1) * (n - 2) or 1
    return {v: bc[v] / norm for v in nodes}


def shape_network(df: pd.DataFrame, config: dict) -> dict:
    """Link analysis: source-to-target pairs (category/category2 roles, like
    sankey) with an optional weight measure. Ships positions AND centralities so
    the renderer stays a pure draw:

      * layout: seeded Fruchterman-Reingold in numpy -- deterministic, so the
        same data always lands in the same shape (a network that rearranges on
        every refresh cannot be compared across refreshes);
      * degree, closeness and betweenness per node, plus reach (fraction of the
        graph reachable) -- assignable to node size via `centrality_metric`.

    Nodes are capped by degree: the busiest nodes carry the structure, and an
    unreadable 5,000-node hairball answers nothing.
    """
    import collections

    import numpy as np

    roles = resolve_roles(config)
    src, dst = roles.get("category"), roles.get("category2")
    if not (src and dst and src in df.columns and dst in df.columns):
        return {"type": "empty", "rows": [], "total": 0}
    df = _apply_filters(df, config.get("filters", []))
    meas = roles.get("measure")
    max_nodes = min(int(config.get("limit") or 100), 300)

    pairs = df[[src, dst]].dropna()
    if meas and meas in df.columns:
        w = pd.to_numeric(df[meas][pairs.index.isin(df.index)], errors="coerce").reindex(pairs.index).fillna(1.0)
    else:
        w = pd.Series(1.0, index=pairs.index)
    agg = pd.DataFrame({"s": pairs[src].astype(str), "t": pairs[dst].astype(str), "w": w})
    agg = agg[agg["s"] != agg["t"]].groupby(["s", "t"])["w"].sum().reset_index()
    if agg.empty:
        return {"type": "network", "nodes": [], "links": [], "total": len(df)}

    degree = collections.Counter(agg["s"]) + collections.Counter(agg["t"])
    keep = {n for n, _ in degree.most_common(max_nodes)}
    agg = agg[agg["s"].isin(keep) & agg["t"].isin(keep)]
    nodes = sorted(set(agg["s"]) | set(agg["t"]))
    index = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)

    adj = {v: set() for v in nodes}
    for _, row in agg.iterrows():
        adj[row["s"]].add(row["t"])
        adj[row["t"]].add(row["s"])

    deg_c = {v: len(adj[v]) / max(n - 1, 1) for v in nodes}
    clo_c, reach_c = {}, {}
    for v in nodes:
        seen = {v: 0}
        queue = collections.deque([v])
        while queue:
            u = queue.popleft()
            for x in adj[u]:
                if x not in seen:
                    seen[x] = seen[u] + 1
                    queue.append(x)
        reachable = len(seen) - 1
        total_dist = sum(seen.values())
        clo_c[v] = (reachable / total_dist) * (reachable / max(n - 1, 1)) if total_dist else 0.0
        reach_c[v] = reachable / max(n - 1, 1)
    bet_c = _brandes_betweenness(adj, nodes)
    community = _label_propagation(adj, nodes)
    suggested = _predicted_links(adj, nodes)

    rng = np.random.default_rng(42)
    pos = rng.random((n, 2))
    k = (1.0 / max(n, 1)) ** 0.5
    edges = [(index[r["s"]], index[r["t"]]) for _, r in agg.iterrows()]
    for _ in range(60):
        disp = np.zeros((n, 2))
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.linalg.norm(delta, axis=2) + 1e-9
        rep = (k * k / dist)[:, :, None] * (delta / dist[:, :, None])
        disp += rep.sum(axis=1)
        for a, b in edges:
            d = pos[a] - pos[b]
            dd = np.linalg.norm(d) + 1e-9
            f = (dd * dd / k) * (d / dd)
            disp[a] -= f
            disp[b] += f
        length = np.linalg.norm(disp, axis=1) + 1e-9
        pos += (disp / length[:, None]) * np.minimum(length, 0.05)[:, None]
        pos = np.clip(pos, 0.0, 1.0)

    return {
        "type": "network",
        "nodes": [{"id": v, "x": float(pos[index[v], 0]), "y": float(pos[index[v], 1]),
                   "degree": round(deg_c[v], 4), "closeness": round(clo_c[v], 4),
                   "betweenness": round(bet_c[v], 4), "reach": round(reach_c[v], 4),
                   "community": community[v]}
                  for v in nodes],
        "links": [{"source": r["s"], "target": r["t"], "value": _safe(r["w"])}
                  for _, r in agg.iterrows()],
        # Kept OUT of `links` deliberately: these are inferred, and a renderer
        # drawing them alongside observed edges would show the chart asserting
        # something the data does not contain.
        "suggested_links": suggested,
        "communities": len(set(community.values())),
        "total": len(df),
    }


def _naive_forecast(series: pd.Series, periods: int) -> tuple[list[float], list[float] | None, list[float] | None]:
    """Hand-rolled fallback: a least-squares linear trend extrapolated forward.

    Used when the series is too short for statsmodels to fit reliably (< 8 points),
    or when the ETS fit itself fails or produces NaNs. The band is the same
    ±1.96·sigma·sqrt(horizon) construction as the ETS path, computed from this fit's
    own in-sample residuals; it's omitted (None) when there aren't enough points to
    estimate a residual spread.
    """
    import math
    y = series.to_numpy(dtype=float)
    n = len(y)
    x = np.arange(n)
    if n >= 2:
        slope, intercept = np.polyfit(x, y, 1)
        fitted = slope * x + intercept
        sigma = float(pd.Series(y - fitted).std() or 0.0) if n > 2 else 0.0
    else:
        slope, intercept, sigma = 0.0, float(y[0]) if n else 0.0, 0.0
    future_x = np.arange(n, n + periods)
    yhat = [float(v) for v in (slope * future_x + intercept)]
    if sigma:
        lo = [float(v - 1.96 * sigma * math.sqrt(i + 1)) for i, v in enumerate(yhat)]
        hi = [float(v + 1.96 * sigma * math.sqrt(i + 1)) for i, v in enumerate(yhat)]
    else:
        lo = hi = None
    return yhat, lo, hi



#: Forecast horizon bounds -- the registry's params schema pins itself to
#: these (test_registry), so a clamp change here can't silently drift there.
FORECAST_MIN_PERIODS = 1
MAX_FORECAST_PERIODS = 36
DEFAULT_FORECAST_PERIODS = 6

def shape_forecast(df: pd.DataFrame, config: dict) -> dict:
    """A time series with its forecast and confidence band.

    History is shaped exactly like a monthly line chart (same grouping, filters and
    aggregation), then extended `forecast_periods` steps ahead.

    A3: `config["method"]` picks the algorithm -- `"ets"` (default, NEW) fits a
    per-series StatsForecast AutoETS model; `"simple"` runs the original hand-rolled
    forecast (statsmodels Holt-Winters ETS, falling back to a naive linear-trend
    extrapolation for short/unfittable series) UNCHANGED, byte-for-byte, so pinned
    expectations from before this task survive. The `"ets"` path also falls back to
    `"simple"` at runtime whenever the StatsForecast fit is unavailable (import
    failure) or degenerate (raises, or yields NaNs) -- an unfittable series should
    degrade gracefully, never 500. The response's `method` field keeps its original
    meaning (`"ets" | "naive"`, describing which algorithm actually produced the
    numbers); `forecast_method` is an ADDITIVE field carrying the requested
    `"ets" | "simple"` choice verbatim.

    The band is the model's 95%% prediction interval. It widens with horizon, which is
    the honest part: a forecast whose uncertainty does not grow is lying about one of
    the two.
    """
    roles = resolve_roles(config)
    dim = roles.get("category")
    meas = roles.get("measure")
    filters = config.get("filters", [])
    df = _apply_filters(df, filters)
    if not dim or dim not in df.columns or not meas or meas not in df.columns or df.empty:
        return {"type": "empty", "rows": [], "total": 0}

    granularity = config.get("dimension_granularity") or "month"
    labels = _dimension_granularity_label(df[dim], granularity)
    agg = (config.get("aggregation") or "sum").lower()
    series = df.assign(__k__=labels).groupby("__k__")[meas].agg(_pandas_agg_fn(agg)).sort_index()
    series = pd.to_numeric(series, errors="coerce").dropna()
    if len(series) < 2:
        return {"type": "empty", "rows": [], "total": 0,
                "error": "Forecasting needs at least 2 periods of history"}

    periods = max(FORECAST_MIN_PERIODS,
                  min(int(config.get("forecast_periods") or DEFAULT_FORECAST_PERIODS),
                      MAX_FORECAST_PERIODS))
    season = {"month": 12, "quarter": 4, "week": 52, "day": 7}.get(granularity, 0)
    use_season = season > 1 and len(series) >= 2 * season

    requested_method = str(config.get("method") or "ets").lower()
    if requested_method not in ("ets", "simple"):
        requested_method = "ets"

    yhat = lo = hi = None
    method = "naive"
    if requested_method == "ets":
        try:
            sf_result = _forecast_statsforecast_ets(
                series, periods, season if use_season else 0, granularity)
        except Exception:
            sf_result = None
        if sf_result is not None:
            yhat, lo, hi = sf_result
            method = "ets"

    if yhat is None:
        yhat, lo, hi, method = _forecast_simple(series, periods, use_season, season)

    last = str(series.index[-1])
    future_labels = _next_period_labels(last, granularity, periods)
    rows = [{"name": str(k), "value": _safe(v)} for k, v in series.items()]
    forecast = []
    for i in range(periods):
        point = {"name": future_labels[i], "yhat": _safe(float(yhat[i]))}
        if lo is not None:
            point["lo"] = _safe(lo[i])
            point["hi"] = _safe(hi[i])
        forecast.append(point)
    out = {"type": "forecast", "dimension": dim, "measure": meas,
           "rows": rows, "forecast": forecast, "total": len(series), "method": method,
           "forecast_method": requested_method}

    # "When do we reach X?" -- answered here, where the history and the
    # projection already are. Computing it again in the browser, or through a
    # second endpoint that re-fits, would put a caption on screen that could
    # disagree with the chart above it.
    #
    # A target that cannot be answered costs the CAPTION, never the chart: the
    # forecast is the point and the target is an annotation on it.
    target = config.get("forecast_target")
    if target is not None and target != "":
        from .forecast_goal import ForecastGoalError, forecast_goal
        try:
            out["goal"] = forecast_goal(rows, forecast, target)
        except ForecastGoalError:
            pass
    return out


def _forecast_simple(series: pd.Series, periods: int, use_season: bool, season: int
                      ) -> tuple[list[float], list[float] | None, list[float] | None, str]:
    """The original hand-rolled forecast (kept byte-for-byte as the `simple` method
    and as the runtime fallback for the `ets` path): statsmodels Holt-Winters ETS
    when there's enough history, falling back to a naive linear-trend extrapolation
    otherwise (or if the ETS fit raises or yields NaNs)."""
    method = "naive"
    yhat = lo = hi = None
    if len(series) >= 8:
        import math
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            model = ExponentialSmoothing(
                series.to_numpy(), trend="add",
                seasonal="add" if use_season else None,
                seasonal_periods=season if use_season else None,
                initialization_method="estimated",
            ).fit()
            fit_yhat = model.forecast(periods)
            # 95%% interval from the in-sample residual spread, widened with sqrt(horizon):
            # the classic random-walk-error growth. statsmodels' simulate() would be
            # tighter but non-deterministic; a deterministic band beats a slightly
            # better noisy one for a chart that re-renders on every interaction.
            resid = series.to_numpy() - model.fittedvalues
            sigma = float(pd.Series(resid).std() or 0.0)
            if not (np.any(np.isnan(fit_yhat)) or math.isnan(sigma)):
                yhat = [float(v) for v in fit_yhat]
                lo = [float(v - 1.96 * sigma * math.sqrt(i + 1)) for i, v in enumerate(yhat)]
                hi = [float(v + 1.96 * sigma * math.sqrt(i + 1)) for i, v in enumerate(yhat)]
                method = "ets"
        except Exception:
            pass  # fall through to the naive fallback below

    if yhat is None:
        yhat, lo, hi = _naive_forecast(series, periods)
        method = "naive"
    return yhat, lo, hi, method


def _forecast_statsforecast_ets(series: pd.Series, periods: int, season_length: int, granularity: str
                                 ) -> tuple[list[float], list[float], list[float]] | None:
    """A3: per-series AutoETS fit via StatsForecast. LAZILY imported here -- numba's
    JIT warmup costs real seconds and must never run at app startup (see the
    sys.modules lazy-import test in test_shape_forecast.py). Returns None (never
    raises) on any failure so the caller falls straight through to the `simple`
    statsmodels/naive path."""
    from statsforecast import StatsForecast
    from statsforecast.models import AutoETS

    freq = {"month": "MS", "quarter": "QS", "week": "W", "day": "D", "year": "YS"}.get(granularity, "MS")
    try:
        ds = [pd.Period(str(k)).to_timestamp() for k in series.index]
    except Exception:
        return None

    sf_df = pd.DataFrame({"unique_id": "series", "ds": ds, "y": series.to_numpy(dtype=float)})
    model = AutoETS(season_length=max(1, season_length))
    sf = StatsForecast(models=[model], freq=freq, n_jobs=1)
    forecast_df = sf.forecast(df=sf_df, h=periods, level=[95])

    col = getattr(model, "alias", None) or "AutoETS"
    if col not in forecast_df.columns:
        # StatsForecast names the value column after the model's alias; fall back to
        # whichever non-id/ds/interval column is present if that guess is wrong.
        candidates = [c for c in forecast_df.columns
                      if c not in ("unique_id", "ds") and "-lo-" not in c and "-hi-" not in c]
        if not candidates:
            return None
        col = candidates[0]

    lo_col, hi_col = f"{col}-lo-95", f"{col}-hi-95"
    if lo_col not in forecast_df.columns or hi_col not in forecast_df.columns:
        return None

    yhat = forecast_df[col].to_numpy(dtype=float)
    lo = forecast_df[lo_col].to_numpy(dtype=float)
    hi = forecast_df[hi_col].to_numpy(dtype=float)
    if len(yhat) != periods or np.any(np.isnan(yhat)) or np.any(np.isnan(lo)) or np.any(np.isnan(hi)):
        return None

    # Guarantee lo <= yhat <= hi even if the model's interval estimate is noisy for a
    # short/near-degenerate series -- the chart and the ordering test both depend on
    # this holding, not just "usually."
    lo = np.minimum(lo, yhat)
    hi = np.maximum(hi, yhat)
    return [float(v) for v in yhat], [float(v) for v in lo], [float(v) for v in hi]


def _next_period_labels(last_label: str, granularity: str, periods: int) -> list[str]:
    """Continue the label sequence the granularity produced ("2025-12" -> "2026-01")."""
    freq = {"month": "MS", "quarter": "QS", "week": "W", "day": "D", "year": "YS"}.get(granularity, "MS")
    try:
        start = pd.Period(last_label).to_timestamp()
    except Exception:
        start = pd.Timestamp.today().normalize()
    stamps = pd.date_range(start=start, periods=periods + 1, freq=freq)[1:]
    fmt = {"month": "%Y-%m", "quarter": "%Y-%m", "week": "%Y-%m-%d",
           "day": "%Y-%m-%d", "year": "%Y"}.get(granularity, "%Y-%m")
    return [ts.strftime(fmt) for ts in stamps]


def shape_sankey(df: pd.DataFrame, config: dict) -> dict:
    """Nodes and weighted links for a flow diagram.

    Roles: category (source), category2 (target), measure (link weight; row count
    when unset). Self-loops are dropped -- Recharts' sankey layout cannot draw them
    and one self-referential row would blank the whole widget. Node identity is
    (side, name): "US" as a source and "US" as a target are two nodes, which is what
    keeps a two-column flow readable when the same value appears on both sides.
    """
    roles = resolve_roles(config)
    src, dst, meas = roles.get("category"), roles.get("category2"), roles.get("measure")
    filters = config.get("filters", [])
    df = _apply_filters(df, filters)
    if not src or not dst or src not in df.columns or dst not in df.columns or df.empty:
        return {"type": "empty", "rows": [], "total": 0}

    limit = max(1, min(int(config.get("limit") or 30), 200))
    if meas and meas in df.columns:
        grouped = df.groupby([src, dst])[meas].sum()
    else:
        grouped = df.groupby([src, dst]).size()
    grouped = grouped.sort_values(ascending=False).head(limit)

    nodes: list[dict] = []
    index: dict[tuple, int] = {}
    def node_id(side: str, name) -> int:
        key = (side, str(name))
        if key not in index:
            index[key] = len(nodes)
            nodes.append({"name": str(name)})
        return index[key]

    links = []
    for (a, b), v in grouped.items():
        if pd.isna(a) or pd.isna(b) or str(a) == str(b):
            continue
        links.append({"source": node_id("s", a), "target": node_id("t", b),
                      "value": abs(_safe(float(v)) or 0)})
    return {"type": "sankey", "nodes": nodes, "links": links,
            "rows": [], "total": len(links)}


#: How many children one level of a decomposition tree may show. A node fanned
#: out to fifty bars is not a drill-down, it is a bar chart nobody asked for --
#: the rest are folded into an "Other" bucket so the total still reconciles.
DECOMP_MAX_CHILDREN = 12

#: How deep a single response may go. Each level multiplies the node count, and
#: a tree deeper than this is navigation nobody follows.
DECOMP_MAX_DEPTH = 6

#: A field with more distinct values than this is not a level, it is a list.
#: Splitting revenue by `date` gives 633 one-row groups: maximal variation,
#: zero explanation -- and because variation is exactly what the auto-split
#: ranks on, an id-like column would win every time it was offered. The same
#: guard analysis/influencers.py applies, for the same reason.
DECOMP_MAX_LEVELS = 50


def _decomp_children(df: pd.DataFrame, field: str, measure: str | None,
                     aggregation: str, limit: int) -> list[dict]:
    """One level: the value of `measure` for each group of `field`.

    Sorted by contribution, capped, with the tail folded into "Other" rather
    than dropped -- a decomposition whose children do not sum to their parent
    is worse than useless, because the reader cannot tell what is missing.
    """
    if field not in df.columns or df.empty:
        return []
    if measure and measure in df.columns:
        grouped = df.groupby(field)[measure].agg(_pandas_agg_fn(aggregation))
    else:
        grouped = df.groupby(field).size()
    grouped = grouped.sort_values(ascending=False)

    head = grouped.head(limit)
    out = [{"name": str(k), "value": _safe(v), "rows": int((df[field] == k).sum())}
           for k, v in head.items()]
    tail = grouped.iloc[limit:]
    if len(tail):
        # Only meaningful for additive aggregations; for min/max/avg an "Other"
        # bucket would be a number that is not the sum of anything, so the tail
        # is named but its value withheld.
        additive = aggregation in ("sum", "count")
        out.append({
            "name": "Other", "value": _safe(tail.sum()) if additive else None,
            "rows": int(df[field].isin(tail.index).sum()),
            "collapsed": int(len(tail)), "terminal": True,
        })
    return out


def _decomp_best_field(df: pd.DataFrame, candidates: list[str], measure: str | None,
                       aggregation: str) -> str | None:
    """The field that splits this node most sharply.

    "Most sharply" is the spread of group values relative to their mean --
    the same intuition key influencers uses, reduced to one number so levels
    can be ranked. A field whose groups all look alike explains nothing, however
    many of them there are.
    """
    best, best_score = None, 0.0
    for f in candidates:
        if f not in df.columns:
            continue
        try:
            if measure and measure in df.columns:
                g = df.groupby(f)[measure].agg(_pandas_agg_fn(aggregation))
            else:
                g = df.groupby(f).size()
        except Exception:  # noqa: BLE001 -- an unusable column is skipped, not fatal
            continue
        if len(g) < 2:
            continue
        mean = float(g.mean())
        if mean == 0:
            continue
        # Coefficient of variation: scale-free, so a revenue column and a count
        # column are comparable.
        score = float(g.std()) / abs(mean)
        if score > best_score:
            best, best_score = f, score
    return best


def shape_decomposition(df: pd.DataFrame, config: dict) -> dict:
    """A number broken down one level at a time, along a chosen path.

    The tree is driven by `path`: a list of {field, value} steps already taken.
    Each response returns the children of the node that path arrives at, plus
    the running total, so the client holds no analytical logic -- it renders
    what it is given and asks again when the reader drills.

    `split_by` names the field for the NEXT level. When it is absent and
    `auto_split` is set, the server picks the field that separates this node
    most sharply, which is the "explain" behaviour; the reader can always
    override it. Auto-picking every level was deliberately not the default: a
    wrong split at level one sends the whole exploration astray, and the reader
    cannot tell it happened.
    """
    roles = resolve_roles(config)
    measure = roles.get("measure")
    aggregation = config.get("aggregation") or "sum"
    df = _apply_filters(df, config.get("filters", []))

    path = [p for p in (config.get("path") or [])
            if isinstance(p, dict) and p.get("field")]
    if len(path) > DECOMP_MAX_DEPTH:
        path = path[:DECOMP_MAX_DEPTH]

    # Walk the path, narrowing the frame at each step. A step naming a value
    # that no longer exists (the data changed under a saved widget) yields an
    # empty frame rather than an error -- the reader sees an empty branch and
    # can climb back out.
    node = df
    for step in path:
        f, v = step.get("field"), step.get("value")
        if f in node.columns:
            node = node[node[f].astype(str) == str(v)]

    if measure and measure in node.columns and len(node):
        total = _safe(_agg_series(node[measure], aggregation))
    else:
        total = int(len(node))

    used = {p["field"] for p in path}
    candidates = []
    for c in node.columns:
        if c in used or c == measure or pd.api.types.is_numeric_dtype(node[c]):
            continue
        levels = node[c].nunique(dropna=True)
        if 1 < levels <= DECOMP_MAX_LEVELS:
            candidates.append(c)

    split_by = config.get("split_by")
    auto = False
    if not split_by and config.get("auto_split"):
        split_by = _decomp_best_field(node, candidates, measure, aggregation)
        auto = split_by is not None

    limit = max(1, min(int(config.get("limit") or DECOMP_MAX_CHILDREN), 50))
    children = _decomp_children(node, split_by, measure, aggregation, limit) if split_by else []

    return {
        "type": "decomposition",
        "total": total,
        "path": path,
        "split_by": split_by,
        # Set when the server chose the field, so the UI can say so rather than
        # letting a suggestion masquerade as the reader's own choice.
        "auto": auto,
        "children": children,
        # What the reader may drill by next, so the UI needs no schema call.
        "available": candidates,
        "at_max_depth": len(path) >= DECOMP_MAX_DEPTH,
        "rows": [],
    }


#: How many panels one small-multiples widget may draw. Past this the panels are
#: too small to read and the request is doing N shaping passes for nothing --
#: the point of the visual is comparison at a glance, and nobody compares 40
#: things at a glance.
FACET_MAX_PANELS = 12


def shape_small_multiples(df: pd.DataFrame, config: dict) -> dict:
    """The same chart, once per value of a facet field.

    Deliberately a WRAPPER, not a new shaping path: each panel is produced by
    the ordinary `SHAPERS` entry for the inner widget type, over a frame
    filtered to that facet value. So a small-multiples bar chart is exactly the
    bar chart -- same aggregation, same measures, same quick calcs, same
    formatting -- and any future fix to that shaper reaches the panels for free.
    Reimplementing the shaping per-panel would have created a second code path
    that silently drifts from the first.

    Panels are ordered by size (largest facet first) and capped. The tail is
    reported as `omitted` rather than dropped in silence, because a reader
    comparing panels cannot see which categories never made it onto the page.

    **Every panel shares one scale.** `max_value` is computed across all panels
    and returned once, because the entire point of small multiples is comparing
    the panels to each other -- per-panel axes would make a small category look
    identical to a large one, which is the single way this visual lies.
    """
    facet = config.get("facet_by")
    inner = config.get("inner_widget_type") or "bar"
    if inner in ("small_multiples",):        # no recursion, ever
        inner = "bar"

    base = {k: v for k, v in config.items()
            if k not in ("facet_by", "inner_widget_type")}

    if not facet or facet not in df.columns or df.empty:
        # Degrade to the single chart the reader configured rather than drawing
        # nothing: a missing facet column (a renamed field, a saved widget
        # outliving its data) should cost the panels, not the visual.
        one = SHAPERS.get(inner, shape_series)(df, base)
        return {"type": "small_multiples", "facet_by": facet, "inner": inner,
                "panels": [{"name": None, "result": one}], "omitted": 0,
                "max_value": _facet_max([one]), "rows": [], "total": len(df)}

    order = df[facet].astype(str).value_counts()
    limit = max(1, min(int(config.get("facet_limit") or FACET_MAX_PANELS), 30))
    keep = list(order.index[:limit])
    omitted = int(len(order) - len(keep))

    panels = []
    for value in keep:
        sub = df[df[facet].astype(str) == value]
        if sub.empty:
            continue
        panels.append({"name": value,
                       "result": SHAPERS.get(inner, shape_series)(sub, base)})

    return {"type": "small_multiples", "facet_by": facet, "inner": inner,
            "panels": panels, "omitted": omitted,
            "max_value": _facet_max([p["result"] for p in panels]),
            "rows": [], "total": len(df)}


#: Chart types that take lattice roles: the cartesian family, whose panels
#: can share one value axis.
LATTICE_TYPES = ("bar", "line", "area", "scatter", "step", "dot_plot")
#: Chart types with an animation role (a play control through an ordered field).
ANIMATION_TYPES = ("bar", "line", "area", "scatter", "step", "dot_plot", "pie", "donut")
LATTICE_MAX_ROWS = 8
LATTICE_MAX_COLS = 8
LATTICE_MAX_CELLS = 60
_NON_VALUE_KEYS = {"name", "target", "highlight", "x"}


def _lattice_domain(results: list[dict], stacked: bool) -> list[float] | None:
    """One value range across every cell -- the shared axis that makes a
    lattice comparable. Stacked bars span their row sums, not single values."""
    lo = hi = None

    def numeric(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v

    for r in results:
        cols = r.get("columns") or []
        for row in (r.get("rows") or []):
            if isinstance(row, dict):
                nums = [v for k, v in row.items() if k not in _NON_VALUE_KEYS and numeric(v)]
            elif isinstance(row, (list, tuple)):
                # a crossed (dimension2) result: [label, series..., __total__]
                nums = [v for i, v in enumerate(row)
                        if i > 0 and (i >= len(cols) or cols[i] != "__total__") and numeric(v)]
            else:
                continue
            if not nums:
                continue
            cand = [sum(nums)] if stacked and len(nums) > 1 else nums
            lo = min(cand + ([lo] if lo is not None else []))
            hi = max(cand + ([hi] if hi is not None else []))
    if lo is None:
        return None
    return [min(lo, 0.0), max(hi, 0.0)]


def shape_lattice(df: pd.DataFrame, config: dict, widget_type: str,
                  measures: list[dict] | None, flag_partial: bool) -> dict:
    """The widget's own chart, once per (lattice row, lattice column) value pair.

    Like small multiples, a wrapper: each cell is produced by the ordinary
    pipeline for this widget type over the frame narrowed to that pair, so a
    lattice line chart IS the line chart -- same measures, quick calcs,
    display rules, relative dates. Values are ordered by how many rows they hold
    after the widget's filters (largest first) and capped; what was cut is
    worded, never dropped in silence. Every cell shares one value axis
    (`domain`), because per-cell axes would draw a small panel like a big one.
    """
    rows_by = config.get("lattice_rows") or None
    cols_by = config.get("lattice_columns") or None
    base = {k: v for k, v in config.items() if k not in ("lattice_rows", "lattice_columns")}
    missing = [c for c in (rows_by, cols_by) if c and c not in df.columns]
    if missing:
        one = get_widget_data_from_df(df, base, widget_type, measures, flag_partial)
        one["lattice_note"] = f"Lattice column '{missing[0]}' is not in this data; showing one chart."
        return one

    counted = _apply_filters(df, base.get("filters") or [])

    def ordered(col, cap):
        if not col:
            return [None], 0, 0
        vc = counted[col].astype(str).value_counts()
        return list(vc.index[:cap]), int(len(vc)), int(min(cap, len(vc)))

    row_vals, row_total, _ = ordered(rows_by, LATTICE_MAX_ROWS)
    col_cap = LATTICE_MAX_COLS if not rows_by else max(1, min(LATTICE_MAX_COLS, LATTICE_MAX_CELLS // max(1, len(row_vals))))
    col_vals, col_total, _ = ordered(cols_by, col_cap)

    keys = {}
    if rows_by:
        keys["r"] = df[rows_by].astype(str)
    if cols_by:
        keys["c"] = df[cols_by].astype(str)
    cells = []
    for rv in row_vals:
        for cv in col_vals:
            mask = pd.Series(True, index=df.index)
            if rows_by:
                mask &= keys["r"] == rv
            if cols_by:
                mask &= keys["c"] == cv
            sub = df[mask]
            if sub.empty:
                result = {"type": "empty", "rows": [], "total": 0}
            else:
                # no per-cell partial flag: a panel whose category stopped
                # selling in June is not "unfinished" -- coverage is judged once,
                # over the whole frame, below
                result = get_widget_data_from_df(sub, base, widget_type, measures, False)
            cells.append({"row": rv, "col": cv, "result": result})

    partial = None
    if flag_partial:
        from .relative_dates import partial_period
        try:
            partial = partial_period(df, base.get("dimension"), base.get("dimension_granularity"),
                                     {"rows": [r for c in cells for r in (c["result"].get("rows") or [])]})
        except Exception:  # noqa: BLE001 -- a flag must never break a render
            partial = None
        if partial:
            for c in cells:
                if c["result"].get("type") not in ("empty", "error"):
                    c["result"]["partial_period"] = partial

    parts = []
    if rows_by and row_total > len(row_vals):
        parts.append(f"{len(row_vals)} of {row_total} {rows_by} values")
    if cols_by and col_total > len(col_vals):
        parts.append(f"{len(col_vals)} of {col_total} {cols_by} values")
    truncation = None
    if parts:
        truncation = {"text": "Showing " + " and ".join(parts)
                      + f" (those with the most rows) -- at most {LATTICE_MAX_CELLS} panels stay readable.",
                      "rows_shown": len(row_vals), "rows_of": row_total,
                      "cols_shown": len(col_vals), "cols_of": col_total}
    stacked = str(config.get("bar_mode") or "") in ("stacked", "stacked100")
    return {
        "type": "lattice", "inner": widget_type,
        "rows_by": rows_by, "cols_by": cols_by,
        "row_values": row_vals if rows_by else [], "col_values": col_vals if cols_by else [],
        "cells": cells,
        "domain": None if str(config.get("bar_mode") or "") == "stacked100"
                  else _lattice_domain([c["result"] for c in cells], stacked),
        "lattice_truncation": truncation,
        **({"partial_period": partial} if partial else {}),
        "rows": [], "total": int(len(counted)),
    }


ANIMATION_MAX_FRAMES = 60


def shape_animation(df: pd.DataFrame, config: dict, widget_type: str,
                    measures: list[dict] | None) -> dict:
    """The widget's chart once per value of an ordered field, for a play control.

    Frames are in the field's own order -- chronological for dates (bucketed by
    `animate_granularity` when set: month, quarter, year...), numeric for
    numbers, alphabetical otherwise -- never by size, because a time-lapse out
    of order is not a time-lapse. Each frame is the ordinary pipeline for this
    widget type over that slice; all frames share one value axis so bars grow
    and shrink against a fixed scale instead of the axis rescaling under them.
    Past the frame cap the MOST RECENT frames are kept, and the cut is worded.
    """
    col = config.get("animate_by")
    gran = config.get("animate_granularity") or None
    base = {k: v for k, v in config.items() if k not in ("animate_by", "animate_granularity")}
    if col not in df.columns:
        one = get_widget_data_from_df(df, base, widget_type, measures, False)
        one["animation_note"] = f"Animation field '{col}' is not in this data; showing one chart."
        return one

    series = df[col]
    if gran:
        keys = _bucket_dimension(series, gran)
    else:
        keys = series
    counted = _apply_filters(df.assign(__frame__=keys), base.get("filters") or [])
    present = counted["__frame__"].dropna().unique().tolist()
    if not present:
        return {"type": "empty", "rows": [], "total": 0}

    def sort_key(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return (0, float(v), "")
        try:
            return (1, pd.Timestamp(v).value, "")
        except (ValueError, TypeError):
            return (2, 0.0, str(v))
    ordered = sorted(present, key=sort_key)
    omitted = max(0, len(ordered) - ANIMATION_MAX_FRAMES)
    ordered = ordered[-ANIMATION_MAX_FRAMES:]

    framed = df.assign(__frame__=keys)
    frames = []
    for v in ordered:
        sub = framed[framed["__frame__"] == v].drop(columns="__frame__")
        frames.append({"label": str(v.date()) if isinstance(v, pd.Timestamp) else str(v),
                       "result": get_widget_data_from_df(sub, base, widget_type, measures, False)})
    stacked = str(config.get("bar_mode") or "") in ("stacked", "stacked100")
    return {
        "type": "animated", "inner": widget_type, "animate_by": col, "granularity": gran,
        "frames": frames,
        "domain": None if str(config.get("bar_mode") or "") == "stacked100"
                  else _lattice_domain([f["result"] for f in frames], stacked),
        "animation_truncation": ({"text": f"Showing the last {len(frames)} of {len(frames) + omitted} "
                                          f"{col} values -- a longer run stops being watchable.",
                                  "shown": len(frames), "of": len(frames) + omitted} if omitted else None),
        "rows": [], "total": int(len(counted)),
    }


def _facet_max(results: list[dict]) -> float | None:
    """The largest value across every panel, for one shared scale.

    None when no panel carries numeric rows -- the renderer then falls back to
    per-panel scaling, which is wrong for comparison but better than dividing
    by nothing.
    """
    best = None
    for r in results or []:
        for row in (r.get("rows") or []):
            v = row.get("value") if isinstance(row, dict) else None
            if isinstance(v, (int, float)):
                best = v if best is None else max(best, v)
    return best


SHAPERS: dict[str, Callable[[pd.DataFrame, dict], dict]] = {
    "bar":      shape_series,
    "map_choropleth": shape_series,
    "forecast":       shape_forecast,
    "sankey":         shape_sankey,
    "map_points":     shape_geo_points,
    "map_bubbles":    shape_geo_points,
    "map_lines":      shape_geo_lines,
    "map_clusters":   shape_geo_clusters,
    "map_density":    shape_geo_clusters,
    "map_contour":    shape_geo_contour,
    "map_pie":        shape_geo_pies,
    "map_network":    shape_geo_network,
    "map_layers":     shape_geo_layers,
    "network":        shape_network,
    "decomposition":  shape_decomposition,
    "small_multiples": shape_small_multiples,
    "line":     shape_series,
    "pie":      shape_series,
    "donut":    shape_series,
    "treemap":  shape_series,
    "custom_graph": shape_custom_graph,
    "slicer": shape_slicer,
    "scatter":  shape_series,
    "step":     shape_series,
    "dot_plot": shape_series,
    "kpi":      shape_series,
    "table":    shape_series,
    "crosstab": shape_series,
    "matrix": shape_series,
    "list":     shape_series,
    "needle":   shape_series,
    "histogram": shape_histogram,
    "butterfly":               shape_dual_series,
    "dual_axis_bar":           shape_dual_series,
    "dual_axis_line":          shape_dual_series,
    "dual_axis_bar_line":      shape_dual_series,
    "dual_axis_time_series":   shape_dual_series,
    "comparative_time_series": shape_dual_series,
    "numeric_series": shape_xy_numeric,
    "bubble": shape_bubble,
    "bubble_change": shape_bubble_animated,
    "correlation_matrix": shape_correlation_matrix,
    "heatmap": shape_heatmap,
    "parallel_coordinates": shape_parallel_coordinates,
    "box_plot": shape_box_plot,
    "waterfall": shape_waterfall,
    "gauge": shape_gauge,
    "schedule": shape_gantt,
    "vector_plot": shape_vector_plot,
    "word_cloud": shape_series,
    "area": shape_series,
    "funnel": shape_series,
    "card": shape_card,
    "script": shape_script,
    "ribbon": shape_heatmap,
}

#: Widget types whose shaper honours `config.rank` -- DERIVED from the dispatch
#: table, never hand-listed, so a shaper gaining or losing ranking changes this
#: automatically and the frontend mirror test fails until the panel catches up.
#: The hierarchy family is deliberately absent: sunburst/icicle/tree have their
#: own reconciling top-N + "Other" (HIER_MAX_CHILDREN), and a second rank path
#: there would drift from the first. `network` likewise ranks by its degree cap.
_RANKING_SHAPERS = ("shape_series", "shape_dual_series", "shape_heatmap")
#: kpi is excluded by name: it aggregates ONE number with no dimension, so a
#: Top-N control there is a control wired to nothing.
RANKED_WIDGETS = tuple(sorted(
    k for k, v in SHAPERS.items()
    if getattr(v, "__name__", "") in _RANKING_SHAPERS and k != "kpi"))



_LEGACY_ROLE_KEYS = {
    "dimension": "category", "dimension2": "category2", "measure": "measure",
    "measure2": "measure2", "start": "start",
    "size": "size", "color": "color", "group": "group", "animation": "animation",
    "end": "end", "target": "target", "direction": "direction",
    # Multi-value roles are written by WidgetConfigPanel at TOP LEVEL under the role's
    # own name (`config[rf.role] = vals`), unlike single roles which go through
    # configKeyFor. Without this entry resolve_roles returned {} for a panel-authored
    # card or parallel-coordinates widget, and both rendered empty -- configurable in
    # the UI, blank on the canvas. Every widget with `multi: true` in ROLE_SPECS uses
    # this one role name.
    "measures": "measures",
    "lat": "lat", "lon": "lon", "lat2": "lat2", "lon2": "lon2",
}


def resolve_roles(config: dict) -> dict:
    """Map a widget config to its role assignments.

    If the 'roles' key is present in config at all (even as an empty dict),
    it is authoritative and REPLACES the legacy mapping entirely — it is not
    merged with dimension/dimension2/measure. Only when 'roles' is absent are
    roles built from the legacy dimension/dimension2/measure keys, for
    backward compatibility with configs saved before the roles model existed.
    """
    if "roles" in config:
        return {k: v for k, v in (config["roles"] or {}).items() if v}
    roles = {}
    for legacy_key, role_name in _LEGACY_ROLE_KEYS.items():
        value = config.get(legacy_key)
        if value:
            roles[role_name] = value
    return roles


def get_widget_data_from_df(
    df: pd.DataFrame, config: dict, widget_type: str = "bar",
    measures: list[dict] | None = None, flag_partial: bool = True,
    check_fields: bool = True,
) -> dict:
    """Dispatch to the shaper registered for widget_type, falling back to shape_series
    for any widget_type not yet registered (keeps unknown/future types working).

    Measure definitions travel to the shaper inside a copy of config rather than as a
    new parameter on all 15 shaper signatures. The key is overwritten, never merged, so
    a client cannot smuggle its own measure definitions in through the request body.

    `check_fields=False` is for a PRE-AGGREGATED frame (the DuckDB and DirectQuery
    aggregate paths), which holds only the dimension and measure columns and whose
    caller has already validated the config's fields against the dataset."""
    shaper = SHAPERS.get(widget_type, shape_series)
    if check_fields:
        # A field the widget names that is neither a column here nor a defined
        # measure used to fall through the shaper's no-measure branch and
        # render a ROW COUNT under the measure's name -- live, "Margin % by
        # region" read 517, 514, 509, 460 after its measure was renamed. An
        # explicit error the frontend already draws as a tile, never a count.
        known = set(df.columns) | {m.get("name") for m in (measures or []) if isinstance(m, dict)}
        for key in ("measure", "measure2", "dimension", "dimension2"):
            name = config.get(key)
            if isinstance(name, str) and name and name not in known:
                return {"type": "error", "code": "unknown_field",
                        "message": f"'{name}' is not a column or measure on this dataset",
                        "field": key, "rows": [], "total": 0}
    # The widget type travels IN the config as well, for the same reason
    # measure_defs does: the five hierarchy layouts share one shaper and it must
    # know which of them it is drawing -- a sunburst refuses aggregations a tree
    # accepts. Overwritten rather than merged, so a request body cannot claim to
    # be a different widget than the one that was dispatched.
    config = {**config, "measure_defs": measures or [], "widget_type": widget_type}
    # Relative dates resolve HERE, once, over the reader's whole visible frame:
    # every shaper then sees a concrete date_range, and the resolved windows
    # travel back as notes naming their anchor (see services/relative_dates).
    from .relative_dates import has_relative, partial_period, resolve_filters
    relative_notes: list[dict] = []
    if has_relative(config.get("filters")):
        resolved, relative_notes = resolve_filters(df, config.get("filters"),
                                                   _today_for(config))
        config["filters"] = resolved
    if widget_type in ANIMATION_TYPES and config.get("animate_by"):
        anim = shape_animation(df, {k: v for k, v in config.items()
                                    if k not in ("measure_defs", "widget_type")},
                               widget_type, measures)
        if relative_notes:
            anim["relative_dates"] = relative_notes
        return anim
    if widget_type in LATTICE_TYPES and (config.get("lattice_rows") or config.get("lattice_columns")):
        lattice = shape_lattice(df, {k: v for k, v in config.items()
                                     if k not in ("measure_defs", "widget_type")},
                                widget_type, measures, flag_partial)
        if relative_notes:
            lattice["relative_dates"] = relative_notes
        return lattice
    try:
        result = shaper(df, config)
    except ValueError as e:
        # Measure evaluation failed. Surfacing the error beats falling back to a base
        # column, which would render a plausible-looking but wrong number.
        # `code` beside `message`: this body is the second error channel a
        # widget can receive, and until it carried a code the frontend never
        # read it -- the widget drew an empty chart and the message was lost.
        return {"type": "error", "code": "measure_error", "message": str(e),
                "rows": [], "total": 0}

    # Display rules are resolved against the SHAPED result, because a rule refers to the
    # aggregated value a mark shows. Attached here rather than inside each of the 15
    # shapers, so every widget type gets rules without touching a shaper.
    rules = config.get("display_rules") or []
    if rules and result.get("type") != "error":
        from app.services.display_rules import evaluate_rules  # local: avoids an import cycle

        styles = evaluate_rules(result, rules)
        result["rule_errors"] = styles.pop("errors")
        result["rule_styles"] = styles
    if relative_notes and isinstance(result, dict):
        result["relative_dates"] = relative_notes
    # flag_partial is off for pre-aggregated frames (DuckDB, DirectQuery):
    # their date column holds bucket labels, not the data's real dates.
    if flag_partial and isinstance(result, dict) and result.get("type") not in ("error", "empty"):
        try:
            partial = partial_period(df, config.get("dimension"),
                                     config.get("dimension_granularity"), result)
        except Exception:  # noqa: BLE001 -- a flag must never break a render
            partial = None
        if partial:
            result["partial_period"] = partial
    # One disclosure vocabulary (constitution rules 4 and 5): every result says
    # how many rows it describes, under one name. Shapers already report that
    # population as `total`; the crosstab, whose `total` counts its grid,
    # reports its own. Shapers that keep every group say so explicitly, so a
    # client never has to guess whether a missing `truncation` means "nothing
    # dropped" or "nobody said".
    if isinstance(result, dict) and result.get("type") != "error":
        if "rows_scanned" not in result and isinstance(result.get("total"), int):
            result["rows_scanned"] = result["total"]
        if "truncation" not in result and shaper in _KEEPS_EVERY_GROUP:
            result["truncation"] = {"applied": False, "reason": "none"}
    return result


def _today_for(config: dict):
    """The 'today' a relative filter anchors to. get_widget_data stamps it into
    the config (and so into the cache key) so a cached "last 7 days" can never
    be served the next morning; a direct caller gets the server's date."""
    from datetime import date
    stamp = config.get("__today__")
    if isinstance(stamp, str):
        try:
            return date.fromisoformat(stamp)
        except ValueError:
            pass
    return date.today()


import ast as _ast
import math as _math
import re as _re

_ALLOWED_AST_NODES = (
    _ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.BoolOp, _ast.Compare,
    _ast.Call, _ast.Name, _ast.Constant, _ast.Load,
    _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Mod, _ast.Pow, _ast.FloorDiv,
    _ast.USub, _ast.UAdd, _ast.Not, _ast.And, _ast.Or,
    _ast.Eq, _ast.NotEq, _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE, _ast.In, _ast.NotIn,
    _ast.List, _ast.Tuple,
)


def _validate_expr_safety(expr: str) -> None:
    """Reject any expression that isn't built from a small allowlist of safe AST node
    types. Critically, ast.Attribute (all `x.y` dot access) is NOT in the allowlist —
    this blocks both dunder attribute escapes (e.g. `SUM.__globals__`, including
    unicode-lookalike-underscore variants that survive a substring blocklist) and
    zero-dunder method-call escapes (e.g. `a.to_csv(path)`) structurally, rather than
    trying to enumerate dangerous names.

    Backtick-quoted column names (e.g. `col name`) aren't valid Python syntax on their
    own, so they're normalized to a placeholder identifier before parsing — otherwise
    ast.parse would raise SyntaxError on any backtick-containing expression and this
    check would be skipped entirely, letting an expression like `` `a`.sum.__globals__ ``
    reach pandas' own df.eval() unvalidated (df.eval() natively resolves attribute
    chains on backtick-quoted columns, including dunders — confirmed by direct test).

    A SyntaxError from ast.parse is treated as REJECTED, not passed through. pandas'
    own df.eval() supports syntax that isn't valid standalone Python — most notably
    `@name` to resolve a local/global variable by name (e.g. `@df.to_csv(path)`
    resolves `df` from _eval_expr's own frame and calls an arbitrary method on it,
    confirmed exploitable for arbitrary file write/RCE via to_csv/to_pickle). A prior
    version of this check treated SyntaxError as "not our problem, let df.eval/eval
    raise their own error" — but df.eval() doesn't raise on `@`-syntax, it executes it.
    Nothing legitimate in this codebase needs syntax standard Python doesn't have, so
    anything that fails to parse here is rejected outright."""
    normalized = _re.sub(r'`[^`]+`', 'col', expr)
    try:
        tree = _ast.parse(normalized, mode='eval')
    except SyntaxError as e:
        raise ValueError(f"Expression is not valid: {e}") from e
    for node in _ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ValueError(f"Expression contains a disallowed construct: {type(node).__name__}")
        if isinstance(node, _ast.Name) and node.id.startswith('_'):
            raise ValueError("Expression references a disallowed identifier")


def _build_safe_ns(df: pd.DataFrame) -> tuple[dict, dict]:
    """Return (safe_globals, local_ns) for evaluating expressions against df."""
    def IF(cond, true_val, false_val):  # noqa: N802
        return np.where(cond, true_val, false_val)

    def SWITCH(col, *args):  # noqa: N802
        """SWITCH(col, val1, res1, val2, res2, ..., default)"""
        conditions, choices = [], []
        i = 0
        while i + 1 < len(args):
            conditions.append(col == args[i])
            choices.append(args[i + 1])
            i += 2
        default = args[i] if i < len(args) else None
        result = np.select(conditions, choices, default=default) if conditions else col
        return pd.Series(result, index=col.index)

    # ── Text ──────────────────────────────────────────────────────────────────
    # These have to be real functions rather than a user-facing `.str.*` accessor:
    # _validate_expr_safety structurally forbids attribute access, which is exactly
    # why the expression palette once shipped snippets that could never run.
    #
    # Two conventions, both chosen to match SAS and DAX rather than Python:
    #   - positions are 1-based (SUBSTRING/FIND/SPLIT)
    #   - FIND returns 0 when absent, so the result doubles as a truthiness test
    def _txt(s):
        """Coerce to string, rendering missing values as '' rather than the literal
        'nan' — which would otherwise appear in a chart axis as real data."""
        if isinstance(s, pd.Series):
            return s.fillna("").astype(str)
        return "" if pd.isna(s) else str(s)

    def SENTIMENT(s):  # noqa: N802
        """Lexicon tone of each text, -1..1 (English + Arabic, negation-aware);
        empty where the text holds no scored word -- unscored, not neutral."""
        from .text_lang import sentiment_series
        return sentiment_series(_txt(s)) if isinstance(s, pd.Series) else sentiment_series(pd.Series([_txt(s)])).iloc[0]

    def SENTIMENT_LABEL(s):  # noqa: N802
        from .text_lang import label_of, sentiment_series
        if isinstance(s, pd.Series):
            return sentiment_series(_txt(s)).map(label_of)
        return label_of(sentiment_series(pd.Series([_txt(s)])).iloc[0])

    def UPPER(s):      return _txt(s).str.upper()                      # noqa: E704,N802
    def LOWER(s):      return _txt(s).str.lower()                      # noqa: E704,N802
    def TRIM(s):       return _txt(s).str.strip()                      # noqa: E704,N802
    def LEN(s):        return _txt(s).str.len()                        # noqa: E704,N802
    def REVERSE(s):    return _txt(s).str[::-1]                        # noqa: E704,N802
    def LEFT(s, n):    return _txt(s).str[:int(n)]                     # noqa: E704,N802
    def RIGHT(s, n):   return _txt(s).str[-int(n):]                    # noqa: E704,N802
    def SUBSTRING(s, start, length):  # noqa: N802
        begin = max(int(start) - 1, 0)
        return _txt(s).str[begin:begin + int(length)]
    def CONCAT(a, b):  return _txt(a) + _txt(b)                        # noqa: E704,N802
    def REPLACE(s, find, repl):  # noqa: N802
        return _txt(s).str.replace(str(find), str(repl), regex=False)
    def FIND(s, sub):  # noqa: N802
        return _txt(s).str.find(str(sub)) + 1
    def CONTAINS(s, sub):    return _txt(s).str.contains(str(sub), regex=False)   # noqa: E704,N802
    def STARTSWITH(s, pre):  return _txt(s).str.startswith(str(pre))              # noqa: E704,N802
    def ENDSWITH(s, suf):    return _txt(s).str.endswith(str(suf))                # noqa: E704,N802
    def SPLIT(s, sep, index):  # noqa: N802
        i = int(index) - 1
        return _txt(s).str.split(str(sep)).map(lambda parts: parts[i] if 0 <= i < len(parts) else "")
    def LPAD(s, width, fill=" "):  # noqa: N802
        return _txt(s).str.rjust(int(width), str(fill)[:1] or " ")
    def RPAD(s, width, fill=" "):  # noqa: N802
        return _txt(s).str.ljust(int(width), str(fill)[:1] or " ")

    # ── Aggregation (return scalar broadcast across all rows) ─────────────────
    def SUM(s):       return s.sum()         # noqa: N802
    def AVG(s):       return s.mean()        # noqa: N802
    def MEDIAN(s):    return s.median()      # noqa: N802
    def COUNT(s):     return s.count()       # noqa: N802
    def COUNTD(s):    return s.nunique()     # noqa: N802
    def STDEV(s):     return s.std()         # noqa: N802
    def VARIANCE(s):  return s.var()         # noqa: N802
    def PCT_TOTAL(s): return s / s.sum() * 100                              # noqa: N802
    def NORMALIZE(s): return (s - s.min()) / (s.max() - s.min())           # noqa: N802
    def ZSCORE(s):    return (s - s.mean()) / s.std()                       # noqa: N802

    # ── Running / window ──────────────────────────────────────────────────────
    def CUMSUM(s):       return s.cumsum()                                  # noqa: N802
    def CUMPCT(s):       return s.cumsum() / s.sum() * 100                 # noqa: N802
    def RANK(s):         return s.rank()                                    # noqa: N802
    def DIFF(s):         return s.diff()                                    # noqa: N802
    def LAG(s, n=1):     return s.shift(n)                                  # noqa: N802
    def LEAD(s, n=1):    return s.shift(-n)                                 # noqa: N802

    # ── Group-by window (aggregate per group, broadcast back) ─────────────────
    def GROUPSUM(s, g):   return s.groupby(g).transform('sum')             # noqa: N802
    def GROUPAVG(s, g):   return s.groupby(g).transform('mean')            # noqa: N802
    def GROUPCOUNT(s, g): return s.groupby(g).transform('count')           # noqa: N802
    def GROUPRANK(s, g):  return s.groupby(g).transform('rank')            # noqa: N802
    def GROUPMIN(s, g):   return s.groupby(g).transform('min')             # noqa: N802
    def GROUPMAX(s, g):   return s.groupby(g).transform('max')             # noqa: N802
    def GROUPPCT(s, g):   return s / s.groupby(g).transform('sum') * 100   # noqa: N802

    # ── Date / time intelligence ───────────────────────────────────────────
    def _as_datetime(s):
        """Coerce a Series to datetime64 if it isn't already; errors='coerce' turns
        unparseable values into NaT rather than raising."""
        if pd.api.types.is_datetime64_any_dtype(s):
            return s
        return pd.to_datetime(s, errors='coerce')

    def YEAR(s):     return _as_datetime(s).dt.year        # noqa: N802
    def QUARTER(s):  return _as_datetime(s).dt.quarter      # noqa: N802
    def MONTH(s):    return _as_datetime(s).dt.month        # noqa: N802
    def DAY(s):      return _as_datetime(s).dt.day          # noqa: N802

    def WEEKDAY(s):  return _as_datetime(s).dt.dayofweek + 1   # noqa: N802  1 = Monday, matching SAS
    def WEEK(s):     return _as_datetime(s).dt.isocalendar().week.astype("Int64")  # noqa: N802
    def HOUR(s):     return _as_datetime(s).dt.hour        # noqa: N802
    def MINUTE(s):   return _as_datetime(s).dt.minute      # noqa: N802
    def SECOND(s):   return _as_datetime(s).dt.second      # noqa: N802
    def DAYOFYEAR(s): return _as_datetime(s).dt.dayofyear  # noqa: N802
    def MONTHNAME(s): return _as_datetime(s).dt.month_name()   # noqa: N802
    def DAYNAME(s):   return _as_datetime(s).dt.day_name()     # noqa: N802

    # ── Date construction ──────────────────────────────────────────────────────
    # Named after SAS's DateFromMDY / Now / Today rather than Python's constructors,
    # because the expression language these appear in is modelled on SAS and DAX.
    def DATEFROMYMD(y, m, d):  # noqa: N802
        """Build a date from year, month and day parts, each a column or a constant."""
        parts = pd.DataFrame({"year": y, "month": m, "day": d})
        return pd.to_datetime(parts, errors="coerce")

    def DATEADD(s, amount, unit="day"):  # noqa: N802
        """Shift a date by a whole number of units. Months and years go through
        DateOffset rather than a fixed number of days, so month-end arithmetic
        behaves the way a calendar does rather than the way 30-day maths does."""
        dt = _as_datetime(s)
        unit = str(unit).lower().rstrip("s")
        n = int(amount)
        if unit in ("month", "year"):
            return dt + pd.DateOffset(**{unit + "s": n})
        allowed = {"day": "D", "week": "W", "hour": "h", "minute": "min", "second": "s"}
        if unit not in allowed:
            raise ValueError(f"DATEADD: unsupported unit {unit!r}")
        return dt + pd.to_timedelta(n, unit=allowed[unit])

    def DATEDIFF(a, b, unit="day"):  # noqa: N802
        """Whole units from `a` to `b`. Months and years are calendar differences,
        not a timedelta divided by an average month length."""
        d1, d2 = _as_datetime(a), _as_datetime(b)
        unit = str(unit).lower().rstrip("s")
        if unit == "year":
            return d2.dt.year - d1.dt.year
        if unit == "month":
            return (d2.dt.year - d1.dt.year) * 12 + (d2.dt.month - d1.dt.month)
        delta = d2 - d1
        if unit == "day":    return delta.dt.days
        if unit == "week":   return delta.dt.days // 7
        if unit == "hour":   return (delta.dt.total_seconds() // 3600).astype("Int64")
        if unit == "minute": return (delta.dt.total_seconds() // 60).astype("Int64")
        if unit == "second": return delta.dt.total_seconds().astype("Int64")
        raise ValueError(f"DATEDIFF: unsupported unit {unit!r}")

    def TODAY():  # noqa: N802
        return pd.Timestamp.today().normalize()

    def NOW():  # noqa: N802
        return pd.Timestamp.now()

    # ── Date <-> number coercion ───────────────────────────────────────────────
    def TODATE(s):  # noqa: N802
        """Parse text or an epoch-day number into a date. The two directions are a
        pair: TONUMBER(TODATE(x)) round-trips."""
        if pd.api.types.is_numeric_dtype(s):
            return pd.to_datetime(s, unit="D", origin="unix", errors="coerce")
        return _as_datetime(s)

    def TONUMBER(s):  # noqa: N802
        """Epoch days, matching TODATE's numeric input. NaT becomes NA rather than a
        misleading zero, which would plot as 1970."""
        dt = _as_datetime(s)
        return (dt - pd.Timestamp("1970-01-01")).dt.days.astype("Int64")

    # ── Advanced statistics ────────────────────────────────────────────────────
    def PERCENTILE(s, q):  # noqa: N802
        """q is 0-100, matching SAS and Excel rather than pandas' 0-1."""
        return s.quantile(float(q) / 100.0)

    def MODE(s):      return s.mode().iloc[0] if not s.mode().empty else None  # noqa: N802
    def CORR(a, b):   return a.corr(b)        # noqa: N802
    def COVAR(a, b):  return a.cov(b)         # noqa: N802
    def SKEW(s):      return s.skew()         # noqa: N802
    def KURTOSIS(s):  return s.kurt()         # noqa: N802
    def IQR(s):       return s.quantile(0.75) - s.quantile(0.25)  # noqa: N802
    def SE(s):        return s.sem()          # noqa: N802

    def PVALT(s, mu=0):  # noqa: N802
        """Two-sided one-sample t-test p-value against mu, matching SAS's PvalT.
        scipy was already a project dependency; this closes the last name the
        advanced-statistics gap row listed."""
        from scipy import stats as _scipy_stats
        clean = s.dropna() if hasattr(s, "dropna") else s
        if len(clean) < 2:
            return pd.NA
        return float(_scipy_stats.ttest_1samp(clean, float(mu)).pvalue)

    def COEFVAR(s):  # noqa: N802
        """Coefficient of variation as a percentage, matching SAS's CoefVar. Returns NA
        rather than infinity when the mean is zero -- a division blow-up in a chart axis
        is worse than a gap."""
        mean = s.mean()
        return (s.std() / mean * 100) if mean else pd.NA

    def CSS(s):       return ((s - s.mean()) ** 2).sum()   # noqa: N802  corrected sum of squares
    def FIRST(s):     return s.iloc[0] if len(s) else None  # noqa: N802
    def LAST(s):      return s.iloc[-1] if len(s) else None  # noqa: N802

    def DATETRUNC(s, unit):  # noqa: N802
        dt = _as_datetime(s)
        unit = str(unit).lower()
        period_code = {'year': 'Y', 'quarter': 'Q', 'month': 'M', 'week': 'W', 'day': 'D'}.get(unit)
        if period_code is None:
            raise ValueError(f"DATETRUNC: unsupported unit '{unit}'")
        if period_code == 'D':
            return dt.dt.normalize()
        return dt.dt.to_period(period_code).dt.start_time

    def YTD(measure, date_col):  # noqa: N802
        """Cumulative sum within each calendar year, resetting at each year boundary.
        Uses row order (positional), matching CUMSUM/DIFF/LAG/LEAD's existing convention
        of never implicitly re-sorting the caller's dataframe."""
        year = _as_datetime(date_col).dt.year
        return measure.groupby(year).cumsum()

    def SAMEPERIODLASTYEAR(measure, date_col):  # noqa: N802
        """Monthly YoY lookup: SUM of measure in the same calendar month one year
        earlier, broadcast to every row sharing that (year, month). NaN if no data
        exists for (year-1, month)."""
        dt = _as_datetime(date_col)
        year, month = dt.dt.year, dt.dt.month
        totals = measure.groupby([year, month]).sum()
        prior_index = pd.MultiIndex.from_arrays([year - 1, month])
        result = totals.reindex(prior_index)
        result.index = measure.index
        return result

    def QTD(measure, date_col):  # noqa: N802
        """Cumulative sum within each calendar quarter, resetting at each quarter
        boundary. Positional order, like YTD."""
        dt = _as_datetime(date_col)
        return measure.groupby([dt.dt.year, dt.dt.quarter]).cumsum()

    def WTD(measure, date_col):  # noqa: N802
        """Cumulative sum within each ISO week."""
        iso = _as_datetime(date_col).dt.isocalendar()
        return measure.groupby([iso.year, iso.week]).cumsum()

    def _same_period_prior(measure, date_col, keys_fn, shift_fn):
        dt = _as_datetime(date_col)
        keys = keys_fn(dt)
        totals = measure.groupby(keys).sum()
        prior_index = pd.MultiIndex.from_arrays(shift_fn(dt))
        result = totals.reindex(prior_index)
        result.index = measure.index
        return result

    def SAMEPERIODLASTQUARTER(measure, date_col):  # noqa: N802
        """SUM of measure in the same month one quarter (3 months) earlier."""
        dt = _as_datetime(date_col)
        month_serial = dt.dt.year * 12 + (dt.dt.month - 1)
        totals = measure.groupby(month_serial).sum()
        result = totals.reindex(month_serial - 3)
        result.index = measure.index
        return result

    def SAMEPERIODLASTWEEK(measure, date_col):  # noqa: N802
        """SUM of measure on the same weekday one ISO week earlier."""
        day = _as_datetime(date_col).dt.normalize()
        totals = measure.groupby(day).sum()
        result = totals.reindex(day - pd.Timedelta(days=7))
        result.index = measure.index
        return result

    def QOQ_GROWTH(measure, date_col):  # noqa: N802
        """Percent change of this month's total vs the same month one quarter
        earlier -- NaN (never inf) when the prior period is missing or zero."""
        dt = _as_datetime(date_col)
        month_serial = dt.dt.year * 12 + (dt.dt.month - 1)
        current = measure.groupby(month_serial).transform('sum')
        prior = SAMEPERIODLASTQUARTER(measure, date_col)
        result = (current - prior) / prior * 100
        return result.mask(prior == 0)

    def YOY_GROWTH(measure, date_col):  # noqa: N802
        dt = _as_datetime(date_col)
        year, month = dt.dt.year, dt.dt.month
        current = measure.groupby([year, month]).transform('sum')
        prior = SAMEPERIODLASTYEAR(measure, date_col)
        result = (current - prior) / prior * 100
        return result.mask(prior == 0)

    safe_globals = {
        '__builtins__': {},
        # scalar math
        'abs': abs, 'round': round, 'min': min, 'max': max,
        'int': int, 'float': float, 'str': str, 'len': len,
        'pow': pow,
        'log': _math.log, 'sqrt': _math.sqrt, 'exp': _math.exp,
        'floor': _math.floor, 'ceil': _math.ceil,
        # conditional
        'IF': IF, 'SWITCH': SWITCH, 'isnull': pd.isnull,
        'SENTIMENT': SENTIMENT, 'SENTIMENT_LABEL': SENTIMENT_LABEL,
        'UPPER': UPPER, 'LOWER': LOWER, 'TRIM': TRIM, 'LEN': LEN, 'REVERSE': REVERSE,
        'LEFT': LEFT, 'RIGHT': RIGHT, 'SUBSTRING': SUBSTRING, 'CONCAT': CONCAT,
        'REPLACE': REPLACE, 'FIND': FIND, 'CONTAINS': CONTAINS,
        'STARTSWITH': STARTSWITH, 'ENDSWITH': ENDSWITH, 'SPLIT': SPLIT,
        'LPAD': LPAD, 'RPAD': RPAD,
        # aggregation
        'SUM': SUM, 'AVG': AVG, 'MEDIAN': MEDIAN,
        'COUNT': COUNT, 'COUNTD': COUNTD,
        'STDEV': STDEV, 'VARIANCE': VARIANCE,
        'PCT_TOTAL': PCT_TOTAL, 'NORMALIZE': NORMALIZE, 'ZSCORE': ZSCORE,
        # running / window
        'CUMSUM': CUMSUM, 'CUMPCT': CUMPCT,
        'RANK': RANK, 'DIFF': DIFF, 'LAG': LAG, 'LEAD': LEAD,
        # group-by window
        'GROUPSUM': GROUPSUM, 'GROUPAVG': GROUPAVG,
        'GROUPCOUNT': GROUPCOUNT, 'GROUPRANK': GROUPRANK,
        'GROUPMIN': GROUPMIN, 'GROUPMAX': GROUPMAX, 'GROUPPCT': GROUPPCT,
        # date / time intelligence
        'YEAR': YEAR, 'QUARTER': QUARTER, 'MONTH': MONTH, 'DAY': DAY,
        'DATETRUNC': DATETRUNC, 'YTD': YTD, 'QTD': QTD, 'WTD': WTD,
        'SAMEPERIODLASTYEAR': SAMEPERIODLASTYEAR, 'YOY_GROWTH': YOY_GROWTH,
        'SAMEPERIODLASTQUARTER': SAMEPERIODLASTQUARTER,
        'SAMEPERIODLASTWEEK': SAMEPERIODLASTWEEK, 'QOQ_GROWTH': QOQ_GROWTH,
        'WEEKDAY': WEEKDAY, 'WEEK': WEEK, 'HOUR': HOUR, 'MINUTE': MINUTE,
        'SECOND': SECOND, 'DAYOFYEAR': DAYOFYEAR,
        'MONTHNAME': MONTHNAME, 'DAYNAME': DAYNAME,
        # date construction and coercion
        'DATEFROMYMD': DATEFROMYMD, 'DATEADD': DATEADD, 'DATEDIFF': DATEDIFF,
        'TODAY': TODAY, 'NOW': NOW, 'TODATE': TODATE, 'TONUMBER': TONUMBER,
        # advanced statistics
        'PERCENTILE': PERCENTILE, 'MODE': MODE, 'CORR': CORR, 'COVAR': COVAR,
        'SKEW': SKEW, 'KURTOSIS': KURTOSIS, 'IQR': IQR, 'SE': SE,
        'COEFVAR': COEFVAR, 'CSS': CSS, 'FIRST': FIRST, 'LAST': LAST, 'PVALT': PVALT,
    }
    local_ns = {c: df[c] for c in df.columns}
    return safe_globals, local_ns


def _eval_expr(expr: str, df: pd.DataFrame):
    """Try df.eval() first, then fall back to Python eval with safe builtins.
    Backtick-quoted column names (e.g. `col name`) are handled in both paths."""
    _validate_expr_safety(expr)
    # --- df.eval path (handles backtick-quoted names natively) ---
    # local_dict/global_dict/resolvers are pinned empty as defense-in-depth: this
    # disables pandas' `@name`-prefixed external-variable resolution at the source
    # (the mechanism behind the `@df.to_csv(...)` bypass), without affecting normal
    # bare-column-name resolution, which pandas resolves via its own DataFrame-level
    # resolver, independent of these kwargs.
    try:
        return df.eval(expr, local_dict={}, global_dict={}, resolvers=())
    except Exception:
        pass
    # --- Python eval fallback: replace `col name` with safe identifiers ---
    safe_globals, local_ns = _build_safe_ns(df)
    processed = expr
    extra: dict = {}
    def _replace(m: _re.Match) -> str:
        col = m.group(1)
        key = f'__c{abs(hash(col)) % 100000}'
        if col in df.columns:
            extra[key] = df[col]
        return key
    processed = _re.sub(r'`([^`]+)`', _replace, processed)
    local_ns.update(extra)
    return eval(processed, safe_globals, local_ns)  # noqa: S307


def apply_filter_expr(df: pd.DataFrame, expr: str, silent: bool = False) -> pd.DataFrame:
    """Filter rows using a boolean expression. AND/OR/NOT are case-insensitive.

    silent=True swallows errors and returns the unfiltered df (use in production widgets).
    silent=False (default) raises so callers can report the error to users.
    """
    if not expr or not expr.strip():
        return df
    try:
        normalized = _re.sub(r'\bAND\b', 'and', expr, flags=_re.IGNORECASE)
        normalized = _re.sub(r'\bOR\b',  'or',  normalized, flags=_re.IGNORECASE)
        normalized = _re.sub(r'\bNOT\b', 'not', normalized, flags=_re.IGNORECASE)
        mask = _eval_expr(normalized, df)
        if hasattr(mask, 'dtype'):
            return df[mask.fillna(False).astype(bool)]
        return df if bool(mask) else df.iloc[0:0]
    except Exception:
        if silent:
            return df
        raise


def apply_rls_filter(df: pd.DataFrame, expr: str | None) -> pd.DataFrame:
    """Apply a RowSecurityRule filter expression. Unlike apply_filter_expr(silent=True)
    used for report-level filters, this fails CLOSED: a malformed/broken RLS expression
    returns zero rows rather than the unfiltered dataframe, because a broken security
    control should hide rows, not reveal them.

    Contrast app.services.display_rules, which fails OPEN for exactly the opposite
    reason: display rules are cosmetic, so a broken one must not blank a widget. Two
    expression paths, two deliberate failure modes — do not unify them."""
    if not expr or not expr.strip():
        return df
    try:
        return apply_filter_expr(df, expr, silent=False)
    except Exception:
        return df.iloc[0:0]


def apply_calculated_columns(df: pd.DataFrame, calc_cols: list[dict],
                              custom_functions: list[dict] | None = None) -> pd.DataFrame:
    """Evaluate expression-based calculated columns and append them to the
    dataframe. custom_functions, when given, are macro-expanded into each
    expression before evaluation (services/custom_functions.py).

    This is the ONLY call site where custom-function expansion happens.
    apply_filter_expr/apply_rls_filter never receive custom_functions -- that
    is what keeps a custom function from ever being usable inside a security
    rule (see the design doc's "Editing or deleting a function" and RLS
    sections)."""
    from .custom_functions import expand_custom_functions
    for col in calc_cols:
        name = (col.get('name') or '').strip()
        expr = (col.get('expression') or '').strip()
        if not name or not expr:
            continue
        try:
            if custom_functions:
                expr = expand_custom_functions(expr, custom_functions)
            result = _eval_expr(expr, df)
            df = df.copy()
            df[name] = result
        except Exception:
            pass
    return df


def preview_expression(file_path: str, expression: str, n: int = 8, rls_filter_expr: str | None = None,
                       prep_steps: list[dict] | None = None, prep_aux_frames: dict | None = None,
                       denied_columns: list[str] | None = None,
                       custom_functions: list[dict] | None = None) -> dict:
    """Evaluate an expression against the dataset and return sample values.

    `denied_columns` is the caller's column-security verdict; the columns leave
    the frame before evaluation, so an expression over one reports it unknown
    rather than computing the value the rule hides.

    `custom_functions`, when given, is macro-expanded into the expression
    before evaluation -- same expansion apply_calculated_columns performs --
    so the calc-column editor's preview matches what saving the column and
    rendering it elsewhere would actually produce.
    """
    try:
        df = load_file(file_path)
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    df = apply_rls_filter(df, rls_filter_expr)
    if prep_steps:
        from .prep import apply_prep_steps
        df = apply_prep_steps(df, prep_steps, prep_aux_frames)
    if denied_columns:
        present = [c for c in denied_columns if c in df.columns]
        if present:
            df = df.drop(columns=present)
    try:
        from .custom_functions import expand_custom_functions
        if custom_functions:
            expression = expand_custom_functions(expression, custom_functions)
        result = _eval_expr(expression, df)
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    try:
        if hasattr(result, 'head'):          # pandas Series
            sample = result.head(n).tolist()
        elif hasattr(result, '__len__'):     # numpy array or list
            sample = list(result[:n])
        else:
            sample = [result]
        try:
            dtype = 'numeric' if pd.api.types.is_numeric_dtype(result) else 'text'
        except Exception:
            dtype = 'text'
        return {'ok': True, 'dtype': dtype, 'sample': [_safe(v) for v in sample]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── result cache ──────────────────────────────────────────────────────────────
# The cache subsystem lives in widget_shaping.py, shared with direct_query.py.
# It moved as one unit -- store, backends, and accessors -- because
# widget_cache_get/set branch on `backend is _inprocess_backend`, an identity
# check that breaks silently if the functions and the singletons end up in
# different modules.
#
# The names below are re-exported, not re-implemented: `_WIDGET_DATA_CACHE` is
# the SAME OrderedDict object the in-process backend wraps, so tests that
# introspect `wd._WIDGET_DATA_CACHE` keep observing real cache state.
from .widget_shaping import (  # noqa: E402
    WIDGET_DATA_CACHE as _WIDGET_DATA_CACHE,
    WIDGET_DATA_CACHE_LOCK as _WIDGET_DATA_CACHE_LOCK,
    clear_widget_data_cache,
    get_cache_backend as _get_cache_backend,
    reset_cache_backend,
    widget_cache_get as _widget_data_cache_get,
    widget_cache_key as _widget_data_cache_key,
    widget_cache_set as _widget_data_cache_set,
)
from .widget_shaping import _inprocess_backend  # noqa: E402  (identity checks in tests)


def get_widget_data(
    file_path: str, config: dict, widget_type: str = "bar",
    calculated_columns: list[dict] | None = None, filter_expr: str | None = None,
    rls_filter_expr: str | None = None, use_cache: bool = True,
    measures: list[dict] | None = None, drop_columns: list[str] | None = None,
    prep_steps: list[dict] | None = None,
    prep_aux_frames: dict | None = None,
    org_id: int | None = None, dataset_id: int | None = None,
    custom_functions: list[dict] | None = None,
) -> dict:
    # T5: single choke point for the import/pandas widget path -- every render
    # (cache hit or miss) funnels through here, called via asyncio.to_thread from
    # the widget_data router, so log_query_run_sync's own event loop is safe to spin
    # up (this worker thread has none of its own).
    start = time.monotonic()
    # A pipeline with a join reads OTHER files whose mtimes the cache key cannot
    # see; a stale joined result is a correctness bug, so joined reads skip the
    # result cache entirely rather than serving one.
    if any(isinstance(x, dict) and x.get("kind") == "join" for x in (prep_steps or [])):
        use_cache = False
    file_stat = None
    from .relative_dates import has_relative
    if has_relative(config.get("filters")) and "__today__" not in config:
        from datetime import date
        config = {**config, "__today__": date.today().isoformat()}
    if use_cache:
        try:
            st = os.stat(file_path)
            file_stat = (st.st_mtime, st.st_size)
        except OSError:
            file_stat = None  # file missing/unreadable -- fall through, load_file() raises below
        key = _widget_data_cache_key(
            file_path, file_stat,
            {**config, "__denied__": sorted(drop_columns or []),
             "__prep__": prep_steps or [],
             "__custom_fns__": custom_functions or []},
            widget_type, calculated_columns, filter_expr, rls_filter_expr,
            measures,
        )
        cached = _widget_data_cache_get(key)
        if cached is not None:
            log_query_run_sync(
                org_id=org_id, source_kind="import", data_source_id=None,
                dataset_id=dataset_id, sql_hash=None, rows_returned=None,
                duration_ms=int((time.monotonic() - start) * 1000),
                executor="pandas", cache_hit=True,
            )
            _record_widget_metrics("pandas", True,
                                    int((time.monotonic() - start) * 1000))
            return copy.deepcopy(cached)

    # DuckDB pre-aggregation (services/duck_agg.py), off unless
    # settings.widget_duckdb_pushdown. Attempted BEFORE load_file so an eligible
    # query never materialises the full frame -- which is the entire point:
    # measured 1808 MB -> 270 MB on a 406 MB source.
    #
    # Every stage below this line is a pandas transformation of the full frame
    # (column denial, RLS, prep, filter expressions, calculated columns), and
    # none has a SQL equivalent here yet. Their presence means the frame must be
    # built, so pushdown is only attempted when all of them are absent. This is
    # a deliberately conservative gate: the memory-dominant case the benchmark
    # measured is a plain dimension+measure render, which has none of them.
    # Local import: duck_agg imports direct_query for the grain-safety rules,
    # and direct_query imports this module. A module-scope import here would
    # close that cycle.
    from . import duck_agg as _duck_agg

    # RLS, the report filter expression and column security used to make a
    # widget ineligible outright -- which meant every GOVERNED widget, the
    # ones an enterprise actually runs, fell to pandas and met the row cap.
    # They are now translated into the DuckDB plan by the same translator
    # DirectQuery has always used, or the widget declines and takes the
    # pandas path exactly as before. Nothing here can produce a third
    # outcome.
    duck_extra, duck_visible, duck_ok = [], None, False
    if (_duck_agg.is_enabled() and not prep_steps and not calculated_columns
            and not measures
            # a lattice needs the row-level frame to split into panels
            and not (config.get("lattice_rows") or config.get("lattice_columns")
                     or config.get("animate_by"))):
        try:
            cols = list(load_file_columns(file_path))
        except Exception:  # noqa: BLE001 -- unreadable header: pandas path reports it properly
            cols = []
        if cols:
            from .sql_expr import (ExpressionTranslationError,
                                   translate_filter_expr_null_safe)
            # What the READER may see. The plan validates dimension, measure
            # and filter columns against this, so a denied column in any of
            # them is 'not a real column' and the plan declines -- the same
            # refusal the pandas path reaches after dropping the column.
            duck_visible = [c for c in cols if c not in set(drop_columns or [])]
            try:
                if rls_filter_expr:
                    # Against EVERY file column, not the visible ones: the row
                    # rule is the admin's predicate and only removes rows, and
                    # the reader never receives the column it reads (the plan
                    # below is validated against `duck_visible`). This mirrors
                    # the pandas path, which applies RLS before it drops the
                    # denied columns, and DirectQuery, whose predicate has
                    # always been translated against the whole table. A rule
                    # on a column the reader cannot see therefore selects
                    # rows instead of silently returning none.
                    duck_extra.append(translate_filter_expr_null_safe(
                        rls_filter_expr, set(cols)))
                if filter_expr:
                    duck_extra.append(translate_filter_expr_null_safe(
                        filter_expr, set(duck_visible)))
                duck_ok = True
            except ExpressionTranslationError as e:
                # Untranslatable or negated: pandas, where a broken RLS rule
                # fails closed (zero rows) and a broken report filter fails
                # open (unfiltered) -- both unchanged from before.
                _duck_agg.logger.info("DuckDB pushdown declined: %s", e)
        if cols and duck_ok:
            duck_df, _reason = _duck_agg.try_aggregate(
                file_path, config, duck_visible, extra_where=duck_extra)
            if duck_df is not None:
                # The frame is already one row per group, so the shaper's own
                # groupby is a no-op pass-through -- the same grain invariant
                # run_direct_query relies on, which is why only grain-safe
                # aggregations are eligible.
                # check_fields off: the frame is pre-aggregated, and duck_agg.plan
                # already refused any dimension/measure that is not a real column.
                result = get_widget_data_from_df(duck_df, config, widget_type, flag_partial=False,
                                                 check_fields=False)
                # The shaper derives `total` from len(df), which on a
                # pre-aggregated frame is the GROUP count. `total` means source
                # rows, so restore the real figure DuckDB counted.
                source_rows = duck_df.attrs.get("source_row_count")
                if source_rows is not None and "total" in result:
                    result["total"] = source_rows
                    result["rows_scanned"] = source_rows  # the population, not the pre-aggregated groups
                # Same reason: the null-keyed rows never reached the shaper, so
                # its own count of them is 0. DuckDB counted them.
                missing = duck_df.attrs.get("missing_dimension_rows")
                if missing is not None and "missing_category" in result:
                    result["missing_category"] = {"rows": int(missing)}
                if use_cache:
                    try:
                        entry_size = len(json.dumps(result, default=str))
                    except (TypeError, ValueError):
                        entry_size = 0
                    if entry_size <= settings.widget_data_cache_max_entry_bytes:
                        _widget_data_cache_set(key, copy.deepcopy(result))
                log_query_run_sync(
                    org_id=org_id, source_kind="import", data_source_id=None,
                    dataset_id=dataset_id, sql_hash=None,
                    rows_returned=len(result.get("rows") or []),
                    duration_ms=int((time.monotonic() - start) * 1000),
                    executor="duckdb", cache_hit=False,
                )
                _record_widget_metrics("duckdb", False,
                                        int((time.monotonic() - start) * 1000))
                return result

    # Row security FIRST, over every column, then column security. The rule
    # is the admin's predicate: it decides which rows this reader gets, and
    # the reader never sees the column it reads, so evaluating it on a denied
    # column leaks nothing. The reverse order turned "hide tenant_id, and
    # filter rows by tenant_id" -- the ordinary tenant setup -- into an empty
    # dashboard with no error, while DirectQuery, the expression-parameter
    # path and every analysis surface answered correctly. A rule on a column
    # that does not exist at all still fails closed inside apply_rls_filter.
    df = load_file(file_path)
    _enforce_import_row_cap(df, file_path)
    df = apply_rls_filter(df, rls_filter_expr)
    if drop_columns:
        # Column-level security: the denied columns cease to exist before anything
        # else -- filters, calculated columns, shaping -- can read them. Same
        # cache-key treatment as RLS, so two roles with different masks never
        # share an entry.
        present = [c for c in drop_columns if c in df.columns]
        if present:
            df = df.drop(columns=present)
    if prep_steps:
        # After RLS on purpose: an aggregate step must summarise only the rows
        # this user may see, and fill-from-mean must impute from the visible
        # slice. Before the dataset filter and calc columns, which read the
        # prepped (renamed/split/cleansed) shape.
        from .prep import apply_prep_steps
        df = apply_prep_steps(df, prep_steps, prep_aux_frames)
    if filter_expr:
        df = apply_filter_expr(df, filter_expr, silent=True)
    if calculated_columns:
        df = apply_calculated_columns(df, calculated_columns, custom_functions)
    result = get_widget_data_from_df(df, config, widget_type, measures=measures)

    if use_cache:
        try:
            entry_size = len(json.dumps(result, default=str))
        except (TypeError, ValueError):
            entry_size = 0  # unserializable result — don't let a size-check failure block the cache write path elsewhere; just skip caching this one
        if entry_size <= settings.widget_data_cache_max_entry_bytes:
            _widget_data_cache_set(key, copy.deepcopy(result))
    log_query_run_sync(
        org_id=org_id, source_kind="import", data_source_id=None,
        dataset_id=dataset_id, sql_hash=None, rows_returned=len(df),
        duration_ms=int((time.monotonic() - start) * 1000),
        executor="pandas", cache_hit=False,
    )
    _record_widget_metrics("pandas", False,
                            int((time.monotonic() - start) * 1000))
    return result


# ── Hierarchy ────────────────────────────────────────────────────────────────
# ONE shaper behind five widget types (tree, sunburst, icicle, dendrogram, org),
# for the reason small multiples has one: a layout that computed its own numbers
# would be a second aggregation path, and the two would drift. The renderers
# differ only in how they draw the same nested contract.

#: Children per node, matching decomposition. Beyond this a ring or a row of
#: boxes is unreadable and the labels stop fitting.
HIER_MAX_CHILDREN = 12

#: Depth. Each level multiplies the node count, and a hierarchy deeper than this
#: is navigation nobody follows.
HIER_MAX_DEPTH = 8

#: A total-node ceiling, which the per-level caps alone do not give: 12 children
#: at 8 levels is 12^8 nodes. Parent-child data especially explodes -- an org
#: chart of a large company is tens of thousands of nodes, and serialising them
#: all is a request nobody can render.
HIER_MAX_NODES = 2_000

#: A field with more distinct values than this is a list, not a level. The
#: decomposition tree first auto-split on `date` (633 values) because maximal
#: variation and zero explanation look identical to a variance score.
HIER_MAX_LEVEL_VALUES = 50

#: Partition charts (sunburst, icicle) encode value as ANGLE or AREA, so a
#: parent's wedge is the sum of its children's. An average or a maximum does not
#: add up that way, and drawing it as area states a falsehood the reader cannot
#: see. These are the aggregations that survive the geometry.
ADDITIVE_AGGREGATIONS = {"sum", "count", "frequency"}

#: Widget types whose geometry encodes magnitude and therefore require one.
PARTITION_WIDGETS = {"sunburst", "icicle", "circle_pack"}


class HierarchyError(ValueError):
    """A refusal a user should read: a cycle, a missing column, a
    non-additive aggregation on a partition chart."""


def _node(name, value=None, depth=0):
    return {"name": name, "value": value, "children": [], "depth": depth,
            "omitted": 0, "omitted_value": None}


def _levels_hierarchy(df: pd.DataFrame, levels: list[str], measure: str | None,
                      aggregation: str, max_depth: int) -> dict:
    """Nest by successive level columns: country -> region -> city.

    Children are capped and the remainder folded into an "Other" node carrying
    its real total, never dropped -- a breakdown whose parts do not sum to the
    whole is worse than no breakdown, which is the rule the decomposition tree
    already lives by.
    """
    total = _agg_value(df, measure, aggregation)
    root = _node("All", total, 0)
    budget = [HIER_MAX_NODES]

    def build(frame: pd.DataFrame, parent: dict, remaining: list[str]) -> None:
        if not remaining or parent["depth"] >= max_depth or budget[0] <= 0:
            return
        field, rest = remaining[0], remaining[1:]
        if field not in frame.columns:
            return
        groups = []
        for value, sub in frame.groupby(field, dropna=False, sort=False):
            groups.append((("(blank)" if pd.isna(value) else str(value)),
                           _agg_value(sub, measure, aggregation), sub))
        groups.sort(key=lambda g: (g[1] is None, -(g[1] or 0)))

        kept = groups[:HIER_MAX_CHILDREN]
        tail = groups[HIER_MAX_CHILDREN:]
        for name, value, sub in kept:
            if budget[0] <= 0:
                break
            budget[0] -= 1
            child = _node(name, value, parent["depth"] + 1)
            parent["children"].append(child)
            build(sub, child, rest)
        if tail:
            # The residual carries its real total so the level still reconciles.
            residual = _agg_value(pd.concat([g[2] for g in tail]), measure, aggregation)
            parent["omitted"] = len(tail)
            parent["omitted_value"] = residual
            parent["children"].append(
                {**_node(f"Other ({len(tail)})", residual, parent["depth"] + 1),
                 "is_other": True})

    build(df, root, levels[:max_depth])
    return root


def _parent_child_hierarchy(df: pd.DataFrame, id_col: str, parent_col: str,
                            label_col: str | None, measure: str | None,
                            aggregation: str, max_depth: int) -> tuple[dict, dict]:
    """Nest by explicit id/parent links: an org chart, a bill of materials.

    ORPHANS BECOME ROOTS rather than an error. A row whose parent is not in the
    frame is not corrupt data -- most often the parent was removed by row-level
    security, and the honest rendering is a forest whose visible subtrees root
    where the caller's permission begins. Erroring instead would tell a
    restricted user their data is broken.

    CYCLES ARE REFUSED BY NAME. A manager chain that loops has no root and no
    depth; following it hangs the renderer, and silently breaking it invents a
    hierarchy that does not exist.
    """
    for col in (id_col, parent_col):
        if col not in df.columns:
            raise HierarchyError(f"Column not found: {col}")

    work = df[[c for c in {id_col, parent_col, label_col} if c]].copy()
    if measure and measure in df.columns:
        work[measure] = df[measure]
    work = work.dropna(subset=[id_col])

    ids = [str(v) for v in work[id_col]]
    parents = [None if pd.isna(v) else str(v) for v in work[parent_col]]
    labels = ([str(v) for v in work[label_col]] if label_col and label_col in work
              else ids)
    values = (list(pd.to_numeric(work[measure], errors="coerce"))
              if measure and measure in work else [None] * len(ids))

    present = set(ids)
    children_of: dict[str | None, list[int]] = {}
    for i, (pid, cid) in enumerate(zip(parents, ids)):
        # A parent outside the frame (or absent) makes this row a root.
        key = pid if (pid in present and pid != cid) else None
        children_of.setdefault(key, []).append(i)

    # Cycle detection over the id->parent mapping, before any traversal.
    parent_of = {cid: (pid if pid in present and pid != cid else None)
                 for cid, pid in zip(ids, parents)}
    for start in parent_of:
        seen, cur = set(), start
        while cur is not None:
            if cur in seen:
                raise HierarchyError(
                    f"The parent chain loops at '{cur}' -- a hierarchy cannot "
                    f"contain a cycle. Fix the parent of that row and retry.")
            seen.add(cur)
            cur = parent_of.get(cur)

    stats = {"nodes": 0, "truncated": False}

    def build(index: int, depth: int) -> dict:
        stats["nodes"] += 1
        node = _node(labels[index], _clean_number(values[index]), depth)
        if depth >= max_depth or stats["nodes"] >= HIER_MAX_NODES:
            kids = children_of.get(ids[index], [])
            if kids:
                node["omitted"] = len(kids)
                stats["truncated"] = True
            return node
        kids = children_of.get(ids[index], [])
        for k in kids[:HIER_MAX_CHILDREN]:
            if stats["nodes"] >= HIER_MAX_NODES:
                stats["truncated"] = True
                break
            node["children"].append(build(k, depth + 1))
        if len(kids) > HIER_MAX_CHILDREN:
            node["omitted"] = len(kids) - HIER_MAX_CHILDREN
        return node

    roots = [build(i, 1) for i in children_of.get(None, [])[:HIER_MAX_CHILDREN]]
    root = _node("All", None, 0)
    root["children"] = roots
    n_roots = len(children_of.get(None, []))
    if n_roots > HIER_MAX_CHILDREN:
        root["omitted"] = n_roots - HIER_MAX_CHILDREN
    return root, stats


def _agg_value(frame: pd.DataFrame, measure: str | None, aggregation: str):
    """One aggregate for a node. No measure means count the rows, which is what
    a hierarchy of categories means without one."""
    if not measure or measure not in frame.columns:
        return int(len(frame))
    series = pd.to_numeric(frame[measure], errors="coerce").dropna()
    if series.empty:
        return None
    agg = (aggregation or "sum").lower()
    fn = {"sum": series.sum, "count": lambda: len(series),
          "frequency": lambda: len(series), "avg": series.mean,
          "mean": series.mean, "average": series.mean, "median": series.median,
          "min": series.min, "minimum": series.min, "max": series.max,
          "maximum": series.max}.get(agg, series.sum)
    return _clean_number(fn())


def _clean_number(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (_math.isnan(f) or _math.isinf(f)) else f


def shape_hierarchy(df: pd.DataFrame, config: dict) -> dict:
    """The single shaper behind tree, sunburst, icicle, dendrogram, org and
    circle pack.

    TWO INPUT MODES, because hierarchies arrive in two shapes:

      * LEVEL COLUMNS -- `levels: [country, region, city]`. Each level nests
        inside the one before, aggregating a measure at every node.
      * PARENT-CHILD -- `id_col` and `parent_col`. An org chart or a bill of
        materials, where the depth is data rather than schema.

    Both produce the same nested `{name, value, children, omitted}` contract, so
    the six renderers are layouts over one set of numbers rather than six
    aggregation paths that drift apart.

    PARTITION CHARTS REFUSE NON-ADDITIVE AGGREGATIONS. A sunburst draws value as
    an angle, an icicle as a width and a circle pack as the area its parent's
    circle must contain: the parent's share IS the sum of its children's. Feed
    it an
    average and the geometry states something false -- children that visibly do
    not fill their parent, with no indication that the picture is wrong rather
    than the data. A tree or org chart prints the number instead of encoding it,
    so any aggregation is fine there.
    """
    widget = str(config.get("widget_type") or config.get("_widget") or "tree")
    measure = config.get("measure")
    aggregation = str(config.get("aggregation") or "sum").lower()
    max_depth = min(int(config.get("max_depth") or HIER_MAX_DEPTH), HIER_MAX_DEPTH)

    if widget in PARTITION_WIDGETS and measure and aggregation not in ADDITIVE_AGGREGATIONS:
        raise HierarchyError(
            f"A {widget} draws each value as a share of its parent, so it needs "
            f"an additive aggregation ({', '.join(sorted(ADDITIVE_AGGREGATIONS))}). "
            f"'{aggregation}' does not add up across levels -- use a tree or "
            f"dendrogram to show it instead.")

    id_col, parent_col = config.get("id_col"), config.get("parent_col")
    if id_col and parent_col:
        root, stats = _parent_child_hierarchy(
            df, id_col, parent_col, config.get("label_col"), measure,
            aggregation, max_depth)
        mode, truncated = "parent_child", stats["truncated"]
        levels_used: list[str] = []
    else:
        levels = [c for c in (config.get("levels") or []) if c in df.columns]
        if not levels:
            raise HierarchyError(
                "Choose the columns that form the hierarchy, or an id and "
                "parent column for a parent-child structure.")
        for lvl in levels:
            n = df[lvl].nunique(dropna=False)
            if n > HIER_MAX_LEVEL_VALUES:
                raise HierarchyError(
                    f"'{lvl}' has {n:,} distinct values, which is a list rather "
                    f"than a level of a hierarchy (limit "
                    f"{HIER_MAX_LEVEL_VALUES}).")
        root = _levels_hierarchy(df, levels, measure, aggregation, max_depth)
        mode, truncated, levels_used = "levels", False, levels

    return {
        "type": widget, "mode": mode, "root": root,
        "levels": levels_used, "measure": measure, "aggregation": aggregation,
        "max_depth": max_depth, "truncated": truncated,
        "additive": aggregation in ADDITIVE_AGGREGATIONS,
    }


for _hier_widget in ('tree', 'sunburst', 'icicle', 'dendrogram', 'org', 'circle_pack'):
    # One shaper, six layouts. Registering each type separately keeps the
    # widget catalogue honest -- a user picks a sunburst, not a "hierarchy" --
    # while the numbers behind all six come from the same code path.
    SHAPERS[_hier_widget] = shape_hierarchy


# Models as widgets (MASTER_PLAN Phase 3). Registered last and from their own
# module: the model shapers import the analysis registry lazily, and nothing
# in model_widgets imports this module, so there is no cycle.
from .model_widgets import MODEL_SHAPERS as _MODEL_SHAPERS  # noqa: E402
SHAPERS.update(_MODEL_SHAPERS)


#: Shapers that SUM a measure whose config names no aggregation. A histogram or a
#: numeric x/y series plots raw values, so a year on its axis is not a sum of years.
_SUMS_BY_DEFAULT = {shape_series, shape_dual_series, shape_card, shape_gauge,
                    shape_waterfall, shape_heatmap, shape_decomposition,
                    shape_bubble, shape_bubble_animated}


#: Shapers that never drop a group: they aggregate everything into one value,
#: or bin / pivot every row. Their results are stamped "nothing dropped".
_KEEPS_EVERY_GROUP = {shape_gauge, shape_card, shape_histogram, shape_heatmap}


def sums_measure_by_default(widget_type: str) -> bool:
    """Whether this widget type adds up a measure that names no aggregation."""
    return SHAPERS.get(widget_type, shape_series) in _SUMS_BY_DEFAULT

