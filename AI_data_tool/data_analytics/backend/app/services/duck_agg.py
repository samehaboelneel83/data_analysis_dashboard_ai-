"""DuckDB pre-aggregation for the import/pandas widget path.

Layer 4. The problem this solves is memory, measured 2026-08-28: a 406 MB /
2M-row / 30-column CSV costs ~1.8 GB of RSS on the pandas path to answer a
five-row question, and every concurrent render holds its own frame. The same
aggregate through DuckDB costs 270 MB and 0.47s against 1808 MB and 7.16s.

The design mirrors `direct_query.py` rather than reimplementing `shape_series`:

    eligible config  ->  DuckDB produces a small PRE-AGGREGATED frame
                     ->  get_widget_data_from_df shapes it, exactly as
                         run_direct_query already does
    anything else    ->  pandas, unchanged

`shape_series` has roughly fifteen features (hierarchy levels, granularity
labels, crosstab, post-aggregation measures, quick calcs, running totals,
suppression, multi-key sort). Translating all of that into SQL would be a
rewrite. Instead `plan()` below is deliberately narrow: it recognises the plain
dimension + measure + grain-safe aggregation shape, which is exactly the
memory-dominant case the benchmark measured, and declines everything else with
a reason.

**Declining is free.** Unlike DirectQuery -- where an unsupported config must
raise, because there is no local frame to fall back to -- the fallback here is
the current pandas path, which is never wrong, only slower. So every failure
mode of this module, including an unexpected DuckDB exception, is "slower, never
wrong". That is what makes it safe to put behind a flag and turn on.

The grain-safety rules are imported from `direct_query`, not restated: applying
an aggregation twice (once here, once in the shaper) is only a no-op for
sum/avg/min/max/median/percentiles, and that analysis is already written down.
"""
from __future__ import annotations

import re
import logging
import os
from dataclasses import dataclass

import pandas as pd

from ..core.config import settings
from .direct_query import GRAIN_SAFE_AGGREGATIONS, _SUPPORTED_FILTER_OPS

logger = logging.getLogger(__name__)

#: SQL aggregate per config aggregation name. Only grain-safe entries appear:
#: the shaper re-aggregates whatever we return, so `count`/`countd`/`std`/
#: `variance`/`range` would be recomputed over one row and come out wrong.
_SQL_AGG = {
    "sum": "SUM", "avg": "AVG", "mean": "AVG", "average": "AVG",
    "min": "MIN", "max": "MAX", "median": "MEDIAN",
    "p25": "QUANTILE_CONT({col}, 0.25)", "p75": "QUANTILE_CONT({col}, 0.75)",
    "p90": "QUANTILE_CONT({col}, 0.90)", "p95": "QUANTILE_CONT({col}, 0.95)",
}

_SQL_COMPARISON = {"eq": "=", "neq": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}

#: The ONLY config keys this path understands. An ALLOWLIST, deliberately.
#:
#: The first version of this was a blocklist of features to decline, and it was
#: wrong in the way blocklists are wrong: it failed OPEN. A butterfly chart
#: passes `measure2` for its second series; that key was not on the list, so the
#: query looked eligible, DuckDB aggregated `measure` alone, and the widget
#: rendered with every `value2` missing. Caught by running the whole suite with
#: the flag forced on -- not by inspection.
#:
#: There are 34 distinct `config.get(...)` keys across app/. Any of them, and any
#: key added later, must make a config ineligible until someone has decided what
#: it means here. Unknown key -> pandas is the only safe default.
_SUPPORTED_KEYS = frozenset({
    "dimension",     # the GROUP BY column
    "measure",       # the aggregated column
    "aggregation",   # must be grain-safe; checked below
    "filters",       # translated to WHERE; ops checked below
    "limit",         # applied by the shaper, not here
    "sort",          # applied by the shaper, not here
    "sort_by",       # applied by the shaper, not here
    "sort_col",      # only when it equals the dimension; checked below
    "dimension_granularity",  # date bucketing; the label SQL is below
    "__demo__",      # a marker the demo fixtures carry; affects nothing
    # Totals presentation. Inert here: `show_subtotals` only acts on a crosstab
    # (`dimension2`, declined above) and the other two only when `show_totals`
    # is on, which is not on this list -- so none can change what this path
    # returns. Listed because new table widgets are created carrying them, and
    # an unlisted key would push every one of those onto pandas.
    "show_subtotals", "totals_position", "totals_scope",
})


#: The bucket label per granularity, as SQL over a TIMESTAMP expression `{ts}`.
#: Each must be the string `widget_data._dimension_granularity_label` produces
#: for the same date -- AND must survive that function being applied to it a
#: second time, because the shaper re-buckets whatever DuckDB hands back.
#: "2024-01", "2024-Q1", "2024-01-05" re-parse to the same label; "2024-W05"
#: fails to parse at all, so pandas hands it back untouched; and year is text
#: because `pd.to_datetime(2024)` is 1970-01-01 plus 2024 nanoseconds.
#: ISO week is %G-W%V, matching pandas isocalendar(): 2025-12-29 is 2026-W01.
_GRANULARITY_SQL = {
    "year":    "CAST(year({ts}) AS VARCHAR)",
    "quarter": "CAST(year({ts}) AS VARCHAR) || '-Q' || CAST(quarter({ts}) AS VARCHAR)",
    "month":   "strftime({ts}, '%Y-%m')",
    "week":    "strftime({ts}, '%G-W%V')",
    "day":     "strftime({ts}, '%Y-%m-%d')",
}


