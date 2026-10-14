"""Auto-bin: a chart with too many values is grouped into buckets on the SERVER.

Measured on dashboard 213 (2026-09-29): a donut by `price` drew 5,670 slices,
a scatter 5,670 points, and every chart may ship up to FULL_DATA_LIMIT (10,000)
groups. The browser then draws thousands of SVG marks, which is what made big
dashboards slow to load and slow to filter. Nobody can read 5,670 slices.

When the dimension has more distinct values than the chart can show (its
*target*), the values are grouped:

  * a date column  -> the finest grain (hour, day, week, month, quarter, year)
                      whose bucket count fits the target;
  * a number column -> equal-width ranges with a "nice" width (1, 2, 2.5, 5 x 10^k).

Text columns are left alone here (they take Top N + "Other", a separate step).

Zoom ("smart slider"): the reader drags the chart's range slider; the page
asks again with `bin_range` = the window in the RAW column's units. Only rows
inside the window are read, and the grain is chosen again for the narrower
span -- so zooming in shows finer buckets, down to the raw values.

What never changes: every row is still counted. Grouping merges marks; it does
not drop data, so totals are the same with or without binning. The result says
what was done (`binning`), and each row carries `bin_start`/`bin_end` so a
click or a zoom can be turned back into a range on the real column.

Config keys (all optional; stripped before any engine sees the config):
  auto_bin    False switches binning off for this widget. Default: on.
  bin_target  the most buckets the chart should draw (clamped 2..2000).
  bin_range   {"start": ..., "end": ...}: the zoom window, end exclusive.

The author's own choice always wins: an explicit `dimension_granularity`
(other than "auto"), a hierarchy, a crosstab or a Top N is never re-binned.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

#: The column the bucket is computed into on engines that need a real column
#: (the DirectQuery SQL layer, the pandas frame). Never shown: the result's
#: `dimension` is put back to the reader's column.
BIN_COL = "__bin__"

CONFIG_KEYS = ("auto_bin", "bin_target", "bin_range", "top_n")

#: Text columns: how many values a chart shows before the rest become one
#: "All Other" slice. Only charts where a category is a mark people compare --
#: a line over 30,000 product ids is not a chart to rescue this way.
TOP_N_DEFAULTS: dict[str, int] = {
    "pie": 10, "donut": 10, "funnel": 10, "bar": 20, "dot_plot": 20, "treemap": 30,
}
#: The choices the chart's chip offers (and the only values accepted).
TOP_N_CHOICES = (10, 20, 50)
OTHER_LABEL = "All Other"   # the shaper's own Top-N residual label

#: Buckets per chart type when the author set nothing. Chosen for readability,
#: not for speed: a line stays a line at 150 points, a bar chart past ~50 bars
#: has hairline bars, and a donut past a dozen slices is unreadable.
DEFAULT_TARGETS: dict[str, int] = {
    "line": 150, "area": 150, "step": 150,
    "bar": 50, "dot_plot": 60, "treemap": 50, "funnel": 20,
    "pie": 12, "donut": 12,
    # One point per x value already (shape_series groups a scatter by its x),
    # so 5,670 distinct prices were 5,670 points; 500 ranges draw the same cloud.
    "scatter": 500,
}

#: Date grains, finest first, with their length in days (approximate is fine:
#: this only chooses a grain, it never computes a bucket).
_GRAINS: list[tuple[str, float]] = [
    ("hour", 1 / 24), ("day", 1.0), ("week", 7.0), ("month", 30.44),
    ("quarter", 91.31), ("year", 365.25),
]
_GRAIN_ORDER = [g for g, _ in _GRAINS]


@dataclass
class Stats:
    lo: object          # datetime | float | None
    hi: object
    distinct: int


@dataclass
class BinPlan:
    column: str
    kind: str                     # "date" | "number"
    target: int
    distinct: int
    grain: str | None = None      # date: chosen grain; None = raw values fit
    width: float | None = None    # number: bucket width; None = raw values fit
    origin: float | None = None
    window: tuple | None = None   # (start, end) the reader zoomed to
    full: tuple | None = None     # (lo, hi) of the data in the window
    extra_filters: list = field(default_factory=list)
    #: text: how many values are shown before the rest become "All Other".
    top_n: int | None = None
    #: A scatter plots `x` on a numeric axis: each range sits at its midpoint.
    point_x: bool = False
    #: False for a grain the AUTHOR chose, pushed down only for speed: the
    #: result then carries no `binning` (nothing was auto-grouped, and the
    #: page must not offer a zoom that would override the author's grain).
    announce: bool = True

    @property
    def grouped(self) -> bool:
        return self.grain is not None or self.width is not None or self.top_n is not None


# ── eligibility ────────────────────────────────────────────────────────────

def column_kind(dtype: str | None) -> str | None:
    d = (dtype or "").lower()
    if d in ("datetime", "date", "timestamp"):
        return "date"
    if d in ("numeric", "number", "integer", "float", "int", "decimal"):
        return "number"
    if d in ("categorical", "text", "string", "object", "category", "boolean", "bool"):
        return "text"
    return None


def top_n_of(config: dict, widget_type: str) -> int:
    try:
        n = int(config.get("top_n") or 0)
    except (TypeError, ValueError):
        n = 0
    return n if n in TOP_N_CHOICES else TOP_N_DEFAULTS.get(widget_type, 20)


def wants_bins(config: dict, widget_type: str, kind: str | None = None) -> bool:
    if kind == "text" and widget_type not in TOP_N_DEFAULTS:
        return False
    if widget_type == "scatter" and kind != "number":
        return False
    if widget_type not in DEFAULT_TARGETS:
        return False
    if config.get("auto_bin") is False:
        return False
    if not config.get("dimension") or config.get("dimension2"):
        return False
    if config.get("dimension_levels") or config.get("rank") or config.get("dimension_bin"):
        return False
    g = config.get("dimension_granularity")
    if g and g != "auto":
        return False
    return True


def target_of(config: dict, widget_type: str) -> int:
    try:
        t = int(config.get("bin_target") or DEFAULT_TARGETS.get(widget_type, 50))
    except (TypeError, ValueError):
        t = DEFAULT_TARGETS.get(widget_type, 50)
    return max(2, min(t, 2000))


def strip_keys(config: dict) -> dict:
    """The config without auto-bin's own keys: every engine allowlists what it
    understands (DuckDB declines an unknown key), so these never reach one."""
    out = {k: v for k, v in config.items() if k not in CONFIG_KEYS}
    if out.get("dimension_granularity") == "auto":
        out.pop("dimension_granularity")
    return out


# ── the zoom window ────────────────────────────────────────────────────────

def _to_dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    try:
        ts = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts.to_pydatetime()


def _to_num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _bound(d: datetime) -> str:
    if d.hour == d.minute == d.second == d.microsecond == 0:
        return d.strftime("%Y-%m-%d")
    return d.isoformat(sep=" ")


def parse_window(config: dict, kind: str) -> tuple | None:
    r = config.get("bin_range")
    if not isinstance(r, dict):
        return None
    conv = _to_dt if kind == "date" else _to_num
    a, b = conv(r.get("start")), conv(r.get("end"))
    if a is None or b is None or not a < b:
        return None
    return (a, b)


def window_filters(column: str, kind: str, window: tuple | None) -> list[dict]:
    """The zoom window as ordinary filters every engine already runs:
    start inclusive, end exclusive (buckets are [start, end))."""
    if not window:
        return []
    a, b = window
    if kind == "date":
        # Midnight as a bare date: an uploaded CSV's date column is often
        # TEXT, compared as strings, and "2023-03-01" < "2023-03-01 00:00:00".
        a, b = _bound(a), _bound(b)
    return [{"column": column, "op": "gte", "value": a},
            {"column": column, "op": "lt", "value": b}]


def same_column_bounds(config: dict, column: str, kind: str) -> list[dict]:
    """Filters on the binned column itself that narrow its span (a date range
    the reader picked, a cross-filter). The stats query honours these so the
    grain fits what is actually on screen; filters on OTHER columns narrow the
    counts, not the span, and are left to the chart's own query."""
    out = []
    for f in config.get("filters") or []:
        if isinstance(f, dict) and f.get("column") == column \
                and f.get("op") in ("gt", "gte", "lt", "lte") and not f.get("granularity"):
            out.append(f)
    return out


