"""The publish/grant regime (0014): draft -> publish (view-only) -> share-to.

The contract, per authored dashboard:

  draft      invisible to other members: not in the list, not in the tree, and
             every /reports/{id} endpoint 404s (never 403 -- a 403 confirms
             the id exists)
  published  org members open it at 'view' -- THE LAYOUT IS LOCKED: a normal
             user without a grant cannot move one widget from its position
  granted    a named user gets the granted level regardless of publication --
             an 'edit' grantee designs it, a 'view' grantee may read a draft

Unowned reports (pre-authorship) are grandfathered and appear here only as a
regression pin: nothing about them changes.
"""
from app.core.security import create_access_token, hash_password
from app.models.models import Report, ReportPage, ReportWidget, Role, User


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


async def _draft_with_widget(client, db, author):
    """An authored dashboard with one widget: (report_id, page_id, widget_id)."""
    rid = (await client.post("/api/v1/reports", json={"name": "Draft"},
                             headers=_hdr(author))).json()["id"]
    page = (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(author))
            ).json()["pages"][0]
    w = await client.post(f"/api/v1/reports/{rid}/pages/{page['id']}/widgets",
                          json={"widget_type": "text", "title": "T",
                                "config": {}, "layout": {"x": 0, "y": 0, "w": 4, "h": 3}},
                          headers=_hdr(author))
    assert w.status_code == 201
    return rid, page["id"], w.json()["id"]


class TestDraftPrivacy:
    async def test_a_draft_is_invisible_and_404s_for_another_member(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "author")
        _, other = await _member(db_session, org.id, "bystander")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)

        assert (await client.get("/api/v1/reports", headers=_hdr(other))).json() == []
        tree = (await client.get("/api/v1/workspace/tree", headers=_hdr(other))).json()
        assert all(n["report_id"] != rid for n in tree["unfiled"])
        opened = await client.get(f"/api/v1/reports/{rid}", headers=_hdr(other))
        assert opened.status_code == 404          # never 403: don't confirm the id

    async def test_the_gate_covers_subresources_not_just_the_report(
            self, client, db_session, two_orgs):
        """The router-level dependency is the whole point: bookmarks,
        schedules, deliveries and the rest must not leak a draft's existence
        one endpoint at a time (the column-security lesson)."""
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "writer")
        _, other = await _member(db_session, org.id, "walker")
        await db_session.commit()
        rid, pg, wid = await _draft_with_widget(client, db_session, author)

        for path in (f"/api/v1/reports/{rid}/bookmarks",
                     f"/api/v1/reports/{rid}/schedules",
                     f"/api/v1/reports/{rid}/deliveries",
                     f"/api/v1/reports/{rid}/revision"):
            resp = await client.get(path, headers=_hdr(other))
            assert resp.status_code == 404, path

    async def test_the_author_and_an_admin_still_see_the_draft(
            self, client, db_session, two_orgs, auth_headers):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "maker")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        assert (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(author))).status_code == 200
        assert (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).status_code == 200

    async def test_org_isolation_is_unchanged(self, client, db_session, two_orgs, auth_headers):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "insider")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=_hdr(author))
        # Published to ORG A -- org B's admin still gets a 404.
        assert (await client.get(f"/api/v1/reports/{rid}",
                                 headers=auth_headers["b"])).status_code == 404