class Ineligible(Exception):
    """Not an error: this config simply belongs on the pandas path."""


@dataclass
class DuckPlan:
    sql: str
    #: Counts rows AFTER the user's filters but BEFORE the null-dimension drop,
    #: because that is what `shape_series` reports as `total` -- it filters, then
    #: groups (which discards NaN keys), and takes len() of the filtered frame.
    count_sql: str
    params: list
    #: Set when the dimension is date-bucketed: (unparsable, parsed) counts
    #: over the filtered rows. pandas hands a column back UNTOUCHED when
    #: nothing in it parses, and parses formats TRY_CAST does not
    #: ("01/02/2024"), so the aggregation only runs when every non-null
    #: value cast and at least one did. Otherwise: pandas.
    probe_sql: str | None
    dimension: str
    measure: str | None


#: `:r0`, `:r1` ... as `sql_expr._Translator._param` emits them. Anchored to
#: that exact shape so a colon inside a string literal can never match --
#: literals are bound, never inlined, so none reach the SQL text anyway.
_NAMED_PARAM = re.compile(r":(r\d+)\b")


def _quote_ident(name: str) -> str:
    """Double-quote an identifier for DuckDB, escaping embedded quotes.

    Column names reaching here are validated against the frame's real columns
    by `plan()` before this is called, so this is defence in depth rather than
    the primary control -- the same allowlist-not-escaping stance
    `direct_query._validate_columns` takes.
    """
    return '"' + str(name).replace('"', '""') + '"'


def is_enabled() -> bool:
    return bool(settings.widget_duckdb_pushdown)


