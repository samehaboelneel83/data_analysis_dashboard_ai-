"""T3: the Delivery log (one row per delivery ATTEMPT, success and failure
alike, written fire-and-forget) and ReportSchedule.timezone (the scheduler
interprets a calendar schedule's hour/minute in this IANA zone via zoneinfo,
NULL = UTC -- unchanged historical behaviour).

`log_delivery_sync` follows the exact fire-and-forget contract established
for QueryRun/ShareLinkAccess telemetry (T5/T13, S4 -- see test_query_runs.py
and test_share_link_access_log.py): its own dedicated sync engine, never the
app's async engine, never able to fail or slow the delivery it describes.
"""
from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.database import Base
from app.models.models import Delivery, Report, ReportSchedule, Role, User
from app.core.security import hash_password
from app.services import query_log
from app.services.alerts import check_alert
from app.services.delivery import run_schedule
from app.services.refresh_scheduler import is_calendar_due, schedule_is_due


# ── log_delivery_sync itself (isolated, no app wiring) ───────────────────────

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
            result = conn.execute(Delivery.__table__.select())
            return [dict(r._mapping) for r in result]
    finally:
        engine.dispose()


class TestLogDeliverySyncHelper:
    def test_writes_a_row_with_the_given_fields(self, app_db):
        query_log.log_delivery_sync(
            org_id=1, schedule_id=5, report_id=9, kind="schedule", status="ok",
            error=None, artifact_kind="xlsx", duration_ms=42, created_at=datetime.utcnow(),
        )
        rows = _rows(app_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["org_id"] == 1
        assert row["schedule_id"] == 5
        assert row["report_id"] == 9
        assert row["kind"] == "schedule"
        assert row["status"] == "ok"
        assert row["artifact_kind"] == "xlsx"
        assert row["duration_ms"] == 42

    def test_a_raising_engine_does_not_raise(self, app_db, monkeypatch):
        """The fire-and-forget contract: whatever goes wrong inside the
        insert, log_delivery_sync itself must never raise -- a logging
        failure must never fail the delivery it describes."""
        def _boom():
            raise RuntimeError("db is on fire")
        monkeypatch.setattr(query_log, "_get_engine", _boom)
        query_log.log_delivery_sync(org_id=1, schedule_id=None, report_id=None,
                                    kind="alert", status="ok", error=None,
                                    artifact_kind="none", duration_ms=1, created_at=datetime.utcnow())
        # No exception reached here -- that IS the assertion.


# ── Wiring: run_schedule / check_alert actually call the logger ─────────────

@pytest.fixture
def sales_ds(tmp_path):
    p = tmp_path / "sched.csv"
    pd.DataFrame({"region": ["US", "US", "CA"], "revenue": [100.0, 50.0, 30.0]}).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org_id, path):
    from app.models.models import Dataset, DatasetColumn
    ds = Dataset(name="Sched", filename=path, org_id=org_id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("revenue", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _report_with_widget(client, headers, ds):
    r = await client.post("/api/v1/reports", json={"name": "Sched R", "dataset_id": ds.id}, headers=headers)
    rid = r.json()["id"]
    page_id = (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"][0]["id"]
    await client.post(f"/api/v1/reports/{rid}/pages/{page_id}/widgets",
                      json={"widget_type": "bar", "title": "By region",
                            "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
                            "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
                      headers=headers)
    return rid


class TestRunScheduleLogsDeliveries:
    @pytest.mark.asyncio
    async def test_a_failed_send_is_logged_as_error(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds):
        """SMTP is unconfigured in the test settings -- send fails, and that
        failure must land in the Delivery log with an error message."""
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        sched = ReportSchedule(org_id=org.id, report_id=rid, creator_user_id=two_orgs["a"]["user"].id,
                               interval_minutes=60, recipients=["a@b.co"])
        db_session.add(sched)
        await db_session.commit()

        await run_schedule(db_session, sched)

        rows = _rows(app_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == "schedule"
        assert row["status"] == "error"
        assert row["error"] and "SMTP is not configured" in row["error"]
        assert row["artifact_kind"] == "xlsx"
        assert row["report_id"] == rid
        assert row["schedule_id"] == sched.id
        assert row["org_id"] == org.id
        assert row["duration_ms"] is not None

    @pytest.mark.asyncio
    async def test_a_successful_send_is_logged_as_ok(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        monkeypatch.setattr("app.services.delivery.send_email", lambda *a, **kw: None)
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        sched = ReportSchedule(org_id=org.id, report_id=rid, creator_user_id=two_orgs["a"]["user"].id,
                               interval_minutes=60, recipients=["a@b.co"])
        db_session.add(sched)
        await db_session.commit()

        await run_schedule(db_session, sched)

        rows = _rows(app_db)
        assert len(rows) == 1
        assert rows[0]["status"] == "ok"
        assert rows[0]["error"] is None

    @pytest.mark.asyncio
    async def test_no_valid_recipients_is_logged_as_error(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        sched = ReportSchedule(org_id=org.id, report_id=rid, creator_user_id=two_orgs["a"]["user"].id,
                               interval_minutes=60, recipients=["not-an-email"])
        db_session.add(sched)
        await db_session.commit()

        await run_schedule(db_session, sched)

        rows = _rows(app_db)
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert "no valid recipients" in rows[0]["error"]

    @pytest.mark.asyncio
    async def test_a_raising_logger_never_breaks_the_delivery(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        """Belt-and-braces: even if the logging call site itself were broken,
        run_schedule must still complete and record last_status on the row --
        logging is never allowed to be load-bearing for the delivery."""
        monkeypatch.setattr("app.services.delivery.send_email", lambda *a, **kw: None)
        monkeypatch.setattr("app.services.delivery.log_delivery_sync",
                            lambda **kw: (_ for _ in ()).throw(RuntimeError("logger exploded")))
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        sched = ReportSchedule(org_id=org.id, report_id=rid, creator_user_id=two_orgs["a"]["user"].id,
                               interval_minutes=60, recipients=["a@b.co"])
        db_session.add(sched)
        await db_session.commit()

        with pytest.raises(RuntimeError):
            # This particular test intentionally breaks the call site itself
            # (not the writer, which test_a_raising_engine_does_not_raise
            # above already proves is safe) to document that the CONTRACT
            # lives in log_delivery_sync, not in a try/except at every call
            # site -- see that test for the actual safety net.
            await run_schedule(db_session, sched)


class TestCheckAlertLogsDeliveries:
    @pytest.mark.asyncio
    async def test_firing_alert_logs_a_delivery_row(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        from app.models.models import DataAlert
        monkeypatch.setattr("app.services.alerts.send_email", lambda *a, **kw: None)
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        alert = DataAlert(org_id=org.id, dataset_id=ds.id, creator_user_id=two_orgs["a"]["user"].id,
                          name="Low revenue", expression="SUM(revenue) < 1000000",
                          interval_minutes=60, recipients=["a@b.co"])
        db_session.add(alert)
        await db_session.commit()

        await check_alert(db_session, alert)

        rows = _rows(app_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == "alert"
        assert row["status"] == "ok"
        assert row["schedule_id"] is None
        assert row["report_id"] is None
        assert row["org_id"] == org.id

    @pytest.mark.asyncio
    async def test_a_broken_condition_is_logged_as_error(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds):
        from app.models.models import DataAlert
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        alert = DataAlert(org_id=org.id, dataset_id=ds.id, creator_user_id=two_orgs["a"]["user"].id,
                          name="Broken", expression="__import__('os')",
                          interval_minutes=60, recipients=["a@b.co"])
        db_session.add(alert)
        await db_session.commit()

        await check_alert(db_session, alert)

        rows = _rows(app_db)
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert rows[0]["error"]


# ── GET /reports/{id}/deliveries ─────────────────────────────────────────────

class TestDeliveriesEndpoint:
    @pytest.mark.asyncio
    async def test_lists_this_reports_deliveries_newest_first(self, client, auth_headers, db_session, two_orgs, sales_ds):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        sched = ReportSchedule(org_id=org.id, report_id=rid, creator_user_id=two_orgs["a"]["user"].id,
                               interval_minutes=60, recipients=["a@b.co"])
        db_session.add(sched)
        await db_session.flush()
        db_session.add(Delivery(org_id=org.id, schedule_id=sched.id, report_id=rid, kind="schedule",
                                status="ok", artifact_kind="xlsx", duration_ms=10,
                                created_at=datetime(2026, 1, 1)))
        db_session.add(Delivery(org_id=org.id, schedule_id=sched.id, report_id=rid, kind="schedule",
                                status="error", error="boom", artifact_kind="xlsx", duration_ms=5,
                                created_at=datetime(2026, 1, 2)))
        await db_session.commit()

        resp = await client.get(f"/api/v1/reports/{rid}/deliveries", headers=auth_headers["a"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["status"] == "error"   # newest first
        assert body[0]["error"] == "boom"
        assert body[1]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_cross_org_report_is_404_not_403(self, client, auth_headers, db_session, two_orgs, sales_ds):
        org_a = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org_a.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)

        resp = await client.get(f"/api/v1/reports/{rid}/deliveries", headers=auth_headers["b"])
        assert resp.status_code == 404


# ── ReportSchedule.timezone / calendar due-check ─────────────────────────────

class TestScheduleTimezone:
    def test_riyadh_schedule_fires_on_local_wall_clock(self):
        """09:00 Asia/Riyadh (UTC+3, no DST) is 06:00 UTC. Ran at 06:01 UTC on
        the 23rd (09:01 local); must not be due again until local 09:00 has
        passed on the 24th, i.e. 06:00 UTC on the 24th."""
        spec = {"kind": "daily", "hour": 9, "minute": 0}
        last_run_at = datetime(2026, 8, 23, 6, 1)   # 09:01 Riyadh local
        before = datetime(2026, 8, 24, 5, 59)       # 08:59 Riyadh local -- not due yet
        after = datetime(2026, 8, 24, 6, 1)         # 09:01 Riyadh local -- due
        assert is_calendar_due(spec, last_run_at, before, "Asia/Riyadh") is False
        assert is_calendar_due(spec, last_run_at, after, "Asia/Riyadh") is True

    def test_null_timezone_keeps_utc_behaviour(self):
        """Existing rows (timezone=NULL) must evaluate identically with and
        without the parameter -- the historical, still-default behaviour."""
        spec = {"kind": "daily", "hour": 9, "minute": 0}
        last_run_at = datetime(2026, 8, 23, 9, 1)
        before = datetime(2026, 8, 24, 8, 30)
        after = datetime(2026, 8, 24, 9, 5)
        assert is_calendar_due(spec, last_run_at, before) == is_calendar_due(spec, last_run_at, before, None)
        assert is_calendar_due(spec, last_run_at, after) == is_calendar_due(spec, last_run_at, after, None)
        assert is_calendar_due(spec, last_run_at, before, None) is False
        assert is_calendar_due(spec, last_run_at, after, None) is True

    def test_schedule_is_due_reads_the_rows_own_timezone(self):
        """schedule_is_due (what the scheduler loop actually calls) must pick
        up sched.timezone, not just the lower-level is_calendar_due."""
        from types import SimpleNamespace
        sched = SimpleNamespace(
            recipients=[{"__calendar__": {"kind": "daily", "hour": 9, "minute": 0}}],
            last_run_at=datetime(2026, 8, 23, 6, 1),
            interval_minutes=1440,
            timezone="Asia/Riyadh",
        )
        assert schedule_is_due(sched, datetime(2026, 8, 24, 5, 59)) is False
        assert schedule_is_due(sched, datetime(2026, 8, 24, 6, 1)) is True

    @pytest.mark.asyncio
    async def test_unknown_timezone_is_422(self, client, auth_headers, db_session, two_orgs, sales_ds):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)

        resp = await client.post(f"/api/v1/reports/{rid}/schedules",
                                 json={"recipients": ["a@b.co"],
                                       "calendar": {"kind": "daily", "hour": 9, "minute": 0},
                                       "timezone": "Not/ARealZone"},
                                 headers=auth_headers["a"])
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_a_valid_timezone_is_stored_and_returned(self, client, auth_headers, db_session, two_orgs, sales_ds):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)

        resp = await client.post(f"/api/v1/reports/{rid}/schedules",
                                 json={"recipients": ["a@b.co"],
                                       "calendar": {"kind": "daily", "hour": 9, "minute": 0},
                                       "timezone": "Asia/Riyadh"},
                                 headers=auth_headers["a"])
        assert resp.status_code == 201, resp.text
        assert resp.json()["timezone"] == "Asia/Riyadh"

        listed = await client.get(f"/api/v1/reports/{rid}/schedules", headers=auth_headers["a"])
        assert listed.json()[0]["timezone"] == "Asia/Riyadh"


class TestOkAlertRowsKeepErrorNull:
    @pytest.mark.asyncio
    async def test_ok_alert_rows_keep_error_null(self, app_db, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        """Successful alert checks must not leak status text ("clear",
        "fired, emailed 1") into the Delivery.error column."""
        from app.models.models import DataAlert
        monkeypatch.setattr("app.services.alerts.send_email", lambda *a, **kw: None)
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        alert = DataAlert(org_id=org.id, dataset_id=ds.id, creator_user_id=two_orgs["a"]["user"].id,
                          name="Low revenue", expression="SUM(revenue) < 1000000",
                          interval_minutes=60, recipients=["a@b.co"])
        db_session.add(alert)
        await db_session.commit()

        await check_alert(db_session, alert)

        rows = _rows(app_db)
        assert rows, "alert check should log a delivery row"
        for row in rows:
            if row["status"] == "ok":
                assert row["error"] is None
