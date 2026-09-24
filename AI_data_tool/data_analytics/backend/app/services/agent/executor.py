"""V5 (dry run) + execution + sanity — the only module that touches the
customer's database, and it does so bounded in three ways: a statement
timeout, an injected row cap, and to_thread so a slow query never holds the
event loop (the lesson the whole app relearned when infer_keys froze it for
four minutes).
"""
from __future__ import annotations

import asyncio
import hashlib
import time

import sqlglot
from sqlglot import exp

from ..metadata import sample
from ..query_log import log_query_run_sync
from .validate import _dialect


def _engine_for(cfg: dict):
    """Seam, monkeypatched in tests — the interactive pool, because a person
    is waiting on this answer (the metadata pool is for background work)."""
    from ..engines import get_engine
    return get_engine(cfg)


def _cap_rows(sql: str, family: str, cap: int) -> str:
    tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    existing = tree.args.get("limit")
    if existing is None:
        return tree.limit(cap).sql(dialect=_dialect(family))
    # A model-written LIMIT larger than the cap (or a non-literal one we
    # can't compare) must still be floored — the cap is a hard ceiling on
    # rows returned, not merely a default for queries that omit LIMIT.
    try:
        existing_n = int(existing.expression.name)
    except (AttributeError, ValueError):
        return tree.limit(cap).sql(dialect=_dialect(family))
    if existing_n > cap:
        return tree.limit(cap).sql(dialect=_dialect(family))
    return sql


def _first_line(exc: Exception) -> str:
    lines = str(exc).strip().splitlines()
    return (lines[0].strip()[:200] if lines else type(exc).__name__)


def _guarded_interrupt(conn, done):
    """The watchdog timer's callback, factored out so its race-closing
    logic (H2 review finding) is directly unit-testable without spinning
    up DuckDB or racing real wall-clock timing.

    timer.cancel() cannot stop a callback that has already fired — if the
    timer thread wins the race and this runs in the window between the
    query genuinely finishing and the caller's cancel() call, a succeeded
    query would be reported as an interrupt error, and conn.interrupt()
    could run concurrently with conn.close(). `done` closes that window:
    the caller sets it the moment the query has finished (before any
    post-processing or close()), and this callback checks it before
    touching conn at all — so interrupt-vs-close can no longer overlap on
    the success path. On the failure path nothing changes: either the
    interrupt already happened (that's the point) or the query failed on
    its own, and conn.close() only runs after the query call returns
    either way."""
    def _interrupt():
        if not done.is_set():
            conn.interrupt()
    return _interrupt


def _run(sql: str, cfg: dict, family: str, *, org_id: int | None = None,
        data_source_id: int | None = None, dataset_id: int | None = None,
        ) -> tuple[list[dict] | None, str | None]:
    from sqlalchemy import text

    from ...core.config import settings

    start = time.monotonic()
    engine = _engine_for(cfg)
    conn = engine.connect()
    try:
        deadline = sample.statement_timeout_sql(
            family, settings.agent_statement_timeout_s)
        if deadline:
            conn.execute(text(deadline))
        capped = _cap_rows(sql, family, settings.agent_row_cap)
        # V5: EXPLAIN first — type errors, ambiguous columns and permission
        # failures surface here without touching a single row.
        conn.execute(text(f"EXPLAIN {capped}"))
        rows = [dict(r._mapping) for r in conn.execute(text(capped))]
        # T5: fire-and-forget telemetry -- this thread has no event loop of its
        # own (asyncio.to_thread), which is exactly what log_query_run_sync
        # needs. sql_hash, never the SQL text itself -- see QueryRun's docstring.
        log_query_run_sync(
            org_id=org_id, source_kind="agent", data_source_id=data_source_id,
            dataset_id=dataset_id, sql_hash=hashlib.sha256(capped.encode()).hexdigest(),
            rows_returned=len(rows), duration_ms=int((time.monotonic() - start) * 1000),
            executor="pushdown", cache_hit=False,
        )
        return rows, None
    except Exception as exc:
        # A cancelled statement leaves the connection in an aborted
        # transaction that pool_pre_ping cannot see. Discard it.
        conn.invalidate()
        return None, _first_line(exc)
    finally:
        conn.close()


async def execute_sql(sql: str, cfg: dict, family: str, *, org_id: int | None = None,
                      data_source_id: int | None = None, dataset_id: int | None = None,
                      ) -> tuple[list[dict] | None, str | None]:
    return await asyncio.to_thread(
        _run, sql, cfg, family,
        org_id=org_id, data_source_id=data_source_id, dataset_id=dataset_id,
    )


