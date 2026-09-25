"""E07/E12: durable jobs, with database imports as the first workload.

An import used to run inside the HTTP request: close the tab and the outcome
was lost, restart the server and the work was lost, and there was nothing to
cancel or retry. These pin the job contract (services/jobs.py) through the
real import path: queue, run, cancel, resume after a dead worker, fencing
between overlapping workers, permissions at execution, retries, visibility.

The worker is driven by hand (`jobs.run_next` / `jobs.claim`) with explicit
clock values, so "the lease ran out" is a parameter rather than a sleep.
"""
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.core.config import settings
from app.models.models import AuditLogEntry, DataSource, Dataset, Job, Role, User
from app.services import jobs


@pytest.fixture(autouse=True)
def _uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


@pytest.fixture
def factory(db_session):
    """Sessions on the test's one in-memory database, as a worker would open."""
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _sqlite(tmp_path, n=3):
    path = tmp_path / "src.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER, region TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(i, "North" if i % 2 else "South") for i in range(n)])
    conn.commit()
    conn.close()
    return str(path)


async def _source(db_session, org_id, tmp_path, n=3):
    src = DataSource(name="Warehouse", type="sqlite", config={"filepath": _sqlite(tmp_path, n)}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    return src


async def _queue(client, src, headers, **body):
    payload = {"dataset_name": "Orders", "table": "t", **body}
    key = payload.pop("key", None)
    h = dict(headers, **({"Idempotency-Key": key} if key else {}))
    return await client.post(f"/api/v1/data-sources/{src.id}/import-jobs", json=payload, headers=h)


async def _job(db_session, job_id) -> Job:
    return (await db_session.execute(select(Job).where(Job.id == job_id)
                                     .execution_options(populate_existing=True))).scalar_one()


async def _count(db_session, model) -> int:
    return (await db_session.execute(select(func.count()).select_from(model))).scalar_one()


def _upload_files(tmp_path):
    root = tmp_path / "uploads"
    return sorted(p.name for p in root.rglob("*") if p.is_file()) if root.exists() else []


# ── The happy path ───────────────────────────────────────────────────────────

async def test_a_queued_import_answers_at_once_and_the_worker_makes_the_dataset(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path, n=5)
    r = await _queue(client, src, auth_headers["a"])
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["state"] == "queued" and body["kind"] == "dataset.import"
    assert body["subject"] == "Warehouse · t → Orders"
    assert await _count(db_session, Dataset) == 0          # nothing yet: it is queued

    assert await jobs.run_next(factory, "w1") == "succeeded"

    job = await _job(db_session, body["id"])
    assert job.state == "succeeded" and job.attempt == 1 and job.lease_owner is not None
    assert job.result["row_count"] == 5 and job.result["replaced"] is False
    ds = await db_session.get(Dataset, job.result["dataset_id"])
    assert ds.name == "Orders" and ds.row_count == 5 and Path(ds.filename).exists()
    assert job.progress == {"stage": "done"} and job.finished_at is not None

    # Same audit trail as the request path, plus the queueing itself.
    actions = (await db_session.execute(select(AuditLogEntry.action))).scalars().all()
    assert "job.enqueue" in actions and "dataset.import" in actions

    # The owner can read it back through the API.
    got = await client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers["a"])
    assert got.status_code == 200 and got.json()["result"]["dataset_id"] == ds.id
    assert "inputs" not in got.json()
    assert await jobs.run_next(factory, "w1") is None      # nothing left to do


async def test_a_reimport_job_replaces_the_dataset_in_place(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path, n=4)
    first = await client.post(f"/api/v1/data-sources/{src.id}/import", headers=auth_headers["a"],
                              json={"dataset_name": "Orders", "table": "t"})
    ds_id = first.json()["id"]
    r = await _queue(client, src, auth_headers["a"], table=None,
                     query="SELECT * FROM t WHERE id < 2", dataset_id=ds_id)
    assert r.status_code == 202, r.text
    assert await jobs.run_next(factory, "w1") == "succeeded"
    job = await _job(db_session, r.json()["id"])
    assert job.result["dataset_id"] == ds_id and job.result["replaced"] is True
    assert await _count(db_session, Dataset) == 1
    ds = (await db_session.execute(select(Dataset).where(Dataset.id == ds_id)
                                   .execution_options(populate_existing=True))).scalar_one()
    assert ds.row_count == 2