# ── choosing the buckets ───────────────────────────────────────────────────

def nice_width(raw: float) -> float:
    """The smallest 'nice' width (1, 2, 2.5, 5 x 10^k) at least `raw`."""
    if raw <= 0 or not math.isfinite(raw):
        return 1.0
    exp = math.floor(math.log10(raw))
    base = 10 ** exp
    for m in (1, 2, 2.5, 5, 10):
        w = m * base
        if w >= raw * (1 - 1e-12):
            return float(w)
    return float(10 * base)


def choose_grain(lo: datetime, hi: datetime, target: int) -> str:
    span_days = max((hi - lo).total_seconds() / 86400.0, 0.0)
    for grain, days in _GRAINS:
        # +1: a span of 30 days touches 31 day buckets.
        if span_days / days + 1 <= target:
            return grain
    return "year"


def plan_bins(config: dict, widget_type: str, kind: str, stats: Stats,
              window: tuple | None = None) -> BinPlan:
    column = config["dimension"]
    if kind == "text":
        n = top_n_of(config, widget_type)
        plan = BinPlan(column=column, kind="text", target=n, distinct=int(stats.distinct or 0))
        # One more value than N fits as itself: an "All Other" of one value
        # would hide a name to save nothing.
        if plan.distinct > n + 1:
            plan.top_n = n
        return plan
    target = target_of(config, widget_type)
    plan = BinPlan(column=column, kind=kind, target=target, distinct=int(stats.distinct or 0),
                   window=window, full=(stats.lo, stats.hi) if stats.lo is not None else None,
                   extra_filters=window_filters(column, kind, window),
                   point_x=widget_type == "scatter")
    if stats.lo is None or stats.hi is None or plan.distinct <= target:
        return plan                      # the raw values already fit
    if kind == "date":
        plan.grain = choose_grain(stats.lo, stats.hi, target)
    else:
        lo, hi = float(stats.lo), float(stats.hi)
        width = nice_width((hi - lo) / target) if hi > lo else 1.0
        # A nice width can round up so far that the ranges no longer fit
        # (e.g. 0..1000 into 3): widen until they do.
        while math.floor(hi / width) - math.floor(lo / width) + 1 > target:
            width = nice_width(width * 1.0001)
        plan.width = width
        plan.origin = math.floor(lo / width) * width
    return plan


