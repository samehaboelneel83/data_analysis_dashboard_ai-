"""The workspace tree: folders, filed reports, and the rules that protect them.

Three contracts carry real risk, and each has its own class below:

  * Deleting a folder must never delete the reports inside it. `parent_id` is
    ON DELETE CASCADE, so the naive implementation destroys somebody's filed
    work on a misclick.
  * A node must not be movable into its own subtree. This tree is the org's
    navigation menu; a cycle in it hangs the renderer for everyone.
  * Every report must be reachable. A report that exists but cannot be opened
    from the menu is worse than the flat list this replaces.

The rest is ordinary CRUD and org isolation.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.models import (Organization, Report, ReportPage, Role, User,
                               WorkspaceNode)
from app.core.security import create_access_token, hash_password
from app.routers.workspace import _would_cycle


@pytest_asyncio.fixture
async def org(db_session):
    o = Organization(name="Tree Co")
    db_session.add(o)
    await db_session.flush()
    role = Role(org_id=o.id, name="member", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=o.id, role_id=role.id, email="tree@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return {"org": o, "user": user,
            "headers": {"Authorization":
                        f"Bearer {create_access_token(user.id, o.id)}"}}


@pytest_asyncio.fixture
async def reports(db_session, org):
    made = []
    for name in ("Alpha", "Beta", "Gamma"):
        r = Report(name=name, org_id=org["org"].id)
        db_session.add(r)
        await db_session.flush()
        db_session.add(ReportPage(report_id=r.id, name="Page 1", position=0))
        made.append(r)
    await db_session.commit()
    return made


class TestTheTree:
    @pytest.mark.asyncio
    async def test_an_empty_org_has_no_folders(self, client, org):
        r = await client.get("/api/v1/workspace/tree", headers=org["headers"])
        assert r.status_code == 200
        assert r.json()["roots"] == []

    @pytest.mark.asyncio
    async def test_an_unfiled_report_is_still_reachable(self, client, org, reports):
        """The contract that makes this navigation rather than tagging: a report
        with no node must still appear, or it becomes unopenable."""
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        assert {n["name"] for n in body["unfiled"]} == {"Alpha", "Beta", "Gamma"}

    @pytest.mark.asyncio
    async def test_a_filed_report_leaves_unfiled(self, client, org, reports):
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Sales"},
                                    headers=org["headers"])).json()
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "report", "report_id": reports[0].id,
                                "parent_id": folder["id"]},
                          headers=org["headers"])

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        assert {n["name"] for n in body["unfiled"]} == {"Beta", "Gamma"}
        assert body["roots"][0]["name"] == "Sales"
        assert body["roots"][0]["children"][0]["name"] == "Alpha"

    @pytest.mark.asyncio
    async def test_pages_appear_under_their_report(self, client, org, reports):
        """Pages are joined in at read time, never stored -- so a page added in
        the builder shows up without a second write anywhere."""
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report",
                                        "report_id": reports[0].id},
                                  headers=org["headers"])).json()
        assert node["report_id"] == reports[0].id

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        filed = [n for n in body["roots"] if n["report_id"] == reports[0].id][0]
        assert [p["name"] for p in filed["pages"]] == ["Page 1"]

    @pytest.mark.asyncio
    async def test_a_report_node_shows_the_reports_current_name(
            self, client, db_session, org, reports):
        """A report node stores no name of its own, so renaming the report is
        the only edit needed -- there is no second title to drift."""
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "report", "report_id": reports[0].id},
                          headers=org["headers"])
        reports[0].name = "Alpha (renamed)"
        await db_session.commit()

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        assert body["roots"][0]["name"] == "Alpha (renamed)"


class TestDeletingAFolderKeepsItsReports:
    """The highest-stakes behaviour here. `parent_id` cascades, so the naive
    delete takes the whole subtree -- and with it the user's filed reports."""

    @pytest.mark.asyncio
    async def test_children_are_reparented_not_deleted(self, client, db_session,
                                                       org, reports):
        outer = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "folder", "name": "Outer"},
                                   headers=org["headers"])).json()
        inner = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "folder", "name": "Inner",
                                         "parent_id": outer["id"]},
                                   headers=org["headers"])).json()
        filed = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "report",
                                         "report_id": reports[0].id,
                                         "parent_id": inner["id"]},
                                   headers=org["headers"])).json()

        r = await client.delete(f"/api/v1/workspace/nodes/{inner['id']}",
                                headers=org["headers"])
        assert r.status_code == 204

        node = await db_session.get(WorkspaceNode, filed["id"])
        assert node is not None, "deleting a folder destroyed the report node"
        assert node.parent_id == outer["id"], "the child was not re-parented"

    @pytest.mark.asyncio
    async def test_the_report_itself_always_survives(self, client, db_session,
                                                     org, reports):
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report",
                                        "report_id": reports[0].id},
                                  headers=org["headers"])).json()
        await client.delete(f"/api/v1/workspace/nodes/{node['id']}",
                            headers=org["headers"])

        still = await db_session.get(Report, reports[0].id)
        assert still is not None, "unfiling a report deleted it"

    @pytest.mark.asyncio
    async def test_an_unfiled_report_returns_to_the_root_list(self, client, org,
                                                              reports):
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report",
                                        "report_id": reports[0].id},
                                  headers=org["headers"])).json()
        await client.delete(f"/api/v1/workspace/nodes/{node['id']}",
                            headers=org["headers"])

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        assert "Alpha" in {n["name"] for n in body["unfiled"]}


