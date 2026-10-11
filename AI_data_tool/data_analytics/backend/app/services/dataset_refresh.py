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


def write_csv_atomic(df: pd.DataFrame, path) -> list[str]:
    """Write beside the live file, then swap it in (E07). A refresh writes over
    the file a dataset is reading; a crash or a full disk mid-write used to
    leave a truncated CSV behind a dataset that still looked ready.

    Offset-carrying instants are converted IN PLACE to the reference zone
    first (services/timezones.py), so what is written, and the frame the
    caller types afterwards, hold one kind of time. Returns those columns."""
    import os
    from .timezones import normalize_instants
    converted = normalize_instants(df)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    if is_parquet(path):
        # A dataset imported as a stream is a parquet file: CSV text written
        # under that name would be unreadable.
        df.to_parquet(tmp, index=False)
    else:
        df.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return converted


def is_parquet(path) -> bool:
    return str(path).lower().endswith(".parquet")


def rows_of(df: pd.DataFrame) -> int:
    """How many rows the dataset now holds. A refresh that was written to disk
    as it arrived hands back a SAMPLE of the rows, with the real count on it."""
    return int(df.attrs.get("rows", len(df)))


def missing_of(df: pd.DataFrame, column: str) -> float:
    """How empty a column is, counted on every row either way."""
    from .ingest import missing_pct
    counted = df.attrs.get("missing")
    return float(counted.get(column, 0.0)) if isinstance(counted, dict) else missing_pct(df[column])


STAGE_PREFIX = "refresh_"


def _stage_dir(path: Path) -> str:
    """Where a large reload is written before it replaces the file. One per
    dataset file: what an earlier attempt left behind (a reload cancelled
    after the fetch) is removed first."""
    import shutil
    import tempfile
    mine = f"{STAGE_PREFIX}{path.stem}_"
    path.parent.mkdir(parents=True, exist_ok=True)
    for old in path.parent.glob(mine + "*"):
        shutil.rmtree(old, ignore_errors=True)
    return tempfile.mkdtemp(prefix=mine, dir=str(path.parent))


def _drop_stage(stage: str | None) -> None:
    import shutil
    if stage:
        shutil.rmtree(stage, ignore_errors=True)


def _fetch_full(source_cfg: dict, table: str | None, query: str | None, path: Path | None,
                required: set[str] | None, column_map: dict[str, str] | None,
                cursor_column: str | None = None) -> tuple[pd.DataFrame, str | None, object]:
    """The whole source, for a full reload: (frame, stage, cursor).

    A dataset whose file is parquet may be far larger than memory, so its
    reload is written to disk as it arrives, exactly as its import was. The
    frame handed back is then a random SAMPLE of the rows, carrying
    `attrs["rows"]` (the real count), `attrs["missing"]` (how empty each
    column is, counted on every row) and `attrs["staged"]` (the finished file,
    not yet swapped in); `cursor` is the highest cursor value in the file.
    Anything else is fetched into memory as it always was (stage None)."""
    from .connections import Streamed, import_to_dataframe
    from .ingest import detect_types
    from .timezones import normalize_instants
    if path is None or not is_parquet(path):
        return guard_schema(import_to_dataframe(source_cfg, table, query), required, column_map), None, None
    rename = {new: old for new, old in (column_map or {}).items()}

    def _prepare(chunk):
        if rename:
            chunk = chunk.rename(columns={n: o for n, o in rename.items() if n in chunk.columns})
        normalize_instants(chunk)
        detect_types(chunk)
        return chunk

    stage = _stage_dir(path)
    try:
        got = import_to_dataframe(source_cfg, table, query, stream_dir=stage, prepare=_prepare)
        if not isinstance(got, Streamed):
            _drop_stage(stage)
            return guard_schema(got, required, column_map), None, None
        sample = guard_schema(got.sample, required)
        sample.attrs.update(rows=int(got.rows), missing=dict(got.missing), staged=str(got.path))
        cursor = None
        if cursor_column and cursor_column in sample.columns:
            import duckdb
            con = duckdb.connect()
            try:
                cursor = con.execute(
                    'SELECT max("%s") FROM read_parquet(?)' % cursor_column.replace('"', '""'),
                    [str(got.path)]).fetchone()[0]
            finally:
                con.close()
        return sample, stage, cursor
    except BaseException:
        _drop_stage(stage)
        raise


