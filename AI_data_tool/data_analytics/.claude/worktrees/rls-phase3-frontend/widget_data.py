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
"""

import pandas as pd
import numpy as np
from .analytics import load_file, detect_types


def _safe(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)): return None if np.isnan(v) else float(v)
    if isinstance(v, float) and (v != v): return None   # NaN check
    try:
        if pd.isna(v): return None
    except Exception:
        pass
    return v


# ── Aggregation function map ──────────────────────────────────────────────────
def _agg_series(series: pd.Series, agg: str) -> float | None:
    """Apply a named aggregation to a pandas Series."""
    s = series.dropna()
    if len(s) == 0:
        return None
    agg = agg.lower()
    if agg in ("sum",):                  return _safe(s.sum())
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
    return _safe(s.sum())   # default fallback


def _pandas_agg_fn(agg: str):
    """Return a pandas-compatible aggregation string or lambda."""
    agg = agg.lower()
    mapping = {
        "sum": "sum", "avg": "mean", "mean": "mean", "average": "mean",
        "min": "min", "minimum": "min", "max": "max", "maximum": "max",
        "median": "median", "count": "count", "frequency": "count",
        "countd": "nunique", "distinct": "nunique",
        "std": "std", "stdev": "std", "variance": "var", "var": "var",
        "range": lambda x: x.max() - x.min(),
        "p25": lambda x: x.quantile(.25),
        "p75": lambda x: x.quantile(.75),
        "p90": lambda x: x.quantile(.90),
        "p95": lambda x: x.quantile(.95),
    }
    return mapping.get(agg, "sum")


def _apply_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    for f in filters:
        col, op, val = f.get("column"), f.get("op"), f.get("value")
        if not col or col not in df.columns:
            continue
        try:
            if op == "eq":     df = df[df[col].astype(str) == str(val)] if df[col].dtype == object else df[df[col] == val]
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


def query_widget(df: pd.DataFrame, config: dict) -> dict:
    """
    Main query entry point.  config keys:
      dimension    str    – grouping / X-axis column
      dimension2   str    – second grouping (crosstab pivot)
      measure      str    – numeric column to aggregate
      aggregation  str    – aggregation name (see module docstring)
      filters      list   – [{column, op, value}, …]
      limit        int    – max result rows (default 50)
      sort         str    – 'asc' | 'desc'
      sort_by      str    – 'value' | 'name' (default 'value')
      columns      list   – explicit column list for table/list widgets
      running      str    – 'sum' | 'avg'  apply running metric to result
    """
    filters     = config.get("filters", [])
    dim         = config.get("dimension") or None
    dim2        = config.get("dimension2") or None
    meas        = config.get("measure") or None
    agg         = (config.get("aggregation") or "sum").lower()
    limit       = int(config.get("limit") or 50)
    sort        = (config.get("sort") or "desc").lower()
    sort_by     = (config.get("sort_by") or "value").lower()
    running     = (config.get("running") or "").lower()
    explicit_cols = config.get("columns") or []

    # 1. Apply filters
    df = _apply_filters(df, filters)
    if df.empty:
        return {"type": "empty", "rows": [], "total": 0}

    # 2. Raw table / list — no grouping requested
    if not dim and not meas:
        cols = [c for c in (explicit_cols or list(df.columns)) if c in df.columns]
        sub  = df[cols].head(limit)
        return {
            "type": "table",
            "columns": cols,
            "rows": [[_safe(v) for v in row] for row in sub.itertuples(index=False)],
            "total": len(df),
        }

    agg_fn = _pandas_agg_fn(agg)

    # 3. Crosstab (dim + dim2)
    if dim and dim2 and dim in df.columns and dim2 in df.columns:
        if meas and meas in df.columns:
            pivot = df.groupby([dim, dim2])[meas].agg(agg_fn).unstack(fill_value=0).reset_index()
        else:
            pivot = df.groupby([dim, dim2]).size().unstack(fill_value=0).reset_index()

        # Add row totals
        num_cols = [c for c in pivot.columns if c != dim]
        pivot["__total__"] = pivot[num_cols].sum(axis=1)
        col_names = [str(c) for c in pivot.columns]
        return {
            "type": "crosstab",
            "columns": col_names,
            "rows": [[_safe(v) for v in row] for row in pivot.itertuples(index=False)],
            "total": len(pivot),
        }

    # 4. Grouped series
    if dim and dim in df.columns:
        if meas and meas in df.columns:
            grouped = df.groupby(dim)[meas].agg(agg_fn).reset_index(name="value")
        elif agg in ("count", "frequency"):
            grouped = df.groupby(dim).size().reset_index(name="value")
        else:
            grouped = df.groupby(dim).size().reset_index(name="value")

        # Percentage aggregation
        if agg == "pct":
            total = grouped["value"].sum()
            grouped["value"] = (grouped["value"] / total * 100).round(2)

        # Sort
        if sort_by == "name":
            grouped = grouped.sort_values(dim, ascending=(sort == "asc"))
        else:
            grouped = grouped.sort_values("value", ascending=(sort == "asc"))
        grouped = grouped.head(limit)

        rows = [{"name": _safe(row[dim]), "value": _safe(row["value"])} for _, row in grouped.iterrows()]

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

        return {
            "type": "series",
            "dimension": dim,
            "measure": meas or "count",
            "aggregation": agg,
            "rows": rows,
            "total": len(df),
        }

    # 5. Single aggregate scalar (no dimension — KPI use case)
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


def get_widget_data(file_path: str, config: dict) -> dict:
    df = load_file(file_path)
    return query_widget(df, config)