class TestCyclesAreRejected:
    """`hierarchy.py`'s PATCH does a blind setattr and has no such guard --
    survivable for a small hand-built dataset tree, not for the org's menu."""

    @pytest.mark.asyncio
    async def test_a_node_cannot_be_its_own_parent(self, client, org):
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "F"},
                                    headers=org["headers"])).json()
        r = await client.patch(f"/api/v1/workspace/nodes/{folder['id']}",
                               json={"parent_id": folder["id"]},
                               headers=org["headers"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_a_node_cannot_move_into_its_own_descendant(self, client, org):
        outer = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "folder", "name": "Outer"},
                                   headers=org["headers"])).json()
        inner = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "folder", "name": "Inner",
                                         "parent_id": outer["id"]},
                                   headers=org["headers"])).json()
        r = await client.patch(f"/api/v1/workspace/nodes/{outer['id']}",
                               json={"parent_id": inner["id"]},
                               headers=org["headers"])
        assert r.status_code == 400, "Outer was moved inside its own child"

    @pytest.mark.asyncio
    async def test_a_legitimate_move_still_works(self, client, org):
        a = (await client.post("/api/v1/workspace/nodes",
                               json={"node_type": "folder", "name": "A"},
                               headers=org["headers"])).json()
        b = (await client.post("/api/v1/workspace/nodes",
                               json={"node_type": "folder", "name": "B"},
                               headers=org["headers"])).json()
        r = await client.patch(f"/api/v1/workspace/nodes/{b['id']}",
                               json={"parent_id": a["id"]},
                               headers=org["headers"])
        assert r.status_code == 200
        assert r.json()["parent_id"] == a["id"]

    def test_the_walk_terminates_on_an_already_cyclic_tree(self):
        """A cycle written directly into the database must not hang the request
        that is trying to move a node out of it."""
        class N:
            def __init__(self, id, parent_id):
                self.id, self.parent_id = id, parent_id

        nodes = [N(1, 2), N(2, 1)]          # already looping
        assert _would_cycle(nodes, 3, 1) is False