class TestPublishing:
    async def test_publish_makes_it_view_only_the_widget_cannot_move(
            self, client, db_session, two_orgs):
        """THE hint made executable: a normal user without a grant cannot move
        any widget from its position on a published dashboard."""
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "designer")
        _, normal = await _member(db_session, org.id, "consumer")
        await db_session.commit()
        rid, pg, wid = await _draft_with_widget(client, db_session, author)
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=_hdr(author))

        opened = await client.get(f"/api/v1/reports/{rid}", headers=_hdr(normal))
        assert opened.status_code == 200
        assert opened.json()["my_capability"] == "view"
        moved = await client.patch(f"/api/v1/reports/{rid}/pages/{pg}/widgets/{wid}",
                                   json={"layout": {"x": 6, "y": 0, "w": 4, "h": 3}},
                                   headers=_hdr(normal))
        assert moved.status_code == 403
        # And the author still designs freely.
        assert (await client.patch(f"/api/v1/reports/{rid}/pages/{pg}/widgets/{wid}",
                                   json={"layout": {"x": 6, "y": 0, "w": 4, "h": 3}},
                                   headers=_hdr(author))).status_code == 200

    async def test_unpublishing_takes_it_back_out_of_sight(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "retractor")
        _, other = await _member(db_session, org.id, "audience")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                          headers=_hdr(author))
        assert (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(other))).status_code == 200
        await client.post(f"/api/v1/reports/{rid}/publish", json={"published": False},
                          headers=_hdr(author))
        assert (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(other))).status_code == 404

    async def test_only_the_author_or_an_admin_publishes(
            self, client, db_session, two_orgs, auth_headers):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "owner2")
        _, other = await _member(db_session, org.id, "impostor")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        # The stranger cannot even see it, so their publish attempt 404s.
        assert (await client.post(f"/api/v1/reports/{rid}/publish",
                                  json={"published": True},
                                  headers=_hdr(other))).status_code == 404
        # The admin can.
        assert (await client.post(f"/api/v1/reports/{rid}/publish",
                                  json={"published": True},
                                  headers=auth_headers["a"])).status_code == 200

    async def test_publishing_a_folder_publishes_the_workspace(
            self, client, db_session, two_orgs, auth_headers):
        """Folder publish = the whole subtree, resolved live: filing a new
        draft into a published workspace publishes it too."""
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "workspacer")
        _, other = await _member(db_session, org.id, "onlooker")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Team"},
                                    headers=_hdr(author))).json()
        sub = (await client.post("/api/v1/workspace/nodes",
                                 json={"node_type": "folder", "name": "Q3",
                                       "parent_id": folder["id"]},
                                 headers=_hdr(author))).json()
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "report", "report_id": rid,
                                "parent_id": sub["id"]},
                          headers=_hdr(author))
        assert (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(other))).status_code == 404

        pub = await client.patch(f"/api/v1/workspace/nodes/{folder['id']}",
                                 json={"published": True}, headers=_hdr(author))
        assert pub.status_code == 200 and pub.json()["published"] is True

        opened = await client.get(f"/api/v1/reports/{rid}", headers=_hdr(other))
        assert opened.status_code == 200
        assert opened.json()["my_capability"] == "view"

    async def test_a_report_node_refuses_the_folder_flag(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "filer2")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report", "report_id": rid},
                                  headers=_hdr(author))).json()
        resp = await client.patch(f"/api/v1/workspace/nodes/{node['id']}",
                                  json={"published": True}, headers=_hdr(author))
        assert resp.status_code == 400


