"""Groups of columns that hold one kind of score (persona test 2.4).

A rating form, a survey or an exam often stores one score per item as its own
column (`q1 … q20`, `s2_1 … s3_10`): the same small set of whole numbers on
the same scale. "The average score" then means the average over all of them,
and "the weakest item" means the column with the lowest average. Found from
the values alone -- never from the columns' names -- so it works in any
language and under any naming.

For each group the setup makes its row average as a calculated column (made
on the dataset only when a kept chart uses it) and tells the planner what the
group is.
"""
from __future__ import annotations

import pandas as pd

#: A score column: whole numbers with at least three (a yes/no column is not a
#: score) and at most this many different values...
GROUP_MAX_DISTINCT = 11
#: ...on a scale no wider than this (a 0-100 mark is a score, a year is not).
GROUP_MAX_VALUE = 100
#: At least this many columns make a group (two or three may be anything).
GROUP_MIN_COLUMNS = 4
#: Columns share a scale when each one's range covers this share of the
#: group's whole range.
GROUP_OVERLAP = 0.5
#: Items of one form move together (they rate the same person or thing): each
#: member correlates at least this much with the average of the others. A
#: code column on a similar range does not (measured: 0.48+ for twenty
#: evaluation items against about 0 for three code columns beside them).
GROUP_MIN_CORRELATION = 0.2


def _score_column(s: pd.Series) -> tuple[float, float] | None:
    if not pd.api.types.is_numeric_dtype(s) or s.dtype == bool:
        return None
    v = pd.to_numeric(s, errors="coerce").dropna()
    if len(v) < 2 or not bool((v == v.round()).all()):
        return None
    lo, hi = float(v.min()), float(v.max())
    if lo < 0 or hi > GROUP_MAX_VALUE or hi <= lo or v.nunique() > GROUP_MAX_DISTINCT or v.nunique() < 3:
        return None
    return lo, hi


def score_groups(df: pd.DataFrame, skip: set[str] | None = None) -> list[dict]:
    """[{"columns": [...], "low", "high", "name", "expression"}]: each group of
    four or more score columns on one scale, in the frame's column order."""
    ranges = {}
    for c in df.columns:
        if str(c) in (skip or set()):
            continue
        r = _score_column(df[c])
        if r:
            ranges[str(c)] = r
    groups: list[list[str]] = []
    for c, (lo, hi) in ranges.items():
        for g in groups:
            glo, ghi = min(ranges[x][0] for x in g), max(ranges[x][1] for x in g)
            span = max(ghi, hi) - min(glo, lo)
            covers = lambda a, b: (b - a) / span >= GROUP_OVERLAP if span else True
            if covers(lo, hi) and covers(glo, ghi):
                g.append(c)
                break
        else:
            groups.append([c])
    out = []
    for g in groups:
        g = _moving_together(df, g)
        if len(g) < GROUP_MIN_COLUMNS:
            continue
        name = f"average_of_{len(g)}_{g[0]}_to_{g[-1]}"
        if name in df.columns:
            continue
        out.append({"columns": g, "low": min(ranges[c][0] for c in g), "high": max(ranges[c][1] for c in g),
                    "name": name, "expression": "(" + " + ".join(g) + f") / {len(g)}", "dtype": "numeric",
                    "format": {"type": "number", "decimals": 2}})
    return out


def _moving_together(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """The members that correlate with the average of the others, dropping
    the weakest one at a time until every member does."""
    cols = list(cols)
    num = df[cols].apply(pd.to_numeric, errors="coerce")
    while len(cols) >= GROUP_MIN_COLUMNS:
        total = num[cols].sum(axis=1)
        corr = {c: num[c].corr((total - num[c]) / (len(cols) - 1)) for c in cols}
        worst = min(cols, key=lambda c: (corr[c] if pd.notna(corr[c]) else -1.0))
        if pd.notna(corr[worst]) and corr[worst] >= GROUP_MIN_CORRELATION:
            break
        cols.remove(worst)
    return cols


def describe(groups: list[dict]) -> str:
    """The planner's note on each group."""
    lines = []
    for g in groups:
        cols = g["columns"]
        shown = ", ".join(f"`{c}`" for c in cols[:6]) + (f" … `{cols[-1]}`" if len(cols) > 6 else "")
        lines.append(
            f"- {shown} ({len(cols)} columns) hold one kind of score on one scale "
            f"({g['low']:g} to {g['high']:g}), one per item. `{g['name']}` is each row's average over them: "
            "use it (with `avg`) for the average score and for its trend. To name the strongest or weakest "
            "item, draw a bar with NO dimension, `measures` listing these columns, `aggregation` avg and "
            "`sort` asc: one bar per item.")
    return "\n".join(lines)
