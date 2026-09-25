"""Durable jobs: list, inspect, cancel and retry (services/jobs.py).

Who sees a job: the person who queued it, and their org's admins. Anyone else
gets 404, the same "does not exist / not yours" answer org scoping gives.
Starting a job is not here: each workload has its own endpoint that validates
its inputs and enqueues (e.g. POST /data-sources/{id}/import-jobs).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..dependencies import get_current_user
from ..models.models import Job, User
from ..schemas.schemas import JobOut
from ..services import jobs as job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _is_admin(user: User) -> bool:
    return bool(user.role and user.role.is_org_admin)


async def _visible_job(db: AsyncSession, job_id: int, user: User) -> Job:
    job = await db.get(Job, job_id)
    if job is None or job.org_id != user.org_id or (
            job.created_by != user.id and not _is_admin(user)):
        raise HTTPException(404, "Job not found")
    return job


@router.get("", response_model=list[JobOut])
async def list_jobs(kind: Optional[str] = None, state: Optional[str] = None,
                    active: bool = False, limit: int = Query(50, ge=1, le=200),
                    db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Newest first. `active=true` keeps only queued and running jobs."""
    q = select(Job).where(Job.org_id == current_user.org_id)
    if not _is_admin(current_user):
        q = q.where(Job.created_by == current_user.id)
    if kind:
        q = q.where(Job.kind == kind)
    if state:
        if state not in job_service.STATES:
            raise HTTPException(400, f"Unknown state '{state}'")
        q = q.where(Job.state == state)
    if active:
        q = q.where(Job.state.in_([job_service.QUEUED, job_service.RUNNING]))
    rows = (await db.execute(q.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit))).scalars().all()
    return rows


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    job = await _visible_job(db, job_id, current_user)
    # Another process moves this row; never answer from a stale identity map.
    await db.refresh(job)
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: int, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """Queued: cancelled now. Running: stops at its next checkpoint, with
    nothing written. Finished: returned unchanged."""
    job = await _visible_job(db, job_id, current_user)
    await db.refresh(job)
    return await job_service.request_cancel(db, job, current_user)


@router.post("/{job_id}/retry", response_model=JobOut, status_code=202)
async def retry_job(job_id: int, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """A NEW job with the same inputs; the failed one stays as it was.

    The retry runs as the person retrying it, so their permissions -- checked
    again when it runs -- are the ones that apply."""
    job = await _visible_job(db, job_id, current_user)
    await db.refresh(job)
    try:
        return await job_service.retry(db, job, current_user)
    except job_service.JobError as e:
        raise HTTPException(409, str(e))
