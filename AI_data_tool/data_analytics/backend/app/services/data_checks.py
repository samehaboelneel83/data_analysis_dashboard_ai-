"""Saved quality checks, run on new data BEFORE it replaces the old (pipeline plan, phase 3).

A refresh used to publish whatever the source returned. A load that came back
with half the rows, a key column full of blanks or a status nobody has heard
of went straight onto every dashboard. Each `DataCheck` is evaluated on the
fetched frame first:

* a failing `warn` check is recorded on the run and the data is published;
* a failing `block` check keeps the previous file live, records the run as
  `blocked`, and the owner is told which check failed (phase 2's alerts).

Schema notes ride along on every run with checks or not: a column the data no
longer has, a new column, a column whose type changed. Never blocking on their
own -- a dropped column something USES is already refused by `guard_schema`.

Pure functions over a DataFrame, so the same evaluation serves the scheduler,
a manual refresh, an incremental append and the "try it now" button.

Results carry COUNTS, never sample values. Checks run over every row, before
any reader's row rules or hidden columns apply; a message like "repeated ids,
e.g. 7" would show an editor whose access is limited a value from a row they
may not see. Row totals are no secret (every reader sees a dataset's row
count), so counts are safe to show to whoever may edit the dataset.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

KINDS = ("not_null", "unique", "accepted_values", "row_count", "row_drop", "rule")
#: Kinds that look at one column.
COLUMN_KINDS = ("not_null", "unique", "accepted_values")
SEVERITIES = ("warn", "block")
MAX_CHECKS_PER_DATASET = 50
MAX_ACCEPTED_VALUES = 500


class ChecksBlocked(Exception):
    """A blocking check failed: the new data must not replace the old."""

    def __init__(self, results: list[dict]):
        self.results = results
        failed = [r for r in results if r.get("severity") == "block" and not r.get("passed")]
        super().__init__("; ".join(describe(r) for r in failed) or "a blocking check failed")


class InvalidCheck(ValueError):
    pass


def validate_check(kind: str, column: str | None, params: dict | None, severity: str) -> dict:
    """Refuse, when a check is SAVED, what could never be evaluated. Returns
    the cleaned params."""
    params = dict(params or {})
    if kind not in KINDS:
        raise InvalidCheck(f"kind must be one of {', '.join(KINDS)}")
    if severity not in SEVERITIES:
        raise InvalidCheck("severity must be 'warn' or 'block'")
    if kind in COLUMN_KINDS and not (isinstance(column, str) and column.strip()):
        raise InvalidCheck(f"A {kind.replace('_', ' ')} check needs a column")
    if kind == "accepted_values":
        values = params.get("values")
        if not isinstance(values, list) or not values:
            raise InvalidCheck("List the accepted values")
        if len(values) > MAX_ACCEPTED_VALUES:
            raise InvalidCheck(f"At most {MAX_ACCEPTED_VALUES} accepted values")
        params = {"values": [str(v) for v in values]}
    elif kind == "row_count":
        lo, hi = params.get("min"), params.get("max")
        for name, v in (("min", lo), ("max", hi)):
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0):
                raise InvalidCheck(f"{name} must be a number of rows")
        if lo is None and hi is None:
            raise InvalidCheck("Give a minimum, a maximum, or both")
        if lo is not None and hi is not None and lo > hi:
            raise InvalidCheck("The minimum is above the maximum")
        params = {"min": lo, "max": hi}
    elif kind == "row_drop":
        pct = params.get("max_drop_pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 < pct <= 100:
            raise InvalidCheck("max_drop_pct must be between 1 and 100")
        params = {"max_drop_pct": pct}
    elif kind == "rule":
        expr = params.get("expression")
        if not isinstance(expr, str) or not expr.strip():
            raise InvalidCheck("Write the rule every good row must satisfy")
        from .widget_data import _validate_expr_safety
        try:
            _validate_expr_safety(expr)
        except Exception as e:  # noqa: BLE001
            raise InvalidCheck(f"That rule cannot be used: {e}")
        params = {"expression": expr.strip()}
    else:
        params = {}
    return params


def _one(df: pd.DataFrame, check: dict, previous_rows: int | None) -> dict:
    kind, col, params = check["kind"], check.get("column"), check.get("params") or {}
    res: dict[str, Any] = {"id": check.get("id"), "kind": kind, "column": col,
                           "severity": check.get("severity", "warn"), "passed": True,
                           "failing": 0, "detail": None}
    if kind in COLUMN_KINDS and col not in df.columns:
        res.update(passed=False, detail=f"the data has no column '{col}'")
        return res
    if kind == "not_null":
        s = df[col]
        blank = s.isna() | (s.astype(str).str.strip() == "")
        n = int(blank.sum())
        if n:
            res.update(passed=False, failing=n, detail=f"{n:,} of {len(df):,} rows have no {col}")
    elif kind == "unique":
        s = df[col].dropna()
        dup = s[s.duplicated(keep=False)]
        n = int(s.duplicated().sum())
        if n:
            res.update(passed=False, failing=n,
                       detail=f"{n:,} repeated {col} values ({dup.nunique():,} distinct values repeat)")
    elif kind == "accepted_values":
        allowed = {str(v) for v in params.get("values") or []}
        s = df[col].dropna().astype(str)
        bad = s[~s.isin(allowed)]
        if len(bad):
            res.update(passed=False, failing=int(len(bad)),
                       detail=f"{len(bad):,} rows have values outside the list "
                              f"({bad.nunique():,} different values)")
    elif kind == "row_count":
        n, lo, hi = len(df), params.get("min"), params.get("max")
        if lo is not None and n < lo:
            res.update(passed=False, detail=f"{n:,} rows, fewer than the minimum {int(lo):,}")
        elif hi is not None and n > hi:
            res.update(passed=False, detail=f"{n:,} rows, more than the maximum {int(hi):,}")
    elif kind == "row_drop":
        pct = float(params.get("max_drop_pct") or 0)
        if previous_rows and previous_rows > 0:
            fell = (previous_rows - len(df)) * 100.0 / previous_rows
            if fell > pct:
                res.update(passed=False,
                           detail=f"rows fell {fell:.0f}% ({previous_rows:,} to {len(df):,}); "
                                  f"the limit is {pct:g}%")
    elif kind == "rule":
        from .widget_data import apply_filter_expr
        expr = params.get("expression") or ""
        try:
            kept = apply_filter_expr(df, expr, silent=False)
        except Exception as e:  # noqa: BLE001 -- a broken rule fails, visibly
            res.update(passed=False, detail=f"the rule could not run: {e}"[:300])
            return res
        n = int(len(df) - len(kept))
        if n:
            res.update(passed=False, failing=n, detail=f"{n:,} rows break the rule {expr}")
    return res


def schema_notes(df: pd.DataFrame, known: dict[str, str]) -> list[dict]:
    """What changed in the columns since the last load: gone, new, retyped.
    `known` maps the dataset's recorded columns to their dtype."""
    if not known:
        return []
    from .ingest import detect_types
    types = detect_types(df)
    notes = []
    gone = [c for c in known if c not in df.columns]
    new = [c for c in df.columns if c not in known]
    if gone:
        notes.append({"kind": "schema", "severity": "warn", "passed": False, "column": None,
                      "detail": f"no longer in the data: {', '.join(gone[:8])}"})
    if new:
        notes.append({"kind": "schema", "severity": "warn", "passed": False, "column": None,
                      "detail": f"new in the data: {', '.join(new[:8])}"})
    retyped = [f"{c} ({known[c]} to {types[c]})" for c in df.columns
               if c in known and c in types and known[c] and types[c] != known[c]]
    if retyped:
        notes.append({"kind": "schema", "severity": "warn", "passed": False, "column": None,
                      "detail": f"type changed: {', '.join(retyped[:8])}"})
    return notes


