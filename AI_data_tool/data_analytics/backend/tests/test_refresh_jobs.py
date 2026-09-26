"""E12: a manual dataset refresh as a durable job.

The synchronous refresh held the request for as long as the source took, lost
its outcome to a closed tab or a proxy timeout, lost its work to a restart,
and let two refreshes write one file at once -- an incremental one appends, so
two overlapping appends wrote the same rows twice. These pin the queued path
(services/refresh_jobs.py): the same refresh as the endpoint, run by the
worker, one per dataset, cancellable, retried after a dead worker, and
writing its file only once its success is fenced.

The worker is driven by hand (`jobs.run_next` / `jobs.claim` / `jobs.execute`)
as in test_jobs.py; the source is `connections.import_to_dataframe`,
monkeypatched, counting its calls.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.models import (AuditLogEntry, DataSource, Dataset, DatasetColumn,
                               Job, Report, ReportPage, ReportWidget, Role, User,
                               Watermark)
from app.services import jobs
from app.services.refresh_jobs import REFRESH_JOB_KIND


@pytest.fixture(autouse=True)
def _uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


class Source:
    """The connection's table, as `import_to_dataframe` returns it: everything
    for a full load, only the rows past the cursor for an incremental one."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def __call__(self, cfg, table, query, params=None):
        self.calls += 1
        df = pd.DataFrame(self.rows)
        if params and "cursor_val" in params:
            df = df[df["updated_at"] > float(params["cursor_val"])]
        return df.reset_index(drop=True)


@pytest.fixture
def source(monkeypatch):
    src = Source([{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20},
                  {"id": 3, "updated_at": 30}])
    monkeypatch.setattr("app.services.connections.import_to_dataframe", src)
    return src


async def _dataset(db_session, org_id, tmp_path, *, cursor=None, owner=None):
    """A dataset imported from a connection: its file holds ids 1 and 2."""
    path = tmp_path / "orders.csv"
    pd.DataFrame([{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}]).to_csv(path, index=False)
    src = DataSource(name="Warehouse", type="sqlite", config={"filepath": "x.db"}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="Orders", filename=str(path), org_id=org_id, row_count=2, col_count=2,
                 data_source_id=src.id, source_table="t", created_by=owner)
    db_session.add(ds)
    await db_session.flush()
    for col in ("id", "updated_at"):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype="numeric", missing_pct=0, stats={}))
    if cursor is not None:
        db_session.add(Watermark(dataset_id=ds.id, strategy="incremental",
                                 cursor_column="updated_at", cursor_value=cursor))
    await db_session.commit()
    return ds


def _ids(ds) -> list[int]:
    return sorted(pd.read_csv(ds.filename)["id"].tolist())


async def _queue(client, ds, headers, **body):
    key = body.pop("key", None)
    h = dict(headers, **({"Idempotency-Key": key} if key else {}))
    return await client.post(f"/api/v1/datasets/{ds.id}/refresh-jobs",
                             json={"mode": "full", **body}, headers=h)


async def _job(db_session, job_id) -> Job:
    return (await db_session.execute(select(Job).where(Job.id == job_id)
                                     .execution_options(populate_existing=True))).scalar_one()


async def _fresh(db_session, model, id_):
    return (await db_session.execute(select(model).where(model.id == id_)
                                     .execution_options(populate_existing=True))).scalar_one()


# ── Queue, run, land ─────────────────────────────────────────────────────────

