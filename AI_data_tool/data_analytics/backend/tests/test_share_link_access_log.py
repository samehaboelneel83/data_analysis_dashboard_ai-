"""S4: share-link access log. `log_share_access_sync` follows the exact
fire-and-forget contract established for QueryRun telemetry (T5/T13, see
test_query_runs.py) -- its own dedicated sync engine, never the app's async
engine, never able to fail or slow the render it describes."""
import hashlib

import pytest
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.database import Base
from app.models.models import ShareLinkAccess
from app.services import query_log


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    """Same convention as test_query_runs.py's app_db: a real file-backed
    sqlite database sharing Base.metadata, pointed at via
    settings.database_url (what query_log's writer actually reads)."""
    db_path = tmp_path / "app.db"
    setup_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(setup_engine)
    setup_engine.dispose()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(query_log, "_sync_engine", None)
    yield db_path
    monkeypatch.setattr(query_log, "_sync_engine", None)


def _rows(db_path):
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            result = conn.execute(ShareLinkAccess.__table__.select())
            return [dict(r._mapping) for r in result]
    finally:
        engine.dispose()


def test_log_share_access_sync_writes_a_row(app_db):
    query_log.log_share_access_sync(
        share_link_id=1, viewer_user_id=None,
        ip_hash=hashlib.sha256(b"127.0.0.1").hexdigest(), user_agent="pytest-agent",
    )
    rows = _rows(app_db)
    assert len(rows) == 1
    assert rows[0]["share_link_id"] == 1
    assert rows[0]["viewer_user_id"] is None
    assert rows[0]["user_agent"] == "pytest-agent"
    assert len(rows[0]["ip_hash"]) == 64  # sha256 hex digest -- never a raw IP


def test_viewer_user_id_recorded_when_an_in_org_viewer_renders(app_db):
    query_log.log_share_access_sync(share_link_id=2, viewer_user_id=42, ip_hash=None, user_agent=None)
    rows = _rows(app_db)
    assert rows[0]["viewer_user_id"] == 42


def test_a_raising_logger_does_not_raise(app_db, monkeypatch):
    def _boom():
        raise RuntimeError("db is on fire")
    monkeypatch.setattr(query_log, "_get_engine", _boom)
    query_log.log_share_access_sync(share_link_id=1, viewer_user_id=None, ip_hash=None, user_agent=None)
    # No exception reached here -- that IS the assertion.


def test_one_visit_is_one_row_however_often_the_page_fetches(app_db):
    """The owner reads these rows as a count of VISITS.

    One open of a share link fired the render route twice (React StrictMode
    double-invokes effects in development, and a remount does it in any build),
    so a link opened once reported "2 views" -- a number that overstates the
    reach of everything anyone shares. Identical repeats inside the dedupe
    window are one visit.
    """
    for _ in range(5):
        query_log.log_share_access_sync(share_link_id=9, viewer_user_id=None,
                                        ip_hash=None, user_agent=None)
    assert len(_rows(app_db)) == 1


def test_different_visitors_are_never_collapsed(app_db):
    """Only an IDENTICAL repeat is a duplicate: two people reading the same
    link at the same moment are two views, and so is a signed-in colleague
    opening it beside an anonymous visitor."""
    query_log.log_share_access_sync(share_link_id=9, viewer_user_id=None,
                                    ip_hash="aaa", user_agent="Firefox")
    query_log.log_share_access_sync(share_link_id=9, viewer_user_id=None,
                                    ip_hash="bbb", user_agent="Firefox")
    query_log.log_share_access_sync(share_link_id=9, viewer_user_id=7,
                                    ip_hash="aaa", user_agent="Firefox")
    query_log.log_share_access_sync(share_link_id=10, viewer_user_id=None,
                                    ip_hash="aaa", user_agent="Firefox")
    assert len(_rows(app_db)) == 4


def test_a_later_visit_still_counts(app_db, monkeypatch):
    """A reload a minute later is a real second visit -- the window is about
    one page load fetching twice, not about rate-limiting a reader."""
    query_log.log_share_access_sync(share_link_id=9, viewer_user_id=None,
                                    ip_hash="aaa", user_agent="Firefox")
    monkeypatch.setattr(query_log, "_SHARE_ACCESS_DEDUPE_S", 0)
    query_log.log_share_access_sync(share_link_id=9, viewer_user_id=None,
                                    ip_hash="aaa", user_agent="Firefox")
    assert len(_rows(app_db)) == 2


@pytest.mark.asyncio
async def test_guest_render_calls_the_access_logger(client, auth_headers, db_session, two_orgs, monkeypatch):
    """Wiring test: GET /shared/{token} (the guest render) actually calls the
    logger with this link's id -- not just that the logger itself works in
    isolation (covered above)."""
    from app.models.models import Dataset, DatasetColumn, Report, ReportPage
    from app.routers import shared as shared_router

    org = two_orgs["a"]["org"]
    ds = Dataset(name="S", filename="x.csv", org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    db_session.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"))
    r = Report(name="R", dataset_id=ds.id, org_id=org.id)
    db_session.add(r)
    await db_session.flush()
    db_session.add(ReportPage(report_id=r.id, name="P1", position=0))
    await db_session.commit()

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]

    calls = []
    monkeypatch.setattr(shared_router, "_log_access", lambda link, viewer, request: calls.append(link.id))

    resp = await client.get(f"/api/v1/shared/{token}")
    assert resp.status_code == 200
    assert len(calls) == 1
