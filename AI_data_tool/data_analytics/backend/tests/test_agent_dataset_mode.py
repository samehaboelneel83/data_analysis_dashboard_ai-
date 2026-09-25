"""The multi-mode amendment (Tasks 16-17): the agent answers over uploaded
datasets exactly as it answers over DirectQuery — one SQL surface, DuckDB
standing in for the customer's engine, dataset RLS applied to the BASE frame
before it ever enters DuckDB. What's pinned here: a confirmed Relationship
lets the model join two files; an inferred one is rejected the same way an
inferred SourceRelationship is (F1, unchanged); dataset RLS filters the
aggregate the same way ObjectRowPolicy does for DirectQuery; cross-org
dataset ids 404 like every other org-scoped resource; the row cap holds.
"""
import pytest
from sqlalchemy import select

from app.models.models import (AgentStep, Dataset, DatasetColumn,
                               Organization, Relationship, Role,
                               RowSecurityRule, User)
from app.services.agent.executor import execute_on_datasets
from app.services.agent.graph import run_agent

from .test_agent_graph import NOT_AMBIGUOUS, ONE_STEP, ScriptedClient
from .test_agent_results_graph import FollowupClient


def _write_csv(path, header, rows):
    lines = [",".join(header)]
    lines += [",".join(str(v) for v in row) for row in rows]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


@pytest.fixture
async def joined_world(db_session, tmp_path):
    """Two datasets, joinable on orders.region_id = regions.id."""
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

    orders_path = _write_csv(tmp_path / "orders.csv",
                             ["id", "total", "region_id"],
                             [(1, 10, 1), (2, 20, 2)])
    regions_path = _write_csv(tmp_path / "regions.csv",
                              ["id", "name"], [(1, "west"), (2, "east")])

    orders = Dataset(name="orders", org_id=org.id, mode="import",
                     filename=orders_path)
    regions = Dataset(name="regions", org_id=org.id, mode="import",
                      filename=regions_path)
    db_session.add_all([orders, regions])
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=orders.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=orders.id, name="total", dtype="numeric"),
        DatasetColumn(dataset_id=orders.id, name="region_id", dtype="integer"),
        DatasetColumn(dataset_id=regions.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=regions.id, name="name", dtype="text"),
    ])
    await db_session.commit()
    yield {"org": org, "user": user, "role": role,
          "orders": orders, "regions": regions}


@pytest.fixture
async def single_world(db_session, tmp_path):
    """One dataset (orders: id, total, region) — the RLS pinning test."""
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

    orders_path = _write_csv(tmp_path / "orders.csv",
                             ["id", "total", "region"],
                             [(1, 10, "west"), (2, 20, "east")])
    orders = Dataset(name="orders", org_id=org.id, mode="import",
                     filename=orders_path)
    db_session.add(orders)
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=orders.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=orders.id, name="total", dtype="numeric"),
        DatasetColumn(dataset_id=orders.id, name="region", dtype="text"),
    ])
    await db_session.commit()
    yield {"org": org, "user": user, "role": role, "orders": orders}


JOIN_SQL = ("SELECT r.name, sum(o.total) AS total FROM orders o "
           "JOIN regions r ON o.region_id = r.id GROUP BY r.name")


class TestDatasetJoin:
    async def test_a_confirmed_relationship_lets_two_files_be_joined(
            self, db_session, joined_world):
        db_session.add(Relationship(
            org_id=joined_world["org"].id,
            from_dataset_id=joined_world["orders"].id, from_column="region_id",
            to_dataset_id=joined_world["regions"].id, to_column="id",
            source="confirmed"))
        await db_session.commit()

        client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[{"sql": JOIN_SQL}])
        run = await run_agent(
            db_session, question="total sales by region",
            datasets=[joined_world["orders"], joined_world["regions"]],
            user=joined_world["user"], client=client)
        await db_session.commit()

        assert run.status == "ok"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.sql == JOIN_SQL
        assert step.rows_returned == 2

    async def test_the_same_join_is_rejected_when_the_relationship_is_only_inferred(
            self, db_session, joined_world):
        db_session.add(Relationship(
            org_id=joined_world["org"].id,
            from_dataset_id=joined_world["orders"].id, from_column="region_id",
            to_dataset_id=joined_world["regions"].id, to_column="id",
            source="inferred"))
        await db_session.commit()

        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": JOIN_SQL}] * 3)
        run = await run_agent(
            db_session, question="total sales by region",
            datasets=[joined_world["orders"], joined_world["regions"]],
            user=joined_world["user"], client=client)
        await db_session.commit()

        assert run.status == "failed"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.validation_failures[0]["rung"] == "V3"


