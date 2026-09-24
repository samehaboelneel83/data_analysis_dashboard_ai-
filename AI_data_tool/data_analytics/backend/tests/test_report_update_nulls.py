"""PATCH /reports/{id}: which nulls mean "clear".

The builder's undo of "attach data" on a report created without a dataset has
to put the report back to NO primary dataset. Before, every null in the body
was dropped, so that undo silently did nothing. Only dataset_id may be cleared
this way; a null name is still ignored (a report cannot lose its name).
"""
from app.models.models import Dataset


async def test_explicit_null_clears_only_the_primary_dataset(client, db_session, two_orgs, auth_headers):
    ds = Dataset(name="Sales", org_id=two_orgs["a"]["org"].id, mode="directquery", source_table="sales")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    made = await client.post("/api/v1/reports", json={"name": "Q3"}, headers=auth_headers["a"])
    assert made.status_code in (200, 201), made.text
    rid = made.json()["id"]

    r = await client.patch(f"/api/v1/reports/{rid}", json={"dataset_id": ds.id}, headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["dataset_id"] == ds.id

    # Unset: untouched.
    r = await client.patch(f"/api/v1/reports/{rid}", json={"theme": "ocean"}, headers=auth_headers["a"])
    assert r.json()["dataset_id"] == ds.id

    # Explicit null on the dataset clears it; on the name it is ignored.
    r = await client.patch(f"/api/v1/reports/{rid}", json={"dataset_id": None, "name": None},
                           headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["dataset_id"] is None
    assert r.json()["name"] == "Q3"
