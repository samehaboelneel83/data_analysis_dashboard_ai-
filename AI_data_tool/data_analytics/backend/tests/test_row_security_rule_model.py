import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.models import Organization, Role, Dataset, RowSecurityRule


async def _seed_role_and_dataset(db_session):
    org = Organization(name="Org")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Regional", is_org_admin=False)
    ds = Dataset(name="D", org_id=org.id)
    db_session.add_all([role, ds])
    await db_session.flush()
    return role, ds


async def test_row_security_rule_round_trip(db_session):
    role, ds = await _seed_role_and_dataset(db_session)
    rule = RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    assert rule.id is not None
    assert rule.role.id == role.id
    assert rule.dataset.id == ds.id
    assert rule.filter_expr == "region == 'North'"


async def test_row_security_rule_unique_per_role_and_dataset(db_session):
    role, ds = await _seed_role_and_dataset(db_session)
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="a == 1"))
    await db_session.commit()

    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="b == 2"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_role_cascades_to_its_rules(db_session):
    role, ds = await _seed_role_and_dataset(db_session)
    rule = RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="a == 1")
    db_session.add(rule)
    await db_session.commit()
    rule_id = rule.id

    await db_session.delete(role)
    await db_session.commit()

    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == rule_id))
    assert result.scalar_one_or_none() is None
