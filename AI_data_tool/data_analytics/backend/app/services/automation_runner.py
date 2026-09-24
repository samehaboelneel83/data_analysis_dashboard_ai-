"""Power Pi: the orchestrator that runs the pipeline nobody is watching.

The pieces already exist -- profiling, insights, dashboard suggestion, widget
review, report composition. What was missing is something that runs them in
order, by itself, and survives the ways an unattended chain actually breaks: a
process restart mid-step, a source that is down for an hour, a user deleted
between step 2 and step 6.

All seven steps (`profile`, `describe`, `scan`, `propose`, `review`,
`compose`, `notify`) are real. `_stub` remains for the next step somebody
adds: it lands behind the same `StepSpec` interface and must not change the
contract the tests pin. `test_the_shipped_chain_runs_end_to_end_unmonkeypatched`
walks the shipped list and fails on any `stub://` ref.

Describe behaviour here, not project phase -- `direct_query.py` carries the
same warning for the same reason: an earlier version of THIS docstring still
said all seven were stubs after two of them shipped, and prose is believed
over code. No test asserts on a docstring; keep it true by hand.

THREE DECISIONS THAT SHAPE EVERYTHING ELSE
------------------------------------------

**One step per tick, never a chain.** `tick()` executes exactly one step and
returns. A tick that ran a whole run would hold the shared scheduler loop for
as long as the slowest chain takes, starving dataset refreshes and alerts that
share it. It also means a restart loses at most one step.

**`output_ref` is the resume marker, not `status`.** A step that already has a
ref is skipped whatever its status says. A worker killed between writing the
ref and committing the status would otherwise redo the work -- re-profiling a
large dataset, or re-composing a report and leaving two behind.

**The creator's identity is a precondition, not a parameter.** RLS here is
per-user: `core/rls.resolve_rls_expr` answers a different predicate per role.
A step that ran headless would read the unfiltered frame and build a dashboard
from rows the creator may not see -- and it would look like a success, because
nobody is watching. So a run whose creator cannot be resolved is FAILED, with
the reason recorded, rather than executed. Never make this a warning.

WHY `failed` IS NOT TERMINAL
----------------------------
A run that fails at step 5 must resume at step 5. `tick` therefore treats
`failed` as eligible and lets the *step's* `next_attempt_at` gate the retry,
using the same backoff ladder as `refresh_scheduler` rather than a second one.

`needs_review` is the FOURTH state and the one exception: it is in neither
ACTIVE_RUN_STATUSES nor TERMINAL_RUN_STATUSES, because a quality judgement is
not transient (retrying reproduces it) and not the end (a person can say yes).
`approve_review` resumes the chain where it stopped; `reject_review` cancels
it. See NEEDS_REVIEW below.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from ..models.models import AutomationRun, AutomationStep, User
from .notifications import notify
from .refresh_scheduler import _as_utc_naive, backoff_minutes

log = logging.getLogger(__name__)

#: A quality judgement waiting on a person. **Deliberately in neither set.**
#:
#: Not ACTIVE: `tick` would retry it, and retrying a judgement reproduces the
#: same judgement at 5, 15 and 45 minutes and then hourly. `failed` retries
#: because the things that fail a step are transient -- a source down for an
#: hour, a restart mid-write. "These widgets are not good enough" is not.
#:
#: Not TERMINAL: work was done, the artifacts are on disk, and a person saying
#: yes resumes the chain rather than starting one.
#:
#: A state with no exit is swallowing with a polite name, so `approve_review`
#: and `reject_review` below are part of the state, not a later feature.
NEEDS_REVIEW = "needs_review"

#: Run statuses. `failed` is deliberately absent from the terminal set -- see
#: the module docstring. `needs_review` is absent from BOTH -- see above.
ACTIVE_RUN_STATUSES = ("pending", "running", "failed")
TERMINAL_RUN_STATUSES = ("done", "cancelled")

#: How many runs a single tick will look past before giving up. A tick that
#: scanned an unbounded backlog looking for one eligible step would itself
#: become the stall it is trying to avoid.
MAX_RUNS_SCANNED_PER_TICK = 50

#: Errors are truncated to the same width `record_failure` uses, so an
#: operator reading either table sees the same shape of message.
MAX_ERROR_CHARS = 2000


class StepRefused(Exception):
    """A step declining to run, with the reason an operator needs.

    Distinct from a crash on purpose. A crash is a bug and its traceback type
    is worth recording; a refusal is a correct outcome -- the dataset is gone,
    the source is unreachable, the creator may not read it -- and the operator
    wants the sentence, not the exception class in front of it.

    Both land in `AutomationStep.error` and both earn backoff. Neither ever
    writes an `output_ref`.
    """


@dataclass(frozen=True)
class StepContext:
    """Everything a step is allowed to know, and nothing it can mutate.

    A frozen value rather than ORM instances, so nothing a step does to it can
    leak back into the runner's session. The session is passed separately, as
    an argument to `run`, precisely so that the identity in here and the
    handle used to read the database cannot drift apart: a step that resolved
    its own user would be one refactor away from resolving the wrong one.
    """
    run_id: int
    org_id: int
    #: Never None by the time a step sees it -- `tick` refuses first.
    user_id: int
    user_email: str
    trigger: str
    subject_type: str | None
    subject_id: int | None
    step_name: str


@dataclass(frozen=True)
class StepSpec:
    """One named step: `async def run(ctx, session) -> output_ref`.

    WHY ASYNC, WHEN THE SKELETON THREADED A SYNC CALLABLE
    -----------------------------------------------------
    A real step needs the database before it can touch a frame: the subject
    row, the creator's RLS predicate, their denied columns, the prep steps.
    None of that can happen inside `asyncio.to_thread`, because an
    AsyncSession is not usable from another thread.

    So the step owns both halves, exactly as `alerts.check_alert` does -- the
    established shape in this codebase for unattended work running as a
    creator. It reads on the loop and wraps its own blocking work in
    `asyncio.to_thread`.

    The invariant that mattered is unchanged: **a step must never block the
    shared scheduler tick**. It is now the step author's explicit
    responsibility rather than something the runner can impose, which is the
    only place it can live once a step needs a session.

    `session` is the runner's, not a factory: a step's reads and the runner's
    bookkeeping belong to one transaction. A step must NOT commit -- the
    runner owns the commit, so a step that fails halfway leaves no partial
    state behind.
    """
    name: str
    run: Callable[[StepContext, object], Awaitable[str]]


def _stub(name: str) -> StepSpec:
    """A placeholder that does the bookkeeping a real step will do.

    It returns a well-formed `output_ref` so the whole chain is walkable
    before any real step exists -- otherwise the first real implementation
    would land on a pipeline nobody had ever run end to end.
    """
    async def _run(ctx: StepContext, session) -> str:
        log.info("automation run %s: step %s (stub) for %s %s as user %s",
                 ctx.run_id, name, ctx.subject_type, ctx.subject_id, ctx.user_id)
        return f"stub://{name}/run/{ctx.run_id}"

    return StepSpec(name=name, run=_run)


# ── step 1: profile ──────────────────────────────────────────────────────────

def _profile_artifact_path(org_id: int, run_id: int):
    """Where one run's profile lives: under the ORG's upload directory.

    Per-org, reusing `upload_store.storage_root`, so a cross-tenant read is a
    filesystem boundary rather than a query filter someone can forget. Per-run
    rather than per-dataset because the profile is RLS-filtered as ONE
    creator: two people with different row rules profiling the same dataset
    must not overwrite each other's view of it.
    """
    from .upload_store import storage_root
    return storage_root(org_id) / "automation" / f"run_{run_id}" / "profile.json"


def _run_artifact_dir(org_id: int, run_id: int):
    """Everything one run leaves on disk, in one directory.

    One place, so `discard_run_artifacts` can remove it without knowing which
    steps wrote what -- the same shape `dataset_cleanup.discard_dataset_artifacts`
    uses for what a dataset leaves behind.
    """
    return _profile_artifact_path(org_id, run_id).parent


def _write_frame_artifact(org_id: int, run_id: int, df) -> str:
    """Persist the creator's SECURED frame as parquet, and return its ref.

    WHY THE FRAME IS PERSISTED AT ALL
    ---------------------------------
    Steps 3, 4 and 5 need the rows, not a description of them. The alternative
    is each of them re-reading the dataset file and re-applying RLS, denied
    columns and prep in the right order -- three more copies of the ordering
    `test_rls_base_frame_choke_point` exists to protect, and the third copy is
    the one somebody gets wrong. Written once here, already secured.

    That makes this the most dangerous artifact the chain produces: the profile
    holds samples, this holds every row the creator may see. Hence the temp
    name and `os.replace` -- a half-written parquet behind a committed
    `output_ref` is TRUNCATED CUSTOMER DATA reaching a model in step 4, which
    is strictly worse than a half-written description.

    Per-RUN, not per-dataset: the frame is filtered to one person's rows, and
    two people with different row rules must not overwrite each other's.
    """
    import os
    from pathlib import Path
    from uuid import uuid4

    from ..core.config import settings

    final = _run_artifact_dir(org_id, run_id) / "frame.parquet"
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.parent / f".frame.{uuid4().hex}.tmp"
    df.to_parquet(tmp, index=False)

    cap_mb = float(getattr(settings, "automation_frame_max_mb", 0) or 0)
    if cap_mb:
        size_mb = tmp.stat().st_size / (1024 * 1024)
        if size_mb > cap_mb:
            # Removed before raising: a refused step must leave nothing behind,
            # or the next attempt inherits a stray file and the disk fills with
            # the artifacts of runs that never succeeded.
            tmp.unlink(missing_ok=True)
            raise StepRefused(
                f"the secured frame is too large to persist: "
                f"{size_mb:.1f} MB against a {cap_mb:.1f} MB limit "
                f"(automation_frame_max_mb)")

    os.replace(tmp, final)
    return "file://" + final.relative_to(Path(settings.upload_dir)).as_posix()


def discard_run_artifacts(org_id: int, run_id: int) -> int:
    """Remove everything a run left on disk. Returns how many files went.

    A run's artifacts exist to be handed between its own steps. Once the run is
    done they are a copy of one person's rows with nothing reading it, so they
    go -- in ONE place, the way `dataset_cleanup.discard_dataset_artifacts`
    removes what a dataset leaves behind rather than each deleting caller
    remembering the list.

    Never raises: cleanup failing must not turn a finished run into a failed
    one. A file left behind is a disk-space problem; an exception here would be
    a correctness problem.
    """
    import shutil

    removed = 0
    try:
        directory = _run_artifact_dir(org_id, run_id)
        if directory.exists():
            removed = sum(1 for p in directory.rglob("*") if p.is_file())
            shutil.rmtree(directory, ignore_errors=True)
    except Exception:                                    # noqa: BLE001
        log.warning("could not remove artifacts for automation run %s", run_id,
                    exc_info=True)
    return removed


def _write_profile_artifact(org_id: int, run_id: int, profile: dict) -> str:
    """Persist the profile and return the ref that addresses it.

    Written to a temp name and moved into place: a half-written file behind a
    committed `output_ref` would be a resume that skips a broken artifact
    forever, which is the one failure `output_ref`-as-resume-marker cannot
    detect.
    """
    import json
    import os
    from pathlib import Path
    from uuid import uuid4

    from ..core.config import settings

    final = _profile_artifact_path(org_id, run_id)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.parent / f".profile.{uuid4().hex}.tmp"
    # default=str: build_profile returns numpy scalars and Timestamps.
    tmp.write_text(json.dumps(profile, default=str), encoding="utf-8")
    os.replace(tmp, final)
    return "file://" + final.relative_to(Path(settings.upload_dir)).as_posix()


async def _profile_step(ctx: StepContext, session) -> str:
    """Profile the run's subject dataset, as the run's creator.

    Shaped after `alerts.check_alert`, which is this codebase's answer to
    "unattended work that must still obey one person's permissions". Every
    refusal below raises `StepRefused` rather than returning a ref: the whole
    contract of this step is that an `output_ref` means a profile that was
    actually earned.

    THE ORDER OF THE FOUR LINES IN `_build` IS THE SECURITY
    -------------------------------------------------------
    1. `load_file`             -- the raw frame
    2. `apply_rls_filter`      -- the creator's rows, failing CLOSED on a
                                  broken rule (pinned by
                                  test_rls_base_frame_choke_point.py, which
                                  requires this to sit ON the base frame)
    3. drop `denied`           -- BEFORE profiling, not after. The profile is
                                  what a model reads in step 4; a column this
                                  creator may not see must never enter it,
                                  and a profile carries sample VALUES.
    4. prep / calculated cols  -- only now, on an already-secured frame.

    Swapping 2 and 4 would profile rows the creator cannot see. Swapping 3
    past `build_profile` would put denied values in the artifact.
    """
    from ..core.capability import can_read_dataset
    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from ..models.models import Dataset
    from .analytics import detect_types
    from .dataset_profile import build_profile
    from .ingest import load_file
    from .prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    from .widget_data import apply_calculated_columns, apply_rls_filter

    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"cannot profile subject_type={ctx.subject_type!r}; "
            f"step 1 profiles datasets")

    ds = await session.get(Dataset, ctx.subject_id)
    # Org check and existence collapse into ONE message on purpose: the same
    # 404-never-403 discipline the rest of the product uses. A refusal that
    # said "exists, but not yours" would confirm another tenant's row.
    if ds is None or ds.org_id != ctx.org_id:
        raise StepRefused("dataset not found")

    user = await _load_creator(session, ctx.user_id)
    if user is None:
        raise StepRefused("creator is no longer available")
    # `can_read_dataset`, not `require_dataset_read`: the raising wrapper is
    # an HTTP concern, and a service that imports HTTPException is unusable
    # from the scheduler without a fake request context (a rule
    # test_layer_conformance pins with no exemptions). The boolean says the
    # same thing and lets this step word its own refusal.
    #
    # And not merely an org check: belonging to the org is not permission to
    # READ, and a profile carries sample VALUES -- the same reasoning the
    # suggestion endpoint in routers/datasets.py gives for the same call.
    if not await can_read_dataset(session, user, ds.id):
        raise StepRefused("dataset not found for this creator")

    if ds.mode == "directquery":
        raise StepRefused(
            "dataset is in directquery mode; step 1 profiles import-mode "
            "datasets, which are the ones that can be read whole")
    if not ds.filename:
        raise StepRefused("dataset has no stored file to profile")

    rls_expr = await resolve_rls_expr(session, user, ds.id)
    denied = await resolve_denied_columns(session, user, ds.id)
    steps = prep_steps_of(ds)
    aux = await resolve_join_frames(session, user, steps) if steps else {}

    def _build() -> dict:
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        df = apply_prep_steps(df, steps, aux)
        if ds.calculated_columns:
            df = apply_calculated_columns(
                df, ds.calculated_columns, ds.custom_functions)
        return df, build_profile(df, detect_types(df), ds.column_meta or {})

    try:
        # Threaded: load_file and build_profile are pandas work, and the
        # shared scheduler tick must keep running underneath.
        secured, profile = await asyncio.to_thread(_build)
    except FileNotFoundError:
        raise StepRefused("the dataset's file is missing from the server") from None

    # The frame first: the profile records the ref, so writing the profile
    # before the frame would commit a pointer to something that does not exist
    # yet. If the frame is refused (over the ceiling) nothing is written at all.
    frame_ref = await asyncio.to_thread(
        _write_frame_artifact, ctx.org_id, ctx.run_id, secured)
    profile["frame_ref"] = frame_ref
    return await asyncio.to_thread(
        _write_profile_artifact, ctx.org_id, ctx.run_id, profile)


# ── the exit from needs_review ───────────────────────────────────────────────

async def approve_review(session, run: AutomationRun) -> AutomationRun:
    """A person accepted the proposal: resume the chain where it stopped.

    **Resumes, never restarts.** Nothing here touches any step's `output_ref`,
    so `tick`'s existing rule -- the first step with no ref is the next one --
    lands on step 6 by itself. Clearing refs to "start clean" would re-profile
    and re-scan the dataset and overwrite the very artifacts the reviewer just
    looked at, which is worse than the problem it would be solving.

    Refuses a run that is not awaiting review. Approval is a transition out of
    ONE state, not a way to push any run forward: approving a `failed` run
    would skip the step that failed and leave a hole in the middle of the
    chain that `output_ref`-as-resume-marker cannot detect.
    """
    if run.status != NEEDS_REVIEW:
        raise ValueError(
            f"run {run.id} is {run.status!r}, not {NEEDS_REVIEW!r}; only a run "
            f"awaiting review can be approved")
    run.status = "running"
    run.error = None
    await session.commit()
    log.info("automation run %s approved; resuming", run.id)
    return run


async def reject_review(session, run: AutomationRun,
                        *, reason: str | None = None) -> AutomationRun:
    """A person rejected the proposal: the run is over.

    `cancelled` rather than `failed`, and the difference matters: `failed`
    retries, and a rejected proposal must not come back in five minutes. The
    reason is recorded because "cancelled" with no sentence tells whoever finds
    this run nothing about why.
    """
    if run.status != NEEDS_REVIEW:
        raise ValueError(
            f"run {run.id} is {run.status!r}, not {NEEDS_REVIEW!r}; only a run "
            f"awaiting review can be rejected")
    run.status = "cancelled"
    run.error = (reason or "rejected at review")[:MAX_ERROR_CHARS]
    if run.finished_at is None:
        run.finished_at = datetime.utcnow()
    # A rejected run's artifacts are a copy of one person's rows that nothing
    # will read -- the same reason a finished run's go.
    discard_run_artifacts(run.org_id, run.id)
    await session.commit()
    log.info("automation run %s rejected at review: %s", run.id, run.error)
    return run


# ── loading the person a step runs as ────────────────────────────────────────
#
# READ THIS BEFORE YOU WRITE A STEP.
#
# A step runs on the scheduler tick, not inside a request. Under async
# SQLAlchemy an implicit relationship access is not merely slow out here -- it
# raises MissingGreenlet, because there is no greenlet to suspend into. It does
# not fail reliably either: it succeeds whenever the related row happens to be
# in the session's identity map already, which depends on what some earlier,
# unrelated code did. So it passes in tests that built the rows moments before,
# and fails on a cold tick in production.
#
# This module has now been bitten twice:
#
#   1. `_fail` read `step.attempts` after `session.rollback()` expired every
#      instance -- which would have turned a recorded failure into an
#      unrecorded crash. Fixed by taking ids first and re-reading the rows.
#   2. `can_read_dataset` opens with `user.role.is_org_admin`. Every step calls
#      it. Fixed HERE rather than at six call sites, because eager-loading in
#      six places means forgetting it in one.
#
# The rule: **anything a step reaches through a relationship must be loaded
# before the step touches it.** If you need more than `user.role` -- step 6
# (compose) will want reports, pages and widgets -- add the `selectinload` to
# the query that fetches it, and add a test that clears the identity map with
# `expunge_all()` first. A test that builds its fixtures in the same session is
# structurally incapable of catching this.


async def _load_creator(session, user_id: int):
    """The run's creator, with `role` eagerly loaded, or None.

    One function so every step inherits the eager load. `can_read_dataset`
    reads `user.role.is_org_admin` on its first line, so a step that loaded
    the user with a bare `session.get` would be a cold tick away from failing
    its own permission check -- see the note above.
    """
    return (await session.execute(
        select(User).where(User.id == user_id)
        .options(selectinload(User.role)))).scalar_one_or_none()


# ── the structured record ────────────────────────────────────────────────────

#: The columns a step may write onto its run. A typo in a caller raises here
#: rather than setting a Python attribute SQLAlchemy silently never persists --
#: which is exactly how `run.error` was "recorded" in three places and stored
#: in none until migration 0032 gave it a column.
_RECORD_FIELDS = frozenset({
    "result_report_id", "result_report_name", "proposal_path",
    "widgets_accepted", "widgets_rejected", "rejection_reasons",
    "raw_proposals", "error",
})


async def record_run_result(session, run_id: int, **fields) -> AutomationRun | None:
    """Write what a step learned onto the run's TYPED record.

    One writer, called by every step that knows something: step 4 records the
    path and the raw proposals, step 5 the counts and reasons, step 6 the
    report. Nothing here formats a sentence -- `describe_run` derives one at
    render time from these columns, and nothing parses it back.

    WHY THE RECORD IS IN COLUMNS AND NOT IN THE ARTIFACTS
    -----------------------------------------------------
    `discard_run_artifacts` deletes the run's directory at `done`. The first
    real run composed a report with a meaningless lead KPI, and by the time
    anyone looked, the 17 proposals it was chosen from were gone. Model output
    is not reproducible; an uncaptured proposal set is gone for good, and it is
    the only material that lets a quality claim be checked afterwards. So the
    raw proposals are stored whole. It is a small JSON.

    Does not commit: the runner owns the commit, so a step that fails after
    recording leaves nothing half-written.
    """
    unknown = set(fields) - _RECORD_FIELDS
    if unknown:
        raise ValueError(f"not a record column: {sorted(unknown)}")
    run = await session.get(AutomationRun, run_id)
    if run is None:
        return None
    for name, value in fields.items():
        setattr(run, name, value)
    return run


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def describe_run(run: AutomationRun) -> tuple[str, str | None]:
    """One sentence and a link, DERIVED from the typed record every time.

    The record is the source of truth; this is a rendering of it, and
    nothing parses the sentence back. The bell stores a copy because that
    is what a notification row is, and Home can filter and order by the
    columns while showing the same words, because both call this.

    Two shapes, because the reader acts on one and not the other: a
    finished run is something to open, a held run is something to decide.
    A held run has no report yet, so its link is None until runs get a page
    of their own -- a link to nowhere would be worse than no link.
    """
    accepted = run.widgets_accepted or 0
    rejected = run.widgets_rejected or 0
    link = f"/reports/{run.result_report_id}" if run.result_report_id else None
    if run.status == NEEDS_REVIEW:
        why = f" {run.error}." if run.error else ""
        return (f"Your automated analysis needs a decision:{why} "
                f"{_plural(accepted, 'widget')} passed review, {rejected} did not. "
                f"Open it to approve or reject."), link
    name = run.result_report_name or "Your automated report"
    if rejected:
        return (f'"{name}" is ready: {_plural(accepted, "widget")} kept, '
                f"{rejected} rejected by review."), link
    return f'"{name}" is ready: all {_plural(accepted, "widget")} passed review.', link


async def notify_run(session, run: AutomationRun) -> None:
    """Tell the run's creator, and only them, through the one in-app channel.

    Shared by step 7 and by step 5's hold, so a run that stops for a decision
    is announced by the same code path as one that finished. Creator-only
    because the report was composed from THEIR rows: a colleague's link
    would 404 or, worse, open numbers that are not theirs. Does not commit --
    the row rides in the runner's own transaction, next to the step's ref.
    """
    text, link = describe_run(run)
    await notify(session, run.org_id, run.created_by, "automation", text, link)


# ── reading the step before you ──────────────────────────────────────────────

async def _previous_output_ref(session, ctx: StepContext, step_name: str) -> str:
    """The `output_ref` an earlier step in THIS run earned, or a refusal.

    Every step from 2 onward consumes the one before it, so this is shared
    rather than repeated per step -- and it is the one place that decides what
    "the previous step did not produce anything" means. It means refuse: a
    step that carried on with no input would write a ref it did not earn,
    which is the single invariant the whole chain rests on.

    Looked up by NAME, not by order-1, so inserting a step into the middle of
    `STEPS` later cannot silently repoint a consumer at its new neighbour.
    """
    from sqlalchemy import select

    from ..models.models import AutomationStep

    ref = (await session.execute(
        select(AutomationStep.output_ref).where(
            AutomationStep.run_id == ctx.run_id,
            AutomationStep.name == step_name))).scalar_one_or_none()
    if not ref:
        raise StepRefused(f"step '{step_name}' produced no output to consume")
    return ref


# ── step 2: describe ─────────────────────────────────────────────────────────

def _describe_artifact_path(org_id: int, run_id: int):
    """Beside the profile, under the same per-org, per-run directory."""
    from .upload_store import storage_root
    return storage_root(org_id) / "automation" / f"run_{run_id}" / "describe.json"


def _read_profile_artifact(ref: str) -> dict:
    """Load what step 1 wrote, by the ref step 1 earned.

    Raises FileNotFoundError, which the caller turns into a StepRefused. A
    missing artifact behind a committed ref is the one failure the
    ref-as-resume-marker cannot detect on its own, so this step is where it
    gets detected.
    """
    import json
    from pathlib import Path

    from ..core.config import settings

    if not ref or not ref.startswith("file://"):
        raise FileNotFoundError(ref or "<no ref>")
    path = Path(settings.upload_dir) / ref[len("file://"):]
    return json.loads(path.read_text(encoding="utf-8"))


def _write_describe_artifact(org_id: int, run_id: int, payload: dict) -> str:
    """Same temp-then-rename discipline as the profile artifact."""
    import json
    import os
    from pathlib import Path
    from uuid import uuid4

    from ..core.config import settings

    final = _describe_artifact_path(org_id, run_id)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.parent / f".describe.{uuid4().hex}.tmp"
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    os.replace(tmp, final)
    return "file://" + final.relative_to(Path(settings.upload_dir)).as_posix()


def _semantics_from_profile(profile: dict) -> dict[str, dict]:
    """Turn step 1's profile into role/semantic proposals.

    WHY THIS RE-CLASSIFIES RATHER THAN COPYING `is_identifier` FORWARD
    ------------------------------------------------------------------
    The profile's `is_identifier` comes from `widget_data._is_id_like_column`,
    which matches the NAME only. That catches `student_id` and misses
    `cohort_ref` -- numeric, near-unique, and named nothing in particular.
    `classify_role` is the canonical heuristic and uses both halves, so the
    profile's own distinct/row counts are fed back through it here. This is
    the step's entire reason for existing: the identifier concept has to
    arrive somewhere the analyses read, and it has to be the good version.

    No frame is touched. Every input comes from the artifact.
    """
    from .metadata.infer_semantic import classify_role

    row_count = int(profile.get("row_count") or 0)
    proposals: dict[str, dict] = {}
    #: The profile speaks in render roles (numeric/categorical/datetime);
    #: classify_role speaks in dtypes. Enough of a dtype to answer its
    #: date/time question -- the rest of its decision is the counts.
    dtype_of = {"numeric": "float64", "datetime": "datetime64[ns]",
                "categorical": "object"}

    for entry in profile.get("columns") or []:
        name = entry.get("name")
        if not name:
            continue
        role = classify_role(
            name, dtype_of.get(entry.get("role"), "object"),
            {"distinct_count": entry.get("distinct"), "row_count": row_count})
        proposed: dict = {"role": role}
        # A personal column is flagged by pii.py at profile time, on values
        # this step never sees. Carried through rather than re-derived, which
        # would need the rows back.
        if entry.get("is_personal"):
            proposed["semantic_type"] = "personal"
        proposals[name] = proposed
    return proposals


async def _describe_step(ctx: StepContext, session) -> str:
    """Give every column a role the analyses can read, as the run's creator.

    Consumes step 1's artifact rather than re-reading the dataset. That is not
    only about cost: step 1 filtered the frame by the creator's RLS and
    dropped their denied columns BEFORE profiling, so a second read here would
    be a second path to the data, and the second path is the one that gets
    forgotten. The artifact is already secured; the file is not.

    The write goes through `metadata.store.apply_inferred_column_semantics`,
    which owns the confirmed > declared > inferred ladder. A human who
    classified a column on the Fields pane keeps their answer.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from ..core.capability import can_read_dataset
    from ..models.models import Dataset
    from .metadata.store import apply_inferred_column_semantics

    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"cannot describe subject_type={ctx.subject_type!r}; "
            f"step 2 describes datasets")

    ds = await session.get(Dataset, ctx.subject_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise StepRefused("dataset not found")

    user = await _load_creator(session, ctx.user_id)
    if user is None:
        raise StepRefused("creator is no longer available")
    # Re-checked, not inherited from step 1: a grant can be revoked between
    # ticks, and this step writes metadata derived from that person's slice.
    if not await can_read_dataset(session, user, ds.id):
        raise StepRefused("dataset not found for this creator")

    previous = await _previous_output_ref(session, ctx, "profile")
    try:
        profile = await asyncio.to_thread(_read_profile_artifact, previous)
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "step 1's profile artifact is missing or unreadable; "
            "nothing to describe") from exc

    proposals = _semantics_from_profile(profile)
    merged, changed = apply_inferred_column_semantics(ds.column_meta, proposals)
    if changed:
        ds.column_meta = merged
        # JSON columns are mutated in place as far as SQLAlchemy can tell, so
        # without this the write is silently dropped on commit.
        flag_modified(ds, "column_meta")

    payload = {
        "dataset_id": ds.id,
        # The MERGED result, not the proposals. Step 3 reads this artifact for
        # its roles, and the proposals are what this step WANTED -- a column a
        # human had already classified keeps their answer, and a consumer given
        # the proposal would act on a value that was deliberately rejected.
        "columns": {name: merged.get(name, {}) for name in proposals},
        "proposed": proposals,
        "changed": changed,
        "identifiers": sorted(n for n, p in proposals.items()
                              if p.get("role") == "identifier"),
        "source_profile": previous,
        # Carried forward so step 3 reads ONE artifact rather than following a
        # chain of refs back to step 1.
        "frame_ref": profile.get("frame_ref"),
    }
    return await asyncio.to_thread(
        _write_describe_artifact, ctx.org_id, ctx.run_id, payload)


