"""The "Load demo content" endpoint.

The endpoint composes four seeders that are individually well covered elsewhere, so
these tests are about the composition: that all four run, that the org boundary holds,
and that loading twice is safe.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import DataSource, Dataset, Report, ReportPage
from app.services.demo_content import is_demo_dataset, is_demo_report


async def _datasets(db, org_id):
    return (await db.execute(select(Dataset).where(Dataset.org_id == org_id))).scalars().all()


async def _reports(db, org_id):
    """Eager-loads pages and widgets: async SQLAlchemy forbids lazy loading outside an
    await, so walking report.pages on a plain select raises MissingGreenlet."""
    return (await db.execute(
        select(Report)
        .where(Report.org_id == org_id)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
    )).scalars().unique().all()


@pytest.mark.asyncio
async def test_seeding_requires_authentication(client):
    """The demo writes into an org, so it needs to know which one."""
    assert (await client.post("/api/v1/demo/seed")).status_code in (401, 403)
    assert (await client.delete("/api/v1/demo/seed")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_seeding_fills_the_callers_org(client, auth_headers, db_session, two_orgs):
    r = await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["datasets"] >= 5      # four import frames + the DirectQuery one
    assert body["reports"] >= 5       # four widget-family reports + the DirectQuery one
    assert body["widgets"] > 40

    org_a = two_orgs["a"]["org"].id
    assert all(is_demo_dataset(d) for d in await _datasets(db_session, org_a))
    assert all(is_demo_report(r) for r in await _reports(db_session, org_a))


@pytest.mark.asyncio
async def test_the_feature_pass_actually_ran(client, auth_headers, db_session, two_orgs):
    """seed_demo_features is the pass easiest to leave unwired: without it the demo
    still loads and looks complete, just with no display rules, formats, calculated
    column or measures -- half the point, missing, and invisible.

    So this asserts an OBSERVABLE ARTEFACT of that pass rather than that a function was
    called: a mock-based assertion would survive the endpoint calling it with the wrong
    arguments, and calling it correctly is the part that can break.
    """
    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    org_a = two_orgs["a"]["org"].id

    datasets = await _datasets(db_session, org_a)
    assert any(d.calculated_columns for d in datasets), "no calculated column was seeded"
    assert any(d.measures for d in datasets), "no measure was seeded"
    assert any(d.column_formats for d in datasets), "no column formats were seeded"

    rules = [
        rule
        for report in await _reports(db_session, org_a)
        for page in report.pages
        for widget in page.widgets
        for rule in (widget.config.get("display_rules") or [])
    ]
    assert rules, "no display rules were seeded"
    # All three kinds are authorable now; the demo is meant to show each.
    assert {rule.get("kind") or "expression" for rule in rules} >= {"expression", "value_map", "interval"}


@pytest.mark.asyncio
async def test_the_directquery_pass_actually_ran(client, auth_headers, db_session, two_orgs):
    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    org_a = two_orgs["a"]["org"].id

    sources = (await db_session.execute(
        select(DataSource).where(DataSource.org_id == org_a)
    )).scalars().all()
    assert sources, "no DataSource was seeded"
    assert any(d.mode == "directquery" for d in await _datasets(db_session, org_a))


@pytest.mark.asyncio
async def test_one_orgs_demo_is_invisible_from_another(client, auth_headers, db_session, two_orgs):
    """The security-relevant case, asserted from the OTHER side: org B must see nothing,
    which is a stronger claim than org A seeing its own content."""
    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])

    org_b = two_orgs["b"]["org"].id
    assert await _datasets(db_session, org_b) == []
    assert await _reports(db_session, org_b) == []


@pytest.mark.asyncio
async def test_seeding_twice_leaves_one_demo(client, auth_headers, db_session, two_orgs):
    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    org_a = two_orgs["a"]["org"].id
    first = len(await _datasets(db_session, org_a)), len(await _reports(db_session, org_a))

    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    assert (len(await _datasets(db_session, org_a)), len(await _reports(db_session, org_a))) == first


@pytest.mark.asyncio
async def test_reseeding_leaves_the_users_own_content_alone(client, auth_headers, db_session, two_orgs):
    """A user's own dataset named exactly like a demo one must survive. Matching demo
    rows by name instead of by marker passes every other test in this file."""
    org_a = two_orgs["a"]["org"].id
    mine = Dataset(name="Demo — Sales", org_id=org_a, filename=None)
    db_session.add(mine)
    await db_session.commit()

    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])

    survivors = [d for d in await _datasets(db_session, org_a) if d.id == mine.id]
    assert survivors, "a user's own dataset was destroyed by the demo seeder"


@pytest.mark.asyncio
async def test_unseeding_removes_the_demo_and_only_the_demo(client, auth_headers, db_session, two_orgs):
    org_a = two_orgs["a"]["org"].id
    mine = Dataset(name="My Real Data", org_id=org_a, filename=None)
    db_session.add(mine)
    await db_session.commit()

    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    r = await client.delete("/api/v1/demo/seed", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["datasets"] >= 5

    remaining = await _datasets(db_session, org_a)
    assert [d.id for d in remaining] == [mine.id]
    assert await _reports(db_session, org_a) == []


@pytest.mark.asyncio
async def test_unseeding_one_org_leaves_another_orgs_demo_intact(client, auth_headers, db_session, two_orgs):
    await client.post("/api/v1/demo/seed", headers=auth_headers["a"])
    await client.post("/api/v1/demo/seed", headers=auth_headers["b"])

    await client.delete("/api/v1/demo/seed", headers=auth_headers["a"])

    org_b = two_orgs["b"]["org"].id
    assert await _datasets(db_session, org_b), "org B's demo was removed by org A's unseed"
