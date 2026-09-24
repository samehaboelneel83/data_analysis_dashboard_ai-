"""
DirectQuery Service
====================
Pushes aggregate-strategy widget queries (the `shape_series` config shape --
dimension/measure/aggregation) down into SQL against a live data source,
instead of materializing the whole table into pandas first.
See docs/superpowers/specs/2026-08-15-directquery-design.md for the design.

Row-level security is pushed down with the query, so this path is open to
every user, not just admins. `run_direct_query` takes `rls_filter_expr`;
`_base_query_sql` wraps that predicate around the base query BEFORE widget
filters are applied, and callers (routers/widget_data.py, analysis.py,
datasets.py) pass the result of `core.rls.resolve_rls_expr`. An expression
that cannot be translated to SQL fails the request rather than widening it,
and the filter expression is part of the cache key so two roles never share
a cached frame.

Describe behaviour here, not project phase: an earlier version of this
docstring still claimed RLS pushdown was unimplemented and the path
admin-only long after both had changed, and that prose was believed over the
code. No test asserts on a docstring -- keep it true by hand.

The grain invariant
--------------------
`run_direct_query` hands its (already-aggregated) result to the SAME
`get_widget_data_from_df` / shaper that import-mode datasets use, so the
shaper re-runs its own groupby/agg against a frame that already has one row
per group. That second pass is only a no-op pass-through when the aggregation
is "grain-safe": applying the aggregation again to an already-aggregated
single value must reproduce that same value.

sum/avg/min/max/median/percentiles all have this property (the aggregate of
a one-element set is that element, for any of these). count, countd/distinct,
std/variance and range do NOT: re-counting one row gives 1, not the real
count; std/variance of a single value is undefined; range of one value is 0.
GRAIN_SAFE_AGGREGATIONS is exactly the safe subset -- anything else is
rejected by `plan_query` rather than silently computed wrong.
"""
import copy
import decimal
import hashlib
import json
import dataclasses
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import pandas as pd
import sqlglot
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..core import telemetry
from ..core.config import settings
from .connections import _build_url
from . import connectors
from .query_log import log_query_run_sync
from .sql_expr import ExpressionTranslationError, translate_filter_expr
from .widget_data import get_widget_data_from_df
from .widget_shaping import (safe as _safe, widget_cache_get as _widget_data_cache_get,
                             widget_cache_set as _widget_data_cache_set)

GRAIN_SAFE_AGGREGATIONS = {
    "sum", "avg", "mean", "average", "min", "minimum", "max", "maximum",
    "median", "p25", "p75", "p90", "p95",
}

# Explicit allowlist of widget_types DirectQuery Phase 1 knows how to push
# down -- deliberately not derived from widget_data.SHAPERS, so DirectQuery's
# supported surface can't silently grow just because a new widget_type gets
# registered against shape_series. "table"/"list"/"kpi"/"card" widgets need
# row-level data (or no grouping at all), not a GROUP BY -- they're handled
# by ROW_CAPPED_WIDGET_TYPES below instead of this aggregate-pushdown set.
AGGREGATE_STRATEGY_WIDGET_TYPES = {
    "bar", "line", "pie", "donut", "treemap", "scatter", "step",
    "dot_plot", "crosstab", "needle", "word_cloud",
}

_SUPPORTED_FILTER_OPS = {"eq", "neq", "gt", "lt", "gte", "lte", "in"}

# Dialects supported for pushdown. sqlserver was originally excluded because its
# TOP-n syntax sits after SELECT rather than at the end of the query, which does
# not fit the `... GROUP BY ... ORDER BY ... <limit clause>` shape build_sql
# produces. SQL Server 2012+ accepts `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`
# as a trailing clause instead, which does fit -- and build_sql always emits the
# ORDER BY that syntax requires. Percentile aggregations remain unsupported on
# sqlserver (see _DIALECTS_WITH_PERCENTILE_CONT) because T-SQL's PERCENTILE_CONT
# is a window function, not an aggregate, so it cannot sit in a GROUP BY select
# list. Identifiers stay double-quoted: that is ANSI SQL and valid in T-SQL
# whenever QUOTED_IDENTIFIER is ON, which is the default for the drivers here.
SUPPORTED_FAMILIES = {"postgresql", "mysql", "sqlite", "oracle", "sqlserver",
                      "clickhouse"}
# Back-compat alias: a source's resolved sql_family must be in this set for DirectQuery.
SUPPORTED_DIALECTS = SUPPORTED_FAMILIES


class SourceUnavailable(Exception):
    """The customer's database could not be reached.

    Distinct from `DirectQueryUnsupported`, which means "this widget config
    cannot be pushed down" -- the caller's problem, answered with a 400.
    This one is nobody's fault at this end: the source is down, the network is
    cut, the credentials were rotated. A 500 would send the reader to OUR logs
    for an outage in THEIR database.

    CARRIES NO DRIVER TEXT. A connection error embeds the DSN and a DSN embeds
    the password; `/health/ready` refuses to quote exception text for exactly
    that reason, and a widget is seen by far more people than a probe.
    """


class DirectQueryUnsupported(Exception):
    """Raised when a widget config can't be safely pushed down yet. Callers
    must surface this as an explicit error to the user -- never fall back to
    fetching rows and aggregating them locally without saying so, per the
    design spec's "never silently wrong" rule."""


@dataclass
class QueryPlan:
    dim: str
    meas: str
    agg: str
    filters: list[dict] = field(default_factory=list)
    limit: int = 50
    sort_desc: bool = True
    sort_by_dim: bool = False


def plan_query(config: dict, widget_type: str) -> QueryPlan:
    if widget_type not in AGGREGATE_STRATEGY_WIDGET_TYPES:
        raise DirectQueryUnsupported(
            f"widget_type '{widget_type}' is not yet supported for DirectQuery datasets"
        )

    dim = config.get("dimension") or None
    dim2 = config.get("dimension2") or None
    meas = config.get("measure") or None
    agg = (config.get("aggregation") or "sum").lower()
    running = (config.get("running") or "").lower()
    sort_by = (config.get("sort_by") or "value").lower()
    sort_col = config.get("sort_col") or None

    if dim2:
        raise DirectQueryUnsupported("crosstab (dimension2) is not yet supported for DirectQuery datasets")
    if running:
        raise DirectQueryUnsupported("running totals are not yet supported for DirectQuery datasets")
    if not dim:
        raise DirectQueryUnsupported("DirectQuery requires a dimension")
    if sort_col and sort_col != dim:
        raise DirectQueryUnsupported(
            "sort_col on a column other than the dimension is not yet supported for DirectQuery datasets"
        )
    if meas:
        if agg not in GRAIN_SAFE_AGGREGATIONS:
            raise DirectQueryUnsupported(f"aggregation '{agg}' is not yet supported for DirectQuery datasets")
    elif agg == "pct":
        # shape_series computes pct as each group's share of the total BEFORE
        # applying limit/sort, which needs every group's true count fetched
        # (no SQL-side LIMIT) -- not attempted yet, so this combination is
        # rejected rather than silently returning percentages of only the
        # top-N shown groups.
        raise DirectQueryUnsupported("'pct' aggregation without a measure is not yet supported for DirectQuery datasets")

    filters = config.get("filters") or []
    for f in filters:
        if f.get("op") not in _SUPPORTED_FILTER_OPS:
            raise DirectQueryUnsupported(
                f"filter operator '{f.get('op')}' is not yet supported for DirectQuery datasets"
            )

    return QueryPlan(
        dim=dim, meas=meas, agg=agg, filters=filters,
        limit=int(config.get("limit") or 50),
        sort_desc=(config.get("sort") or "desc").lower() != "asc",
        sort_by_dim=(sort_by == "name") or bool(sort_col),
    )