# ── step 3: scan ─────────────────────────────────────────────────────────────

def _read_frame_artifact(ref: str):
    """Load the secured frame step 1 wrote. Raises FileNotFoundError if gone."""
    from pathlib import Path

    import pandas as pd

    from ..core.config import settings

    if not ref or not ref.startswith("file://"):
        raise FileNotFoundError(ref or "<no frame ref>")
    path = Path(settings.upload_dir) / ref[len("file://"):]
    if not path.exists():
        raise FileNotFoundError(str(path))
    return pd.read_parquet(path)


def _write_step_artifact(org_id: int, run_id: int, name: str, payload: dict) -> str:
    """One JSON artifact per step, written temp-then-replace.

    Generalised from the scan writer once step 4 needed the same thing: three
    near-identical writers is how one of them quietly loses the `os.replace`
    and starts committing refs to half-written files.
    """
    import json
    import os
    from pathlib import Path
    from uuid import uuid4

    from ..core.config import settings

    final = _run_artifact_dir(org_id, run_id) / f"{name}.json"
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.parent / f".{name}.{uuid4().hex}.tmp"
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    os.replace(tmp, final)
    return "file://" + final.relative_to(Path(settings.upload_dir)).as_posix()


def _write_scan_artifact(org_id: int, run_id: int, payload: dict) -> str:
    return _write_step_artifact(org_id, run_id, "scan", payload)