class TestValidation:
    @pytest.mark.asyncio
    async def test_a_folder_needs_a_name(self, client, org):
        r = await client.post("/api/v1/workspace/nodes",
                              json={"node_type": "folder", "name": "  "},
                              headers=org["headers"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_a_report_cannot_be_filed_twice(self, client, org, reports):
        payload = {"node_type": "report", "report_id": reports[0].id}
        assert (await client.post("/api/v1/workspace/nodes", json=payload,
                                  headers=org["headers"])).status_code == 201
        r = await client.post("/api/v1/workspace/nodes", json=payload,
                              headers=org["headers"])
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_only_a_folder_can_hold_children(self, client, org, reports):
        leaf = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report",
                                        "report_id": reports[0].id},
                                  headers=org["headers"])).json()
        r = await client.post("/api/v1/workspace/nodes",
                              json={"node_type": "folder", "name": "Nope",
                                    "parent_id": leaf["id"]},
                              headers=org["headers"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_a_report_node_cannot_be_renamed(self, client, org, reports):
        """Its label is the report's name; a second title would diverge."""
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report",
                                        "report_id": reports[0].id},
                                  headers=org["headers"])).json()
        r = await client.patch(f"/api/v1/workspace/nodes/{node['id']}",
                               json={"name": "Something else"},
                               headers=org["headers"])
        assert r.status_code == 400


class TestOrgIsolation:
    @pytest.mark.asyncio
    async def test_another_orgs_tree_is_invisible(self, client, db_session, org):
        other = Organization(name="Other Co")
        db_session.add(other)
        await db_session.flush()
        db_session.add(WorkspaceNode(org_id=other.id, node_type="folder",
                                     name="Their folder", position=0))
        await db_session.commit()

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        assert body["roots"] == []

    @pytest.mark.asyncio
    async def test_another_orgs_node_cannot_be_deleted(self, client, db_session, org):
        other = Organization(name="Other Co")
        db_session.add(other)
        await db_session.flush()
        node = WorkspaceNode(org_id=other.id, node_type="folder",
                             name="Theirs", position=0)
        db_session.add(node)
        await db_session.commit()

        r = await client.delete(f"/api/v1/workspace/nodes/{node.id}",
                                headers=org["headers"])
        assert r.status_code == 404
        assert await db_session.get(WorkspaceNode, node.id) is not None


class TestWhoMayManageANode:
    """Create is open to everyone; change and remove belong to the author.

    Anyone in the org can make folders and file reports -- that is how a tree
    gets organised at all. Editing or deleting what someone ELSE put there is
    the part that needs an owner, so it is the author or an admin, who needs a
    way to tidy up after people who have left.
    """

    @pytest_asyncio.fixture
    async def member(self, db_session, org):
        role = Role(org_id=org["org"].id, name="viewer", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org["org"].id, role_id=role.id,
                    email="member@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()
        return {"user": user,
                "headers": {"Authorization":
                            f"Bearer {create_access_token(user.id, org['org'].id)}"}}

    @pytest.mark.asyncio
    async def test_creating_records_the_author(self, client, db_session, org, member):
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "folder", "name": "Mine"},
                                  headers=member["headers"])).json()
        row = await db_session.get(WorkspaceNode, node["id"])
        assert row.created_by == member["user"].id

    @pytest.mark.asyncio
    async def test_a_member_can_manage_their_own_folder(self, client, org, member):
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "folder", "name": "Mine"},
                                  headers=member["headers"])).json()

        renamed = await client.patch(f"/api/v1/workspace/nodes/{node['id']}",
                                     json={"name": "Mine, renamed"},
                                     headers=member["headers"])
        assert renamed.status_code == 200

        removed = await client.delete(f"/api/v1/workspace/nodes/{node['id']}",
                                      headers=member["headers"])
        assert removed.status_code == 204

    @pytest.mark.asyncio
    async def test_a_member_cannot_delete_someone_elses_folder(
            self, client, db_session, org, member):
        """The admin fixture created this one."""
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "folder", "name": "Theirs"},
                                  headers=org["headers"])).json()

        r = await client.delete(f"/api/v1/workspace/nodes/{node['id']}",
                                headers=member["headers"])
        assert r.status_code == 403
        assert await db_session.get(WorkspaceNode, node["id"]) is not None

    @pytest.mark.asyncio
    async def test_a_member_cannot_rename_someone_elses_folder(
            self, client, org, member):
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "folder", "name": "Theirs"},
                                  headers=org["headers"])).json()
        r = await client.patch(f"/api/v1/workspace/nodes/{node['id']}",
                               json={"name": "Hijacked"},
                               headers=member["headers"])
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_an_admin_can_manage_anything(self, client, org, member):
        """Somebody has to be able to tidy up after a departed colleague."""
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "folder", "name": "Mine"},
                                  headers=member["headers"])).json()
        r = await client.delete(f"/api/v1/workspace/nodes/{node['id']}",
                                headers=org["headers"])
        assert r.status_code == 204

    @pytest.mark.asyncio
    async def test_an_unowned_node_is_admin_only(self, client, db_session, org, member):
        """Rows predating created_by -- and everything the demo seeder makes --
        have no author. "Nobody owns it" must not read as "anybody may delete
        it"."""
        orphan = WorkspaceNode(org_id=org["org"].id, node_type="folder",
                               name="Seeded", position=0, created_by=None)
        db_session.add(orphan)
        await db_session.commit()

        assert (await client.delete(f"/api/v1/workspace/nodes/{orphan.id}",
                                    headers=member["headers"])).status_code == 403
        assert (await client.delete(f"/api/v1/workspace/nodes/{orphan.id}",
                                    headers=org["headers"])).status_code == 204

    @pytest.mark.asyncio
    async def test_any_member_may_create(self, client, org, member):
        """Creating stays open: gating it would mean nobody but an admin can
        organise their own reports, which is how a folder tree ends up unused."""
        r = await client.post("/api/v1/workspace/nodes",
                              json={"node_type": "folder", "name": "Scratch"},
                              headers=member["headers"])
        assert r.status_code == 201


