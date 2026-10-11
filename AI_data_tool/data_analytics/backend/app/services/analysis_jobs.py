"""A slow analysis as a durable job (services/jobs.py; docs/discovery/PLAN.md §X-4).

Most analyses answer inside a request. A few fit models -- groups of similar
rows searched over several sizes, a comparison of prediction models -- and on
a large table that is longer than a request should be held open for. Queued
as a job, the person can leave the page; the browser finds the job again and
shows the result when it is there.

Runs as the person who queued it, checked again when it runs: a dataset no
longer readable ends it. The frame is the one the request path uses
(`routers/analysis._secured_frame`: row rules, hidden columns, preparation
steps), so a job can never see more than the person could in the request.
The result is the same envelope the request returns, stored on the job row.
"""
from __future__ import annotations

import asyncio

from . import jobs

ANALYSIS_JOB_KIND = "analysis.run"
#: Rows from which a slow analysis is queued instead of run in the request.
#: Measured (scripts/bench_discovery.py, 2026-10-11): every slow analysis answers
#: in 0.1-5.4 s on 2,000,000 rows on the development machine, because each
#: samples before it fits. So the request is fine well past a million rows
#: there; the threshold leaves room for a slower host, not for this one.
BACKGROUND_ROWS = 1_000_000
#: Cost tier (services/discovery/capabilities.py) that counts as slow.
SLOW_TIER = 2


def background_rows() -> int:
    """The threshold as it is set now (Admin -> Settings -> Data import and limits)."""
    from ..core.config import settings
    return int(getattr(settings, "analysis_background_rows", BACKGROUND_ROWS) or 0)


def is_slow(name: str) -> bool:
    """A model-fitting analysis, by the registry's own cost tier."""
    from .discovery import capabilities as caps
    cap = caps.analysis(name)
    return cap is not None and cap.cost >= SLOW_TIER


def should_queue(name: str, rows: int | None, asked) -> bool:
    """`asked` is what the caller sent: True / False decide; "auto" (what the
    browser sends) queues a slow analysis on a large table and nothing else."""
    if asked is True:
        return True
    if asked == "auto":
        return is_slow(name) and background_rows() > 0 and (rows or 0) >= background_rows()
    return False


@jobs.register(ANALYSIS_JOB_KIND)
async def run_analysis_job(ctx: jobs.JobContext) -> None:
    from .analysis_contract import safe_clean
    from ..core.capability import can_read_dataset
    from ..models.models import Dataset
    from ..routers.analysis import _refuse_denied, _secured_frame, _strings_in
    from .analysis import registry

    dataset_id, name = int(ctx.inputs["dataset_id"]), str(ctx.inputs["name"])
    params = ctx.inputs.get("params") or {}
    await ctx.checkpoint("reading")
    async with ctx.session_factory() as db:
        user = await ctx.load_user(db)
        if user is None:
            raise jobs.JobError("The person who asked for this analysis can no longer use it.", code="forbidden")
        ds = await db.get(Dataset, dataset_id)
        if ds is None or ds.org_id != ctx.org_id or not await can_read_dataset(db, user, dataset_id):
            raise jobs.JobError("The dataset is gone, or no longer readable by you.", code="not_found")
        spec = registry.get(name)
        if spec is None or spec.handler is None:
            raise jobs.JobError(f"No analysis named '{name}' can be run.", code="refused")
        try:
            df, denied = await _secured_frame(dataset_id, db, user)
            _refuse_denied(_strings_in(params), denied)
        except Exception as exc:                             # noqa: BLE001
            # The router's own refusal (an HTTP error) becomes the job's, in its
            # words; told apart by shape so this service imports no web framework.
            if not (hasattr(exc, "status_code") and hasattr(exc, "detail")):
                raise
            raise jobs.JobError(str(exc.detail), code="refused")
    await ctx.checkpoint("computing", rows=int(len(df)))
    try:
        result = await asyncio.to_thread(registry.run_analysis, name, df, params)
    except (jobs.JobCancelled, jobs.LeaseLost):
        raise
    except (ValueError, TypeError, KeyError) as exc:
        # The analysis' own refusal, in its own words: the same 400 the request gives.
        raise jobs.JobError(str(exc)[:500], code="refused") from exc
    except Exception as exc:                                 # noqa: BLE001
        raise jobs.JobError(f"The analysis stopped: {type(exc).__name__}: {exc}"[:500], code="analysis_failed") from exc
    from .suggest_jobs import _json_safe
    envelope = _json_safe({"analysis": spec.name, "result_kind": spec.result_kind, "params": params,
                           "result": safe_clean(result), "dataset_id": dataset_id})
    async with ctx.session_factory() as db:
        await ctx.complete(db, envelope)
        await db.commit()