def plan(config: dict, columns: list[str], source: str,
         extra_where: list[tuple[str, dict]] | None = None) -> DuckPlan:
    """Build a pushdown plan, or raise `Ineligible` with the reason.

    `columns` is the real column list of the dataset; every identifier that
    reaches the SQL must appear in it.
    """
    unknown = sorted(k for k, v in config.items()
                     if k not in _SUPPORTED_KEYS and v not in (None, "", [], {}))
    if unknown:
        raise Ineligible(f"config uses {unknown[0]!r}")

    dim = config.get("dimension") or None
    meas = config.get("measure") or None
    agg = (config.get("aggregation") or "sum").lower()

    if not dim:
        raise Ineligible("no dimension (scalar/KPI shape)")
    if dim not in columns:
        raise Ineligible(f"dimension '{dim}' is not a real column")
    if not meas:
        raise Ineligible("no measure (count-style aggregation)")
    if meas not in columns:
        # A measure name that is not a column is a post-aggregation measure
        # expression, resolved by measure_eval against the full frame.
        raise Ineligible(f"measure '{meas}' is not a real column")
    if agg not in GRAIN_SAFE_AGGREGATIONS or agg not in _SQL_AGG:
        raise Ineligible(f"aggregation '{agg}' is not grain-safe")

    sort_col = config.get("sort_col") or None
    if sort_col and sort_col != dim:
        raise Ineligible("sort_col on a non-dimension column")

    where, params = [], []
    # Predicates translated elsewhere -- an RLS rule, a report filter
    # expression -- arrive as (sql, {name: value}) with `:rN` placeholders,
    # the shape `sql_expr` emits for Postgres. DuckDB binds positionally, so
    # each name is replaced by `?` in the order it appears and its value
    # appended in that same order. They go FIRST: pandas applies RLS, then
    # the filter expression, then the widget's own filters, and `total` is
    # counted after all of them.
    for frag_sql, frag_params in extra_where or []:
        if not frag_sql:
            continue
        positional_sql = _NAMED_PARAM.sub(
            lambda m: params.append(frag_params[m.group(1)]) or "?", frag_sql)
        where.append(f"({positional_sql})")
    for f in config.get("filters") or []:
        op = f.get("op")
        col = f.get("column")
        if op not in _SUPPORTED_FILTER_OPS:
            raise Ineligible(f"filter op '{op}'")
        if col not in columns:
            raise Ineligible(f"filter column '{col}' is not a real column")
        ident = _quote_ident(col)
        if op == "in":
            values = f.get("value")
            if not isinstance(values, (list, tuple)) or not values:
                raise Ineligible("'in' filter without a list of values")
            where.append(f"{ident} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        else:
            where.append(f"{ident} {_SQL_COMPARISON[op]} ?")
            params.append(f.get("value"))

    dim_i, meas_i = _quote_ident(dim), _quote_ident(meas)

    granularity = str(config.get("dimension_granularity") or "").lower()
    probe_sql = None
    if granularity:
        if granularity not in _GRANULARITY_SQL:
            raise Ineligible(f"granularity {granularity!r}")
        ts = f"TRY_CAST({dim_i} AS TIMESTAMP)"
        dim_expr = _GRANULARITY_SQL[granularity].format(ts=ts)
    else:
        dim_expr = dim_i

    # `total` is counted here -- after the user's filters, before the null drop.
    filtered_where = " AND ".join(where) if where else "TRUE"
    count_sql = f"SELECT COUNT(*) FROM {source} WHERE {filtered_where}"
    if granularity:
        probe_sql = (f"SELECT COUNT({dim_i}) - COUNT({ts}), COUNT({ts}) "
                     f"FROM {source} WHERE {filtered_where}")

    # pandas `groupby` DROPS rows whose key is NaN; SQL `GROUP BY` keeps NULL as
    # its own group. Without this predicate a null-keyed group would appear as an
    # extra bar that the pandas path never produced -- a visible, wrong result.
    # Verified 2026-08-28 against a fixture with nulls in both columns.
    where.append(f"{dim_expr} IS NOT NULL")

    template = _SQL_AGG[agg]
    agg_expr = (template.format(col=meas_i) if "{col}" in template
                else f"{template}({meas_i})")

    sql = (
        f"SELECT {dim_expr} AS __dim__, {agg_expr} AS __value__ "
        f"FROM {source} "
        f"WHERE {' AND '.join(where)} "
        f"GROUP BY {dim_expr}"
    )
    return DuckPlan(sql=sql, count_sql=count_sql, params=params,
                    probe_sql=probe_sql, dimension=dim, measure=meas)


def _source_expr(file_path: str) -> str:
    """The DuckDB scan expression for this dataset's backing file.

    Prefers the parquet sidecar `frame_cache` maintains next to a CSV: it is
    written from a RE-READ of the CSV (never from a caller's frame), so its
    dtypes are what a fresh `pd.read_csv` yields -- which is exactly the parity
    this path needs -- and reading it avoids re-parsing the CSV per query.
    Falls back to the CSV when the sidecar is missing or older than its source,
    matching `frame_cache._parse`'s own staleness rule.
    """
    from .frame_cache import sidecar_path

    path = str(file_path)
    duck = path.replace("\\", "/")
    if path.lower().endswith(".csv"):
        pq = str(sidecar_path(path))
        try:
            if os.stat(pq).st_mtime_ns >= os.stat(path).st_mtime_ns:
                return f"read_parquet('{pq.replace(chr(92), '/')}')"
        except OSError:
            pass
        return f"read_csv_auto('{duck}')"
    if path.lower().endswith(".parquet"):
        return f"read_parquet('{duck}')"
    raise Ineligible("source file is neither CSV nor parquet")


def aggregate(file_path: str, config: dict, columns: list[str],
              extra_where: list[tuple[str, dict]] | None = None) -> pd.DataFrame:
    """Return a small pre-aggregated frame, or raise `Ineligible`.

    The frame has the ORIGINAL dimension and measure column names, so the shaper
    treats it exactly like the full frame it would otherwise have grouped -- one
    row per group, which is why only grain-safe aggregations may take this path.
    """
    import duckdb

    source = _source_expr(file_path)
    p = plan(config, columns, source, extra_where=extra_where)

    con = duckdb.connect()
    try:
        con.execute(f"SET threads TO {max(1, settings.widget_duckdb_threads)}")
        if p.probe_sql:
            unparsable, parsed = con.execute(p.probe_sql, p.params).fetchone()
            if unparsable:
                raise Ineligible(f"{unparsable} date values TRY_CAST cannot read")
            if not parsed:
                raise Ineligible("no date values to bucket")
        frame = con.execute(p.sql, p.params).fetch_df()
        # `total` in a shaped result means SOURCE rows, not groups -- the shaper
        # derives it from len(df), which for a pre-aggregated frame would be the
        # group count instead. Ask for the real number so the two engines agree.
        total = con.execute(p.count_sql, p.params).fetchone()[0]
    finally:
        con.close()

    frame = frame.rename(columns={"__dim__": p.dimension, "__value__": p.measure})
    frame.attrs["source_row_count"] = int(total)
    return frame


def try_aggregate(file_path: str, config: dict, columns: list[str],
                  extra_where: list[tuple[str, dict]] | None = None):
    """`aggregate` with every failure turned into None.

    Returns (frame, reason). A None frame means "use pandas"; `reason` says why,
    for the query log. An unexpected DuckDB error is logged and declined rather
    than raised: the whole value of this module is that its worst case is the
    behaviour that existed before it.
    """
    if not is_enabled():
        return None, "disabled"
    try:
        return aggregate(file_path, config, columns, extra_where=extra_where), None
    except Ineligible as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001 -- deliberate: never fail a render
        logger.warning("DuckDB pushdown failed, falling back to pandas: %s", e)
        return None, f"error: {type(e).__name__}"