class TestFolderVisibility:
    """Who sees which folders in the menu.

    The default is the whole migration story: a folder with NO grants is visible
    to everyone. Grants restrict. Any other default would empty every non-admin
    menu the day this shipped -- the same stance PageRoleVisibility and
    ReportCapability already take, recorded in their docstrings.
    """

    @pytest_asyncio.fixture
    async def member(self, db_session, org):
        role = Role(org_id=org["org"].id, name="analyst", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org["org"].id, role_id=role.id,
                    email="analyst@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()
        return {"user": user, "role": role,
                "headers": {"Authorization":
                            f"Bearer {create_access_token(user.id, org['org'].id)}"}}

    async def _names(self, client, headers):
        body = (await client.get("/api/v1/workspace/tree", headers=headers)).json()
        return {n["name"] for n in body["roots"]}

    async def _extra_role(self, db_session, org, name="finance"):
        role = Role(org_id=org["org"].id, name=name, is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        await db_session.commit()
        return role

    @pytest.mark.asyncio
    async def test_an_ungranted_folder_is_visible_to_everyone(
            self, client, org, member):
        """The default, pinned so nobody turns it into deny-by-default."""
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "folder", "name": "Shared"},
                          headers=org["headers"])
        assert "Shared" in await self._names(client, member["headers"])

    @pytest.mark.asyncio
    async def test_a_granted_folder_hides_from_everyone_else(
            self, client, db_session, org, member):
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Finance"},
                                    headers=org["headers"])).json()
        other = await self._extra_role(db_session, org)

        r = await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                             json=[other.id], headers=org["headers"])
        assert r.status_code == 200
        assert "Finance" not in await self._names(client, member["headers"])

    @pytest.mark.asyncio
    async def test_a_granted_role_sees_it(self, client, org, member):
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Finance"},
                                    headers=org["headers"])).json()
        await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                         json=[member["role"].id], headers=org["headers"])
        assert "Finance" in await self._names(client, member["headers"])

    @pytest.mark.asyncio
    async def test_an_admin_always_sees_it(self, client, db_session, org, member):
        """An admin locked out could not administer the lock."""
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Finance"},
                                    headers=org["headers"])).json()
        other = await self._extra_role(db_session, org, "nobody")
        await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                         json=[other.id], headers=org["headers"])
        assert "Finance" in await self._names(client, org["headers"])

    @pytest.mark.asyncio
    async def test_the_creator_always_sees_their_own_folder(
            self, client, db_session, org, member):
        """Otherwise they would simply make another copy."""
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Mine"},
                                    headers=member["headers"])).json()
        other = await self._extra_role(db_session, org, "nobody")
        await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                         json=[other.id], headers=member["headers"])
        assert "Mine" in await self._names(client, member["headers"])

    @pytest.mark.asyncio
    async def test_restriction_hides_the_whole_subtree(
            self, client, db_session, org, member, reports):
        """A report inside a hidden folder is absent from the ENTIRE response --
        not relocated to unfiled, which would defeat the restriction by moving
        the entry rather than hiding it."""
        outer = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "folder", "name": "Finance"},
                                   headers=org["headers"])).json()
        inner = (await client.post("/api/v1/workspace/nodes",
                                   json={"node_type": "folder", "name": "Payroll",
                                         "parent_id": outer["id"]},
                                   headers=org["headers"])).json()
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "report", "report_id": reports[0].id,
                                "parent_id": inner["id"]},
                          headers=org["headers"])
        other = await self._extra_role(db_session, org)
        await client.put(f"/api/v1/workspace/nodes/{outer['id']}/roles",
                         json=[other.id], headers=org["headers"])

        body = (await client.get("/api/v1/workspace/tree",
                                 headers=member["headers"])).json()
        everything = str(body)
        assert "Finance" not in everything
        assert "Payroll" not in everything, "the child folder leaked"
        assert "Alpha" not in everything, "the report leaked, or fell to unfiled"

    @pytest.mark.asyncio
    async def test_removing_the_grants_makes_it_public_again(
            self, client, db_session, org, member):
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Finance"},
                                    headers=org["headers"])).json()
        other = await self._extra_role(db_session, org)

        await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                         json=[other.id], headers=org["headers"])
        assert "Finance" not in await self._names(client, member["headers"])

        await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                         json=[], headers=org["headers"])
        assert "Finance" in await self._names(client, member["headers"])


