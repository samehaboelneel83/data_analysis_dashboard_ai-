"""The Monitoring read API: /admin/monitoring/jobs and /deliveries.

Both endpoints only AGGREGATE state other features already write (schedules,
refresh timestamps, the delivery log), so what these tests pin is the
aggregation itself: every job kind appears in the one normalised shape, and
nothing from another org ever does. Admin gating is not re-tested here --
test_admin_endpoints_require_admin.py sweeps every /api/v1/admin route
parametrically, and these two are registered under that prefix.
"""
from datetime import datetime, timezone

from app.models.models import (DataAlert, Dataflow, Dataset, Delivery, Report,
                               ReportSchedule)


async def _seed_world(db_session, two_orgs):
    """One of each scheduled thing in org A, plus an org-B twin of each --
    the twin is what makes the isolation assertions non-vacuous."""
    a, b = two_orgs["a"], two_orgs["b"]
    rows = {}
    for key, org, user in (("a", a["org"], a["user"]), ("b", b["org"], b["user"])):
        ds = Dataset(name=f"ds-{key}", org_id=org.id, refresh_interval_minutes=60,
                     last_refreshed_at=datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc))
        flow = Dataflow(name=f"flow-{key}", org_id=org.id, steps=[],
                        refresh_interval_minutes=30, last_run_status="ok",
                        created_by=user.id)
        report = Report(name=f"report-{key}")
        db_session.add_all([ds, flow, report])
        await db_session.flush()
        sched = ReportSchedule(org_id=org.id, report_id=report.id,
                               creator_user_id=user.id, interval_minutes=1440,
                               recipients=[], subject=None, last_status="sent to 2")
        alert = DataAlert(org_id=org.id, dataset_id=ds.id, creator_user_id=user.id,
                          name=f"alert-{key}", expression="SUM(x) < 1",
                          interval_minutes=60, recipients=[])
        db_session.add_all([sched, alert])
        await db_session.flush()
        delivery = Delivery(org_id=org.id, schedule_id=sched.id, report_id=report.id,
                            kind="schedule", status="error", error="smtp down",
                            artifact_kind="pdf", duration_ms=too_ms(key))
        db_session.add(delivery)
        rows[key] = {"ds": ds, "flow": flow, "report": report,
                     "sched": sched, "alert": alert}
    await db_session.commit()
    return rows


def too_ms(key: str) -> int:
    return 100 if key == "a" else 200


class TestJobs:
    async def test_every_scheduled_kind_appears_once_in_the_uniform_shape(
            self, client, db_session, two_orgs, auth_headers):
        seeded = await _seed_world(db_session, two_orgs)
        resp = await client.get("/api/v1/admin/monitoring/jobs", headers=auth_headers["a"])
        assert resp.status_code == 200
        jobs = resp.json()
        by_kind = {j["kind"]: j for j in jobs}
        assert set(by_kind) == {"dataset_refresh", "dataflow", "report_schedule", "alert"}
        assert len(jobs) == 4

        assert by_kind["dataset_refresh"]["name"] == "ds-a"
        assert by_kind["dataset_refresh"]["interval_minutes"] == 60
        assert by_kind["dataset_refresh"]["last_run_at"] is not None
        assert by_kind["dataflow"]["status"] == "ok"
        # A schedule with no subject borrows its report's name -- a row named
        # "None" answers nothing.
        assert by_kind["report_schedule"]["name"] == "report-a"
        assert by_kind["report_schedule"]["report_id"] == seeded["a"]["report"].id
        # An alert's dataset_id rides along so the page can link to the data
        # it watches (the row's own id is the alert's, not the dataset's).
        assert by_kind["alert"]["dataset_id"] == seeded["a"]["ds"].id

    async def test_an_unscheduled_dataset_is_not_a_job(
            self, client, db_session, two_orgs, auth_headers):
        db_session.add(Dataset(name="manual", org_id=two_orgs["a"]["org"].id))
        await db_session.commit()
        resp = await client.get("/api/v1/admin/monitoring/jobs", headers=auth_headers["a"])
        assert resp.json() == []

    async def test_org_b_admin_sees_only_org_b_jobs(
            self, client, db_session, two_orgs, auth_headers):
        await _seed_world(db_session, two_orgs)
        resp = await client.get("/api/v1/admin/monitoring/jobs", headers=auth_headers["b"])
        names = {j["name"] for j in resp.json()}
        assert names == {"ds-b", "flow-b", "report-b", "alert-b"}


class TestDeliveries:
    async def test_the_org_log_carries_the_report_name_and_the_error(
            self, client, db_session, two_orgs, auth_headers):
        await _seed_world(db_session, two_orgs)
        resp = await client.get("/api/v1/admin/monitoring/deliveries", headers=auth_headers["a"])
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["report_name"] == "report-a"
        assert row["status"] == "error"
        assert row["error"] == "smtp down"
        assert row["duration_ms"] == 100

    async def test_an_alert_delivery_with_no_report_still_lists(
            self, client, db_session, two_orgs, auth_headers):
        # kind="alert" rows have NULL report and schedule FKs -- an INNER join
        # on reports would silently drop exactly the failures alerts produce.
        db_session.add(Delivery(org_id=two_orgs["a"]["org"].id, kind="alert",
                                status="ok", artifact_kind="none"))
        await db_session.commit()
        resp = await client.get("/api/v1/admin/monitoring/deliveries", headers=auth_headers["a"])
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["report_name"] is None
        assert rows[0]["kind"] == "alert"

    async def test_org_isolation(self, client, db_session, two_orgs, auth_headers):
        await _seed_world(db_session, two_orgs)
        resp = await client.get("/api/v1/admin/monitoring/deliveries", headers=auth_headers["b"])
        assert [r["report_name"] for r in resp.json()] == ["report-b"]