# ── Idempotency ──────────────────────────────────────────────────────────────

async def test_the_same_idempotency_key_returns_the_same_job(client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    r1 = await _queue(client, src, auth_headers["a"], key="click-1")
    r2 = await _queue(client, src, auth_headers["a"], key="click-1")
    assert r1.status_code == r2.status_code == 202
    assert r1.json()["id"] == r2.json()["id"]
    assert await _count(db_session, Job) == 1

    clash = await _queue(client, src, auth_headers["a"], key="click-1", dataset_name="Other")
    assert clash.status_code == 409


async def test_two_identical_requests_racing_past_the_lookup_get_one_job(
        client, db_session, two_orgs, auth_headers, tmp_path, monkeypatch):
    """The unique constraint settles the race the lookup cannot see. The
    loser's rollback expires the request's user; enqueue must reload it (and
    its role) or the request dies on a lazy load (seen live on Postgres)."""
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    first = (await _queue(client, src, auth_headers["a"], key="race")).json()["id"]

    real = jobs._find_by_key
    calls = {"n": 0}

    async def _blind_first_lookup(db, org_id, key):
        calls["n"] += 1
        return None if calls["n"] == 1 else await real(db, org_id, key)

    monkeypatch.setattr(jobs, "_find_by_key", _blind_first_lookup)
    r = await _queue(client, src, auth_headers["a"], key="race")
    assert r.status_code == 202, r.text
    assert r.json()["id"] == first and calls["n"] == 2
    assert await _count(db_session, Job) == 1


# ── Cancellation ─────────────────────────────────────────────────────────────

async def test_cancelling_a_queued_job_means_it_never_runs(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    c = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers["a"])
    assert c.status_code == 200 and c.json()["state"] == "cancelled"
    assert await jobs.run_next(factory, "w1") is None
    assert await _count(db_session, Dataset) == 0


async def test_cancelling_a_running_import_stops_it_with_nothing_written(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    """The cancel lands while the source query runs; the next checkpoint stops
    the job before any file is written or any dataset committed."""
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]

    async with factory() as s:
        claimed = await jobs.claim(s, "w1")
    assert claimed is not None
    # Cancel requested after the claim, i.e. while it is running.
    c = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers["a"])
    assert c.status_code == 200 and c.json()["state"] == "running" and c.json()["cancel_requested"]

    assert await jobs.execute(factory, *claimed) == "cancelled"
    job = await _job(db_session, job_id)
    assert job.state == "cancelled" and job.result is None
    assert await _count(db_session, Dataset) == 0
    assert _upload_files(tmp_path) == []                  # no file, no .tmp, no sidecar


async def test_a_cancel_after_the_file_is_written_aside_removes_it(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, monkeypatch):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    async with factory() as s:
        claimed = await jobs.claim(s, "w1")

    orig_checkpoint = jobs.JobContext.checkpoint

    async def _cancel_before_saving(self, stage, **detail):
        if stage == "saving":
            async with factory() as s2:
                job = await s2.get(Job, self.job_id)
                await jobs.request_cancel(s2, job, two_orgs["a"]["user"])
        return await orig_checkpoint(self, stage, **detail)

    monkeypatch.setattr(jobs.JobContext, "checkpoint", _cancel_before_saving)
    assert await jobs.execute(factory, *claimed) == "cancelled"
    assert await _count(db_session, Dataset) == 0
    assert _upload_files(tmp_path) == []
    assert (await _job(db_session, job_id)).state == "cancelled"


# ── Restart: a dead worker's job resumes; overlapping workers never double up ─