class TestGrants:
    async def test_an_edit_grant_lets_that_user_move_the_widget(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "sharer")
        _, friend = await _member(db_session, org.id, "grantee")
        await db_session.commit()
        rid, pg, wid = await _draft_with_widget(client, db_session, author)

        shared = await client.post(f"/api/v1/reports/{rid}/grants",
                                   json={"email": friend.email, "level": "edit"},
                                   headers=_hdr(author))
        assert shared.status_code == 201

        # The DRAFT is now visible to exactly this user, at edit strength.
        opened = await client.get(f"/api/v1/reports/{rid}", headers=_hdr(friend))
        assert opened.status_code == 200
        assert opened.json()["my_capability"] == "edit"
        assert (await client.patch(f"/api/v1/reports/{rid}/pages/{pg}/widgets/{wid}",
                                   json={"layout": {"x": 8, "y": 0, "w": 4, "h": 3}},
                                   headers=_hdr(friend))).status_code == 200

    async def test_a_view_grant_shares_a_draft_read_only(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "previewer")
        _, reviewer = await _member(db_session, org.id, "reviewer")
        await db_session.commit()
        rid, pg, wid = await _draft_with_widget(client, db_session, author)
        await client.post(f"/api/v1/reports/{rid}/grants",
                          json={"email": reviewer.email, "level": "view"},
                          headers=_hdr(author))
        opened = await client.get(f"/api/v1/reports/{rid}", headers=_hdr(reviewer))
        assert opened.status_code == 200
        assert opened.json()["my_capability"] == "view"
        assert (await client.patch(f"/api/v1/reports/{rid}/pages/{pg}/widgets/{wid}",
                                   json={"layout": {"x": 8, "y": 0, "w": 4, "h": 3}},
                                   headers=_hdr(reviewer))).status_code == 403

    async def test_revoking_the_grant_closes_the_door(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "revoker")
        _, friend = await _member(db_session, org.id, "exfriend")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        gid = (await client.post(f"/api/v1/reports/{rid}/grants",
                                 json={"email": friend.email, "level": "edit"},
                                 headers=_hdr(author))).json()["id"]
        assert (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(friend))).status_code == 200
        assert (await client.delete(f"/api/v1/reports/{rid}/grants/{gid}",
                                    headers=_hdr(author))).status_code == 204
        assert (await client.get(f"/api/v1/reports/{rid}", headers=_hdr(friend))).status_code == 404

    async def test_a_grantee_cannot_reshare_or_publish(
            self, client, db_session, two_orgs):
        """Edit capability is design power, not sharing power: publishing and
        granting stay the author's (and the admin's)."""
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "principal")
        _, friend = await _member(db_session, org.id, "delegate")
        _, third = await _member(db_session, org.id, "third")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        await client.post(f"/api/v1/reports/{rid}/grants",
                          json={"email": friend.email, "level": "edit"},
                          headers=_hdr(author))
        assert (await client.post(f"/api/v1/reports/{rid}/publish",
                                  json={"published": True},
                                  headers=_hdr(friend))).status_code == 403
        assert (await client.post(f"/api/v1/reports/{rid}/grants",
                                  json={"email": third.email, "level": "edit"},
                                  headers=_hdr(friend))).status_code == 403

    async def test_sharing_resolves_email_within_the_org_only(
            self, client, db_session, two_orgs):
        org_a = two_orgs["a"]["org"]
        _, author = await _member(db_session, org_a.id, "insider2")
        _, outsider = await _member(db_session, two_orgs["b"]["org"].id, "outsider")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        resp = await client.post(f"/api/v1/reports/{rid}/grants",
                                 json={"email": outsider.email, "level": "edit"},
                                 headers=_hdr(author))
        assert resp.status_code == 404

    async def test_resharing_updates_the_level_instead_of_conflicting(
            self, client, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, author = await _member(db_session, org.id, "upgrader")
        _, friend = await _member(db_session, org.id, "upgraded")
        await db_session.commit()
        rid, _pg, _w = await _draft_with_widget(client, db_session, author)
        await client.post(f"/api/v1/reports/{rid}/grants",
                          json={"email": friend.email, "level": "view"},
                          headers=_hdr(author))
        again = await client.post(f"/api/v1/reports/{rid}/grants",
                                  json={"email": friend.email, "level": "edit"},
                                  headers=_hdr(author))
        assert again.status_code == 201
        grants = (await client.get(f"/api/v1/reports/{rid}/grants",
                                   headers=_hdr(author))).json()
        assert [g["level"] for g in grants] == ["edit"]


class TestGrandfathering:
    async def test_unowned_reports_are_view_only_for_members(
            self, client, db_session, two_orgs):
        """Demo / pre-authorship dashboards have no author. Treating them as
        full 'data' made every workspace View share a no-op: the viewer still
        got the studio. They stay visible, but look-and-filter only unless an
        admin or an explicit edit grant says otherwise."""
        org = two_orgs["a"]["org"]
        _, member = await _member(db_session, org.id, "oldtimer")
        legacy = Report(name="Legacy", org_id=org.id, created_by=None)
        db_session.add(legacy)
        await db_session.flush()
        db_session.add(ReportPage(report_id=legacy.id, name="P1", position=0))
        await db_session.commit()

        listed = (await client.get("/api/v1/reports", headers=_hdr(member))).json()
        assert [r["name"] for r in listed] == ["Legacy"]
        assert listed[0]["my_capability"] == "view"
        page = (await client.get(f"/api/v1/reports/{legacy.id}", headers=_hdr(member))
                ).json()["pages"][0]
        assert page["name"] == "P1"
        assert (await client.post(f"/api/v1/reports/{legacy.id}/pages",
                                  json={"name": "P2", "position": 1},
                                  headers=_hdr(member))).status_code == 403

    async def test_publishing_a_legacy_report_is_refused_with_an_explanation(
            self, client, db_session, two_orgs, auth_headers):
        legacy = Report(name="Old", org_id=two_orgs["a"]["org"].id, created_by=None)
        db_session.add(legacy)
        await db_session.commit()
        resp = await client.post(f"/api/v1/reports/{legacy.id}/publish",
                                 json={"published": True}, headers=auth_headers["a"])
        assert resp.status_code == 400
