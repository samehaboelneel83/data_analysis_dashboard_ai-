"""Shared dataset-refresh work.

Extracted so the manual `POST /datasets/{id}/refresh` endpoint and the background
scheduler run exactly the same code. Two copies of "re-fetch and overwrite the CSV"
would drift, and the divergence would only show up as a dataset that refreshes
differently depending on who triggered it.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import telemetry
from .frame_cache import sidecar_path, write_parquet_sidecar


def rewrite_dataset_file(
    source_cfg: dict, filename: str, source_table: str | None, source_query: str | None,
) -> tuple[pd.DataFrame, dict]:
    """Re-fetch from the connection and overwrite the cached CSV in place.

    Returns the fresh frame and its detected type map so the caller can update
    DatasetColumn rows. Synchronous and blocking — callers run it in a thread.
    """
    from .ingest import detect_types
    from .connections import import_to_dataframe

    df = import_to_dataframe(source_cfg, source_table, source_query)
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    write_parquet_sidecar(str(path))  # synchronous like the rest; callers thread us
    return df, detect_types(df)


# ── F3: watermark-driven full / incremental refresh ────────────────────────────

def build_incremental_query(table: str | None, query: str | None,
                             cursor_column: str, cursor_value,
                             valid_columns: set[str] | None = None) -> str:
    """The incremental fetch: everything past the watermark. `:cursor_val` is a
    SQLAlchemy bind parameter, never string-interpolated, so the cursor value
    (whatever type or content it carries) can never reshape the query.

    `cursor_column`, unlike the value, is identifier text that has to be
    interpolated (bind params can't stand in for column names) and it is
    user-settable (the watermark config on the dataset) — so it gets two
    independent defenses: when `valid_columns` is given (the dataset's actual
    column names), anything not in that allowlist is rejected outright rather
    than reaching SQL at all; and the identifier is always quote-escaped
    (`"` doubled) so even a column name carrying a literal quote can't break
    out of its quoting. Callers should treat a raised ValueError the same as
    any other incremental-query failure: fall back to a full refresh.

    A stored source_query wraps as a subquery rather than being edited in
    place — arbitrary hand-written SQL (possibly with its own WHERE, ORDER BY,
    or trailing semicolon) stays intact and simply gets filtered further."""
    if valid_columns is not None and cursor_column not in valid_columns:
        raise ValueError(f"Unknown cursor column: {cursor_column!r}")
    quoted_col = '"{}"'.format(cursor_column.replace('"', '""'))
    if query:
        base = query.strip().rstrip(";")
        return f"SELECT * FROM ({base}) AS _base WHERE {quoted_col} > :cursor_val"
    return f'SELECT * FROM "{table}" WHERE {quoted_col} > :cursor_val'


def _max_cursor(df: pd.DataFrame, cursor_column: str | None, previous):
    """The new watermark: the highest value seen for cursor_column in `df`, kept
    as text (the column may be a timestamp, an id, or an opaque token — Watermark
    stores it untyped and the column that produced it knows how to compare it).
    Falls back to the previous value when the column is absent, empty, or every
    value is null, so a bad refresh never regresses the cursor."""
    if not cursor_column or cursor_column not in df.columns or df.empty:
        return previous
    try:
        m = df[cursor_column].max()
    except Exception:  # noqa: BLE001 - an unorderable column falls back, not raises
        return previous
    if pd.isna(m):
        return previous
    return str(m)


def refresh_dataset(
    source_cfg: dict,
    filename: str | None,
    source_table: str | None,
    source_query: str | None,
    mode: str,
    cursor_column: str | None,
    cursor_value: str | None,
    valid_columns: set[str] | None = None,
) -> dict:
    """Full or incremental refresh of one source-backed dataset's cached file.

    Full: re-run the stored query/table wholesale, overwriting the file — the
    existing manual-refresh behaviour, now also the fallback for every
    incremental misconfiguration (missing cursor column, a cursor column the
    current data doesn't have, or a query that fails) so a bad watermark setup
    degrades to "refreshed, but read everything" rather than erroring the whole
    request. Incremental: fetch only rows past the watermark and append them to
    what's on disk; the very first incremental run (no prior cursor_value) has
    nothing to be incremental FROM, so it is a full load that also establishes
    the baseline cursor for every run after it.

    Synchronous and blocking — callers run it in a thread. Returns
    {df, type_map, mode, cursor_value, warning, rows_added}; `mode` and
    `warning` reflect what actually ran, which may differ from what was asked.
    """
    # E3: one span per refresh. Attributes are identifiers/status/timings
    # only -- source_table/source_query text is never attached, mirroring
    # the hash-only discipline used elsewhere (there's no single "the SQL"
    # here to hash, since incremental/full each build their own query).
    start = time.monotonic()
    with telemetry.tracer.start_as_current_span("dataset.refresh") as span:
        span.set_attribute("requested_mode", mode)
        result = _refresh_dataset_body(
            source_cfg, filename, source_table, source_query, mode,
            cursor_column, cursor_value, valid_columns,
        )
        span.set_attribute("status", "ok")
        span.set_attribute("effective_mode", result["mode"])
        span.set_attribute("rows_added", result["rows_added"])
        span.set_attribute("ms", int((time.monotonic() - start) * 1000))
        return result


def _refresh_dataset_body(
    source_cfg: dict,
    filename: str | None,
    source_table: str | None,
    source_query: str | None,
    mode: str,
    cursor_column: str | None,
    cursor_value: str | None,
    valid_columns: set[str] | None = None,
) -> dict:
    from .ingest import detect_types
    from .connections import import_to_dataframe

    warning = None
    effective_mode = "incremental" if mode == "incremental" else "full"
    path = Path(filename) if filename else None

    if effective_mode == "incremental" and not cursor_column:
        effective_mode = "full"
        warning = "No watermark column configured — ran a full refresh instead."

    existing_df = None
    if effective_mode == "incremental" and path is not None and path.exists():
        try:
            existing_df = pd.read_csv(path)
        except Exception:  # noqa: BLE001 - unreadable cache: full refresh recovers it
            existing_df = None
        if existing_df is not None and cursor_column not in existing_df.columns:
            effective_mode = "full"
            warning = f"Column '{cursor_column}' not found on the dataset — ran a full refresh instead."

    if effective_mode == "incremental" and cursor_value not in (None, ""):
        # Allowlist for the identifier interpolated into the query below: the
        # cached file's own columns when we just read it, else whatever the
        # caller knows about the dataset's schema (e.g. its DatasetColumn
        # names) — either way, `cursor_column` must be an actual column, not
        # arbitrary attacker-settable SQL-identifier text.
        cols = set(existing_df.columns) if existing_df is not None else valid_columns
        try:
            incr_sql = build_incremental_query(source_table, source_query, cursor_column, cursor_value, cols)
            new_rows = import_to_dataframe(source_cfg, None, incr_sql, params={"cursor_val": cursor_value})
        except Exception as e:  # noqa: BLE001 - bad cursor/query: fall back, don't 500
            effective_mode = "full"
            warning = f"Incremental query failed ({e}) — ran a full refresh instead."
        else:
            df = (pd.concat([existing_df, new_rows], ignore_index=True)
                  if existing_df is not None and len(existing_df) else new_rows)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(path, index=False)
                write_parquet_sidecar(str(path))
            return {
                "df": df, "type_map": detect_types(df), "mode": "incremental",
                "cursor_value": _max_cursor(df, cursor_column, cursor_value),
                "warning": warning, "rows_added": len(new_rows),
            }

    # Full load: explicitly requested, the first incremental run (no baseline
    # cursor yet), or any of the fallbacks above.
    df = import_to_dataframe(source_cfg, source_table, source_query)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        write_parquet_sidecar(str(path))
    new_cursor = _max_cursor(df, cursor_column, cursor_value) if cursor_column else cursor_value
    return {
        "df": df, "type_map": detect_types(df), "mode": "full",
        "cursor_value": new_cursor, "warning": warning, "rows_added": len(df),
    }


# ── O3: materialization manifest ────────────────────────────────────────────

async def write_materialization(
    db: AsyncSession, dataset_id: int, csv_path: str, kind: str,
    row_count: int, columns: list[str], watermark_value: str | None,
) -> "object":
    """Record the manifest row for the parquet sidecar a refresh just wrote
    (write_parquet_sidecar, called by every caller of this module — see its
    docstring). ONE Materialization row per dataset is the contract: any
    prior row(s) for this dataset are superseded (deleted) here, and the
    file a superseded row pointed at is unlinked -- but ONLY when no
    surviving row (the one this call just inserted) still references that
    same path. In practice `csv_path`'s sidecar path never changes across
    refreshes of the same dataset, so this prunes manifest rows, not files;
    the guard exists for the rename/re-import edge case where it would.

    Takes an AsyncSession rather than living in the router/scheduler call
    sites separately: both callers (routers/datasets.py refresh endpoint,
    services/refresh_scheduler.py refresh_one) already hold an open
    AsyncSession at the point they call this, right after the synchronous
    refresh_dataset()/rewrite_dataset_file() call returns.
    """
    from ..models.models import Materialization

    from datetime import datetime

    path = sidecar_path(csv_path)
    existing = (await db.execute(
        select(Materialization).where(Materialization.dataset_id == dataset_id)
    )).scalars().all()

    # dataset_id is UNIQUE (one manifest row per dataset, DB-enforced), so
    # supersede by updating the surviving row in place; extras (only possible
    # from a pre-constraint race) are deleted first. Insert-then-delete would
    # trip the constraint on the second refresh.
    stale_paths = [old.path for old in existing if old.path != path]
    if existing:
        row, *extras = existing
        for extra in extras:
            await db.delete(extra)
        row.path = path
        row.kind = kind
        row.row_count = row_count
        row.columns = list(columns)
        row.watermark_value = watermark_value
        row.created_at = datetime.utcnow()
    else:
        row = Materialization(
            dataset_id=dataset_id, path=path, kind=kind, row_count=row_count,
            columns=list(columns), watermark_value=watermark_value,
        )
        db.add(row)
    await db.flush()
    for old_path in stale_paths:
        # never unlink the file the surviving row references
        import os
        try:
            os.remove(old_path)
        except OSError:
            pass
    return row
