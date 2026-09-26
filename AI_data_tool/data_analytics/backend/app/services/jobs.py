"""Durable jobs: long work that outlives the request that asked for it.

The plan's `Job` contract (§8), built once and shared: E07's import queue is the
first workload, and E12's automation and E13's training are meant to move onto
the same rows rather than grow a second queue. `models.Job` describes the row;
this module is the only code that changes a job's `state`.

HOW A JOB RUNS
--------------
`enqueue` writes a `queued` row and returns at once. A worker loop
(`run_worker`, started in `main.lifespan`, one per API process) claims queued
rows and runs the handler registered for the job's `kind`.

**Claiming is a compare-and-set, not a lock.** `claim` issues
`UPDATE jobs SET state='running', lease_owner=<token> ... WHERE id=? AND
<still claimable>` and keeps the job only if that UPDATE changed one row. Two
workers racing for the same row cannot both win, on Postgres or SQLite, and no
advisory lock or long-held connection is needed.

**A lease, renewed while the work runs.** The winner gets `lease_expires_at`
LEASE_SECONDS ahead and a heartbeat task pushes it forward. A process that dies
stops renewing; once the lease has run out the row is claimable again and the
next claim is `attempt + 1`. That is how a restart resumes a job -- no startup
reaper, because with several API processes "running" is not proof of death.
After `max_attempts` interrupted attempts the job is failed as `interrupted`
instead of being retried forever.

**Fencing.** Every write a worker makes -- progress, the final state -- is
conditional on `lease_owner` still being its own token. A worker that lost its
lease (paused past it, or its host was presumed dead) cannot record an outcome.
A handler commits its effects in the SAME transaction as `succeeded`
(`JobContext.complete`), so the loser's effects roll back with its refused
state write: two overlapping attempts cannot both create the dataset.

**Cancellation is cooperative.** A queued job is cancelled at once. A running
one gets `cancel_requested`; the handler sees it at its next `checkpoint` and
stops there with nothing written. Work already inside a driver call (a long
source query) is not interrupted -- it is bounded by
`SOURCE_STATEMENT_TIMEOUT_S` -- and a handler past its point of no return
finishes normally. The row then says both: `succeeded`, `cancel_requested`.

**Errors are sanitized.** What a job stores is what a user may read:
credentials in connection strings are masked, the text is capped, and an
unexpected exception is stored as a generic sentence (its detail goes to the
log, not the row).

**Retry is a new row.** `inputs` is immutable, so retrying a failed or
cancelled job enqueues a fresh job with the same inputs and `retry_of` pointing
back. What a job ran with is always what its own row says.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from ..models.models import Job, User

log = logging.getLogger(__name__)

QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = (
    "queued", "running", "succeeded", "failed", "cancelled")
TERMINAL_STATES = frozenset({SUCCEEDED, FAILED, CANCELLED})
STATES = (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)

#: How long a claim holds without a heartbeat. A dead worker's job waits at
#: most this long before another worker resumes it.
LEASE_SECONDS = 60
#: Renewal cadence: three chances to renew before the lease runs out.
HEARTBEAT_SECONDS = 20
#: How often an idle worker looks for work.
POLL_SECONDS = 2
#: Jobs one process runs at once. Imports are I/O against customer databases
#: plus a CSV write; more than a couple per process mostly adds source load.
WORKER_CONCURRENCY = 2
#: Stored error text cap. The UI shows it; a driver can return pages.
ERROR_MAX_CHARS = 1000

Handler = Callable[["JobContext"], Awaitable[None]]
HANDLERS: dict[str, Handler] = {}


#: Modules whose import registers handlers. Listed here so the worker and
#: `enqueue` know every kind without depending on import order elsewhere.
HANDLER_MODULES = ("app.services.source_import", "app.services.refresh_jobs")


def load_handlers() -> None:
    import importlib
    for name in HANDLER_MODULES:
        importlib.import_module(name)


def register(kind: str) -> Callable[[Handler], Handler]:
    """Register the coroutine that runs jobs of `kind`."""
    def deco(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn
    return deco


class JobError(Exception):
    """A handler's refusal, worded for the person who queued the job.

    Raise this for the expected failures (the source rejected the query, the
    quota is full, the user may no longer import). Anything else that escapes
    a handler is stored as `unexpected` with a generic message.

    `detail` is what the person needs to act on the refusal, stored as the
    job's `result` (a refresh refused by a schema break carries the missing
    columns and their likely new names, so the page can offer the mapping).
    Like `message`, it must be fit for the person who queued the job."""

    def __init__(self, message: str, code: str = "refused", detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


class JobCancelled(Exception):
    """Raised by `checkpoint` when cancellation was requested."""


class LeaseLost(Exception):
    """This worker no longer owns the job; it must stop without writing."""


class IdempotencyConflict(Exception):
    """The idempotency key names a job with different inputs."""


_CRED_IN_URL = re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^@\s/]*@", re.I)
_SECRET_PAIR = re.compile(r"(?P<k>\b(?:password|passwd|pwd|secret|token|api[_-]?key)\b\s*[=:]\s*)"
                          r"(?P<q>['\"]?)[^\s'\";,&]+(?P=q)", re.I)


def sanitize_error(message: object) -> str:
    """What a stored job error may say: no credentials, bounded length."""
    text = str(message or "").strip()
    text = _CRED_IN_URL.sub(lambda m: m.group("scheme") + "***:***@", text)
    text = _SECRET_PAIR.sub(lambda m: m.group("k") + "***", text)
    if len(text) > ERROR_MAX_CHARS:
        text = text[:ERROR_MAX_CHARS - 1] + "…"
    return text


def _utcnow() -> datetime:
    return datetime.utcnow()


# ── Enqueue, cancel, retry (called from request handlers) ────────────────────

async def _find_by_key(db, org_id: int, key: str) -> Job | None:
    return (await db.execute(select(Job).where(
        Job.org_id == org_id, Job.idempotency_key == key))).scalar_one_or_none()


async def enqueue(db, *, user: User, kind: str, inputs: dict, subject: str | None = None,
                  idempotency_key: str | None = None, max_attempts: int = 3) -> tuple[Job, bool]:
    """Queue a job; return `(job, created)`.

    With an idempotency key the same request twice returns the first job
    (`created` False). The same key with different inputs is a client bug and
    raises IdempotencyConflict rather than silently answering with someone
    else's job. Commits: the job must exist before the response says so."""
    load_handlers()
    if kind not in HANDLERS:
        raise ValueError(f"No handler registered for job kind {kind!r}")
    key = (idempotency_key or "").strip() or None
    # Read before anything can roll back: a rollback expires `user`, and a
    # lazy reload from a plain attribute access fails on an async session.
    org_id, user_id = user.org_id, user.id

    async def _existing() -> Job | None:
        return None if key is None else await _find_by_key(db, org_id, key)

    found = await _existing()
    if found is None:
        job = Job(org_id=org_id, created_by=user_id, kind=kind, state=QUEUED,
                  subject=(subject or "")[:255] or None, inputs=dict(inputs),
                  idempotency_key=key, progress={"stage": "queued"},
                  attempt=0, max_attempts=max_attempts, cancel_requested=False,
                  created_at=_utcnow())
        db.add(job)
        try:
            await db.flush()
            from .audit import record
            await record(db, user, "job.enqueue", "job", job.id, f"{kind}: {job.subject or ''}")
            await db.commit()
            return job, True
        except IntegrityError:
            # Two identical requests raced past the lookup; the unique
            # constraint picked the winner. Answer with it. The rollback
            # expired the caller's user (and its role): reload both, so the
            # request that goes on using them does not trip over it.
            await db.rollback()
            await db.refresh(user)
            await db.refresh(user, ["role"])
            found = await _existing()
            if found is None:
                raise
    if found.kind != kind or (found.inputs or {}) != dict(inputs):
        raise IdempotencyConflict(
            "This idempotency key was already used for a different request")
    return found, False


