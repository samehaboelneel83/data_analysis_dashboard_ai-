"""E12: scheduled deliveries as durable jobs, each occurrence sent at most once.

The scheduler used to send inside its tick, and one delivery could go out twice:
two processes each holding the same due list (the per-item lock stopped them
overlapping, not following one another), or a restart between sending and
recording. These pin services/delivery_jobs.py: one job per due occurrence
however many processes see it, a claim on the schedule row before anything is
sent, and a resumed attempt that does not send again.

The worker is driven by hand (`jobs.run_next` / `jobs.claim` / `jobs.execute`)
as in test_jobs.py. Recipients are a webhook, whose sender is replaced by a
counter, so "sent" is observable without SMTP.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.models import Job, ReportSchedule, ScheduleFailure
from app.services import jobs
from app.services.delivery_jobs import DELIVERY_JOB_KIND, enqueue_due
from app.services.refresh_scheduler import enqueue_deliveries

from .test_scheduled_delivery import _dataset, _report_with_widget

HOOK = "https://hooks.example.com/sales"


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.delivery.post_webhook",
                        lambda url, title, text: calls.append(url) or None)
    return calls


@pytest.fixture
async def schedule(client, auth_headers, db_session, two_orgs, sales_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
    rid = await _report_with_widget(client, auth_headers["a"], ds)
    r = await client.post(f"/api/v1/reports/{rid}/schedules",
                          json={"interval_minutes": 60, "recipients": [HOOK]},
                          headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    return {"id": r.json()["id"], "report_id": rid}


@pytest.fixture
def sales_ds(tmp_path):
    import pandas as pd
    p = tmp_path / "sched.csv"
    pd.DataFrame({"region": ["US", "US", "CA"], "revenue": [100.0, 50.0, 30.0]}).to_csv(p, index=False)
    return str(p)


async def _jobs(db_session):
    return (await db_session.execute(select(Job).where(Job.kind == DELIVERY_JOB_KIND)
                                      .order_by(Job.id))).scalars().all()


async def _sched(db_session, sid):
    row = await db_session.get(ReportSchedule, sid)
    await db_session.refresh(row)
    return row


class TestOneJobPerOccurrence:
    async def test_two_processes_seeing_the_same_due_delivery_queue_one_job(
            self, db_session, factory, schedule, sent):
        await enqueue_deliveries(factory, [schedule["id"]])
        await enqueue_deliveries(factory, [schedule["id"]])      # the other process
        [job] = await _jobs(db_session)
        assert job.state == jobs.QUEUED
        assert job.inputs == {"schedule_id": schedule["id"], "after": None}
        assert job.idempotency_key == f"delivery:{schedule['id']}:first:0"
        assert job.created_by is not None           # runs as the creator
        assert sent == [], "queuing sends nothing"

    async def test_the_job_sends_once_and_the_schedule_is_no_longer_due(
            self, db_session, factory, schedule, sent):
        await enqueue_deliveries(factory, [schedule["id"]])
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        assert sent == [HOOK]
        [job] = await _jobs(db_session)
        await db_session.refresh(job)
        assert job.result["outcome"] == "sent"
        assert "posted to webhook" in job.result["status"]
        sched = await _sched(db_session, schedule["id"])
        assert sched.last_run_at is not None and "posted to webhook" in sched.last_status
        # The next occurrence follows this run: a different key.
        await enqueue_deliveries(factory, [schedule["id"]])
        assert len(await _jobs(db_session)) == 2
        assert (await _jobs(db_session))[1].inputs["after"] is not None


class TestAtMostOnce:
    async def test_a_second_job_for_the_same_occurrence_does_not_send_again(
            self, db_session, factory, schedule, sent, two_orgs):
        """However a duplicate arises (a manual retry, a key collision), the
        claim on the schedule row lets one of them send."""
        await enqueue_deliveries(factory, [schedule["id"]])
        [first] = await _jobs(db_session)
        await jobs.enqueue(db_session, user=two_orgs["a"]["user"], kind=DELIVERY_JOB_KIND,
                           inputs=dict(first.inputs), idempotency_key="another-key")
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        assert await jobs.run_next(factory, "w2") == jobs.SUCCEEDED
        assert sent == [HOOK]
        second = (await _jobs(db_session))[1]
        await db_session.refresh(second)
        assert second.result == {"outcome": "skipped", "reason": "already delivered for this occurrence"}

    async def test_send_now_in_between_means_the_queued_delivery_is_skipped(
            self, client, auth_headers, db_session, factory, schedule, sent):
        await enqueue_deliveries(factory, [schedule["id"]])
        r = await client.post(f"/api/v1/reports/{schedule['report_id']}/schedules/{schedule['id']}/run-now",
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        assert sent == [HOOK], "Send now delivered it; the queued job must not repeat it"

    async def test_a_resumed_attempt_after_the_claim_does_not_send_again(
            self, db_session, factory, schedule, sent):
        """The server stopped after claiming the occurrence: whether it went
        out is unknown, and a second copy is worse than a visible note."""
        await enqueue_deliveries(factory, [schedule["id"]])
        async with factory() as s:
            job_id, _token = await jobs.claim(s, "w1")
        # What the first attempt left: its claim on the schedule, then silence.
        await db_session.execute(update(ReportSchedule).where(ReportSchedule.id == schedule["id"])
                                 .values(last_run_at=datetime.utcnow(),
                                         last_status=f"sending (job {job_id})"))
        await db_session.execute(update(Job).where(Job.id == job_id).values(
            lease_expires_at=datetime.utcnow() - timedelta(seconds=1)))
        await db_session.commit()

        assert await jobs.run_next(factory, "w2") == jobs.SUCCEEDED
        assert sent == []
        job = await db_session.get(Job, job_id)
        await db_session.refresh(job)
        assert (job.attempt, job.result) == (2, {"outcome": "interrupted"})
        sched = await _sched(db_session, schedule["id"])
        assert sched.last_status.startswith("interrupted while sending: not resent")

    async def test_a_worker_that_lost_its_lease_cannot_claim_the_occurrence(
            self, db_session, factory, schedule, sent):
        await enqueue_deliveries(factory, [schedule["id"]])
        async with factory() as s:
            job_id, token = await jobs.claim(s, "w1")
        # Presumed dead and taken over before it got going.
        await db_session.execute(update(Job).where(Job.id == job_id).values(lease_owner="someone-else"))
        await db_session.commit()
        assert await jobs.execute(factory, job_id, token) is None
        assert sent == []
        sched = await _sched(db_session, schedule["id"])
        assert sched.last_run_at is None and not (sched.last_status or "").startswith("sending")


class TestFailures:
    async def test_a_delivery_that_cannot_be_built_fails_backs_off_and_is_queued_again_later(
            self, db_session, factory, schedule, sent, monkeypatch):
        async def broken(*a, **kw):
            raise RuntimeError("widget query failed")
        monkeypatch.setattr("app.services.delivery.build_digest", broken)
        await enqueue_deliveries(factory, [schedule["id"]])
        assert await jobs.run_next(factory, "w1") == jobs.FAILED
        [job] = await _jobs(db_session)
        await db_session.refresh(job)
        assert job.error_code == "build_failed" and "widget query failed" in job.error
        failure = (await db_session.execute(select(ScheduleFailure).where(
            ScheduleFailure.kind == "schedule", ScheduleFailure.item_id == schedule["id"]))).scalar_one()
        assert failure.attempts == 1 and failure.next_attempt_at is not None
        assert sent == []

        # When it is due again after the backoff, a NEW job is queued (the
        # failure count is in the key), not the failed one found again.
        await db_session.execute(update(ReportSchedule).where(ReportSchedule.id == schedule["id"])
                                 .values(last_run_at=None))
        await db_session.commit()
        await enqueue_deliveries(factory, [schedule["id"]])
        assert len(await _jobs(db_session)) == 2

    async def test_success_clears_an_earlier_failure(self, db_session, factory, schedule, sent):
        db_session.add(ScheduleFailure(kind="schedule", item_id=schedule["id"], attempts=2,
                                       first_failed_at=datetime.utcnow()))
        await db_session.commit()
        await enqueue_deliveries(factory, [schedule["id"]])
        assert (await _jobs(db_session))[0].idempotency_key.endswith(":2")
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        assert (await db_session.execute(select(func.count()).select_from(ScheduleFailure))).scalar_one() == 0


class TestTheTick:
    async def test_without_a_job_worker_the_tick_sends_inline_as_before(
            self, db_session, factory, schedule, sent, monkeypatch):
        """A deployment that turned the worker off must not queue deliveries
        nothing will ever run."""
        from app.services import refresh_scheduler
        monkeypatch.setattr(settings, "job_worker_enabled", False)
        await refresh_scheduler.deliver_due(factory, [schedule["id"]])
        assert sent == [HOOK]
        assert await _jobs(db_session) == []

    async def test_with_a_job_worker_the_tick_queues_and_sends_nothing(
            self, db_session, factory, schedule, sent):
        from app.services import refresh_scheduler
        await refresh_scheduler.deliver_due(factory, [schedule["id"]])
        assert sent == [] and len(await _jobs(db_session)) == 1

    async def test_a_schedule_whose_creator_is_gone_is_not_queued(self, db_session, schedule):
        stored = await db_session.get(ReportSchedule, schedule["id"])
        # A copy that is not in the session: the foreign key keeps a real
        # row's creator, and run_schedule is where an orphan disables itself.
        orphan = ReportSchedule(id=stored.id, org_id=stored.org_id, report_id=stored.report_id,
                                creator_user_id=999_999, interval_minutes=60, recipients=[HOOK])
        assert await enqueue_due(db_session, orphan) is None
        assert await _jobs(db_session) == []