async def _scan_step(ctx: StepContext, session) -> str:
    """Run the insight scan over the secured frame, with the recorded roles.

    This is the step the previous two existed to make possible. `effective_roles`
    can now answer `identifier`, so `generate_insights` stops treating a numeric
    id as a measure -- which is what produced findings about row order.

    Everything it reads was earned by an earlier step: the frame from step 1,
    the roles from step 2. It never opens the dataset file, because step 1
    already filtered it by this creator's RLS and dropped their denied columns,
    and a second read would be a second path to the same rows.
    """
    from ..core.capability import can_read_dataset
    from ..models.models import Dataset
    from .analytics import detect_types
    from .insights import effective_roles, generate_insights

    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"cannot scan subject_type={ctx.subject_type!r}; step 3 scans datasets")

    ds = await session.get(Dataset, ctx.subject_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise StepRefused("dataset not found")

    user = await _load_creator(session, ctx.user_id)
    if user is None:
        raise StepRefused("creator is no longer available")
    if not await can_read_dataset(session, user, ds.id):
        raise StepRefused("dataset not found for this creator")

    previous = await _previous_output_ref(session, ctx, "describe")
    try:
        described = await asyncio.to_thread(_read_profile_artifact, previous)
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "step 2's description is missing or unreadable; nothing to scan"
        ) from exc

    try:
        frame = await asyncio.to_thread(
            _read_frame_artifact, described.get("frame_ref"))
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "the secured frame from step 1 is missing; step 3 will not "
            "re-read the dataset to replace it") from exc

    # The MERGED metadata step 2 recorded, not its proposals: a column a human
    # classified keeps their answer, and that answer has to reach the scan or
    # the provenance ladder stops one step short of mattering.
    column_meta = described.get("columns") or {}

    def _scan() -> dict:
        type_map = detect_types(frame)
        roles = effective_roles(type_map, column_meta)
        result = generate_insights(frame, type_map, column_meta)
        scanned = sorted(c for c, kind in roles.items()
                         if kind in ("numeric", "categorical", "datetime"))
        # Named, not dropped. A column that simply vanishes reads as one the
        # scan never saw, and the reader has no way to tell the difference.
        excluded = {c: kind for c, kind in roles.items() if c not in scanned}
        return {"findings": result.get("findings") or [],
                "narrative": result.get("narrative") or "",
                "scanned_columns": scanned,
                "excluded_columns": excluded,
                "source_describe": previous,
                # Carried forward, so step 4 reads ONE artifact rather than
                # walking back through three. Same reason step 2 carries
                # frame_ref: a chain of refs is a chain of things that can be
                # missing, each with its own refusal to word.
                "frame_ref": described.get("frame_ref"),
                "profile_ref": described.get("source_profile")}

    payload = await asyncio.to_thread(_scan)
    payload["dataset_id"] = ds.id
    return await asyncio.to_thread(
        _write_scan_artifact, ctx.org_id, ctx.run_id, payload)


