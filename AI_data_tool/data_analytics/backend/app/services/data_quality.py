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


#: Share of rows one placeholder value must hold before it is reported. Below
#: this, a -1 is as likely a real value as a code.
PLACEHOLDER_SHARE = 0.01
_NEGATIVE_CODES = (-1, -9, -99, -999, -9999)
_TEXT_CODES = {"n/", "n/a", "na", "#n/a", "-", "--", "?", "null", "none", "unknown", "nil"}


def _placeholder(s: pd.Series, column: str) -> tuple[object, int] | None:
    """The value standing in for "unknown" in this column, and how many rows
    hold it -- or None. Live QA 2026-09-28: a call log's IMEI, IMSI and LAC
    held -1 in ~750 rows each, SITE_ID held 0 in 719 and ALPHA_SITE_ID "N/"
    in 719; none was flagged, and SUM(LAC) came out as -196.

    Deliberately narrow: a 0 in an AMOUNT is a real zero (the same log's
    RATED_AMOUNT is 0 in half its rows), so 0 counts only in an identifier."""
    from .semantic_guard import non_additive_kind
    non_null = s.dropna()
    if not len(non_null):
        return None
    floor = max(1, int(len(non_null) * PLACEHOLDER_SHARE))
    if pd.api.types.is_numeric_dtype(s) and s.dtype != bool:
        counts = non_null.value_counts()
        for code in _NEGATIVE_CODES:
            n = int(counts.get(code, 0))
            if n >= floor and bool((non_null[non_null != code] >= 0).all()):
                return code, n
        if non_additive_kind(column) == "identifier":
            n = int(counts.get(0, 0))
            if n >= floor:
                return 0, n
        return None
    if s.dtype == object:
        text = non_null.astype(str).str.strip()
        hits = text[text.str.lower().isin(_TEXT_CODES)]
        if len(hits) >= floor:
            value = hits.mode().iloc[0]
            return value, int((text == value).sum())
    return None


def _column(df: pd.DataFrame, c: str) -> dict:
    s = df[c]
    rows = len(df)
    non_null = s.dropna()
    missing = int(s.isna().sum())
    issues: list[str] = []
    distinct = int(non_null.nunique())
    if rows > 1 and distinct <= 1:
        issues.append("constant" if distinct == 1 else "empty")
    placeholder = _placeholder(s, c)
    if placeholder:
        value, n = placeholder
        shown = f'"{value}"' if isinstance(value, str) else str(value)
        issues.append(f"{n:,} row{'s' if n != 1 else ''} hold {shown}, which looks like a code for "
                      f"“unknown” -- it is counted, summed and averaged as a real value")
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
            "distinct": distinct, "outliers": outliers, "issues": issues,
            "placeholder": ({"value": placeholder[0], "rows": placeholder[1]} if placeholder else None)}


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
