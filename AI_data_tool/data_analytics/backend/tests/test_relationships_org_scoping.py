from sqlalchemy import select
from app.models.models import Dataset, DatasetColumn, Relationship


async def _seed_dataset_with_column(db_session, org_id, name, col_name):
    ds = Dataset(name=name, org_id=org_id)
    db_session.add(ds)
    await db_session.flush()
    db_session.add(DatasetColumn(dataset_id=ds.id, name=col_name, dtype="numeric"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_create_relationship_with_valid_columns(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")

    resp = await client.post(
        "/api/v1/relationships",
        json={"from_dataset_id": orders.id, "from_column": "customer_id", "to_dataset_id": customers.id, "to_column": "id"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(Relationship).where(Relationship.id == resp.json()["id"]))
    assert result.scalar_one() is not None


async def test_create_relationship_rejects_unknown_column(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")

    resp = await client.post(
        "/api/v1/relationships",
        json={"from_dataset_id": orders.id, "from_column": "does_not_exist", "to_dataset_id": customers.id, "to_column": "id"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_create_relationship_cross_org_dataset_returns_404(client, db_session, two_orgs, auth_headers):
    org_b_ds = await _seed_dataset_with_column(db_session, two_orgs["b"]["org"].id, "Other Org Data", "id")
    orders = await _seed_dataset_with_column(db_session, two_orgs["a"]["org"].id, "Orders", "customer_id")

    resp = await client.post(
        "/api/v1/relationships",
        json={"from_dataset_id": orders.id, "from_column": "customer_id", "to_dataset_id": org_b_ds.id, "to_column": "id"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_list_relationships_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")
    db_session.add(Relationship(org_id=org_id, from_dataset_id=orders.id, from_column="customer_id", to_dataset_id=customers.id, to_column="id"))
    db_session.add(Relationship(org_id=two_orgs["b"]["org"].id, from_dataset_id=orders.id, from_column="x", to_dataset_id=customers.id, to_column="y"))
    await db_session.commit()

    resp = await client.get("/api/v1/relationships", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_delete_relationship_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["b"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")
    rel = Relationship(org_id=org_id, from_dataset_id=orders.id, from_column="customer_id", to_dataset_id=customers.id, to_column="id")
    db_session.add(rel)
    await db_session.commit()
    await db_session.refresh(rel)

    resp = await client.delete(f"/api/v1/relationships/{rel.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_list_exposes_provenance_so_a_guess_is_distinguishable(
    client, db_session, two_orgs, auth_headers,
):
    """`source`, `confidence` and `cardinality` reach the wire.

    The model has carried them since Layer 1 and inference fills them in, but
    they were absent from `RelationshipOut`, so a caller could not tell a link a
    human approved from one the platform guessed. The join editor ranks its key
    suggestions on exactly those fields -- confirmed > declared > inferred, then
    confidence -- so without them it could only pick arbitrarily.
    """
    import pytest
    org = two_orgs["a"]["org"]
    a = Dataset(name="A", org_id=org.id)
    b = Dataset(name="B", org_id=org.id)
    db_session.add_all([a, b])
    await db_session.flush()
    db_session.add_all([DatasetColumn(dataset_id=a.id, name="cust", dtype="text"),
                        DatasetColumn(dataset_id=b.id, name="id", dtype="text")])
    db_session.add(Relationship(
        org_id=org.id, from_dataset_id=a.id, from_column="cust",
        to_dataset_id=b.id, to_column="id",
        source="inferred", confidence=0.87, cardinality="many_to_one",
        evidence={"overlap": 0.97, "sample_size": 1000}))
    await db_session.commit()

    rows = (await client.get("/api/v1/relationships", headers=auth_headers["a"])).json()
    rel = next(r for r in rows if r["from_dataset_id"] == a.id)

    assert rel["source"] == "inferred"
    assert rel["confidence"] == pytest.approx(0.87)
    assert rel["cardinality"] == "many_to_one"
    # `evidence` stays server-side: it is review material for SourceReview, and
    # nothing consuming a suggestion reads it.
    assert "evidence" not in rel
