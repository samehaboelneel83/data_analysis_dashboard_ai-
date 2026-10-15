"""Automated analysis runs, from the product (E12).

The automation runner (`services/automation_runner.py`) could profile a
dataset, describe it, scan it, propose a dashboard, review the proposal,
compose the report and tell its owner -- durable, resumable and held for a
person when review says no -- but nothing in the product could start one,
watch one or answer one: no endpoint created a run, and a held run's
notification linked nowhere. These are its controls:

  POST /automation/runs                 start a run on a dataset
  GET  /automation/runs                 the runs the caller may see
  GET  /automation/runs/{id}            one run, step by step
  POST /automation/runs/{id}/approve    a held run: continue
  POST /automation/runs/{id}/reject     a held run: stop
  POST /automation/runs/{id}/cancel     stop a run that has not finished
  POST /automation/runs/{id}/retry      a failed step: try again now

A run is its creator's: the steps read the dataset as them (row rules and
denied columns included), so only they -- or an org admin -- may see, answer
or stop it, and starting one is authoring on the dataset, as training a
model is. Every action is audited.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import require_dataset_capability, require_dataset_read
from ..core.database import get_db
from ..dependencies import get_current_user
from ..models.models import AutomationRun, AutomationStep, Dataset, User
from ..services import automation_runner as runner
from ..services.audit import record as audit
from ..services.notifications import notify

router = APIRouter(prefix="/automation", tags=["automation"])

#: Plain words for the seven steps, for the run page.
STEP_LABELS = runner.STEP_LABELS


class StartRun(BaseModel):
    dataset_id: int


class RejectRun(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _is_admin(user: User) -> bool:
    return bool(user.role and user.role.is_org_admin)


async def _visible_run(db: AsyncSession, run_id: int, user: User) -> AutomationRun:
    run = await db.get(AutomationRun, run_id)
    if run is None or run.org_id != user.org_id or (
            run.created_by != user.id and not _is_admin(user)):
        raise HTTPException(404, "Run not found")
    return run


async def _out(db: AsyncSession, run: AutomationRun, *, detail: bool = False) -> dict:
    steps = (await db.execute(select(AutomationStep).where(AutomationStep.run_id == run.id)
                              .order_by(AutomationStep.order))).scalars().all()
    ds = await db.get(Dataset, run.subject_id) if run.subject_type == "dataset" and run.subject_id else None
    sentence, link = runner.describe_run(run) if run.status in ("done", runner.NEEDS_REVIEW) else (None, None)
    out = {
        "id": run.id, "status": run.status, "trigger": run.trigger,
        "created_by": run.created_by,
        "dataset": {"id": ds.id, "name": ds.name} if ds is not None and ds.org_id == run.org_id else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error, "summary": sentence,
        "widgets_accepted": run.widgets_accepted, "widgets_rejected": run.widgets_rejected,
        "result_report": ({"id": run.result_report_id, "name": run.result_report_name}
                          if run.result_report_id else None),
        "steps": [{"name": s.name, "label": STEP_LABELS.get(s.name, s.name), "order": s.order,
                   "status": s.status, "attempts": s.attempts or 0, "error": s.error,
                   "next_attempt_at": s.next_attempt_at.isoformat() if s.next_attempt_at else None,
                   "started_at": s.started_at.isoformat() if s.started_at else None,
                   "finished_at": s.finished_at.isoformat() if s.finished_at else None}
                  for s in steps],
    }
    if detail:
        out.update({
            "proposal_path": run.proposal_path,
            "rejection_reasons": run.rejection_reasons or [],
        })
    return out


@router.post("/runs", status_code=201)
async def start_run(body: StartRun, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Start an automated analysis of a dataset, as the caller.

    One unfinished run per dataset: a second request gets a 409 naming the
    run already going, rather than a second report built from the same rows."""
    await require_dataset_read(db, user, body.dataset_id)
    ds = await db.get(Dataset, body.dataset_id)
    if ds is None or ds.org_id != user.org_id:
        raise HTTPException(404, "Dataset not found")
    await require_dataset_capability(db, user, body.dataset_id, "data")
    if not ds.filename and not (ds.mode == "directquery" and ds.data_source_id):
        raise HTTPException(400, "This dataset has no data behind it to analyse")
    active = (await db.execute(select(AutomationRun).where(
        AutomationRun.org_id == user.org_id, AutomationRun.subject_type == "dataset",
        AutomationRun.subject_id == ds.id,
        AutomationRun.status.in_([*runner.ACTIVE_RUN_STATUSES, runner.NEEDS_REVIEW]))
        .order_by(AutomationRun.id.desc()))).scalars().first()
    if active is not None:
        raise HTTPException(409, {"code": "run_active", "run_id": active.id,
                                  "message": f"An automated analysis of \"{ds.name}\" is already "
                                             f"{active.status.replace('_', ' ')}."})
    user_id = user.id
    run = await runner.create_run(db, org_id=user.org_id, created_by=user_id, trigger="manual",
                                  subject_type="dataset", subject_id=ds.id)
    await audit(db, user, "automation.start", "automation_run", run.id, f"dataset {ds.id}: {ds.name}")
    await db.commit()
    return await _out(db, run)