# ── step 4: propose ──────────────────────────────────────────────────────────

def masked_profile_for_model(profile: dict) -> dict:
    """The profile with its sample values run through `pii.py`, for the model.

    THIS IS WHERE CUSTOMER DATA LEAVES THE CHAIN.
    ---------------------------------------------
    Step 1 dropped the creator's denied columns, but samples are a SEPARATE
    exposure: a column nobody denied can still hold addresses and phone
    numbers, and the profile carries example values precisely so the model can
    tell what a column means.

    `build_profile` already withholds samples from a column that classifies as
    personal. This adds the per-VALUE pass it cannot do: classification is a
    majority verdict over a column (`pii._MAJORITY`), so a column that is
    mostly city names and occasionally an email address is not personal as a
    whole, while the individual sampled value still is.

    WHAT IS NOT MASKED, AND WHERE TO FIX IT IF THAT CHANGES
    -------------------------------------------------------
    **Free-text columns whose sentences EMBED PII are not masked.** A `notes`
    column reading "emailed a.person@example.com about the invoice" reaches the
    model with that address in it. This is a known, accepted boundary, not an
    oversight:

    `pii.py`'s patterns are anchored (`^...$`) and its majority rule exists for
    exactly this case -- "one email address inside a free-text notes column must
    not turn the whole column into PII -- masking it would destroy real data to
    protect one value." A column of genuine prose is the thing a model most
    needs to read to understand a dataset, and blanket-redacting it removes the
    signal along with the address.

    If that trade-off ever has to tighten, **the change belongs HERE, at the
    payload edge, not in pii.py.** This function is the one place customer data
    crosses out of the chain, so an unanchored scan added here narrows only what
    is sent to a model. The same scan added to `pii.py` would also reach column
    classification, sample masking and the preview path, and would start
    destroying prose in surfaces that were never the concern.

    Returns a COPY. Mutating the artifact in place would mean the profile on
    disk and the profile the model saw are the same object, and a later reader
    could not tell what was actually sent.
    """
    import copy

    from .pii import classify_value, is_pii, mask_value

    out = copy.deepcopy(profile or {})
    for column in out.get("columns") or []:
        samples = column.get("top_values") or []
        for sample in samples:
            raw = sample.get("value")
            if raw is None:
                continue
            # classify_value, not detect_semantic_type: the latter refuses
            # to judge fewer than pii._MIN_SAMPLE values, so asking it about a
            # single sample always returns None and the masking silently does
            # nothing. That is exactly how the first version of this shipped.
            kind = classify_value(raw)
            if is_pii(kind):
                sample["value"] = mask_value(raw, kind)
    return out


