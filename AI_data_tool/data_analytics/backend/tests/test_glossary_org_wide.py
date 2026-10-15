"""B-21 step 1: org-wide glossary terms can be created, not only read.

Org-wide terms (no connection, no dataset) were already read by the AI
(agent/context.load_context, knowledge.glossary_terms_for) and listed with a
connection's terms, but no route could create one: an uploaded dataset could
only get terms of its own, one dataset at a time. `/api/v1/glossary` writes
them -- org admins only, like every glossary write -- and any member reads them.
"""
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import (DataSource, Dataset, DatasetColumn, GlossaryTerm,
                               Organization, Role, User)
from app.services import knowledge


def _h(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest_asyncio.fixture
async def world(db_session, tmp_path):
    orgs = {}
    for name in ("Org wide", "Elsewhere"):
        org = Organization(name=name)
        db_session.add(org)
        await db_session.flush()
        admin_role = Role(org_id=org.id, name="admin", is_org_admin=True)
        member_role = Role(org_id=org.id, name="member", is_org_admin=False)
        db_session.add_all([admin_role, member_role])
        await db_session.flush()
        slug = name.replace(" ", "").lower()
        admin = User(org_id=org.id, role_id=admin_role.id, email=f"admin@{slug}.test", password_hash=hash_password("pw"))
        member = User(org_id=org.id, role_id=member_role.id, email=f"member@{slug}.test", password_hash=hash_password("pw"))
        db_session.add_all([admin, member])
        await db_session.flush()
        orgs[name] = {"org": org, "admin": admin, "member": member}
    org = orgs["Org wide"]["org"]
    src = DataSource(name="warehouse", type="postgresql", config={}, org_id=org.id)
    db_session.add(src)
    await db_session.flush()
    csv = tmp_path / "sales.csv"
    csv.write_text("region,amount\nNorth,10\n", encoding="utf-8")
    # An UPLOADED dataset: no connection to hang a term on.
    sales = Dataset(name="Demo sales", filename=str(csv), org_id=org.id, row_count=1, col_count=2,
                    created_by=orgs["Org wide"]["admin"].id)
    db_session.add(sales)
    await db_session.flush()
    db_session.add_all([DatasetColumn(dataset_id=sales.id, name=n, dtype=t, stats={})
                        for n, t in (("region", "string"), ("amount", "number"))])
    conn_term = GlossaryTerm(org_id=org.id, data_source_id=src.id, term="Paid order", synonyms=[])
    ds_term = GlossaryTerm(org_id=org.id, dataset_id=sales.id, term="Sales term", synonyms=[])
    theirs = GlossaryTerm(org_id=orgs["Elsewhere"]["org"].id, term="Their GMV", synonyms=[])
    db_session.add_all([conn_term, ds_term, theirs])
    await db_session.commit()
    return {**orgs["Org wide"], "other": orgs["Elsewhere"], "src": src, "sales": sales,
            "conn_term": conn_term, "ds_term": ds_term, "theirs": theirs}


async def test_an_admin_creates_an_org_wide_term_and_every_scope_sees_it(client, db_session, world):
    from app.services.agent.context import load_context
    r = await client.post("/api/v1/glossary", headers=_h(world["admin"]), json={
        "term": " GMV ", "definition": "Gross merchandise value", "synonyms": ["إجمالي المبيعات", " gross sales "],
        "maps_to_column": "amount", "rule": " amount > 0 ", "always": True})
    assert r.status_code == 200, r.text
    made = r.json()
    assert made["term"] == "GMV" and made["data_source_id"] is None and made["dataset_id"] is None
    assert made["synonyms"] == ["إجمالي المبيعات", "gross sales"] and made["rule"] == "amount > 0" and made["always"] is True

    # Persisted as an org-wide row of this org.
    row = (await db_session.execute(select(GlossaryTerm).where(GlossaryTerm.id == made["id"]))).scalar_one()
    assert (row.org_id, row.data_source_id, row.dataset_id) == (world["org"].id, None, None)

    # Listed for any member -- only the org's org-wide terms, not a connection's or a dataset's.
    listed = await client.get("/api/v1/glossary", headers=_h(world["member"]))
    assert listed.status_code == 200
    assert [t["term"] for t in listed.json()] == ["GMV"]

    # The connection's glossary and its AI context carry it ...
    on_src = (await client.get(f"/api/v1/data-sources/{world['src'].id}/glossary", headers=_h(world["member"]))).json()
    assert "GMV" in {t["term"] for t in on_src}
    ctx = await load_context(db_session, world["src"].id, world["org"].id)
    assert "GMV" in {g.term for g in ctx.glossary}
    # ... and so do the uploaded dataset's glossary and knowledge context.
    on_ds = (await client.get(f"/api/v1/datasets/{world['sales'].id}/glossary", headers=_h(world["admin"]))).json()
    assert {t["term"] for t in on_ds} == {"GMV", "Sales term"}
    know = await knowledge.for_dataset(db_session, world["sales"])
    assert [g.term for g in know.terms_for("total gross sales by region")] == ["GMV"]


async def test_writes_are_org_admin_only_reads_are_for_members(client, db_session, world):
    member = _h(world["member"])
    assert (await client.post("/api/v1/glossary", headers=member, json={"term": "Mine"})).status_code == 403
    term = GlossaryTerm(org_id=world["org"].id, term="ARR", synonyms=[])
    db_session.add(term)
    await db_session.commit()
    assert (await client.patch(f"/api/v1/glossary/{term.id}", headers=member, json={"definition": "x"})).status_code == 403
    assert (await client.delete(f"/api/v1/glossary/{term.id}", headers=member)).status_code == 403
    assert [t["term"] for t in (await client.get("/api/v1/glossary", headers=member)).json()] == ["ARR"]
    assert (await client.get("/api/v1/glossary")).status_code == 401


async def test_same_validation_as_a_connections_terms(client, world):
    admin = _h(world["admin"])
    assert (await client.post("/api/v1/glossary", headers=admin, json={"term": "  "})).status_code == 422
    assert (await client.post("/api/v1/glossary", headers=admin, json={})).status_code == 422
    assert (await client.post("/api/v1/glossary", headers=admin, json={"term": "X", "synonyms": ["ok", " "]})).status_code == 422
    assert (await client.post("/api/v1/glossary", headers=admin, json={"term": "X", "rule": "r" * 2001})).status_code == 422


async def test_edit_and_delete_an_org_wide_term(client, world):
    admin = _h(world["admin"])
    made = (await client.post("/api/v1/glossary", headers=admin, json={"term": "ARR"})).json()
    r = await client.patch(f"/api/v1/glossary/{made['id']}", headers=admin,
                           json={"definition": "Annual recurring revenue", "synonyms": ["annual run rate", " "],
                                 "rule": "status = 'active'", "always": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["definition"] == "Annual recurring revenue" and body["synonyms"] == ["annual run rate"]
    assert body["rule"] == "status = 'active'" and body["always"] is True
    assert (await client.delete(f"/api/v1/glossary/{made['id']}", headers=admin)).status_code == 204
    assert (await client.get("/api/v1/glossary", headers=admin)).json() == []


async def test_scopes_do_not_cross(client, db_session, world):
    admin = _h(world["admin"])
    # The org-wide routes refuse a connection's, a dataset's and another org's term.
    for t in (world["conn_term"], world["ds_term"], world["theirs"]):
        assert (await client.patch(f"/api/v1/glossary/{t.id}", headers=admin, json={"definition": "x"})).status_code == 404
        assert (await client.delete(f"/api/v1/glossary/{t.id}", headers=admin)).status_code == 404
    assert (await client.patch("/api/v1/glossary/999999", headers=admin, json={"definition": "x"})).status_code == 404
    # Another org never sees this org's org-wide term.
    made = (await client.post("/api/v1/glossary", headers=admin, json={"term": "GMV"})).json()
    assert [t["term"] for t in (await client.get("/api/v1/glossary", headers=_h(world["other"]["member"]))).json()] == ["Their GMV"]
    other_admin = _h(world["other"]["admin"])
    assert (await client.delete(f"/api/v1/glossary/{made['id']}", headers=other_admin)).status_code == 404
    # A connection's routes no longer edit or delete an org-wide term: it is in
    # use on every connection and dataset, so it is changed where it lives.
    src = world["src"].id
    assert (await client.patch(f"/api/v1/data-sources/{src}/glossary/{made['id']}", headers=admin,
                               json={"definition": "x"})).status_code == 404
    assert (await client.delete(f"/api/v1/data-sources/{src}/glossary/{made['id']}", headers=admin)).status_code == 404
    still = (await db_session.execute(select(GlossaryTerm).where(GlossaryTerm.id == made["id"]))).scalar_one()
    assert still.definition is None
