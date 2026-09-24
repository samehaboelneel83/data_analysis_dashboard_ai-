"""Scheduled deliveries and data alerts.

The security spine of both: a run with no viewer resolves row-level security AS THE
CREATOR. "No user at the keyboard" must never degrade to "no RLS".
"""
import io

import pandas as pd
import pytest
from sqlalchemy import text as sa_text
from sqlalchemy import select

from app.models.models import DataAlert, Dataset, DatasetColumn, ReportSchedule, Role, RowSecurityRule, User
from app.core.security import hash_password
from app.services.alerts import check_alert, condition_holds
from app.services.delivery import build_digest, run_schedule, valid_recipients


@pytest.fixture
def sales_ds(tmp_path):
    p = tmp_path / "sched.csv"
    pd.DataFrame({
        "region": ["US", "US", "CA"],
        "revenue": [100.0, 50.0, 30.0],
    }).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org_id, path):
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


class TestRecipients:
    def test_only_plausible_emails_survive(self):
        assert valid_recipients(["a@b.co", "nope", "", None, "x@y.z"]) == ["a@b.co", "x@y.z"]


class TestDigest:
    @pytest.mark.asyncio
    async def test_digest_holds_one_sheet_per_data_widget(self, client, auth_headers, db_session, two_orgs, sales_ds):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        from app.models.models import Report
        report = await db_session.get(Report, rid)
        creator = two_orgs["a"]["user"]

        payload, sheets = await build_digest(db_session, report, creator)
        assert sheets == 1
        book = pd.read_excel(io.BytesIO(payload), sheet_name="By region")
        assert {r["name"]: r["value"] for _, r in book.iterrows()} == {"US": 150.0, "CA": 30.0}

    @pytest.mark.asyncio
    async def test_digest_applies_the_creators_row_level_security(self, client, auth_headers, db_session, two_orgs, sales_ds):
        """THE case this design exists for: a schedule made by a CA-restricted user
        must email the CA slice, not the whole table."""
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)

        role = Role(org_id=org.id, name="CA sched", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'CA'"))
        restricted = User(org_id=org.id, role_id=role.id, email="sched@example.com",
                          password_hash=hash_password("pw"))
        db_session.add(restricted)
        await db_session.commit()

        from app.models.models import Report
        report = await db_session.get(Report, rid)
        payload, _ = await build_digest(db_session, report, restricted)
        book = pd.read_excel(io.BytesIO(payload), sheet_name="By region")
        assert set(book["name"]) == {"CA"}, "creator RLS did not reach the digest"


class TestRunSchedule:
    @pytest.mark.asyncio
    async def test_unconfigured_smtp_is_recorded_not_raised(self, client, auth_headers, db_session, two_orgs, sales_ds):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        r = await client.post(f"/api/v1/reports/{rid}/schedules",
                              json={"interval_minutes": 60, "recipients": ["a@b.co"]},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        run = await client.post(f"/api/v1/reports/{rid}/schedules/{r.json()['id']}/run-now",
                                headers=auth_headers["a"])
        assert run.status_code == 200
        assert "SMTP is not configured" in run.json()["last_status"]

    @pytest.mark.asyncio
    async def test_a_deleted_creator_disables_the_schedule(self, client, auth_headers, db_session, two_orgs, sales_ds):
        """Falling back to unfiltered data when the identity vanishes would be the
        exact leak the creator identity exists to prevent."""
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)

        role = Role(org_id=org.id, name="tmp", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        temp = User(org_id=org.id, role_id=role.id, email="tmp@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(temp)
        await db_session.flush()
        sched = ReportSchedule(org_id=org.id, report_id=rid, creator_user_id=temp.id,
                               interval_minutes=60, recipients=["a@b.co"])
        db_session.add(sched)
        await db_session.commit()

        # Manufacture the orphan DELIBERATELY. creator_user_id is ON DELETE
        # CASCADE, so deleting the user normally takes the schedule with it --
        # and the test database now enforces foreign keys, matching Postgres.
        # But the scenario this guards is real: a soft delete, a manual row
        # removal, or a future schema change that drops the CASCADE all leave a
        # schedule whose creator is gone. The runtime check in run_schedule is
        # defence in depth for exactly that, so the orphan is created by
        # suspending the constraint for one statement rather than by relying on
        # it being off everywhere.
        await db_session.execute(sa_text("PRAGMA foreign_keys=OFF"))
        await db_session.execute(
            sa_text("DELETE FROM users WHERE id = :uid"), {"uid": temp.id})
        await db_session.execute(sa_text("PRAGMA foreign_keys=ON"))
        await db_session.commit()
        # The row is gone from the database, but the session's identity map still
        # holds the User object -- and run_schedule looks the creator up with
        # db.get, which answers from that map without a query. Expire it so the
        # lookup actually goes to the database and sees the absence.
        db_session.expunge(temp)

        # Run the schedule with its creator gone: it must disable itself, never
        # fall back to unfiltered data.
        await run_schedule(db_session, sched)
        assert "disabled" in (sched.last_status or "")

    @pytest.mark.asyncio
    async def test_validation_rejects_junk(self, client, auth_headers, db_session, two_orgs, sales_ds):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        assert (await client.post(f"/api/v1/reports/{rid}/schedules",
                                  json={"interval_minutes": 5, "recipients": ["a@b.co"]},
                                  headers=auth_headers["a"])).status_code == 400
        assert (await client.post(f"/api/v1/reports/{rid}/schedules",
                                  json={"interval_minutes": 60, "recipients": ["not-an-email"]},
                                  headers=auth_headers["a"])).status_code == 400

    @pytest.mark.asyncio
    async def test_calendar_schedule_round_trips(self, client, auth_headers, db_session, two_orgs, sales_ds):
        """A daily-at-09:00 schedule stores its spec as the reserved recipients
        entry, surfaces it as `calendar`, and never leaks the dict as an address."""
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        r = await client.post(f"/api/v1/reports/{rid}/schedules",
                              json={"recipients": ["a@b.co"],
                                    "calendar": {"kind": "daily", "hour": 9, "minute": 0}},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["calendar"] == {"kind": "daily", "hour": 9, "minute": 0}
        assert body["recipients"] == ["a@b.co"]
        assert body["interval_minutes"] == 24 * 60  # period bound backs the SQL scan filter

        listed = (await client.get(f"/api/v1/reports/{rid}/schedules",
                                   headers=auth_headers["a"])).json()
        assert listed[-1]["calendar"]["kind"] == "daily"
        assert listed[-1]["recipients"] == ["a@b.co"]

    @pytest.mark.asyncio
    async def test_calendar_validation_rejects_junk(self, client, auth_headers, db_session, two_orgs, sales_ds):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        for bad in [{"kind": "hourly"}, {"kind": "daily", "hour": 25},
                    {"kind": "weekly", "weekday": 9}, {"kind": "monthly", "monthday": 31}]:
            r = await client.post(f"/api/v1/reports/{rid}/schedules",
                                  json={"recipients": ["a@b.co"], "calendar": bad},
                                  headers=auth_headers["a"])
            assert r.status_code == 400, f"{bad} should be rejected: {r.text}"


class TestAlerts:
    def test_condition_evaluates_aggregates_and_rowwise(self):
        df = pd.DataFrame({"revenue": [100.0, 50.0]})
        assert condition_holds(df, "SUM(revenue) > 100")
        assert not condition_holds(df, "SUM(revenue) > 1000")
        assert condition_holds(df, "revenue > 90")          # any row qualifies

    @pytest.mark.asyncio
    async def test_alert_fires_on_the_rising_edge_only(self, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        sent = []
        monkeypatch.setattr("app.services.alerts.send_email",
                            lambda rec, subj, body: sent.append(subj) or None)

        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/alerts",
                              json={"name": "Rev high", "expression": "SUM(revenue) > 100",
                                    "recipients": ["a@b.co"], "interval_minutes": 15},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        alert = await db_session.get(DataAlert, r.json()["id"])

        await check_alert(db_session, alert)        # true: fires
        await check_alert(db_session, alert)        # still true: must NOT re-send
        assert len(sent) == 1
        assert alert.last_status == "still firing (no re-send)"

    @pytest.mark.asyncio
    async def test_alert_rearms_after_clearing(self, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch, tmp_path):
        sent = []
        monkeypatch.setattr("app.services.alerts.send_email",
                            lambda rec, subj, body: sent.append(subj) or None)
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/alerts",
                              json={"name": "Rearm", "expression": "SUM(revenue) > 100",
                                    "recipients": ["a@b.co"]},
                              headers=auth_headers["a"])
        alert = await db_session.get(DataAlert, r.json()["id"])

        await check_alert(db_session, alert)                        # fires (180 > 100)
        pd.DataFrame({"region": ["US"], "revenue": [10.0]}).to_csv(ds.filename, index=False)
        await check_alert(db_session, alert)                        # clears
        pd.DataFrame({"region": ["US"], "revenue": [500.0]}).to_csv(ds.filename, index=False)
        await check_alert(db_session, alert)                        # fires again
        assert len(sent) == 2

    @pytest.mark.asyncio
    async def test_alert_condition_is_evaluated_over_the_creators_rls_slice(
        self, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        """S1: the alert condition must see only the creator's permitted rows, not
        the full table filtered after the fact. Pin the AGGREGATE value: SUM(revenue)
        over the CA-only slice is 30, so a > 100 condition must NOT fire even though
        the unfiltered table's sum (180) would."""
        sent = []
        monkeypatch.setattr("app.services.alerts.send_email",
                            lambda rec, subj, body: sent.append(subj) or None)
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)

        role = Role(org_id=org.id, name="CA alert", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'CA'"))
        restricted = User(org_id=org.id, role_id=role.id, email="alert-ca@example.com",
                          password_hash=hash_password("pw"))
        db_session.add(restricted)
        await db_session.flush()

        alert = DataAlert(org_id=org.id, dataset_id=ds.id, creator_user_id=restricted.id,
                          name="CA high", expression="SUM(revenue) > 100",
                          recipients=["a@b.co"])
        db_session.add(alert)
        await db_session.commit()

        await check_alert(db_session, alert)
        assert alert.last_state == "clear", "condition fired on the FULL table's sum, not the creator's RLS slice"
        assert not sent

    @pytest.mark.asyncio
    async def test_alert_condition_fails_closed_on_a_broken_rls_rule(
        self, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        """A malformed RLS expression must hide every row (fail CLOSED), so an
        alert that would fire on an unfiltered table must NOT fire when the
        creator's row-security rule is broken."""
        sent = []
        monkeypatch.setattr("app.services.alerts.send_email",
                            lambda rec, subj, body: sent.append(subj) or None)
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, sales_ds)

        role = Role(org_id=org.id, name="Broken RLS", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                                       filter_expr="not_a_real_column == 'x'"))
        restricted = User(org_id=org.id, role_id=role.id, email="alert-broken@example.com",
                          password_hash=hash_password("pw"))
        db_session.add(restricted)
        await db_session.flush()

        # COUNT(revenue) > 0 is true over the full (unfiltered) table but false over
        # the empty frame a fail-closed RLS filter must produce here.
        alert = DataAlert(org_id=org.id, dataset_id=ds.id, creator_user_id=restricted.id,
                          name="Broken", expression="COUNT(revenue) > 0",
                          recipients=["a@b.co"])
        db_session.add(alert)
        await db_session.commit()

        await check_alert(db_session, alert)
        assert alert.last_state != "firing", "broken RLS rule must hide rows, not fire on the unfiltered table"
        assert not sent

    @pytest.mark.asyncio
    async def test_a_dangerous_expression_is_rejected_at_creation(self, client, auth_headers, db_session, two_orgs, sales_ds):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/alerts",
                              json={"name": "Bad", "expression": "__import__('os').system('x')",
                                    "recipients": ["a@b.co"]},
                              headers=auth_headers["a"])
        assert r.status_code == 400


class TestTeamsDelivery:
    def test_webhook_urls_count_as_recipients(self):
        assert valid_recipients(["https://outlook.office.com/webhook/x", "a@b.co", "http://insecure"]) == [
            "https://outlook.office.com/webhook/x", "a@b.co"]
        # http:// is refused: a delivery hook carries report data summaries, and
        # posting them over cleartext is not a transport, it is a leak.

    @pytest.mark.asyncio
    async def test_a_webhook_recipient_routes_to_the_webhook(self, client, auth_headers, db_session, two_orgs, sales_ds, monkeypatch):
        posted = []
        monkeypatch.setattr("app.services.delivery.post_webhook",
                            lambda url, title, text: posted.append((url, title)) or None)
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_ds)
        rid = await _report_with_widget(client, auth_headers["a"], ds)
        r = await client.post(f"/api/v1/reports/{rid}/schedules",
                              json={"interval_minutes": 60,
                                    "recipients": ["https://hooks.example.com/abc"]},
                              headers=auth_headers["a"])
        run = await client.post(f"/api/v1/reports/{rid}/schedules/{r.json()['id']}/run-now",
                                headers=auth_headers["a"])
        assert "posted to webhook" in run.json()["last_status"]
        assert posted and posted[0][0] == "https://hooks.example.com/abc"
