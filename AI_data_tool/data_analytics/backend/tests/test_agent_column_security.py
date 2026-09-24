"""Column security in the AI agent path (R1 of the competitive assessment).

Before this, ColumnSecurityRule bound only the widget endpoints: the chat
agent showed every column to the model and would happily SELECT one a
role was denied — proven live when a sample returned password hashes. The
enforcement now mirrors the platform's own two conventions:

- IMPORT semantics (dataset mode): denied columns cease to exist — dropped
  from the frame before DuckDB ever sees it, and from the schema context
  before the model does.
- DIRECTQUERY semantics (source mode): fail closed — rules of any dataset
  bound to the source map onto its source_table, the context hides those
  columns, and the V6 rung refuses SQL that names one anyway.

Org admins are exempt, exactly as on the widget endpoints.
"""
import pytest
from sqlalchemy import select

from app.models.models import (AgentStep, ColumnSecurityRule, Dataset,
                               DatasetColumn)
from app.services.agent.context import ObjectInfo, SchemaContext
from app.services.agent.graph import run_agent
from app.services.agent.validate import validate_sql

from tests.test_agent_dataset_mode import _write_csv
from tests.test_agent_graph import (NOT_AMBIGUOUS, ONE_STEP,  # noqa: F401
                                    ScriptedClient, world)


class TestV6Rung:
    def _ctx(self):
        c = SchemaContext(source_id=1, family="postgresql")
        c.objects["users"] = ObjectInfo("users", "table",
                                        None, {"id": "integer", "email": "text",
                                               "salary": "numeric"})
        c.denied_columns = {"users": {"salary"}}
        return c

    def test_a_denied_column_is_refused_wherever_it_appears(self):
        for sql in ("SELECT salary FROM users",
                    "SELECT id FROM users WHERE salary > 5",
                    "SELECT u.salary FROM users u",
                    "SELECT sum(SALARY) FROM users"):
            f = validate_sql(sql, self._ctx())
            assert f is not None and f.rung == "V6", sql
            assert "salary" in f.detail.lower()

    def test_clean_sql_passes_and_empty_map_costs_nothing(self):
        assert validate_sql("SELECT id, email FROM users", self._ctx()) is None
        c = self._ctx()
        c.denied_columns = {}
        assert validate_sql("SELECT salary FROM users", c) is None


@pytest.fixture
async def secured_world(db_session, tmp_path):
    """One dataset (people: id, email, salary) whose analyst role is denied
    `salary`; a second, admin user sees everything."""
    from app.models.models import Organization, Role, User
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    analyst = Role(name="analyst", org_id=org.id, is_org_admin=False)
    admin_role = Role(name="admin", org_id=org.id, is_org_admin=True)
    db_session.add_all([analyst, admin_role])
    await db_session.flush()
    user = User(email="a@corp.com", password_hash="x", org_id=org.id,
                role_id=analyst.id)
    user.role = analyst
    admin = User(email="boss@corp.com", password_hash="x", org_id=org.id,
                 role_id=admin_role.id)
    admin.role = admin_role
    db_session.add_all([user, admin])

    path = _write_csv(tmp_path / "people.csv", ["id", "email", "salary"],
                      [(1, "a@x.com", 100), (2, "b@x.com", 200)])
    ds = Dataset(name="people", org_id=org.id, mode="import", filename=path)
    db_session.add(ds)
    await db_session.flush()
    for name, dtype in [("id", "integer"), ("email", "text"), ("salary", "numeric")]:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
    db_session.add(ColumnSecurityRule(role_id=analyst.id, dataset_id=ds.id,
                                      denied_columns=["salary"]))
    await db_session.commit()
    return {"org": org, "user": user, "admin": admin, "ds": ds}


class TestDatasetMode:
    async def test_the_model_never_sees_the_denied_column(self, db_session,
                                                          secured_world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT id, email FROM people"}])
        run = await run_agent(db_session, question="sample the people",
                              datasets=[secured_world["ds"]],
                              user=secured_world["user"], client=client)
        assert run.status == "ok"
        # The schema context the SQL generator received: salary absent.
        assert "email" in client.generate_calls[0]
        assert "salary" not in client.generate_calls[0]

    async def test_sql_naming_the_denied_column_fails_closed(self, db_session,
                                                             secured_world):
        bad = {"sql": "SELECT email, salary FROM people"}
        client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[bad, bad, bad])
        run = await run_agent(db_session, question="emails and salaries",
                              datasets=[secured_world["ds"]],
                              user=secured_world["user"], client=client)
        await db_session.commit()
        assert run.status == "failed"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert any(f["rung"] == "V6" for f in step.validation_failures)
        # The retry was told exactly which column is blocked.
        assert "salary" in client.generate_calls[1]
        assert "column-security" in client.generate_calls[1] or \
               "blocked by a column-security rule" in client.generate_calls[1]

    async def test_the_frame_itself_lacks_the_column(self, db_session,
                                                     secured_world):
        # Defense in depth: even SQL that sneaks past validation cannot read
        # what is not registered. SELECT * returns only permitted columns.
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT * FROM people"}])
        run = await run_agent(db_session, question="everything",
                              datasets=[secured_world["ds"]],
                              user=secured_world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows is not None
        assert "salary" not in step.result_rows["columns"]
        assert set(step.result_rows["columns"]) == {"id", "email"}

    async def test_an_org_admin_is_exempt(self, db_session, secured_world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT salary FROM people"}])
        run = await run_agent(db_session, question="salaries",
                              datasets=[secured_world["ds"]],
                              user=secured_world["admin"], client=client)
        assert run.status == "ok"
        assert "salary" in client.generate_calls[0]


class TestSourceMode:
    async def test_rules_of_a_bound_dataset_guard_the_live_table(
            self, db_session, world):
        # `world` (test_agent_graph): a live SQLite source with an `orders`
        # catalog (id, total, region). Bind a DirectQuery dataset to that
        # table and deny `total` to the analyst role: the context hides it
        # and V6 refuses SQL that names it — chatting about the table shows
        # no more than charting it would.
        ds = Dataset(name="orders_dq", org_id=world["org"].id,
                     mode="directquery", data_source_id=world["ds"].id,
                     source_table="orders")
        db_session.add(ds)
        await db_session.flush()
        db_session.add(ColumnSecurityRule(role_id=world["role"].id,
                                          dataset_id=ds.id,
                                          denied_columns=["total"]))
        await db_session.commit()

        bad = {"sql": "SELECT sum(total) AS t FROM orders"}
        client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[bad, bad, bad])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        assert run.status == "failed"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert any(f["rung"] == "V6" for f in step.validation_failures)
        assert "total" not in client.generate_calls[0].split("Question:")[0].split("orders")[1][:200]