# ── stats, cached ──────────────────────────────────────────────────────────

_STATS_TTL_S = 600
_stats_cache: dict[str, tuple[float, Stats]] = {}
_stats_lock = threading.Lock()


def stats_cached(key: str, compute) -> Stats:
    now = time.monotonic()
    with _stats_lock:
        hit = _stats_cache.get(key)
        if hit and now - hit[0] < _STATS_TTL_S:
            return hit[1]
    s = compute()
    with _stats_lock:
        if len(_stats_cache) > 2000:
            _stats_cache.clear()
        _stats_cache[key] = (now, s)
    return s


def clear_stats_cache() -> None:
    with _stats_lock:
        _stats_cache.clear()


def _stats_from_series(s: pd.Series, kind: str) -> Stats:
    if kind == "text":
        return Stats(None, None, int(s.dropna().nunique()))
    if kind == "date":
        s = s if pd.api.types.is_datetime64_any_dtype(s) else pd.to_datetime(s, errors="coerce")
        if getattr(s.dt, "tz", None) is not None:
            s = s.dt.tz_convert(None)
    else:
        s = pd.to_numeric(s, errors="coerce")
    s = s.dropna()
    if s.empty:
        return Stats(None, None, 0)
    lo, hi = s.min(), s.max()
    if kind == "date":
        lo, hi = pd.Timestamp(lo).to_pydatetime(), pd.Timestamp(hi).to_pydatetime()
    else:
        lo, hi = float(lo), float(hi)
    return Stats(lo, hi, int(s.nunique()))


