"""A crosstab with hierarchies on its rows and columns (hierarchy plan, step 3,
2026-10-10): Country ▸ City down the side, Year ▸ Quarter across the top, each
header opening one level at a time, a subtotal for every group and grand
totals.

The value of every group at every level is computed from that group's OWN
rows -- one grouping per (row depth, column depth) -- so a subtotal of an
average is the average of the group, never a sum or an average of averages.
The reader opens and closes branches without another request: everything to
the configured depth is in one answer, up to the caps below (then it says it
was cut).

Levels are `{column, granularity}` (widget_data._levels_of); a date level is
its bucket label ("2025-Q1"), the same label the slicer tree and the "paths"
filter use, so a click here filters the rest of the page exactly.
"""
from __future__ import annotations

import json

import pandas as pd

#: Most row paths (deepest level) and column paths listed; past them, cut and say so.
MAX_ROW_PATHS = 2000
MAX_COLUMN_PATHS = 120

#: Named aggregations pandas runs natively (fast); others go through _agg_series.
_NATIVE = {"sum": "sum", "avg": "mean", "mean": "mean", "average": "mean", "min": "min", "max": "max",
           "median": "median", "count": "count", "countd": "nunique", "distinct": "nunique"}


def _tree(frame: pd.DataFrame, keys: list[str], cap: int) -> tuple[list[dict], bool]:
    """Nested {value, children} from the distinct combinations, sorted."""
    if not keys:
        return [], False
    combos = frame[keys].drop_duplicates().sort_values(keys)
    cut = len(combos) > cap
    combos = combos.iloc[:cap]
    root: list[dict] = []
    index: dict = {}
    for row in combos.itertuples(index=False):
        siblings, prefix = root, ()
        for v in row:
            prefix = prefix + (v,)
            node = index.get(prefix)
            if node is None:
                node = {"value": v, "children": []}
                index[prefix] = node
                siblings.append(node)
            siblings = node["children"]
    return root, cut


def shape_hier_pivot(df: pd.DataFrame, config: dict) -> dict:
    from .widget_data import _agg_series, _apply_filters, _level_labels, _levels_of, _safe

    row_levels = _levels_of(config.get("hierarchy_rows"))
    col_levels = _levels_of(config.get("hierarchy_columns"))
    if not row_levels:
        return {"type": "error", "code": "missing_field", "message": "Choose a hierarchy for Rows",
                "rows": [], "total": 0}
    for lv in row_levels + col_levels:
        if lv["column"] not in df.columns:
            return {"type": "error", "code": "unknown_field", "field": "dimension",
                    "message": f"'{lv['column']}' is not a column on this dataset", "rows": [], "total": 0}
    meas = config.get("measure") or None
    if meas and meas not in df.columns:
        return {"type": "error", "code": "unknown_field", "field": "measure",
                "message": f"'{meas}' is not a column on this dataset", "rows": [], "total": 0}
    agg = str(config.get("aggregation") or ("sum" if meas else "count")).lower()

    scanned = len(df)
    df = _apply_filters(df, config.get("filters") or [])
    labels = _level_labels(df, row_levels + col_levels)
    rkeys = [f"l{i}" for i in range(len(row_levels))]
    ckeys = [f"l{len(row_levels) + i}" for i in range(len(col_levels))]
    frame = labels.copy()
    frame["__v"] = df[meas] if meas else 1
    complete = frame.dropna(subset=rkeys + ckeys)
    missing = len(frame) - len(complete)

    # Too many paths at the deepest level (a date chain down to Day across the
    # top): drop levels from the bottom until it fits, rather than cutting off
    # whole years. Only a single level that is still too many gets cut.
    def fit(keys: list[str], levels: list[dict], cap: int) -> tuple[list[str], list[dict], list[str]]:
        dropped: list[str] = []
        while len(keys) > 1 and len(complete[keys].drop_duplicates()) > cap:
            dropped.insert(0, levels[len(keys) - 1]["column"] + (f" ({levels[len(keys) - 1]['granularity']})"
                                                               if levels[len(keys) - 1].get("granularity") else ""))
            keys = keys[:-1]
        return keys, levels[:len(keys)], dropped
    rkeys, row_levels, rows_dropped = fit(rkeys, row_levels, MAX_ROW_PATHS)
    ckeys, col_levels, cols_dropped = fit(ckeys, col_levels, MAX_COLUMN_PATHS)

    row_tree, rows_cut = _tree(complete, rkeys, MAX_ROW_PATHS)
    col_tree, cols_cut = _tree(complete, ckeys, MAX_COLUMN_PATHS)

    def value_of(grouped) -> pd.Series:
        """The measure per group; no measure counts rows."""
        if not meas:
            return grouped.size()
        native = _NATIVE.get(agg)
        return grouped["__v"].agg(native) if native else grouped["__v"].apply(lambda s: _agg_series(s, agg))

    cells: list[list] = []
    for i in range(len(rkeys) + 1):
        for j in range(len(ckeys) + 1):
            keys = rkeys[:i] + ckeys[:j]
            if not keys:
                if meas:
                    native = _NATIVE.get(agg)
                    v = complete["__v"].agg(native) if native else _agg_series(complete["__v"], agg)
                else:
                    v = len(complete)
                cells.append([[], [], None if pd.isna(v) else _safe(v)])
                continue
            grouped = complete.groupby(keys, sort=False)
            series = value_of(grouped)
            for k, v in series.items():
                k = k if isinstance(k, tuple) else (k,)
                cells.append([list(k[:i]), list(k[i:]), None if v is None or pd.isna(v) else _safe(v)])

    return {
        "type": "hier_pivot",
        "row_levels": row_levels,
        "column_levels": col_levels,
        "measure": meas or "count",
        "aggregation": agg if meas else "count",
        "row_tree": row_tree,
        "column_tree": col_tree,
        "cells": cells,
        "totals_position": config.get("totals_position") or "after",
        "rows": [],
        "total": int(len(complete)),
        "rows_scanned": scanned,
        "missing_category": {"rows": int(missing)},
        "truncation": {"applied": rows_cut or cols_cut, "rows": rows_cut, "columns": cols_cut,
                       "reason": "limit", "unit": "paths"},
        # Levels left out because they had too many values to show.
        "levels_dropped": {"rows": rows_dropped, "columns": cols_dropped},
    }


def cell_key(row_path: list, col_path: list) -> str:
    """How the frontend looks a cell up (kept here so tests can use it)."""
    return json.dumps([row_path, col_path], ensure_ascii=False)