async def request_cancel(db, job: Job, user: User) -> Job:
    """Cancel a queued job now; ask a running one to stop at its next checkpoint.

    A terminal job is returned unchanged -- cancelling something already
    finished is not an error, it is simply too late."""
    now = _utcnow()
    if job.state == QUEUED:
        res = await db.execute(update(Job).where(Job.id == job.id, Job.state == QUEUED).values(
            state=CANCELLED, cancel_requested=True, finished_at=now, updated_at=now,
            progress={"stage": "cancelled"}))
        if res.rowcount == 0:
            # A worker claimed it between the read and this write: fall
            # through to the running case.
            await db.execute(update(Job).where(Job.id == job.id, Job.state == RUNNING)
                             .values(cancel_requested=True, updated_at=now))
    elif job.state == RUNNING:
        await db.execute(update(Job).where(Job.id == job.id, Job.state == RUNNING)
                         .values(cancel_requested=True, updated_at=now))
    else:
        return job
    from .audit import record
    await record(db, user, "job.cancel", "job", job.id, f"{job.kind}: {job.subject or ''}")
    await db.commit()
    await db.refresh(job)
    return job


async def retry(db, job: Job, user: User) -> Job:
    """A new job with the same inputs. Only a failed or cancelled job may be
    retried: a running one is still trying, a succeeded one has its output."""
    if job.state not in (FAILED, CANCELLED):
        raise JobError("Only a failed or cancelled job can be retried", code="not_retryable")
    new = Job(org_id=job.org_id, created_by=user.id, kind=job.kind, state=QUEUED,
              subject=job.subject, inputs=dict(job.inputs or {}), progress={"stage": "queued"},
              attempt=0, max_attempts=job.max_attempts or 3, cancel_requested=False,
              retry_of=job.id, created_at=_utcnow())
    db.add(new)
    await db.flush()
    from .audit import record
    await record(db, user, "job.retry", "job", new.id, f"retry of job {job.id}: {job.subject or ''}")
    await db.commit()
    await db.refresh(new)
    return new


