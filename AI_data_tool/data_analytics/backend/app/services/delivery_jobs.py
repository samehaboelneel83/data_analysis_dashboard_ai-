"""Scheduled deliveries as durable jobs, each occurrence sent at most once (E12).

The scheduler used to send due deliveries inside its own tick. Two things
could then send one delivery twice:

* Two API processes. Each tick computed the due list, then took a per-item
  advisory lock for the run. The lock stopped two sends from OVERLAPPING, not
  from happening one after the other: the second process, holding the stale
  due list, got the lock once the first released it and sent again.
* A restart between sending and recording. The row still said "due", so the
  next tick sent again.

Now the tick only enqueues: one `delivery.schedule` job per due occurrence,
keyed `delivery:<schedule>:<last run it follows>:<failures>`, so every process
that sees the same occurrence names the same job and the jobs table's unique
key keeps one. The job then CLAIMS the occurrence before sending: a
compare-and-set on the schedule row (`last_run_at` still the value the
occurrence follows -> now, status "sending (job N)"), committed in the same
transaction as a fenced write to its own job row. Whoever wins sends; anyone
else -- a second job, a racing process, an author's "Send now" in between --
finds `last_run_at` moved on and skips.

At most once, deliberately. If the process dies after the claim, the resumed
job finds its own "sending" mark and does NOT send again: whether the email
left is unknown, and a second copy in a customer's inbox is worse than a
visible "interrupted, not resent" on the schedule, which the author can
answer with Send now. A failure before the claim (the report would not build)
fails the job, records the failure for the scheduler's backoff, and the next
due tick enqueues a fresh job (the failure count is in the key).

The job runs as the schedule's creator, as the inline run did: row-level
security and page visibility are the creator's, resolved at send time by
`delivery.run_schedule`, which this calls unchanged.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from ..models.models import Report, ReportSchedule, User
from . import jobs

log = logging.getLogger(__name__)

DELIVERY_JOB_KIND = "delivery.schedule"

#: How close two `last_run_at` readings must be to name the same run. The
#: value comes from the row itself, so this only absorbs a driver's rounding.
_SAME_RUN = timedelta(seconds=1)


def _naive_utc(dt: datetime | None) -> datetime | None:
    from .refresh_scheduler import _as_utc_naive
    return _as_utc_naive(dt)


def _parse(stamp: str | None) -> datetime | None:
    return datetime.fromisoformat(stamp) if stamp else None


def occurrence_key(schedule_id: int, last_run_at: datetime | None, failures: int) -> str:
    """The idempotency key for the delivery that follows `last_run_at`."""
    base = _naive_utc(last_run_at)
    stamp = base.strftime("%Y%m%dT%H%M%S") if base else "first"
    return f"delivery:{schedule_id}:{stamp}:{failures}"


async def enqueue_due(db, sched: ReportSchedule) -> tuple[object, bool] | None:
    """Queue the delivery a due schedule owes; `(job, created)`.

    None when the schedule has no creator to run as -- the caller runs it
    inline, where `run_schedule` disables it rather than sending as nobody."""
    creator = (await db.execute(select(User).options(selectinload(User.role))
                                .where(User.id == sched.creator_user_id))).scalar_one_or_none()
    if creator is None or creator.org_id != sched.org_id:
        return None
    from .refresh_scheduler import _failure_row
    failure = await _failure_row(db, "schedule", sched.id)
    failures = int(getattr(failure, "attempts", 0) or 0) if failure is not None else 0
    base = _naive_utc(sched.last_run_at)
    report = await db.get(Report, sched.report_id)
    subject = f"Scheduled delivery of \"{report.name if report else sched.report_id}\""
    return await jobs.enqueue(
        db, user=creator, kind=DELIVERY_JOB_KIND, subject=subject,
        inputs={"schedule_id": sched.id, "after": base.isoformat() if base else None},
        idempotency_key=occurrence_key(sched.id, base, failures),
        # Retrying a delivery is the scheduler's decision (backoff, then a
        # new job), not the worker's: a resumed attempt must not send again.
        max_attempts=2)


def _sending_mark(job_id: int) -> str:
    return f"sending (job {job_id})"


@jobs.register(DELIVERY_JOB_KIND)
async def run_delivery_job(ctx: jobs.JobContext) -> None:
    from .delivery import run_schedule
    from .refresh_scheduler import clear_failure, record_failure

    schedule_id = int(ctx.inputs["schedule_id"])
    after = _parse(ctx.inputs.get("after"))
    async with ctx.session_factory() as db:
        sched = await db.get(ReportSchedule, schedule_id)
        if sched is None or sched.org_id != ctx.org_id:
            await ctx.complete(db, {"outcome": "skipped", "reason": "the schedule no longer exists"})
            await db.commit()
            return

        # ── Claim the occurrence, or learn someone already has ──────────────
        now = datetime.utcnow()
        still = (ReportSchedule.last_run_at.is_(None) if after is None else
                 ReportSchedule.last_run_at.between(after - _SAME_RUN, after + _SAME_RUN))
        claimed = await db.execute(
            update(ReportSchedule).where(ReportSchedule.id == schedule_id, still)
            .values(last_run_at=now, last_status=_sending_mark(ctx.job_id))
            .execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            await db.rollback()
            sched = await db.get(ReportSchedule, schedule_id)
            await db.refresh(sched)
            if sched.last_status == _sending_mark(ctx.job_id):
                # This job claimed it on an earlier attempt and the server
                # stopped before the outcome was recorded.
                sched.last_status = ("interrupted while sending: not resent, so no one gets it "
                                     "twice. Use Send now to deliver it.")
                await ctx.complete(db, {"outcome": "interrupted"})
                await db.commit()
                return
            await ctx.complete(db, {"outcome": "skipped",
                                    "reason": "already delivered for this occurrence"})
            await db.commit()
            return
        # The claim and a fenced write to this job commit together: a worker
        # that lost its lease cannot claim, so two attempts cannot both send.
        await ctx.mark(db, "sending")
        await db.commit()

        # ── Send, exactly as the inline run did ─────────────────────────────
        await db.refresh(sched)
        try:
            await run_schedule(db, sched)
        except Exception as e:  # noqa: BLE001 - recorded for backoff, then failed
            await db.rollback()
            await record_failure(db, "schedule", schedule_id, str(e))
            raise jobs.JobError(f"The delivery could not be built: {e}", code="build_failed")
        await clear_failure(db, "schedule", schedule_id)
        status = sched.last_status
        await ctx.complete(db, {"outcome": "sent", "status": status})
        await db.commit()
