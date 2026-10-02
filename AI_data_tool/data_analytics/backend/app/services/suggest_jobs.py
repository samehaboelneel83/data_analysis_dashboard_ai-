"""The analyst panel as a durable job (services/jobs.py).

A panel run is minutes of work -- one model call per lens, then every idea
drawn on the data -- too long to hold a dialog and a request open for. Queued
as a job, the person can close the dialog and come back; the dialog finds the
job again and shows its progress stages (facts, proposing, drawing,
selecting) and then the result.

Runs as the person who queued it, checked again when it runs: a dataset no
longer readable ends it. The frame is assembled by `suggest_inputs.prepare`,
the same function the request path uses, so a job can never see more rows or
columns than the person could in the dialog. Nothing is created: the result
is the proposal list, stored on the job row, and building a dashboard from
it is still the person's click.
"""
from __future__ import annotations

from ..models.models import Dataset
from . import jobs

PANEL_JOB_KIND = "suggest.panel"


@jobs.register(PANEL_JOB_KIND)
async def run_panel_job(ctx: jobs.JobContext) -> None:
    from ..core.capability import can_read_dataset
    from . import suggest_inputs as sug

    dataset_id = int(ctx.inputs["dataset_id"])
    await ctx.checkpoint("reading")
    async with ctx.session_factory() as db:
        user = await ctx.load_user(db)
        if user is None:
            raise jobs.JobError("The person who asked for these suggestions can no longer use them.",
                                code="forbidden")
        ds = await db.get(Dataset, dataset_id)
        if ds is None or ds.org_id != ctx.org_id or not await can_read_dataset(db, user, dataset_id):
            raise jobs.JobError("The dataset is gone, or no longer readable by you.", code="not_found")
        try:
            inputs = await sug.prepare(db, user, ds)
        except sug.SuggestUnavailable as exc:
            raise jobs.JobError(exc.message, code="refused")
        name = ds.name

    async def progress(stage: str, detail: dict) -> None:
        await ctx.checkpoint(stage, **detail)

    try:
        result = await sug.panel(inputs, ctx.inputs.get("goal") or None,
                                 int(ctx.inputs.get("size") or 24), progress=progress)
    except (jobs.JobCancelled, jobs.LeaseLost):
        raise
    except Exception as exc:                                 # noqa: BLE001
        # Said on the job, not only in the server log: "unexpected error" was
        # all an Olist run left behind (2026-10-02). jobs.sanitize_error masks
        # anything credential-shaped before it is stored.
        raise jobs.JobError(f"The analyst panel stopped: {type(exc).__name__}: {exc}"[:500],
                            code="panel_failed") from exc
    result["dataset_id"] = dataset_id
    result["dataset_name"] = name
    result = _json_safe(result)
    async with ctx.session_factory() as db:
        await ctx.complete(db, result)
        await db.commit()


def _json_safe(value):
    """The job row stores JSON: numpy numbers and timestamps become plain values."""
    import json
    import math

    def default(o):
        if hasattr(o, "item"):
            return o.item()
        if hasattr(o, "isoformat"):
            return o.isoformat()
        return str(o)

    def clean(o):
        if isinstance(o, float) and not math.isfinite(o):
            return None
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return o

    return clean(json.loads(json.dumps(value, default=default)))