# ── Claiming and running (the worker side) ────────────────────────────────────

def new_worker_id() -> str:
    return f"{socket.gethostname()[:40]}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def _claimable(now: datetime):
    return or_(Job.state == QUEUED,
               and_(Job.state == RUNNING, Job.lease_expires_at < now))


async def claim(db, worker_id: str, now: datetime | None = None,
                kinds: set[str] | None = None) -> tuple[int, str] | None:
    """Take the oldest claimable job; return `(job_id, lease_token)` or None.

    Claimable means queued, or running under a lease that has run out (its
    worker died). A job that has used up its attempts, or whose cancel was
    requested before its worker died, is settled here instead of started."""
    now = now or _utcnow()
    kinds = kinds if kinds is not None else set(HANDLERS)
    if not kinds:
        return None
    rows = (await db.execute(
        select(Job.id, Job.state, Job.attempt, Job.max_attempts, Job.cancel_requested)
        .where(_claimable(now), Job.kind.in_(sorted(kinds)))
        .order_by(Job.created_at, Job.id).limit(10))).all()
    for job_id, state, attempt, max_attempts, cancel_requested in rows:
        was_interrupted = state == RUNNING
        if was_interrupted and (cancel_requested or (attempt or 0) >= (max_attempts or 1)):
            settled = CANCELLED if cancel_requested else FAILED
            values: dict[str, Any] = dict(state=settled, finished_at=now, updated_at=now,
                                          lease_owner=None, lease_expires_at=None,
                                          progress={"stage": settled})
            if settled == FAILED:
                values.update(error_code="interrupted",
                              error=f"The server stopped while this ran, {attempt} time(s). "
                                    "Retry it when the server is stable.")
            await db.execute(update(Job).where(Job.id == job_id, _claimable(now)).values(**values))
            await db.commit()
            continue
        token = f"{worker_id}:{uuid.uuid4().hex[:8]}"
        res = await db.execute(
            update(Job).where(Job.id == job_id, _claimable(now)).values(
                state=RUNNING, lease_owner=token,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                attempt=Job.attempt + 1, updated_at=now,
                progress={"stage": "starting", "resumed": was_interrupted}))
        await db.commit()
        if res.rowcount == 1:
            # started_at records the FIRST start; a resume keeps it.
            await db.execute(update(Job).where(Job.id == job_id, Job.started_at.is_(None))
                             .values(started_at=now))
            await db.commit()
            return job_id, token
    return None


async def _fenced_update(db, job_id: int, token: str, **values) -> bool:
    res = await db.execute(update(Job).where(
        Job.id == job_id, Job.state == RUNNING, Job.lease_owner == token).values(**values))
    return res.rowcount == 1


@dataclass
class JobContext:
    """What a handler gets: its inputs, and the only ways to touch its row."""
    job_id: int
    token: str
    kind: str
    org_id: int
    created_by: int | None
    inputs: dict
    attempt: int
    session_factory: Any
    #: Set by `complete`, for the runner's bookkeeping.
    completed: bool = field(default=False)

    async def checkpoint(self, stage: str, **detail) -> None:
        """Record progress; stop here if cancellation was requested.

        Raises JobCancelled (nothing after this point has run) or LeaseLost
        (another worker owns the job now)."""
        async with self.session_factory() as s:
            now = _utcnow()
            row = (await s.execute(select(Job.cancel_requested, Job.lease_owner, Job.state)
                                   .where(Job.id == self.job_id))).first()
            if row is None or row.state != RUNNING or row.lease_owner != self.token:
                raise LeaseLost()
            if row.cancel_requested:
                raise JobCancelled()
            ok = await _fenced_update(s, self.job_id, self.token, updated_at=now,
                                      progress={"stage": stage, **detail},
                                      lease_expires_at=now + timedelta(seconds=LEASE_SECONDS))
            await s.commit()
            if not ok:
                raise LeaseLost()

    async def complete(self, db, result: dict) -> None:
        """Mark the job succeeded INSIDE the caller's transaction, fenced.

        Call it just before committing the job's effects. If the lease is gone
        this raises LeaseLost and the caller's transaction must roll back, so
        the effects never land twice."""
        now = _utcnow()
        ok = await _fenced_update(db, self.job_id, self.token, state=SUCCEEDED, result=result,
                                  finished_at=now, updated_at=now, lease_expires_at=None,
                                  progress={"stage": "done"}, error=None, error_code=None)
        if not ok:
            raise LeaseLost()
        self.completed = True

    async def load_user(self, db) -> User | None:
        """The person who queued the job, as they are NOW -- permissions are
        checked at execution, not frozen at enqueue."""
        if self.created_by is None:
            return None
        from sqlalchemy.orm import selectinload
        user = (await db.execute(select(User).options(selectinload(User.role))
                                 .where(User.id == self.created_by))).scalar_one_or_none()
        if user is None or not user.is_active or user.org_id != self.org_id:
            return None
        return user


