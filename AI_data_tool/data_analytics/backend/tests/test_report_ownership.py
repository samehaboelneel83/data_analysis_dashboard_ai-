"""Report authorship (`reports.created_by`, 0013) and the honest report list.

Two claims, both grouping-only:

* `is_mine` is AUTHORSHIP -- who created the report -- never permission. An
  admin who can do everything still reads someone else's report as not-mine,
  and a NULL author (every report from before 0013) is mine for nobody.
* the LIST endpoint now populates `my_capability` for real. It used to leave
  the schema default 'data' on every row, so the Reports page offered
  "Open designer" and Delete on reports the server would then 403.

Access control is deliberately NOT retested here: `test_report_capabilities`
owns enforcement, and `test_workspace.TestVisibilityIsNotAccessControl` pins
that grouping never gates anything.
"""
from app.core.security import create_access_token, hash_password
from app.models.models import Report, ReportCapability, Role, User


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


class TestAuthorship:
    async def test_creating_records_the_author_and_lists_it_as_mine(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "author")
        _, other = await _member(db_session, org.id, "colleague")
        await db_session.commit()

        created = await client.post("/api/v1/reports", json={"name": "Mine"},
                                    headers=_hdr(author))
        assert created.status_code == 201
        assert created.json()["is_mine"] is True

        mine_view = (await client.get("/api/v1/reports", headers=_hdr(author))).json()
        assert [r["is_mine"] for r in mine_view] == [True]

        # 0014 changed what the colleague sees: an authored dashboard is a
        # PRIVATE DRAFT until published -- absent from their list entirely.
        # Once published, it appears, and is still not theirs.
        assert (await client.get("/api/v1/reports", headers=_hdr(other))).json() == []
        rid = created.json()["id"]
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=_hdr(author))
        other_view = (await client.get("/api/v1/reports", headers=_hdr(other))).json()
        assert [r["is_mine"] for r in other_view] == [False]

    async def test_an_admin_never_owns_someone_elses_report(
            self, client, db_session, two_orgs, auth_headers):
        """can_manage-style power must not leak into the grouping: the admin
        can edit and delete it, and it is still not theirs."""
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "writer")
        await db_session.commit()
        await client.post("/api/v1/reports", json={"name": "Theirs"}, headers=_hdr(author))

        rows = (await client.get("/api/v1/reports", headers=auth_headers["a"])).json()
        theirs = next(r for r in rows if r["name"] == "Theirs")
        assert theirs["is_mine"] is False
        assert theirs["my_capability"] == "data"   # admin power intact

    async def test_a_pre_authorship_report_is_mine_for_nobody(
            self, client, db_session, two_orgs, auth_headers):
        db_session.add(Report(name="Legacy", org_id=two_orgs["a"]["org"].id,
                              created_by=None))
        await db_session.commit()
        rows = (await client.get("/api/v1/reports", headers=auth_headers["a"])).json()
        assert [r["is_mine"] for r in rows] == [False]


class TestTheListTellsTheTruthAboutCapability:
    async def test_a_view_restricted_report_lists_as_view(
            self, client, db_session, two_orgs):
        """THE regression this file exists for: the list used to claim 'data'
        on every row regardless of the viewer's actual capability."""
        org = two_orgs["a"]["org"]
        role, viewer = await _member(db_session, org.id, "restricted")
        r = Report(name="Board pack", org_id=org.id)
        db_session.add(r)
        await db_session.flush()
        db_session.add(ReportCapability(report_id=r.id, role_id=role.id, level="view"))
        await db_session.commit()

        rows = (await client.get("/api/v1/reports", headers=_hdr(viewer))).json()
        assert [x["my_capability"] for x in rows] == ["view"]

    async def test_unrestricted_unowned_rows_default_to_view(
            self, client, db_session, two_orgs):
        """No capability row used to mean 'data' for everyone. Unowned
        dashboards now default to look-and-filter; an explicit view row still
        lists as view."""
        org = two_orgs["a"]["org"]
        role, viewer = await _member(db_session, org.id, "mixed")
        open_r = Report(name="Open", org_id=org.id)
        shut_r = Report(name="Shut", org_id=org.id)
        db_session.add_all([open_r, shut_r])
        await db_session.flush()
        db_session.add(ReportCapability(report_id=shut_r.id, role_id=role.id, level="view"))
        await db_session.commit()

        rows = (await client.get("/api/v1/reports", headers=_hdr(viewer))).json()
        by_name = {x["name"]: x["my_capability"] for x in rows}
        assert by_name == {"Open": "view", "Shut": "view"}


class TestTheTreeCarriesReportOwnershipAndCapability:
    async def test_a_report_node_answers_with_the_reports_author_not_the_filer(
            self, client, db_session, two_orgs, auth_headers):
        """The admin files the member's report into a folder: the NODE is the
        admin's, the WORK is the member's, and is_mine must say so."""
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "maker")
        await db_session.commit()
        rid = (await client.post("/api/v1/reports", json={"name": "Made"},
                                 headers=_hdr(author))).json()["id"]
        # Admin (not the author) files it at the root.
        filed = await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report", "report_id": rid,
                                        "parent_id": None},
                                  headers=auth_headers["a"])
        assert filed.status_code in (200, 201)

        tree_author = (await client.get("/api/v1/workspace/tree", headers=_hdr(author))).json()
        tree_admin = (await client.get("/api/v1/workspace/tree", headers=auth_headers["a"])).json()
        node_a = next(n for n in tree_author["roots"] if n["report_id"] == rid)
        node_b = next(n for n in tree_admin["roots"] if n["report_id"] == rid)
        assert node_a["is_mine"] is True     # the author's, despite the admin filing it
        assert node_b["is_mine"] is False    # the filer's power is not authorship

    async def test_an_unfiled_report_carries_ownership_and_capability(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        role, viewer = await _member(db_session, org.id, "reader")
        _, author = await _member(db_session, org.id, "owner")
        await db_session.commit()
        rid = (await client.post("/api/v1/reports", json={"name": "Handout"},
                                 headers=_hdr(author))).json()["id"]
        db_session.add(ReportCapability(report_id=rid, role_id=role.id, level="view"))
        await db_session.commit()

        # 0014: while it is a draft, the viewer's tree does not list it at all
        # -- a role row does not open someone's draft.
        tree = (await client.get("/api/v1/workspace/tree", headers=_hdr(viewer))).json()
        assert all(n["report_id"] != rid for n in tree["unfiled"])

        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=_hdr(author))
        tree = (await client.get("/api/v1/workspace/tree", headers=_hdr(viewer))).json()
        entry = next(n for n in tree["unfiled"] if n["report_id"] == rid)
        assert entry["is_mine"] is False
        assert entry["my_capability"] == "view"

        tree_author = (await client.get("/api/v1/workspace/tree", headers=_hdr(author))).json()
        own = next(n for n in tree_author["unfiled"] if n["report_id"] == rid)
        assert own["is_mine"] is True
        assert own["my_capability"] == "data"
