from app.models.models import Relationship


async def test_relationship_persists_join_key(db_session):
    from app.models.models import Dataset, Organization
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    orders = Dataset(name="Orders", org_id=org.id)
    customers = Dataset(name="Customers", org_id=org.id)
    db_session.add_all([orders, customers])
    await db_session.flush()

    rel = Relationship(
        org_id=org.id, from_dataset_id=orders.id, from_column="customer_id",
        to_dataset_id=customers.id, to_column="id",
    )
    db_session.add(rel)
    await db_session.commit()
    await db_session.refresh(rel)

    assert rel.from_column == "customer_id"
    assert rel.to_column == "id"
