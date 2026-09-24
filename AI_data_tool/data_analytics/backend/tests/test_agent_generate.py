"""One generation attempt, and the memory it draws on.

The repair LOOP lives in graph.py; this node is a single attempt whose
prompt carries (a) only the allowed joins, (b) verified examples, and
(c) on retry, the SPECIFIC ladder failure — a model told exactly what was
wrong corrects far more often than one told to try again (D4.4).
"""
from app.models.models import Organization
from app.services.agent.context import JoinInfo, ObjectInfo, SchemaContext
from app.services.agent.memory import recall, remember
from app.services.agent.nodes.generate import GENERATE_SCHEMA, generate_sql


def ctx():
    c = SchemaContext(source_id=1, family="postgresql")
    c.objects["orders"] = ObjectInfo("orders", "table", "Order lines.",
                                     {"id": "integer", "total": "numeric"})
    return c


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply


class TestGenerate:
    async def test_returns_the_sql(self):
        client = FakeClient({"sql": "SELECT sum(total) FROM orders"})
        got = await generate_sql("total sales", ctx(), [], client)
        assert got == "SELECT sum(total) FROM orders"

    async def test_enforced_contract_and_schema(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        assert client.calls[0]["enforce"] is True
        assert client.calls[0]["schema"] is GENERATE_SCHEMA

    async def test_examples_reach_the_prompt(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(),
                           [{"question": "orders per city",
                             "sql": "SELECT city, count(*) FROM orders GROUP BY city"}],
                           client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "orders per city" in text

    async def test_repair_feedback_reaches_the_prompt(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client,
                           feedback="V2: no such column: discount")
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "no such column: discount" in text

    async def test_llm_failure_is_none(self):
        assert await generate_sql("q", ctx(), [], FakeClient(None)) is None

    async def test_a_sample_request_is_a_limited_select_by_contract(self):
        # The companion to classify's rule: once "show me a sample" is a
        # lookup, the SQL for it must be the columns with a LIMIT, not a
        # guess at a metric.
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("show me a sample", ctx(), [], client)
        text = client.calls[0]["messages"][0]["content"]
        assert "the first N rows" in text
        assert "LIMIT 10 when no number is given" in text

    async def test_the_conversation_reaches_the_prompt_with_its_sql(self):
        client = FakeClient({"sql": "SELECT 1"})
        history = [{"role": "user", "content": "orders per city", "sql": [], "results": []},
                   {"role": "assistant", "content": "Cairo 3.",
                    "sql": ["SELECT city, count(*) FROM orders GROUP BY city"],
                    "results": [{"step": "s1", "columns": ["city"], "rows": [["Cairo"]],
                                 "total": 1, "truncated": False}]}]
        await generate_sql("orders per city, Cairo only", ctx(), [], client,
                           history=history)
        text = client.calls[0]["messages"][0]["content"]
        assert "Conversation so far (" in text
        assert "SELECT city, count(*) FROM orders GROUP BY city" in text
        assert "returned 1 rows" in text

    async def test_no_conversation_block_without_history(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        assert "Conversation so far (" not in client.calls[0]["messages"][0]["content"]

    async def test_analyses_available_block_reaches_the_prompt(self):
        """A4: the registry's 'Analyses available' block is part of the
        SQL-generation prompt -- capability discovery, not an invocation
        contract (this node still only ever returns SQL)."""
        from app.services.analysis import registry
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "Analyses available" in text
        for spec in registry.all_analyses():
            assert spec.name in text

    async def test_the_prompt_instructs_base_table_preference(self):
        """H6 fix 1: the wrong-table regression ('5 most common symbols'
        picked a near-duplicate derived table, values off ~200x) — the
        system prompt must now steer toward the base table over a
        near-duplicate derived/normalized/versioned view, using object
        descriptions to pick the most specific, directly-relevant object."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "prefer the BASE TABLE" in system_text
        assert "most specific object" in system_text

    async def test_the_prompt_instructs_canonical_preference(self):
        """T1: an object marked CANONICAL (context.render()'s [CANONICAL ...]
        marker) should beat even the base-table preference."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "CANONICAL" in system_text
        assert "source of truth" in system_text

    async def test_the_prompt_instructs_building_on_parent_step_logic(self):
        """Round-5 fix: a step told 'Step N returned...' by parent_facts
        must build its SQL on that step's logic (subquery/JOIN/WHERE reuse)
        instead of hand-copying sampled values, and a final step whose
        parent already holds the answer must shape it from the same
        source rather than switching to a different convenient column."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "Step N returned" in system_text
        assert "same source" in system_text

    async def test_the_prompt_instructs_dropping_a_refused_join_on_repair(self):
        """Live Q24: a planner-added lookup step's join wasn't even
        proposed, V3 refused it, and repair exhausted re-attempting the
        same join, failing a run whose earlier step already held the
        complete answer. The prompt must tell repair to drop a refused
        join and answer from the permitted tables' own columns."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "do not retry that join another way" in system_text
        assert "identifiers instead of display names" in system_text

    async def test_the_prompt_instructs_using_the_glossary_terms_stored_spelling(self):
        """Verified live: an Arabic glossary synonym matched and the hint
        rendered, but the model still copied the QUESTION's spelling into
        a SQL predicate and got zero rows against the term's canonical
        STORED spelling. The prompt must state the rule generally: the
        glossary TERM is the stored value, never the question's phrasing
        of it."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "the glossary TERM text is the canonical STORED value" in system_text
        assert "never the question's own spelling of it" in system_text


    async def test_the_prompt_instructs_never_using_all_null_columns(self):
        """The measured trap: the agent picked maps_states.students_count for
        a submissions question -- a column literally named what was asked,
        but 100% NULL. context.render() marks such columns 'ALL NULL'; the
        prompt must tell the model never to select/aggregate/filter on one."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "ALL NULL" in system_text
        assert "never" in system_text.lower()


class TestMemory:
    async def test_remember_then_recall_round_trips(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        await remember(db_session, org.id, None, "orders per city",
                       "SELECT city, count(*) FROM orders GROUP BY city")
        await db_session.commit()
        got = await recall(db_session, org.id, None)
        assert got == [{"question": "orders per city",
                        "sql": "SELECT city, count(*) FROM orders GROUP BY city"}]

    async def test_recall_is_org_scoped(self, db_session):
        a, b = Organization(name="A"), Organization(name="B")
        db_session.add_all([a, b])
        await db_session.flush()
        await remember(db_session, a.id, None, "q", "SELECT 1")
        await db_session.commit()
        assert await recall(db_session, b.id, None) == []

    async def test_dataset_key_round_trip(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        await remember(db_session, org.id, None, "orders per city",
                       "SELECT city, count(*) FROM orders GROUP BY city",
                       dataset_key="3,17")
        await db_session.commit()
        got = await recall(db_session, org.id, None, dataset_key="3,17")
        assert got == [{"question": "orders per city",
                        "sql": "SELECT city, count(*) FROM orders GROUP BY city"}]

    async def test_a_different_dataset_key_recalls_nothing(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        await remember(db_session, org.id, None, "q", "SELECT 1",
                       dataset_key="3,17")
        await db_session.commit()
        assert await recall(db_session, org.id, None, dataset_key="99") == []

    async def test_source_mode_recall_never_returns_dataset_rows(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        await remember(db_session, org.id, None, "dataset q", "SELECT 1",
                       dataset_key="3,17")
        await db_session.commit()
        assert await recall(db_session, org.id, None) == []

    async def test_dataset_mode_recall_never_returns_source_rows(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        await remember(db_session, org.id, None, "source q", "SELECT 1")
        await db_session.commit()
        assert await recall(db_session, org.id, None, dataset_key="3,17") == []

class TestOneQueryIsAboutOneGrouping:
    """A UNION ALL that stacks different groupings into one column produces
    rows whose first column means a different thing on different rows.

    Measured live (run 214): "what is this data" over a sales table produced
    `SELECT region, COUNT(*) ... GROUP BY region UNION ALL SELECT country,
    COUNT(*) ... GROUP BY country UNION ALL ...`. The 35 rows that came back
    held regions AND countries AND products in one column named `region`.
    Charted, the axis read `region` while the bars were three different kinds
    of thing -- the chart stated something false about its own axis, and no
    validation rung could see it because every table and column was real."""

    async def test_the_rule_reaches_the_prompt(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("what is this data", ctx(), [], client)
        system = client.calls[0]["messages"][0]["content"]
        assert "NEVER stack different groupings into one column" in system
        assert "its own labelled column" in system

    async def test_the_rule_is_stated_with_the_shape_it_forbids(self):
        """A rule the model cannot recognise in its own output is not a rule:
        the forbidden SQL is spelled out, not merely described."""
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        system = client.calls[0]["messages"][0]["content"]
        assert "UNION ALL SELECT " in system
        assert "GROUP BY country" in system
