"""One question, end to end, with a scripted model and a real SQLite source.

The LLM is faked (deterministic, per-call scripts); the database, catalog,
ladder, policies and executor are real. What these tests pin is the CONTROL
FLOW the spec draws: clarify ends a run, repair is bounded at three, a
failed step never sinks its siblings, and every step leaves an AgentStep row.
"""
import pytest
from sqlalchemy import create_engine, select, text

from app.models.models import (AgentRun, AgentStep, DataSource, Organization,
                               QueryExample, Role, SourceColumn, SourceObject,
                               SourceRelationship, User)
from app.services.agent import executor, graph
from app.services.agent.graph import run_agent


class ScriptedClient:
    """complete_json pops from a script keyed by which schema was asked for."""

    def __init__(self, classify=None, plan=None, generate=None, prose="Answer."):
        self.script = {"classify": list(classify or []),
                       "plan": list(plan or []),
                       "generate": list(generate or [])}
        self.prose = prose
        self.generate_calls = []
        self.explain_calls = []

    async def complete_json(self, messages, schema, **kw):
        props = set(schema.get("properties", {}))
        if "intent" in props:
            return self.script["classify"].pop(0) if self.script["classify"] else None
        if "steps" in props:
            return self.script["plan"].pop(0) if self.script["plan"] else None
        if "sql" in props:
            self.generate_calls.append("".join(m["content"] for m in messages))
            return self.script["generate"].pop(0) if self.script["generate"] else None
        return None

    async def complete(self, messages, **kw):
        # explain() is the only complete() caller with a "Figures:" block;
        # clarify() calls complete() too but with no such marker, so this
        # only ever records explain's prompt.
        joined = "".join(m["content"] for m in messages)
        if "Figures:" in joined:
            self.explain_calls.append(joined)
        return self.prose


@pytest.fixture
async def world(db_session, tmp_path, monkeypatch):
    """An org, a user, a live SQLite source, and its catalog."""
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    role = Role(name="analyst", org_id=org.id)
    db_session.add(role)
    await db_session.flush()
    user = User(email="a@corp.com", password_hash="x", org_id=org.id,
                role_id=role.id)
    user.role = role
    db_session.add(user)

    path = tmp_path / "shop.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL, region TEXT)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10, 'west'), (2, 20, 'east')"))
    monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)

    ds = DataSource(name="shop", type="sqlite", org_id=org.id,
                    config={"filepath": str(path)})
    db_session.add(ds)
    await db_session.flush()
    obj = SourceObject(data_source_id=ds.id, org_id=org.id, name="orders",
                       kind="table")
    db_session.add(obj)
    await db_session.flush()
    for name, dtype in [("id", "integer"), ("total", "numeric"),
                        ("region", "text")]:
        db_session.add(SourceColumn(source_object_id=obj.id, name=name,
                                    dtype=dtype))
    await db_session.commit()
    yield {"org": org, "user": user, "ds": ds, "obj": obj, "role": role}
    eng.dispose()


NOT_AMBIGUOUS = {"intent": "aggregate", "ambiguous": False, "ambiguity_reason": None}
ONE_STEP = {"steps": [{"id": "s1", "question": "total sales", "depends_on": []}]}
TWO_STEP_CHAIN = {"steps": [
    {"id": "s1", "question": "intermediate lookup", "depends_on": []},
    {"id": "s2", "question": "final answer", "depends_on": ["s1"]},
]}


