"""Export disablement, column duplication, org themes."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn


@pytest.fixture
def ds_file(tmp_path):
    p = tmp_path / "d.csv"
    pd.DataFrame({"region": ["US", "CA"], "revenue": [1.0, 2.0]}).to_csv(p, index=False)
    return str(p)


async def _mk(db, org_id, path):
    ds = Dataset(name="D", filename=path, org_id=org_id, mode="import")
    db.add(ds)
    await db.commit()
    return ds


class TestExportDisablement:
    @pytest.mark.asyncio
    async def test_disabling_blocks_both_export_paths(self, client, auth_headers, db_session, two_orgs, ds_file):
        ds = await _mk(db_session, two_orgs["a"]["org"].id, ds_file)
        r = await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true",
                              headers=auth_headers["a"])
        assert r.status_code == 200

        whole = await client.get(f"/api/v1/datasets/{ds.id}/export", headers=auth_headers["a"])
        widget = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv",
            json={"widget_type": "bar", "config": {"dimension": "region", "measure": "revenue"}},
            headers=auth_headers["a"])
        # BOTH paths must refuse: policy enforced on one route and forgotten on the
        # other is not a policy, it is a suggestion.
        assert whole.status_code == 403
        assert widget.status_code == 403

    @pytest.mark.asyncio
    async def test_display_still_works_when_exports_are_disabled(self, client, auth_headers, db_session, two_orgs, ds_file):
        """The control governs data LEAVING, not data showing."""
        ds = await _mk(db_session, two_orgs["a"]["org"].id, ds_file)
        await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true",
                          headers=auth_headers["a"])
        shown = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "bar", "config": {"dimension": "region", "measure": "revenue"}},
            headers=auth_headers["a"])
        assert shown.status_code == 200
        assert shown.json()["rows"]

    @pytest.mark.asyncio
    async def test_only_an_org_admin_can_set_the_policy(self, client, db_session, two_orgs, ds_file):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User
        org = two_orgs["a"]["org"]
        ds = await _mk(db_session, org.id, ds_file)
        role = Role(org_id=org.id, name="viewer", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org.id, role_id=role.id, email="v@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()

        headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}
        r = await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true", headers=headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_reenabling_restores_export(self, client, auth_headers, db_session, two_orgs, ds_file):
        ds = await _mk(db_session, two_orgs["a"]["org"].id, ds_file)
        await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true", headers=auth_headers["a"])
        await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=false", headers=auth_headers["a"])
        r = await client.get(f"/api/v1/datasets/{ds.id}/export", headers=auth_headers["a"])
        assert r.status_code == 200


class TestDuplicateColumn:
    @pytest.mark.asyncio
    async def test_duplicating_creates_an_identity_calculated_column(self, client, auth_headers, db_session, two_orgs, ds_file):
        ds = await _mk(db_session, two_orgs["a"]["org"].id, ds_file)
        db_session.add(DatasetColumn(dataset_id=ds.id, name="revenue", dtype="numeric"))
        await db_session.commit()

        r = await client.post(f"/api/v1/datasets/{ds.id}/columns/revenue/duplicate",
                              headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json() == {"name": "revenue (copy)", "expression": "`revenue`"}

        # And the copy evaluates: same values as the original through the calc engine.
        shown = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "kpi",
                  "config": {"measure": "revenue (copy)", "aggregation": "sum"},
                  "calculated_columns": [r.json()]},
            headers=auth_headers["a"])
        assert shown.json()["rows"][0]["value"] == 3.0

    @pytest.mark.asyncio
    async def test_duplicating_twice_yields_distinct_names(self, client, auth_headers, db_session, two_orgs, ds_file):
        ds = await _mk(db_session, two_orgs["a"]["org"].id, ds_file)
        db_session.add(DatasetColumn(dataset_id=ds.id, name="revenue", dtype="numeric"))
        await db_session.commit()

        a = (await client.post(f"/api/v1/datasets/{ds.id}/columns/revenue/duplicate", headers=auth_headers["a"])).json()
        b = (await client.post(f"/api/v1/datasets/{ds.id}/columns/revenue/duplicate", headers=auth_headers["a"])).json()
        assert a["name"] != b["name"], "two duplicates with one name: nothing downstream could tell them apart"

    @pytest.mark.asyncio
    async def test_duplicating_a_missing_column_404s(self, client, auth_headers, db_session, two_orgs, ds_file):
        ds = await _mk(db_session, two_orgs["a"]["org"].id, ds_file)
        r = await client.post(f"/api/v1/datasets/{ds.id}/columns/ghost/duplicate", headers=auth_headers["a"])
        assert r.status_code == 404


class TestOrgThemes:
    @pytest.mark.asyncio
    async def test_create_list_delete(self, client, auth_headers):
        r = await client.post("/api/v1/reports/themes/custom",
                              json={"name": "Brand", "colors": ["#112233", "#445566", "#778899"]},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        tid = r.json()["id"]

        listed = (await client.get("/api/v1/reports/themes/custom", headers=auth_headers["a"])).json()
        assert any(t["id"] == tid and t["colors"][0] == "#112233" for t in listed)

        assert (await client.delete(f"/api/v1/reports/themes/custom/{tid}", headers=auth_headers["a"])).status_code == 204

    @pytest.mark.asyncio
    async def test_garbage_colours_are_rejected(self, client, auth_headers):
        # These reach SVG fill attributes on every chart; a palette of garbage renders
        # everything black, so it is rejected at the door.
        for colors in (["red", "blue"], ["#12345"], [], ["#123456"] * 21, "nope"):
            r = await client.post("/api/v1/reports/themes/custom",
                                  json={"name": "Bad", "colors": colors},
                                  headers=auth_headers["a"])
            assert r.status_code == 400, colors

    @pytest.mark.asyncio
    async def test_org_isolation(self, client, auth_headers):
        await client.post("/api/v1/reports/themes/custom",
                          json={"name": "A only", "colors": ["#111111", "#222222"]},
                          headers=auth_headers["a"])
        listed_b = (await client.get("/api/v1/reports/themes/custom", headers=auth_headers["b"])).json()
        assert listed_b == []