def frame_stats(df: pd.DataFrame, column: str, kind: str, filters: list[dict]) -> Stats:
    from .widget_data import _apply_filters
    if column not in df.columns:
        return Stats(None, None, 0)
    return _stats_from_series(_apply_filters(df, filters)[column], kind)


def import_stats(file_path: str, column: str, kind: str, filters: list[dict]) -> Stats:
    """Min, max and distinct count of one column of an uploaded file.

    DuckDB first -- a scan of one column, without materialising the frame the
    pandas path would (that is the memory the DuckDB pushdown exists to save).
    Any DuckDB trouble falls back to the frame: slower, never wrong."""
    try:
        import duckdb
        from .duck_agg import _quote_ident, _source_expr
        col = _quote_ident(column)
        val = (f"TRY_CAST({col} AS TIMESTAMP)" if kind == "date"
               else f"TRY_CAST({col} AS DOUBLE)" if kind == "number" else col)
        where, params = [], []
        ops = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        for f in (filters if kind != "text" else []):
            v = _to_dt(f.get("value")) if kind == "date" else _to_num(f.get("value"))
            if v is None or f.get("op") not in ops:
                continue
            where.append(f"{val} {ops[f['op']]} ?")
            params.append(v)
        sql = (f"SELECT MIN({val}), MAX({val}), COUNT(DISTINCT {val}) "
               f"FROM {_source_expr(file_path)}"
               + (f" WHERE {' AND '.join(where)}" if where else ""))
        con = duckdb.connect()
        try:
            lo, hi, n = con.execute(sql, params).fetchone()
        finally:
            con.close()
        if kind == "number":
            lo = float(lo) if lo is not None else None
            hi = float(hi) if hi is not None else None
        if kind == "text":
            lo = hi = None
        return Stats(lo, hi, int(n or 0))
    except Exception:  # noqa: BLE001 -- fall back to the frame
        from .widget_data import load_file
        return frame_stats(load_file(file_path), column, kind, filters)


def dq_stats(source_cfg: dict, dataset, column: str, kind: str, filters: list[dict],
             rls_filter_expr: str | None) -> Stats:
    """The same three numbers from a live source: one small aggregate query."""
    from sqlalchemy import text
    from .direct_query import _base_query_sql, _build_where, _quote, _translate_rls, get_engine
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)
    base = _base_query_sql(dataset, rls_where)
    col = _quote(column)
    where, params = _build_where([f for f in filters if f.get("op") in ("gt", "gte", "lt", "lte")])
    sql = (f"SELECT MIN({col}), MAX({col}), COUNT(DISTINCT {col}) FROM ({base}) AS stat_src"
           + (f" WHERE {where}" if where else ""))
    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        lo, hi, n = conn.execute(text(sql), {**(rls_params or {}), **params}).one()
    if kind == "date":
        lo, hi = _to_dt(lo), _to_dt(hi)
    elif kind == "number":
        lo, hi = _to_num(lo), _to_num(hi)
    else:
        lo = hi = None
    return Stats(lo, hi, int(n or 0))


# ── bucket SQL for live sources ────────────────────────────────────────────

def _num_lit(x: float) -> str:
    return repr(float(x))


