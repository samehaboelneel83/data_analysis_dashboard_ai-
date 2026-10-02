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