class TestTheHappyPath:
    async def test_question_in_answer_out(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert run.answer == "Answer."
        steps = (await db_session.execute(select(AgentStep))).scalars().all()
        assert len(steps) == 1
        assert steps[0].sql == "SELECT sum(total) AS total FROM orders"
        assert steps[0].rows_returned == 1

    async def test_a_good_answer_is_remembered(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        await run_agent(db_session, question="total sales",
                        source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        ex = (await db_session.execute(select(QueryExample))).scalars().all()
        assert len(ex) == 1 and ex[0].question == "total sales"


class TestClarification:
    async def test_an_ambiguous_question_ends_with_a_question(self, db_session, world):
        client = ScriptedClient(
            classify=[{"intent": "lookup", "ambiguous": True,
                       "ambiguity_reason": "no metric named"}],
            prose="Did you mean revenue or order count?")
        run = await run_agent(db_session, question="show me the numbers",
                              source=world["ds"], user=world["user"],
                              client=client)
        assert run.status == "needs_clarification"
        assert run.answer.endswith("?")
        # Nothing was planned, generated or executed.
        assert client.generate_calls == []


class TestRepairIsBounded:
    async def test_a_rejected_query_is_repaired_with_the_specific_error(
            self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT discount FROM orders"},          # V2 fails
                      {"sql": "SELECT sum(total) AS t FROM orders"}])  # fixed
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert "discount" in client.generate_calls[1], (
            "the retry was not told the specific failure")
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.repair_attempts == 1
        assert step.validation_failures[0]["rung"] == "V2"

    async def test_three_rejections_fail_honestly(self, db_session, world):
        bad = {"sql": "SELECT ghost FROM orders"}
        client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[bad, bad, bad, bad])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        assert run.status == "failed"
        assert len(client.generate_calls) == 3, "repair is bounded at 3 total attempts"


class TestPoliciesBind:
    async def test_a_row_policy_filters_the_agents_query(self, db_session, world,
                                                          monkeypatch):
        from app.models.models import ObjectRowPolicy
        db_session.add(ObjectRowPolicy(org_id=world["org"].id,
                                       source_object_id=world["obj"].id,
                                       role_id=world["role"].id,
                                       predicate="region = 'west'"))
        await db_session.commit()

        # A row count of 1 proves nothing here: `SELECT sum(total)` (no
        # GROUP BY) always returns exactly one row, filtered or not. Record
        # the actual computed VALUE by wrapping the real executor, so the
        # test proves the predicate changed the aggregate, not merely that
        # its text landed in the SQL string.
        recorded = []
        real_execute = graph.execute_sql

        async def recording_execute(sql, cfg, family, **kwargs):
            rows, err = await real_execute(sql, cfg, family, **kwargs)
            recorded.append(rows)
            return rows, err

        monkeypatch.setattr(graph, "execute_sql", recording_execute)

        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        # west only: 10, not 30 — filtered BEFORE aggregation.
        assert recorded == [[{"total": 10.0}]]
        assert step.rows_returned == 1
        assert "region = 'west'" in step.sql


class TestExplainSeesOnlySinkSteps:
    """H6 follow-up: on a multi-step run, explain must never see an
    intermediate step's raw rows — only the DAG's sink (the step no other
    step depends_on, i.e. the actual final answer)."""

    async def test_a_two_step_chains_intermediate_rows_never_reach_explain(
            self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[TWO_STEP_CHAIN],
            generate=[{"sql": "SELECT total AS leak_marker FROM orders WHERE id = 1"},
                      {"sql": "SELECT total AS final_marker FROM orders WHERE id = 2"}])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert len(client.explain_calls) == 1
        prompt = client.explain_calls[0]
        assert "final_marker" in prompt
        assert "leak_marker" not in prompt

    async def test_a_single_step_run_still_shows_its_own_rows(
            self, db_session, world):
        """The one step IS the sink — single-step behaviour is unchanged."""
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert "total" in client.explain_calls[0]


class TestPlannerDegradesGracefully:
    async def test_a_failed_plan_becomes_a_single_step(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[None],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        assert run.status == "ok"


class TestParentFactsCarryTotalCount:
    """Round-5 bug: parent_facts showed only 5 sample rows with no total
    count or behavioural rule, so a downstream step read the 5 as complete
    and enumerated them literally in a `NOT IN (...)` clause. Now the
    prompt must state the TOTAL row count and a re-derive rule."""

    async def _world_with_rows(self, db_session, tmp_path, monkeypatch, n):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        role = Role(name="analyst", org_id=org.id)
        db_session.add(role)
        await db_session.flush()
        user = User(email="a@corp.com", password_hash="x", org_id=org.id,
                    role_id=role.id)
        user.role = role
        db_session.add(user)

        path = tmp_path / "shop.db"
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL)"))
            for i in range(1, n + 1):
                conn.execute(text(f"INSERT INTO orders VALUES ({i}, {float(i)})"))
        monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)

        ds = DataSource(name="shop", type="sqlite", org_id=org.id,
                        config={"filepath": str(path)})
        db_session.add(ds)
        await db_session.flush()
        obj = SourceObject(data_source_id=ds.id, org_id=org.id, name="orders",
                           kind="table")
        db_session.add(obj)
        await db_session.flush()
        for cname, dtype in [("id", "integer"), ("total", "numeric")]:
            db_session.add(SourceColumn(source_object_id=obj.id, name=cname,
                                        dtype=dtype))
        await db_session.commit()
        return {"org": org, "user": user, "ds": ds}

    async def test_an_eight_row_parent_states_total_and_never_enumerate_rule(
            self, db_session, tmp_path, monkeypatch):
        world = await self._world_with_rows(db_session, tmp_path, monkeypatch, 8)
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[TWO_STEP_CHAIN],
            generate=[{"sql": "SELECT id FROM orders"},
                      {"sql": "SELECT id FROM orders"}])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        prompt = client.generate_calls[1]
        assert "returned 8 rows" in prompt
        assert "showing first 5" in prompt
        assert "NEVER enumerate the sampled values as literals" in prompt

    async def test_a_three_row_parent_says_all_rows(
            self, db_session, tmp_path, monkeypatch):
        world = await self._world_with_rows(db_session, tmp_path, monkeypatch, 3)
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[TWO_STEP_CHAIN],
            generate=[{"sql": "SELECT id FROM orders"},
                      {"sql": "SELECT id FROM orders"}])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        prompt = client.generate_calls[1]
        assert "all 3 rows" in prompt


