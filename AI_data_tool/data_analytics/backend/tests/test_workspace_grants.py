"""Workspace sharing: folder grants that OPEN live access to a subtree.

The contract under test, end to end:

  * A `WorkspaceFolderGrant` on a folder (or any ancestor) opens every report
    filed beneath it for the named user / role / team — INCLUDING unpublished
    drafts, because sharing the workspace IS the publish act. 'view' cannot
    edit; 'edit' can.
  * Team grants climb the org chart: a grant to "Sales" reaches a user placed
    in "Sales / EMEA", and a multi-placed user keeps the WIDEST level.
  * Precedence is pinned both ways: a per-report `ReportUserGrant` stays
    authoritative over a folder grant (specific beats general), while against
    org-wide publication a folder grant only ever widens (grants open, never
    restrict).
  * Access implies visibility: a granted folder surfaces in the grantee's
    tree marked `shared_with_me` even when a `WorkspaceFolderRole` restriction
    would have hidden the branch — and a non-grantee still sees and opens
    nothing.
  * Only the folder's author or an org admin may read or replace the share
    list, grants live on folders only, and every subject must resolve inside
    the caller's org.
"""
import pytest
import pytest_asyncio

from app.core.capability import effective_capabilities, effective_capability
from app.core.security import create_access_token, hash_password
from app.models.models import (Organization, OrgUnit, Report, ReportPage,
                               ReportCapability, ReportUserGrant, Role, User,
                               UserOrgUnit, WorkspaceNode)


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest_asyncio.fixture
async def world(db_session):
    """Two orgs. In Shareland: an admin, an author, a grantee and a bystander
    (both plain members, different roles), and an org chart Sales > EMEA with
    the grantee placed in EMEA. Author's folder tree Sales HQ > Dashboards
    holds one unpublished report."""
    org = Organization(name="Shareland")
    other = Organization(name="Elsewhere Inc")
    db_session.add_all([org, other])
    await db_session.flush()

    admin_role = Role(org_id=org.id, name="admin", is_org_admin=True)
    makers = Role(org_id=org.id, name="makers", is_org_admin=False)
    viewers = Role(org_id=org.id, name="viewers", is_org_admin=False)
    other_role = Role(org_id=other.id, name="members", is_org_admin=True)
    db_session.add_all([admin_role, makers, viewers, other_role])
    await db_session.flush()

    def mk_user(email, role, org_id):
        return User(org_id=org_id, role_id=role.id, email=email,
                    password_hash=hash_password("pw"))

    admin = mk_user("admin@shareland.test", admin_role, org.id)
    author = mk_user("author@shareland.test", makers, org.id)
    grantee = mk_user("grantee@shareland.test", viewers, org.id)
    bystander = mk_user("bystander@shareland.test", viewers, org.id)
    outsider = mk_user("outsider@elsewhere.test", other_role, other.id)
    db_session.add_all([admin, author, grantee, bystander, outsider])
    await db_session.flush()

    sales = OrgUnit(org_id=org.id, name="Sales", match_value="Sales")
    db_session.add(sales)
    await db_session.flush()
    emea = OrgUnit(org_id=org.id, parent_id=sales.id, name="EMEA",
                   match_value="EMEA")
    db_session.add(emea)
    await db_session.flush()
    db_session.add(UserOrgUnit(user_id=grantee.id, org_unit_id=emea.id))

    report = Report(name="Pipeline", org_id=org.id, created_by=author.id,
                    published=False)
    db_session.add(report)
    await db_session.flush()
    db_session.add(ReportPage(report_id=report.id, name="Page 1", position=0))

    top = WorkspaceNode(org_id=org.id, node_type="folder", name="Sales HQ",
                        created_by=author.id)
    db_session.add(top)
    await db_session.flush()
    sub = WorkspaceNode(org_id=org.id, parent_id=top.id, node_type="folder",
                        name="Dashboards", created_by=author.id)
    db_session.add(sub)
    await db_session.flush()
    leaf = WorkspaceNode(org_id=org.id, parent_id=sub.id, node_type="report",
                         report_id=report.id, created_by=author.id)
    db_session.add(leaf)
    await db_session.commit()

    return {
        "org": org, "admin": admin, "author": author, "grantee": grantee,
        "bystander": bystander, "outsider": outsider,
        "makers": makers, "viewers": viewers,
        "sales": sales, "emea": emea,
        "report": report, "top": top, "sub": sub, "leaf": leaf,
    }


