"""The Power Pi automation runner: one step per tick, resumable, never silent.

These tests pin the four properties that make an unattended orchestrator safe
to leave running, and they are written against the *contract*, not the stubs --
the seven real steps land later and must not change any assertion here.

  1. A run walks its whole chain to `done` across successive ticks.
  2. A failure stops at the failing step, records WHY, and the next attempt
     resumes there -- not at step 1. A run that redid step 1 after failing at
     step 5 would re-profile and re-scan a dataset every retry.
  3. A step that already has an `output_ref` is skipped, so a resumed run
     never repeats work it already paid for.
  4. One sick run cannot starve the queue. The scheduler is shared, so a run
     stuck in backoff must not be a head-of-line block for everyone else.

Plus the property the spec states in prose rather than as a test: a step may
never run without the creator's identity. RLS in this product is per-user, so
a step that ran headless would compose a dashboard from rows the creator is
not allowed to see -- and it would look like a success.
"""
from __future__ import annotations

import pytest

from app.models.models import AutomationRun, AutomationStep
from app.services import automation_runner
from app.services.automation_runner import StepSpec


# ── helpers ──────────────────────────────────────────────────────────────────

def recording_steps(calls: list[str], *, fails: set[str] = frozenset()):
    """Seven steps with the real names that append to `calls` when they run.

    Asserting on this list is how "step 1 was not re-run" is observable at all;
    the shipped stubs are deliberately side-effect-free.
    """
    def make(name: str):
        async def _run(ctx, session):
            calls.append(name)
            if name in fails:
                raise RuntimeError(f"{name} blew up")
            assert ctx.user_id is not None, "a step ran without a user identity"
            assert session is not None, "a step ran with no database handle"
            return f"stub://{name}/{ctx.run_id}"
        return StepSpec(name=name, run=_run)

    return [make(spec.name) for spec in automation_runner.STEPS]


async def _seed(db_session, email="owner@example.invalid", org_name="Power Pi"):
    from app.services.auth_provisioning import create_organization_with_admin
    org, _role, user = await create_organization_with_admin(
        db_session, org_name, email, "password")
    await db_session.commit()
    return org, user


async def _steps_of(db_session, run_id: int) -> list[AutomationStep]:
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(AutomationStep)
        .where(AutomationStep.run_id == run_id)
        .order_by(AutomationStep.order)
    )).scalars().all()
    for r in rows:
        await db_session.refresh(r)
    return rows


# ── 1. the happy path ────────────────────────────────────────────────────────

class TestARunWalksItsWholeChain:
    async def test_seven_ticks_take_a_run_from_pending_to_done(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        for _ in range(len(automation_runner.STEPS)):
            assert await automation_runner.tick(db_session) is True

        await db_session.refresh(run)
        assert run.status == "done"
        assert run.finished_at is not None
        assert calls == ["profile", "describe", "scan", "propose",
                         "review", "compose", "notify"]
        assert all(s.status == "ok" and s.output_ref for s in
                   await _steps_of(db_session, run.id))

    async def test_a_tick_runs_exactly_one_step(self, db_session, monkeypatch):
        """The whole point of the design: a tick is a slice, not a chain."""
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        await automation_runner.tick(db_session)

        assert calls == ["profile"]
        await db_session.refresh(run)
        assert run.status == "running"

    async def test_an_idle_queue_reports_no_work(self, db_session, monkeypatch):
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps([]))
        assert await automation_runner.tick(db_session) is False


# ── 2. failure stops, records, and resumes in place ──────────────────────────

class TestAFailureResumesWhereItStopped:
    async def test_step_four_fails_and_the_first_three_stay_ok(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS",
                            recording_steps(calls, fails={"propose"}))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        for _ in range(4):
            await automation_runner.tick(db_session)

        await db_session.refresh(run)
        assert run.status == "failed"

        steps = await _steps_of(db_session, run.id)
        assert [s.status for s in steps[:3]] == ["ok", "ok", "ok"]
        failed = steps[3]
        assert failed.name == "propose"
        assert failed.status == "failed"
        assert "propose blew up" in (failed.error or "")
        assert failed.attempts == 1
        assert failed.next_attempt_at is not None
        assert failed.output_ref is None
        # Nothing past the failure was touched.
        assert all(s.status == "pending" for s in steps[4:])

    async def test_the_next_attempt_retries_only_the_failed_step(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS",
                            recording_steps(calls, fails={"propose"}))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        for _ in range(4):
            await automation_runner.tick(db_session)
        assert calls == ["profile", "describe", "scan", "propose"]

        # Let the backoff elapse rather than sleeping through it. `now` is a
        # parameter for exactly this reason -- same idiom as record_failure.
        from datetime import datetime, timedelta
        later = datetime.utcnow() + timedelta(days=2)

        calls.clear()
        await automation_runner.tick(db_session, now=later)

        assert calls == ["propose"], "a retry must resume in place, not restart"

    async def test_a_step_in_backoff_is_not_retried_early(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS",
                            recording_steps(calls, fails={"profile"}))

        org, user = await _seed(db_session)
        await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        await automation_runner.tick(db_session)
        calls.clear()

        assert await automation_runner.tick(db_session) is False
        assert calls == []

    async def test_a_retry_that_succeeds_clears_the_error(
            self, db_session, monkeypatch):
        calls: list[str] = []
        flaky = {"scan"}
        monkeypatch.setattr(automation_runner, "STEPS",
                            recording_steps(calls, fails=flaky))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        for _ in range(3):
            await automation_runner.tick(db_session)

        # The source of the failure goes away; the same step is tried again.
        calls2: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls2))
        from datetime import datetime, timedelta
        await automation_runner.tick(db_session,
                                     now=datetime.utcnow() + timedelta(days=2))

        steps = await _steps_of(db_session, run.id)
        scan = next(s for s in steps if s.name == "scan")
        assert scan.status == "ok"
        assert scan.output_ref
        assert scan.error is None, "a recovered step must not keep a stale error"
        await db_session.refresh(run)
        assert run.status == "running"


# ── 3. an existing output_ref means the work is already paid for ─────────────

class TestWorkIsNeverRepeated:
    async def test_a_step_with_an_output_ref_is_skipped(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        steps = await _steps_of(db_session, run.id)
        steps[0].output_ref = "already://profiled"
        steps[0].status = "ok"
        await db_session.commit()

        await automation_runner.tick(db_session)

        assert calls == ["describe"], "the skip must not consume the tick"
        steps = await _steps_of(db_session, run.id)
        assert steps[0].output_ref == "already://profiled"

    async def test_an_output_ref_survives_even_if_the_status_lies(
            self, db_session, monkeypatch):
        """output_ref is the resume marker, not status -- a process killed
        between writing the ref and committing the status must not redo it."""
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        steps = await _steps_of(db_session, run.id)
        steps[0].output_ref = "half://written"
        steps[0].status = "running"
        await db_session.commit()

        await automation_runner.tick(db_session)

        assert calls == ["describe"]


# ── 4. a sick run must not starve the queue ──────────────────────────────────

class TestOneBadRunDoesNotBlockTheOthers:
    async def test_a_run_in_backoff_yields_the_tick_to_the_next_run(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS",
                            recording_steps(calls, fails={"profile"}))

        org, user = await _seed(db_session)
        sick = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=1)
        healthy = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=2)

        await automation_runner.tick(db_session)          # sick run fails
        await db_session.refresh(sick)
        assert sick.status == "failed"

        # Only the healthy run's steps may run now.
        good: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(good))

        assert await automation_runner.tick(db_session) is True
        assert good == ["profile"]

        healthy_steps = await _steps_of(db_session, healthy.id)
        assert healthy_steps[0].status == "ok"
        sick_steps = await _steps_of(db_session, sick.id)
        assert sick_steps[0].status == "failed"

    async def test_the_older_run_is_served_first(self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))

        org, user = await _seed(db_session)
        first = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=1)
        second = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=2)

        await automation_runner.tick(db_session)

        assert (await _steps_of(db_session, first.id))[0].status == "ok"
        assert (await _steps_of(db_session, second.id))[0].status == "pending"


# ── the identity requirement, as a test rather than a comment ────────────────

class TestAStepNeverRunsWithoutTheCreator:
    async def test_a_run_whose_creator_is_gone_fails_instead_of_running(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))

        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        await db_session.delete(user)
        await db_session.commit()

        assert await automation_runner.tick(db_session) is True
        assert calls == [], "no step may run without the creator's identity"

        await db_session.refresh(run)
        assert run.status == "failed"
        first = (await _steps_of(db_session, run.id))[0]
        assert first.status == "failed"
        assert "creator" in (first.error or "").lower()

    async def test_every_step_receives_the_creators_identity(
            self, db_session, monkeypatch):
        seen: list[tuple[int, str]] = []

        def make(name: str):
            async def _run(ctx, session):
                seen.append((ctx.user_id, ctx.user_email))
                return f"stub://{name}"
            return StepSpec(name=name, run=_run)

        monkeypatch.setattr(automation_runner, "STEPS",
                            [make(s.name) for s in automation_runner.STEPS])

        org, user = await _seed(db_session, email="rls@example.invalid")
        await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        for _ in range(7):
            await automation_runner.tick(db_session)

        assert len(seen) == 7
        assert set(seen) == {(user.id, "rls@example.invalid")}


# ── step 1: profile, for real ────────────────────────────────────────────────

class ProfileFixtures:
    """Shared setup for the profile step.

    A NON-ADMIN role throughout, deliberately: org admins bypass both row and
    column security (`core/rls`), so a security test written against the admin
    that `create_organization_with_admin` returns would pass no matter what
    the step did.
    """

    @staticmethod
    async def member(db_session, org, email, *, name="Member"):
        from app.models.models import Role, User
        from app.core.security import hash_password
        role = Role(org_id=org.id, name=name, is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org.id, email=email, role_id=role.id,
                    password_hash=hash_password("password"), is_active=True)
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()
        return role, user

    @staticmethod
    async def dataset(db_session, org, owner, path, *, mode="import",
                      filename=None):
        from app.models.models import Dataset
        ds = Dataset(name="Sales", filename=filename if filename is not None else str(path),
                     org_id=org.id, mode=mode, created_by=owner.id if owner else None)
        db_session.add(ds)
        await db_session.flush()
        await db_session.commit()
        return ds


@pytest.fixture
def sales_csv(tmp_path):
    """Three regions, one cost column the tests deny, one row EMEA only."""
    import pandas as pd
    p = tmp_path / "sales.csv"
    pd.DataFrame({
        "region":  ["EMEA", "EMEA", "APAC", "AMER"],
        "product": ["alpha", "beta", "gamma", "delta"],
        "revenue": [100.0, 50.0, 30.0, 20.0],
        "cost":    [10.0, 5.0, 3.0, 2.0],
    }).to_csv(p, index=False)
    return p


@pytest.fixture
def artifact_dir(tmp_path, monkeypatch):
    """Point the upload root at a temp dir so profile artifacts land there."""
    from app.core.config import settings
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(root))
    return root


async def _run_profile(db_session, org, user, ds_id):
    """Create a run aimed at `ds_id` and tick once. Returns (run, step)."""
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    did = await automation_runner.tick(db_session)
    await db_session.refresh(run)
    step = (await _steps_of(db_session, run.id))[0]
    return run, step, did