class TestDatasetRLS:
    async def test_a_dataset_rls_rule_filters_the_aggregate(
            self, db_session, single_world, monkeypatch):
        db_session.add(RowSecurityRule(
            role_id=single_world["role"].id, dataset_id=single_world["orders"].id,
            filter_expr="region == 'west'"))
        await db_session.commit()

        # A row count of 1 proves nothing (SELECT sum(...) with no GROUP BY
        # always returns one row, filtered or not) — record the actual
        # computed VALUE by wrapping the real executor, exactly like
        # TestPoliciesBind does for the DirectQuery path.
        import app.services.agent.graph as graph_module
        recorded = []
        real_execute = graph_module.execute_on_datasets

        async def recording_execute(sql, frames, **kwargs):
            rows, err = await real_execute(sql, frames, **kwargs)
            recorded.append(rows)
            return rows, err

        monkeypatch.setattr(graph_module, "execute_on_datasets", recording_execute)

        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(
            db_session, question="total sales",
            datasets=[single_world["orders"]],
            user=single_world["user"], client=client)
        await db_session.commit()

        assert run.status == "ok"
        # west only: 10, not 30 — filtered on the BASE frame, before DuckDB
        # ever aggregates it.
        assert recorded == [[{"total": 10.0}]]


class TestConversationInXOR:
    """ConversationIn requires exactly one of data_source_id / dataset_ids —
    this gates which security branch `ask` later takes (org-checked
    DataSource vs org-checked datasets), so both malformed shapes must 422
    before either branch is ever reached."""

    async def test_both_data_source_id_and_dataset_ids_set_is_422(
            self, client, auth_headers, two_orgs, db_session, tmp_path):
        from app.models.models import DataSource

        path = _write_csv(tmp_path / "x.csv", ["id"], [(1,)])
        ds = Dataset(name="x", org_id=two_orgs["a"]["org"].id, mode="import",
                    filename=path)
        src = DataSource(name="wh", type="postgresql",
                         org_id=two_orgs["a"]["org"].id)
        db_session.add_all([ds, src])
        await db_session.commit()

        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": src.id,
                                    "dataset_ids": [ds.id]},
                              headers=auth_headers["a"])
        assert r.status_code == 422

    async def test_neither_data_source_id_nor_dataset_ids_set_is_422(
            self, client, auth_headers, two_orgs):
        r = await client.post("/api/v1/agent/conversations", json={},
                              headers=auth_headers["a"])
        assert r.status_code == 422


class TestCrossOrgDataset:
    async def test_a_dataset_id_from_another_org_is_404_on_create(
            self, client, auth_headers, two_orgs, db_session, tmp_path):
        path = _write_csv(tmp_path / "x.csv", ["id"], [(1,)])
        ds_b = Dataset(name="x", org_id=two_orgs["b"]["org"].id, mode="import",
                       filename=path)
        db_session.add(ds_b)
        await db_session.commit()

        r = await client.post("/api/v1/agent/conversations",
                              json={"dataset_ids": [ds_b.id]},
                              headers=auth_headers["a"])
        assert r.status_code == 404

    async def test_a_dataset_id_from_another_org_is_404_on_ask(
            self, client, auth_headers, two_orgs, db_session, tmp_path):
        path = _write_csv(tmp_path / "x.csv", ["id"], [(1,)])
        ds_a = Dataset(name="x", org_id=two_orgs["a"]["org"].id, mode="import",
                       filename=path)
        ds_b = Dataset(name="y", org_id=two_orgs["b"]["org"].id, mode="import",
                       filename=path)
        db_session.add_all([ds_a, ds_b])
        await db_session.commit()

        r = await client.post("/api/v1/agent/conversations",
                              json={"dataset_ids": [ds_a.id]},
                              headers=auth_headers["a"])
        cid = r.json()["id"]

        # Smuggle another org's dataset id onto the stored conversation, the
        # way a bug (not the API, which already validated at create time)
        # might — `ask` must re-check every id, not trust what's stored.
        from app.models.models import Conversation
        conv = await db_session.get(Conversation, cid)
        conv.dataset_ids = [ds_a.id, ds_b.id]
        await db_session.commit()

        probe = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                  json={"question": "q"},
                                  headers=auth_headers["a"])
        assert probe.status_code == 404


