"""Reusable data views: snapshot a dataset's semantic layer, apply it to another
dataset by column name, skip-and-report whatever doesn't fit."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn, HierarchyNode


@pytest.fixture
def files(tmp_path):
    a = tmp_path / "q1.csv"
    pd.DataFrame({"region": ["US"], "revenue": [1.0], "cost": [0.5]}).to_csv(a, index=False)
    b = tmp_path / "q2.csv"
    # q2 lacks `cost` -- the piece of the bundle that must be skipped, not fatal.
    pd.DataFrame({"region": ["EU"], "revenue": [2.0]}).to_csv(b, index=False)
    return str(a), str(b)


async def _dataset(db, org, path, cols):
    ds = Dataset(name=path.split("\\")[-1], filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c in cols:
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    await db.commit()
    return ds


async def _rich_source(db, org, files):
    """A dataset with every bundleable piece authored."""
    src = await _dataset(db, org, files[0], ["region", "revenue", "cost"])
    src.column_meta = {"region": {"role": "category"}, "revenue": {"aggregation": "sum"},
                       "__exports_disabled__": True}
    src.column_formats = {"revenue": {"type": "currency", "symbol": "$"},
                          "cost": {"type": "currency", "symbol": "$"}}
    src.calculated_columns = [{"name": "profit", "expression": "`revenue` - `cost`"},
                              {"name": "revenue2", "expression": "`revenue` * 2"}]
    src.measures = [{"name": "total_profit", "expression": "SUM(`revenue`) - SUM(`cost`)"}]
    src.default_filter_expr = "`revenue` > 0"
    db.add(HierarchyNode(dataset_id=src.id, name="Geo", node_type="folder", position=0))
    await db.flush()
    folder = (await db.execute(
        __import__("sqlalchemy").select(HierarchyNode).where(HierarchyNode.dataset_id == src.id)
    )).scalars().one()
    db.add(HierarchyNode(dataset_id=src.id, parent_id=folder.id, name="Region",
                         node_type="category", column_name="region", position=0))
    await db.commit()
    return src


@pytest.mark.asyncio
async def test_snapshot_excludes_reserved_keys(client, auth_headers, db_session, two_orgs, files):
    src = await _rich_source(db_session, two_orgs["a"]["org"], files)
    r = await client.post(f"/api/v1/datasets/{src.id}/save-data-view?name=Sales semantics",
                          headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    from app.models.models import DataView
    view = await db_session.get(DataView, r.json()["id"])
    assert "__exports_disabled__" not in view.payload["column_meta"]
    assert view.payload["column_meta"]["region"] == {"role": "category"}
    assert view.payload["hierarchy"][0]["children"][0]["column_name"] == "region"


@pytest.mark.asyncio
async def test_apply_transfers_what_fits_and_reports_what_does_not(client, auth_headers, db_session, two_orgs, files):
    org = two_orgs["a"]["org"]
    src = await _rich_source(db_session, org, files)
    dst = await _dataset(db_session, org, files[1], ["region", "revenue"])

    r = await client.post(f"/api/v1/datasets/{src.id}/save-data-view?name=V", headers=auth_headers["a"])
    vid = r.json()["id"]
    r = await client.post(f"/api/v1/datasets/{dst.id}/apply-data-view?view_id={vid}",
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()

    # revenue2 fits (`revenue` exists); profit needs `cost` and is skipped by name.
    assert body["applied"]["calculated_columns"] == 1
    assert any("profit" in x and "cost" in x for x in body["skipped"])
    assert any("total_profit" in x for x in body["skipped"])          # measure needs cost
    assert any("format for 'cost'" in x for x in body["skipped"])
    assert body["applied"]["default_filter_expr"] == 1
    assert body["applied"]["hierarchy_nodes"] == 2                    # folder + region node

    await db_session.refresh(dst)
    assert [c["name"] for c in dst.calculated_columns] == ["revenue2"]
    assert dst.column_formats == {"revenue": {"type": "currency", "symbol": "$"}}
    assert dst.column_meta["region"] == {"role": "category"}
    assert dst.default_filter_expr == "`revenue` > 0"


@pytest.mark.asyncio
async def test_apply_preserves_target_reserved_keys(client, auth_headers, db_session, two_orgs, files):
    """The target's own export policy must survive an apply -- a semantic bundle
    is not a governance bypass."""
    org = two_orgs["a"]["org"]
    src = await _rich_source(db_session, org, files)
    dst = await _dataset(db_session, org, files[1], ["region", "revenue"])
    dst.column_meta = {"__exports_disabled__": True}
    await db_session.commit()

    r = await client.post(f"/api/v1/datasets/{src.id}/save-data-view?name=V", headers=auth_headers["a"])
    await client.post(f"/api/v1/datasets/{dst.id}/apply-data-view?view_id={r.json()['id']}",
                      headers=auth_headers["a"])
    await db_session.refresh(dst)
    assert dst.column_meta.get("__exports_disabled__") is True


@pytest.mark.asyncio
async def test_views_are_org_scoped(client, auth_headers, db_session, two_orgs, files):
    src = await _rich_source(db_session, two_orgs["a"]["org"], files)
    r = await client.post(f"/api/v1/datasets/{src.id}/save-data-view?name=Private", headers=auth_headers["a"])
    vid = r.json()["id"]

    r = await client.get("/api/v1/datasets/data-views/list", headers=auth_headers["b"])
    assert r.json() == []
    foreign_ds = await _dataset(db_session, two_orgs["b"]["org"], files[1], ["region", "revenue"])
    r = await client.post(f"/api/v1/datasets/{foreign_ds.id}/apply-data-view?view_id={vid}",
                          headers=auth_headers["b"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_names_the_pieces_and_delete_removes(client, auth_headers, db_session, two_orgs, files):
    src = await _rich_source(db_session, two_orgs["a"]["org"], files)
    r = await client.post(f"/api/v1/datasets/{src.id}/save-data-view?name=V", headers=auth_headers["a"])
    vid = r.json()["id"]
    r = await client.get("/api/v1/datasets/data-views/list", headers=auth_headers["a"])
    row = r.json()[0]
    assert "calculated_columns" in row["pieces"] and "hierarchy" in row["pieces"]
    r = await client.delete(f"/api/v1/datasets/data-views/{vid}", headers=auth_headers["a"])
    assert r.status_code == 204
    r = await client.get("/api/v1/datasets/data-views/list", headers=auth_headers["a"])
    assert r.json() == []
