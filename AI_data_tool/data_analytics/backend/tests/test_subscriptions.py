"""Self-serve subscriptions: a viewer signs themselves up for a report.

The whole design turns on one fact: a `ReportSchedule` resolves row-level
security **as its creator**. Appending a subscriber to somebody else's schedule
would email them the creator's slice of the data -- silently, and possibly rows
they must not see. So subscribing creates a schedule the SUBSCRIBER owns, and
the tests below pin that ownership rather than the plumbing around it.

The second rule is about authority: subscribing yourself needs only `view`,
because receiving data you can already read grants you nothing new, while adding
somebody ELSE to a distribution list still needs `edit`.
"""
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (Dataset, Report, ReportCapability, ReportSchedule,
                               Role, User)


async def _report(db, org, name="Quarterly"):
    ds = Dataset(name="D", org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    r = Report(name=name, org_id=org.id, dataset_id=ds.id)
    db.add(r)
    await db.flush()
    await db.commit()
    return r


async def _viewer(db, org, email="viewer@example.com", report_id=None):
    """A user with no edit rights anywhere."""
    role = Role(org_id=org.id, name=f"viewers-{email}", is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org.id, role_id=role.id, email=email,
                password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    if report_id is not None:
        db.add(ReportCapability(report_id=report_id, role_id=role.id, level="view"))
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def _schedules(db, report_id):
    from sqlalchemy import select
    return (await db.execute(select(ReportSchedule).where(
        ReportSchedule.report_id == report_id))).scalars().all()


class TestASubscriberGetsTheirOwnData:
    @pytest.mark.asyncio
    async def test_the_schedule_belongs_to_the_subscriber(
            self, client, db_session, two_orgs):
        """The point of the whole feature. A schedule resolves RLS as its
        creator, so the subscriber must BE the creator or they receive somebody
        else's slice."""
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        user, headers = await _viewer(db_session, org, report_id=rep.id)

        resp = await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                                 json={"cadence": "daily"}, headers=headers)

        assert resp.status_code == 201, resp.text
        scheds = await _schedules(db_session, rep.id)
        assert len(scheds) == 1
        assert scheds[0].creator_user_id == user.id

    @pytest.mark.asyncio
    async def test_it_delivers_only_to_the_subscriber(
            self, client, db_session, two_orgs):
        """A subscription is not a distribution list -- one recipient, and it is
        the person who asked."""
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        user, headers = await _viewer(db_session, org, report_id=rep.id)

        await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                          json={"cadence": "daily"}, headers=headers)

        sched = (await _schedules(db_session, rep.id))[0]
        emails = [r for r in sched.recipients if isinstance(r, str)]
        assert emails == [user.email]

    @pytest.mark.asyncio
    async def test_two_subscribers_get_two_schedules(
            self, client, db_session, two_orgs):
        """One render each is the price of each person seeing their own rows."""
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, h1 = await _viewer(db_session, org, "one@example.com", rep.id)
        _, h2 = await _viewer(db_session, org, "two@example.com", rep.id)

        await client.post(f"/api/v1/reports/{rep.id}/subscribe", json={}, headers=h1)
        await client.post(f"/api/v1/reports/{rep.id}/subscribe", json={}, headers=h2)

        assert len(await _schedules(db_session, rep.id)) == 2


class TestAuthority:
    @pytest.mark.asyncio
    async def test_a_viewer_may_subscribe_themselves(
            self, client, db_session, two_orgs):
        """Only `view` is required: receiving data you can already read grants
        you nothing new. Creating a schedule for OTHER people still needs edit."""
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)

        resp = await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                                 json={}, headers=headers)
        assert resp.status_code == 201, resp.text

    @pytest.mark.asyncio
    async def test_a_viewer_still_cannot_create_a_schedule_for_others(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)

        resp = await client.post(
            f"/api/v1/reports/{rep.id}/schedules",
            json={"recipients": ["someone.else@example.com"], "interval_minutes": 60},
            headers=headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_another_orgs_report_cannot_be_subscribed_to(
            self, client, db_session, two_orgs, auth_headers):
        rep = await _report(db_session, two_orgs["a"]["org"])
        resp = await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                                 json={}, headers=auth_headers["b"])
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unsubscribing_cannot_delete_an_authors_schedule(
            self, client, db_session, two_orgs, auth_headers):
        """A subscriber removing their own delivery must not take the report's
        distribution list with it."""
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        made = await client.post(
            f"/api/v1/reports/{rep.id}/schedules",
            json={"recipients": ["team@example.com"], "interval_minutes": 60},
            headers=auth_headers["a"])
        assert made.status_code == 201, made.text
        _, headers = await _viewer(db_session, org, report_id=rep.id)

        resp = await client.delete(f"/api/v1/reports/{rep.id}/subscribe", headers=headers)

        assert resp.status_code == 404, "a non-subscriber found something to delete"
        assert len(await _schedules(db_session, rep.id)) == 1


class TestTheLifecycle:
    @pytest.mark.asyncio
    async def test_it_reports_whether_you_are_subscribed(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)

        before = await client.get(f"/api/v1/reports/{rep.id}/subscription", headers=headers)
        assert before.json() == {"subscribed": False}

        await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                          json={"cadence": "weekly", "hour": 7}, headers=headers)

        after = (await client.get(f"/api/v1/reports/{rep.id}/subscription",
                                  headers=headers)).json()
        assert after["subscribed"] is True
        assert after["calendar"]["kind"] == "weekly"
        assert after["calendar"]["hour"] == 7

    @pytest.mark.asyncio
    async def test_subscribing_twice_edits_rather_than_duplicates(
            self, client, db_session, two_orgs):
        """Otherwise a double click delivers the report twice, forever."""
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)

        await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                          json={"cadence": "daily"}, headers=headers)
        await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                          json={"cadence": "monthly", "monthday": 3}, headers=headers)

        scheds = await _schedules(db_session, rep.id)
        assert len(scheds) == 1
        state = (await client.get(f"/api/v1/reports/{rep.id}/subscription",
                                  headers=headers)).json()
        assert state["calendar"]["kind"] == "monthly"

    @pytest.mark.asyncio
    async def test_unsubscribing_removes_it(self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)
        await client.post(f"/api/v1/reports/{rep.id}/subscribe", json={}, headers=headers)

        resp = await client.delete(f"/api/v1/reports/{rep.id}/subscribe", headers=headers)

        assert resp.status_code == 204
        assert await _schedules(db_session, rep.id) == []

    @pytest.mark.asyncio
    async def test_unsubscribing_when_not_subscribed_is_a_404(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)
        resp = await client.delete(f"/api/v1/reports/{rep.id}/subscribe", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_a_bad_cadence_is_refused(self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)
        resp = await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                                 json={"cadence": "hourly"}, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_pdf_can_be_chosen(self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        rep = await _report(db_session, org)
        _, headers = await _viewer(db_session, org, report_id=rep.id)
        resp = await client.post(f"/api/v1/reports/{rep.id}/subscribe",
                                 json={"format": "pdf"}, headers=headers)
        assert resp.json()["format"] == "pdf"