def _load_artifact(step, artifact_dir):
    import json
    import os
    assert step.output_ref.startswith("file://"), step.output_ref
    rel = step.output_ref[len("file://"):]
    path = os.path.join(str(artifact_dir), rel)
    assert os.path.exists(path), f"output_ref points at nothing: {path}"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class TestProfileStepHappyPath:
    async def test_it_writes_a_real_profile_artifact(
            self, db_session, sales_csv, artifact_dir):
        org, admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        run, step, did = await _run_profile(db_session, org, user, ds.id)

        assert did is True
        assert step.name == "profile"
        assert step.status == "ok", step.error
        assert step.error is None
        profile = _load_artifact(step, artifact_dir)
        assert profile["row_count"] == 4
        assert {c["name"] for c in profile["columns"]} == {
            "region", "product", "revenue", "cost"}
        await db_session.refresh(run)
        assert run.status == "running"          # six steps still to go

    async def test_the_rest_of_the_chain_still_walks_to_done(
            self, db_session, sales_csv, artifact_dir):
        """Profile being real must not break the steps behind it."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(7):
            assert await automation_runner.tick(db_session) is True

        await db_session.refresh(run)
        assert run.status == "done", [s.error for s in
                                      await _steps_of(db_session, run.id)]


class TestProfileRunsAsTheCreator:
    async def test_the_creators_row_rule_narrows_the_profile(
            self, db_session, sales_csv, artifact_dir):
        """The whole reason created_by is load-bearing.

        Asserts on a VALUE the rule excludes being absent from the profile --
        not on resolve_rls_expr having been called.
        """
        from app.models.models import RowSecurityRule
        org, _admin = await _seed(db_session)
        role, user = await ProfileFixtures.member(
            db_session, org, "emea@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                                       filter_expr="region == 'EMEA'"))
        await db_session.commit()

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "ok", step.error

        profile = _load_artifact(step, artifact_dir)
        assert profile["row_count"] == 2, "the rule did not narrow the frame"
        region = next(c for c in profile["columns"] if c["name"] == "region")
        labels = {v["value"] for v in region["top_values"]}
        assert labels == {"EMEA"}
        assert "APAC" not in labels and "AMER" not in labels

    async def test_a_denied_column_never_enters_the_profile(
            self, db_session, sales_csv, artifact_dir):
        from app.models.models import ColumnSecurityRule
        org, _admin = await _seed(db_session)
        role, user = await ProfileFixtures.member(
            db_session, org, "nocost@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id,
                                          denied_columns=["cost"]))
        await db_session.commit()

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "ok", step.error

        profile = _load_artifact(step, artifact_dir)
        names = {c["name"] for c in profile["columns"]}
        names |= {c["name"] for c in profile.get("other_columns", [])}
        assert "cost" not in names, (
            "a column this role may not see reached the profile, which is what "
            "gets sent to a model")
        assert "revenue" in names


class TestProfileRefusesRatherThanGuessing:
    """Every refusal: status failed, a reason recorded, and NO output_ref."""

    async def _assert_refused(self, step, *, mentions: str):
        assert step.status == "failed"
        assert step.output_ref is None, "an unearned output_ref was written"
        assert step.error, "a failure with no reason is the thing we forbid"
        assert mentions.lower() in step.error.lower(), step.error

    async def test_dataset_gone(self, db_session, artifact_dir):
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "a@example.invalid")
        _run, step, did = await _run_profile(db_session, org, user, 999_999)
        assert did is True
        await self._assert_refused(step, mentions="not found")

    async def test_a_dataset_in_another_org(self, db_session, sales_csv,
                                            artifact_dir):
        from app.services.auth_provisioning import create_organization_with_admin
        org_a, _admin_a = await _seed(db_session, email="a@example.invalid",
                                      org_name="A")
        org_b, _role_b, _admin_b = await create_organization_with_admin(
            db_session, "B", "b-admin@example.invalid", "password")
        await db_session.commit()
        _role, user = await ProfileFixtures.member(
            db_session, org_a, "member-a@example.invalid")
        foreign = await ProfileFixtures.dataset(db_session, org_b, None, sales_csv)

        _run, step, _ = await _run_profile(db_session, org_a, user, foreign.id)
        await self._assert_refused(step, mentions="not found")
        assert "Sales" not in (step.error or ""), (
            "the refusal named a dataset in another tenant")

    async def test_an_org_admin_still_cannot_profile_another_tenants_dataset(
            self, db_session, sales_csv, artifact_dir):
        """The tenancy check is the ONLY guard for an admin.

        `can_read_dataset` short-circuits to True for `is_org_admin`, so the
        org comparison in the step is what stands between an admin and another
        tenant's rows. A mutation that deleted it survived every other test in
        this file, because for a non-admin the readable-set query is itself
        org-filtered and refuses independently. This pins the guard directly.
        """
        from app.services.auth_provisioning import create_organization_with_admin
        org_a, admin_a = await _seed(db_session, email="admin-a@example.invalid",
                                     org_name="Tenant A")
        org_b, _role_b, _admin_b = await create_organization_with_admin(
            db_session, "Tenant B", "admin-b@example.invalid", "password")
        await db_session.commit()
        foreign = await ProfileFixtures.dataset(db_session, org_b, None, sales_csv)

        _run, step, _ = await _run_profile(db_session, org_a, admin_a, foreign.id)

        assert step.status == "failed", (
            "an org admin profiled a dataset belonging to another tenant")
        assert step.output_ref is None
        await self._assert_refused(step, mentions="not found")

    async def test_the_creator_cannot_read_the_dataset(
            self, db_session, sales_csv, artifact_dir):
        org, _admin = await _seed(db_session)
        _r1, owner = await ProfileFixtures.member(
            db_session, org, "dataset-owner@example.invalid", name="Owners")
        _r2, outsider = await ProfileFixtures.member(
            db_session, org, "outsider@example.invalid", name="Outsiders")
        ds = await ProfileFixtures.dataset(db_session, org, owner, sales_csv)

        _run, step, _ = await _run_profile(db_session, org, outsider, ds.id)
        await self._assert_refused(step, mentions="not found")

    async def test_a_directquery_dataset(self, db_session, sales_csv,
                                         artifact_dir):
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "dq@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv,
                                           mode="directquery")

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        await self._assert_refused(step, mentions="directquery")

    async def test_the_file_is_missing_from_disk(self, db_session, tmp_path,
                                                 artifact_dir):
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "gone@example.invalid")
        ds = await ProfileFixtures.dataset(
            db_session, org, user, None,
            filename=str(tmp_path / "never-written.csv"))

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "failed"
        assert step.output_ref is None
        assert step.error

    async def test_a_refusal_is_retried_not_abandoned(
            self, db_session, artifact_dir):
        """A refusal is still a failure: it earns backoff, and the run stays
        resumable at the same step rather than dying."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "retry@example.invalid")
        run, step, _ = await _run_profile(db_session, org, user, 999_999)

        assert step.attempts == 1
        assert step.next_attempt_at is not None
        await db_session.refresh(run)
        assert run.status == "failed"
        assert run.status not in automation_runner.TERMINAL_RUN_STATUSES


# ── the shipped skeleton itself ──────────────────────────────────────────────

class TestTheShippedStepList:
    def test_the_seven_steps_are_named_and_ordered_as_specified(self):
        assert [s.name for s in automation_runner.STEPS] == [
            "profile", "describe", "scan", "propose", "review", "compose", "notify"]

    async def test_the_shipped_chain_runs_end_to_end_unmonkeypatched(
            self, db_session, sales_csv, artifact_dir):
        """The chain must be walkable exactly as shipped.

        Step 1 is real now, so this needs a real dataset -- which is the point:
        this is the only test that exercises the SHIPPED list rather than a
        recording double, and it is what catches a new step wired in wrongly.
        """
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "shipped@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="schedule", subject_type="dataset", subject_id=ds.id)

        for _ in range(7):
            assert await automation_runner.tick(db_session) is True

        await db_session.refresh(run)
        steps = await _steps_of(db_session, run.id)
        assert run.status == "done", [s.error for s in steps]
        assert all(s.output_ref for s in steps)
        # Every ref addresses something real -- an artifact on disk or a row
        # in the database. No stub is left; a step that regressed to one
        # would fail here, which is how this test noticed each step going
        # live. Looked up by name so inserting a step cannot repoint it.
        by_name = {s.name: s for s in steps}
        assert not any(s.output_ref.startswith("stub://") for s in steps), (
            [(s.name, s.output_ref) for s in steps])
        assert by_name["profile"].output_ref.startswith("file://")
        assert by_name["compose"].output_ref.startswith("file://")
        assert by_name["notify"].output_ref.startswith("db://notifications/"), (
            by_name["notify"].error)

    async def test_create_run_lays_down_one_row_per_step_in_order(
            self, db_session):
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)

        steps = await _steps_of(db_session, run.id)
        assert [s.order for s in steps] == list(range(1, 8))
        assert [s.name for s in steps] == [s.name for s in automation_runner.STEPS]
        assert all(s.status == "pending" and s.attempts == 0 for s in steps)
        assert run.status == "pending"




# ── step 1 also persists the secured frame ───────────────────────────────────
#
# Steps 3, 4 and 5 all need the ROWS, not just a description of them. The
# alternative to persisting them once here is each of those steps re-reading
# the dataset file and re-applying RLS, denied columns and prep in the right
# order -- three more copies of the ordering that
# test_rls_base_frame_choke_point exists to protect, and the third one is the
# one somebody gets wrong.
#
# So the frame is written once, already secured, beside the profile. Which
# makes it the most dangerous artifact the chain produces: profile.json holds
# samples, frame.parquet holds every row this creator may see. These tests
# assert the security on the FRAME, not on the profile that describes it.


def _frame_of(step, artifact_dir):
    """The parquet step 1 wrote, loaded. Follows frame_ref out of the profile
    rather than guessing the filename, so a change to the layout fails here
    rather than silently reading nothing."""
    import os

    import pandas as pd
    profile = _load_artifact(step, artifact_dir)
    ref = profile.get("frame_ref")
    assert ref and ref.startswith("file://"), f"no frame_ref in the profile: {ref}"
    path = os.path.join(str(artifact_dir), ref[len("file://"):])
    assert os.path.exists(path), f"frame_ref points at nothing: {path}"
    return pd.read_parquet(path)


