"""A slow analysis as a background job (docs/discovery/PLAN.md §X-4)."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import Job
from app.services import analysis_jobs, jobs
from tests.test_discovery_endpoint import _world, data_csv  # noqa: F401  (fixture)


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def test_the_threshold_is_a_setting_an_administrator_can_change(monkeypatch):
    from app.core.config import settings
    from app.services import app_settings
    assert app_settings.BY_KEY["analysis_background_rows"].editable
    monkeypatch.setattr(settings, "analysis_background_rows", 5_000)
    assert analysis_jobs.should_queue("segment", 5_000, "auto") is True
    monkeypatch.setattr(settings, "analysis_background_rows", 0)                    # 0: never by size
    assert analysis_jobs.should_queue("segment", 10**9, "auto") is False
    assert analysis_jobs.should_queue("segment", 10, True) is True                  # still on request


def test_only_a_slow_analysis_on_a_large_table_is_queued_by_itself():
    big, small = analysis_jobs.background_rows(), analysis_jobs.background_rows() - 1
    assert analysis_jobs.is_slow("automated_prediction") and analysis_jobs.is_slow("segment")
    assert not analysis_jobs.is_slow("explain_change") and not analysis_jobs.is_slow("no_such_analysis")
    assert analysis_jobs.should_queue("segment", big, "auto") is True
    assert analysis_jobs.should_queue("segment", small, "auto") is False          # small table: in the request
    assert analysis_jobs.should_queue("explain_change", big * 10, "auto") is False  # quick analysis: in the request
    assert analysis_jobs.should_queue("explain_change", 10, True) is True          # asked for outright
    assert analysis_jobs.should_queue("segment", big, None) is False               # not asked: as it always was
    assert analysis_jobs.should_queue("segment", big, False) is False


async def test_a_queued_analysis_gives_the_same_answer_the_request_does(client, two_orgs, db_session, data_csv, factory):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    body = {"name": "correlation_test", "params": {"col_a": "v1", "col_b": "v2"}}
    direct = (await client.post(f"/api/v1/datasets/{ds.id}/analysis/run", json=body, headers=headers)).json()
    assert "job_id" not in direct and direct["result"]

    queued = await client.post(f"/api/v1/datasets/{ds.id}/analysis/run", json={**body, "background": True}, headers=headers)
    assert queued.status_code == 200, queued.text
    job_id = queued.json()["job_id"]
    assert queued.json()["result_kind"] == direct["result_kind"]
    assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
    got = (await client.get(f"/api/v1/jobs/{job_id}", headers=headers)).json()
    assert got["state"] == "succeeded" and got["result"]["analysis"] == "correlation_test"
    assert got["result"]["result"] == direct["result"]


async def test_auto_runs_a_quick_analysis_in_the_request(client, two_orgs, db_session, data_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    r = await client.post(f"/api/v1/datasets/{ds.id}/analysis/run", headers=headers,
                          json={"name": "correlation_test", "params": {"col_a": "v1", "col_b": "v2"}, "background": "auto"})
    assert r.status_code == 200 and "job_id" not in r.json() and r.json()["result"]


async def test_a_job_refuses_in_the_analysis_own_words_and_never_reads_a_hidden_column(
        client, two_orgs, db_session, data_csv, factory):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv, deny=["secret"])
    # A column the reader may not see: refused when the job runs, as the request refuses it.
    q = await client.post(f"/api/v1/datasets/{ds.id}/analysis/run", headers=headers,
                          json={"name": "correlation_test", "params": {"col_a": "v1", "col_b": "secret"}, "background": True})
    assert await jobs.run_next(factory, "w1") == jobs.FAILED
    job = await db_session.get(Job, q.json()["job_id"])
    await db_session.refresh(job)
    assert job.state == "failed" and job.error and "0." not in (job.error or "")       # a reason, no figure
    # The analysis' own refusal.
    q = await client.post(f"/api/v1/datasets/{ds.id}/analysis/run", headers=headers,
                          json={"name": "compare_two_groups", "params": {"group_col": "g", "outcome": "v1"}, "background": True})
    assert await jobs.run_next(factory, "w1") == jobs.FAILED
    job = await db_session.get(Job, q.json()["job_id"])
    await db_session.refresh(job)
    assert "exactly two groups" in job.error


async def test_someone_elses_dataset_cannot_be_queued(client, two_orgs, db_session, data_csv):
    ds, _headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    from app.core.security import create_access_token
    other = two_orgs["b"]
    outsider = {"Authorization": f"Bearer {create_access_token(other['admin'].id, other['org'].id)}"} if "admin" in other else None
    if outsider is None:
        pytest.skip("no second-org user in this fixture")
    r = await client.post(f"/api/v1/datasets/{ds.id}/analysis/run", headers=outsider,
                          json={"name": "correlation_test", "params": {"col_a": "v1", "col_b": "v2"}, "background": True})
    assert r.status_code in (403, 404)
