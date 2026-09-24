"""The agent's data model.

`agent_steps` is not optional bookkeeping (spec, Data model section): without
a per-node record of what SQL ran, what the ladder rejected and how many
repairs it took, neither the eval gate nor a support conversation has
anything to work from.
"""
import pytest
from sqlalchemy import select

from app.models.models import (AgentMessage, AgentRun, AgentStep, Conversation,
                               DataSource, ObjectRowPolicy, Organization,
                               QueryExample, Role, User)


@pytest.fixture
async def org(db_session):
    o = Organization(name="Acme")
    db_session.add(o)
    await db_session.flush()
    return o


class TestConversationShape:
    async def test_a_conversation_belongs_to_an_org_and_user(self, db_session, org):
        role = Role(org_id=org.id, name="analyst")
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org.id, role_id=role.id, email="a@corp.com",
                    password_hash="x")
        db_session.add(user)
        await db_session.flush()

        conv = Conversation(org_id=org.id, user_id=user.id, title="Revenue Qs")
        db_session.add(conv)
        await db_session.commit()

        row = (await db_session.execute(select(Conversation))).scalar_one()
        assert row.org_id == org.id
        assert row.title == "Revenue Qs"

    async def test_messages_cascade_with_their_conversation(self, db_session, org):
        conv = Conversation(org_id=org.id, user_id=None, title="t")
        db_session.add(conv)
        await db_session.flush()
        db_session.add(AgentMessage(conversation_id=conv.id, role="user",
                                    content="how many orders?"))
        await db_session.commit()
        await db_session.delete(conv)
        await db_session.commit()
        assert (await db_session.execute(select(AgentMessage))).scalars().all() == []


class TestRunRecord:
    async def test_a_run_records_plan_answer_and_status(self, db_session, org):
        run = AgentRun(org_id=org.id, question="total sales by city",
                       status="ok", intent="aggregate",
                       plan=[{"id": "s1", "question": "total sales by city"}],
                       answer="Sales total 12,400 across 3 cities.")
        db_session.add(run)
        await db_session.commit()
        row = (await db_session.execute(select(AgentRun))).scalar_one()
        assert row.plan[0]["id"] == "s1"
        assert row.status == "ok"

    async def test_a_step_records_what_the_ladder_did(self, db_session, org):
        run = AgentRun(org_id=org.id, question="q", status="ok")
        db_session.add(run)
        await db_session.flush()
        db_session.add(AgentStep(
            agent_run_id=run.id, node="s1", status="ok",
            sql="SELECT count(*) FROM orders", rows_returned=1,
            validation_failures=[{"rung": "V2", "detail": "no such column x"}],
            repair_attempts=1, ms=840))
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.validation_failures[0]["rung"] == "V2"
        assert step.repair_attempts == 1

    async def test_a_sink_step_keeps_a_result_snapshot_and_a_run_its_presentation(
            self, db_session, org):
        # The chat draws the result from this snapshot and reloads it with
        # the conversation; before it existed only a row COUNT survived the
        # run, so "present a table" had nothing to present.
        run = AgentRun(org_id=org.id, question="as a bar chart", status="ok",
                       intent="present", presentation={"format": "bar", "limit": None},
                       context_objects=["orders", "customers"])
        db_session.add(run)
        await db_session.flush()
        db_session.add(AgentStep(
            agent_run_id=run.id, node="s1", status="ok",
            sql="SELECT city, count(*) AS n FROM orders GROUP BY city",
            rows_returned=2,
            result_rows={"columns": ["city", "n"], "rows": [["Cairo", 3], ["Giza", 1]],
                         "total": 2, "truncated": False}))
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows["columns"] == ["city", "n"]
        assert step.result_rows["rows"][0] == ["Cairo", 3]
        got = (await db_session.execute(select(AgentRun))).scalar_one()
        assert got.presentation == {"format": "bar", "limit": None}
        assert got.context_objects == ["orders", "customers"]


class TestPolicyAndMemory:
    async def test_a_row_policy_binds_role_to_source_object(self, db_session, org):
        role = Role(org_id=org.id, name="viewer")
        ds = DataSource(name="s", type="postgresql", org_id=org.id, config={})
        db_session.add_all([role, ds])
        await db_session.flush()
        from app.models.models import SourceObject
        obj = SourceObject(data_source_id=ds.id, org_id=org.id,
                           name="orders", kind="table")
        db_session.add(obj)
        await db_session.flush()

        db_session.add(ObjectRowPolicy(org_id=org.id, source_object_id=obj.id,
                                       role_id=role.id,
                                       predicate="region = 'west'"))
        await db_session.commit()
        pol = (await db_session.execute(select(ObjectRowPolicy))).scalar_one()
        assert pol.predicate == "region = 'west'"

    async def test_query_examples_store_the_verified_pair(self, db_session, org):
        db_session.add(QueryExample(org_id=org.id, question="orders per city",
                                    sql="SELECT city, count(*) FROM orders GROUP BY city"))
        await db_session.commit()
        ex = (await db_session.execute(select(QueryExample))).scalar_one()
        assert "GROUP BY" in ex.sql