def _time_axis_default(plan: QueryPlan, config: dict, dataset) -> QueryPlan:
    """The import path's rule, for SQL: a time dimension with no stated `sort_by`
    is ordered by time, ascending (see widget_data's "time axis defaults to time
    order"). `plan_query` sees only the config; the column's dtype lives on the
    dataset, so the rule is applied here, where both are in hand."""
    if "sort_by" in config or not plan.dim or plan.sort_by_dim:
        return plan
    col = next((c for c in getattr(dataset, "columns", None) or [] if c.name == plan.dim), None)
    if col is None or str(getattr(col, "dtype", "")).lower() not in ("datetime", "date"):
        return plan
    return dataclasses.replace(plan, sort_by_dim=True, sort_desc=False)


_SQL_COMPARISON_OPS = {"eq": "=", "neq": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}

_SQL_AGG_FN = {
    "sum": "SUM",
    "avg": "AVG", "mean": "AVG", "average": "AVG",
    "min": "MIN", "minimum": "MIN",
    "max": "MAX", "maximum": "MAX",
}

_PERCENTILE_FRACTIONS = {"p25": 0.25, "p75": 0.75, "p90": 0.90, "p95": 0.95, "median": 0.5}


def _quote(identifier: str) -> str:
    return f'"{identifier}"'


#: SQLAlchemy binds, as the builder writes them, and the sentinel they hide
#: behind while sqlglot rewrites the statement around them.
_BIND_RE = re.compile(r":([a-zA-Z_]\w*)")
_SENTINEL_RE = re.compile(r"'__dqbind_(\w+)__'")


def _finalize_for_dialect(sql: str, dialect: str) -> str:
    """Identity for the five wire-compatible families; ClickHouse for the sixth.

    Everything above emits one ANSI-ish shape whatever the family, which is what
    lets five dialects share one set of builder tests. ClickHouse parses that
    shape but spells several things its own way -- RANDOM() is randCanonical(),
    STDDEV() is stddevSamp(), VAR_SAMP() is varSamp() -- so instead of growing a
    sixth branch inside every helper, the finished statement is transpiled once,
    here.

    Returning `sql` untouched for the other five is the whole safety argument for
    adding a family at all: ClickHouse support must not rewrite a byte of the SQL
    an existing customer already runs. `tests/test_clickhouse_connector.py` pins
    that identity for each of the five.

    **Why the binds are hidden.** sqlglot does not know `:f0` is a SQLAlchemy
    placeholder. Its ClickHouse writer renders it as `{f0: }` -- a ClickHouse
    named placeholder with an EMPTY type -- which the server rejects, and which
    would have shipped as a runtime syntax error rather than a test failure.
    Swapping each bind for a string literal across the transpile keeps sqlglot
    parsing a valid statement, and swapping back restores exactly what
    `sqlalchemy.text()` expects. The sentinel carries the bind name so order
    cannot matter, and no value reaches this function -- only the parameterised
    statement -- so a hostile value cannot forge one.
    """
    if dialect != "clickhouse":
        return sql
    guarded = _BIND_RE.sub(lambda m: f"'__dqbind_{m.group(1)}__'", sql)
    transpiled = sqlglot.transpile(guarded, read="postgres", write="clickhouse")[0]
    return _SENTINEL_RE.sub(lambda m: f":{m.group(1)}", transpiled)


def _build_where(filters: list[dict]) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict = {}
    for i, f in enumerate(filters):
        col, op, val = f.get("column"), f.get("op"), f.get("value")
        if not col:
            continue
        col_sql = _quote(col)
        if op == "in":
            vals = val if isinstance(val, list) else [val]
            keys = [f"f{i}_{j}" for j in range(len(vals))]
            params.update(dict(zip(keys, vals)))
            clauses.append(f"{col_sql} IN ({', '.join(':' + k for k in keys)})")
        else:
            key = f"f{i}"
            params[key] = val
            clauses.append(f"{col_sql} {_SQL_COMPARISON_OPS[op]} :{key}")
    return " AND ".join(clauses), params


_DIALECTS_WITH_PERCENTILE_CONT = {"postgresql", "oracle"}


def _agg_sql(agg: str, meas_sql: str, dialect: str) -> str:
    if agg in _PERCENTILE_FRACTIONS:
        if dialect not in _DIALECTS_WITH_PERCENTILE_CONT:
            # Neither MySQL (pre-8.0 without rare extensions) nor SQLite have
            # PERCENTILE_CONT or a MEDIAN aggregate built in; Phase 1 doesn't
            # attempt a portable fallback for either.
            raise DirectQueryUnsupported(
                f"aggregation '{agg}' is not supported for {dialect} DirectQuery sources yet"
            )
        frac = _PERCENTILE_FRACTIONS[agg]
        return f"PERCENTILE_CONT({frac}) WITHIN GROUP (ORDER BY {meas_sql})"
    return f"{_SQL_AGG_FN[agg]}({meas_sql})"


def _limit_clause(dialect: str, limit: int) -> str:
    if dialect == "oracle":
        return f"FETCH FIRST {limit} ROWS ONLY"
    if dialect == "sqlserver":
        # T-SQL has no LIMIT. OFFSET/FETCH is the only row-limiting syntax that
        # trails the query rather than sitting after SELECT, and it requires the
        # ORDER BY that every build_sql query already emits.
        return f"OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"
    return f"LIMIT {limit}"


def _base_query_sql(dataset, rls_where: str = "") -> str:
    inner = dataset.source_query.strip().rstrip(";") if dataset.source_query else f"SELECT * FROM {_quote(dataset.source_table)}"
    if not rls_where:
        return inner
    # The RLS predicate gets its own subquery boundary, applied before anything
    # else touches the data -- see the design spec's "Row-Level Security
    # Pushdown" section. A widget-level filter's WHERE (added by the caller,
    # outside this subquery) can only narrow what's already here; it can never
    # resurrect a row this subquery already excluded, even via an OR.
    return f"SELECT * FROM ({inner}) AS rls_src WHERE {rls_where}"


def build_sql(
    dataset, plan: QueryPlan, dialect: str,
    rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """Pure SQL string builder -- no I/O, so dialect coverage is testable without a
    live connection. Identifiers are quoted but NOT allowlist-checked here; the
    caller (run_direct_query) validates dim/meas/filter columns against the
    dataset's known DatasetColumn names before this is called. rls_where/
    rls_params come pre-translated from sql_expr.translate_filter_expr --
    this function only wires them into the query shape, it doesn't translate."""
    base = _base_query_sql(dataset, rls_where)
    dim_sql, meas_sql = _quote(plan.dim), _quote(plan.meas)
    agg_sql = _agg_sql(plan.agg, meas_sql, dialect)

    # NULL dimension rows are excluded here for the same reason the total builders
    # exclude them, plus one specific to this query: it applies the LIMIT in SQL, so a
    # NULL group does not merely go unrendered -- it CONSUMES a top-N slot and then
    # vanishes when shape_series re-groups the frame with pandas. At limit=2 that
    # rendered one row where import mode rendered two; at limit=1 it rendered an empty
    # table beneath a non-zero total.
    where_clause, params = _dim_group_where(plan)
    order_col = "1" if plan.sort_by_dim else "2"
    order_dir = "ASC" if (plan.sort_by_dim or not plan.sort_desc) else "DESC"
    # Ties broken by the dimension, ascending, matching shape_series. SQL leaves the
    # order among equal values unspecified, so without this two groups with the same
    # value came back in an engine-dependent order -- and one that could differ from
    # import mode's for identical data. Redundant when already ordering by the
    # dimension, which is unique per group.
    tiebreak = "" if plan.sort_by_dim else ", 1 ASC"

    sql = (
        f"SELECT {dim_sql} AS {dim_sql}, {agg_sql} AS {meas_sql} "
        f"FROM ({base}) AS src{where_clause} "
        f"GROUP BY {dim_sql} "
        f"ORDER BY {order_col} {order_dir}{tiebreak} "
        f"{_limit_clause(dialect, plan.limit)}"
    )
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}


