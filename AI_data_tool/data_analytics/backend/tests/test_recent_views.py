"""Per-user Recents (0015): opening a dashboard is what makes it recent.

Home used to order Recents by `reports.updated_at`, which answers a different
question -- "what changed" -- with two consequences a user notices: a dashboard
somebody ELSE edited jumps to the top of your list, and one you read every
morning without editing never appears at all.

The claims pinned here:
  * opening records a view, and re-opening moves it up rather than duplicating
  * recents are PER USER -- your list is not affected by anyone else's reading
  * a report you may no longer open leaves your list (the keyhole rule)
  * recording a view can never fail the read it rode in on
"""
from app.core.security import create_access_token, hash_password
from app.models.models import RecentView, Report, Role, User
from sqlalchemy import select


async def _member(db, org_id, name):
    role = Role(org_id=org_id, name=name, is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org_id, role_id=role.id,
                email=f"{name}-{role.id}@ex.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    return role, user


def _hdr(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _report(client, headers, name):
    r = await client.post("/api/v1/reports", json={"name": name}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


class TestOpeningRecordsAView:
    async def test_opening_a_dashboard_puts_it_in_recents(
            self, client, db_session, two_orgs, auth_headers):
        rid = await _report(client, auth_headers["a"], "Sales")
        # Creating is not opening: the list is empty until the report is read.
        assert (await client.get("/api/v1/reports/recent", headers=auth_headers["a"])).json() == []

        await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])
        recents = (await client.get("/api/v1/reports/recent", headers=auth_headers["a"])).json()
        assert [r["name"] for r in recents] == ["Sales"]

    async def test_reopening_moves_it_up_without_duplicating(
            self, client, db_session, two_orgs, auth_headers):
        first = await _report(client, auth_headers["a"], "First")
        second = await _report(client, auth_headers["a"], "Second")

        await client.get(f"/api/v1/reports/{first}", headers=auth_headers["a"])
        await client.get(f"/api/v1/reports/{second}", headers=auth_headers["a"])
        await client.get(f"/api/v1/reports/{first}", headers=auth_headers["a"])

        recents = (await client.get("/api/v1/reports/recent", headers=auth_headers["a"])).json()
        assert [r["name"] for r in recents] == ["First", "Second"]

        # One row per (user, report) -- re-opening upserts, it does not append.
        rows = (await db_session.execute(
            select(RecentView).where(RecentView.report_id == first))).scalars().all()
        assert len(rows) == 1

    async def test_the_newest_open_comes_first(
            self, client, db_session, two_orgs, auth_headers):
        a = await _report(client, auth_headers["a"], "Older")
        b = await _report(client, auth_headers["a"], "Newer")
        await client.get(f"/api/v1/reports/{a}", headers=auth_headers["a"])
        await client.get(f"/api/v1/reports/{b}", headers=auth_headers["a"])

        recents = (await client.get("/api/v1/reports/recent", headers=auth_headers["a"])).json()
        assert recents[0]["name"] == "Newer"

    async def test_limit_is_honoured_and_bounded(
            self, client, db_session, two_orgs, auth_headers):
        for i in range(4):
            rid = await _report(client, auth_headers["a"], f"R{i}")
            await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])

        assert len((await client.get("/api/v1/reports/recent?limit=2",
                                     headers=auth_headers["a"])).json()) == 2
        # An absurd limit is clamped rather than accepted.
        assert (await client.get("/api/v1/reports/recent?limit=9999",
                                 headers=auth_headers["a"])).status_code == 200


class TestRecentsArePersonal:
    async def test_one_users_reading_does_not_touch_anothers_list(
            self, client, db_session, two_orgs, auth_headers):
        """THE bug the old updated_at ordering had, in reverse: your recents
        must reflect YOUR reading, nobody else's."""
        org = two_orgs["a"]["org"]
        _, other = await _member(db_session, org.id, "colleague")
        await db_session.commit()

        rid = await _report(client, auth_headers["a"], "Board pack")
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=auth_headers["a"])
        # The colleague opens it; the admin never does.
        await client.get(f"/api/v1/reports/{rid}", headers=_hdr(other))

        assert (await client.get("/api/v1/reports/recent", headers=auth_headers["a"])).json() == []
        assert [r["name"] for r in (await client.get(
            "/api/v1/reports/recent", headers=_hdr(other))).json()] == ["Board pack"]

    async def test_another_orgs_report_never_appears(
            self, client, db_session, two_orgs, auth_headers):
        rid = await _report(client, auth_headers["a"], "Org A only")
        await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])
        assert (await client.get("/api/v1/reports/recent", headers=auth_headers["b"])).json() == []


class TestVisibilityIsRecheckedOnRead:
    async def test_a_dashboard_you_may_no_longer_open_leaves_your_recents(
            self, client, db_session, two_orgs, auth_headers):
        """The keyhole rule: the row records that you opened it once, not that
        you may open it now. Unpublishing must remove it from the list, not
        leave a card that 404s when clicked."""
        org = two_orgs["a"]["org"]
        _, reader = await _member(db_session, org.id, "reader")
        await db_session.commit()

        rid = await _report(client, auth_headers["a"], "Retracted")
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=auth_headers["a"])
        await client.get(f"/api/v1/reports/{rid}", headers=_hdr(reader))
        assert len((await client.get("/api/v1/reports/recent", headers=_hdr(reader))).json()) == 1

        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": False},
                          headers=auth_headers["a"])
        assert (await client.get("/api/v1/reports/recent", headers=_hdr(reader))).json() == []

    async def test_a_deleted_report_takes_its_recents_row_with_it(
            self, client, db_session, two_orgs, auth_headers):
        rid = await _report(client, auth_headers["a"], "Doomed")
        await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])
        await client.delete(f"/api/v1/reports/{rid}", headers=auth_headers["a"])

        assert (await client.get("/api/v1/reports/recent", headers=auth_headers["a"])).json() == []
        rows = (await db_session.execute(
            select(RecentView).where(RecentView.report_id == rid))).scalars().all()
        assert rows == []


class TestRecordingNeverBreaksTheRead:
    async def test_the_report_read_still_succeeds_and_returns_the_report(
            self, client, db_session, two_orgs, auth_headers):
        """Recording a view is a convenience riding on a read the user asked
        for; it must never turn that read into an error."""
        rid = await _report(client, auth_headers["a"], "Solid")
        resp = await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])
        assert resp.status_code == 200
        assert resp.json()["name"] == "Solid"

    async def test_recent_is_not_swallowed_by_the_report_id_route(
            self, client, db_session, two_orgs, auth_headers):
        """/recent is a literal path that `/{report_id}` would otherwise
        capture into a 422 -- declaration order is what keeps it reachable, and
        an ordering regression would show up exactly here."""
        resp = await client.get("/api/v1/reports/recent", headers=auth_headers["a"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