async def test_a_job_whose_worker_died_is_resumed_by_the_next_claim(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    t0 = datetime.utcnow()
    async with factory() as s:
        assert await jobs.claim(s, "dead-worker", now=t0) is not None
    # The process died here: the row still says running, under a live lease.
    async with factory() as s:
        assert await jobs.claim(s, "w2", now=t0 + timedelta(seconds=10)) is None

    later = t0 + timedelta(seconds=jobs.LEASE_SECONDS + 1)
    assert await jobs.run_next(factory, "w2", now=later) == "succeeded"
    job = await _job(db_session, job_id)
    assert job.state == "succeeded" and job.attempt == 2
    assert job.lease_owner.startswith("w2:")
    assert await _count(db_session, Dataset) == 1


async def test_a_worker_that_lost_its_lease_cannot_commit_a_second_dataset(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, monkeypatch):
    """Worker A stalls past its lease inside the source query; worker B takes
    the job over. A must not commit anything when it wakes up, and must not
    leave its file behind: exactly one dataset, B's."""
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    t0 = datetime.utcnow()
    async with factory() as s:
        claim_a = await jobs.claim(s, "A", now=t0)

    stolen: dict = {}

    orig_checkpoint = jobs.JobContext.checkpoint

    async def _b_takes_over_while_a_queries(self, stage, **detail):
        if self.token == claim_a[1] and stage == "writing" and not stolen:
            async with factory() as s2:
                stolen["b"] = await jobs.claim(s2, "B", now=t0 + timedelta(seconds=jobs.LEASE_SECONDS + 5))
        return await orig_checkpoint(self, stage, **detail)

    monkeypatch.setattr(jobs.JobContext, "checkpoint", _b_takes_over_while_a_queries)

    assert await jobs.execute(factory, *claim_a) is None           # A: lease lost, no outcome
    assert await _count(db_session, Dataset) == 0
    assert _upload_files(tmp_path) == []

    assert stolen["b"] is not None
    assert await jobs.execute(factory, *stolen["b"]) == "succeeded"
    assert await _count(db_session, Dataset) == 1
    assert (await _job(db_session, job_id)).attempt == 2


async def test_the_completion_write_is_fenced_by_the_lease(db_session, two_orgs, factory):
    """The last line of defence: even at commit time, a stale token writes
    nothing, so the handler's transaction (dataset and all) rolls back."""
    user = two_orgs["a"]["user"]
    job, _ = await jobs.enqueue(db_session, user=user, kind="dataset.import",
                                inputs={"data_source_id": 1, "dataset_name": "x", "table": "t"})
    async with factory() as s:
        job_id, token = await jobs.claim(s, "A")
    ctx = jobs.JobContext(job_id=job_id, token="A:stale", kind=job.kind, org_id=job.org_id,
                          created_by=user.id, inputs={}, attempt=1, session_factory=factory)
    async with factory() as s:
        with pytest.raises(jobs.LeaseLost):
            await ctx.complete(s, {"dataset_id": 1})
        await s.rollback()
    assert (await _job(db_session, job_id)).state == "running"


async def test_a_job_interrupted_too_often_fails_instead_of_looping(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    t = datetime.utcnow()
    for i in range(3):   # max_attempts: three workers die in turn
        async with factory() as s:
            assert await jobs.claim(s, f"dead-{i}", now=t) is not None
        t += timedelta(seconds=jobs.LEASE_SECONDS + 1)
    async with factory() as s:
        assert await jobs.claim(s, "w", now=t) is None
    job = await _job(db_session, job_id)
    assert job.state == "failed" and job.error_code == "interrupted" and job.attempt == 3
    assert await _count(db_session, Dataset) == 0


# ── Permissions are checked when the job runs ────────────────────────────────

async def test_an_admin_demoted_while_the_job_waited_does_not_get_the_import(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    org_id = two_orgs["a"]["org"].id
    src = await _source(db_session, org_id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]

    viewer = Role(org_id=org_id, name="Viewer", is_org_admin=False)
    db_session.add(viewer)
    await db_session.flush()
    admin = await db_session.get(User, two_orgs["a"]["user"].id)
    admin.role_id = viewer.id
    await db_session.commit()

    assert await jobs.run_next(factory, "w1") == "failed"
    job = await _job(db_session, job_id)
    assert job.error_code == "not_allowed"
    assert await _count(db_session, Dataset) == 0


async def test_a_connection_deleted_while_the_job_waited_fails_it_plainly(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    await db_session.delete(src)
    await db_session.commit()
    assert await jobs.run_next(factory, "w1") == "failed"
    assert "no longer exists" in (await _job(db_session, job_id)).error


# ── Failures, retries ────────────────────────────────────────────────────────

async def test_a_source_error_fails_the_job_with_the_sources_reason_and_retry_is_a_new_job(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"], table="missing_table")).json()["id"]
    assert await jobs.run_next(factory, "w1") == "failed"
    job = await _job(db_session, job_id)
    assert job.error_code == "refused" and "missing_table" in job.error
    assert _upload_files(tmp_path) == []

    r = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers["a"])
    assert r.status_code == 202, r.text
    retry = r.json()
    assert retry["id"] != job_id and retry["retry_of"] == job_id and retry["state"] == "queued"
    assert (await _job(db_session, job_id)).state == "failed"      # the old one is history
    again = await _job(db_session, retry["id"])
    assert again.inputs == job.inputs                              # same inputs, verbatim


async def test_only_a_failed_or_cancelled_job_can_be_retried(
        client, db_session, two_orgs, auth_headers, tmp_path, factory):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    assert (await client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers["a"])).status_code == 409
    await jobs.run_next(factory, "w1")
    assert (await client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_headers["a"])).status_code == 409


async def test_an_unexpected_crash_is_stored_without_its_internals(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, monkeypatch):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    from app.services import source_import

    async def _boom(*a, **k):
        raise RuntimeError("secret internal state at 0xdeadbeef")

    monkeypatch.setattr(source_import, "import_from_source", _boom)
    assert await jobs.run_next(factory, "w1") == "failed"
    job = await _job(db_session, job_id)
    assert job.error_code == "unexpected" and "0xdeadbeef" not in job.error


def test_stored_errors_mask_credentials_and_are_capped():
    msg = ("could not connect: postgresql://etl:Hunter2@db.internal:5432/sales "
           "password=Hunter2 PWD='Hunter2';")
    out = jobs.sanitize_error(msg)
    assert "Hunter2" not in out
    assert "postgresql://***:***@db.internal:5432/sales" in out
    assert len(jobs.sanitize_error("x" * 5000)) == jobs.ERROR_MAX_CHARS


# ── Who may queue and see jobs ───────────────────────────────────────────────

async def _member_headers(db_session, org_id):
    from app.core.security import create_access_token, hash_password
    role = Role(org_id=org_id, name="Member", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email="member-jobs@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, org_id)}"}


async def test_jobs_are_visible_to_their_owner_and_org_admins_only(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    member = await _member_headers(db_session, two_orgs["a"]["org"].id)

    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers["b"])).status_code == 404
    assert (await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers["b"])).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=member)).status_code == 404
    assert (await client.get("/api/v1/jobs", headers=member)).json() == []
    assert (await client.get("/api/v1/jobs", headers=auth_headers["b"])).json() == []

    listed = (await client.get("/api/v1/jobs?kind=dataset.import&active=true", headers=auth_headers["a"])).json()
    assert [j["id"] for j in listed] == [job_id]