class TestRefusedJoinIsNotRetried:
    """Live Q24: a planner-added lookup step's join wasn't even proposed,
    V3 refused it, and repair exhausted re-attempting the same join,
    failing a run whose step already held the complete answer. The V3
    repair feedback must tell the model to drop the join, not retry it."""

    @pytest.fixture
    async def two_table_world(self, db_session, tmp_path, monkeypatch):
        """orders and students, with NO relationship declared between them —
        any join across the two is refused by V3 as not confirmed."""
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        role = Role(name="analyst", org_id=org.id)
        db_session.add(role)
        await db_session.flush()
        user = User(email="a@corp.com", password_hash="x", org_id=org.id,
                    role_id=role.id)
        user.role = role
        db_session.add(user)

        path = tmp_path / "shop.db"
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE orders (id INTEGER, student_id INTEGER)"))
            conn.execute(text("CREATE TABLE students (id INTEGER, name TEXT)"))
            conn.execute(text("INSERT INTO orders VALUES (1, 1)"))
            conn.execute(text("INSERT INTO students VALUES (1, 'Ann')"))
        monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)

        ds = DataSource(name="shop", type="sqlite", org_id=org.id,
                        config={"filepath": str(path)})
        db_session.add(ds)
        await db_session.flush()

        for name, cols in [("orders", [("id", "integer"),
                                       ("student_id", "integer")]),
                          ("students", [("id", "integer"), ("name", "text")])]:
            o = SourceObject(data_source_id=ds.id, org_id=org.id, name=name,
                             kind="table")
            db_session.add(o)
            await db_session.flush()
            for cname, dtype in cols:
                db_session.add(SourceColumn(source_object_id=o.id, name=cname,
                                            dtype=dtype))
        await db_session.commit()
        return {"org": org, "user": user, "ds": ds}

    async def test_the_v3_feedback_tells_repair_not_to_retry_the_join(
            self, db_session, two_table_world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[
                {"sql": "SELECT o.id, s.name FROM orders o "
                       "JOIN students s ON o.student_id = s.id"},  # V3 refused
                {"sql": "SELECT id, student_id FROM orders"},      # join-free
            ])
        run = await run_agent(db_session, question="order student ids",
                              source=two_table_world["ds"],
                              user=two_table_world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert len(client.generate_calls) == 2
        assert ("Do not attempt this join again in any form" in
               client.generate_calls[1])


class TestJoinRouteReachesGenerate:
    """T4: two known tables named in a step's question, with no direct edge
    between them, should hand generate a resolved multi-hop route — the same
    "extra context appended to the question" mechanism parent_facts already
    uses (graph.py's node runner)."""

    @pytest.fixture
    async def two_hop_world(self, db_session, tmp_path, monkeypatch):
        """orders -> customers -> regions, confirmed/declared only, so a
        question naming orders and regions has no DIRECT edge and needs the
        two-hop route."""
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        role = Role(name="analyst", org_id=org.id)
        db_session.add(role)
        await db_session.flush()
        user = User(email="a@corp.com", password_hash="x", org_id=org.id,
                    role_id=role.id)
        user.role = role
        db_session.add(user)

        path = tmp_path / "shop.db"
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as conn:
            conn.execute(text(
                "CREATE TABLE orders (id INTEGER, customer_id INTEGER)"))
            conn.execute(text(
                "CREATE TABLE customers (id INTEGER, region_id INTEGER)"))
            conn.execute(text("CREATE TABLE regions (id INTEGER, name TEXT)"))
            conn.execute(text("INSERT INTO orders VALUES (1, 1)"))
            conn.execute(text("INSERT INTO customers VALUES (1, 1)"))
            conn.execute(text("INSERT INTO regions VALUES (1, 'west')"))
        monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)

        ds = DataSource(name="shop", type="sqlite", org_id=org.id,
                        config={"filepath": str(path)})
        db_session.add(ds)
        await db_session.flush()

        objs = {}
        for name, cols in [("orders", [("id", "integer"),
                                       ("customer_id", "integer")]),
                          ("customers", [("id", "integer"),
                                        ("region_id", "integer")]),
                          ("regions", [("id", "integer"), ("name", "text")])]:
            o = SourceObject(data_source_id=ds.id, org_id=org.id, name=name,
                             kind="table")
            db_session.add(o)
            await db_session.flush()
            objs[name] = o
            for cname, dtype in cols:
                db_session.add(SourceColumn(source_object_id=o.id, name=cname,
                                            dtype=dtype))

        db_session.add(SourceRelationship(
            data_source_id=ds.id, org_id=org.id,
            from_object_id=objs["orders"].id, from_column="customer_id",
            to_object_id=objs["customers"].id, to_column="id",
            source="declared", confidence=1.0))
        db_session.add(SourceRelationship(
            data_source_id=ds.id, org_id=org.id,
            from_object_id=objs["customers"].id, from_column="region_id",
            to_object_id=objs["regions"].id, to_column="id",
            source="confirmed", confidence=1.0))
        await db_session.commit()
        yield {"org": org, "user": user, "ds": ds}
        eng.dispose()

    async def test_the_route_reaches_generates_prompt(self, db_session, two_hop_world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[
                {"steps": [{"id": "s1",
                           "question": "orders joined to regions",
                           "depends_on": []}]}],
            generate=[{"sql": "SELECT o.id FROM orders o "
                             "JOIN customers c ON o.customer_id = c.id "
                             "JOIN regions r ON c.region_id = r.id"}])
        run = await run_agent(db_session, question="orders joined to regions",
                              source=two_hop_world["ds"],
                              user=two_hop_world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert len(client.generate_calls) == 1
        prompt = client.generate_calls[0]
        assert ("Join route: orders.customer_id = customers.id "
               "THEN customers.region_id = regions.id") in prompt

    async def test_no_route_when_fewer_than_two_tables_are_named(
            self, db_session, two_hop_world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT id FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=two_hop_world["ds"],
                              user=two_hop_world["user"], client=client)
        assert run.status == "ok"
        assert "Join route:" not in client.generate_calls[0]


CHAT = {"intent": "chat", "ambiguous": False, "ambiguity_reason": None}


class TalkativeClient(ScriptedClient):
    """ScriptedClient that also keeps every complete() prompt, so a test can
    read what the conversational reply was actually shown."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.prose_calls = []

    async def complete(self, messages, **kw):
        self.prose_calls.append("".join(m["content"] for m in messages))
        return await super().complete(messages, **kw)


class MuteClient(TalkativeClient):
    """The model endpoint is unreachable: complete() returns None."""

    async def complete(self, messages, **kw):
        await super().complete(messages, **kw)
        return None


class TestAMessageThatIsNotAQuestion:
    """"hi" used to come back as ten rows of a table.

    The classifier's enum held six DATA intents and was sent with
    enforce=True, so there was no legal way for the model to say "this asks
    nothing about the data"; `lookup` was the nearest available answer and the
    graph planned, queried and narrated it. The seventh intent leaves the
    pipeline here, before plan, SQL or explain -- nothing is queried because
    nothing was asked."""

    async def test_a_greeting_never_reaches_the_database(self, db_session, world):
        client = TalkativeClient(classify=[CHAT],
                                 prose="Hello! Ask me anything about this data.")
        run = await run_agent(db_session, question="hi", source=world["ds"],
                              user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert run.intent == "chat"
        assert run.answer == "Hello! Ask me anything about this data."
        # No plan, no SQL, no step -- and therefore no rows to narrate.
        assert run.plan is None
        assert client.generate_calls == []
        assert (await db_session.execute(select(AgentStep))).scalars().all() == []

    async def test_it_is_not_sent_back_as_a_clarification(self, db_session, world):
        """A greeting is not a tie between two readings, so "which table did
        you mean?" is as wrong an answer as the table itself. The chat branch
        is checked BEFORE ambiguity for exactly this."""
        client = TalkativeClient(
            classify=[{"intent": "chat", "ambiguous": True,
                       "ambiguity_reason": "no table named"}],
            prose="Hi there.")
        run = await run_agent(db_session, question="hi", source=world["ds"],
                              user=world["user"], client=client)
        assert run.status == "ok"
        assert run.answer == "Hi there."

    async def test_the_reply_knows_what_the_data_is_about_but_states_no_figures(
            self, db_session, world):
        client = TalkativeClient(classify=[CHAT], prose="Hi.")
        await run_agent(db_session, question="what can you do",
                        source=world["ds"], user=world["user"], client=client)
        prompt = client.prose_calls[0]
        # It may say the data is about orders...
        assert "orders" in prompt
        # ...but nothing has been queried, so any number would be invented.
        assert "MUST NOT state any row count" in prompt

    async def test_it_never_denies_something_it_can_do(self, db_session, world):
        """Live, this prompt produced "I can't generate charts directly" — to
        a person looking at a product whose job is charts. An earlier version
        told the model not to offer what the page cannot do, and it invented
        a limitation; the prompt now lists what it CAN do and forbids denying
        any of it."""
        client = TalkativeClient(classify=[CHAT], prose="Hi.")
        await run_agent(db_session, question="hi", source=world["ds"],
                        user=world["user"], client=client)
        prompt = client.prose_calls[0]
        assert "NEVER say you cannot" in prompt
        for capability in ("draw a bar, line or pie chart", "show the "
                           "matching rows", "export it as CSV"):
            assert capability in prompt

    async def test_a_request_to_act_is_told_where_the_action_lives(
            self, db_session, world):
        client = TalkativeClient(classify=[CHAT], prose="Datasets are created on the Datasets page.")
        run = await run_agent(db_session, question="create a new dataset",
                              source=world["ds"], user=world["user"], client=client)
        assert run.status == "ok"
        assert client.generate_calls == []
        assert "You take NO actions" in client.prose_calls[0]
        assert "Never describe an action as done" in client.prose_calls[0]

    async def test_an_unreachable_model_still_answers(self, db_session, world):
        """A greeting does not need a model to be answered, so it must not
        fail when there is none -- unlike a real question, where guessing
        would be the dishonest option."""
        from app.services.agent.nodes.converse import FALLBACK
        client = MuteClient(classify=[CHAT])
        run = await run_agent(db_session, question="hi", source=world["ds"],
                              user=world["user"], client=client)
        assert run.status == "ok"
        assert run.answer == FALLBACK

class TestTheClassifiersDashboardVerdict:
    async def test_it_reaches_the_designer_instead_of_the_planner(
            self, db_session, world, monkeypatch):
        """"choose the best table to draw a useful graph for me" has no
        "dashboard" in it, so the word check let it through; the classifier
        said `suggest_dashboard`, and the graph -- which only ever routed that
        intent from the word check -- planned it as SQL and dumped ten rows,
        then called the dump "the best table". A verdict the enum offers has
        to lead somewhere."""
        seen = {}

        async def fake_suggest(db, run, started, source, user, question, client=None):
            seen["question"] = question
            return graph._finish(run, started, status="ok", answer="designed")

        monkeypatch.setattr(graph, "_suggest_dashboards", fake_suggest)
        client = ScriptedClient(classify=[{
            "intent": "suggest_dashboard", "ambiguous": False, "ambiguity_reason": None}])
        run = await run_agent(db_session, question="pick the best table to graph",
                              source=world["ds"], user=world["user"], client=client)
        assert run.answer == "designed"
        assert seen["question"] == "pick the best table to graph"
        assert client.generate_calls == []


class TestTheDashboardIsForWhoTheyAre:
    async def test_what_they_said_beats_their_account_role(
            self, db_session, world, monkeypatch):
        """The account says Platform Admin; the request says department
        manager. The designer, the answer and the label on the created
        dashboard all follow the request."""
        seen = {}

        async def fake_design(catalog, for_role, goal=None, **kw):
            seen["for_role"] = for_role
            return [{"title": "Dept", "sql": "SELECT 1 AS n", "widgets": []}], ""

        from app.services import suggest_dashboard as sd
        monkeypatch.setattr(sd, "suggest_dashboards", fake_design)
        monkeypatch.setattr(graph, "_review_proposal", None, raising=False)

        class Client(ScriptedClient):
            async def complete_json(self, messages, schema, **kw):
                if "persona" in set(schema.get("properties", {})):
                    return {"persona": "department manager"}
                return await super().complete_json(messages, schema, **kw)

        client = Client(classify=[{"intent": "suggest_dashboard",
                                   "ambiguous": False, "ambiguity_reason": None}])
        run = await run_agent(
            db_session, question="i am a department manager, i need a dashboard",
            source=world["ds"], user=world["user"], client=client)
        assert seen["for_role"] == "department manager"
        assert run.presentation["for_role"] == "department manager"
        assert "for a department manager" in run.answer

    async def test_the_role_is_the_fallback(self, db_session, world, monkeypatch):
        seen = {}

        async def fake_design(catalog, for_role, goal=None, **kw):
            seen["for_role"] = for_role
            return [{"title": "T", "sql": "SELECT 1 AS n", "widgets": []}], ""

        from app.services import suggest_dashboard as sd
        monkeypatch.setattr(sd, "suggest_dashboards", fake_design)
        # ScriptedClient answers None to the persona schema: nothing stated.
        client = ScriptedClient(classify=[{"intent": "suggest_dashboard",
                                           "ambiguous": False, "ambiguity_reason": None}])
        run = await run_agent(db_session, question="suggest a dashboard",
                              source=world["ds"], user=world["user"], client=client)
        assert seen["for_role"] == world["role"].name
        assert run.presentation["for_role"] == world["role"].name
