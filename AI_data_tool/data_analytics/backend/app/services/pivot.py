"""A crosstab with several fields on Rows, on Columns, and several Measures --
the SAS VA crosstab: Continent > Country down the side, Product Line >
Product Category across the top, Quantity Ordered (and more) in the cells.

A crosstab or matrix with one field each way keeps its own shaper
(widget_data._shape_grid, with ranking, subtotals and totals). This one is
used only when the widget holds MORE: `rows_extra` (further row levels,
outermost first after `dimension`), `columns_extra` (after `dimension2`) or
`extra_measures` (after `measure`).

Every engine reaches it: DuckDB's pushdown declines keys it does not know
(duck_agg._SUPPORTED_KEYS is an allow-list), and a DirectQuery source fetches
the rows for these keys (direct_query._ROW_LEVEL_KEYS) and shapes them here.
"""
from __future__ import annotations

import pandas as pd

#: The widget types drawn as a crosstab. MIRRORS `PIVOT_WIDGETS` in
#: frontend/src/types/report.ts (pinned by tests/test_frontend_constant_mirrors.py).
PIVOT_WIDGETS = frozenset({"crosstab", "matrix"})

#: The config keys that make a crosstab multi-level.
PIVOT_EXTRA_KEYS = ("rows_extra", "columns_extra", "extra_measures")

#: Row groups returned before the rest are disclosed as truncated.
DEFAULT_ROW_LIMIT = 10000


def _names(v) -> list[str]:
    return [x for x in (v if isinstance(v, list) else []) if isinstance(x, str) and x]


def is_multilevel(widget_type: str, config: dict | None) -> bool:
    cfg = config or {}
    return widget_type in PIVOT_WIDGETS and any(_names(cfg.get(k)) for k in PIVOT_EXTRA_KEYS)


def fields_of(config: dict) -> tuple[list[str], list[str], list[str]]:
    """Rows, columns and measures, each outermost / first first, no repeats."""
    rows = list(dict.fromkeys(_names([config.get("dimension")]) + _names(config.get("rows_extra"))))
    cols = list(dict.fromkeys(_names([config.get("dimension2")]) + _names(config.get("columns_extra"))))
    meas = list(dict.fromkeys(_names([config.get("measure")]) + _names(config.get("extra_measures"))))
    return rows, cols, meas


def shape_pivot(df: pd.DataFrame, config: dict) -> dict:
    """The nested crosstab.

    - A row with a blank in any Rows or Columns field is in no cell; how many
      is disclosed as `missing_category`, as the one-level crosstab does.
    - Each cell is its measure's aggregation over the cell's own rows, with
      the same named aggregations every other shaper uses (`_agg_series`).
      No measure: the cells count rows.
    - Row groups and column groups are in ascending order of their labels,
      outer level first.
    - A defined measure (a formula over the widget's grain) is not evaluated
      per cell here yet; it is refused by name rather than read as a column.
    """
    from .widget_data import _agg_series, _apply_filters, _safe

    rows, cols, meas = fields_of(config)
    if not rows:
        return {"type": "error", "code": "missing_field", "message": "Choose at least one field for Rows",
                "rows": [], "total": 0}
    defined = {m.get("name") for m in (config.get("measure_defs") or []) if isinstance(m, dict)}
    for m in meas:
        if m not in df.columns:
            if m in defined:
                return {"type": "error", "code": "unsupported",
                        "message": f"'{m}' is a defined measure; a crosstab with more than one field "
                                   "each way does not evaluate defined measures yet -- use its columns",
                        "rows": [], "total": 0}
            return {"type": "error", "code": "unknown_field", "field": "measure",
                    "message": f"'{m}' is not a column or measure on this dataset", "rows": [], "total": 0}
    for f in rows + cols:
        if f not in df.columns:
            return {"type": "error", "code": "unknown_field", "field": "dimension",
                    "message": f"'{f}' is not a column on this dataset", "rows": [], "total": 0}

    scanned = len(df)
    df = _apply_filters(df, config.get("filters") or [])
    keys = rows + cols
    complete = df.dropna(subset=keys)
    missing = len(df) - len(complete)
    agg = str(config.get("aggregation") or "sum")

    if complete.empty:
        return {"type": "empty", "rows": [], "total": 0, "rows_scanned": scanned,
                "missing_category": {"rows": int(missing)}}

    grouped = complete.groupby(keys, sort=True, dropna=True)
    series: list[pd.Series] = []
    if meas:
        for m in meas:
            series.append(grouped[m].apply(lambda s, a=agg: _agg_series(s, a)))
    else:
        series.append(grouped.size())
    cells: dict[tuple, list] = {}
    for i, s in enumerate(series):
        for k, v in s.items():
            k = k if isinstance(k, tuple) else (k,)
            cells.setdefault(k, [None] * len(series))[i] = None if v is None else _safe(v)

    def label(v):
        return v.item() if hasattr(v, "item") else v

    row_keys = sorted({k[:len(rows)] for k in cells}, key=lambda t: tuple(str(x) for x in t))
    col_keys = sorted({k[len(rows):] for k in cells}, key=lambda t: tuple(str(x) for x in t)) or [()]
    limit = int(config.get("limit") or DEFAULT_ROW_LIMIT)
    shown = row_keys[:limit]
    out_rows = []
    for rk in shown:
        values = []
        for ck in col_keys:
            got = cells.get(rk + ck)
            values.extend(got if got is not None else [None] * len(series))
        out_rows.append({"keys": [label(x) for x in rk], "values": values})

    return {
        "type": "pivot",
        "row_fields": rows,
        "column_fields": cols,
        "measures": meas or ["count"],
        "aggregation": agg if meas else "count",
        "column_keys": [[label(x) for x in ck] for ck in col_keys],
        "rows": out_rows,
        "total": len(row_keys),
        "rows_scanned": scanned,
        "missing_category": {"rows": int(missing), "columns": keys},
        "truncation": {"applied": len(row_keys) > limit, "shown": len(shown), "of": len(row_keys),
                       "limit": limit, "reason": "limit", "unit": "groups"},
    }