async def _propose_step(ctx: StepContext, session) -> str:
    """Turn the scan into candidate dashboards, by one of two paths.

    THE BRANCH IS A CONTRACT, NOT A PREFERENCE
    ------------------------------------------
    Step 5 judges a model proposal and a statistical one by different
    standards, so the artifact has to say which it is holding.

    - `llm_enabled=False` -> `suggest_from_insights`, deterministic, no model.
    - `llm_enabled=True`  -> `suggest_for_dataset`, falling back to the
      deterministic path if the model fails for ANY reason: endpoint down,
      timeout, malformed JSON, a proposal that conforms to nothing, or an
      empty answer.

    **The fallback is recorded, never swallowed.** A degraded proposal that
    looks identical to a deliberate one is the precise failure this chain
    exists to prevent, so `model_attempted` and `model_error` travel with the
    artifact whether or not anyone reads them today.
    """
    from ..core.capability import can_read_dataset
    from ..core.config import settings
    from ..models.models import Dataset

    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"cannot propose for subject_type={ctx.subject_type!r}; "
            f"step 4 proposes for datasets")

    ds = await session.get(Dataset, ctx.subject_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise StepRefused("dataset not found")

    user = await _load_creator(session, ctx.user_id)
    if user is None:
        raise StepRefused("creator is no longer available")
    if not await can_read_dataset(session, user, ds.id):
        raise StepRefused("dataset not found for this creator")

    previous = await _previous_output_ref(session, ctx, "scan")
    try:
        scan = await asyncio.to_thread(_read_profile_artifact, previous)
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "step 3's scan is missing or unreadable; nothing to propose from"
        ) from exc

    try:
        profile = await asyncio.to_thread(
            _read_profile_artifact, scan.get("profile_ref"))
        frame = await asyncio.to_thread(
            _read_frame_artifact, scan.get("frame_ref"))
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "the profile or secured frame from step 1 is missing; step 4 will "
            "not re-read the dataset to replace it") from exc

    proposals: list = []
    path = "insights"
    model_attempted = False
    model_error: str | None = None

    if settings.llm_enabled:
        from .suggest_dataset_dashboard import suggest_for_dataset
        model_attempted = True
        try:
            # Masked HERE, at the boundary, rather than trusting the artifact:
            # this is the one call that leaves the chain.
            payload = await asyncio.to_thread(masked_profile_for_model, profile)
            got, reason = await suggest_for_dataset(
                payload, ds.description or None)
            if got:
                proposals, path = list(got), "model"
            else:
                model_error = reason or "the model returned no proposal"
        except Exception as exc:                          # noqa: BLE001
            # ANY failure falls back. The reason is kept: an operator reading
            # this run needs to know the proposal in front of them is the
            # statistical one and why.
            model_error = f"{type(exc).__name__}: {exc}"

    if path != "model":
        from .suggest_from_insights import suggest_from_insights
        got, _reason = await suggest_from_insights(
            frame, profile, description=ds.description or None)
        proposals = list(got or [])

    payload = {
        "dataset_id": ds.id,
        "path": path,
        "model_attempted": model_attempted,
        "model_error": model_error,
        "proposals": proposals,
        "source_scan": previous,
        "frame_ref": scan.get("frame_ref"),
        "profile_ref": scan.get("profile_ref"),
    }
    # Recorded BEFORE the gate sees them: this is the raw set, whatever step 5
    # goes on to reject. The artifact copy below is deleted at done; this is
    # the one that survives.
    await record_run_result(session, ctx.run_id,
                            proposal_path=path, raw_proposals=proposals)
    return await asyncio.to_thread(
        _write_step_artifact, ctx.org_id, ctx.run_id, "propose", payload)


# ── step 5: review ───────────────────────────────────────────────────────────

#: A model proposal has to earn its place. Below this share of its widgets
#: surviving the gate, a person looks before it becomes a dashboard: four good
#: widgets beat twelve arbitrary ones, and one good widget out of four is a
#: model that did not understand the dataset.
MODEL_PASS_RATIO = 0.5


def _review_proposals(proposals: list, profile: dict) -> tuple[list, list]:
    """`(accepted, rejected)` — every widget judged, none silently dropped.

    Same contract as step 3's scanned/excluded columns: a widget that vanishes
    reads as one that was never proposed, and the reviewer cannot tell the
    difference between "the model did not suggest a map" and "we threw its map
    away". Each rejection carries `validate_widget`'s own sentence, which names
    the widget and what was wrong with it.
    """
    from .suggest_dataset_dashboard import validate_widget

    accepted: list = []
    rejected: list = []
    for proposal in proposals or []:
        for widget in proposal.get("widgets") or []:
            ok, why = validate_widget(widget, profile)
            if ok:
                accepted.append(widget)
            else:
                rejected.append({
                    "title": widget.get("title") or widget.get("widget_type"),
                    "widget_type": widget.get("widget_type"),
                    "reason": why,
                })
    return accepted, rejected