async def _share(client, w, entries, node=None, as_user=None, expect=200):
    node = node or w["top"]
    r = await client.put(f"/api/v1/workspace/nodes/{node.id}/grants",
                         json=entries, headers=_headers(as_user or w["author"]))
    assert r.status_code == expect, r.text
    return r


class TestGrantOpensTheSubtree:
    @pytest.mark.asyncio
    async def test_without_a_grant_the_draft_is_a_404(self, client, world):
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_a_view_grant_on_an_ancestor_opens_the_unpublished_report(
            self, client, world):
        """Sharing IS publishing for the subtree: the grant sits two levels
        above the report, and the report stays report.published == False."""
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "view"

    @pytest.mark.asyncio
    async def test_view_cannot_edit_but_edit_can(self, client, world):
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        r = await client.patch(f"/api/v1/reports/{world['report'].id}",
                               json={"name": "Renamed"},
                               headers=_headers(world["grantee"]))
        assert r.status_code == 403

        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "edit"}])
        r = await client.patch(f"/api/v1/reports/{world['report'].id}",
                               json={"name": "Renamed"},
                               headers=_headers(world["grantee"]))
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_a_view_grant_on_an_unowned_demo_report_is_still_view(
            self, client, db_session, world):
        """Demo dashboards ship with created_by NULL. The old resolver returned
        'data' before it ever looked at folder grants, so sharing Widget gallery
        as View still opened the full studio."""
        world["report"].created_by = None
        await db_session.commit()
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "view"
        denied = await client.patch(f"/api/v1/reports/{world['report'].id}",
                                    json={"name": "Hacked"},
                                    headers=_headers(world["grantee"]))
        assert denied.status_code == 403

    @pytest.mark.asyncio
    async def test_a_bystander_gains_nothing_from_someone_elses_grant(
            self, client, world):
        """The grant names the grantee; a same-org, same-ROLE colleague stays
        at 404. Sharing with a person must not quietly share with their role."""
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "edit"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["bystander"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_a_role_grant_reaches_every_holder_of_the_role(
            self, client, world):
        await _share(client, world,
                     [{"role_id": world["viewers"].id, "level": "view"}])
        for u in (world["grantee"], world["bystander"]):
            r = await client.get(f"/api/v1/reports/{world['report'].id}",
                                 headers=_headers(u))
            assert r.status_code == 200
            assert r.json()["my_capability"] == "view"


class TestTeamGrants:
    @pytest.mark.asyncio
    async def test_a_grant_to_the_parent_unit_reaches_a_child_placement(
            self, client, world):
        """Membership climbs: the grantee is placed in EMEA, the grant names
        Sales. Being in EMEA makes you part of Sales — the mirror of the RLS
        walk, which scopes DATA downward from a placement."""
        await _share(client, world,
                     [{"org_unit_id": world["sales"].id, "level": "view"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "view"

    @pytest.mark.asyncio
    async def test_any_tier_of_the_chart_can_be_shared_with(
            self, client, db_session, world):
        """Country > Region > Department > Team: a grant on ANY tier reaches
        the placements beneath it. The tiers are the org's own free-text
        `level_name`s, and the share picker groups on them."""
        egypt = OrgUnit(org_id=world["org"].id, name="Egypt",
                        level_name="Country", match_value="Egypt")
        db_session.add(egypt)
        await db_session.flush()
        world["sales"].parent_id = egypt.id
        world["sales"].level_name = "Department"
        world["emea"].level_name = "Team"
        await db_session.commit()

        await _share(client, world,
                     [{"org_unit_id": egypt.id, "level": "view"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "view"

    @pytest.mark.asyncio
    async def test_a_multi_placed_user_keeps_the_widest_level(
            self, client, db_session, world):
        """Placements union (models.UserOrgUnit): a user in two granted teams
        resolves to the max of the levels, never the narrower one."""
        support = OrgUnit(org_id=world["org"].id, name="Support",
                          match_value="Support")
        db_session.add(support)
        await db_session.flush()
        db_session.add(UserOrgUnit(user_id=world["grantee"].id,
                                   org_unit_id=support.id))
        await db_session.commit()

        await _share(client, world,
                     [{"org_unit_id": world["sales"].id, "level": "view"},
                      {"org_unit_id": support.id, "level": "edit"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "edit"

    @pytest.mark.asyncio
    async def test_a_sibling_unit_grant_reaches_nobody_placed_elsewhere(
            self, client, db_session, world):
        """Climbing goes UP only: a grant to EMEA's sibling must not leak to
        an EMEA placement through their shared parent."""
        apac = OrgUnit(org_id=world["org"].id, parent_id=world["sales"].id,
                       name="APAC", match_value="APAC")
        db_session.add(apac)
        await db_session.commit()

        await _share(client, world,
                     [{"org_unit_id": apac.id, "level": "edit"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 404


class TestPrecedence:
    @pytest.mark.asyncio
    async def test_a_per_report_grant_stays_authoritative(
            self, client, db_session, world):
        """Pinned choice: report 'view' under a folder shared 'edit' stays
        'view'. The author named this person on this report; the specific
        instrument wins — same reason the grant rung already beat publication."""
        db_session.add(ReportUserGrant(report_id=world["report"].id,
                                       user_id=world["grantee"].id,
                                       level="view"))
        await db_session.commit()
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "edit"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "view"

    @pytest.mark.asyncio
    async def test_against_publication_a_folder_grant_only_widens(
            self, client, db_session, world):
        """Published report, admin role-row 'edit' for the grantee's role, and
        a folder grant of 'view': the grantee keeps 'edit'. A team share must
        never hand a grantee less than any stranger in the org gets."""
        world["report"].published = True
        db_session.add(ReportCapability(report_id=world["report"].id,
                                        role_id=world["viewers"].id,
                                        level="edit"))
        await db_session.commit()
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 200
        assert r.json()["my_capability"] == "edit"

    @pytest.mark.asyncio
    async def test_batch_resolver_agrees_with_the_single_one(
            self, client, db_session, world):
        """`effective_capabilities` is what lists and trees use; it must give
        the folder-grant answer the per-report resolver gives, report by
        report — including 'none' for a report OUTSIDE the shared subtree."""
        outside = Report(name="Private", org_id=world["org"].id,
                         created_by=world["author"].id, published=False)
        db_session.add(outside)
        await db_session.commit()

        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "edit"}])

        ids = [world["report"].id, outside.id]
        single = {rid: await effective_capability(db_session, world["grantee"], rid)
                  for rid in ids}
        batch = await effective_capabilities(db_session, world["grantee"], ids)
        assert single == batch == {world["report"].id: "edit",
                                   outside.id: "none"}


class TestTheTreeSide:
    @pytest.mark.asyncio
    async def test_the_grantee_tree_marks_the_shared_branch(self, client, world):
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["grantee"]))).json()
        top = [n for n in body["roots"] if n["name"] == "Sales HQ"][0]
        assert top["shared_with_me"] is True
        assert top["is_mine"] is False
        sub = top["children"][0]
        assert sub["shared_with_me"] is True
        assert sub["children"][0]["report_id"] == world["report"].id
        assert sub["children"][0]["my_capability"] == "view"

    @pytest.mark.asyncio
    async def test_the_authors_own_tree_wears_no_shared_marker(
            self, client, world):
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["author"]))).json()
        top = [n for n in body["roots"] if n["name"] == "Sales HQ"][0]
        assert top["shared_with_me"] is False
        assert top["is_mine"] is True

    @pytest.mark.asyncio
    async def test_without_a_grant_the_draft_never_reaches_the_tree(
            self, client, world):
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["grantee"]))).json()
        top = [n for n in body["roots"] if n["name"] == "Sales HQ"][0]
        sub = top["children"][0]
        assert sub["children"] == []          # the draft is not advertised

    @pytest.mark.asyncio
    async def test_access_implies_visibility_through_a_role_restriction(
            self, client, world):
        """The folder is menu-restricted to the author's role — the grantee
        would normally not even see it. The grant punches through: a share
        that opened a report the menu refused to mention would be the old
        visibility!=security confusion, inverted."""
        r = await client.put(f"/api/v1/workspace/nodes/{world['top'].id}/roles",
                             json=[world["makers"].id],
                             headers=_headers(world["author"]))
        assert r.status_code == 200

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["grantee"]))).json()
        assert [n for n in body["roots"] if n["name"] == "Sales HQ"] == []

        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["grantee"]))).json()
        top = [n for n in body["roots"] if n["name"] == "Sales HQ"][0]
        assert top["shared_with_me"] is True
        # And the bystander (same role as the grantee, no grant) still sees
        # nothing — the punch-through is personal, not a hole in the fence.
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["bystander"]))).json()
        assert [n for n in body["roots"] if n["name"] == "Sales HQ"] == []


