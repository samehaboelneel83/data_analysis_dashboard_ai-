"""Row counts for live (DirectQuery) datasets (4.5).

A live dataset stores no rows, so the Datasets list and Overview said "—"
for "Current workforce" -- the one number an analyst checks first. The count
is one cheap `SELECT COUNT(*)` over the dataset's own SQL, cached on the
dataset (`row_count` + `column_meta.__live_count_at__`) and refreshed when
older than an hour, by an hourly sweep and on demand.

The count is the dataset's total, before row-level security: the same number
an imported dataset's `row_count` shows every reader.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..models.models import DataSource, Dataset

log = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=1)
STAMP = "__live_count_at__"


def _stamp_of(ds: Dataset) -> datetime | None:
    raw = (ds.column_meta or {}).get(STAMP)
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_stale(ds: Dataset, now: datetime | None = None) -> bool:
    t = _stamp_of(ds)
    return t is None or (now or datetime.now(timezone.utc)) - t > MAX_AGE


def _count_sync(cfg: dict, ds: Dataset) -> int:
    from sqlalchemy import text

    from . import connectors
    from .direct_query import RowFetchPlan, build_count_sql, get_engine
    dialect = connectors.sql_family_of(cfg)
    sql, params = build_count_sql(ds, RowFetchPlan(filters=[]), dialect)
    with get_engine(cfg).connect() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


async def refresh_live_count(db, ds: Dataset, *, force: bool = False) -> dict:
    """Count a live dataset's rows if the cached count is missing or stale."""
    if ds.mode != "directquery" or ds.data_source_id is None:
        return {"row_count": ds.row_count, "counted_at": None, "live": False}
    if not force and not is_stale(ds):
        return {"row_count": ds.row_count, "counted_at": (ds.column_meta or {}).get(STAMP), "live": True}
    source = await db.get(DataSource, ds.data_source_id)
    if source is None:
        return {"row_count": ds.row_count, "counted_at": None, "live": True,
                "error": "The connection behind this dataset no longer exists."}
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    try:
        n = await asyncio.to_thread(_count_sync, cfg, ds)
    except Exception as exc:  # noqa: BLE001 -- a dead source keeps the old count
        log.info("live count for dataset %s failed: %s", ds.id, exc)
        return {"row_count": ds.row_count, "counted_at": (ds.column_meta or {}).get(STAMP), "live": True,
                "error": "Could not reach the data source to count its rows."}
    stamp = datetime.now(timezone.utc).isoformat()
    ds.row_count = n
    ds.column_meta = {**(ds.column_meta or {}), STAMP: stamp}
    flag_modified(ds, "column_meta")
    await db.commit()
    return {"row_count": n, "counted_at": stamp, "live": True}


async def refresh_stale_live_counts(session_factory) -> int:
    """One sweep: recount every live dataset whose count is stale."""
    done = 0
    async with session_factory() as db:
        rows = (await db.execute(select(Dataset).where(
            Dataset.mode == "directquery", Dataset.data_source_id.is_not(None)))).scalars().all()
        for ds in rows:
            if is_stale(ds):
                got = await refresh_live_count(db, ds, force=True)
                done += 0 if got.get("error") else 1
    return done


async def run_live_count_loop(session_factory, every: float = 3600.0) -> None:
    """The hourly sweep, started with the app."""
    while True:
        try:
            await refresh_stale_live_counts(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- never let a sweep kill the loop
            log.exception("live count sweep failed")
        await asyncio.sleep(every)