class TestRowCap:
    async def test_execute_on_datasets_respects_the_row_cap(self, monkeypatch):
        import pandas as pd

        from app.core.config import settings

        monkeypatch.setattr(settings, "agent_row_cap", 2)
        frame = pd.DataFrame({"n": [1, 2, 3, 4, 5]})
        rows, error = await execute_on_datasets(
            "SELECT n FROM t ORDER BY n", {"t": frame})
        assert error is None
        assert len(rows) == 2


class TestF4FrameFilteringOrder:
    async def test_rls_filters_the_base_frame_before_duckdb_registration(
            self, db_session, single_world, monkeypatch):
        """F4 pin: the dataset path applies apply_rls_filter to the BASE
        frame before it is ever registered with DuckDB, and never to the
        already-computed result rows -- the same WHERE-before-aggregation
        guarantee policy.py's SQL predicate injection gives DirectQuery,
        enforced here in pandas instead. Assert via call order and the row
        counts each call actually saw: apply_rls_filter must see the FULL
        base frame, and execute_on_datasets must receive the frame already
        reduced by the filter."""
        db_session.add(RowSecurityRule(
            role_id=single_world["role"].id, dataset_id=single_world["orders"].id,
            filter_expr="region == 'west'"))
        await db_session.commit()

        import app.services.agent.graph as graph_module

        call_order = []
        real_apply_rls = graph_module.widget_data.apply_rls_filter
        real_execute = graph_module.execute_on_datasets

        def recording_apply_rls(frame, expr):
            call_order.append(("apply_rls_filter", len(frame)))
            return real_apply_rls(frame, expr)

        async def recording_execute(sql, frames, **kwargs):
            for name, frame in frames.items():
                call_order.append(("execute_on_datasets", name, len(frame)))
            return await real_execute(sql, frames, **kwargs)

        monkeypatch.setattr(graph_module.widget_data, "apply_rls_filter",
                            recording_apply_rls)
        monkeypatch.setattr(graph_module, "execute_on_datasets", recording_execute)

        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(
            db_session, question="total sales",
            datasets=[single_world["orders"]],
            user=single_world["user"], client=client)
        await db_session.commit()

        assert run.status == "ok"
        assert [c[0] for c in call_order] == ["apply_rls_filter", "execute_on_datasets"]
        # apply_rls_filter saw the FULL base frame -- both rows (west + east).
        assert call_order[0][1] == 2
        # execute_on_datasets received the frame already reduced to west only.
        assert call_order[1][2] == 1


