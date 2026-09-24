"""Editing auto-generated hierarchies: level removal heals the chain, levels
re-order by re-parenting, and date levels change granularity."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn, HierarchyNode
from sqlalchemy import select


@pytest.fixture
def dated(tmp_path):
    p = tmp_path / "d.csv"
    pd.DataFrame({"order_date": pd.date_range("2026-01-01", periods=30).strftime("%Y-%m-%d"),
                  "v": range(30)}).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path):
    ds = Dataset(name="D", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("order_date", "datetime"), ("v", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _chain(client, headers, ds_id):
    """id list of the date chain, top to bottom, from the API."""
    nodes = (await client.get(f"/api/v1/datasets/{ds_id}/hierarchy", headers=headers)).json()
    by_parent = {n["parent_id"]: n for n in nodes if n.get("format")}
    chain, pid = [], None
    # walk from the topmost date node
    tops = [n for n in nodes if n.get("format") and not any(
        m["id"] == n["parent_id"] and m.get("format") for m in nodes)]
    node = tops[0] if tops else None
    while node:
        chain.append(node)
        node = next((n for n in nodes if n["parent_id"] == node["id"]), None)
    return chain


@pytest.mark.asyncio
async def test_deleting_a_middle_level_heals_the_chain(client, auth_headers, db_session, two_orgs, dated):
    ds = await _dataset(db_session, two_orgs["a"]["org"], dated)
    r = await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    chain = await _chain(client, auth_headers["a"], ds.id)
    formats = [n["format"] for n in chain]
    assert formats == ["year", "quarter", "month", "day"]

    quarter = chain[1]
    r = await client.delete(f"/api/v1/datasets/{ds.id}/hierarchy/{quarter['id']}",
                            headers=auth_headers["a"])
    assert r.status_code == 204

    chain = await _chain(client, auth_headers["a"], ds.id)
    # the regression this test exists for: month and day used to CASCADE away
    assert [n["format"] for n in chain] == ["year", "month", "day"]


@pytest.mark.asyncio
async def test_patch_changes_a_date_levels_granularity(client, auth_headers, db_session, two_orgs, dated):
    ds = await _dataset(db_session, two_orgs["a"]["org"], dated)
    await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    chain = await _chain(client, auth_headers["a"], ds.id)
    month = next(n for n in chain if n["format"] == "month")
    r = await client.patch(f"/api/v1/datasets/{ds.id}/hierarchy/{month['id']}",
                           json={"format": "week", "name": "Week"}, headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["format"] == "week" and r.json()["name"] == "Week"


@pytest.mark.asyncio
async def test_levels_reorder_by_swapping_with_parent(client, auth_headers, db_session, two_orgs, dated):
    """Moving Month above Quarter: month takes quarter's parent, quarter becomes
    month's child, and month's old child re-parents to quarter -- all through
    the existing PATCH parent_id, no new endpoint needed."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], dated)
    await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    chain = await _chain(client, auth_headers["a"], ds.id)
    year, quarter, month, day = chain

    h = auth_headers["a"]
    await client.patch(f"/api/v1/datasets/{ds.id}/hierarchy/{month['id']}",
                       json={"parent_id": year["id"]}, headers=h)
    await client.patch(f"/api/v1/datasets/{ds.id}/hierarchy/{quarter['id']}",
                       json={"parent_id": month["id"]}, headers=h)
    await client.patch(f"/api/v1/datasets/{ds.id}/hierarchy/{day['id']}",
                       json={"parent_id": quarter["id"]}, headers=h)

    chain = await _chain(client, auth_headers["a"], ds.id)
    assert [n["format"] for n in chain] == ["year", "month", "quarter", "day"]