class TestVisibilityIsNotAccessControl:
    """The honesty test.

    Folder grants hide MENU ENTRIES. They do not stop anyone opening a report by
    id -- ReportCapability is the access-control layer, and RLS governs the rows.
    If this ever starts failing, someone has quietly turned the menu into an ACL
    and the documentation that says otherwise has become wrong.
    """

    @pytest_asyncio.fixture
    async def member(self, db_session, org):
        role = Role(org_id=org["org"].id, name="analyst", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org["org"].id, role_id=role.id,
                    email="analyst2@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()
        return {"headers": {"Authorization":
                            f"Bearer {create_access_token(user.id, org['org'].id)}"}}

    @pytest.mark.asyncio
    async def test_a_hidden_report_can_still_be_opened_by_id(
            self, client, db_session, org, member, reports):
        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "Finance"},
                                    headers=org["headers"])).json()
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "report", "report_id": reports[0].id,
                                "parent_id": folder["id"]},
                          headers=org["headers"])
        other = Role(org_id=org["org"].id, name="finance", is_org_admin=False)
        db_session.add(other)
        await db_session.flush()
        await db_session.commit()
        await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                         json=[other.id], headers=org["headers"])

        # Absent from the menu...
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=member["headers"])).json()
        assert "Alpha" not in str(body)

        # ...but still readable directly. The documented boundary, not an
        # oversight: hiding a menu entry is tidiness, not authorisation.
        direct = await client.get(f"/api/v1/reports/{reports[0].id}",
                                  headers=member["headers"])
        assert direct.status_code == 200


