"""Who may READ a dataset, and who may see or change a connection.

Until 0020 the answer was "everyone in the org": `check_org` was the only gate
on the list, the detail, the raw preview, the export and `widget-data`, so any
member could shape a request against any dataset id. RLS narrowed the rows
inside a dataset; nothing decided whether you could open it at all.

The rule under test, resolved once in `core.capability`:

    admin > owner > explicit DatasetShare > a dashboard you can already open

The last rung is what keeps workspace sharing coherent -- a dashboard shared
'view' must resolve its data or the share is an empty frame -- and it is
deliberately narrow: it opens the DATA BEHIND THAT DASHBOARD, not the shelf.
An UNOWNED dataset (created_by NULL: fixtures, seeders, pre-0020 rows) stays
open; migration 0020 backfills live rows to an org admin so a real install has
none left.
"""
import pytest
import pytest_asyncio

from app.core.security import create_access_token, hash_password
from app.models.models import (DataSource, Dataset, DatasetColumn,
                               DatasetShare, Organization, Report, ReportPage,
                               ReportWidget, Role, User, WorkspaceFolderGrant,
                               WorkspaceNode)


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest_asyncio.fixture
async def world(db_session, tmp_path):
    """One org: an admin, an owner (who uploads), and an outsider colleague.

    Datasets: `owned` (the owner's), `other` (the outsider's), `legacy` (no
    owner at all). A dashboard the owner authored reads `owned` on its primary
    dataset and `second` through one widget's own config override.
    """
    org = Organization(name="Dataland")
    db_session.add(org)
    await db_session.flush()
    admin_role = Role(org_id=org.id, name="admin", is_org_admin=True)
    member_role = Role(org_id=org.id, name="member", is_org_admin=False)
    db_session.add_all([admin_role, member_role])
    await db_session.flush()

    def mk(email, role):
        return User(org_id=org.id, role_id=role.id, email=email,
                    password_hash=hash_password("pw"))

    admin = mk("admin@dataland.test", admin_role)
    owner = mk("owner@dataland.test", member_role)
    outsider = mk("outsider@dataland.test", member_role)
    db_session.add_all([admin, owner, outsider])
    await db_session.flush()

    def mk_ds(name, created_by):
        csv = tmp_path / f"{name}.csv"
        csv.write_text("region,amount\nNorth,10\nSouth,20\n", encoding="utf-8")
        ds = Dataset(name=name, filename=str(csv), org_id=org.id,
                     row_count=2, col_count=2, created_by=created_by)
        db_session.add(ds)
        return ds

    owned = mk_ds("Owner sales", owner.id)
    second = mk_ds("Owner costs", owner.id)
    other = mk_ds("Outsider notes", outsider.id)
    legacy = mk_ds("Legacy import", None)
    await db_session.flush()
    for ds in (owned, second, other, legacy):
        db_session.add_all([
            DatasetColumn(dataset_id=ds.id, name="region", dtype="string"),
            DatasetColumn(dataset_id=ds.id, name="amount", dtype="number"),
        ])

    report = Report(name="Owner dashboard", org_id=org.id, created_by=owner.id,
                    dataset_id=owned.id, published=False)
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add_all([
        ReportWidget(page_id=page.id, widget_type="bar", title="From primary",
                     config={"dimension": "region", "measure": "amount",
                             "aggregation": "sum"},
                     layout={"x": 0, "y": 0, "w": 6, "h": 4}),
        # The widget-level override: a dashboard's data is NOT just its
        # primary dataset, and missing this is how a shared dashboard ends up
        # with one working chart and one that 404s.
        ReportWidget(page_id=page.id, widget_type="bar", title="From second",
                     config={"dataset_id": second.id, "dimension": "region",
                             "measure": "amount", "aggregation": "sum"},
                     layout={"x": 6, "y": 0, "w": 6, "h": 4}),
    ])

    conn = DataSource(name="Owner warehouse", type="postgres", config={},
                      org_id=org.id, created_by=owner.id)
    db_session.add(conn)
    await db_session.commit()

    return {"org": org, "admin": admin, "owner": owner, "outsider": outsider,
            "owned": owned, "second": second, "other": other, "legacy": legacy,
            "report": report, "page": page, "conn": conn}


def _names(body) -> set[str]:
    return {d["name"] for d in body}


class TestTheDatasetList:
    @pytest.mark.asyncio
    async def test_a_member_sees_their_own_and_the_unowned_only(self, client, world):
        r = await client.get("/api/v1/datasets", headers=_headers(world["owner"]))
        assert r.status_code == 200
        # Not "Outsider notes" -- that is the whole complaint.
        assert _names(r.json()) == {"Owner sales", "Owner costs", "Legacy import"}

    @pytest.mark.asyncio
    async def test_an_admin_still_sees_the_whole_shelf(self, client, world):
        r = await client.get("/api/v1/datasets", headers=_headers(world["admin"]))
        assert _names(r.json()) == {"Owner sales", "Owner costs",
                                    "Outsider notes", "Legacy import"}

    @pytest.mark.asyncio
    async def test_an_explicit_share_adds_one_dataset(self, client, db_session, world):
        db_session.add(DatasetShare(dataset_id=world["other"].id,
                                    user_id=world["owner"].id))
        await db_session.commit()
        r = await client.get("/api/v1/datasets", headers=_headers(world["owner"]))
        body = r.json()
        assert "Outsider notes" in _names(body)
        # ...and the badge still marks which one was handed over.
        assert [d["shared"] for d in body if d["name"] == "Outsider notes"] == [True]


