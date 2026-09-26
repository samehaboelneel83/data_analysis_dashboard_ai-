"""Drift over time: each champion checked daily, the checks kept (E13).

A drift check compared a model version with today's rows on demand, and the
answer was gone when the panel closed: nobody could see that a predictor had
been creeping for three weeks. Now every check -- the daily one the
scheduler queues for each champion, and each one a person asks for -- is kept
on the version's card (`drift_history`, newest last, the last 90), so the
panel can show the trend.

The daily check runs as a durable job AS THE PERSON WHO TRAINED the version:
a model may only be used by someone who sees the rows it saw
(services/model_access.py), and its trainer is who that was. If they no
longer do -- a row rule changed, their account is gone -- the job fails with
the reason and nothing is recorded.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from ..models.models import Dataset, PredictionModel, User
from . import jobs

MODEL_DRIFT_KIND = "model.drift"
HISTORY_CAP = 90
DAILY = timedelta(hours=24)


def snapshot(report: dict, at: datetime | None = None) -> dict:
    feats = report.get("features") or []
    psis = [f["psi"] for f in feats if f.get("psi") is not None]
    return {"at": (at or datetime.utcnow()).replace(microsecond=0).isoformat() + "Z",
            "overall": report.get("overall"), "rows": report.get("rows"),
            "max_psi": round(max(psis), 4) if psis else None,
            "features": {f["feature"]: f.get("psi") for f in feats}}


def history_of(model: PredictionModel) -> list[dict]:
    return list((model.card or {}).get("drift_history") or [])


def record(model: PredictionModel, snap: dict) -> list[dict]:
    """Append a check to the version's card (a new dict, so the JSON column
    is seen as changed); the oldest go past HISTORY_CAP."""
    history = [*history_of(model), snap][-HISTORY_CAP:]
    model.card = {**(model.card or {}), "drift_history": history}
    return history


def _last_at(model: PredictionModel) -> datetime | None:
    h = history_of(model)
    if not h:
        return None
    try:
        return datetime.fromisoformat(h[-1]["at"].rstrip("Z"))
    except (KeyError, ValueError):
        return None


async def enqueue_daily(session_factory, now: datetime | None = None) -> int:
    """Queue a check for every champion with a training profile whose last
    check is a day old (or that has none). One key per model per day, so
    every API process's scheduler names the same job."""
    now = now or datetime.utcnow()
    queued = 0
    async with session_factory() as db:
        champions = (await db.execute(select(PredictionModel).where(
            PredictionModel.status == "champion"))).scalars().all()
        for m in champions:
            if not (m.card or {}).get("feature_profile") or m.created_by is None:
                continue
            last = _last_at(m)
            if last is not None and now - last < DAILY:
                continue
            user = await db.get(User, m.created_by)
            if user is None:
                continue
            _job, created = await jobs.enqueue(
                db, user=user, kind=MODEL_DRIFT_KIND, inputs={"model_id": m.id},
                subject=f"Drift check: {m.name} v{m.version or 1}",
                idempotency_key=f"drift:{m.id}:{now.date().isoformat()}", max_attempts=1)
            queued += int(created)
    return queued


@jobs.register(MODEL_DRIFT_KIND)
async def run_drift_job(ctx: jobs.JobContext) -> None:
    from .analysis.model_store import drift_report
    from .model_access import ModelAccessError, secured_frame, usable_model

    model_id = int(ctx.inputs["model_id"])
    async with ctx.session_factory() as db:
        user = await ctx.load_user(db)
        if user is None:
            raise jobs.JobError("The person who trained this version can no longer use it.", code="forbidden")
        model = await db.get(PredictionModel, model_id)
        if model is None or model.org_id != ctx.org_id:
            raise jobs.JobError("The model version is gone.", code="not_found")
        profile = (model.card or {}).get("feature_profile")
        if not profile:
            raise jobs.JobError("This version has no training profile to compare with.", code="refused")
        ds = await db.get(Dataset, model.dataset_id)
        try:
            await usable_model(db, user, model.dataset_id, model_id)
            await ctx.checkpoint("reading")
            frame = await secured_frame(db, user, ds)
        except ModelAccessError as e:
            raise jobs.JobError(e.message, code="refused")
    await ctx.checkpoint("comparing", rows=len(frame))
    report = await asyncio.to_thread(drift_report, profile, frame)
    async with ctx.session_factory() as db:
        model = await db.get(PredictionModel, model_id)
        if model is None:
            raise jobs.JobError("The model version is gone.", code="not_found")
        snap = snapshot(report)
        record(model, snap)
        await ctx.complete(db, {"model_id": model_id, "overall": snap["overall"],
                                "max_psi": snap["max_psi"], "rows": snap["rows"]})
        await db.commit()