class TestGrantPermissions:
    @pytest.mark.asyncio
    async def test_only_a_folder_can_be_restricted(self, client, org, reports):
        node = (await client.post("/api/v1/workspace/nodes",
                                  json={"node_type": "report",
                                        "report_id": reports[0].id},
                                  headers=org["headers"])).json()
        r = await client.put(f"/api/v1/workspace/nodes/{node['id']}/roles",
                             json=[], headers=org["headers"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_a_role_from_another_org_is_rejected(self, client, db_session, org):
        other_org = Organization(name="Elsewhere")
        db_session.add(other_org)
        await db_session.flush()
        foreign = Role(org_id=other_org.id, name="theirs", is_org_admin=False)
        db_session.add(foreign)
        await db_session.flush()
        await db_session.commit()

        folder = (await client.post("/api/v1/workspace/nodes",
                                    json={"node_type": "folder", "name": "F"},
                                    headers=org["headers"])).json()
        r = await client.put(f"/api/v1/workspace/nodes/{folder['id']}/roles",
                             json=[foreign.id], headers=org["headers"])
        assert r.status_code == 400, (
            "a grant to another tenant's role is a restriction nobody here "
            "could ever satisfy")

    @pytest.mark.asyncio
    async def test_can_manage_is_reported_per_viewer(self, client, org):
        """The UI shows or hides controls from this, rather than re-implementing
        the ownership rule client-side."""
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "folder", "name": "Admins"},
                          headers=org["headers"])
        body = (await client.get("/api/v1/workspace/tree",
                                 headers=org["headers"])).json()
        assert body["roots"][0]["can_manage"] is True


class TestIsMine:
    """Ownership, reported per viewer.

    `can_manage` cannot answer "is this mine?" -- it is true for an admin on
    every node in the org. The menu groups My workspaces / Shared with me on
    `is_mine`, so the two flags have to disagree for an admin looking at
    somebody else's folder, and this pins that.
    """

    @pytest_asyncio.fixture
    async def member(self, db_session, org):
        role = Role(org_id=org["org"].id, name="member2", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org["org"].id, role_id=role.id,
                    email="owner@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()
        return {"user": user,
                "headers": {"Authorization":
                            f"Bearer {create_access_token(user.id, org['org'].id)}"}}

    async def _root(self, client, headers, name):
        body = (await client.get("/api/v1/workspace/tree", headers=headers)).json()
        return next(n for n in body["roots"] if n["name"] == name)

    @pytest.mark.asyncio
    async def test_true_for_the_creator(self, client, org, member):
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "folder", "name": "Mine"},
                          headers=member["headers"])
        node = await self._root(client, member["headers"], "Mine")
        assert node["is_mine"] is True
        assert node["can_manage"] is True

    @pytest.mark.asyncio
    async def test_false_for_someone_else(self, client, org, member):
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "folder", "name": "Theirs"},
                          headers=org["headers"])
        node = await self._root(client, member["headers"], "Theirs")
        assert node["is_mine"] is False
        assert node["can_manage"] is False

    @pytest.mark.asyncio
    async def test_false_for_an_admin_who_can_manage_it(self, client, org, member):
        """The case the whole flag exists for: an admin may manage a member's
        folder, but it is not theirs, and the menu must not claim it is."""
        await client.post("/api/v1/workspace/nodes",
                          json={"node_type": "folder", "name": "Mine"},
                          headers=member["headers"])
        node = await self._root(client, org["headers"], "Mine")
        assert node["can_manage"] is True, "an admin should still be able to manage it"
        assert node["is_mine"] is False, "but it is not the admin's folder"

    @pytest.mark.asyncio
    async def test_false_for_an_unowned_node(self, client, db_session, org):
        """Demo-seeded folders and anything predating created_by belong to
        nobody -- they are shared, not mine."""
        orphan = WorkspaceNode(org_id=org["org"].id, node_type="folder",
                               name="Seeded", position=0, created_by=None)
        db_session.add(orphan)
        await db_session.commit()

        node = await self._root(client, org["headers"], "Seeded")
        assert node["is_mine"] is False