def _swap_staged(df: pd.DataFrame, path: Path) -> None:
    """Put a staged reload in the dataset's place, and clear its folder."""
    import os
    staged = Path(df.attrs.pop("staged"))
    path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, path)
    _drop_stage(str(staged.parent))


def _staged_cursor(found, previous):
    """`_max_cursor` for a value read off the staged file. The file holds
    wall-clock time in the reference zone; the watermark goes back to the
    source as an instant."""
    if found is None or (not isinstance(found, str) and pd.isna(found)):
        return previous
    import datetime as _dt
    if isinstance(found, (_dt.datetime, pd.Timestamp)):
        stamp = pd.Timestamp(found)
        if stamp.tzinfo is None:
            from .timezones import reference_zone
            stamp = stamp.tz_localize(reference_zone(), ambiguous=True, nonexistent="shift_forward")
        return stamp.isoformat()
    return str(found)


class SchemaBreak(Exception):
    """The source no longer has columns something on this dataset uses (E05).

    A refresh used to overwrite the file regardless, and every widget, measure
    or filter naming a vanished column broke at once, silently. Raised BEFORE
    anything is written, so the file on disk is still the last good one.
    `suggestions` pairs each missing column with the new columns that look
    like its renamed self -- the mapping the caller can send back."""

    def __init__(self, missing: list[str], suggestions: dict[str, list[str]],
                 available: list[str] | None = None):
        self.missing = missing
        self.suggestions = suggestions
        self.available = available or []   # every incoming column, for a picker
        super().__init__("The source no longer has " + ", ".join(repr(m) for m in missing))