def bucket_sql(dialect: str, column_sql: str, plan: BinPlan) -> str | None:
    """The bucket START for one row, as SQL. Dates truncate to the grain's
    first instant (labelled in Python afterwards, so every engine produces the
    import path's exact labels); numbers floor to the range's lower edge.
    None when this dialect has no expression here (the caller falls back)."""
    # A live table often stores dates and numbers as TEXT (a CSV loaded
    # as-is): dashboard 213's delivery date is text in Postgres, and
    # date_trunc(text) does not exist there. Cast where the dialect is strict;
    # MySQL and SQLite date functions read ISO text as it is.
    if plan.kind == "number":
        w, o = _num_lit(plan.width), _num_lit(plan.origin)
        c = f"CAST({column_sql} AS DOUBLE PRECISION)" if dialect == "postgresql" else column_sql
        return f"(FLOOR(({c} - {o}) / {w}) * {w} + {o})"
    g = plan.grain
    c = column_sql
    if dialect == "postgresql":
        return f"date_trunc('{g}', CAST({c} AS timestamp))"
    if dialect == "oracle":
        fmt = {"hour": "HH24", "day": "DD", "week": "IW", "month": "MM", "quarter": "Q", "year": "YYYY"}[g]
        return f"TRUNC({c}, '{fmt}')"
    if dialect == "clickhouse":
        fn = {"hour": "toStartOfHour", "day": "toStartOfDay", "week": "toMonday",
              "month": "toStartOfMonth", "quarter": "toStartOfQuarter", "year": "toStartOfYear"}[g]
        return f"{fn}(toDateTime({c}))"
    if dialect == "mysql":
        return {
            "hour": f"DATE_FORMAT({c}, '%Y-%m-%d %H:00:00')",
            "day": f"DATE({c})",
            "week": f"DATE_SUB(DATE({c}), INTERVAL WEEKDAY({c}) DAY)",
            "month": f"DATE_FORMAT({c}, '%Y-%m-01')",
            "quarter": f"MAKEDATE(YEAR({c}), 1) + INTERVAL (QUARTER({c}) - 1) QUARTER",
            "year": f"DATE_FORMAT({c}, '%Y-01-01')",
        }[g]
    if dialect == "sqlserver":
        c = f"CAST({c} AS datetime2)"
        if g == "week":
            return f"DATEADD(day, -((DATEPART(weekday, {c}) + @@DATEFIRST - 2) % 7), CAST({c} AS date))"
        part = {"hour": "hour", "day": "day", "month": "month", "quarter": "quarter", "year": "year"}[g]
        return f"DATEADD({part}, DATEDIFF({part}, 0, {c}), 0)"
    if dialect == "sqlite":
        return {
            "hour": f"strftime('%Y-%m-%d %H:00:00', {c})",
            "day": f"date({c})",
            "week": f"date({c}, '-' || ((CAST(strftime('%w', {c}) AS INTEGER) + 6) % 7) || ' days')",
            "month": f"strftime('%Y-%m-01', {c})",
            "quarter": (f"printf('%s-%02d-01', strftime('%Y', {c}), "
                        f"((CAST(strftime('%m', {c}) AS INTEGER) - 1) / 3) * 3 + 1)"),
            "year": f"strftime('%Y-01-01', {c})",
        }[g]
    return None


# ── labels and ranges for the result ───────────────────────────────────────

