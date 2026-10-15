"""B-21: a glossary term may belong to one dataset, and a column links to it.

The glossary only worked per connection: an uploaded dataset (Demo -- Sales)
could not get terms. A dataset-scoped term (glossary_terms.dataset_id) is seen
and used only where that dataset is readable, never as an org-wide term, and
never when it names a column the reader is denied."""
import pytest
import pytest_asyncio

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, DataSource, Dataset, DatasetColumn,
                               GlossaryTerm, Organization, Role, User)
from app.services import knowledge


def _h(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest_asyncio.fixture
async def world(db_session, tmp_path):
    org = Organization(name="Glossland")
    db_session.add(org)
    await db_session.flush()
    admin_role = Role(org_id=org.id, name="admin", is_org_admin=True)
    member_role = Role(org_id=org.id, name="member", is_org_admin=False)
    db_session.add_all([admin_role, member_role])
    await db_session.flush()
    admin = User(org_id=org.id, role_id=admin_role.id, email="admin@g.test", password_hash=hash_password("pw"))
    owner = User(org_id=org.id, role_id=member_role.id, email="owner@g.test", password_hash=hash_password("pw"))
    outsider = User(org_id=org.id, role_id=member_role.id, email="out@g.test", password_hash=hash_password("pw"))
    db_session.add_all([admin, owner, outsider])
    await db_session.flush()
    src = DataSource(name="warehouse", type="postgresql", config={}, org_id=org.id)
    db_session.add(src)
    await db_session.flush()

    def mk(name, created_by):
        csv = tmp_path / f"{name}.csv"
        csv.write_text("region,amount,margin\nNorth,10,1\n", encoding="utf-8")
        return Dataset(name=name, filename=str(csv), org_id=org.id, row_count=1, col_count=3,
                       created_by=created_by)
    sales, other = mk("Demo sales", owner.id), mk("Other", owner.id)
    db_session.add_all([sales, other])
    await db_session.flush()
    for ds in (sales, other):
        db_session.add_all([DatasetColumn(dataset_id=ds.id, name=n, dtype=t, stats={})
                            for n, t in (("region", "string"), ("amount", "number"), ("margin", "number"))])
    db_session.add_all([
        GlossaryTerm(org_id=org.id, term="GMV", synonyms=[]),                                  # org-wide
        GlossaryTerm(org_id=org.id, data_source_id=src.id, term="Paid order", synonyms=[]),    # a connection's
        GlossaryTerm(org_id=org.id, dataset_id=other.id, term="Other's term", synonyms=[]),    # another dataset's
    ])
    await db_session.commit()
    return {"org": org, "admin": admin, "owner": owner, "outsider": outsider, "member_role": member_role,
            "src": src, "sales": sales, "other": other}


async def test_an_admin_links_a_term_to_a_dataset_column(client, world):
    sales = world["sales"]
    r = await client.post(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["admin"]), json={
        "term": "Revenue", "definition": "What was sold", "synonyms": ["المبيعات"], "maps_to_column": "amount"})
    assert r.status_code == 200, r.text
    made = r.json()
    assert made["dataset_id"] == sales.id and made["data_source_id"] is None and made["maps_to_column"] == "amount"
    listed = (await client.get(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["owner"]))).json()
    # Its own term and the org-wide one; never another dataset's or a connection it does not read from.
    assert {t["term"] for t in listed} == {"GMV", "Revenue"}
    # A column that is not on the dataset is refused.
    bad = await client.post(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["admin"]),
                            json={"term": "X", "maps_to_column": "nope"})
    assert bad.status_code == 422


async def test_only_an_admin_writes_and_only_readers_read(client, world):
    sales = world["sales"]
    r = await client.post(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["owner"]), json={"term": "Mine"})
    assert r.status_code == 403
    # A dataset the member was not given does not exist for them, nor do its terms.
    r = await client.get(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["outsider"]))
    assert r.status_code == 404


async def test_a_term_on_a_denied_column_is_hidden(client, db_session, world):
    sales = world["sales"]
    db_session.add(GlossaryTerm(org_id=world["org"].id, dataset_id=sales.id, term="Margin", synonyms=[],
                                maps_to_column="margin"))
    db_session.add(ColumnSecurityRule(role_id=world["member_role"].id, dataset_id=sales.id,
                                      denied_columns=["margin"]))
    await db_session.commit()
    owner_sees = (await client.get(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["owner"]))).json()
    admin_sees = (await client.get(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["admin"]))).json()
    assert "Margin" not in {t["term"] for t in owner_sees}
    assert "Margin" in {t["term"] for t in admin_sees}
    know = await knowledge.for_dataset(db_session, sales, denied={"margin"})
    assert "Margin" not in {g.term for g in know.glossary}


async def test_the_ai_reads_a_datasets_terms_only_on_that_dataset(db_session, world):
    db_session.add(GlossaryTerm(org_id=world["org"].id, dataset_id=world["sales"].id, term="Revenue",
                                synonyms=["turnover"], maps_to_column="amount"))
    await db_session.commit()
    sales = await knowledge.for_dataset(db_session, world["sales"])
    other = await knowledge.for_dataset(db_session, world["other"])
    assert {g.term for g in sales.glossary} == {"GMV", "Revenue"}
    assert [g.term for g in sales.terms_for("total turnover by region")] == ["Revenue"]
    assert {g.term for g in other.glossary} == {"GMV", "Other's term"}


async def test_a_datasets_term_is_not_an_org_wide_term_of_a_connection(client, db_session, world):
    from app.services.agent.context import load_context
    src = world["src"]
    listed = (await client.get(f"/api/v1/data-sources/{src.id}/glossary", headers=_h(world["admin"]))).json()
    assert {t["term"] for t in listed} == {"GMV", "Paid order"}
    ctx = await load_context(db_session, src.id, world["org"].id)
    assert {g.term for g in ctx.glossary} == {"GMV", "Paid order"}


async def test_edit_and_delete_stay_on_the_datasets_own_terms(client, db_session, world):
    sales, other = world["sales"], world["other"]
    made = (await client.post(f"/api/v1/datasets/{sales.id}/glossary", headers=_h(world["admin"]),
                              json={"term": "Revenue", "maps_to_column": "amount"})).json()
    r = await client.patch(f"/api/v1/datasets/{sales.id}/glossary/{made['id']}", headers=_h(world["admin"]),
                           json={"definition": "Money in"})
    assert r.status_code == 200 and r.json()["definition"] == "Money in"
    theirs = next(t for t in (await client.get(f"/api/v1/datasets/{other.id}/glossary",
                                               headers=_h(world["admin"]))).json() if t["term"] == "Other's term")
    # Another dataset's term (or an org-wide one) is not reachable through this dataset.
    assert (await client.delete(f"/api/v1/datasets/{sales.id}/glossary/{theirs['id']}",
                                headers=_h(world["admin"]))).status_code == 404
    assert (await client.delete(f"/api/v1/datasets/{sales.id}/glossary/{made['id']}",
                                headers=_h(world["admin"]))).status_code == 204