class TestTheSecuredFrameIsPersisted:
    async def test_the_profile_names_a_frame_beside_it(
            self, db_session, sales_csv, artifact_dir):
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "frame@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "ok", step.error

        frame = _frame_of(step, artifact_dir)
        assert len(frame) == 4
        assert set(frame.columns) == {"region", "product", "revenue", "cost"}

    async def test_the_frame_carries_the_creators_rows_only(
            self, db_session, sales_csv, artifact_dir):
        """The profile equivalent of this test asserts on a SAMPLE. This one
        asserts on every row, which is what the artifact actually contains and
        what steps 3-5 will read."""
        from app.models.models import RowSecurityRule
        org, _admin = await _seed(db_session)
        role, user = await ProfileFixtures.member(
            db_session, org, "emeaframe@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                                       filter_expr="region == 'EMEA'"))
        await db_session.commit()

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "ok", step.error

        frame = _frame_of(step, artifact_dir)
        assert set(frame["region"]) == {"EMEA"}
        assert len(frame) == 2

    async def test_a_denied_column_is_absent_from_the_frame(
            self, db_session, sales_csv, artifact_dir):
        """A denied column in the profile leaks summary statistics. A denied
        column in the FRAME leaks every value."""
        from app.models.models import ColumnSecurityRule
        org, _admin = await _seed(db_session)
        role, user = await ProfileFixtures.member(
            db_session, org, "nocost@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id,
                                          denied_columns=["cost"]))
        await db_session.commit()

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "ok", step.error

        frame = _frame_of(step, artifact_dir)
        assert "cost" not in frame.columns

    async def test_no_temp_file_is_left_behind(
            self, db_session, sales_csv, artifact_dir):
        """Written to a temp name and moved into place, like the profile. A
        half-written parquet behind a committed ref is TRUNCATED CUSTOMER DATA
        reaching a model -- strictly worse than a half-written description."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "tmp@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        leftovers = [p for p in artifact_dir.rglob("*") if p.name.startswith(".")]
        assert not leftovers, f"temp artifacts survived: {leftovers}"


    async def test_a_crash_mid_write_leaves_no_frame_at_the_final_name(
            self, db_session, sales_csv, artifact_dir, monkeypatch):
        """THE property temp-then-replace buys, and the one the leftover-temp
        test above cannot see: writing in place leaves no temp file either, so
        that test passes for the broken implementation too. A mutation run
        proved it.

        Here the write dies partway. With the temp name,  was
        never created; without it, a TRUNCATED parquet sits at the final name
        and a later step reads short customer data as though it were whole.
        """
        import pandas as pd

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "crash@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        real = pd.DataFrame.to_parquet

        def _die(self, path, *a, **k):
            # Write something, then fail -- exactly the shape of a killed
            # worker, not a clean no-op.
            with open(path, "wb") as fh:
                fh.write(b"PAR1-partial")
            raise OSError("disk went away mid-write")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", _die)
        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        monkeypatch.setattr(pd.DataFrame, "to_parquet", real)

        assert step.status == "failed"
        assert not step.output_ref
        finals = list(artifact_dir.rglob("frame.parquet"))
        assert not finals, f"a truncated frame reached the final name: {finals}"


class TestTheFrameHasACeiling:
    async def test_an_oversized_frame_is_refused_with_a_reason(
            self, db_session, sales_csv, artifact_dir, monkeypatch):
        """Refuse rather than fill the disk. The same call import_row_cap
        makes: a bounded failure naming both numbers beats an unbounded write
        that takes the host down with it."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "automation_frame_max_mb", 0.000001)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "big@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "failed"
        assert not step.output_ref, "a ref was written for work that was refused"
        assert "too large" in (step.error or "").lower()

    async def test_the_refusal_leaves_no_partial_artifact(
            self, db_session, sales_csv, artifact_dir, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "automation_frame_max_mb", 0.000001)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "big2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        await _run_profile(db_session, org, user, ds.id)

        stray = [p for p in artifact_dir.rglob("*") if p.is_file()]
        assert not stray, f"a refused step left artifacts behind: {stray}"

    async def test_a_zero_ceiling_disables_the_check(
            self, db_session, sales_csv, artifact_dir, monkeypatch):
        """Same escape hatch import_row_cap gives an operator with the disk."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "automation_frame_max_mb", 0)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "nocap@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)

        _run, step, _ = await _run_profile(db_session, org, user, ds.id)
        assert step.status == "ok", step.error


class TestTheRunDirectoryIsCleanedUp:
    async def test_a_completed_run_leaves_nothing_on_disk(
            self, db_session, sales_csv, artifact_dir):
        """A run's artifacts exist to be handed between its own steps. Once it
        is done they are a copy of one person's rows sitting on disk with
        nothing reading it -- so they go, in one place, the way
        dataset_cleanup.py removes what a dataset leaves behind."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "clean@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)

        for _ in range(len(automation_runner.STEPS)):
            await automation_runner.tick(db_session)
        await db_session.refresh(run)
        assert run.status == "done"

        left = [p for p in artifact_dir.rglob(f"run_{run.id}/*") if p.is_file()]
        assert not left, f"a finished run left its frame on disk: {left}"

    async def test_an_unfinished_run_keeps_its_artifacts(
            self, db_session, sales_csv, artifact_dir):
        """The other half, and the one that matters for resume: a run still
        walking its chain must not have its inputs deleted underneath it."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "midway@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, sales_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)

        await automation_runner.tick(db_session)      # profile only
        await db_session.refresh(run)
        assert run.status != "done"

        left = [p for p in artifact_dir.rglob(f"run_{run.id}/*") if p.is_file()]
        assert left, "a mid-flight run lost the artifacts its next step reads"



# ── step 3: scan, for real ───────────────────────────────────────────────────
#
# The step the previous two existed to make possible. It runs `generate_insights`
# over the frame step 1 secured, with the roles step 2 recorded -- so the scan
# finally knows which numeric columns are identifiers and stops reporting
# findings about row order.


def _scan_of(step, artifact_dir):
    import json
    import os
    assert step.output_ref and step.output_ref.startswith("file://"), step.error
    path = os.path.join(str(artifact_dir), step.output_ref[len("file://"):])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def _run_through_scan(db_session, org, user, ds_id):
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    for _ in range(3):
        await automation_runner.tick(db_session)
    return run, await _steps_of(db_session, run.id)


@pytest.fixture
def scannable_csv(tmp_path):
    """Enough rows for insights to say anything, with an identifier in them.

    `student_id` is numeric and unique per row. Before step 2 it was a measure
    to every analysis; the scan is where that became visible as findings about
    a column that means nothing.
    """
    import pandas as pd
    n = 120
    p = tmp_path / "enrolments.csv"
    pd.DataFrame({
        "student_id": range(1000, 1000 + n),
        "faculty": ["eng", "law", "med", "arts"] * (n // 4),
        "score": [70.0, 65.0, 88.0, 59.0, 91.0, 55.0] * (n // 6),
        "fee": [1000.0, 1200.0, 1500.0] * (n // 3),
    }).to_csv(p, index=False)
    return p


class TestScanConsumesWhatTheChainAlreadyEarned:
    async def test_it_writes_a_real_scan_artifact(
            self, db_session, scannable_csv, artifact_dir):
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "scan@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_scan(db_session, org, user, ds.id)
        assert steps[2].name == "scan"
        assert steps[2].status == "ok", steps[2].error
        scan = _scan_of(steps[2], artifact_dir)
        assert "findings" in scan

    async def test_it_never_reads_the_dataset_file(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        """Step 1 filtered the frame by the creator's RLS and dropped their
        denied columns before writing it. A second read here would be a second
        path to the same data, and the second path is the one that gets its
        ordering wrong."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "noread@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await automation_runner.tick(db_session)      # profile reads the file
        await automation_runner.tick(db_session)      # describe

        def _boom(*a, **k):
            raise AssertionError("scan re-read the dataset file")
        monkeypatch.setattr("app.services.ingest.load_file", _boom)

        assert await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[2].status == "ok", steps[2].error

    async def test_it_refuses_when_the_frame_is_gone(
            self, db_session, scannable_csv, artifact_dir):
        import os
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "noframe@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await automation_runner.tick(db_session)
        await automation_runner.tick(db_session)

        for p in artifact_dir.rglob("frame.parquet"):
            os.remove(p)

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[2].status == "failed"
        assert not steps[2].output_ref

    async def test_a_non_dataset_subject_is_refused(self, db_session):
        org, admin = await _seed(db_session)
        ctx = automation_runner.StepContext(
            run_id=1, org_id=org.id, user_id=admin.id, user_email=admin.email,
            trigger="manual", subject_type="report", subject_id=1,
            step_name="scan")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._scan_step(ctx, db_session)


    async def test_access_revoked_between_steps_stops_the_scan(
            self, db_session, scannable_csv, artifact_dir):
        """The module docstring names this case: a user deleted between step 2
        and step 6. Revocation is the same shape and likelier.

        Step 1 refuses an unreadable dataset, so without this the re-check in
        step 3 is unreachable -- a mutation deleting it survived the whole
        suite. What it defends is the window BETWEEN steps: a run holds a
        frame of this person's rows on disk, and if their access goes away
        mid-chain the remaining steps must stop using it.
        """
        org, admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "revoked@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await automation_runner.tick(db_session)      # profile
        await automation_runner.tick(db_session)      # describe

        # Hand the dataset to someone else. The member no longer owns it and
        # has no share, so can_read_dataset stops answering yes.
        ds.created_by = admin.id
        await db_session.commit()

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[2].status == "failed"
        assert not steps[2].output_ref


class TestScanExcludesIdentifiers:
    """The VALUE test. Step 2's structural pins could see that the role lookup
    happened and never that its answer was acted on -- a mutation run deleted
    the exclusion with the lookup left in place and every pin still passed.
    These assert on the OUTPUT.
    """

    async def test_no_finding_names_the_identifier(
            self, db_session, scannable_csv, artifact_dir):
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "noids@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_scan(db_session, org, user, ds.id)
        assert steps[2].status == "ok", steps[2].error

        scan = _scan_of(steps[2], artifact_dir)
        named = " ".join(str(f.get("columns")) for f in scan.get("findings") or [])
        assert "student_id" not in named, (
            f"the scan reported a finding about an identifier: {named}")

    async def test_the_real_measures_are_still_scanned(
            self, db_session, scannable_csv, artifact_dir):
        """Excluding identifiers must not empty the scan -- a step that found
        nothing would satisfy the test above for the wrong reason."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "measures@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_scan(db_session, org, user, ds.id)
        scan = _scan_of(steps[2], artifact_dir)
        assert scan.get("scanned_columns"), "the scan recorded nothing it looked at"
        assert "student_id" not in scan["scanned_columns"]
        assert {"score", "fee"} & set(scan["scanned_columns"]), (
            "the real measures were dropped along with the identifier")

    async def test_the_identifier_is_recorded_as_excluded_not_forgotten(
            self, db_session, scannable_csv, artifact_dir):
        """A column that silently vanishes reads as 'never seen'. Saying which
        columns were set aside, and why, is the difference between a scan a
        person can trust and one they have to re-derive."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "excluded@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_scan(db_session, org, user, ds.id)
        scan = _scan_of(steps[2], artifact_dir)
        assert "student_id" in (scan.get("excluded_columns") or {})

    async def test_an_authored_measure_is_scanned_even_if_it_looks_like_an_id(
            self, db_session, scannable_csv, artifact_dir):
        """The provenance ladder reaching all the way to the scan: a human who
        said `student_id` is a measure gets it scanned as one."""
        from sqlalchemy.orm.attributes import flag_modified
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "authored@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)
        ds.column_meta = {"student_id": {"role": "measure",
                                         "role_source": "confirmed"}}
        flag_modified(ds, "column_meta")
        await db_session.commit()

        _run, steps = await _run_through_scan(db_session, org, user, ds.id)
        scan = _scan_of(steps[2], artifact_dir)
        assert "student_id" in (scan.get("scanned_columns") or [])



# ── step 4: propose, for real ────────────────────────────────────────────────
#
# The first step in the chain where customer data leaves it. Two things are
# therefore pinned harder than anywhere else: WHICH path produced a proposal,
# and WHAT reached the model.
#
# The branch is not a preference, it is a contract step 5 depends on: a model
# proposal and a statistical one are judged by different standards, so
# `output_ref` has to say which one it is holding.


def _proposal_of(step, artifact_dir):
    import json
    import os
    assert step.output_ref and step.output_ref.startswith("file://"), step.error
    path = os.path.join(str(artifact_dir), step.output_ref[len("file://"):])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def _run_through_propose(db_session, org, user, ds_id):
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    for _ in range(4):
        await automation_runner.tick(db_session)
    return run, await _steps_of(db_session, run.id)


