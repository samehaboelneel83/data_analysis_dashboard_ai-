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


class TestRefreshRuns:
    """Pipeline plan, phase 1: a dataset's job row reports its last attempt,
    and /monitoring/refresh-runs lists the history, org-scoped."""

    async def _runs(self, db_session, two_orgs):
        from app.models.models import RefreshRun, ScheduleFailure
        seeded = await _seed_world(db_session, two_orgs)
        a_ds, b_ds = seeded["a"]["ds"], seeded["b"]["ds"]
        db_session.add_all([
            RefreshRun(org_id=two_orgs["a"]["org"].id, kind="dataset", item_id=a_ds.id,
                       trigger="schedule", status="ok", rows=10),
            RefreshRun(org_id=two_orgs["a"]["org"].id, kind="dataset", item_id=a_ds.id,
                       trigger="schedule", status="failed", error="source down",
                       error_code="refresh_failed"),
            RefreshRun(org_id=two_orgs["b"]["org"].id, kind="dataset", item_id=b_ds.id,
                       trigger="manual", status="failed", error="b's secret error"),
            ScheduleFailure(kind="dataset", item_id=a_ds.id, attempts=1,
                            next_attempt_at=datetime(2026, 10, 3, 9, 5, tzinfo=timezone.utc),
                            last_error="source down"),
        ])
        await db_session.commit()
        return seeded

    async def test_a_dataset_job_shows_its_last_attempt(self, client, db_session, two_orgs, auth_headers):
        seeded = await self._runs(db_session, two_orgs)
        jobs = (await client.get("/api/v1/admin/monitoring/jobs", headers=auth_headers["a"])).json()
        [row] = [j for j in jobs if j["kind"] == "dataset_refresh"]
        assert row["id"] == seeded["a"]["ds"].id
        assert row["status"] == "failed" and row["error"] == "source down"
        assert row["next_retry_at"] is not None
        assert row["last_refreshed_at"] is not None

    async def test_the_history_is_newest_first_and_org_scoped(self, client, db_session, two_orgs, auth_headers):
        await self._runs(db_session, two_orgs)
        runs = (await client.get("/api/v1/admin/monitoring/refresh-runs",
                                 headers=auth_headers["a"])).json()
        assert [r["status"] for r in runs] == ["failed", "ok"]
        assert runs[0]["name"] == "ds-a"
        assert all("secret" not in (r["error"] or "") for r in runs)

    async def test_failed_only(self, client, db_session, two_orgs, auth_headers):
        await self._runs(db_session, two_orgs)
        runs = (await client.get("/api/v1/admin/monitoring/refresh-runs",
                                 params={"status": "failed"}, headers=auth_headers["a"])).json()
        assert [r["error_code"] for r in runs] == ["refresh_failed"]


class TestAutomationRunsAndChecks:
    """AD-17: "Everything that runs" includes automated analyses, and the
    refresh history says how each run's checks went."""

    async def test_automation_runs_are_listed_for_their_org_only(self, client, db_session, two_orgs, auth_headers):
        from app.services import automation_runner as runner
        seeded = await _seed_world(db_session, two_orgs)
        mine = await runner.create_run(db_session, org_id=two_orgs["a"]["org"].id,
                                       created_by=two_orgs["a"]["user"].id, trigger="manual",
                                       subject_type="dataset", subject_id=seeded["a"]["ds"].id)
        await runner.create_run(db_session, org_id=two_orgs["b"]["org"].id,
                                created_by=two_orgs["b"]["user"].id, trigger="manual",
                                subject_type="dataset", subject_id=seeded["b"]["ds"].id)
        r = await client.get("/api/v1/admin/monitoring/automation-runs", headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        rows = r.json()
        assert [x["id"] for x in rows] == [mine.id]
        assert rows[0]["status"] == "pending" and rows[0]["dataset_name"] == "ds-a"
        assert rows[0]["step"] == "Profile the data"
        assert "started_at" in rows[0] and "finished_at" in rows[0] and "error" in rows[0]

    async def test_a_refresh_run_carries_a_checks_summary(self, client, db_session, two_orgs, auth_headers):
        from app.models.models import RefreshRun
        seeded = await _seed_world(db_session, two_orgs)
        db_session.add(RefreshRun(org_id=two_orgs["a"]["org"].id, kind="dataset", item_id=seeded["a"]["ds"].id,
                                  trigger="schedule", status="ok", rows=5, checks=[
                                      {"id": 1, "severity": "block", "passed": True},
                                      {"id": 2, "severity": "warn", "passed": True},
                                      {"id": 3, "severity": "warn", "passed": False}]))
        await db_session.commit()
        runs = (await client.get("/api/v1/admin/monitoring/refresh-runs", headers=auth_headers["a"])).json()
        assert runs[0]["checks_summary"] == {"pass": 2, "warn": 1, "fail": 0}


class TestActivityPaging:
    """AD-19: the Activity log pages and filters on the server."""

    async def _log(self, db_session, two_orgs, n=5):
        from app.models.models import AuditLogEntry
        org = two_orgs["a"]["org"].id
        for i in range(n):
            db_session.add(AuditLogEntry(org_id=org, user_email="x@example.com" if i % 2 else "y@example.com",
                                         action="report.create" if i % 2 else "dataset.upload",
                                         created_at=datetime(2026, 9, 1 + i, tzinfo=timezone.utc)))
        db_session.add(AuditLogEntry(org_id=two_orgs["b"]["org"].id, action="report.create"))
        await db_session.commit()

    async def test_before_id_pages_without_overlap(self, client, db_session, two_orgs, auth_headers):
        await self._log(db_session, two_orgs)
        url = "/api/v1/admin/audit-log"
        first = (await client.get(url, params={"limit": 2}, headers=auth_headers["a"])).json()
        second = (await client.get(url, params={"limit": 2, "before_id": first[-1]["id"]},
                                   headers=auth_headers["a"])).json()
        rest = (await client.get(url, params={"limit": 10, "before_id": second[-1]["id"]},
                                 headers=auth_headers["a"])).json()
        ids = [r["id"] for r in first + second + rest]
        assert len(ids) == 5 and len(set(ids)) == 5 and ids == sorted(ids, reverse=True)

    async def test_filters(self, client, db_session, two_orgs, auth_headers):
        await self._log(db_session, two_orgs)
        url = "/api/v1/admin/audit-log"
        by_action = (await client.get(url, params={"action": "report.create"}, headers=auth_headers["a"])).json()
        assert len(by_action) == 2 and {r["action"] for r in by_action} == {"report.create"}
        by_user = (await client.get(url, params={"user_email": "y@example.com"}, headers=auth_headers["a"])).json()
        assert len(by_user) == 3
        dated = (await client.get(url, params={"since": "2026-09-02", "until": "2026-09-03T23:59:59"},
                                  headers=auth_headers["a"])).json()
        assert len(dated) == 2
