"""A dataset's data-quality report (requested 2026-09-25).

The pieces existed apart -- missing % in the profile, outliers in an analysis,
duplicate keys in the join check -- and none answered "can I trust this data?"
in one place, nor checked the author's own rules. This does, over the frame it
is given, which the caller has already secured as the viewer (RLS, column
security) and run through the saved prep pipeline: the quality of the rows
this person's charts are actually built from.
"""
from __future__ import annotations

import pandas as pd

#: Share of a text column's values that parse as numbers for it to count as
#: "numbers stored as text" (at or above) or "mixed" (between the two).
NUMERIC_TEXT_SHARE = 0.9
MIXED_SHARE = 0.1
MAX_RULES = 20


def _records(frame: pd.DataFrame, n: int) -> list[dict]:
    from .widget_data import _safe
    return [{k: _safe(v) for k, v in row.items()} for row in frame.head(n).to_dict(orient="records")]


def _column(df: pd.DataFrame, c: str) -> dict:
    s = df[c]
    rows = len(df)
    non_null = s.dropna()
    missing = int(s.isna().sum())
    issues: list[str] = []
    distinct = int(non_null.nunique())
    if rows > 1 and distinct <= 1:
        issues.append("constant" if distinct == 1 else "empty")
    outliers = None
    if pd.api.types.is_numeric_dtype(s) and s.dtype != bool:
        if len(non_null) >= 4:
            q1, q3 = float(non_null.quantile(0.25)), float(non_null.quantile(0.75))
            lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
            outliers = int(((non_null < lo) | (non_null > hi)).sum())
            if outliers:
                issues.append(f"{outliers:,} outlier{'s' if outliers != 1 else ''}")
    elif s.dtype == object and len(non_null):
        text = non_null.astype(str)
        parsed = pd.to_numeric(text.str.replace(",", "", regex=False).str.strip(), errors="coerce")
        share = float(parsed.notna().mean())
        if share >= NUMERIC_TEXT_SHARE:
            issues.append("numbers stored as text")
        elif share >= MIXED_SHARE:
            issues.append("mixed numbers and text")
        spaced = int((text != text.str.strip()).sum())
        if spaced:
            issues.append(f"{spaced:,} value{'s' if spaced != 1 else ''} with leading/trailing spaces")
    if missing and rows:
        issues.insert(0, f"{missing * 100 / rows:.0f}% missing")
    return {"column": c, "dtype": str(s.dtype), "missing": missing,
            "missing_pct": round(missing * 100 / rows, 1) if rows else 0.0,
            "distinct": distinct, "outliers": outliers, "issues": issues}


def quality_report(df: pd.DataFrame, rules: list[str] | None = None, examples: int = 5) -> dict:
    """Columns, duplicates and rule checks for `df`. Pure: no I/O."""
    from .widget_data import apply_filter_expr

    rows = len(df)
    columns = [_column(df, c) for c in df.columns]
    extra_copies = int(df.duplicated().sum()) if rows else 0
    dup_rows = df[df.duplicated(keep=False)] if extra_copies else df.iloc[0:0]
    checks = []
    for expr in (rules or [])[:MAX_RULES]:
        expr = (expr or "").strip()
        if not expr:
            continue
        try:
            kept = apply_filter_expr(df, expr, silent=False)
        except Exception as e:  # noqa: BLE001 -- a bad rule is reported, not raised
            checks.append({"rule": expr, "error": str(e)})
            continue
        failing = df.loc[~df.index.isin(kept.index)]
        checks.append({"rule": expr, "failing_rows": int(len(failing)),
                       "examples": _records(failing, 3)})
    cells = rows * len(df.columns)
    missing_cells = sum(c["missing"] for c in columns)
    return {
        "rows": rows, "columns": len(df.columns),
        "missing_cells": missing_cells,
        "missing_pct": round(missing_cells * 100 / cells, 1) if cells else 0.0,
        "duplicate_rows": extra_copies,
        "duplicate_examples": _records(dup_rows, examples),
        "columns_with_issues": sum(1 for c in columns if c["issues"]),
        "column_report": columns,
        "rules": checks,
    }