def evaluate(df: pd.DataFrame, checks: list[dict], *, previous_rows: int | None = None,
             known_types: dict[str, str] | None = None) -> list[dict]:
    """Every enabled check's result on `df`, then the schema notes."""
    out = [_one(df, c, previous_rows) for c in checks if c.get("enabled", True)]
    out += schema_notes(df, known_types or {})
    return out


def blocking_failures(results: list[dict]) -> list[dict]:
    return [r for r in results if r.get("severity") == "block" and not r.get("passed")]


def describe(r: dict) -> str:
    label = {"not_null": "No blanks in", "unique": "Unique", "accepted_values": "Allowed values in",
             "row_count": "Row count", "row_drop": "Row drop", "rule": "Rule",
             "schema": "Columns"}.get(r.get("kind"), r.get("kind") or "check")
    head = f"{label} {r['column']}" if r.get("column") else label
    return f"{head}: {r['detail']}" if r.get("detail") else head


def check_rows(rows) -> list[dict]:
    """DataCheck ORM rows as the plain dicts `evaluate` takes."""
    return [{"id": c.id, "kind": c.kind, "column": c.column, "params": c.params or {},
             "severity": c.severity, "enabled": bool(c.enabled)} for c in rows]


async def load_checks(session, dataset_id: int) -> list[dict]:
    from sqlalchemy import select
    from ..models.models import DataCheck
    rows = (await session.execute(select(DataCheck).where(
        DataCheck.dataset_id == dataset_id).order_by(DataCheck.id))).scalars().all()
    return check_rows(rows)


async def known_types(session, dataset_id: int) -> dict[str, str]:
    from sqlalchemy import select
    from ..models.models import DatasetColumn
    return {c.name: c.dtype for c in (await session.execute(select(DatasetColumn).where(
        DatasetColumn.dataset_id == dataset_id))).scalars().all()}


def make_validator(checks: list[dict], previous_rows: int | None,
                   known: dict[str, str], holder: dict, *, force: bool = False):
    """A callback for the refresh functions: called with the new frame right
    before the file is written. Stores the results in `holder["checks"]` and
    raises ChecksBlocked on a blocking failure (unless `force`: an editor
    chose to publish anyway)."""
    def _validate(df: pd.DataFrame) -> None:
        results = evaluate(df, checks, previous_rows=previous_rows, known_types=known)
        holder["checks"] = results
        if not force and blocking_failures(results):
            raise ChecksBlocked(results)
    return _validate