def _review_verdict(path: str, accepted: list, rejected: list) -> tuple[bool, str]:
    """`(needs_a_person, why)` — the two paths judged by different standards.

    Step 4 records which path produced the proposal precisely so this can
    differ, and it should: a model GUESSED and a statistical pass DERIVED.

    - A model proposal that mostly failed the gate is a model that misread the
      dataset. Somebody should see that before it becomes a dashboard.
    - A statistical proposal is held to the floor only. It did not invent
      columns; its widgets come from findings that were already computed over
      real data, so a low survival rate says the dataset is thin, not that the
      generator was wrong. Only an EMPTY result means there is nothing to show.
    """
    total = len(accepted) + len(rejected)
    if not accepted:
        return True, ("no proposed widget survived review"
                      if total else "nothing was proposed to review")
    if path == "model":
        ratio = len(accepted) / total
        if ratio < MODEL_PASS_RATIO:
            return True, (
                f"only {len(accepted)} of {total} proposed widgets survived "
                f"review; a person should look before this becomes a dashboard")
    return False, ""


async def _review_step(ctx: StepContext, session) -> str:
    """Judge step 4's proposal, and stop for a person when it does not hold up.

    This is the step that finally writes `needs_review`. It still writes an
    `output_ref` when it does: the review has to say WHAT it found, or the
    person it stopped for has nothing to read.
    """
    from ..core.capability import can_read_dataset
    from ..models.models import Dataset

    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"cannot review subject_type={ctx.subject_type!r}; "
            f"step 5 reviews dataset proposals")

    ds = await session.get(Dataset, ctx.subject_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise StepRefused("dataset not found")

    user = await _load_creator(session, ctx.user_id)
    if user is None:
        raise StepRefused("creator is no longer available")
    if not await can_read_dataset(session, user, ds.id):
        raise StepRefused("dataset not found for this creator")

    previous = await _previous_output_ref(session, ctx, "propose")
    try:
        proposed = await asyncio.to_thread(_read_profile_artifact, previous)
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "step 4's proposal is missing or unreadable; nothing to review"
        ) from exc

    try:
        profile = await asyncio.to_thread(
            _read_profile_artifact, proposed.get("profile_ref"))
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "the profile from step 1 is missing; a widget cannot be judged "
            "without knowing what the dataset holds") from exc

    path = proposed.get("path") or "insights"
    accepted, rejected = await asyncio.to_thread(
        _review_proposals, proposed.get("proposals") or [], profile)
    hold, why = _review_verdict(path, accepted, rejected)

    payload = {
        "dataset_id": ds.id,
        "path": path,
        "accepted": accepted,
        "rejected": rejected,
        "needs_review": hold,
        "review_reason": why,
        "source_propose": previous,
        "frame_ref": proposed.get("frame_ref"),
        "profile_ref": proposed.get("profile_ref"),
    }
    ref = await asyncio.to_thread(
        _write_step_artifact, ctx.org_id, ctx.run_id, "review", payload)

    # Counts and per-widget reasons onto the typed record, hold or not. The
    # artifact above is deleted at done; a person judging quality afterwards
    # reads these columns.
    run = await record_run_result(
        session, ctx.run_id,
        widgets_accepted=len(accepted), widgets_rejected=len(rejected),
        rejection_reasons=rejected, error=(why if hold else None))

    if hold and run is not None:
        # The step SUCCEEDED -- it reviewed, and its artifact says what it
        # found. What stops is the RUN, and it stops in a state nothing
        # retries. `_succeed` would otherwise set the run running again on the
        # next tick, so the status is written after the ref, and the runner's
        # own commit carries both.
        run.status = NEEDS_REVIEW
        # Step 7 never runs for a held run -- the run leaves the active
        # set here -- so the hold itself has to say so, or the work waits
        # for a person nobody told.
        await notify_run(session, run)
    return ref


# ── step 6: compose ──────────────────────────────────────────────────────────

#: `Report.origin` for what this chain composes. A person's report stays
#: "user", which is what every report predating the column already says.
REPORT_ORIGIN_AUTOMATION = "automation"

#: Report names are trimmed to fit the column and to stay readable in a list.
MAX_REPORT_NAME = 120


#: PII kinds redacted from any text this chain PERSISTS or SENDS. Derived from
#: `pii._PATTERNS` so there is one source of pattern truth -- a fifth copy of
#: the email regex is how the anchored and unanchored forms drift apart.
#:
#: `credit_card` and `national_id` are deliberately absent. Both are bare digit
#: runs, and matching them unanchored inside prose would redact order numbers,
#: years and row counts. Anchored whole-value classification still catches a
#: column of them; this is only the in-sentence pass.
REDACTED_TYPES = ("email", "iban", "phone")


def _unanchored(pattern: str) -> str:
    """`^...$` made searchable inside a sentence.

    `pii.py`'s patterns are anchored on purpose -- a match anywhere inside free
    text is not evidence that a COLUMN holds that kind of value, and its
    majority rule exists so one address cannot turn a notes column into PII.
    That reasoning is about classification and remains untouched.

    This is the other question: the text is already leaving the chain, and the
    address inside it is still an address. Stripping the anchors reuses the one
    definition rather than writing a second.
    """
    return pattern.lstrip("^").rstrip("$")


def redact_row_values(text: str | None) -> str:
    """Remove PII-shaped values from text that will be stored or displayed.

    THE BOUNDARY THIS CLOSES
    ------------------------
    `insights.py` builds finding titles out of a categorical column's actual
    VALUES ("`{low_name}` trails the other `{cat}` values on `{m}`"). Run on a
    real upload, that produced a report literally named after a customer's
    email address -- in `reports.name`, in the description, in the summary
    widget, and therefore in Recents and every list a report appears in.

    `masked_profile_for_model` covered only the model path. This covers text on
    BOTH paths, at the point it is about to be persisted, which is the only
    place that catches the deterministic one.
    """
    import re as _re

    from .pii import _PATTERNS, mask_value

    out = text or ""
    for name, pattern in _PATTERNS:
        if name not in REDACTED_TYPES:
            continue
        out = _re.sub(_unanchored(pattern.pattern),
                      lambda m, _k=name: mask_value(m.group(0), _k) or "",
                      out)
    return out


def _structural_name_part(findings: list) -> str:
    """What the leading finding is ABOUT, in schema terms.

    Columns and finding kinds come from the catalogue; they cannot contain a
    row value. A finding's `title` can and does, which is why it is not used
    here even though it reads better. Redaction alone would leave the name one
    new phrasing in `insights.py` away from leaking again -- so the name is
    built from things that are structurally incapable of carrying data.
    """
    kinds = {
        "trend": "trend", "standout": "breakdown", "concentration": "breakdown",
        "correlation": "relationship", "outlier": "outliers",
        "missing": "data quality",
    }
    for finding in findings or []:
        columns = [c for c in (finding.get("columns") or []) if c]
        if not columns:
            continue
        shape = kinds.get((finding.get("kind") or "").lower(), "overview")
        if len(columns) >= 2:
            return f"{columns[0]} by {columns[1]} ({shape})"
        return f"{columns[0]} ({shape})"
    return ""


def _compose_name(dataset_name: str | None, findings: list, run_id: int,
                  taken: set[str]) -> str:
    """A name derived from the data, not from a template or a model.

    WHY NOT ASK THE MODEL
    ---------------------
    Step 4 established that the model may be absent, so a name that depended on
    it would mean two behaviours for the same work -- and this name lands in
    Recents with nobody reviewing it. A derivation can be pinned by a test; a
    generated one cannot.

    WHY NOT THE COMPOSER'S OWN NAME
    -------------------------------
    `report_composer.compose_page` returns the fixed string "Auto-generated
    insights". Every automated report in an install would carry it, which in a
    list of Recents is the same as having no name at all.

    DISTINCTNESS IS GUARANTEED, NOT HOPED FOR
    -----------------------------------------
    The dataset may contribute nothing: one dataset in this install is named
    "2", and a dataset with too few rows produces no findings. So the base is
    whatever the data gives, and a name already taken gets the run id appended
    -- which is unique by construction. Two nightly runs over the same dataset
    therefore differ even when every input to them is identical.
    """
    source = (dataset_name or "").strip() or "Dataset"
    about = _structural_name_part(findings)
    base = f"{source} — {about}" if about else f"{source} — automated review"

    #: Reserved so the suffix survives truncation. The first version appended
    #: "(run N)" and THEN truncated to the column width, which on a long base
    #: removed the suffix it had just added -- two runs produced names differing
    #: by a single trailing space. Truncate the BASE, then append.
    room = MAX_REPORT_NAME - len(f" (run {run_id})")
    base = base[:MAX_REPORT_NAME].rstrip(" —")
    if base not in taken:
        return base
    return f"{base[:room].rstrip(' —')} (run {run_id})"