def _run_datasets(sql: str, frames: dict, *, org_id: int | None = None,
                  dataset_id: int | None = None,
                  ) -> tuple[list[dict] | None, str | None]:
    """Dataset mode's V5: one SQL surface (spec, multi-mode amendment) — the
    generated SQL always targets DuckDB, with each dataset's already-RLS'd
    frame registered as a table under the name the context (context.py's
    dataset_table_names) gave it. A fresh in-memory connection per call keeps
    this stateless and thread-safe under to_thread, same as the customer-DB
    path's own connection-per-call discipline."""
    import math
    import threading

    import numpy as np
    import pandas as pd

    import duckdb

    from ...core.config import settings

    start = time.monotonic()
    conn = duckdb.connect()
    # See _guarded_interrupt's docstring for why `done` (not just
    # timer.cancel()) is required to close the interrupt-vs-close race.
    done = threading.Event()
    timer = threading.Timer(settings.agent_statement_timeout_s,
                            _guarded_interrupt(conn, done))
    try:
        # Defence in depth: even if a hallucinated or adversarial
        # read_csv('...')/read_parquet('...')/COPY ... call slipped past
        # the parser-level checks, DuckDB itself must be unable to touch
        # the local filesystem or network from this connection.
        conn.execute("SET enable_external_access=false")
        for name, frame in frames.items():
            conn.register(name, frame)
        capped = _cap_rows(sql, "duckdb", settings.agent_row_cap)
        # DuckDB has no statement-timeout pragma (unlike the customer-DB path
        # in _run above) — a watchdog timer is the only way to bound a
        # pathological query. conn.interrupt() from another thread makes the
        # running query raise, which the except below turns into the normal
        # (None, error) tuple, same shape as any other failed dataset query.
        timer.start()
        result = conn.execute(capped).fetchdf()
        # The fetch has completed successfully — close the interrupt window
        # before any further work touches conn.
        done.set()
        timer.cancel()
        # NaN/NaT -> None so the rows are JSON-safe, and numpy scalar types
        # (int64/float64) -> native Python, matching execute_sql's dict(...)
        # rows which SQLAlchemy already hands back as native types.
        # df.where(pd.notnull(df), None) alone is NOT enough: on a float64
        # column pandas coerces the injected None straight back to NaN
        # (dtype stays float64), so NaN survives to .item() as float('nan')
        # -- verified empirically, not assumed. The per-value NaN check
        # below is the real guard; .where() above only handles object/
        # datetime columns where None does stick.
        result = result.where(pd.notnull(result), None)
        rows = []
        for record in result.to_dict("records"):
            clean = {}
            for k, v in record.items():
                if isinstance(v, np.generic):
                    v = v.item()
                if isinstance(v, float) and math.isnan(v):
                    v = None
                clean[k] = v
            rows.append(clean)
        # T5: same fire-and-forget telemetry as _run above -- this thread has
        # no event loop of its own (asyncio.to_thread).
        log_query_run_sync(
            org_id=org_id, source_kind="agent", data_source_id=None,
            dataset_id=dataset_id, sql_hash=hashlib.sha256(capped.encode()).hexdigest(),
            rows_returned=len(rows), duration_ms=int((time.monotonic() - start) * 1000),
            executor="duckdb", cache_hit=False,
        )
        return rows, None
    except Exception as exc:
        return None, _first_line(exc)
    finally:
        # Backstop, not the guard: on the success path `done` is already
        # set (so a not-yet-fired timer becomes a no-op) and on the
        # failure path the interrupt either already ran or never needed
        # to. Either way this cancel just avoids leaking a live timer.
        timer.cancel()
        conn.close()


async def execute_on_datasets(sql: str, frames: dict, *, org_id: int | None = None,
                              dataset_id: int | None = None,
                              ) -> tuple[list[dict] | None, str | None]:
    return await asyncio.to_thread(
        _run_datasets, sql, frames, org_id=org_id, dataset_id=dataset_id,
    )


def sanity_check(rows: list[dict], question: str) -> str | None:
    """Empty / absurd / oversized (spec: sanity node). A concern is a string
    for the answer to CARRY, not a failure — an empty result may be the true
    answer, but the person deserves to know it looked odd."""
    from ...core.config import settings

    if not rows:
        return "the query returned no rows — the answer may be 'none', or a filter may be wrong"
    if len(rows) >= settings.agent_row_cap:
        return (f"the result hit the {settings.agent_row_cap}-row cap and is "
                "probably truncated")
    values = [v for r in rows for v in r.values()]
    if values and all(v is None for v in values):
        return "every value in the result is NULL"
    return None