class TestMemoryScopedInDatasetMode:
    async def test_dataset_mode_calls_recall_and_remember_with_dataset_key(
            self, db_session, single_world, monkeypatch):
        """Dataset-mode memory is not skipped -- it's scoped by dataset_key
        (the sorted dataset ids), which keeps a dataset-mode run from ever
        seeing the ORG's DirectQuery few-shot examples (SQL written against
        tables that may not exist in this dataset's own catalog) without
        giving up few-shot learning altogether. Pin that both recall and
        remember are invoked with the single dataset's id as the key."""
        import app.services.agent.graph as graph_module

        recall_calls = []
        remember_calls = []

        async def fake_recall(db, org_id, source_id, dataset_key=None, limit=5,
                              question=None):
            recall_calls.append((org_id, source_id, dataset_key))
            return []

        async def fake_remember(db, org_id, source_id, question, sql,
                                user_id=None, dataset_key=None):
            remember_calls.append((org_id, source_id, question, sql, dataset_key))

        monkeypatch.setattr(graph_module.memory, "recall", fake_recall)
        monkeypatch.setattr(graph_module.memory, "remember", fake_remember)

        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(
            db_session, question="total sales",
            datasets=[single_world["orders"]],
            user=single_world["user"], client=client)
        await db_session.commit()

        expected_key = str(single_world["orders"].id)
        assert run.status == "ok"
        assert recall_calls == [(single_world["org"].id, None, expected_key)]
        assert remember_calls == [(single_world["org"].id, None, "total sales",
                                   "SELECT sum(total) AS total FROM orders",
                                   expected_key)]


class TestFilesystemLockdown:
    async def test_read_csv_never_returns_rows_even_if_it_slipped_past_the_parser(
            self, tmp_path):
        """Defence in depth (item 8): V1-V3 already refuse SQL that names a
        table not in the catalog, and read_csv('x.csv') has no registered
        DuckDB relation, so it should never get this far. This test proves
        the SECOND independent layer holds on its own -- even if a future
        parser gap let a read_csv(...)/read_parquet(...) call through,
        DuckDB's own enable_external_access=false must refuse it: an error
        tuple, never rows, and never actual file contents."""
        secret = tmp_path / "x.csv"
        secret.write_text("secret\n1\n", encoding="utf-8")

        rows, error = await execute_on_datasets(
            f"SELECT * FROM read_csv('{secret.as_posix()}')", {})
        assert rows is None
        assert error is not None


class TestJsonSafety:
    async def test_a_null_float_cell_comes_back_as_none_not_nan(self):
        """df.where(pd.notnull(df), None) alone does not do this on a
        float64 column -- pandas coerces the injected None straight back to
        NaN. A NaN in a JSON response either serializes as the non-standard
        literal `NaN` or breaks strict encoders outright, so this must be a
        real None, not a float that merely prints as `nan`."""
        import pandas as pd

        frame = pd.DataFrame({"a": [1.0, None]})
        rows, error = await execute_on_datasets(
            "SELECT a FROM t ORDER BY a NULLS LAST", {"t": frame})
        assert error is None
        assert rows[-1]["a"] is None