async def _compose_step(ctx: StepContext, session) -> str:
    """Write the report, from the widgets step 5 ACCEPTED.

    Never the raw proposal: composing what the gate rejected would put those
    widgets on the page anyway and reduce step 5 to a log line.

    RELATIONSHIPS ARE EAGER-LOADED FROM THE START
    ---------------------------------------------
    `Report.pages` and `ReportPage.widgets` are both lazy, and a lazy
    relationship access out here raises MissingGreenlet rather than being slow
    -- see the note above `_load_creator`. This is the third place in this
    module to need that and the first to be written with it rather than after
    it: `tests/test_automation_runner.py::TestComposeSurvivesAColdSession`
    clears the identity map before the composing tick, which is the only shape
    of test that catches it.
    """
    from sqlalchemy.orm import selectinload

    from ..core.capability import can_read_dataset
    from ..models.models import Dataset, Report, ReportPage, ReportWidget

    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"cannot compose for subject_type={ctx.subject_type!r}; "
            f"step 6 composes dataset reports")

    ds = await session.get(Dataset, ctx.subject_id)
    if ds is None or ds.org_id != ctx.org_id:
        raise StepRefused("dataset not found")

    user = await _load_creator(session, ctx.user_id)
    if user is None:
        raise StepRefused("creator is no longer available")
    if not await can_read_dataset(session, user, ds.id):
        raise StepRefused("dataset not found for this creator")

    previous = await _previous_output_ref(session, ctx, "review")
    try:
        reviewed = await asyncio.to_thread(_read_profile_artifact, previous)
    except (FileNotFoundError, ValueError) as exc:
        raise StepRefused(
            "step 5's review is missing or unreadable; nothing to compose"
        ) from exc

    accepted = reviewed.get("accepted") or []
    if not accepted:
        raise StepRefused(
            "no widget survived review; there is nothing to compose")

    scan_ref = reviewed.get("source_propose")
    findings: list = []
    narrative = ""
    try:
        proposed = await asyncio.to_thread(_read_profile_artifact, scan_ref)
        scan = await asyncio.to_thread(
            _read_profile_artifact, proposed.get("source_scan"))
        findings = scan.get("findings") or []
        narrative = scan.get("narrative") or ""
    except (FileNotFoundError, ValueError):
        # The scan's prose is an improvement to the page, not a precondition
        # for it. A missing narrative costs a paragraph; refusing here would
        # cost the whole report.
        log.info("automation run %s: composing without the scan narrative",
                 ctx.run_id)

    from sqlalchemy import select as _select
    taken = set((await session.execute(
        _select(Report.name).where(Report.org_id == ctx.org_id))).scalars().all())
    name = _compose_name(ds.name, findings, ctx.run_id, taken)

    # Scrubbed BEFORE composing, not after: compose_page copies finding titles
    # into widget titles and the narrative into a text widget, so scrubbing the
    # output would mean finding every place it had already been copied to.
    narrative = redact_row_values(narrative)
    findings = [{**f, "title": redact_row_values(f.get("title"))}
                for f in (findings or [])]

    def _page() -> dict:
        from .report_composer import compose_page
        return compose_page(findings, accepted, narrative or None)

    composed = await asyncio.to_thread(_page)

    report = Report(
        name=name,
        description=redact_row_values(narrative) or None,
        dataset_id=ds.id,
        org_id=ctx.org_id,
        created_by=ctx.user_id,
        # The marker. Without it Recents cannot tell this from a draft somebody
        # started and abandoned, and Home has nothing to filter on.
        origin=REPORT_ORIGIN_AUTOMATION,
    )
    session.add(report)
    await session.flush()

    page = ReportPage(report_id=report.id, name="Overview", position=0)
    session.add(page)
    await session.flush()

    for widget in composed.get("widgets") or []:
        session.add(ReportWidget(
            page_id=page.id,
            widget_type=widget.get("widget_type"),
            title=widget.get("title") or "",
            config=widget.get("config") or {},
            layout=widget.get("layout") or {},
        ))
    await session.flush()

    await record_run_result(session, ctx.run_id,
                            result_report_id=report.id, result_report_name=name)

    # Eager-loaded, because counting what was written means walking
    # Report -> pages -> widgets, and both hops are lazy. A bare re-read here
    # is a MissingGreenlet on any tick that did not create these rows.
    written = (await session.execute(
        _select(Report).where(Report.id == report.id)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
    )).scalar_one()
    widget_count = sum(len(p.widgets) for p in written.pages)

    payload = {
        "dataset_id": ds.id,
        "report_id": report.id,
        "report_name": name,
        "origin": REPORT_ORIGIN_AUTOMATION,
        "widgets_composed": widget_count,
        "widgets_accepted": len(accepted),
        "source_review": previous,
    }
    return await asyncio.to_thread(
        _write_step_artifact, ctx.org_id, ctx.run_id, "compose", payload)


# ── step 7: notify ───────────────────────────────────────────────────────────

async def _notify_step(ctx: StepContext, session) -> str:
    """Tell the creator the report is ready.

    Consumes step 6's RECORD, not merely its ref: a compose ref with no report
    id behind it is a link to nothing, and the honest output for that is a
    refusal, not a bell. Returns a db:// ref rather than writing an artifact
    -- the notification row IS the output -- and that ref commits in the same
    transaction as the row, so a crash between the two cannot send twice: the
    resume re-runs both or neither.
    """
    if ctx.subject_type != "dataset" or ctx.subject_id is None:
        raise StepRefused(
            f"notify only handles datasets, not {ctx.subject_type!r}")
    await _previous_output_ref(session, ctx, "compose")
    run = await session.get(AutomationRun, ctx.run_id)
    if run is None or run.result_report_id is None:
        raise StepRefused("compose recorded no report to announce")
    await notify_run(session, run)
    return f"db://notifications/user/{run.created_by}/run/{run.id}"


#: The chain, in order. This list is the single source of truth for both the
#: step names and their sequence: `create_run` lays down one row per entry and
#: `tick` looks each row's spec up by name, so adding a step is one line here.
STEPS: list[StepSpec] = [
    StepSpec(name="profile", run=_profile_step),
    StepSpec(name="describe", run=_describe_step),
    StepSpec(name="scan", run=_scan_step),
    StepSpec(name="propose", run=_propose_step),
    StepSpec(name="review", run=_review_step),
    StepSpec(name="compose", run=_compose_step),
    StepSpec(name="notify", run=_notify_step),
]


# ── creating a run ───────────────────────────────────────────────────────────

async def create_run(session, *, org_id: int, created_by: int,
                     trigger: str = "manual",
                     subject_type: str | None = None,
                     subject_id: int | None = None) -> AutomationRun:
    """Create a run and lay down one pending step per entry in `STEPS`.

    The steps are materialised up front rather than discovered as the chain
    advances, so a half-finished run is legible in a list view: you can see
    which of the seven it reached without replaying anything.
    """
    run = AutomationRun(
        org_id=org_id, created_by=created_by, trigger=trigger,
        subject_type=subject_type, subject_id=subject_id, status="pending",
        created_at=datetime.utcnow(),
    )
    session.add(run)
    await session.flush()
    for position, spec in enumerate(STEPS, start=1):
        session.add(AutomationStep(run_id=run.id, name=spec.name,
                                   order=position, status="pending",
                                   attempts=0))
    await session.commit()
    return run


# ── advisory locking, so N workers do not run the same step ──────────────────

def advisory_lock_key(run_id: int) -> int:
    """A stable per-run key for pg_try_advisory_lock, which takes a bigint.

    Hashed rather than using the id directly, and namespaced distinctly from
    `refresh_scheduler.advisory_lock_key`, so an automation run and a dataset
    refresh with the same numeric id cannot collide.
    """
    digest = hashlib.sha256(f"datalytics.automation.run.{run_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") - 2**63