def build_count_sql(
    dataset, plan: QueryPlan, dialect: str,
    rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """Companion query to build_sql: shape_series reports `total` as the row
    count of the frame it was handed, which for import mode is every raw row.
    The aggregate query only returns one row per group, so this recovers the
    true underlying row count (with the same WHERE, including RLS) to keep
    `total`'s meaning consistent between import and DirectQuery results."""
    base = _base_query_sql(dataset, rls_where)
    where_sql, params = _build_where(plan.filters)
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    sql = f"SELECT COUNT(*) FROM ({base}) AS src{where_clause}"
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}


def _dim_group_where(plan: QueryPlan) -> tuple[str, dict]:
    """The WHERE clause for a per-dimension GROUP BY, with NULL dimension rows
    excluded.

    Import mode groups with pandas, whose groupby DROPS rows with a NaN key, so a
    NULL dimension value is never a rendered group there. SQL disagrees: GROUP BY
    gives NULL a group of its own. DirectQuery standardises on the pandas answer,
    because the aggregate path's rows are literally produced by pandas -- the
    pushed-down frame goes back through shape_series, which drops the NULL group
    before the widget ever sees it. Any SQL total or row set that kept it would be
    describing rows nothing renders."""
    where_sql, params = _build_where(plan.filters)
    clauses = [c for c in (where_sql, f"{_quote(plan.dim)} IS NOT NULL") if c]
    return " WHERE " + " AND ".join(clauses), params


def build_group_total_sql(
    dataset, plan: QueryPlan, dialect: str,
    rls_where: str = "", rls_params: dict | None = None, count_only: bool = False,
    only_dims: list | None = None,
) -> tuple[str, dict]:
    """Grand total for a grouped ("show totals") result, and its group count.

    build_sql pushes `plan.limit` into SQL, so the frame handed back to the shaper
    holds only the top-N groups -- a total built from it would silently describe
    the visible page. This aggregates the SOURCE rows directly (same base, same
    WHERE, same RLS), with no GROUP BY: the total is the configured aggregation
    at no grain -- AVG over every row, never the sum or mean of per-group AVGs,
    which only coincide for SUM and COUNT. The second column counts the groups,
    so the caller knows whether the page shows all of them.

    `only_dims` restricts it to the rows of those dimension values -- the
    "shown rows" total for a page that shows some of the groups.

    `count_only` mirrors _build_count_series_sql's COUNT(*)-per-group shape for the
    no-measure case.

    NULL dimension values are EXCLUDED (see _dim_group_where). SQL's GROUP BY makes
    NULL a group of its own; pandas' groupby drops those rows outright, so on the
    aggregate path -- where shape_series re-groups the pushed-down frame -- a NULL
    group is never rendered. A total that counted it would describe rows the table
    does not show, which is the exact failure this builder exists to prevent."""
    base = _base_query_sql(dataset, rls_where)
    dim_sql = _quote(plan.dim)
    value_sql = "COUNT(*)" if count_only else _agg_sql(plan.agg, _quote(plan.meas), dialect)
    where_clause, params = _dim_group_where(plan)
    if only_dims is not None:
        # Bound, never inlined -- the same `:name` binds _build_where writes.
        names = [f"__tot_d{i}" for i in range(len(only_dims))]
        params = {**params, **dict(zip(names, only_dims))}
        in_list = ", ".join(f":{n}" for n in names) or "NULL"
        where_clause += f" AND {dim_sql} IN ({in_list})"
    sql = (
        f'SELECT {value_sql} AS "__dq_v__", COUNT(DISTINCT {dim_sql}) AS "__dq_g__" '
        f"FROM ({base}) AS src{where_clause}"
    )
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}


def build_row_totals_sql(
    dataset, plan: "RowFetchPlan", dialect: str, columns: list[str],
    rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """Column totals for a raw-table result, computed over every matching row.

    _run_row_capped hands the shaper a frame capped at DEFAULT_ROW_CAP and randomly
    sampled when the table is bigger, so the shaper's own column sums would be the
    sample's sums wearing a "Total" label -- directly under a truthful "Showing
    10,000 of 4,000,000". This sums the real columns in SQL instead, with the same
    base/WHERE/RLS the fetch used, so the displayed total is the true one."""
    base = _base_query_sql(dataset, rls_where)
    where_sql, params = _build_where(plan.filters)
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    select_list = ", ".join(f'SUM({_quote(c)}) AS "t{i}"' for i, c in enumerate(columns))
    sql = f"SELECT {select_list} FROM ({base}) AS src{where_clause}"
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}


def _histogram_bin_edges(low: float, high: float, bins: int) -> list[float]:
    """Mirrors numpy's np.histogram(..., bins=n) edge calculation exactly (verified
    against numpy directly): evenly spaced edges across [low, high], except when
    low == high, where numpy widens the range by 0.5 on each side rather than
    producing zero-width bins."""
    if low == high:
        low, high = low - 0.5, high + 0.5
    step = (high - low) / bins
    return [low + i * step for i in range(bins)] + [high]


@dataclass
class HistogramPlan:
    meas: str
    bins: int
    filters: list[dict] = field(default_factory=list)


def plan_histogram(config: dict, widget_type: str) -> HistogramPlan:
    if widget_type != "histogram":
        raise DirectQueryUnsupported(f"widget_type '{widget_type}' is not a histogram")
    meas = config.get("measure") or None
    if not meas:
        raise DirectQueryUnsupported("histogram requires a measure")
    filters = config.get("filters") or []
    for f in filters:
        if f.get("op") not in _SUPPORTED_FILTER_OPS:
            raise DirectQueryUnsupported(
                f"filter operator '{f.get('op')}' is not yet supported for DirectQuery datasets"
            )
    return HistogramPlan(meas=meas, bins=int(config.get("bins") or 10), filters=filters)


def build_histogram_stats_sql(dataset, plan: HistogramPlan, rls_where: str = "", rls_params: dict | None = None) -> tuple[str, dict]:
    """First pass: min/max/count of the non-null measure, needed to compute bin
    edges the same way numpy would (evenly spaced across the observed range)."""
    base = _base_query_sql(dataset, rls_where)
    meas_sql = _quote(plan.meas)
    where_sql, params = _build_where(plan.filters)
    conditions = [f"{meas_sql} IS NOT NULL"] + ([where_sql] if where_sql else [])
    sql = (
        f"SELECT MIN({meas_sql}) AS lo, MAX({meas_sql}) AS hi, COUNT({meas_sql}) AS n "
        f"FROM ({base}) AS src WHERE {' AND '.join(conditions)}"
    )
    return sql, {**(rls_params or {}), **params}