@pytest.fixture
def pii_csv(tmp_path):
    """A dataset whose columns are obvious PII, plus one that is not.

    `email` and `phone` classify as personal by majority, which is the case the
    profile already suppresses samples for. The test asserts the suppression
    holds all the way to the model payload rather than trusting it.
    """
    import pandas as pd
    p = tmp_path / "contacts.csv"
    pd.DataFrame({
        # Wholly personal: classifies by majority, so build_profile already
        # withholds its samples. Kept so the test covers that path too.
        "email": [f"person{i}@example.com" for i in range(120)],
        # THE case step 4 masking exists for, and the one an earlier version of
        # this fixture missed: mostly city names, so the column is NOT personal
        # by majority and its samples ARE kept -- with a bare address among
        # them. A mutation that skipped masking entirely survived the whole
        # suite because no fixture produced a profile that carried PII.
        "contact_point": ["Cairo"] * 50 + ["Giza"] * 40 + ["ops@example.com"] * 30,
        "spend": [100.0, 250.0, 75.0, 320.0] * 30,
    }).to_csv(p, index=False)
    return p


class TestProposeBranchesOnTheModelBeingAvailable:
    async def test_with_the_model_off_it_takes_the_deterministic_path(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", False)

        called = []

        async def _never(*a, **k):
            called.append(1)
            return [], "should not have been asked"
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _never)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "nollm@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_propose(db_session, org, user, ds.id)
        assert steps[3].status == "ok", steps[3].error
        out = _proposal_of(steps[3], artifact_dir)
        assert out["path"] == "insights"
        assert out["model_attempted"] is False
        assert not called, "the model was asked while llm_enabled was False"

    async def test_with_the_model_on_and_answering_it_takes_the_model_path(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", True)

        async def _ok(profile, goal, count=3, client=None, probe=None):
            return ([{"title": "Enrolment overview", "widgets": []}], "")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _ok)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "llmok@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_propose(db_session, org, user, ds.id)
        assert steps[3].status == "ok", steps[3].error
        out = _proposal_of(steps[3], artifact_dir)
        assert out["path"] == "model"
        assert out["model_attempted"] is True
        assert out["proposals"]


class TestAFailedModelFallsBackAndSaysSo:
    """A silently degraded proposal is the exact failure this chain exists to
    prevent. Every one of these asserts BOTH halves: the run continued, and the
    artifact records that the model was tried and why it did not answer.
    """

    async def test_an_exception_falls_back_rather_than_failing_the_run(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", True)

        async def _explode(*a, **k):
            raise ConnectionError("the endpoint is not there")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _explode)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "boom@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_propose(db_session, org, user, ds.id)
        assert steps[3].status == "ok", steps[3].error
        out = _proposal_of(steps[3], artifact_dir)
        assert out["path"] == "insights"
        assert out["model_attempted"] is True
        assert "not there" in (out.get("model_error") or "")

    async def test_an_empty_proposal_falls_back_with_the_models_own_reason(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", True)

        async def _empty(*a, **k):
            return ([], "the model did not answer")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _empty)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "empty@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_propose(db_session, org, user, ds.id)
        assert steps[3].status == "ok", steps[3].error
        out = _proposal_of(steps[3], artifact_dir)
        assert out["path"] == "insights"
        assert out["model_attempted"] is True
        assert "did not answer" in (out.get("model_error") or "")

    async def test_the_fallback_is_never_silent(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        """The property, stated once on its own: a run that fell back must be
        distinguishable afterwards from one that never tried. Without this a
        degraded proposal and a deterministic one are the same artifact."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", True)

        async def _explode(*a, **k):
            raise TimeoutError("timed out")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _explode)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "silent@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)

        _run, steps = await _run_through_propose(db_session, org, user, ds.id)
        out = _proposal_of(steps[3], artifact_dir)
        assert out["model_attempted"] is True and out.get("model_error"), (
            "the run fell back to the deterministic path leaving no trace that "
            "a model was ever tried")


class TestWhatReachesTheModel:
    """The first time customer data leaves the chain.

    Step 1 dropped the creator's denied columns, but SAMPLES are a separate
    exposure: a column nobody denied can still hold addresses and phone
    numbers, and the profile carries example values so the model can tell what
    a column means.
    """

    async def test_no_pii_value_appears_in_the_model_payload(
            self, db_session, pii_csv, artifact_dir, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", True)

        seen: dict = {}

        async def _capture(profile, goal, count=3, client=None, probe=None):
            seen["profile"] = profile
            return ([{"title": "Contacts", "widgets": []}], "")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _capture)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "pii@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, pii_csv)

        _run, steps = await _run_through_propose(db_session, org, user, ds.id)
        assert steps[3].status == "ok", steps[3].error
        assert seen.get("profile"), "the model was never handed a profile"

        import json
        payload = json.dumps(seen["profile"])
        # The VALUE test. Not "masking was called" -- the actual addresses and
        # numbers from the file must not be in what we sent.
        assert "person0@example.com" not in payload
        assert "person41@example.com" not in payload
        # The one that matters: a bare address inside a column that is NOT
        # personal by majority, which build_profile therefore samples.
        assert "ops@example.com" not in payload, (
            "an address reached the model because the column as a whole did "
            "not classify as personal")

    async def test_the_useful_values_still_reach_it(
            self, db_session, pii_csv, artifact_dir, monkeypatch):
        """Masking that removed everything would pass the test above and make
        the model useless. The non-personal columns must survive intact."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", True)

        seen: dict = {}

        async def _capture(profile, goal, count=3, client=None, probe=None):
            seen["profile"] = profile
            return ([{"title": "Contacts", "widgets": []}], "")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _capture)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "useful@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, pii_csv)

        await _run_through_propose(db_session, org, user, ds.id)

        import json
        payload = json.dumps(seen["profile"])
        assert "Cairo" in payload, "a harmless sample was masked away"
        assert "Giza" in payload
        assert "spend" in payload


class TestProposeReadsOnlyWhatTheChainEarned:
    async def test_it_never_reads_the_dataset_file(
            self, db_session, scannable_csv, artifact_dir, monkeypatch):
        """Step 3 has this test; step 4 did not, and a mutation swapping the
        secured frame for a fresh load_file survived because the two happen to
        hold the same rows when no rule narrows them. They do not when one
        does -- and step 4 is the step that hands data to a model."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "llm_enabled", False)

        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "noread4@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(3):
            await automation_runner.tick(db_session)      # profile, describe, scan

        def _boom(*a, **k):
            raise AssertionError("propose re-read the dataset file")
        monkeypatch.setattr("app.services.ingest.load_file", _boom)

        assert await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[3].status == "ok", steps[3].error


class TestProposeContract:
    async def test_it_refuses_when_step_three_left_nothing(
            self, db_session, scannable_csv, artifact_dir):
        import os
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "noscan@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, scannable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(3):
            await automation_runner.tick(db_session)
        for p in artifact_dir.rglob("scan.json"):
            os.remove(p)

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[3].status == "failed"
        assert not steps[3].output_ref

    async def test_a_non_dataset_subject_is_refused(self, db_session):
        org, admin = await _seed(db_session)
        ctx = automation_runner.StepContext(
            run_id=1, org_id=org.id, user_id=admin.id, user_email=admin.email,
            trigger="manual", subject_type="report", subject_id=1,
            step_name="propose")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._propose_step(ctx, db_session)



# ── needs_review: the fourth state, and its exit ─────────────────────────────
#
# `failed` retries forever on a backoff ladder, because the things that fail a
# step are transient: a source down for an hour, a restart mid-write. A quality
# judgement is not transient. Retrying "these widgets are not good enough"
# reproduces the same judgement at 5, 15 and 45 minutes and then hourly.
#
# So `needs_review` is neither active nor terminal:
#   - out of ACTIVE_RUN_STATUSES, so `tick` skips it and nothing retries;
#   - out of TERMINAL_RUN_STATUSES, because work was done and is resumable.
#
# A state with no exit is swallowing with a polite name, so the exit is built
# here with the state rather than left for the UI that will eventually call it.


class TestNeedsReviewIsNeitherActiveNorTerminal:
    def test_it_is_absent_from_both_sets(self):
        assert automation_runner.NEEDS_REVIEW not in automation_runner.ACTIVE_RUN_STATUSES
        assert automation_runner.NEEDS_REVIEW not in automation_runner.TERMINAL_RUN_STATUSES

    async def test_a_run_awaiting_review_is_not_ticked(
            self, db_session, monkeypatch):
        """The property, as behaviour rather than as set membership: a tick
        must not touch it, now or in an hour."""
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        await automation_runner.tick(db_session)          # step 1 runs
        calls.clear()

        run.status = automation_runner.NEEDS_REVIEW
        await db_session.commit()

        assert await automation_runner.tick(db_session) is False
        from datetime import datetime, timedelta
        later = datetime.utcnow() + timedelta(days=7)
        assert await automation_runner.tick(db_session, now=later) is False
        assert calls == [], "a run awaiting review was retried"


class TestReviewHasAnExit:
    async def test_approving_resumes_where_it_stopped_not_at_the_start(
            self, db_session, monkeypatch):
        """THE assertion. Resuming at step 1 would re-profile and re-scan, and
        would overwrite the very artifacts the reviewer just approved.

        Asserted on which steps RAN after approval, not on the status -- the
        status being right while the chain restarts is the failure this is
        written against.
        """
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        for _ in range(5):
            await automation_runner.tick(db_session)
        assert calls == ["profile", "describe", "scan", "propose", "review"]

        run.status = automation_runner.NEEDS_REVIEW
        await db_session.commit()
        calls.clear()

        await automation_runner.approve_review(db_session, run)
        await automation_runner.tick(db_session)

        assert calls == ["compose"], (
            f"approval restarted the chain instead of resuming it: {calls}")

    async def test_approving_keeps_every_earlier_artifact(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        for _ in range(5):
            await automation_runner.tick(db_session)
        before = [s.output_ref for s in await _steps_of(db_session, run.id)][:5]

        run.status = automation_runner.NEEDS_REVIEW
        await db_session.commit()
        await automation_runner.approve_review(db_session, run)
        await automation_runner.tick(db_session)

        after = [s.output_ref for s in await _steps_of(db_session, run.id)][:5]
        assert after == before, "approval discarded work the reviewer approved"

    async def test_rejecting_is_terminal_and_stays_that_way(
            self, db_session, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps(calls))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        await automation_runner.tick(db_session)
        run.status = automation_runner.NEEDS_REVIEW
        await db_session.commit()
        calls.clear()

        await automation_runner.reject_review(db_session, run, reason="not useful")

        assert run.status in automation_runner.TERMINAL_RUN_STATUSES
        assert await automation_runner.tick(db_session) is False
        assert calls == []

    async def test_rejecting_records_why(self, db_session, monkeypatch):
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps([]))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        run.status = automation_runner.NEEDS_REVIEW
        await db_session.commit()

        await automation_runner.reject_review(db_session, run, reason="all twelve were noise")
        assert "noise" in (run.error or "")

    async def test_a_run_not_awaiting_review_cannot_be_approved(
            self, db_session, monkeypatch):
        """Approval is a transition out of ONE state, not a way to force any
        run forward. Without this, approving a `failed` run would skip the step
        that failed and leave a hole in the chain."""
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps([]))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        run.status = "failed"
        await db_session.commit()
        with pytest.raises(ValueError):
            await automation_runner.approve_review(db_session, run)


# ── step 5: review, for real ─────────────────────────────────────────────────

@pytest.fixture
def reviewable_csv(tmp_path):
    """Two columns and no geography, so a map proposal is provably unusable."""
    import pandas as pd
    p = tmp_path / "courses.csv"
    pd.DataFrame({
        "faculty": ["eng", "law", "med", "arts"] * 30,
        "score": [70.0, 65.0, 88.0, 59.0] * 30,
    }).to_csv(p, index=False)
    return p


#: `avg`, not `sum`. This fixture was `sum` of `score` for three steps' worth
#: of tests -- the exact meaningless KPI defect 3's rule now rejects. The rule
#: was right and the fixture was proposing the bad widget the whole time; it
#: only surfaced when the record tests asserted the run reached `done`.
GOOD_WIDGET = {"widget_type": "bar", "title": "Score by faculty",
               "config": {"dimension": "faculty", "measure": "score",
                          "aggregation": "avg"}}
#: Each of these is rejected for a DIFFERENT reason, verified against
#: validate_widget directly before these tests were written -- the D3 lesson:
#: a filter has to be shown an input that actually trips it.
INVENTED_COLUMN = {"widget_type": "bar", "title": "By nothing",
                   "config": {"dimension": "does_not_exist", "measure": "score",
                              "aggregation": "sum"}}
KPI_NO_MEASURE = {"widget_type": "kpi", "title": "A number",
                  "config": {"aggregation": "median"}}
MAP_NO_GEO = {"widget_type": "map_bubble", "title": "Map",
              "config": {"roles": {"lat": "a", "lon": "b"}}}


def _with_proposal(monkeypatch, widgets, *, path="model"):
    """Force step 4 down a chosen path with a chosen set of widgets."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_enabled", path == "model")
    if path == "model":
        async def _model(profile, goal, count=3, client=None, probe=None):
            return ([{"title": "Proposed", "widgets": list(widgets)}], "")
        monkeypatch.setattr(
            "app.services.suggest_dataset_dashboard.suggest_for_dataset", _model)
    else:
        async def _det(df, profile, probe=None, description=None):
            return ([{"title": "Proposed", "widgets": list(widgets)}], "")
        monkeypatch.setattr(
            "app.services.suggest_from_insights.suggest_from_insights", _det)