async def test_queueing_needs_an_admin_a_real_target_and_an_import_mode(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    member = await _member_headers(db_session, two_orgs["a"]["org"].id)
    assert (await _queue(client, src, member)).status_code == 403
    assert (await _queue(client, src, auth_headers["b"])).status_code == 404       # other org's source
    assert (await _queue(client, src, auth_headers["a"], mode="directquery")).status_code == 400
    assert (await _queue(client, src, auth_headers["a"], dataset_id=999)).status_code == 404
    assert (await _queue(client, src, auth_headers["a"], table=None)).status_code == 400
    assert await _count(db_session, Job) == 0


async def test_the_worker_loop_picks_up_a_queued_import_by_itself(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, monkeypatch):
    """The loop main.lifespan starts: nobody calls run_next, the job still runs."""
    import asyncio
    monkeypatch.setattr(jobs, "POLL_SECONDS", 0.01)
    # One job at a time: this suite's in-memory SQLite is ONE shared connection
    # (StaticPool), so an idle poll closing its session would roll back the
    # running job's open transaction under it. Real pools hand each session its
    # own connection; the claim/fencing tests above cover concurrency.
    monkeypatch.setattr(jobs, "WORKER_CONCURRENCY", 1)
    src = await _source(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, src, auth_headers["a"])).json()["id"]
    # Wait on the worker's own outcome rather than polling the shared
    # connection from here while it writes.
    done = asyncio.Event()
    outcomes: list = []
    real_execute = jobs.execute

    async def _execute_and_signal(*a, **k):
        outcomes.append(await real_execute(*a, **k))
        done.set()
        return outcomes[-1]

    monkeypatch.setattr(jobs, "execute", _execute_and_signal)
    worker = asyncio.create_task(jobs.run_worker(factory, "loop"))
    try:
        await asyncio.wait_for(done.wait(), timeout=30)
    finally:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
    assert outcomes == ["succeeded"]
    assert (await _job(db_session, job_id)).state == "succeeded"
    assert await _count(db_session, Dataset) == 1