def _norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def guard_schema(df: pd.DataFrame, required: set[str] | None,
                 column_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Apply a rename mapping (new column -> the old name everything uses),
    then refuse if anything `required` is still missing."""
    if column_map:
        df = df.rename(columns={new: old for new, old in column_map.items() if new in df.columns})
    missing = sorted(set(required or ()) - set(df.columns))
    if missing:
        import difflib
        fresh = [c for c in df.columns if c not in (required or ())]
        suggestions = {}
        for m in missing:
            same = [c for c in fresh if _norm(c) == _norm(m)]
            suggestions[m] = same or difflib.get_close_matches(str(m), [str(c) for c in fresh], n=3, cutoff=0.6)
        raise SchemaBreak(missing, suggestions, [str(c) for c in df.columns])
    return df


def rewrite_dataset_file(
    source_cfg: dict, filename: str, source_table: str | None, source_query: str | None,
    required_columns: set[str] | None = None,
    validate=None,
) -> tuple[pd.DataFrame, dict]:
    """Re-fetch from the connection and overwrite the cached CSV in place.

    Returns the fresh frame and its detected type map so the caller can update
    DatasetColumn rows. Synchronous and blocking — callers run it in a thread.
    `required_columns`: raise SchemaBreak, writing nothing, if any is gone.
    `validate(df)`: called on the new frame before anything is written; it
    raises (services/data_checks.ChecksBlocked) to keep the old file.
    """
    from .ingest import detect_types

    path = Path(filename)
    df, stage, _cursor = _fetch_full(source_cfg, source_table, source_query, path, required_columns, None)
    try:
        if validate is not None:
            validate(df)
    except BaseException:
        _drop_stage(stage)
        raise
    if stage:
        # Larger than memory: already on disk; `df` is a sample (see rows_of).
        _swap_staged(df, path)
        return df, detect_types(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(df, path)
    write_parquet_sidecar(str(path))  # synchronous like the rest; callers thread us
    return df, detect_types(df)


# ── F3: watermark-driven full / incremental refresh ────────────────────────────

def build_incremental_query(table: str | None, query: str | None,
                             cursor_column: str, cursor_value,
                             valid_columns: set[str] | None = None,
                             family: str | None = None) -> str:
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
    # Quoted for the source's dialect (2026-10-10): MySQL reads "col" as a
    # TEXT value, so `"updated_at" > :cursor_val` compared a constant string.
    from .sql_safety import quote_ident
    quoted_col = quote_ident(family or "postgresql", cursor_column)
    return f"SELECT * FROM {_base_source(table, query, family)} WHERE {quoted_col} > :cursor_val"


def _base_source(table: str | None, query: str | None, family: str | None) -> str:
    from .sql_safety import quote_ident
    if query:
        return f"({query.strip().rstrip(';')}) AS _base"
    return quote_ident(family or "postgresql", table or "")


def build_key_query(table: str | None, query: str | None, key_column: str,
                    valid_columns: set[str] | None = None, family: str | None = None) -> str:
    """Every key the source holds NOW (one column), to find rows deleted there.
    The key is checked against the dataset's columns like the cursor is."""
    if valid_columns is not None and key_column not in valid_columns:
        raise ValueError(f"Unknown key column: {key_column!r}")
    from .sql_safety import quote_ident
    return f"SELECT {quote_ident(family or 'postgresql', key_column)} FROM {_base_source(table, query, family)}"


def drop_deleted(df: pd.DataFrame, key_column: str, source_keys: pd.Series) -> tuple[pd.DataFrame, int, str | None]:
    """Rows whose key the source no longer has, removed: (frame, removed, warning).

    An EMPTY key list while the dataset holds rows is far more likely a broken
    or filtered source than "everything was deleted": nothing is removed and
    the run says so, rather than emptying every dashboard."""
    if len(df) and not len(source_keys):
        return df, 0, "The source returned no keys, so no rows were removed as deleted."
    from .data_checks import key_text
    alive = set(key_text(source_keys))
    # A row with no key cannot be matched, so it is never treated as deleted.
    keep = df[key_column].isna() | key_text(df[key_column], keep_empty=True).isin(alive)
    return df[keep].reset_index(drop=True), int((~keep).sum()), None


def _max_cursor(df: pd.DataFrame, cursor_column: str | None, previous,
                converted: list[str] | None = None):
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
    if converted and cursor_column in converted and isinstance(m, pd.Timestamp):
        # The stored column is wall-clock time in the reference zone (E07); the
        # watermark goes back to the SOURCE, which must compare the same instant
        # rather than read a bare time in its own session zone. In a DST
        # fall-back hour the earlier instant is taken: re-reading an hour beats
        # skipping one.
        from .timezones import reference_zone
        return m.tz_localize(reference_zone(), ambiguous=True,
                             nonexistent="shift_forward").isoformat()
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
    required_columns: set[str] | None = None,
    column_map: dict[str, str] | None = None,
    write: bool = True,
    validate=None,
    key_column: str | None = None,
    lookback_hours: int | None = None,
    reconcile_deletes: bool = False,
) -> dict:
    """Full or incremental refresh of one source-backed dataset's cached file.

    2026-10-10: `reconcile_deletes` (with a key) also removes rows whose key
    the source no longer holds -- a merge otherwise keeps deleted rows forever.

    Phase 4: `key_column` makes an incremental load a MERGE -- an incoming
    row whose key the file already holds replaces it, so an updated order
    appears once with its new values instead of twice. `lookback_hours`
    re-reads that far behind a date cursor to catch late updates (only with
    a key; the re-read rows are then replaced, not duplicated).

    `validate(df)` (pipeline plan, phase 3) is called on the frame the
    dataset would hold -- after an incremental append, the whole of it --
    before anything is written, so a blocking check keeps the old file.

    E12: `write=False` fetches and builds the new frame but leaves the file
    alone; the caller writes it with `write_dataset_files` once it knows its
    outcome will stand (a queued refresh does that only after it has fenced
    its job's success, so two overlapping attempts cannot both append).

    E05: `column_map` renames incoming columns (new -> old) before anything
    else, and a FULL load missing any of `required_columns` raises SchemaBreak
    before the file is touched. (An incremental append keeps the file's
    existing columns, so it cannot drop one.)

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
            cursor_column, cursor_value, valid_columns, required_columns, column_map,
            write, validate, key_column, lookback_hours, reconcile_deletes,
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
    required_columns: set[str] | None = None,
    column_map: dict[str, str] | None = None,
    write: bool = True,
    validate=None,
    key_column: str | None = None,
    lookback_hours: int | None = None,
    reconcile_deletes: bool = False,
) -> dict:
    from .ingest import detect_types
    from .timezones import normalize_instants
    from .connections import import_to_dataframe
    from . import connectors
    family = connectors.sql_family_of(source_cfg) if source_cfg else None

    warning = None
    effective_mode = "incremental" if mode == "incremental" else "full"
    path = Path(filename) if filename else None

    if effective_mode == "incremental" and not cursor_column:
        effective_mode = "full"
        warning = "No watermark column configured — ran a full refresh instead."

    existing_df = None
    if effective_mode == "incremental" and path is not None and path.exists():
        try:
            if is_parquet(path):
                # Appending means holding every row; a file too large for
                # that is reloaded whole, written to disk as it arrives.
                from . import memory_guard
                with memory_guard.reserved(str(path)):
                    existing_df = pd.read_parquet(path)
            else:
                existing_df = pd.read_csv(path)
        except Exception as e:  # noqa: BLE001 - unreadable cache: full refresh recovers it
            existing_df = None
            from .memory_guard import TooLargeToLoad
            if isinstance(e, TooLargeToLoad):
                effective_mode = "full"
                warning = ("The dataset is too large to add rows to in memory — "
                           "ran a full refresh instead.")
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
        # A key the file does not hold cannot be merged on: append, and say so.
        if key_column and existing_df is not None and key_column not in existing_df.columns:
            warning = f"Key column '{key_column}' not found on the dataset — appended without merging."
            key_column = None
        fetch_from = lookback_cursor(cursor_value, lookback_hours) if key_column else cursor_value
        try:
            incr_sql = build_incremental_query(source_table, source_query, cursor_column, cursor_value, cols, family)
            new_rows = import_to_dataframe(source_cfg, None, incr_sql, params={"cursor_val": fetch_from})
            if column_map:
                new_rows = new_rows.rename(columns={n: o for n, o in column_map.items() if n in new_rows.columns})
        except Exception as e:  # noqa: BLE001 - bad cursor/query: fall back, don't 500
            effective_mode = "full"
            warning = f"Incremental query failed ({e}) — ran a full refresh instead."
        else:
            if existing_df is not None and new_rows.empty:
                # Nothing new -- the commonest incremental run. The empty fetch
                # has UNTYPED columns; concatenated onto the file it turned whole
                # numbers into objects, which the instant normaliser then read as
                # nanoseconds: every id became 1970-01-01 00:00:00.000000001.
                new_rows = existing_df.iloc[0:0]
            rows_updated = 0
            if key_column and existing_df is not None and len(existing_df) and key_column in new_rows.columns:
                # Merge: the incoming row wins. Keys are compared as text so
                # 7 and "7" (a CSV round trip) are one key.
                # Keys compared as text (data_checks.key_text): 7, "7" and 7.0
                # are one key -- a CSV round trip or a key column with a gap
                # stores 7 as 7.0, and the update was appended as a duplicate.
                from .data_checks import key_text
                held_txt = key_text(existing_df[key_column], keep_empty=True)
                incoming = key_text(new_rows[key_column], keep_empty=True)
                rows_updated = int(incoming.isin(set(held_txt.dropna())).sum())
                kept = existing_df[~held_txt.isin(set(incoming.dropna()))]
                df = pd.concat([kept, new_rows], ignore_index=True)
                dedup = key_text(df[key_column], keep_empty=True)
                df = df[~(dedup.notna() & dedup.duplicated(keep="last"))].reset_index(drop=True)
            else:
                df = (pd.concat([existing_df, new_rows], ignore_index=True)
                      if existing_df is not None and len(existing_df) else new_rows)
            rows_deleted = 0
            if reconcile_deletes and key_column and key_column in df.columns:
                try:
                    keys = import_to_dataframe(source_cfg, None, build_key_query(
                        source_table, source_query, key_column, cols, family))
                    if column_map:
                        keys = keys.rename(columns={n: o for n, o in column_map.items() if n in keys.columns})
                    df, rows_deleted, note = drop_deleted(df, key_column, keys[key_column] if key_column in keys.columns
                                                          else keys.iloc[:, 0])
                    if note:
                        warning = note
                except Exception as e:  # noqa: BLE001 -- the merge stands; deletes wait for next run
                    warning = f"Could not check for deleted rows ({e}); none were removed this time."
            # The cap is on what the dataset HOLDS: appending past it refuses
            # like a full load over it would, rather than growing unchecked.
            from .connections import _checked, _import_cap
            _checked(df, _import_cap())
            if validate is not None:
                validate(df)
            converted: list[str] = []
            if path is not None and write:
                path.parent.mkdir(parents=True, exist_ok=True)
                converted = write_csv_atomic(df, path)
                write_parquet_sidecar(str(path))
            else:
                converted = normalize_instants(df)
            return {
                "df": df, "type_map": detect_types(df), "mode": "incremental",
                "cursor_value": _max_cursor(df, cursor_column, cursor_value, converted),
                "warning": warning, "rows_added": len(new_rows) - rows_updated,
                "rows_updated": rows_updated, "rows_deleted": rows_deleted,
            }

    # Full load: explicitly requested, the first incremental run (no baseline
    # cursor yet), or any of the fallbacks above.
    df, stage, staged_cursor = _fetch_full(source_cfg, source_table, source_query, path,
                                           required_columns, column_map, cursor_column)
    try:
        if validate is not None:
            validate(df)
    except BaseException:
        _drop_stage(stage)
        raise
    if stage:
        # Larger than memory: the reload is a finished file beside the live
        # one, and `df` a sample of it. Swapped in here, or by the caller's
        # `write_dataset_files` when the write was left to it.
        if write:
            _swap_staged(df, path)
        return {
            "df": df, "type_map": detect_types(df), "mode": "full",
            "cursor_value": _staged_cursor(staged_cursor, cursor_value) if cursor_column else cursor_value,
            "warning": warning, "rows_added": rows_of(df),
        }
    converted: list[str] = []
    if path is not None and write:
        path.parent.mkdir(parents=True, exist_ok=True)
        converted = write_csv_atomic(df, path)
        write_parquet_sidecar(str(path))
    else:
        converted = normalize_instants(df)
    new_cursor = (_max_cursor(df, cursor_column, cursor_value, converted)
                  if cursor_column else cursor_value)
    return {
        "df": df, "type_map": detect_types(df), "mode": "full",
        "cursor_value": new_cursor, "warning": warning, "rows_added": len(df),
    }


def lookback_cursor(cursor_value, lookback_hours: int | None):
    """The cursor to fetch from: `lookback_hours` before a DATE cursor.

    A numeric or opaque cursor is returned as it is -- "six hours before
    order 1,042" means nothing. The stored watermark is never moved back;
    only this fetch reads further."""
    if not lookback_hours or cursor_value in (None, ""):
        return cursor_value
    text = str(cursor_value)
    try:
        float(text)
        return cursor_value               # a number, not a date
    except ValueError:
        pass
    try:
        stamp = pd.Timestamp(text)
    except (ValueError, TypeError):
        return cursor_value
    if pd.isna(stamp):
        return cursor_value
    back = stamp - pd.Timedelta(hours=int(lookback_hours))
    # Same shape as the stored value: a date stays a date, a time a time.
    return back.date().isoformat() if len(text) <= 10 else back.isoformat(sep=" ")


def write_dataset_files(df: pd.DataFrame, filename: str) -> None:
    """The file write `refresh_dataset(write=False)` left to its caller: the
    CSV swapped in atomically, then its parquet sidecar. Blocking."""
    path = Path(filename)
    if df.attrs.get("staged"):
        _swap_staged(df, path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(df, path)
    write_parquet_sidecar(str(path))


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