async def _run_through_review(db_session, org, user, ds_id):
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    for _ in range(5):
        await automation_runner.tick(db_session)
    await db_session.refresh(run)
    return run, await _steps_of(db_session, run.id)


class TestReviewRecordsBothSides:
    async def test_it_records_what_passed_and_what_was_rejected(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Same contract as step 3's scanned/excluded: a widget that silently
        disappears reads as one that was never proposed."""
        _with_proposal(monkeypatch, [GOOD_WIDGET, INVENTED_COLUMN])
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        _run, steps = await _run_through_review(db_session, org, user, ds.id)
        assert steps[4].status == "ok", steps[4].error
        out = _proposal_of(steps[4], artifact_dir)

        assert [w["title"] for w in out["accepted"]] == ["Score by faculty"]
        assert [r["title"] for r in out["rejected"]] == ["By nothing"]

    async def test_every_rejection_carries_its_own_reason(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Three widgets rejected for three different reasons. One shared
        message would pass a weaker assertion and tell a reviewer nothing."""
        _with_proposal(monkeypatch,
                       [GOOD_WIDGET, INVENTED_COLUMN, KPI_NO_MEASURE, MAP_NO_GEO])
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        _run, steps = await _run_through_review(db_session, org, user, ds.id)
        out = _proposal_of(steps[4], artifact_dir)
        reasons = {r["title"]: r["reason"] for r in out["rejected"]}

        assert "does_not_exist" in reasons["By nothing"]
        assert "measure" in reasons["A number"]
        assert "not usable" in reasons["Map"]
        assert len(set(reasons.values())) == 3, "the reasons are not distinct"


class TestTheGateJudgesTheTwoPathsDifferently:
    async def test_a_model_proposal_that_mostly_fails_goes_to_review(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Four good widgets beat twelve arbitrary ones -- and one good widget
        out of four is a model that did not understand the dataset. A person
        should look before that becomes a dashboard."""
        _with_proposal(monkeypatch,
                       [GOOD_WIDGET, INVENTED_COLUMN, KPI_NO_MEASURE, MAP_NO_GEO],
                       path="model")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev3@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, steps = await _run_through_review(db_session, org, user, ds.id)
        assert run.status == automation_runner.NEEDS_REVIEW
        assert steps[4].output_ref, "the review still has to say what it found"

    async def test_a_clean_model_proposal_passes_straight_through(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        _with_proposal(monkeypatch, [GOOD_WIDGET, GOOD_WIDGET], path="model")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev4@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, steps = await _run_through_review(db_session, org, user, ds.id)
        assert run.status != automation_runner.NEEDS_REVIEW
        assert steps[4].status == "ok", steps[4].error

    async def test_a_deterministic_proposal_is_held_to_a_lower_bar(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """The same one-in-four ratio that stops a model proposal does not stop
        a statistical one: it did not guess, it derived. Only an EMPTY result
        means there is nothing to show."""
        _with_proposal(monkeypatch,
                       [GOOD_WIDGET, INVENTED_COLUMN, KPI_NO_MEASURE, MAP_NO_GEO],
                       path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev5@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, steps = await _run_through_review(db_session, org, user, ds.id)
        assert run.status != automation_runner.NEEDS_REVIEW, (
            "a deterministic proposal was judged by the model's standard")
        out = _proposal_of(steps[4], artifact_dir)
        assert len(out["rejected"]) == 3, "the bad widgets were kept anyway"

    async def test_nothing_surviving_goes_to_review_on_either_path(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        _with_proposal(monkeypatch, [INVENTED_COLUMN, KPI_NO_MEASURE],
                       path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev6@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, _steps = await _run_through_review(db_session, org, user, ds.id)
        assert run.status == automation_runner.NEEDS_REVIEW


class TestReviewContract:
    async def test_it_refuses_when_step_four_left_nothing(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        import os
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rev7@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(4):
            await automation_runner.tick(db_session)
        for p in artifact_dir.rglob("propose.json"):
            os.remove(p)

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[4].status == "failed"
        assert not steps[4].output_ref

    async def test_a_non_dataset_subject_is_refused(self, db_session):
        org, admin = await _seed(db_session)
        ctx = automation_runner.StepContext(
            run_id=1, org_id=org.id, user_id=admin.id, user_email=admin.email,
            trigger="manual", subject_type="report", subject_id=1,
            step_name="review")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._review_step(ctx, db_session)



# ── step 6: compose, for real ────────────────────────────────────────────────
#
# The relationship-heavy step. `Report.pages` and `ReportPage.widgets` are both
# lazy, and a lazy relationship access outside a request raises MissingGreenlet
# rather than merely being slow. Verified before this file was written:
#
#     expunge_all(); list(report.pages)  ->  MissingGreenlet
#
# so the cold-session test below is a real guard, not a ritual. It is written
# first on purpose: this is the third time in this module, and the previous two
# were each found by a failure rather than by a test.


def _report_artifact(step, artifact_dir):
    import json
    import os
    assert step.output_ref and step.output_ref.startswith("file://"), step.error
    path = os.path.join(str(artifact_dir), step.output_ref[len("file://"):])
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def _run_through_compose(db_session, org, user, ds_id):
    """Tick until THIS run has composed, not a fixed number of times.

    A fixed count silently under-runs the second run in a test: ticks are
    shared, ordered by age, so an older run still holding step 7 consumes one
    of them. The first version of this helper did exactly that and the
    two-runs-same-dataset test failed on a None report id rather than on the
    thing it was written to check.
    """
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    for _ in range(len(automation_runner.STEPS) * 3):
        steps = await _steps_of(db_session, run.id)
        if steps[5].output_ref or steps[5].status == "failed":
            break
        if not await automation_runner.tick(db_session):
            break
    await db_session.refresh(run)
    return run, await _steps_of(db_session, run.id)


class TestComposeSurvivesAColdSession:
    """Written before the implementation, because the two MissingGreenlets
    already in this module were both found by a failure instead."""

    async def test_it_composes_with_nothing_pre_warmed(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "cold6@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(5):
            await automation_runner.tick(db_session)
        await db_session.commit()

        # The production shape: the tick that composes did not create any of
        # the rows it is about to traverse.
        db_session.expunge_all()

        assert await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[5].status == "ok", steps[5].error


class TestComposeUsesTheAcceptedSetOnly:
    async def test_a_rejected_widget_never_reaches_the_report(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """The whole point of step 5. Composing the raw proposal would put the
        widgets the gate rejected onto the page anyway, and the review would be
        a log line rather than a gate."""
        from app.models.models import ReportPage, ReportWidget
        from sqlalchemy import select

        _with_proposal(monkeypatch, [GOOD_WIDGET, INVENTED_COLUMN],
                       path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "acc1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, steps = await _run_through_compose(db_session, org, user, ds.id)
        assert steps[5].status == "ok", steps[5].error
        assert run.result_report_id

        titles = (await db_session.execute(
            select(ReportWidget.title)
            .join(ReportPage, ReportWidget.page_id == ReportPage.id)
            .where(ReportPage.report_id == run.result_report_id)
        )).scalars().all()
        assert "By nothing" not in titles, (
            f"a rejected widget was composed onto the page: {titles}")

    async def test_the_accepted_widget_does_reach_it(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """The other half: a filter that dropped everything would satisfy the
        test above and produce an empty report."""
        from app.models.models import ReportPage, ReportWidget
        from sqlalchemy import select

        _with_proposal(monkeypatch, [GOOD_WIDGET, INVENTED_COLUMN],
                       path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "acc2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, _steps = await _run_through_compose(db_session, org, user, ds.id)
        count = (await db_session.execute(
            select(ReportWidget)
            .join(ReportPage, ReportWidget.page_id == ReportPage.id)
            .where(ReportPage.report_id == run.result_report_id)
        )).scalars().all()
        assert count, "the composed report has no widgets at all"


class TestTheReportIsMarkedAsAutomationProduced:
    async def test_the_composed_report_carries_the_marker(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Recents cannot currently tell an automated report from a draft
        somebody started and walked away from. Step 7 and Home both need to."""
        from app.models.models import Report

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "mark1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, _steps = await _run_through_compose(db_session, org, user, ds.id)
        report = await db_session.get(Report, run.result_report_id)
        assert report.origin == automation_runner.REPORT_ORIGIN_AUTOMATION

    async def test_a_report_a_person_made_is_not_marked(self, db_session):
        """The control. A marker every report carries distinguishes nothing."""
        from app.models.models import Organization, Report
        org = Organization(name="Hand made")
        db_session.add(org)
        await db_session.flush()
        r = Report(name="My dashboard", org_id=org.id)
        db_session.add(r)
        await db_session.commit()
        assert r.origin != automation_runner.REPORT_ORIGIN_AUTOMATION


class TestTheNameIsDerivedNotTemplated:
    async def test_it_carries_the_dataset_and_the_leading_finding(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        from app.models.models import Report

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "name1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, _steps = await _run_through_compose(db_session, org, user, ds.id)
        report = await db_session.get(Report, run.result_report_id)
        assert ds.name in report.name
        assert report.name != "Auto-generated insights", (
            "the composer's fixed template name was used")

    async def test_two_runs_over_the_same_dataset_get_different_names(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Same dataset, same findings, same everything -- and still two rows a
        person can tell apart in Recents. Without this, an install that runs
        nightly accumulates a column of identical names."""
        from app.models.models import Report

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "name2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        first, _ = await _run_through_compose(db_session, org, user, ds.id)
        second, _ = await _run_through_compose(db_session, org, user, ds.id)

        a = await db_session.get(Report, first.result_report_id)
        b = await db_session.get(Report, second.result_report_id)
        assert a.name != b.name, f"both runs produced {a.name!r}"

    async def test_a_dataset_whose_name_says_nothing_still_disambiguates(
            self, db_session, tmp_path, artifact_dir, monkeypatch):
        """THE collision case. One dataset in this install is literally named
        "2"; the derivation has to hold up when the source contributes nothing
        worth reading."""
        import pandas as pd
        from app.models.models import Report

        csv = tmp_path / "two.csv"
        pd.DataFrame({"faculty": ["eng", "law"] * 60,
                      "score": [70.0, 65.0] * 60}).to_csv(csv, index=False)

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "name3@example.invalid")
        from app.models.models import Dataset
        ds = Dataset(name="2", filename=str(csv), org_id=org.id, mode="import",
                     created_by=user.id)
        db_session.add(ds)
        await db_session.flush()
        await db_session.commit()

        first, _ = await _run_through_compose(db_session, org, user, ds.id)
        second, _ = await _run_through_compose(db_session, org, user, ds.id)

        a = await db_session.get(Report, first.result_report_id)
        b = await db_session.get(Report, second.result_report_id)
        assert a.name != b.name
        assert a.name.strip() not in ("2", "", "2 —"), (
            f"the name collapsed to the dataset name alone: {a.name!r}")


class TestComposeContract:
    async def test_it_refuses_when_step_five_left_nothing(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        import os
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "comp1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(5):
            await automation_runner.tick(db_session)
        for p in artifact_dir.rglob("review.json"):
            os.remove(p)

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[5].status == "failed"
        assert not steps[5].output_ref

    async def test_an_empty_accepted_set_is_refused_when_reached_directly(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Unreachable through the chain, and pinned anyway.

        Step 5 holds a run at needs_review when nothing survives, so compose is
        never ticked with an empty accepted set -- a mutation deleting this
        refusal survived the whole suite for exactly that reason. It is defence
        against a FUTURE caller (a retry path, an approval that resumes past a
        review), so it is tested the only way it can be: by calling the step.
        """
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "empty6@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for _ in range(5):
            await automation_runner.tick(db_session)

        # Rewrite step 5's artifact so it accepts nothing, then compose it.
        import json, os
        review = next(artifact_dir.rglob("review.json"))
        payload = json.loads(review.read_text(encoding="utf-8"))
        payload["accepted"] = []
        review.write_text(json.dumps(payload), encoding="utf-8")

        ctx = automation_runner.StepContext(
            run_id=run.id, org_id=org.id, user_id=user.id,
            user_email=user.email, trigger="manual",
            subject_type="dataset", subject_id=ds.id, step_name="compose")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._compose_step(ctx, db_session)

    async def test_a_non_dataset_subject_is_refused(self, db_session):
        org, admin = await _seed(db_session)
        ctx = automation_runner.StepContext(
            run_id=1, org_id=org.id, user_id=admin.id, user_email=admin.email,
            trigger="manual", subject_type="report", subject_id=1,
            step_name="compose")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._compose_step(ctx, db_session)



# ── defects 1 and 2: what a report may be named, and after what ──────────────
#
# Found by running the chain on real data, not by the suite. The composed
# report was called:
#
#   "Enrolments 2025 — escalated to registrar, emailed h.farouk@example.edu
#    about the transfer trails the other notes values"
#
# `insights.py:252,265` put a categorical column's actual VALUE into a finding
# title, `_compose_name` took that title verbatim, and the address landed in
# `reports.name` -- the database, Recents, and every list a report appears in.
#
# Two boundaries were missing, not one:
#   a) scrubbing applied only on the model path (`masked_profile_for_model`);
#      the deterministic path had none at all;
#   b) the name was built from a SENTENCE. Even perfectly scrubbed, a name made
#      of generated prose is one new finding phrasing away from leaking again.
#      So it is now built from schema: dataset, columns, finding kind.
#
# And the collision test certified a collision: two runs produced names
# differing by one trailing space, because the `(run N)` suffix was appended
# and THEN truncated off. `a.name != b.name` was satisfied by that space.


@pytest.fixture
def leaky_csv(tmp_path):
    """The real shape that leaked: a free-text column whose values become a
    finding title, with an address embedded mid-sentence in one row.

    Verified against pii._PATTERNS before this test was written -- the
    unanchored email pattern matches `h.farouk@example.edu` inside this exact
    sentence, so the guard below is reachable.
    """
    import pandas as pd
    n = 240
    notes = ["no issues raised", "requested a timetable change",
             "attendance follow-up", "scholarship enquiry"] * (n // 4)
    notes[137] = ("escalated to registrar, emailed h.farouk@example.edu "
                  "about the transfer")
    p = tmp_path / "enrolments.csv"
    pd.DataFrame({
        "student_id": range(100000, 100000 + n),
        "faculty": ["Engineering", "Law", "Medicine", "Arts"] * (n // 4),
        # Named `score` so GOOD_WIDGET validates against it -- the gate is not
        # what this fixture is testing, and a rejected widget would halt the
        # run at review before compose ever names anything.
        "score": [72.0, 68.0, 84.0, 61.0] * (n // 4),
        "notes": notes,
    }).to_csv(p, index=False)
    return p


class TestNoRowValueReachesAPersistedName:
    async def test_an_embedded_address_never_reaches_the_report_name(
            self, db_session, leaky_csv, artifact_dir, monkeypatch):
        from app.models.models import Report

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "leak1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, leaky_csv)

        run, _steps = await _run_through_compose(db_session, org, user, ds.id)
        report = await db_session.get(Report, run.result_report_id)
        assert "h.farouk@example.edu" not in report.name
        assert "@" not in report.name, (
            f"an address-shaped value reached the name: {report.name!r}")

    async def test_it_never_reaches_the_summary_widget_either(
            self, db_session, leaky_csv, artifact_dir, monkeypatch):
        from sqlalchemy import select
        from app.models.models import ReportPage, ReportWidget

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "leak2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, leaky_csv)

        run, _steps = await _run_through_compose(db_session, org, user, ds.id)
        blobs = (await db_session.execute(
            select(ReportWidget.config)
            .join(ReportPage, ReportWidget.page_id == ReportPage.id)
            .where(ReportPage.report_id == run.result_report_id)
        )).scalars().all()
        text = " ".join(str(b) for b in blobs)
        assert "h.farouk@example.edu" not in text

    async def test_it_never_reaches_the_description(
            self, db_session, leaky_csv, artifact_dir, monkeypatch):
        from app.models.models import Report

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "leak3@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, leaky_csv)

        run, _steps = await _run_through_compose(db_session, org, user, ds.id)
        report = await db_session.get(Report, run.result_report_id)
        assert "h.farouk@example.edu" not in (report.description or "")


class TestTheNameIsStructuralNotASentence:
    def test_it_is_built_from_schema_not_prose(self):
        """Even a scrubbed sentence is the wrong SOURCE. Columns and the
        dataset name are schema -- they cannot contain a row value."""
        finding = {"kind": "standout", "columns": ["faculty", "final_score"],
                   "title": "Arts trails the other faculty values on final_score"}
        name = automation_runner._compose_name(
            "Enrolments 2025", [finding], run_id=1, taken=set())
        assert "Enrolments 2025" in name
        assert "final_score" in name or "faculty" in name
        assert "trails the other" not in name, (
            "the finding's sentence was copied into the name")

    def test_a_finding_whose_title_is_pure_row_values_contributes_none_of_them(self):
        finding = {"kind": "standout", "columns": ["notes", "final_score"],
                   "title": "emailed h.farouk@example.edu trails the other notes values"}
        name = automation_runner._compose_name(
            "Enrolments 2025", [finding], run_id=1, taken=set())
        assert "h.farouk" not in name and "@" not in name

    def test_with_no_findings_it_still_names_the_dataset(self):
        name = automation_runner._compose_name("Enrolments 2025", [], 1, set())
        assert "Enrolments 2025" in name


class TestTheCollisionSuffixSurvivesTruncation:
    def test_a_long_base_still_disambiguates(self):
        """THE case that shipped broken. The suffix was appended and then
        truncated off, so two runs differed by one trailing space."""
        long_name = "Enrolment and attainment review for the twenty twenty five intake cohort across every faculty"
        finding = {"kind": "standout", "columns": ["faculty", "final_score"],
                   "title": "x"}
        first = automation_runner._compose_name(long_name, [finding], 1, set())
        second = automation_runner._compose_name(long_name, [finding], 2, {first})
        assert first != second
        assert second.strip() != first.strip(), (
            "the two names differ only by whitespace, which no reader can see")
        assert "2" in second

    def test_neither_name_exceeds_the_column(self):
        long_name = "x" * 400
        finding = {"kind": "standout", "columns": ["a", "b"], "title": "t"}
        first = automation_runner._compose_name(long_name, [finding], 1, set())
        second = automation_runner._compose_name(long_name, [finding], 2, {first})
        assert len(first) <= automation_runner.MAX_REPORT_NAME
        assert len(second) <= automation_runner.MAX_REPORT_NAME

    def test_distinctness_is_visible_not_whitespace(self):
        """Written because the previous assertion was `a != b`, which one
        trailing space satisfies. This is what the test should have said."""
        base = "Dataset " + "y" * 200
        finding = {"kind": "standout", "columns": ["a"], "title": "t"}
        a = automation_runner._compose_name(base, [finding], 1, set())
        b = automation_runner._compose_name(base, [finding], 2, {a})
        assert a.strip().casefold() != b.strip().casefold()


class TestScrubbingCoversBothPaths:
    def test_the_redactor_removes_an_embedded_address(self):
        text = ("escalated to registrar, emailed h.farouk@example.edu about "
                "the transfer")
        out = automation_runner.redact_row_values(text)
        assert "h.farouk@example.edu" not in out
        assert "escalated to registrar" in out, "surrounding prose was destroyed"

    def test_it_leaves_ordinary_prose_alone(self):
        text = "Arts trails the other faculty values on final_score"
        assert automation_runner.redact_row_values(text) == text

    def test_its_patterns_stay_derived_from_pii(self):
        """One source of pattern truth. A fifth copy of the email regex is how
        the anchored and unanchored forms drift apart."""
        from app.services import pii
        derived = {n for n, _ in pii._PATTERNS if n in pii._PII_TYPES}
        assert derived & set(automation_runner.REDACTED_TYPES), (
            "the payload scrubber no longer derives from pii._PATTERNS")



# ── defect 5: the structured record ──────────────────────────────────────────
#
# `discard_run_artifacts` deletes a run's directory at `done`. The first real
# run composed a report with a meaningless lead KPI, and by the time that was
# noticed the 17 proposals it was chosen from were gone -- the gate fix could
# not be verified against the proposals that had actually failed it. Model
# output is not reproducible, so that material was gone for good.
#
# The record lives in typed columns because Home filters and orders on it, and
# because the artifacts do not survive. Every test here asserts on a COLUMN read
# back from the database after commit -- never on an in-memory attribute, which
# is how `run.error` was "tested" while never being persisted at all.


async def _reloaded(db_session, run_id):
    """The row as the database holds it, not as this session remembers it."""
    from app.models.models import AutomationRun
    db_session.expunge_all()
    return await db_session.get(AutomationRun, run_id)


async def _drive(db_session, org, user, ds_id, ticks):
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    for _ in range(ticks * 3):
        steps = await _steps_of(db_session, run.id)
        done = sum(1 for s in steps if s.output_ref)
        if done >= ticks or any(s.status == "failed" for s in steps):
            break
        if not await automation_runner.tick(db_session):
            break
    await db_session.commit()
    return run.id


class TestTheRecordSurvivesTheArtifacts:
    async def test_the_counts_and_reasons_are_columns_read_back_after_commit(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """[GOOD_WIDGET, INVENTED_COLUMN] provably yields exactly one rejection
        (verified against validate_widget in step 5). If widgets_rejected reads
        0 here, the record is not being populated from the review."""
        _with_proposal(monkeypatch, [GOOD_WIDGET, INVENTED_COLUMN], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(db_session, org, "rec1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run_id = await _drive(db_session, org, user, ds.id, ticks=7)
        run = await _reloaded(db_session, run_id)

        assert run.status == "done", run.error
        assert run.widgets_accepted == 1
        assert run.widgets_rejected == 1
        assert run.proposal_path == "insights"
        assert run.result_report_id and run.result_report_name
        reasons = run.rejection_reasons or []
        assert len(reasons) == 1
        assert reasons[0]["title"] == "By nothing"
        assert "does_not_exist" in reasons[0]["reason"]

    async def test_the_record_is_there_after_the_artifacts_are_gone(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """The whole point. Artifacts gone, columns present."""
        _with_proposal(monkeypatch, [GOOD_WIDGET, INVENTED_COLUMN], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(db_session, org, "rec2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run_id = await _drive(db_session, org, user, ds.id, ticks=7)
        left = [p for p in artifact_dir.rglob(f"run_{run_id}/*") if p.is_file()]
        assert not left, "artifacts were not discarded; this test proves nothing"

        run = await _reloaded(db_session, run_id)
        assert run.widgets_rejected == 1
        assert run.raw_proposals

    async def test_the_raw_proposals_include_what_the_gate_rejected(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Raw, not accepted-only. The rejected widget's title present in the
        stored set is the discriminator: an implementation that stored the
        accepted list would pass every other assertion in this file."""
        import json
        _with_proposal(monkeypatch, [GOOD_WIDGET, INVENTED_COLUMN], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(db_session, org, "rec3@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run_id = await _drive(db_session, org, user, ds.id, ticks=7)
        run = await _reloaded(db_session, run_id)
        blob = json.dumps(run.raw_proposals)
        assert "By nothing" in blob, "the rejected proposal was not kept"
        assert "Score by faculty" in blob

    async def test_a_held_run_records_its_reason_in_a_real_column(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """`run.error` was assigned and never persisted. Reading it back after
        expunge_all is the only assertion that can tell."""
        _with_proposal(monkeypatch,
                       [GOOD_WIDGET, INVENTED_COLUMN, KPI_NO_MEASURE, MAP_NO_GEO],
                       path="model")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(db_session, org, "rec4@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run_id = await _drive(db_session, org, user, ds.id, ticks=5)
        run = await _reloaded(db_session, run_id)
        assert run.status == automation_runner.NEEDS_REVIEW
        assert run.error, "the needs_review reason was not persisted"
        assert "survived review" in run.error
        assert run.widgets_accepted == 1 and run.widgets_rejected == 3
        assert run.proposal_path == "model"

    async def test_a_rejection_reason_is_persisted_too(self, db_session, monkeypatch):
        monkeypatch.setattr(automation_runner, "STEPS", recording_steps([]))
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        run.status = automation_runner.NEEDS_REVIEW
        await db_session.commit()
        await automation_runner.reject_review(db_session, run, reason="all noise")

        fresh = await _reloaded(db_session, run.id)
        assert fresh.status == "cancelled"
        assert "all noise" in (fresh.error or ""), "rejection reason lost on commit"


class TestTheWriterRefusesWhatIsNotAColumn:
    async def test_a_misspelt_field_raises_instead_of_vanishing(self, db_session):
        """The guard that stops the run.error bug recurring. Without it a typo
        sets a Python attribute SQLAlchemy never persists, the caller sees no
        error, and the value is gone on commit -- which is exactly how three
        assignments to a non-existent column shipped."""
        org, user = await _seed(db_session)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=7)
        with pytest.raises(ValueError):
            await automation_runner.record_run_result(
                db_session, run.id, widgets_acepted=3)


class TestTheRecordIsQueryableNotParsed:
    async def test_runs_can_be_selected_by_path_without_reading_any_text(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        from sqlalchemy import select
        from app.models.models import AutomationRun
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(db_session, org, "q1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        await _drive(db_session, org, user, ds.id, ticks=7)

        rows = (await db_session.execute(
            select(AutomationRun).where(AutomationRun.proposal_path == "insights")
        )).scalars().all()
        assert rows

# ── the creator is loaded with their role, every time ────────────────────────

class TestTheCreatorIsLoadedWithTheirRole:
    """`can_read_dataset` opens with `user.role and user.role.is_org_admin`.

    Under async SQLAlchemy an implicit relationship load is not slow, it is
    ILLEGAL -- it raises MissingGreenlet. Whether it happens depends on whether
    that Role is already in the session's identity map, which depends on what
    the caller did earlier. So the failure is intermittent, and it lands in the
    permission check: the one place in a step that must not be flaky.

    These tests clear the identity map first, which is what makes them fail
    without the eager load. Every other test in this file happens to create the
    Role moments earlier in the same session, which is exactly why this bug
    survived step 1 being written, reviewed and merged.
    """

    async def test_step_one_survives_a_cold_session(
            self, db_session, ids_csv, artifact_dir):
        org, _admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "cold1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=member.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await db_session.commit()

        # Nothing pre-warmed. This is the production shape: the scheduler tick
        # that picks a run up did not create its user.
        db_session.expunge_all()

        assert await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[0].status == "ok", steps[0].error

    async def test_step_two_survives_a_cold_session(
            self, db_session, ids_csv, artifact_dir):
        org, _admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "cold2@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=member.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await db_session.commit()
        await automation_runner.tick(db_session)

        db_session.expunge_all()

        assert await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[1].status == "ok", steps[1].error

    async def test_the_loader_asks_for_the_role_rather_than_hoping(self):
        """Structural companion: the two tests above pass the moment the Role
        is in the identity map for any incidental reason, so they cannot prove
        the eager load is what saved them. This can."""
        import inspect
        src = inspect.getsource(automation_runner._load_creator)
        assert "selectinload" in src and "User.role" in src


# ── step 2: describe, for real ───────────────────────────────────────────────
#
# Step 2 exists to do one job the rest of the product has been unable to do:
# get `classify_role`'s IDENTIFIER concept into the place analyses actually
# read. Four copies of the identifier heuristic already existed --
# infer_semantic.classify_role (canonical, name + near-uniqueness),
# widget_data._is_id_like_column (name only, used by the profile),
# columnRole.ts (frontend mirror), and influencers' cardinality check on its
# categorical branch only -- and none of them reached `Dataset.column_meta`,
# which is what `insights.effective_roles` consults. So an identifier stayed a
# "numeric" column to every analysis, and Key influencers ranked student_id as
# a top driver by slicing it into quantile ranges.
#
# These tests pin the bridge, not the heuristic: the heuristic is
# classify_role's and is tested where it lives.


async def _run_through_describe(db_session, org, user, ds_id):
    """Tick twice: profile, then describe. Returns (run, [profile, describe])."""
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    await automation_runner.tick(db_session)
    await automation_runner.tick(db_session)
    await db_session.refresh(run)
    steps = await _steps_of(db_session, run.id)
    return run, steps[:2]


@pytest.fixture
def ids_csv(tmp_path):
    """A dataset with the shape that produced the bug.

    `student_id` is numeric and near-unique -- an identifier by both halves of
    classify_role. `cohort_ref` is numeric and near-unique but NAMED nothing
    like an id, so only the uniqueness half catches it: that is the column the
    profile's name-only check misses and step 2 must not.
    `score` is a real measure and must survive.
    """
    import pandas as pd
    p = tmp_path / "students.csv"
    pd.DataFrame({
        "student_id": list(range(101, 113)),
        "cohort_ref": list(range(9001, 9013)),
        "faculty":    ["eng", "eng", "law", "law", "med", "med"] * 2,
        # Repeats on purpose: a measure whose every value is distinct IS
        # near-unique, and classify_role would be right to call it an
        # identifier. 4 distinct over 12 rows is the shape a measure has.
        "score":      [70.0, 65.0, 88.0, 59.0] * 3,
    }).to_csv(p, index=False)
    return p


class TestDescribeConsumesStepOneRatherThanRepeatingIt:
    async def test_it_reads_the_profile_artifact_and_never_loads_the_file(
            self, db_session, ids_csv, artifact_dir, monkeypatch):
        """The contract that makes the chain worth having.

        Re-reading the CSV would not merely be slow: step 1 filtered it by the
        creator's RLS and dropped their denied columns before profiling, so a
        second read is a second, unsecured path to the data -- the exact shape
        of bug `test_rls_base_frame_choke_point` exists to prevent.
        """
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)

        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=member.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await automation_runner.tick(db_session)          # step 1 reads the file

        def _boom(*a, **k):
            raise AssertionError("describe re-read the dataset file")
        monkeypatch.setattr("app.services.ingest.load_file", _boom)

        assert await automation_runner.tick(db_session)   # step 2 must not
        steps = await _steps_of(db_session, run.id)
        assert steps[1].status == "ok"
        assert steps[1].output_ref

    async def test_it_refuses_when_step_one_left_no_artifact(
            self, db_session, ids_csv, artifact_dir):
        """A ref it did not earn is the one thing a step may never write."""
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=member.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await automation_runner.tick(db_session)

        steps = await _steps_of(db_session, run.id)
        import os
        rel = steps[0].output_ref[len("file://"):]
        os.remove(os.path.join(str(artifact_dir), rel))

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[1].status == "failed"
        assert not steps[1].output_ref
        assert "profile" in (steps[1].error or "").lower()


class TestDescribeWritesTheRolesAnalysesRead:
    async def test_a_named_identifier_is_persisted_as_one(
            self, db_session, ids_csv, artifact_dir):
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        await _run_through_describe(db_session, org, member, ds.id)

        await db_session.refresh(ds)
        assert (ds.column_meta or {}).get("student_id", {}).get("role") == "identifier"

    async def test_an_unnamed_near_unique_column_is_caught_too(
            self, db_session, ids_csv, artifact_dir):
        """`cohort_ref` matches no id name pattern. Step 1's profile calls it
        numeric; classify_role's uniqueness half is what catches it, and this
        is the assertion that proves step 2 consults the canonical heuristic
        rather than copying step 1's `is_identifier` forward."""
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        await _run_through_describe(db_session, org, member, ds.id)

        await db_session.refresh(ds)
        assert (ds.column_meta or {}).get("cohort_ref", {}).get("role") == "identifier"

    async def test_a_real_measure_is_left_alone(
            self, db_session, ids_csv, artifact_dir):
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        await _run_through_describe(db_session, org, member, ds.id)

        await db_session.refresh(ds)
        assert (ds.column_meta or {}).get("score", {}).get("role") != "identifier"

    async def test_the_step_marks_its_writes_as_inferred(
            self, db_session, ids_csv, artifact_dir):
        """Provenance travels WITH the value, or the next writer cannot tell
        a guess from a decision."""
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        await _run_through_describe(db_session, org, member, ds.id)

        await db_session.refresh(ds)
        assert (ds.column_meta or {}).get("student_id", {}).get("role_source") == "inferred"


class TestDescribeNeverOverwritesAHuman:
    async def test_an_authored_role_survives_the_step(
            self, db_session, ids_csv, artifact_dir):
        """ARCHITECTURE.md principle 5: human confirmation outranks inference
        permanently. A user who classified `student_id` as a category on the
        Fields pane must not find it relabelled by tonight's automation run.
        """
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        ds.column_meta = {"student_id": {"role": "category", "role_source": "confirmed"}}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(ds, "column_meta")
        await db_session.commit()

        await _run_through_describe(db_session, org, member, ds.id)

        await db_session.refresh(ds)
        assert ds.column_meta["student_id"]["role"] == "category"
        assert ds.column_meta["student_id"]["role_source"] == "confirmed"

    async def test_it_still_fills_the_gaps_around_that_column(
            self, db_session, ids_csv, artifact_dir):
        """Respecting one authored value must not abandon the rest of the
        table -- the step fills gaps, it does not relitigate decisions."""
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        ds.column_meta = {"student_id": {"role": "category", "role_source": "confirmed"}}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(ds, "column_meta")
        await db_session.commit()

        await _run_through_describe(db_session, org, member, ds.id)

        await db_session.refresh(ds)
        assert ds.column_meta.get("cohort_ref", {}).get("role") == "identifier"


class TestDescribeRefusals:
    async def test_a_non_dataset_subject_is_refused(self, db_session):
        """Called directly, not through the chain: step 1 refuses a non-dataset
        subject first, so a chain-level test would prove step ONE's contract
        and leave step 2's untested -- which is how a step ends up with no
        refusal of its own and nobody notices until a subject type changes."""
        org, admin = await _seed(db_session)
        ctx = automation_runner.StepContext(
            run_id=1, org_id=org.id, user_id=admin.id, user_email=admin.email,
            trigger="manual", subject_type="report", subject_id=1,
            step_name="describe")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._describe_step(ctx, db_session)

    async def test_a_missing_previous_ref_is_refused_not_defaulted(
            self, db_session, ids_csv, artifact_dir):
        """The file-deleted case above proves the artifact is READ. This proves
        the REF is required in the first place.

        A mutation that made _previous_output_ref return "" instead of raising
        survived the whole suite, because every other test left a real ref
        behind and only removed the file it pointed at. Distinct failures need
        distinct tests.
        """
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "norefs@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        ctx = automation_runner.StepContext(
            run_id=999, org_id=org.id, user_id=member.id,
            user_email=member.email, trigger="manual",
            subject_type="dataset", subject_id=ds.id, step_name="describe")
        # run 999 has no steps at all, so there is no profile ref to consume.
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._describe_step(ctx, db_session)

    async def test_a_dataset_deleted_between_steps_is_refused(
            self, db_session, ids_csv, artifact_dir):
        """Step 1 succeeded, so an artifact exists -- but the subject is gone.
        Describe must refuse rather than write metadata onto nothing, and the
        refusal is the org-blind 404 wording the rest of the product uses."""
        org, admin = await _seed(db_session)
        _role, member = await ProfileFixtures.member(
            db_session, org, "analyst@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, member, ids_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=member.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        await automation_runner.tick(db_session)

        await db_session.delete(ds)
        await db_session.commit()

        await automation_runner.tick(db_session)
        steps = await _steps_of(db_session, run.id)
        assert steps[1].status == "failed"
        assert not steps[1].output_ref


# ── step 7: notify, for real ─────────────────────────────────────────────────
#
# WHY THE SENTENCE IS NOT THE RECORD
# ----------------------------------
# A stored sentence can be rendered and nothing else: no filtering by path, no
# ordering by how much was rejected, no "needs your call" badge. So the record
# is typed columns (see the step-5/6 tests above), and `describe_run` derives
# the sentence from them at render time. The notification row carries a copy
# of that sentence because that is what a notification IS -- but it is a
# rendering, never a source. These tests pin the direction of that arrow.


async def _notifications_for(db_session, user_id: int):
    from sqlalchemy import select
    from app.models.models import Notification
    return (await db_session.execute(
        select(Notification).where(Notification.user_id == user_id)
        .order_by(Notification.id))).scalars().all()


async def _run_whole_chain(db_session, org, user, ds_id):
    """Tick until this run carries a ref on every step, or stops on its own
    (held for review, or failed). Ticks are shared and age-ordered, so a
    fixed count under-runs a second run; this loops on the run's own state."""
    run = await automation_runner.create_run(
        db_session, org_id=org.id, created_by=user.id,
        trigger="manual", subject_type="dataset", subject_id=ds_id)
    for _ in range(len(automation_runner.STEPS) * 3):
        steps = await _steps_of(db_session, run.id)
        if all(s.output_ref for s in steps) or any(
                s.status == "failed" for s in steps):
            break
        if not await automation_runner.tick(db_session):
            break
    await db_session.refresh(run)
    return run, await _steps_of(db_session, run.id)


class TestTheSentenceIsDerivedNotStored:
    async def test_the_sentence_changes_when_the_record_does(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """Change the record, and the sentence changes -- which is only true if
        the sentence is computed FROM it rather than stored beside it."""
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rec3@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run, _steps = await _run_whole_chain(db_session, org, user, ds.id)

        before, _link = automation_runner.describe_run(run)
        run.widgets_rejected = 99
        after, _link2 = automation_runner.describe_run(run)
        assert before != after, (
            "describe_run ignored the record; the sentence is stored, not derived")

    async def test_a_done_run_names_its_report_and_links_to_it(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """The reader has to know WHICH report is ready, and get there. Both
        come from the record's report columns, not from a fixed phrase."""
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "rec4@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run, _steps = await _run_whole_chain(db_session, org, user, ds.id)
        assert run.status == "done", [s.error for s in _steps]

        text, link = automation_runner.describe_run(run)
        assert run.result_report_name in text
        assert str(run.result_report_id) in (link or "")


class TestTheCreatorIsTheOneNotified:
    async def test_the_run_creator_gets_a_copy_of_the_derived_sentence(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """One row, for the creator, whose text IS the rendering of the record
        -- not a second sentence formatted somewhere else."""
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "note1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, _steps = await _run_whole_chain(db_session, org, user, ds.id)
        mine = await _notifications_for(db_session, user.id)
        assert mine, "the person whose run it was was never told"
        text, link = automation_runner.describe_run(run)
        assert mine[-1].text == text
        assert mine[-1].link == link
        assert str(run.result_report_id) in (mine[-1].link or "")

    async def test_nobody_else_in_the_org_does(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """RLS here is per-user: the report was composed from the CREATOR's
        rows. Telling a colleague about it advertises a slice that is not
        theirs, and the link would 404 or show different numbers."""
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "note2@example.invalid")
        _role2, bystander = await ProfileFixtures.member(
            db_session, org, "bystander@example.invalid", name="Other")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        await _run_whole_chain(db_session, org, user, ds.id)

        assert await _notifications_for(db_session, user.id)
        assert not await _notifications_for(db_session, bystander.id)
        assert not await _notifications_for(db_session, admin.id)


class TestNeedsReviewNotifiesToo:
    """"I built something and need your call" is the MORE important message.
    A run that halts at review and tells nobody is work nobody knows exists --
    and because the run stops at step 5, step 7 never runs for it at all. So
    the hold itself has to send, through the same `notify_run`."""

    async def test_a_held_run_still_notifies(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        _with_proposal(monkeypatch,
                       [GOOD_WIDGET, INVENTED_COLUMN, KPI_NO_MEASURE, MAP_NO_GEO],
                       path="model")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "hold1@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        run, _steps = await _run_whole_chain(db_session, org, user, ds.id)
        assert run.status == automation_runner.NEEDS_REVIEW

        mine = await _notifications_for(db_session, user.id)
        assert mine, "a run stopped for a decision and told nobody"
        assert mine[-1].text == automation_runner.describe_run(run)[0]

    async def test_the_two_messages_are_distinguishable(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """A finished run and a held one must not read the same. The reader
        acts on one and not the other."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "both@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        done_run, _ = await _run_whole_chain(db_session, org, user, ds.id)

        _with_proposal(monkeypatch,
                       [GOOD_WIDGET, INVENTED_COLUMN, KPI_NO_MEASURE, MAP_NO_GEO],
                       path="model")
        held_run, _ = await _run_whole_chain(db_session, org, user, ds.id)
        assert done_run.status == "done"
        assert held_run.status == automation_runner.NEEDS_REVIEW

        done_text, _ = automation_runner.describe_run(done_run)
        held_text, _ = automation_runner.describe_run(held_run)
        assert done_text != held_text
        # The held sentence asks for a decision and never claims readiness;
        # the finished one is the reverse. "review" alone separates nothing
        # -- both shapes say what review did -- and an earlier version of
        # this assertion let a mutation announce a held run as ready.
        assert "decision" in held_text.lower(), held_text
        assert "ready" not in held_text.lower(), held_text
        assert "ready" in done_text.lower(), done_text
        assert "decision" not in done_text.lower(), done_text


class TestNotifyContract:
    async def test_one_row_per_run_not_one_per_tick(
            self, db_session, reviewable_csv, artifact_dir, monkeypatch):
        """`output_ref` makes a step idempotent, and step 7's ref is committed
        in the same transaction as its row. If either half slipped, further
        ticks would send again."""
        _with_proposal(monkeypatch, [GOOD_WIDGET], path="insights")
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "once@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)

        await _run_whole_chain(db_session, org, user, ds.id)
        first = len(await _notifications_for(db_session, user.id))
        assert first == 1
        for _ in range(3):
            await automation_runner.tick(db_session)
        assert len(await _notifications_for(db_session, user.id)) == first

    async def test_a_non_dataset_subject_is_refused(self, db_session):
        org, admin = await _seed(db_session)
        ctx = automation_runner.StepContext(
            run_id=1, org_id=org.id, user_id=admin.id, user_email=admin.email,
            trigger="manual", subject_type="report", subject_id=1,
            step_name="notify")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._notify_step(ctx, db_session)

    async def test_a_run_whose_compose_recorded_no_report_is_refused(
            self, db_session, reviewable_csv, artifact_dir):
        """Step 7 consumes the RECORD, not just step 6's ref. A compose ref with
        no report id behind it is a link to nothing; refusing is the only
        honest output."""
        org, _admin = await _seed(db_session)
        _role, user = await ProfileFixtures.member(
            db_session, org, "noreport@example.invalid")
        ds = await ProfileFixtures.dataset(db_session, org, user, reviewable_csv)
        run = await automation_runner.create_run(
            db_session, org_id=org.id, created_by=user.id,
            trigger="manual", subject_type="dataset", subject_id=ds.id)
        for step in await _steps_of(db_session, run.id):
            if step.name == "compose":
                step.output_ref = "file:///nowhere/compose.json"
        await db_session.flush()
        assert run.result_report_id is None

        ctx = automation_runner.StepContext(
            run_id=run.id, org_id=org.id, user_id=user.id, user_email=user.email,
            trigger="manual", subject_type="dataset", subject_id=ds.id,
            step_name="notify")
        with pytest.raises(automation_runner.StepRefused):
            await automation_runner._notify_step(ctx, db_session)
        assert not await _notifications_for(db_session, user.id)
