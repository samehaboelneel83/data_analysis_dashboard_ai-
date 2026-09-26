"""Batch scoring as a durable job: a model version scores a dataset (E13).

The score endpoint answers in the request, capped at 50,000 rows, and keeps
nothing. A batch score is the other half of a model lifecycle: every row the
person may see, scored by one named version, kept as a new dataset -- the
dataset's columns plus the prediction, named after the model and version --
so the output can be charted, joined and traced to what made it.

Runs as the person who queued it, checked again when it runs (a share
revoked in between ends it): `model_access.usable_model` and
`secured_frame`, the same functions the request path uses. The new dataset is
created in the same transaction as the job's fenced success, so an attempt
that lost its lease leaves nothing behind.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

from ..models.models import Dataset, DatasetColumn
from . import jobs

MODEL_SCORE_KIND = "model.score"
#: column_meta key on a scored dataset: the dataset and model version it came from.
SCORED_BY_KEY = "__scored_by__"


@jobs.register(MODEL_SCORE_KIND)
async def run_score_job(ctx: jobs.JobContext) -> None:
    from ..core.capability import can_read_dataset
    from .analysis.model_store import ModelStoreError, score_frame
    from .analytics import detect_types
    from .frame_cache import remove_parquet_sidecar, write_parquet_sidecar
    from .ingest import missing_pct
    from .model_access import ModelAccessError, secured_frame, usable_model
    from .quotas import QuotaExceeded, enforce_storage_quota
    from .upload_store import allocate_path

    dataset_id = int(ctx.inputs["dataset_id"])
    model_id = int(ctx.inputs["model_id"])
    async with ctx.session_factory() as db:
        user = await ctx.load_user(db)
        if user is None:
            raise jobs.JobError("The person who queued this scoring can no longer use it.", code="forbidden")
        ds = await db.get(Dataset, dataset_id)
        if ds is None or ds.org_id != ctx.org_id or not await can_read_dataset(db, user, dataset_id):
            raise jobs.JobError("The dataset is gone, or no longer readable by you.", code="not_found")
        try:
            model, pkg = await usable_model(db, user, dataset_id, model_id)
            await ctx.checkpoint("reading")
            frame = await secured_frame(db, user, ds)
        except ModelAccessError as e:
            raise jobs.JobError(e.message, code="refused")
        name, version, target = model.name, model.version or 1, model.target
        org_id, user_id, ds_name = ds.org_id, user.id, ds.name

    await ctx.checkpoint("scoring", rows=len(frame))
    try:
        out = await asyncio.to_thread(score_frame, pkg, frame)
    except ModelStoreError as e:
        raise jobs.JobError(str(e), code="refused")
    column = f"predicted_{target}"
    while column in frame.columns:
        column += "_"
    frame = frame.copy()
    frame[column] = out["predictions"]

    await ctx.checkpoint("writing", rows=len(frame))

    def _write():
        path = allocate_path(org_id, "scored.csv")
        tmp = path.with_name(path.name + ".tmp")
        types = detect_types(frame)
        frame.to_csv(tmp, index=False)
        os.replace(tmp, path)
        write_parquet_sidecar(str(path))
        return path, types

    path, types = await asyncio.to_thread(_write)
    try:
        async with ctx.session_factory() as db:
            try:
                await enforce_storage_quota(db, org_id, Path(path).stat().st_size)
            except QuotaExceeded as e:
                raise jobs.JobError(str(e.detail), code="quota")
            scored = Dataset(
                name=f"{ds_name} scored by {name} v{version}"[:255],
                description=(f"Predictions of {target} by the saved model \"{name}\" v{version} "
                             f"(job {ctx.job_id}), over the rows of \"{ds_name}\" its author could see."),
                filename=str(path), row_count=len(frame), col_count=len(frame.columns),
                file_size=Path(path).stat().st_size, org_id=org_id, created_by=user_id,
                mode="import", last_refreshed_at=datetime.utcnow(),
                # Where the rows came from, for the catalog and lineage (E06).
                # Not the prep recipe key: a scoring is not replayable by prep.
                column_meta={SCORED_BY_KEY: {"source_dataset_id": dataset_id, "model_id": model_id,
                                             "model_name": name, "version": version, "job_id": ctx.job_id}})
            db.add(scored)
            await db.flush()
            for col, dtype in types.items():
                db.add(DatasetColumn(dataset_id=scored.id, name=col, dtype=dtype,
                                     missing_pct=missing_pct(frame[col]), stats={}))
            await ctx.complete(db, {
                "dataset_id": scored.id, "rows": len(frame), "column": column,
                "model": {"id": model_id, "name": name, "version": version},
                "unseen_values": out.get("unseen_values") or {},
            })
            await db.commit()
    except BaseException:
        # Lease lost, or anything else before the commit: no dataset points
        # at the file, so it goes.
        Path(path).unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise
