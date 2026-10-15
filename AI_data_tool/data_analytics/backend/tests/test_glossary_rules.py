"""HR evaluation 2026-10-01, blocker 3: the agent did not know the company
rule "current = to_date 9999-01-01". A glossary term can now carry a rule, and
an `always` rule is in the prompt for every question."""
from app.services.agent.context import GlossaryInfo, SchemaContext


def _ctx(*terms):
    ctx = SchemaContext(source_id=1, family="postgresql")
    ctx.glossary.extend(terms)
    return ctx


def test_always_rules_render_for_any_question():
    ctx = _ctx(GlossaryInfo(term="Current employee", definition="still employed",
                            rule="dept_emp.to_date = '9999-01-01'", always=True))
    out = ctx.render(question="employees per department")
    assert "Business rules" in out and "9999-01-01" in out


def test_a_named_rule_rides_on_its_glossary_line():
    ctx = _ctx(GlossaryInfo(term="leaver", definition=None,
                            rule="latest salaries.to_date before 9999-01-01"))
    assert "RULE (apply it)" in ctx.render(question="how many leavers per year")
    assert "RULE" not in ctx.render(question="headcount")


def test_no_rules_no_block():
    assert "Business rules" not in _ctx().render(question="x")


async def test_an_org_wide_term_is_in_the_knowledge_context_of_an_uploaded_dataset(client, db_session, tmp_path):
    """B-21 step 1: a term made org-wide through /glossary (no connection, no
    dataset) reaches the AI context of an uploaded dataset."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import Dataset, DatasetColumn, Organization, Role, User
    from app.services import knowledge
    org = Organization(name="Rules")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    admin = User(org_id=org.id, role_id=role.id, email="rules@x.test", password_hash=hash_password("pw"))
    db_session.add(admin)
    await db_session.flush()
    csv = tmp_path / "sales.csv"
    csv.write_text("region,amount\nNorth,10\n", encoding="utf-8")
    ds = Dataset(name="Demo sales", filename=str(csv), org_id=org.id, row_count=1, col_count=2, created_by=admin.id)
    db_session.add(ds)
    await db_session.flush()
    db_session.add(DatasetColumn(dataset_id=ds.id, name="amount", dtype="number", stats={}))
    await db_session.commit()
    r = await client.post("/api/v1/glossary", json={"term": "GMV", "synonyms": ["turnover"], "maps_to_column": "amount"},
                          headers={"Authorization": f"Bearer {create_access_token(admin.id, org.id)}"})
    assert r.status_code == 200, r.text
    know = await knowledge.for_dataset(db_session, ds)
    assert [g.term for g in know.terms_for("total turnover")] == ["GMV"]
