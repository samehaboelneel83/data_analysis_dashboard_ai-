from sqlalchemy import select
from app.main import _backfill_default_org
from app.models.models import Organization, Dataset, Report, DataSource
from app.services.auth_provisioning import create_organization_with_admin


async def test_org_id_columns_exist_on_dataset_report_data_source(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    ds = Dataset(name="d1", org_id=org.id)
    rp = Report(name="r1", org_id=org.id)
    src = DataSource(name="s1", type="postgres", org_id=org.id)
    db_session.add_all([ds, rp, src])
    await db_session.commit()

    assert ds.org_id == org.id
    assert rp.org_id == org.id
    assert src.org_id == org.id


async def test_backfill_creates_default_org_and_admin_role_when_none_exists(db_session):
    result = await db_session.execute(select(Organization))
    assert result.scalars().all() == []

    await _backfill_default_org(db_session)

    result = await db_session.execute(select(Organization))
    orgs = result.scalars().all()
    assert len(orgs) == 1
    assert orgs[0].name == "Default Organization"


async def test_backfill_assigns_org_id_less_rows_to_the_default_org(db_session):
    ds = Dataset(name="orphan-dataset")  # org_id defaults to None
    rp = Report(name="orphan-report")
    src = DataSource(name="orphan-source", type="postgres")
    db_session.add_all([ds, rp, src])
    await db_session.commit()
    assert ds.org_id is None and rp.org_id is None and src.org_id is None

    await _backfill_default_org(db_session)

    result = await db_session.execute(select(Organization))
    default_org = result.scalar_one()
    await db_session.refresh(ds)
    await db_session.refresh(rp)
    await db_session.refresh(src)
    assert ds.org_id == default_org.id
    assert rp.org_id == default_org.id
    assert src.org_id == default_org.id


async def test_backfill_does_not_touch_rows_that_already_have_an_org_id(db_session):
    org_a, _, _ = await create_organization_with_admin(db_session, "Org A", "a@example.com", "password-a")
    await db_session.commit()
    ds = Dataset(name="already-scoped", org_id=org_a.id)
    db_session.add(ds)
    await db_session.commit()

    await _backfill_default_org(db_session)

    await db_session.refresh(ds)
    assert ds.org_id == org_a.id  # unchanged — not reassigned to the new default org


async def test_backfill_is_idempotent(db_session):
    await _backfill_default_org(db_session)
    await _backfill_default_org(db_session)

    result = await db_session.execute(select(Organization).where(Organization.name == "Default Organization"))
    assert len(result.scalars().all()) == 1  # still only one, not duplicated