class TestSharedMeansGiven:
    """`shared_with_me` is a claim about PRIVILEGE, so it has to be earned.

    Anything else a viewer can see -- the org's own folders, a colleague's
    folder an admin sees by office, a published workspace open to everyone --
    was given to nobody in particular, and the tree must not dress it up as a
    personal share.
    """

    @pytest.mark.asyncio
    async def test_an_ordinary_org_folder_is_not_shared_with_anyone(
            self, client, db_session, world):
        loose = WorkspaceNode(org_id=world["org"].id, node_type="folder",
                              name="Widget gallery", created_by=world["author"].id)
        db_session.add(loose)
        await db_session.commit()

        for who in ("grantee", "admin"):
            body = (await client.get("/api/v1/workspace/tree",
                                     headers=_headers(world[who]))).json()
            node = [n for n in body["roots"] if n["name"] == "Widget gallery"][0]
            assert node["shared_with_me"] is False, who
            assert node["is_mine"] is False, who

    @pytest.mark.asyncio
    async def test_publishing_to_everyone_is_not_a_personal_share(
            self, client, world):
        """A published workspace is open to the whole org -- that is the
        opposite of somebody choosing you."""
        r = await client.patch(f"/api/v1/workspace/nodes/{world['top'].id}",
                               json={"published": True},
                               headers=_headers(world["author"]))
        assert r.status_code == 200
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["bystander"]))).json()
        top = [n for n in body["roots"] if n["name"] == "Sales HQ"][0]
        assert top["shared_with_me"] is False
        # ...and the dashboard inside is readable all the same.
        assert top["children"][0]["children"][0]["my_capability"] == "view"

    @pytest.mark.asyncio
    async def test_a_per_report_grant_marks_that_report_shared(
            self, client, db_session, world):
        """The other way a thing is genuinely given: your name on a
        dashboard's own grant list."""
        loose = Report(name="Just for you", org_id=world["org"].id,
                       created_by=world["author"].id, published=False)
        db_session.add(loose)
        await db_session.flush()
        db_session.add(ReportUserGrant(report_id=loose.id,
                                       user_id=world["grantee"].id, level="view"))
        await db_session.commit()

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["grantee"]))).json()
        entry = [n for n in body["unfiled"] if n["name"] == "Just for you"][0]
        assert entry["shared_with_me"] is True
        # The bystander cannot see it at all, let alone as a share.
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=_headers(world["bystander"]))).json()
        assert [n for n in body["unfiled"] if n["name"] == "Just for you"] == []


