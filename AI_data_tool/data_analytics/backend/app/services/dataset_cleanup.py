"""What a dataset leaves behind, removed in one place.

A dataset row cascades at the database (aggregates, columns, manifests), but
two things do not: its CSV and parquet sidecar on disk, and its
`ScheduleFailure` rows, which are keyed (kind, item_id) with no FK. Both the
dataset delete and the data-source delete need the same sweep, and a router
cannot import another router, so it lives here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, select

from .frame_cache import remove_parquet_sidecar


async def discard_dataset_artifacts(db, datasets: Iterable) -> int:
    """Unlink each dataset's file and sidecar and delete its failure rows.
    Does not commit. Returns how many files were removed."""
    from ..models.models import ScheduleFailure
    removed = 0
    ids = []
    for ds in datasets:
        ids.append(ds.id)
        if ds.filename:
            if Path(ds.filename).exists():
                removed += 1
            Path(ds.filename).unlink(missing_ok=True)
            remove_parquet_sidecar(ds.filename)
    if ids:
        await db.execute(delete(ScheduleFailure).where(
            ScheduleFailure.kind == "dataset", ScheduleFailure.item_id.in_(ids)))
    return removed