class TestAChartAskedForBeforeAnythingIsOnScreen:
    """"i need chart" as the second message of a thread.

    There is no result to re-draw and the message names no columns, so the
    product used to answer it as small talk -- "I can't generate charts
    directly", which is false. The missing piece is WHICH TWO COLUMNS, and in
    dataset mode that is answerable from the data itself: the same rule that
    picks the axes of a result on screen (services/agent/charts.py), applied
    to the dataset.
    """

    GREETED = [{"role": "user", "content": "hi", "sql": [], "results": []},
               {"role": "assistant", "content": "Hello! Ask me anything.",
                "sql": [], "results": []}]

    async def test_it_asks_which_columns_using_the_datasets_own(
            self, db_session, single_world):
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "Draw a chart",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need chart",
                              datasets=[single_world["orders"]],
                              user=single_world["user"], client=client,
                        history=self.GREETED)
        await db_session.commit()
        assert run.status == "needs_clarification", run.error
        assert run.presentation["kind"] == "choices"
        # region labels; id and total are the two things that could size a
        # bar -- every option names columns this dataset actually has.
        assert set(run.presentation["options"]) == {"Chart id by region",
                                                    "Chart total by region"}
        # Nothing was queried to ask a question.
        assert client.classify_calls == []
        assert client.generate_calls == []
        assert (await db_session.execute(select(AgentStep))).scalars().all() == []

    async def test_choosing_a_pair_goes_and_gets_the_rows_then_draws_them(
            self, db_session, single_world):
        """The option, clicked. The pair is known now but the rows are not,
        so the run continues as a data question -- and the chart rides to the
        end with it, because a chart of nothing is not an answer."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "Draw total by region",
                       "format": "bar", "limit": None, "x": "region", "y": "total"}],
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, sum(total) AS total "
                              "FROM orders GROUP BY region"}])
        run = await run_agent(db_session, question="Chart total by region",
                              datasets=[single_world["orders"]],
                              user=single_world["user"], client=client,
                        history=self.GREETED)
        await db_session.commit()
        assert run.status == "ok"
        assert client.generate_calls, "the rows had to be fetched"
        assert run.presentation == {"format": "bar", "limit": None,
                                    "x": "region", "y": "total"}
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows["columns"] == ["region", "total"]

    async def test_the_question_asked_is_built_from_the_columns_chosen(
            self, db_session, single_world):
        """The one rewrite made without a model: both names came from the
        dataset's own columns a moment earlier, so there is nothing to guess
        and nothing to invent."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "ignored",
                       "format": "bar", "limit": None, "x": "region", "y": "total"}],
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, sum(total) AS total "
                              "FROM orders GROUP BY region"}])
        await run_agent(db_session, question="Chart total by region",
                        datasets=[single_world["orders"]],
                        user=single_world["user"], client=client,
                        history=self.GREETED)
        assert "total by region" in client.classify_calls[0]

    async def test_a_chart_over_several_datasets_asks_without_guessing(
            self, db_session, joined_world):
        """Two files in scope: which one to chart is not this node's to
        decide, so it asks plainly rather than offering options from the
        wrong file."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "Draw a chart",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need chart",
                              datasets=[joined_world["orders"],
                                        joined_world["regions"]],
                              user=joined_world["user"], client=client,
                              history=self.GREETED)
        assert run.status == "needs_clarification"
        assert run.presentation["options"] == []
        assert "two columns" in run.answer


class TestDatasetDashboardRequest:
    async def test_creating_a_dashboard_is_refused_not_queried(
            self, db_session, single_world):
        """Ask AI on a dataset must not treat "create a dashboard with a KPI"
        as a data question. Live, that ran SQL and narrated totals as if it
        had built dashboard KPIs."""
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(
            db_session, question="create a dashboard with a KPI",
            datasets=[single_world["orders"]],
            user=single_world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert run.intent == "chat"
        assert "dashboard" in (run.answer or "").lower()
        assert (await db_session.execute(select(AgentStep))).scalars().all() == []


class TestTheAnswerNamesTheDatasetAsItsAuthorDid:
    async def test_the_explain_prompt_carries_the_display_name(self, db_session, tmp_path):
        """BUG-032, both sides of the seam: the graph builds the query-table
        names and must hand explain() the SAME mapping back to display names,
        or the prose keeps saying `qa_chrome_sales` however explain() is
        written."""
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        role = Role(name="analyst", org_id=org.id)
        db_session.add(role)
        await db_session.flush()
        user = User(email="n@corp.com", password_hash="x", org_id=org.id, role_id=role.id)
        user.role = role
        db_session.add(user)
        path = _write_csv(tmp_path / "q.csv", ["region", "sales"], [("west", 2580), ("east", 10)])
        ds = Dataset(name="QA_CHROME sales", org_id=org.id, mode="import", filename=path)
        db_session.add(ds)
        await db_session.flush()
        db_session.add_all([DatasetColumn(dataset_id=ds.id, name="region", dtype="text"),
                            DatasetColumn(dataset_id=ds.id, name="sales", dtype="numeric")])
        await db_session.commit()

        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, sum(sales) AS total FROM qa_chrome_sales GROUP BY region"}])
        run = await run_agent(db_session, question="sales by region",
                              datasets=[ds], user=user, client=client)
        await db_session.commit()

        assert run.status == "ok", run.answer
        prompt = client.explain_calls[-1]
        assert 'rows from "QA_CHROME sales"' in prompt
        assert "rows from qa_chrome_sales" not in prompt
        assert "'total': 2580}" in prompt and "2580.0" not in prompt
        assert prompt.index("'west'") < prompt.index("'east'")
