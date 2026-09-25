"""An aggregate dataset remembers its source, and dies with it.

`aggregate_of_dataset_id` is how read-time security finds the source's rules
(Task 3). A dangling pointer would mean rules that cannot be found -- so the
foreign key cascades: delete the source, the aggregate goes too.
"""
import pytest
from sqlalchemy import select

from app.models.models import Dataset


@pytest.mark.asyncio
async def test_an_aggregate_points_at_its_source_and_keeps_its_spec(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    spec = {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "amount_sum"}]}
    agg = Dataset(name="orders by region", org_id=org.id, mode="import",
                  aggregate_of_dataset_id=src.id, aggregate_spec=spec)
    db_session.add(agg)
    await db_session.commit()
    await db_session.refresh(agg)
    assert agg.aggregate_of_dataset_id == src.id
    assert agg.aggregate_spec == spec


@pytest.mark.asyncio
async def test_deleting_the_source_deletes_the_aggregate(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    agg = Dataset(name="agg", org_id=org.id, mode="import", aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": [], "measures": []})
    db_session.add(agg)
    await db_session.commit()
    agg_id = agg.id
    await db_session.delete(src)
    await db_session.commit()
    db_session.expire_all()
    assert (await db_session.execute(select(Dataset).where(Dataset.id == agg_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_the_fields_are_exposed_on_the_api(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    agg = Dataset(name="agg", org_id=org.id, mode="import", aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": ["region"], "measures": []})
    db_session.add(agg)
    await db_session.commit()
    r = await client.get(f"/api/v1/datasets/{agg.id}", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["aggregate_of_dataset_id"] == src.id
    assert r.json()["aggregate_spec"]["grain"] == ["region"]