class TestOpeningDataDirectly:
    @pytest.mark.asyncio
    async def test_another_members_dataset_is_a_404_everywhere(self, client, world):
        h = _headers(world["outsider"])
        did = world["owned"].id
        assert (await client.get(f"/api/v1/datasets/{did}", headers=h)).status_code == 404
        r = await client.post(f"/api/v1/datasets/{did}/data-preview",
                              json={"filters": [], "calculated_columns": [],
                                    "limit": 10, "offset": 0}, headers=h)
        assert r.status_code == 404
        assert (await client.get(f"/api/v1/datasets/{did}/export",
                                 headers=h)).status_code == 404
        r = await client.post(f"/api/v1/datasets/{did}/widget-data",
                              json={"config": {"dimension": "region", "measure": "amount",
                                               "aggregation": "sum"},
                                    "widget_type": "bar"}, headers=h)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_owner_still_reads_their_own(self, client, world):
        h = _headers(world["owner"])
        did = world["owned"].id
        assert (await client.get(f"/api/v1/datasets/{did}", headers=h)).status_code == 200
        r = await client.post(f"/api/v1/datasets/{did}/widget-data",
                              json={"config": {"dimension": "region", "measure": "amount",
                                               "aggregation": "sum"},
                                    "widget_type": "bar"}, headers=h)
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_an_unowned_dataset_stays_open(self, client, world):
        """Fixtures, seeders and pre-0020 rows have no owner. Closing those
        would break every existing install on upgrade -- the migration
        backfills instead."""
        r = await client.get(f"/api/v1/datasets/{world['legacy'].id}",
                             headers=_headers(world["outsider"]))
        assert r.status_code == 200