class TestAdministeringTheShareList:
    @pytest.mark.asyncio
    async def test_only_the_author_or_an_admin_may_share(self, client, world):
        entries = [{"user_email": world["grantee"].email, "level": "view"}]
        await _share(client, world, entries, as_user=world["bystander"],
                     expect=403)
        await _share(client, world, entries, as_user=world["author"])
        await _share(client, world, entries, as_user=world["admin"])
        # Being GRANTED a folder (even at edit) does not confer re-sharing:
        # capability is about the reports; the share list is the author's.
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "edit"}])
        await _share(client, world, entries, as_user=world["grantee"],
                     expect=403)

    @pytest.mark.asyncio
    async def test_reading_the_list_is_manager_only_and_resolved(
            self, client, world):
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"},
                      {"role_id": world["viewers"].id, "level": "view"},
                      {"org_unit_id": world["sales"].id, "level": "edit"}])
        r = await client.get(f"/api/v1/workspace/nodes/{world['top'].id}/grants",
                             headers=_headers(world["author"]))
        assert r.status_code == 200
        rows = r.json()
        assert {row["user_email"] for row in rows if row["user_id"]} \
            == {world["grantee"].email}
        assert {row["role_name"] for row in rows if row["role_id"]} == {"viewers"}
        assert {row["org_unit_name"] for row in rows if row["org_unit_id"]} \
            == {"Sales"}
        r = await client.get(f"/api/v1/workspace/nodes/{world['top'].id}/grants",
                             headers=_headers(world["bystander"]))
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_an_empty_list_unshares(self, client, world):
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}])
        await _share(client, world, [])
        r = await client.get(f"/api/v1/reports/{world['report'].id}",
                             headers=_headers(world["grantee"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_body_is_validated(self, client, world):
        # Two subjects in one entry.
        await _share(client, world,
                     [{"user_email": world["grantee"].email,
                       "role_id": world["viewers"].id, "level": "view"}],
                     expect=400)
        # No subject at all.
        await _share(client, world, [{"level": "view"}], expect=400)
        # 'data' is not a folder's to give.
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "data"}],
                     expect=400)
        # Unknown email, org-scoped: another tenant's address reads unknown.
        await _share(client, world,
                     [{"user_email": world["outsider"].email, "level": "view"}],
                     expect=400)
        # Another org's role / unit.
        await _share(client, world, [{"role_id": 999999, "level": "view"}],
                     expect=400)
        await _share(client, world, [{"org_unit_id": 999999, "level": "view"}],
                     expect=400)
        # Grants live on folders only.
        await _share(client, world,
                     [{"user_email": world["grantee"].email, "level": "view"}],
                     node=world["leaf"], expect=400)

    @pytest.mark.asyncio
    async def test_cross_org_is_a_404(self, client, world):
        r = await client.put(
            f"/api/v1/workspace/nodes/{world['top'].id}/grants",
            json=[], headers=_headers(world["outsider"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_share_options_lists_roles_and_teams_for_any_member(
            self, client, world):
        """A NON-ADMIN author needs names to address a share and cannot read
        /admin/org-units; members stay unlisted — they are typed as emails."""
        r = await client.get("/api/v1/workspace/share-options",
                             headers=_headers(world["bystander"]))
        assert r.status_code == 200
        body = r.json()
        assert {u["name"] for u in body["org_units"]} >= {"Sales", "EMEA"}
        # Each unit carries the org's OWN word for its tier, so the picker can
        # offer a department or a region instead of calling everything a team.
        assert all("level_name" in u for u in body["org_units"])
        assert {x["name"] for x in body["roles"]} \
            == {"admin", "makers", "viewers"}
        assert "users" not in body