@router.get("/runs")
async def list_runs(dataset_id: int | None = None, limit: int = 50,
                    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Newest first: the caller's own runs, or every run in the org for an admin."""
    q = select(AutomationRun).where(AutomationRun.org_id == user.org_id)
    if not _is_admin(user):
        q = q.where(AutomationRun.created_by == user.id)
    if dataset_id is not None:
        q = q.where(AutomationRun.subject_type == "dataset", AutomationRun.subject_id == dataset_id)
    runs = (await db.execute(q.order_by(AutomationRun.id.desc()).limit(max(1, min(limit, 200))))).scalars().all()
    return [await _out(db, r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return await _out(db, await _visible_run(db, run_id, user), detail=True)


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """A run held at review: build the report from what passed."""
    run = await _visible_run(db, run_id, user)
    if run.status == runner.NEEDS_REVIEW and not (run.widgets_accepted or 0):
        # Found live: a run whose proposal step produced nothing was held with
        # 0 kept and 0 rejected, and approving it would build an empty report.
        raise HTTPException(409, "Nothing passed review, so there is no report to build. Stop this run.")
    try:
        await runner.approve_review(db, run)
    except ValueError:
        raise HTTPException(409, "Only a run waiting for a decision can be approved")
    await audit(db, user, "automation.approve", "automation_run", run.id, None)
    await db.commit()
    return await _out(db, run, detail=True)


@router.post("/runs/{run_id}/reject")
async def reject_run(run_id: int, body: RejectRun | None = None, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    run = await _visible_run(db, run_id, user)
    reason = (body.reason if body else None) or "rejected at review"
    try:
        await runner.reject_review(db, run, reason=reason)
    except ValueError:
        raise HTTPException(409, "Only a run waiting for a decision can be rejected")
    await audit(db, user, "automation.reject", "automation_run", run.id, reason)
    await db.commit()
    return await _out(db, run, detail=True)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Stop a run that has not finished. A step already running finishes, but
    the run does not go on to the next one (the runner keeps `cancelled`)."""
    run = await _visible_run(db, run_id, user)
    if run.status in runner.TERMINAL_RUN_STATUSES:
        return await _out(db, run, detail=True)
    res = await db.execute(update(AutomationRun).where(
        AutomationRun.id == run.id, AutomationRun.status.notin_(runner.TERMINAL_RUN_STATUSES))
        .values(status="cancelled", error="cancelled by " + (user.email or "a user"),
                finished_at=datetime.utcnow()).execution_options(synchronize_session=False))
    if res.rowcount:
        runner.discard_run_artifacts(run.org_id, run.id)
        await audit(db, user, "automation.cancel", "automation_run", run.id, None)
        if run.created_by is not None and run.created_by != user.id:
            # AD-03: someone else stopped this person's run; they should know.
            await db.refresh(run)
            text, link = runner.describe_run(run)
            await notify(db, run.org_id, run.created_by, "automation", text, link)
    await db.commit()
    await db.refresh(run)
    return await _out(db, run, detail=True)


#: AD-22: the runs a person may delete or retry -- stopped ones.
STOPPED = ("failed", "cancelled")


async def _active_twin(db: AsyncSession, run: AutomationRun) -> AutomationRun | None:
    """Another unfinished run of the same dataset (one at a time, as on start)."""
    return (await db.execute(select(AutomationRun).where(
        AutomationRun.org_id == run.org_id, AutomationRun.subject_type == run.subject_type,
        AutomationRun.subject_id == run.subject_id, AutomationRun.id != run.id,
        AutomationRun.status.in_([*runner.ACTIVE_RUN_STATUSES, runner.NEEDS_REVIEW])))).scalars().first()


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """AD-22: remove a stopped (failed or cancelled) run, its steps and any
    artifacts left on disk. A run still going, held for a decision or done
    is not deletable here."""
    run = await _visible_run(db, run_id, user)
    if run.status not in STOPPED:
        raise HTTPException(409, "Only a stopped run (failed or cancelled) can be deleted")
    runner.discard_run_artifacts(run.org_id, run.id)
    for st in (await db.execute(select(AutomationStep).where(AutomationStep.run_id == run.id))).scalars().all():
        await db.delete(st)
    await audit(db, user, "automation.delete", "automation_run", run.id, f"was {run.status}")
    await db.delete(run)
    await db.commit()


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: int, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """A failed step waiting out its backoff: try it on the next tick instead.

    AD-22: a CANCELLED run starts again from its first step. Cancelling
    discarded its artifacts, so no earlier step's output can be reused."""
    run = await _visible_run(db, run_id, user)
    if run.status == "cancelled":
        if await _active_twin(db, run) is not None:
            raise HTTPException(409, "Another automated analysis of this dataset is already going")
        for st in (await db.execute(select(AutomationStep).where(AutomationStep.run_id == run.id))).scalars().all():
            st.status, st.output_ref, st.error = "pending", None, None
            st.attempts, st.next_attempt_at, st.started_at, st.finished_at = 0, None, None, None
        run.status, run.error, run.finished_at = "pending", None, None
        run.widgets_accepted = run.widgets_rejected = None
        run.rejection_reasons = run.raw_proposals = run.proposal_path = None
        await audit(db, user, "automation.retry", "automation_run", run.id, "restarted after a cancel")
        await db.commit()
        await db.refresh(run)
        return await _out(db, run, detail=True)
    if run.status != "failed":
        raise HTTPException(409, "Only a failed or cancelled run can be retried")
    step = (await db.execute(select(AutomationStep).where(
        AutomationStep.run_id == run.id, AutomationStep.output_ref.is_(None))
        .order_by(AutomationStep.order))).scalars().first()
    if step is not None:
        step.next_attempt_at = None
    await audit(db, user, "automation.retry", "automation_run", run.id, step.name if step else None)
    await db.commit()
    return await _out(db, run, detail=True)