def build_histogram_bucket_sql(
    dataset, plan: HistogramPlan, edges: list[float],
    rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """Second pass: bucket counts via WIDTH_BUCKET, clamped into [1, bins] so a
    measure value exactly equal to the observed max lands in the last bin --
    matching numpy's last-bin-closed-on-both-ends behavior, since WIDTH_BUCKET's
    own convention puts values >= high in an out-of-range bucket (bins + 1)."""
    base = _base_query_sql(dataset, rls_where)
    meas_sql = _quote(plan.meas)
    bins = len(edges) - 1
    where_sql, filter_params = _build_where(plan.filters)
    conditions = [f"{meas_sql} IS NOT NULL"] + ([where_sql] if where_sql else [])
    bucket_expr = f"GREATEST(LEAST(WIDTH_BUCKET({meas_sql}, :lo, :hi, :bins), :bins), 1)"
    sql = (
        f"SELECT {bucket_expr} AS bucket, COUNT(*) AS cnt "
        f"FROM ({base}) AS src WHERE {' AND '.join(conditions)} "
        f"GROUP BY bucket"
    )
    params = {**(rls_params or {}), **filter_params, "lo": edges[0], "hi": edges[-1], "bins": bins}
    return sql, params


@dataclass
class CorrelationMatrixPlan:
    measures: list[str]
    filters: list[dict] = field(default_factory=list)


def plan_correlation_matrix(config: dict, widget_type: str) -> CorrelationMatrixPlan:
    if widget_type != "correlation_matrix":
        raise DirectQueryUnsupported(f"widget_type '{widget_type}' is not a correlation_matrix")
    measures = list(dict.fromkeys(config.get("measures") or []))
    if len(measures) < 2:
        raise DirectQueryUnsupported("correlation_matrix requires at least two measures")
    filters = config.get("filters") or []
    for f in filters:
        if f.get("op") not in _SUPPORTED_FILTER_OPS:
            raise DirectQueryUnsupported(
                f"filter operator '{f.get('op')}' is not yet supported for DirectQuery datasets"
            )
    return CorrelationMatrixPlan(measures=measures, filters=filters)


def build_correlation_matrix_sql(
    dataset, plan: CorrelationMatrixPlan, rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """One row, one CORR(mi, mj) column per (i, j) pair with i <= j -- the matrix
    is symmetric, so the caller mirrors these into the lower triangle rather than
    computing them twice."""
    base = _base_query_sql(dataset, rls_where)
    n = len(plan.measures)
    cols = [
        f'CORR({_quote(plan.measures[i])}, {_quote(plan.measures[j])}) AS c{i}_{j}'
        for i in range(n) for j in range(i, n)
    ]
    where_sql, filter_params = _build_where(plan.filters)
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    sql = f"SELECT {', '.join(cols)} FROM ({base}) AS src{where_clause}"
    return sql, {**(rls_params or {}), **filter_params}


DEFAULT_ROW_CAP = 10_000

# widget_type -> the row_capped strategy from the design spec's shaper
# capability matrix: these shapers operate on raw, row-level data (a scatter
# plot literally is one mark per row), so there is no GROUP BY to push down --
# DirectQuery instead fetches up to the cap and lets the existing shaper do
# 100% of its own local computation unchanged, exactly like import mode.
ROW_CAPPED_WIDGET_TYPES = {
    "numeric_series", "bubble", "bubble_change", "parallel_coordinates", "schedule", "vector_plot",
    # "table" also powers the /data-preview endpoint's DirectQuery path -- it reuses
    # this exact row-capped fetch (no dimension/measure grouping) to hand shape_series
    # its raw-table branch a DataFrame, same as import mode's own preview.
    "table", "list", "kpi", "card",
}

_RANDOM_FN = {"mysql": "RAND()", "oracle": "DBMS_RANDOM.VALUE", "sqlserver": "NEWID()"}
# clickhouse is absent on purpose: the builder emits RANDOM() and the
# transpile in _finalize_for_dialect rewrites it to randCanonical().


@dataclass
class RowFetchPlan:
    filters: list[dict] = field(default_factory=list)


def plan_row_fetch(config: dict, widget_type: str,
                   allow_any_widget: bool = False) -> RowFetchPlan:
    """Plan a raw-row fetch.

    `allow_any_widget` is how the FALLBACK gets in. `ROW_CAPPED_WIDGET_TYPES`
    lists the widgets that always take this path (a scatter is one mark per row,
    so there is no GROUP BY to push down). The fallback arrives here for the
    opposite reason -- SQL could not express the widget or its aggregation -- and
    refusing it on a list meant for the first case is what printed "not
    supported" where a chart belonged. Filters are still checked either way.
    """
    if not allow_any_widget and widget_type not in ROW_CAPPED_WIDGET_TYPES:
        raise DirectQueryUnsupported(f"widget_type '{widget_type}' does not support row-capped DirectQuery fetch")
    filters = config.get("filters") or []
    for f in filters:
        if f.get("op") not in _SUPPORTED_FILTER_OPS:
            raise DirectQueryUnsupported(
                f"filter operator '{f.get('op')}' is not yet supported for DirectQuery datasets"
            )
    return RowFetchPlan(filters=filters)


def build_row_fetch_sql(
    dataset, plan: RowFetchPlan, dialect: str, cap: int, sampled: bool,
    rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """Fetches every column (SELECT *), matching import mode's own behavior of
    loading the whole file -- shapers only ever touch their role-mapped columns
    and ignore the rest, so there's no need (or benefit) to guess which columns
    a given widget_type actually needs. When sampled, rows are ordered randomly
    before the cap so the sample is representative of the full filtered set
    rather than an arbitrary prefix (e.g. insertion order)."""
    base = _base_query_sql(dataset, rls_where)
    where_sql, params = _build_where(plan.filters)
    where_clause = f" WHERE {where_sql}" if where_sql else ""
    if sampled:
        order_clause = f" ORDER BY {_RANDOM_FN.get(dialect, 'RANDOM()')}"
    elif dialect == "sqlserver":
        # T-SQL's OFFSET/FETCH is only legal after ORDER BY, and this path has no
        # meaningful sort to apply. `(SELECT NULL)` is the standard idiom for
        # satisfying that requirement without imposing an ordering.
        order_clause = " ORDER BY (SELECT NULL)"
    else:
        order_clause = ""
    sql = f"SELECT * FROM ({base}) AS src{where_clause}{order_clause} {_limit_clause(dialect, cap)}"
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}

# ── engine registry ───────────────────────────────────────────────────────────
# Moved to engines.py (layer 1): opening a pooled connection is connection
# acquisition, not query building. Re-exported here because `agent/executor.py`,
# `metadata/*` and `demo_content.py` import these names from this module.
from .engines import (  # noqa: E402
    _ENGINE_REGISTRY,
    _ENGINE_REGISTRY_LOCK,
    _engine_key,
    dispose_engine,
    get_engine,
    get_metadata_engine,
)


def _validate_columns(dataset, plan: QueryPlan) -> None:
    """Identifier allowlist: every column that will be interpolated into SQL
    (dim, measure, filter columns) must be a real, known column on this
    dataset. This is the SQL-injection defense from the design spec's "SQL
    Safety" section -- an allowlist, not string-escaping, so a column name
    that isn't real can never reach the database at all."""
    known = {c.name for c in dataset.columns}
    referenced = {plan.dim, plan.meas, *(f.get("column") for f in plan.filters)}
    for col in referenced:
        if col and col not in known:
            raise DirectQueryUnsupported(f"unknown column '{col}'")


def _validate_known_columns(dataset, columns: list[str], filters: list[dict]) -> None:
    """Same allowlist check as _validate_columns, generalized for the stat
    strategies (histogram/correlation_matrix), which reference a plain column
    list rather than a QueryPlan's dim/meas shape."""
    known = {c.name for c in dataset.columns}
    referenced = {*columns, *(f.get("column") for f in filters)}
    for col in referenced:
        if col and col not in known:
            raise DirectQueryUnsupported(f"unknown column '{col}'")


def _translate_rls(dataset, rls_filter_expr: str | None) -> tuple[str, dict]:
    """Shared fail-closed RLS translation used by every DirectQuery execution
    path. Translation happens before any connection is opened or query built,
    so an untranslatable rule can never result in a query running without its
    predicate."""
    if not rls_filter_expr:
        return "", {}
    known_columns = {c.name for c in dataset.columns}
    try:
        return translate_filter_expr(rls_filter_expr, known_columns)
    except ExpressionTranslationError as e:
        raise DirectQueryUnsupported(f"row-level security rule could not be translated: {e}") from e


def _directquery_cache_key(
    source_cfg: dict, dataset, config: dict, widget_type: str,
    rls_filter_expr: str | None, ttl_seconds: int, now: float | None = None,
    row_cap: int | None = None, cache_epoch: int = 0,
) -> str:
    """Cache key for DirectQuery results, reusing widget_data's own LRU cache
    rather than a second cache structure. `kind` + data_source_id + source_table/
    source_query is the source discriminator the design spec calls for (file_stat
    is meaningless without a file, and None already means "file missing" in the
    import-mode key, so a DirectQuery entry needs its own identity to avoid
    colliding with one). The TTL bucket (`now // ttl_seconds`) replaces mtime-based
    invalidation -- entries age out by construction as the bucket rolls over,
    without a sweeper. rls_filter_expr stays verbatim, preserving the same
    isolation guarantee as widget_data._widget_data_cache_key: two roles with
    different RLS expressions can never share an entry.

    T6: `cache_epoch` (the DataSource's `cache_epoch` column) is folded in so a
    drift-detected schema/data change makes every existing entry for the source
    unaddressable by any new key, without a sweeper -- the LRU evicts the
    orphaned entries naturally as new ones push it out."""
    bucket = int((now if now is not None else time.time()) // ttl_seconds)
    payload = {
        "kind": "directquery",
        "data_source_id": getattr(dataset, "data_source_id", None),
        "source_table": dataset.source_table,
        "source_query": dataset.source_query,
        "config": config,
        "widget_type": widget_type,
        "rls_filter_expr": rls_filter_expr,
        "row_cap": row_cap,
        "ttl_bucket": bucket,
        "cache_epoch": cache_epoch,
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _query_shape(dataset, config: dict, rls_filter_expr: str | None) -> dict:
    """What index advice needs from a run: the table, the columns the filters
    and the RLS rule read, the grouped column. Column NAMES only -- never a
    value, never SQL. Logged only with runs that reached the source; a cache
    hit cost the database nothing and would only inflate the counts.

    Best effort by construction: a shape that cannot be derived (an RLS rule
    the translator refuses) logs as unknown rather than failing the render
    it describes.
    """
    cols: set[str] = set()
    for f in config.get("filters") or []:
        if f.get("column"):
            cols.add(str(f["column"]))
    if rls_filter_expr:
        try:
            from .sql_expr import expression_columns
            cols |= expression_columns(rls_filter_expr, {c.name for c in dataset.columns})
        except Exception:  # noqa: BLE001 -- advice is best effort; the render is not
            pass
    return {
        "source_table": getattr(dataset, "source_table", None),
        "filter_columns": sorted(cols),
        "group_column": config.get("dimension") or None,
    }



@dataclass
class FetchedFrame:
    """Rows from a live source, and an honest account of what they are.

    `sampled` is the field that matters. Below the cap the frame IS every
    matching row and any figure computed from it is exact -- the same guarantee
    import mode gives. Above the cap it is a RANDOM sample (the fetch orders by
    the dialect's random function before limiting, never an arbitrary prefix),
    so a share or a correlation computed from it is an estimate.

    Callers must carry that distinction into what they show. `insights.py`
    promises "every number is computed here, never guessed"; a sampled figure
    presented without that word would break the promise quietly, which is worse
    than the refusal this function replaces.
    """
    frame: "pd.DataFrame"
    total_rows: int
    sampled: bool
    row_cap: int

    @property
    def exact(self) -> bool:
        return not self.sampled


def fetch_analysis_frame(
    source_cfg: dict, dataset, *, rls_filter_expr: str | None = None,
    row_cap: int = DEFAULT_ROW_CAP, filters: list[dict] | None = None,
) -> FetchedFrame:
    """Read a DirectQuery dataset into a frame, bounded and row-secured.

    Row-level security is pushed down with the query -- `_base_query_sql` wraps
    the predicate around the base BEFORE anything else -- so this is open to
    every user on the same terms a widget is, and an expression that cannot be
    translated fails the request rather than widening it.

    The count comes first, deliberately. It is one cheap query, and it is what
    lets an analysis say "measured over all 112,650 rows" instead of leaving a
    reader to wonder whether they are looking at everything.
    """
    dialect = connectors.sql_family_of(source_cfg)
    if dialect not in SUPPORTED_FAMILIES:
        raise DirectQueryUnsupported(
            f"DirectQuery does not yet support '{dialect}' sources")

    plan = RowFetchPlan(filters=list(filters or []))
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)

    count_sql, count_params = build_count_sql(
        dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)
    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        total = int(conn.execute(text(count_sql), count_params).scalar_one())
        sampled = total > row_cap
        fetch_sql, fetch_params = build_row_fetch_sql(
            dataset, plan, dialect, row_cap, sampled,
            rls_where=rls_where, rls_params=rls_params)
        frame = pd.read_sql(text(fetch_sql), conn, params=fetch_params)

    return FetchedFrame(frame=frame, total_rows=total, sampled=sampled,
                        row_cap=row_cap)

def run_direct_query(*args, **kwargs) -> dict:
    """Execute a pushdown query, translating a dead source into a domain error.

    Every caller went through the generic 500 handler when the customer's
    database was unreachable, so a reader saw "Internal server error" on a
    widget for an outage that was not ours. Translated HERE rather than in each
    router: there are four call sites and they would drift.

    Only CONNECTION-level failures are caught. A bug in the shaping code must
    keep escaping as a 500 -- turning every exception into "the source is
    down" would be a comfortable lie that hides our own faults.

    Which is what the first version of this did: it caught `DBAPIError`, the
    PARENT of ProgrammingError, DataError and IntegrityError, so a renamed
    table or a dropped column reported the customer database as unreachable
    and sent them to check a server that was answering perfectly. Caught by
    a benchmark whose schema name was wrong.

    OperationalError is the connection-level class (server gone, refused,
    authentication, timeout); InterfaceError is the connection being already
    closed, which is what a restart leaves behind. Everything else is a
    question the source understood and answered with a complaint, and that
    is not an outage.
    """
    from sqlalchemy.exc import InterfaceError, OperationalError
    try:
        return _run_direct_query_inner(*args, **kwargs)
    except (OperationalError, InterfaceError) as e:
        # The driver's text is deliberately dropped, not reformatted.
        raise SourceUnavailable("could not reach the data source") from e


def _run_direct_query_inner(
    source_cfg: dict, dataset, config: dict, widget_type: str = "bar",
    rls_filter_expr: str | None = None, row_cap: int | None = None,
    cache_ttl_seconds: int = 60, cache_epoch: int = 0,
    org_id: int | None = None,
) -> dict:
    # E3: one span per DirectQuery execution. Attributes carry only
    # identifiers/status/timings -- never the built SQL or config values,
    # matching query_runs.sql_hash discipline (this path already logs
    # sql_hash=None to query_runs, so there is no SQL text to hash here).
    with telemetry.tracer.start_as_current_span("directquery.run") as span:
        span.set_attribute("dataset_id", getattr(dataset, "id", None) or 0)
        span.set_attribute("widget_type", widget_type)
        start = time.monotonic()
        cache_key = None
        if cache_ttl_seconds > 0:
            cache_key = _directquery_cache_key(
                source_cfg, dataset, config, widget_type, rls_filter_expr, cache_ttl_seconds,
                row_cap=row_cap, cache_epoch=cache_epoch,
            )
            cached = _widget_data_cache_get(cache_key)
            if cached is not None:
                ms = int((time.monotonic() - start) * 1000)
                log_query_run_sync(
                    org_id=org_id, source_kind="directquery",
                    data_source_id=getattr(dataset, "data_source_id", None),
                    dataset_id=getattr(dataset, "id", None), sql_hash=None,
                    rows_returned=None, duration_ms=ms,
                    executor="pushdown", cache_hit=True,
                )
                span.set_attribute("status", "ok")
                span.set_attribute("cache_hit", True)
                span.set_attribute("ms", ms)
                return copy.deepcopy(cached)

        result = _dispatch_direct_query(source_cfg, dataset, config, widget_type, rls_filter_expr, row_cap)
        # The one population field, whichever pushdown strategy answered (the
        # stat strategies return without passing through the import shaper).
        if isinstance(result, dict) and "rows_scanned" not in result and isinstance(result.get("total"), int):
            result["rows_scanned"] = result["total"]
        ms = int((time.monotonic() - start) * 1000)
        log_query_run_sync(
            org_id=org_id, source_kind="directquery",
            data_source_id=getattr(dataset, "data_source_id", None),
            dataset_id=getattr(dataset, "id", None), sql_hash=None,
            rows_returned=result.get("total") if isinstance(result, dict) else None,
            duration_ms=ms,
            executor="pushdown", cache_hit=False,
            **_query_shape(dataset, config, rls_filter_expr),
        )
        span.set_attribute("status", "ok")
        span.set_attribute("cache_hit", False)
        span.set_attribute("ms", ms)

        # Every DirectQuery strategy funnels through here before caching, so a single rule
        # pass covers both kinds of pushdown path: the ones that already ran evaluate_rules
        # inside get_widget_data_from_df (_run_row_capped, and the plain aggregate branch at
        # the bottom of _dispatch_direct_query), and the stat-strategy paths that return
        # directly instead (_run_histogram, _run_correlation_matrix, _run_count_series),
        # which display_rules.py's docstring and the spec claim get rules identically to
        # import mode -- without this, they didn't. Same call shape as
        # get_widget_data_from_df: rules come from config["display_rules"], errors pop into
        # rule_errors, skip on no rules or an error result. The `"rule_styles" not in result`
        # guard makes this idempotent for paths that already evaluated once, instead of
        # scoring every rule against the same frame twice.
        rules = config.get("display_rules") or []
        if rules and result.get("type") != "error" and "rule_styles" not in result:
            from .display_rules import evaluate_rules  # local: avoids an import cycle

            styles = evaluate_rules(result, rules)
            result["rule_errors"] = styles.pop("errors")
            result["rule_styles"] = styles

        if cache_key is not None:
            try:
                entry_size = len(json.dumps(result, default=str))
            except (TypeError, ValueError):
                entry_size = 0
            if entry_size <= settings.widget_data_cache_max_entry_bytes:
                _widget_data_cache_set(cache_key, copy.deepcopy(result), ttl_s=cache_ttl_seconds)
        return result



def _fetch_and_compute(
    source_cfg: dict, dataset, config: dict, widget_type: str,
    rls_filter_expr: str | None, row_cap: int | None,
) -> dict:
    """Fetch the rows and let the ordinary shaper do the work.

    The universal strategy: whatever import mode can draw from a frame, this can
    draw from a live source, because it hands the frame to the same function.
    What it cannot do is see past the row cap -- so above it the frame is a
    random sample and `_run_row_capped` marks the result accordingly.

    Per-object override of the system row cap, clamped: the floor keeps a typo
    from reducing a widget to three rows, and the ceiling (10x default) keeps a
    single widget from asking a production database for everything. The cap is
    about protecting the SOURCE, so an unbounded override would defeat it.
    """
    override = config.get("data_limit")
    # The FALLBACK computes aggregates; the row-capped list draws marks. A
    # scatter plot genuinely does not need more than 10,000 points, but a COUNT
    # over a 10,000-row sample of a 100,000-row table reports a tenth of the
    # truth -- marked `sampled`, and still a wrong number on the screen. So the
    # fallback gets the ANALYSIS cap, which is sized for exactly this: big
    # enough that ordinary tables come back whole, bounded enough that nobody
    # pulls millions of rows across the wire to add them up.
    from ..core.config import settings
    base = (int(getattr(settings, "analysis_row_cap", 250_000) or 250_000)
            if widget_type not in ROW_CAPPED_WIDGET_TYPES
            else (row_cap or DEFAULT_ROW_CAP))
    effective = base
    if override:
        try:
            effective = max(100, min(int(override), base * 10))
        except (TypeError, ValueError):
            pass
    return _run_row_capped(source_cfg, dataset, config, widget_type,
                           rls_filter_expr, effective, allow_any_widget=True)


def _dispatch_direct_query(
    source_cfg: dict, dataset, config: dict, widget_type: str,
    rls_filter_expr: str | None, row_cap: int | None,
) -> dict:
    if widget_type == "histogram":
        return _run_histogram(source_cfg, dataset, config, rls_filter_expr)
    if widget_type == "correlation_matrix":
        return _run_correlation_matrix(source_cfg, dataset, config, rls_filter_expr)
    if widget_type in ROW_CAPPED_WIDGET_TYPES:
        return _fetch_and_compute(source_cfg, dataset, config, widget_type,
                                  rls_filter_expr, row_cap)
    if widget_type in AGGREGATE_STRATEGY_WIDGET_TYPES and not config.get("measure"):
        # No measure = "count of rows per dimension value" (the single most common
        # widget shape). This can't reuse the plain aggregate path below, which
        # hands its pushed-down result back to the shaper for re-aggregation --
        # re-counting an already-one-row-per-group result gives 1 for every group,
        # not the true count (the same grain-invariant hazard as an explicit
        # 'count' aggregation). _run_count_series computes the true count directly
        # instead of routing through the shaper.
        return _run_count_series(source_cfg, dataset, config, widget_type, rls_filter_expr)

    dialect = connectors.sql_family_of(source_cfg)
    if dialect not in SUPPORTED_FAMILIES:
        # The one refusal that survives: with no dialect there is no connection
        # to fetch from either, so there is nothing to fall back TO.
        raise DirectQueryUnsupported(f"DirectQuery does not yet support '{dialect}' sources")

    try:
        plan = _time_axis_default(plan_query(config, widget_type), config, dataset)
    except DirectQueryUnsupported:
        # SQL cannot express this widget or this aggregation grain-safely --
        # `count` re-counted over a pre-aggregated row gives 1, a forecast is not
        # an aggregate at all. Neither is a reason to show the person an apology:
        # fetch the rows and compute it the way import mode does.
        #
        # Only for a widget that REALLY EXISTS, though. An unknown widget_type is
        # not a DirectQuery limitation and must keep saying so -- falling back
        # would turn a typo into a confusing shaper error thrown from inside a
        # database fetch.
        from .widget_data import SHAPERS
        if widget_type not in SHAPERS:
            raise
        return _fetch_and_compute(source_cfg, dataset, config, widget_type,
                                  rls_filter_expr, row_cap)
    _validate_columns(dataset, plan)
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)

    sql, params = build_sql(dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)
    count_sql, count_params = build_count_sql(dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)

    # `show_totals` is only honoured for the table-shaped widget types, but the frame
    # the shaper sees here is already LIMITed by build_sql -- so whenever the shaper
    # would emit a `totals` row, the true grand total has to come from its own
    # unlimited SQL aggregate, computed in the same connection as everything else.
    wants_totals = bool(config.get("show_totals"))
    total_sql = total_params = None
    if wants_totals:
        total_sql, total_params = build_group_total_sql(
            dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params,
        )

    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
        total_rows = conn.execute(text(count_sql), count_params).scalar_one()
        grand_total, n_groups = (conn.execute(text(total_sql), total_params).one()
                                 if wants_totals else (None, None))

    result = get_widget_data_from_df(df, config, widget_type, flag_partial=False)
    if "total" in result:
        result["total"] = total_rows
        result["rows_scanned"] = total_rows  # the population, not the pre-aggregated groups
    # Truncation, measured in SQL. The shaper only ever sees the LIMITed page,
    # so its own `truncation` would always say "nothing cut" -- a false
    # all-clear. A page that came back short cannot have been cut; only a FULL
    # page needs the group count, so the common case costs no extra query.
    if isinstance(result.get("truncation"), dict) and plan.dim:
        shown = result["truncation"].get("shown", 0)
        of = shown
        if len(df) >= plan.limit:
            if n_groups is None:
                gsql, gparams = build_group_total_sql(
                    dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)
                with engine.connect() as conn:
                    _, n_groups = conn.execute(text(gsql), gparams).one()
            of = max(int(n_groups or 0), shown)
        result["truncation"] = {**result["truncation"], "applied": of > shown, "of": of,
                                "limit": plan.limit, "reason": "limit"}
    if wants_totals and _totals_need_sql(result, config):
        shown_total = None
        shown_dims = _shown_dim_values(df[plan.dim], result)
        if len(shown_dims) < (n_groups or 0):
            shown_sql, shown_params = build_group_total_sql(
                dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params,
                only_dims=shown_dims,
            )
            with engine.connect() as conn:
                shown_total = conn.execute(text(shown_sql), shown_params).one()[0]
        _replace_series_grand_total(result, grand_total, n_groups, shown_total)
    return result


def _totals_need_sql(result: dict, config: dict) -> bool:
    """Whether the shaper's `totals` must be replaced by the SQL-measured ones.

    Not when the shaper withheld them (a quick calc outside the measure's units),
    nor for a percent-of-total quick calc, whose total is a share of the page
    rather than a quantity SQL can measure. With suppression active the SQL total
    would include the suppressed groups' rows, so a reader could subtract the
    visible cells to recover them: the total is withheld instead."""
    if not isinstance(result.get("totals"), list) or config.get("quick_calc"):
        return False
    if config.get("suppress_below"):
        result.pop("totals", None)
        result.pop("totals_shown", None)
        result.pop("totals_basis", None)
        result["totals_unavailable"] = "suppressed"
        return False
    return True


def _shown_dim_values(dim_values: pd.Series, result: dict) -> list:
    """The raw dimension values of the groups the shaped result displays.

    Matched on the label the shaper emitted, so a group HAVING or rank dropped
    after the SQL fetch is not counted as shown. Raw values (not labels) are what
    get bound back into the SQL, so the database compares like with like."""
    labels = {str(r.get("name")) for r in (result.get("rows") or []) if isinstance(r, dict)}
    return [v for v in dim_values.tolist() if str(_safe(v)) in labels]


def _replace_series_grand_total(result: dict, grand_total, n_groups=None, shown_total=None) -> None:
    """Swap a shaper-computed grand total for one measured over the whole table.

    shape_series aligns `totals` positionally with the keys of its own row dicts, so
    the position to overwrite is the one for "value"; every other position is a label
    or a page-derived running column and stays None. The shaper only ever saw the
    SQL-limited page, so its basis is rewritten against the real group count too."""
    if not isinstance(result.get("totals"), list):
        return
    rows = result.get("rows") or []
    keys = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else ["name", "value"]
    result["totals"] = [_sql_number(grand_total) if k == "value" else None for k in keys]
    result.pop("totals_shown", None)
    if shown_total is not None:
        result["totals_shown"] = [_sql_number(shown_total) if k == "value" else None for k in keys]
    if n_groups is not None:
        result["totals_basis"] = {"unit": "groups", "shown": len(rows), "of": int(n_groups),
                                  "truncated": shown_total is not None,
                                  "suppressed_excluded": False}


def _sql_number(v):
    """DBAPI drivers hand back Decimal for NUMERIC columns; the rest of a widget
    payload is plain JSON numbers, so normalise here rather than leaving one field
    that only survives because an encoder happens to special-case it."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    return _safe(v)


# sql_stat strategy is Postgres-only for now: WIDTH_BUCKET/CORR semantics were
# verified directly against a live Postgres instance during implementation, but
# MySQL/SQLite/Oracle each differ (no native WIDTH_BUCKET on MySQL/SQLite; Oracle's
# boundary behavior is unverified here) -- rejecting them explicitly beats
# shipping untested dialect SQL.
_STAT_DIALECTS = {"postgresql"}


def _spec_supports_stat(source_cfg: dict) -> bool:
    """Stat pushdown (WIDTH_BUCKET/CORR) support, honoring per-connector overrides
    (a Postgres-wire source like Redshift lacks these and sets stat_override=False)."""
    try:
        return connectors.resolve(source_cfg.get("type")).supports_stat
    except connectors.UnknownConnector:
        return False


def _run_histogram(source_cfg: dict, dataset, config: dict, rls_filter_expr: str | None) -> dict:
    dialect = connectors.sql_family_of(source_cfg)
    if not _spec_supports_stat(source_cfg):
        raise DirectQueryUnsupported(f"histogram pushdown does not yet support '{source_cfg.get('type')}' sources")

    plan = plan_histogram(config, "histogram")
    _validate_known_columns(dataset, [plan.meas], plan.filters)
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)

    stats_sql, stats_params = build_histogram_stats_sql(dataset, plan, rls_where, rls_params)
    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        stats_row = conn.execute(text(stats_sql), stats_params).one()
        if stats_row.n == 0 or stats_row.lo is None:
            return {"type": "empty", "rows": [], "total": 0}
        edges = _histogram_bin_edges(float(stats_row.lo), float(stats_row.hi), plan.bins)

        bucket_sql, bucket_params = build_histogram_bucket_sql(dataset, plan, edges, rls_where, rls_params)
        bucket_rows = conn.execute(text(bucket_sql), bucket_params).all()

    counts = {int(r.bucket): int(r.cnt) for r in bucket_rows}
    rows = []
    for i in range(plan.bins):
        lo, hi = edges[i], edges[i + 1]
        rows.append({
            "name": f"{lo:.2f}–{hi:.2f}",
            "value": counts.get(i + 1, 0),
            "bin_start": lo, "bin_end": hi,
        })
    return {"type": "series", "measure": plan.meas, "rows": rows, "total": int(stats_row.n)}


def _run_correlation_matrix(source_cfg: dict, dataset, config: dict, rls_filter_expr: str | None) -> dict:
    dialect = connectors.sql_family_of(source_cfg)
    if not _spec_supports_stat(source_cfg):
        raise DirectQueryUnsupported(f"correlation_matrix pushdown does not yet support '{dialect}' sources")

    plan = plan_correlation_matrix(config, "correlation_matrix")
    _validate_known_columns(dataset, plan.measures, plan.filters)
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)

    sql, params = build_correlation_matrix_sql(dataset, plan, rls_where, rls_params)
    count_sql, count_params = build_count_sql(dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)

    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        row = conn.execute(text(sql), params).one()
        total = conn.execute(text(count_sql), count_params).scalar_one()

    n = len(plan.measures)
    row_map = row._mapping
    matrix = []
    for i in range(n):
        matrix.append([
            (lambda v: float(v) if v is not None else None)(row_map[f"c{min(i, j)}_{max(i, j)}"])
            for j in range(n)
        ])
    return {"type": "matrix", "measures": plan.measures, "matrix": matrix, "total": int(total)}


def _run_row_capped(
    source_cfg: dict, dataset, config: dict, widget_type: str,
    rls_filter_expr: str | None, row_cap: int, allow_any_widget: bool = False,
) -> dict:
    dialect = connectors.sql_family_of(source_cfg)
    if dialect not in SUPPORTED_FAMILIES:
        raise DirectQueryUnsupported(f"DirectQuery does not yet support '{dialect}' sources")

    plan = plan_row_fetch(config, widget_type, allow_any_widget=allow_any_widget)
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)

    count_sql, count_params = build_count_sql(dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)
    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        total = conn.execute(text(count_sql), count_params).scalar_one()
        sampled = total > row_cap
        fetch_sql, fetch_params = build_row_fetch_sql(
            dataset, plan, dialect, row_cap, sampled, rls_where=rls_where, rls_params=rls_params,
        )
        df = pd.read_sql(text(fetch_sql), conn, params=fetch_params)

        result = get_widget_data_from_df(df, config, widget_type, flag_partial=False)

        # A "Total" must describe the table, never the sample. Below the cap the
        # fetched frame IS every matching row, so the shaper's own sums are already
        # true and no second query is worth its round-trip. Above the cap the frame
        # is a random 10k-row sample, so the shaper's sums are re-measured in SQL
        # over the real rows -- computed rather than suppressed, because the raw
        # table's WHERE/RLS is already built here and SUM() over it is exact.
        totals = result.get("totals")
        if sampled and isinstance(totals, list):
            if result.get("type") == "table":
                cols = result.get("columns") or []
                # `totals[j] is not None` is the shaper's own numeric verdict on
                # column j (is_numeric_dtype); a non-numeric column has no sum in
                # either engine and stays None.
                numeric = [c for c, t in zip(cols, totals) if t is not None]
                if numeric:
                    totals_sql, totals_params = build_row_totals_sql(
                        dataset, plan, dialect, numeric, rls_where=rls_where, rls_params=rls_params,
                    )
                    row = conn.execute(text(totals_sql), totals_params).one()
                    true_sums = dict(zip(numeric, [_sql_number(v) for v in row]))
                    result["totals"] = [true_sums.get(c) if t is not None else None
                                        for c, t in zip(cols, totals)]
            else:
                # A grouped (dimension-configured) table on a sampled DirectQuery
                # frame: the shaper aggregated the sample, so its grand total is a
                # sample's sum. There is no GROUP BY pushdown on this code path to
                # measure the real one with -- plan_row_fetch deliberately plans no
                # aggregation -- so the row is DROPPED rather than shown wrong, and
                # `totals_unavailable` tells the client to say so out loud instead of
                # leaving the author thinking "Show totals" did nothing.
                result.pop("totals", None)
                result["totals_unavailable"] = "sampled"

    if "total" in result:
        result["total"] = total
        result["rows_scanned"] = total  # the population, not the pre-aggregated groups
    result["sampled"] = sampled
    if sampled:
        result["sample_size"] = len(df)
        result["total_rows"] = total
    return result


def _build_count_series_sql(
    dataset, plan: QueryPlan, dialect: str, rls_where: str = "", rls_params: dict | None = None,
) -> tuple[str, dict]:
    """COUNT(*) per dimension value -- the SQL for the no-measure case. Kept
    separate from build_sql rather than letting plan.meas be None there, since
    this result is never handed to the shaper (see _run_count_series)."""
    base = _base_query_sql(dataset, rls_where)
    dim_sql = _quote(plan.dim)
    # NULL dimension rows are excluded here as well as in the total (_dim_group_where):
    # this path builds its rows itself instead of routing them through shape_series, so
    # without this it would RENDER a nameless NULL group that import mode never shows --
    # and the two pushdown paths would disagree about whether NULL is a group at all.
    where_clause, params = _dim_group_where(plan)
    order_col = "1" if plan.sort_by_dim else "2"
    order_dir = "ASC" if (plan.sort_by_dim or not plan.sort_desc) else "DESC"
    # Ties broken by the dimension, ascending, matching shape_series. SQL leaves the
    # order among equal values unspecified, so without this two groups with the same
    # value came back in an engine-dependent order -- and one that could differ from
    # import mode's for identical data. Redundant when already ordering by the
    # dimension, which is unique per group.
    tiebreak = "" if plan.sort_by_dim else ", 1 ASC"
    sql = (
        f'SELECT {dim_sql} AS {dim_sql}, COUNT(*) AS "__dq_count__" '
        f"FROM ({base}) AS src{where_clause} "
        f"GROUP BY {dim_sql} "
        f"ORDER BY {order_col} {order_dir}{tiebreak} "
        f"{_limit_clause(dialect, plan.limit)}"
    )
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}


def _run_count_series(
    source_cfg: dict, dataset, config: dict, widget_type: str, rls_filter_expr: str | None,
) -> dict:
    dialect = connectors.sql_family_of(source_cfg)
    if dialect not in SUPPORTED_FAMILIES:
        raise DirectQueryUnsupported(f"DirectQuery does not yet support '{dialect}' sources")

    plan = _time_axis_default(plan_query(config, widget_type), config, dataset)
    _validate_columns(dataset, plan)
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)

    sql, params = _build_count_series_sql(dataset, plan, dialect, rls_where, rls_params)
    count_sql, count_params = build_count_sql(dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params)

    wants_totals = bool(config.get("show_totals"))
    total_sql = total_params = None
    if wants_totals:
        # The rows below are LIMITed in SQL, so the grand total needs the same
        # GROUP BY run unlimited -- see build_group_total_sql.
        total_sql, total_params = build_group_total_sql(
            dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params, count_only=True,
        )

    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        result_rows = conn.execute(text(sql), params).all()
        total_rows = conn.execute(text(count_sql), count_params).scalar_one()
        grand_total, n_groups = (conn.execute(text(total_sql), total_params).one()
                                 if wants_totals else (None, None))

    # Constructed directly to match shape_series's own no-measure grouped-series
    # branch field-for-field (type/dimension/measure/aggregation/rows/total) --
    # not routed through get_widget_data_from_df, since that would re-aggregate.
    rows = [{"name": _safe(name), "value": int(cnt)} for name, cnt in result_rows]
    agg = (config.get("aggregation") or "sum").lower()
    result = {
        "type": "series", "dimension": plan.dim, "measure": "count",
        "aggregation": agg, "rows": rows, "total": int(total_rows),
    }
    if wants_totals:
        # Same positional alignment shape_series uses for its own `totals`.
        result["totals"] = [None, _sql_number(grand_total)]
        # COUNT is additive over disjoint groups, so the page's own total is the
        # sum of its row counts -- exact, with no second query.
        truncated = len(rows) < int(n_groups or 0)
        if truncated:
            result["totals_shown"] = [None, sum(r["value"] for r in rows)]
        result["totals_basis"] = {"unit": "groups", "shown": len(rows), "of": int(n_groups or 0),
                                  "truncated": truncated, "suppressed_excluded": False}
    # Truncation disclosure, as in the measure path: only a full page can have
    # been cut, so only a full page pays for the group count.
    of = len(rows)
    if len(rows) >= plan.limit:
        if n_groups is None:
            gsql, gparams = build_group_total_sql(
                dataset, plan, dialect, rls_where=rls_where, rls_params=rls_params, count_only=True)
            with engine.connect() as conn:
                _, n_groups = conn.execute(text(gsql), gparams).one()
        of = max(int(n_groups or 0), len(rows))
    result["truncation"] = {"applied": of > len(rows), "shown": len(rows), "of": of,
                            "limit": plan.limit, "reason": "limit"}
    return result