async def _try_lock(session, key: int) -> bool:
    """Take the lock, or report that another worker holds it.

    True on dialects without advisory locks: those are single-process
    deployments, where there is nothing to protect against. Same convention
    as the refresh scheduler.
    """
    if session.bind.dialect.name != "postgresql":
        return True
    return bool((await session.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": key})).scalar())


async def _unlock(session, key: int) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


# ── bookkeeping ──────────────────────────────────────────────────────────────

def _spec_for(name: str) -> StepSpec | None:
    for spec in STEPS:
        if spec.name == name:
            return spec
    return None


async def _fail(session, run: AutomationRun, step: AutomationStep,
                error: str, now: datetime) -> None:
    """Record WHY, count the attempt, and schedule the retry.

    Every failure path in this module goes through here. A step that ended
    without either an `output_ref` or an `error` is the silent failure this
    design exists to prevent, and there is exactly one place to get that
    wrong.
    """
    step.status = "failed"
    step.error = (error or "unknown error")[:MAX_ERROR_CHARS]
    step.attempts = (step.attempts or 0) + 1
    step.next_attempt_at = now + timedelta(minutes=backoff_minutes(step.attempts))
    step.finished_at = now
    run.status = "failed"
    await session.commit()
    log.warning("automation run %s step %s failed (attempt %s), next try in "
                "%s min: %s", run.id, step.name, step.attempts,
                backoff_minutes(step.attempts), step.error)


async def _succeed(session, run: AutomationRun, step: AutomationStep,
                   steps: list[AutomationStep], output_ref: str,
                   now: datetime) -> None:
    step.status = "ok"
    step.output_ref = output_ref
    #: Cleared on purpose: a step that recovered must not keep advertising a
    #: failure that no longer applies. The attempt count is kept -- that a
    #: step needed three tries is worth knowing afterwards.
    step.error = None
    step.next_attempt_at = None
    step.finished_at = now

    remaining = [s for s in steps if s is not step and not s.output_ref]
    if run.status == NEEDS_REVIEW:
        # The step succeeded -- it reviewed, and its artifact says what it
        # found -- but it stopped the RUN for a person. Saying "running" here
        # would put it straight back in the queue on the next tick and undo the
        # only thing needs_review exists to do. The step is the one place that
        # knows a judgement was made, so its verdict wins over the default.
        pass
    elif remaining:
        run.status = "running"
    else:
        run.status = "done"
        run.finished_at = now
        # A finished run's artifacts are a copy of one person's rows with
        # nothing left to read them. Removed here rather than by a sweeper, so
        # the disk is reclaimed at the moment it stops being needed.
        discard_run_artifacts(run.org_id, run.id)
    await session.commit()


async def _finalise_if_complete(session, run: AutomationRun,
                                steps: list[AutomationStep],
                                now: datetime) -> None:
    """A run whose steps all carry a ref is done, however it got that way."""
    run.status = "done"
    if run.finished_at is None:
        run.finished_at = now
    for step in steps:
        if step.output_ref and step.status != "ok":
            step.status = "ok"
    discard_run_artifacts(run.org_id, run.id)
    await session.commit()


# ── the tick ─────────────────────────────────────────────────────────────────

async def tick(session, now: datetime | None = None) -> bool:
    """Advance the queue by exactly one step. Returns True if work was done.

    `now` is a parameter rather than read from the clock so a test can step
    past a backoff without sleeping -- the same idiom `record_failure` uses.
    """
    now = now or datetime.utcnow()

    runs = (await session.execute(
        select(AutomationRun)
        .where(AutomationRun.status.in_(ACTIVE_RUN_STATUSES))
        .order_by(AutomationRun.created_at, AutomationRun.id)
        .limit(MAX_RUNS_SCANNED_PER_TICK)
    )).scalars().all()

    for run in runs:
        steps = (await session.execute(
            select(AutomationStep)
            .where(AutomationStep.run_id == run.id)
            .order_by(AutomationStep.order)
        )).scalars().all()

        # The resume point: the first step with no output_ref. Anything
        # before it has already been paid for, whatever its status says.
        pending = next((s for s in steps if not s.output_ref), None)
        if pending is None:
            if steps and run.status != "done":
                await _finalise_if_complete(session, run, steps, now)
                return True
            continue

        # In backoff: yield the tick to the next run rather than returning,
        # so one sick run is not a head-of-line block for the whole queue.
        if pending.next_attempt_at is not None and \
                _as_utc_naive(now) < _as_utc_naive(pending.next_attempt_at):
            continue

        key = advisory_lock_key(run.id)
        if not await _try_lock(session, key):
            continue  # another worker has this run

        try:
            # Identity first. A run whose creator is gone is failed with the
            # reason recorded -- never executed with no RLS identity.
            user = (await session.execute(
                select(User).where(User.id == run.created_by)
            )).scalars().first() if run.created_by is not None else None
            if user is None:
                await _fail(session, run, pending,
                            "creator is no longer available; refusing to run a "
                            "step without an identity to apply row security as",
                            now)
                return True

            spec = _spec_for(pending.name)
            if spec is None:
                await _fail(session, run, pending,
                            f"no implementation registered for step "
                            f"{pending.name!r}", now)
                return True

            ctx = StepContext(
                run_id=run.id, org_id=run.org_id,
                user_id=user.id, user_email=user.email,
                trigger=run.trigger, subject_type=run.subject_type,
                subject_id=run.subject_id, step_name=pending.name,
            )

            pending.status = "running"
            pending.started_at = now
            run.status = "running"
            await session.commit()

            try:
                # The step owns its own threading: it reads the database on
                # this loop and wraps its blocking work in asyncio.to_thread
                # itself -- see StepSpec. The runner cannot impose that for
                # it, because a step that needs a session cannot run in a
                # thread at all.
                output_ref = await spec.run(ctx, session)
            except Exception as exc:  # noqa: BLE001 -- every failure is recorded
                reason = (str(exc) if isinstance(exc, StepRefused)
                          else f"{type(exc).__name__}: {exc}")
                # A step that reached the database opened a transaction, and
                # rolling it back EXPIRES every instance in this session. The
                # bookkeeping below reads `step.attempts`, and reading an
                # expired attribute from async code raises MissingGreenlet --
                # which would turn a recorded failure into an unrecorded
                # crash, the exact silent failure this module exists to
                # prevent. So the ids are taken first and the rows re-read
                # after, the same reason `refresh_scheduler.run_items`
                # iterates ids rather than instances.
                run_id, step_id = run.id, pending.id
                await session.rollback()
                run = await session.get(AutomationRun, run_id)
                pending = await session.get(AutomationStep, step_id)
                if run is None or pending is None:
                    log.warning("automation run %s vanished while step %s was "
                                "failing; nothing to record", run_id, step_id)
                    return True
                await _fail(session, run, pending, reason, now)
                return True

            if not output_ref:
                await _fail(session, run, pending,
                            "step returned no output_ref; a step must either "
                            "produce a result or say why it could not", now)
                return True

            await _succeed(session, run, pending, steps, str(output_ref), now)
            return True
        finally:
            await _unlock(session, key)

    return False


# ── restart recovery ─────────────────────────────────────────────────────────

async def reap_stuck_automation_steps(session) -> int:
    """Fail steps a restart orphaned, so a dead run stops looking alive.

    Same problem `reap_stuck_sync_runs` solves for metadata syncs: `tick`
    marks a step `running` before threading it, and a process that dies mid-step
    leaves that row saying `running` forever. Nothing would ever correct it,
    and because the step has no `output_ref` the run would sit at the head of
    the queue looking like progress.

    Called once at startup, inside the startup lock, where "still running" is
    impossible by definition: no thread from the previous process survived it.
    A step with an `output_ref` is left alone -- it finished, and only the
    status commit was lost.
    """
    now = datetime.utcnow()
    rows = (await session.execute(
        select(AutomationStep).where(AutomationStep.status == "running")
    )).scalars().all()
    reaped = 0
    for step in rows:
        if step.output_ref:
            step.status = "ok"          # it finished; only the commit was lost
            continue
        step.status = "failed"
        step.error = "Interrupted by a server restart"
        step.attempts = (step.attempts or 0) + 1
        step.next_attempt_at = now + timedelta(
            minutes=backoff_minutes(step.attempts))
        step.finished_at = now
        run = await session.get(AutomationRun, step.run_id)
        if run is not None and run.status not in TERMINAL_RUN_STATUSES:
            run.status = "failed"
        reaped += 1
    if rows:
        await session.commit()
    if reaped:
        log.warning("Reaped %s automation step(s) left running by a restart",
                    reaped)
    return reaped