def grain_start(v, grain: str) -> datetime | None:
    """The first instant of the bucket a value (or an import-path label such
    as "2024-Q1", "2024-W05", "2024") belongs to."""
    if isinstance(v, str):
        s = v.strip()
        try:
            if grain == "year" and len(s) == 4:
                return datetime(int(s), 1, 1)
            if grain == "quarter" and "-Q" in s:
                y, q = s.split("-Q")
                return datetime(int(y), 3 * (int(q) - 1) + 1, 1)
            if grain == "week" and "-W" in s:
                y, w = s.split("-W")
                return datetime.combine(date.fromisocalendar(int(y), int(w), 1), datetime.min.time())
            if grain == "month" and len(s) == 7:
                return datetime(int(s[:4]), int(s[5:7]), 1)
        except (ValueError, TypeError):
            return None
    d = _to_dt(v)
    if d is None:
        return None
    if grain == "hour":
        return d.replace(minute=0, second=0, microsecond=0)
    d = d.replace(hour=0, minute=0, second=0, microsecond=0)
    if grain == "day":
        return d
    if grain == "week":
        return d - timedelta(days=d.weekday())
    if grain == "month":
        return d.replace(day=1)
    if grain == "quarter":
        return d.replace(month=3 * ((d.month - 1) // 3) + 1, day=1)
    return d.replace(month=1, day=1)


def grain_end(start: datetime, grain: str) -> datetime:
    if grain == "hour":
        return start + timedelta(hours=1)
    if grain == "day":
        return start + timedelta(days=1)
    if grain == "week":
        return start + timedelta(days=7)
    months = {"month": 1, "quarter": 3, "year": 12}[grain]
    m = start.month - 1 + months
    return start.replace(year=start.year + m // 12, month=m % 12 + 1)


def grain_label(start: datetime, grain: str) -> str:
    """The import path's label for this bucket (widget_data._dimension_granularity_label)."""
    if grain == "year":
        return str(start.year)
    if grain == "quarter":
        return f"{start.year}-Q{(start.month - 1) // 3 + 1}"
    if grain == "month":
        return start.strftime("%Y-%m")
    if grain == "week":
        y, w, _ = start.isocalendar()
        return f"{y}-W{w:02d}"
    if grain == "day":
        return start.strftime("%Y-%m-%d")
    return start.strftime("%Y-%m-%d %H:00")


def _fmt_num(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.6g}"


def number_label(lo: float, hi: float) -> str:
    return f"{_fmt_num(lo)} – {_fmt_num(hi)}"


def _iso(d) -> str | None:
    return d.isoformat(sep=" ") if isinstance(d, datetime) else None


def finish(result: dict, plan: BinPlan) -> dict:
    """Put the reader's column back, label the buckets, and say what was done."""
    if not isinstance(result, dict):
        return result
    if result.get("dimension") == BIN_COL:
        result["dimension"] = plan.column
    rows = result.get("rows")
    if plan.kind == "text" and plan.top_n and isinstance(rows, list):
        # Other is always last, whatever order the reader asked for; the
        # truncation note would say values were cut -- they were not, they
        # are inside Other.
        other = [r for r in rows if isinstance(r, dict) and r.get("name") == OTHER_LABEL]
        rest = [r for r in rows if not (isinstance(r, dict) and r.get("name") == OTHER_LABEL)]
        for r in other:
            r["other"] = True
        result["rows"] = rows = rest + other
        if isinstance(result.get("truncation"), dict):
            result["truncation"] = {**result["truncation"], "applied": False, "reason": "top_n"}
    elif plan.grouped and isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict) or r.get("name") is None:
                continue
            if plan.kind == "number":
                lo = _to_num(r["name"])
                if lo is None:
                    continue
                hi = lo + plan.width
                r["bin_start"], r["bin_end"] = lo, hi
                r["name"] = number_label(lo, hi)
                if plan.point_x:
                    r["x"] = lo + plan.width / 2
            else:
                start = grain_start(r["name"], plan.grain)
                if start is None:
                    continue
                r["bin_start"] = _iso(start)
                r["bin_end"] = _iso(grain_end(start, plan.grain))
                r["name"] = grain_label(start, plan.grain)
    if not plan.announce:
        return result
    # No min/max of the data here: for an uploaded file the stats that chose
    # the grain are read before row security, and the reader must learn
    # nothing about rows it may not see. The buckets themselves (built from
    # the secured rows) say where the data starts and ends.
    result["binning"] = {
        "column": plan.column,
        "kind": plan.kind,
        "grouped": plan.grouped,
        "grain": plan.grain,
        "width": plan.width,
        "top_n": plan.top_n,
        "top_n_choices": list(TOP_N_CHOICES) if plan.kind == "text" else None,
        "target": plan.target,
        "distinct": plan.distinct,
        "buckets": len(rows) if isinstance(rows, list) else None,
        "window": ([_iso(plan.window[0]), _iso(plan.window[1])] if plan.kind == "date"
                   else list(plan.window)) if plan.window else None,
        # What finer grain a zoom could reach; None at the raw values.
        "finest": plan.grain is None and plan.width is None and plan.top_n is None,
    }
    return result


def import_config(config: dict, plan: BinPlan) -> dict:
    """The config the import engines (DuckDB, pandas) run for this plan."""
    out = strip_keys(config)
    out["filters"] = list(out.get("filters") or []) + plan.extra_filters
    if plan.kind == "date" and plan.grain:
        out["dimension_granularity"] = plan.grain
    elif plan.kind == "number" and plan.width:
        out["dimension_bin"] = {"width": plan.width, "origin": plan.origin}
    elif plan.kind == "text" and plan.top_n:
        out["rank"] = {"mode": "top", "n": plan.top_n, "other": True}
        return out
    if plan.grouped and "sort_by" not in config:
        out["sort_by"], out["sort"] = "name", "asc"
    return out


def dq_config(config: dict, plan: BinPlan) -> dict:
    """The config a live source runs: grouped by the bucket column the SQL
    layer adds, filtered on the raw column."""
    out = strip_keys(config)
    out["filters"] = list(out.get("filters") or []) + plan.extra_filters
    if plan.grouped:
        out["dimension"] = BIN_COL
        if "sort_by" not in config:
            out["sort_by"], out["sort"] = "name", "asc"
    return out


# ── Top N + "All Other" on a live source ───────────────────────────────────

def dq_top_config(config: dict, plan: BinPlan) -> dict:
    """The N largest values, as an ordinary pushed-down GROUP BY ... LIMIT N.
    (The shaper's own `rank` would fetch every row to rank them in Python.)"""
    out = strip_keys(config)
    out["sort_by"], out["sort"], out["limit"] = "value", "desc", plan.top_n
    out.pop("sort_col", None)
    return out


def dq_other(source_cfg: dict, dataset, config: dict, shown: list, rls_filter_expr: str | None,
             dialect: str):
    """The "All Other" value: the chart's own aggregation over every row whose
    value is not one of the N shown -- one more small query at the source. An
    aggregate of the hidden groups' aggregates would be wrong for avg/min/max;
    this is the same number the shaper's rank computes from raw rows.
    Returns (value, rows) or None when this chart's aggregation has no SQL here."""
    from sqlalchemy import text
    from .direct_query import (_SUPPORTED_FILTER_OPS, _agg_sql, _base_query_sql, _build_where,
                               _finalize_for_dialect, _quote, _translate_rls, get_engine)
    filters = config.get("filters") or []
    if any(f.get("granularity") or f.get("op") not in _SUPPORTED_FILTER_OPS for f in filters):
        return None
    meas = config.get("measure") or None
    agg = (config.get("aggregation") or ("sum" if meas else "count")).lower()
    if not meas or agg == "count":
        value_sql = "COUNT(*)"
    elif agg in ("countd", "distinct"):
        value_sql = f"COUNT(DISTINCT {_quote(meas)})"
    else:
        try:
            value_sql = _agg_sql(agg, _quote(meas), dialect)
        except Exception:  # noqa: BLE001 -- percentiles on a dialect without them, pct, ...
            return None
    rls_where, rls_params = _translate_rls(dataset, rls_filter_expr)
    base = _base_query_sql(dataset, rls_where)
    where, params = _build_where(filters)
    dim = _quote(config["dimension"])
    clauses = ([where] if where else []) + [f"{dim} IS NOT NULL"]
    if shown:
        keys = [f"o{i}" for i in range(len(shown))]
        params.update(dict(zip(keys, shown)))
        clauses.append(f"{dim} NOT IN ({', '.join(':' + k for k in keys)})")
    sql = _finalize_for_dialect(
        f"SELECT {value_sql}, COUNT(*) FROM ({base}) AS other_src WHERE {' AND '.join(clauses)}", dialect)
    engine = get_engine(source_cfg)
    with engine.connect() as conn:
        value, n = conn.execute(text(sql), {**(rls_params or {}), **params}).one()
    if not n:
        return None
    try:
        value = float(value) if value is not None else None
        if value is not None and value.is_integer() and value_sql.startswith("COUNT"):
            value = int(value)
    except (TypeError, ValueError):
        pass
    return value, int(n)