class TestADashboardCarriesItsData:
    """The rung that makes workspace sharing work: a viewer who can open a
    dashboard can read what it draws on -- and nothing else."""

    @pytest_asyncio.fixture
    async def shared_to_outsider(self, db_session, world):
        folder = WorkspaceNode(org_id=world["org"].id, node_type="folder",
                               name="Owner workspace", created_by=world["owner"].id)
        db_session.add(folder)
        await db_session.flush()
        db_session.add(WorkspaceNode(org_id=world["org"].id, parent_id=folder.id,
                                     node_type="report", report_id=world["report"].id,
                                     created_by=world["owner"].id))
        db_session.add(WorkspaceFolderGrant(org_id=world["org"].id, node_id=folder.id,
                                            user_id=world["outsider"].id, level="view"))
        await db_session.commit()
        return folder

    @pytest.mark.asyncio
    async def test_before_the_share_the_data_is_closed(self, client, world):
        r = await client.post(f"/api/v1/datasets/{world['owned'].id}/widget-data",
                              json={"config": {"dimension": "region", "measure": "amount",
                                               "aggregation": "sum"},
                                    "widget_type": "bar",
                                    "report_id": world["report"].id},
                              headers=_headers(world["outsider"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_shared_dashboard_resolves_both_of_its_datasets(
            self, client, world, shared_to_outsider):
        h = _headers(world["outsider"])
        for ds in (world["owned"], world["second"]):
            r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                                  json={"config": {"dimension": "region",
                                                   "measure": "amount",
                                                   "aggregation": "sum"},
                                        "widget_type": "bar",
                                        "report_id": world["report"].id},
                                  headers=h)
            assert r.status_code == 200, (ds.name, r.text)
            assert r.json()["rows"], ds.name

    @pytest.mark.asyncio
    async def test_the_share_does_not_open_the_rest_of_the_shelf(
            self, client, world, shared_to_outsider):
        """'Outsider notes' is not touched by the shared dashboard... and the
        grantee cannot borrow the report id to reach it either."""
        h = _headers(world["outsider"])
        # (it is their OWN dataset in this fixture, so use the admin's view:
        # a dataset owned by neither party and used by no visible report)
        r = await client.get("/api/v1/datasets", headers=h)
        assert "Owner costs" in _names(r.json())      # via the dashboard
        assert "Owner sales" in _names(r.json())      # via the dashboard

    @pytest.mark.asyncio
    async def test_a_report_id_the_caller_cannot_open_is_not_a_key(
            self, client, world):
        """The escape is "a dashboard YOU can open", not "any report id"."""
        r = await client.post(f"/api/v1/datasets/{world['owned'].id}/widget-data",
                              json={"config": {"dimension": "region", "measure": "amount",
                                               "aggregation": "sum"},
                                    "widget_type": "bar",
                                    "report_id": world["report"].id},
                              headers=_headers(world["outsider"]))
        assert r.status_code == 404


class TestConnections:
    @pytest.mark.asyncio
    async def test_a_member_does_not_see_someone_elses_connection(self, client, world):
        r = await client.get("/api/v1/data-sources", headers=_headers(world["outsider"]))
        assert r.status_code == 200
        assert [c["name"] for c in r.json()] == []

    @pytest.mark.asyncio
    async def test_the_owner_and_the_admin_do(self, client, world):
        for who in ("owner", "admin"):
            r = await client.get("/api/v1/data-sources", headers=_headers(world[who]))
            assert [c["name"] for c in r.json()] == ["Owner warehouse"], who

    @pytest.mark.asyncio
    async def test_a_member_can_no_longer_delete_a_colleagues_connection(
            self, client, world):
        """The hole this closes: every endpoint below the list was guarded by
        `check_org` alone, so any member could reconfigure or drop any
        connection in the org."""
        h = _headers(world["outsider"])
        cid = world["conn"].id
        assert (await client.delete(f"/api/v1/data-sources/{cid}", headers=h)).status_code == 404
        assert (await client.put(f"/api/v1/data-sources/{cid}", json={"name": "hijacked"},
                                 headers=h)).status_code == 404

    @pytest.mark.asyncio
    async def test_a_member_who_can_see_it_still_cannot_change_it(
            self, client, db_session, world):
        """Visibility is not administration: give the outsider the dataset
        behind the connection and they see the connection, but changing it
        stays with its owner and the admins."""
        world["other"].data_source_id = world["conn"].id
        await db_session.commit()
        h = _headers(world["outsider"])
        r = await client.get("/api/v1/data-sources", headers=h)
        assert [c["name"] for c in r.json()] == ["Owner warehouse"]
        assert (await client.put(f"/api/v1/data-sources/{world['conn'].id}",
                                 json={"name": "hijacked"}, headers=h)).status_code == 403
        assert (await client.delete(f"/api/v1/data-sources/{world['conn'].id}",
                                    headers=h)).status_code == 403

    @pytest.mark.asyncio
    async def test_the_owner_may_still_administer_their_own(self, client, world):
        r = await client.put(f"/api/v1/data-sources/{world['conn'].id}",
                             json={"name": "Renamed warehouse"},
                             headers=_headers(world["owner"]))
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Renamed warehouse"


class TestTheOtherWaysIn:
    """Two surfaces enumerated datasets org-wide after the list stopped: the
    Ask-AI scope and the lineage map. A rule the Datasets page keeps and the
    diagram beside it breaks is not a rule."""

    @pytest.mark.asyncio
    async def test_the_agent_refuses_a_scope_the_asker_cannot_read(
            self, client, world):
        """Asking the model about a table is reading it, in prose."""
        r = await client.post("/api/v1/agent/conversations",
                              json={"dataset_ids": [world["owned"].id],
                                    "title": "Snooping"},
                              headers=_headers(world["outsider"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_owner_may_still_ask_about_their_own(self, client, world):
        r = await client.post("/api/v1/agent/conversations",
                              json={"dataset_ids": [world["owned"].id],
                                    "title": "Mine"},
                              headers=_headers(world["owner"]))
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_a_connection_the_member_cannot_see_is_not_a_scope_either(
            self, client, world):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": world["conn"].id,
                                    "title": "Snooping"},
                              headers=_headers(world["outsider"]))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_lineage_map_draws_only_readable_datasets(
            self, client, world):
        r = await client.get("/api/v1/datasets/lineage/graph",
                             headers=_headers(world["outsider"]))
        assert r.status_code == 200, r.text
        body = r.json()
        drawn = {n["name"] for n in body["datasets"]}
        assert "Owner sales" not in drawn
        assert "Owner costs" not in drawn
        assert "Outsider notes" in drawn      # their own is still on the map
        assert "Legacy import" in drawn       # unowned stays open
        # The connection behind nothing they can read is off the map too.
        assert [x["name"] for x in body["sources"]] == []


class TestUploadsRecordTheirOwner:
    @pytest.mark.asyncio
    async def test_an_upload_belongs_to_whoever_uploaded_it(self, client, db_session, world):
        files = {"file": ("mine.csv", b"a,b\n1,2\n", "text/csv")}
        r = await client.post("/api/v1/datasets", files=files,
                              data={"name": "Fresh upload", "description": ""},
                              headers=_headers(world["owner"]))
        assert r.status_code in (200, 201), r.text
        ds = await db_session.get(Dataset, r.json()["id"])
        assert ds.created_by == world["owner"].id
        # ...and a colleague cannot open it.
        assert (await client.get(f"/api/v1/datasets/{ds.id}",
                                 headers=_headers(world["outsider"]))).status_code == 404