async def _heartbeat(session_factory, job_id: int, token: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            async with session_factory() as s:
                now = _utcnow()
                ok = await _fenced_update(s, job_id, token,
                                          lease_expires_at=now + timedelta(seconds=LEASE_SECONDS))
                await s.commit()
            if not ok:
                return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - a missed beat is retried next time
            log.warning("Job %s heartbeat failed: %s", job_id, e)


async def _settle(session_factory, job_id: int, token: str, **values) -> None:
    now = _utcnow()
    values.setdefault("finished_at", now)
    values.setdefault("updated_at", now)
    values.setdefault("lease_expires_at", None)
    async with session_factory() as s:
        await _fenced_update(s, job_id, token, **values)
        await s.commit()


async def execute(session_factory, job_id: int, token: str) -> str | None:
    """Run one claimed job to an outcome; return its final state (None when
    the lease was lost and the outcome belongs to another worker)."""
    async with session_factory() as s:
        job = await s.get(Job, job_id)
        if job is None:
            return None
        ctx = JobContext(job_id=job.id, token=token, kind=job.kind, org_id=job.org_id,
                         created_by=job.created_by, inputs=dict(job.inputs or {}),
                         attempt=job.attempt or 1, session_factory=session_factory)
    handler = HANDLERS.get(ctx.kind)
    if handler is None:
        await _settle(session_factory, job_id, token, state=FAILED, error_code="unexpected",
                      error=f"This server cannot run '{ctx.kind}' jobs")
        return FAILED

    beat = asyncio.create_task(_heartbeat(session_factory, job_id, token))
    try:
        await handler(ctx)
        if not ctx.completed:
            # A handler with no effects to commit still has to end its job.
            async with session_factory() as s:
                await ctx.complete(s, {})
                await s.commit()
        return SUCCEEDED
    except JobCancelled:
        await _settle(session_factory, job_id, token, state=CANCELLED,
                      progress={"stage": "cancelled"})
        return CANCELLED
    except LeaseLost:
        log.warning("Job %s: lease lost; leaving the outcome to its new owner", job_id)
        return None
    except JobError as e:
        await _settle(session_factory, job_id, token, state=FAILED, error_code=e.code,
                      error=sanitize_error(e), progress={"stage": "failed"},
                      **({"result": e.detail} if e.detail is not None else {}))
        return FAILED
    except asyncio.CancelledError:
        # The process is shutting down. Leave the row RUNNING: the lease runs
        # out and the next claim resumes it as a new attempt.
        raise
    except Exception:  # noqa: BLE001 - one job's crash must not kill the worker
        log.exception("Job %s (%s) crashed", job_id, ctx.kind)
        await _settle(session_factory, job_id, token, state=FAILED, error_code="unexpected",
                      error="The job stopped because of an unexpected server error. "
                            "Retry it; if it fails again, ask an administrator to check "
                            "the server log.",
                      progress={"stage": "failed"})
        return FAILED
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await beat


async def run_next(session_factory, worker_id: str, now: datetime | None = None) -> str | None:
    """Claim and run one job. Returns its final state, or None if idle."""
    async with session_factory() as s:
        claimed = await claim(s, worker_id, now)
    if claimed is None:
        return None
    return await execute(session_factory, *claimed)


async def run_worker(session_factory, worker_id: str | None = None) -> None:
    """The per-process worker loop: never dies, runs up to WORKER_CONCURRENCY
    jobs at once, and polls while idle."""
    load_handlers()
    worker_id = worker_id or new_worker_id()
    running: set[asyncio.Task] = set()
    while True:
        try:
            while len(running) < WORKER_CONCURRENCY:
                async with session_factory() as s:
                    claimed = await claim(s, worker_id)
                if claimed is None:
                    break
                t = asyncio.create_task(execute(session_factory, *claimed))
                running.add(t)
                t.add_done_callback(running.discard)
            await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            # Shutdown: stop the jobs in flight and wait for them to unwind, so
            # none touches the database after the engine is disposed. Their
            # rows stay `running`; the lease runs out and a later claim resumes.
            for t in list(running):
                t.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            raise
        except Exception as e:  # noqa: BLE001 - a bad poll must not kill the loop
            log.warning("Job worker poll failed: %s", e)
            await asyncio.sleep(POLL_SECONDS)