async def test_a_queued_refresh_answers_at_once_and_the_worker_reloads_the_data(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await _queue(client, ds, auth_headers["a"])
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["state"] == "queued" and job["kind"] == REFRESH_JOB_KIND
    assert job["subject"] == "Orders · refresh from Warehouse"
    assert source.calls == 0 and _ids(ds) == [1, 2]            # nothing ran yet

    assert await jobs.run_next(factory, "w1") == "succeeded"
    done = await _job(db_session, job["id"])
    assert done.result == {"dataset_id": ds.id, "dataset_name": "Orders", "row_count": 3,
                           "col_count": 2, "mode": "full", "rows_added": 3, "warning": None}
    assert _ids(ds) == [1, 2, 3]
    fresh = await _fresh(db_session, Dataset, ds.id)
    assert fresh.row_count == 3 and fresh.last_refreshed_at is not None
    audit = (await db_session.execute(select(AuditLogEntry.action).where(
        AuditLogEntry.entity == "dataset", AuditLogEntry.entity_id == ds.id))).scalars().all()
    assert "dataset.refresh" in audit


async def test_an_incremental_refresh_appends_once_and_advances_the_watermark(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path, cursor="20")
    r = await _queue(client, ds, auth_headers["a"], mode="incremental")
    assert r.json()["subject"] == "Orders · incremental refresh from Warehouse"
    assert await jobs.run_next(factory, "w1") == "succeeded"
    assert _ids(ds) == [1, 2, 3]
    wm = (await db_session.execute(select(Watermark).where(Watermark.dataset_id == ds.id)
                                   .execution_options(populate_existing=True))).scalar_one()
    assert wm.cursor_value == "30"
    assert (await _job(db_session, r.json()["id"])).result["rows_added"] == 1


# ── Overlap: one refresh per dataset, and fenced effects ─────────────────────

async def test_a_worker_that_lost_its_lease_writes_nothing_and_the_rows_land_once(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source, monkeypatch):
    """The window the fence closes: attempt 1 fetches the new rows, then loses
    its lease (paused past it; another worker took the job) before it records
    success. It must not append; attempt 2 appends, once."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path, cursor="20")
    job_id = (await _queue(client, ds, auth_headers["a"], mode="incremental")).json()["id"]

    real = jobs.JobContext.checkpoint

    async def stolen_after_fetch(self, stage, **detail):
        await real(self, stage, **detail)
        if stage == "saving" and self.token == first[1]:
            async with factory() as s:        # another worker takes the job over
                await s.execute(update(Job).where(Job.id == self.job_id)
                                .values(lease_owner="w2-token"))
                await s.commit()
    monkeypatch.setattr(jobs.JobContext, "checkpoint", stolen_after_fetch)

    async with factory() as s:
        first = await jobs.claim(s, "w1")
    assert await jobs.execute(factory, *first) is None          # lease lost: no outcome
    assert source.calls == 1
    assert _ids(ds) == [1, 2]                                     # the file is untouched
    wm = (await db_session.execute(select(Watermark).where(Watermark.dataset_id == ds.id)
                                   .execution_options(populate_existing=True))).scalar_one()
    assert wm.cursor_value == "20"                                # nor the watermark

    # The lease runs out; the next worker resumes the job as attempt 2.
    await db_session.execute(update(Job).where(Job.id == job_id).values(
        lease_expires_at=datetime.utcnow() - timedelta(seconds=1)))
    await db_session.commit()
    assert await jobs.run_next(factory, "w3") == "succeeded"
    assert _ids(ds) == [1, 2, 3]                                  # appended once
    assert (await _job(db_session, job_id)).attempt == 2


async def test_one_refresh_per_dataset(client, db_session, two_orgs, auth_headers, tmp_path, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    first = await _queue(client, ds, auth_headers["a"])
    again = await _queue(client, ds, auth_headers["a"])
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    # The synchronous refresh would write the same file under it.
    sync = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full"},
                             headers=auth_headers["a"])
    assert sync.status_code == 409
    assert "already queued or running" in sync.json()["detail"]
    assert source.calls == 0
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 1


async def test_someone_elses_refresh_of_the_dataset_is_a_refusal_not_their_job(
        client, db_session, two_orgs, auth_headers, tmp_path, source):
    """A member who owns the dataset may refresh it, but an admin's queued
    refresh is not theirs to see: they learn one is running, nothing more."""
    from app.core.security import create_access_token, hash_password
    org = two_orgs["a"]["org"]
    member_role = Role(org_id=org.id, name="Member", is_org_admin=False)
    db_session.add(member_role)
    await db_session.flush()
    other = User(org_id=org.id, role_id=member_role.id, email="member@example.com",
                 password_hash=hash_password("pw"))
    db_session.add(other)
    await db_session.commit()
    ds = await _dataset(db_session, org.id, tmp_path, owner=other.id)
    await _queue(client, ds, auth_headers["a"])
    h = {"Authorization": f"Bearer {create_access_token(other.id, other.org_id)}"}
    r = await _queue(client, ds, h)
    assert r.status_code == 409, r.text
    active = (await client.get(f"/api/v1/datasets/{ds.id}/refresh-jobs/active", headers=h)).json()
    assert active == {"state": "queued", "by_someone_else": True}


async def test_the_scheduler_leaves_a_dataset_to_its_queued_refresh(
        client, db_session, two_orgs, auth_headers, tmp_path, source):
    from app.services.refresh_scheduler import refresh_one
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await _queue(client, ds, auth_headers["a"])
    assert await refresh_one(db_session, await _fresh(db_session, Dataset, ds.id)) is False
    assert source.calls == 0 and _ids(ds) == [1, 2]


async def test_the_same_idempotency_key_is_the_same_job(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    a = await _queue(client, ds, auth_headers["a"], key="k-1")
    assert await jobs.run_next(factory, "w1") == "succeeded"
    b = await _queue(client, ds, auth_headers["a"], key="k-1")    # a resent request
    assert b.json()["id"] == a.json()["id"] and b.json()["state"] == "succeeded"
    assert source.calls == 1


# ── Cancel, permissions, schema breaks ───────────────────────────────────────

async def test_a_cancelled_refresh_writes_nothing(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, ds, auth_headers["a"])).json()["id"]
    async with factory() as s:
        claimed = await jobs.claim(s, "w1")                       # running now
    r = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers["a"])
    assert r.json()["cancel_requested"] is True
    assert await jobs.execute(factory, *claimed) == "cancelled"
    assert source.calls == 0 and _ids(ds) == [1, 2]
    assert (await _fresh(db_session, Dataset, ds.id)).row_count == 2


async def test_permissions_are_checked_when_the_job_runs(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, ds, auth_headers["a"])).json()["id"]
    await db_session.execute(update(User).where(User.id == two_orgs["a"]["user"].id)
                             .values(is_active=False))
    await db_session.commit()
    assert await jobs.run_next(factory, "w1") == "failed"
    job = await _job(db_session, job_id)
    assert job.error_code == "not_allowed"
    assert source.calls == 0 and _ids(ds) == [1, 2]


async def test_a_dataset_deleted_while_queued_fails_the_job_plainly(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    job_id = (await _queue(client, ds, auth_headers["a"])).json()["id"]
    await db_session.delete(await _fresh(db_session, Dataset, ds.id))
    await db_session.commit()
    assert await jobs.run_next(factory, "w1") == "failed"
    job = await _job(db_session, job_id)
    assert job.error_code == "not_allowed"
    assert job.error == "This dataset no longer exists, or you may no longer refresh it"


async def test_what_cannot_be_refreshed_is_refused_at_once(
        client, db_session, two_orgs, auth_headers, tmp_path):
    org_id = two_orgs["a"]["org"].id
    upload = Dataset(name="Upload", filename=str(tmp_path / "u.csv"), org_id=org_id)
    db_session.add(upload)
    await db_session.commit()
    r = await _queue(client, upload, auth_headers["a"])
    assert r.status_code == 400
    assert r.json()["detail"] == "This dataset was not imported from a database connection"
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


async def test_a_schema_break_fails_the_job_with_the_mapping_and_the_map_retries_it(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, monkeypatch):
    org_id = two_orgs["a"]["org"].id
    ds = await _dataset(db_session, org_id, tmp_path)
    report = Report(name="R", org_id=org_id, dataset_id=ds.id)
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="P", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=page.id, widget_type="kpi", title="Latest",
                                config={"measure": "updated_at"}, layout={"x": 0, "y": 0, "w": 3, "h": 3}))
    await db_session.commit()
    renamed = Source([{"id": 1, "Updated At": 10}, {"id": 2, "Updated At": 20}, {"id": 3, "Updated At": 30}])
    monkeypatch.setattr("app.services.connections.import_to_dataframe", renamed)

    job_id = (await _queue(client, ds, auth_headers["a"])).json()["id"]
    assert await jobs.run_next(factory, "w1") == "failed"
    job = (await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers["a"])).json()
    assert job["error_code"] == "schema_break"
    assert job["error"].startswith("Not refreshed: the source no longer has 'updated_at'")
    assert job["result"]["missing"] == ["updated_at"]
    assert job["result"]["suggestions"] == {"updated_at": ["Updated At"]}
    assert job["result"]["available"] == ["id", "Updated At"]
    assert [d["kind"] for d in job["result"]["dependents"]["updated_at"]] == ["widget"]
    assert _ids(ds) == [1, 2]                                       # untouched

    r = await _queue(client, ds, auth_headers["a"], column_map={"Updated At": "updated_at"})
    assert r.status_code == 202
    assert await jobs.run_next(factory, "w1") == "succeeded"
    assert list(pd.read_csv(ds.filename).columns) == ["id", "updated_at"]
    assert _ids(ds) == [1, 2, 3]


# ── Following it from the page ───────────────────────────────────────────────

async def test_the_page_can_find_the_refresh_in_progress(
        client, db_session, two_orgs, auth_headers, tmp_path, factory, source):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    url = f"/api/v1/datasets/{ds.id}/refresh-jobs/active"
    assert (await client.get(url, headers=auth_headers["a"])).json() is None
    job_id = (await _queue(client, ds, auth_headers["a"])).json()["id"]
    got = (await client.get(url, headers=auth_headers["a"])).json()
    assert got["id"] == job_id and got["state"] == "queued"
    await jobs.run_next(factory, "w1")
    assert (await client.get(url, headers=auth_headers["a"])).json() is None
    # Another org's dataset is not there at all.
    assert (await client.get(url, headers=auth_headers["b"])).status_code == 404
