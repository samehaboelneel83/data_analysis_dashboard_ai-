"""The agent actually runs the analysis -- checked through the graph, not the node.

`choose_analysis` is unit-tested next door. That proves it picks correctly; it
proves nothing about whether the agent ever calls it. This codebase has shipped
that exact gap before: the agent 404'd for its whole life behind green
service-layer tests, which is why a seam gets a test on BOTH sides.

What is pinned here:
  * a `compare` question in dataset mode comes back as an ANALYSIS, not SQL,
    and the SQL generator was never asked;
  * the answer is computed over the SECURED frame -- row-filtered, denied
    columns already gone -- and not from a second, unsecured read;
  * everything that does not route still routes to SQL, unchanged. This
    feature is additive or it is a regression.
"""
import pytest
from sqlalchemy import select

from app.models.models import (AgentStep, ColumnSecurityRule, Dataset,
                               DatasetColumn, Organization, Role,
                               RowSecurityRule, User)
from app.services.agent.graph import run_agent

from .test_agent_graph import ScriptedClient

COMPARE = {"intent": "compare", "ambiguous": False, "ambiguity_reason": None}
EXPLAIN = {"intent": "explain", "ambiguous": False, "ambiguity_reason": None}
AGGREGATE = {"intent": "aggregate", "ambiguous": False, "ambiguity_reason": None}
ONE_STEP = {"steps": [{"id": "s1", "question": "total", "depends_on": []}]}


class AnalysisClient(ScriptedClient):
    """`ScriptedClient` answers None to any schema it does not recognise, which
    is exactly the fall-through case. This adds the one it should recognise."""

    def __init__(self, *a, analysis=None, **kw):
        super().__init__(*a, **kw)
        self.analysis_replies = list(analysis or [])
        self.analysis_calls = []

    async def complete_json(self, messages, schema, **kw):
        props = set(schema.get("properties", {}))
        if props in ({"value_col", "group_col"}, {"response"}):
            self.analysis_calls.append((messages, schema))
            return self.analysis_replies.pop(0) if self.analysis_replies else None
        return await super().complete_json(messages, schema, **kw)


def _csv(path, header, rows):
    path.write_text("\n".join([",".join(header)]
                              + [",".join(str(v) for v in r) for r in rows]),
                    encoding="utf-8")
    return str(path)


@pytest.fixture
async def world(db_session, tmp_path):
    """Two regions, twelve rows each -- enough for `compare_groups` to run --
    plus a `salary` column that one role is not allowed to see."""
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

    rows = ([("north", 100 + i, 10 + i, 5) for i in range(12)]
            + [("south", 900 + i, 30 + i, 7) for i in range(12)])
    path = _csv(tmp_path / "sales.csv",
                ["region", "revenue", "salary", "units"], rows)
    ds = Dataset(name="sales", org_id=org.id, mode="import", filename=path)
    db_session.add(ds)
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=ds.id, name="region", dtype="text"),
        DatasetColumn(dataset_id=ds.id, name="revenue", dtype="numeric"),
        DatasetColumn(dataset_id=ds.id, name="salary", dtype="numeric"),
        DatasetColumn(dataset_id=ds.id, name="units", dtype="numeric"),
    ])
    await db_session.commit()
    yield {"org": org, "user": user, "role": role, "ds": ds}


async def _run(db_session, world, question, client):
    run = await run_agent(db_session, question=question,
                          datasets=[world["ds"]], user=world["user"],
                          client=client)
    await db_session.commit()
    return run


class TestACompareQuestionBecomesAnAnalysis:
    async def test_it_answers_with_the_analysis(self, db_session, world):
        client = AnalysisClient(
            classify=[COMPARE],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        run = await _run(db_session, world,
                         "is revenue really different between regions?", client)

        assert run.status == "ok", run.error
        assert run.presentation["kind"] == "analysis_result"
        assert run.presentation["analysis"] == "compare_groups"

    async def test_the_envelope_matches_the_run_endpoints(self, db_session, world):
        """Same four keys `POST /analysis/run` answers with, so the chat
        renders it with the panel's renderer instead of a second one."""
        client = AnalysisClient(
            classify=[COMPARE],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        run = await _run(db_session, world, "compare revenue by region", client)
        assert set(run.presentation) >= {
            "kind", "analysis", "result_kind", "params", "result"}
        assert run.presentation["result_kind"] == "statistical_test"

    async def test_it_reports_a_real_effect_size(self, db_session, world):
        """North ~105, South ~905: a difference nobody could call noise.

        The MAGNITUDE is what is asserted -- Cohen's d is signed, and its sign
        says which group is lower, so a run where north is the smaller group
        reports a large NEGATIVE d. Requiring a positive number here would pin
        the alphabetical order of the group names.
        """
        client = AnalysisClient(
            classify=[COMPARE],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        run = await _run(db_session, world, "compare revenue by region", client)
        result = run.presentation["result"]
        assert result["significant"] is True
        assert abs(result["effect_size"]) > 0.8      # "large", by convention
        assert result["effect_label"] == "large"

    async def test_no_sql_was_written(self, db_session, world):
        """The point of the feature. If the SQL node still ran, the analysis is
        a decoration on top of the answer it was meant to replace."""
        client = AnalysisClient(
            classify=[COMPARE], plan=[ONE_STEP],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        await _run(db_session, world, "compare revenue by region", client)
        assert client.generate_calls == []
        steps = (await db_session.execute(select(AgentStep))).scalars().all()
        assert steps == []

    async def test_an_explain_question_routes_too(self, db_session, world):
        client = AnalysisClient(classify=[EXPLAIN],
                                analysis=[{"response": "revenue"}])
        run = await _run(db_session, world, "what drives revenue?", client)
        assert run.presentation["analysis"] == "explain_response"
        assert run.presentation["result"]["factors"]


class TestTheFrameIsTheSecuredOne:
    async def test_row_security_reaches_the_analysis(self, db_session, world):
        """With only the north rows visible there is ONE group left, and
        `compare_groups` needs two -- so the run must not quietly answer as if
        both were there. Proven by the answer changing, not by reading the code.
        """
        db_session.add(RowSecurityRule(role_id=world["role"].id,
                                       dataset_id=world["ds"].id,
                                       filter_expr="region == 'north'"))
        await db_session.commit()
        client = AnalysisClient(
            classify=[COMPARE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, avg(revenue) FROM sales GROUP BY 1"}],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        run = await _run(db_session, world, "compare revenue by region", client)
        # One group is not comparable, so this falls through to SQL rather than
        # reporting a comparison of a group against itself.
        assert run.presentation is None or \
            run.presentation.get("kind") != "analysis_result"

    async def test_a_denied_column_is_never_offered(self, db_session, world):
        """Column security is structural here: the frame has already lost the
        column, so it cannot reach the enum the model chooses from."""
        db_session.add(ColumnSecurityRule(role_id=world["role"].id,
                                          dataset_id=world["ds"].id,
                                          denied_columns=["salary"]))
        await db_session.commit()
        client = AnalysisClient(
            classify=[COMPARE],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        await _run(db_session, world, "compare salary by region", client)

        assert client.analysis_calls, "the analysis node was never reached"
        _, schema = client.analysis_calls[0]
        assert "salary" not in schema["properties"]["value_col"]["enum"]

    async def test_a_denied_column_cannot_be_forced_through(self, db_session, world):
        """And if the model names it anyway -- a broken grammar, a different
        endpoint -- the run must not analyse it."""
        db_session.add(ColumnSecurityRule(role_id=world["role"].id,
                                          dataset_id=world["ds"].id,
                                          denied_columns=["salary"]))
        await db_session.commit()
        client = AnalysisClient(
            classify=[COMPARE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region FROM sales"}],
            analysis=[{"value_col": "salary", "group_col": "region"}])
        run = await _run(db_session, world, "compare salary by region", client)
        assert run.presentation is None or \
            run.presentation.get("kind") != "analysis_result"


class TestEverythingElseStillGoesToSql:
    async def test_an_aggregate_question_is_untouched(self, db_session, world):
        client = AnalysisClient(
            classify=[AGGREGATE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(revenue) AS total FROM sales"}])
        run = await _run(db_session, world, "total revenue", client)
        assert run.status == "ok", run.error
        assert client.generate_calls, "the SQL node should still have run"
        assert not client.analysis_calls, "aggregate must not reach the analysis node"

    async def test_a_compare_the_model_cannot_resolve_falls_back_to_sql(
            self, db_session, world):
        """"why did returns spike" over a frame with no such column. The
        fallback is what keeps this additive: a question the analysis path
        cannot serve still gets the answer it got yesterday."""
        client = AnalysisClient(
            classify=[COMPARE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, avg(revenue) AS a FROM sales GROUP BY 1"}],
            analysis=[None])
        run = await _run(db_session, world, "why did returns spike", client)
        assert run.status == "ok", run.error
        assert client.generate_calls, "it should have fallen through to SQL"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.rows_returned == 2


class TestMultipleDatasetsFallThrough:
    async def test_two_datasets_go_to_sql(self, db_session, world, tmp_path):
        """An analysis takes ONE DataFrame. With two datasets in scope there is
        no way to know which is meant, and joining them first is a decision the
        SQL path already makes properly. Falling through is the honest answer,
        not a guess at the first frame."""
        second = Dataset(name="regions", org_id=world["org"].id, mode="import",
                         filename=_csv(tmp_path / "regions.csv",
                                       ["name", "code"],
                                       [("north", 1), ("south", 2)]))
        db_session.add(second)
        await db_session.flush()
        db_session.add_all([
            DatasetColumn(dataset_id=second.id, name="name", dtype="text"),
            DatasetColumn(dataset_id=second.id, name="code", dtype="numeric"),
        ])
        await db_session.commit()

        client = AnalysisClient(
            classify=[COMPARE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, avg(revenue) AS a FROM sales GROUP BY 1"}],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        run = await run_agent(db_session, question="compare revenue by region",
                              datasets=[world["ds"], second],
                              user=world["user"], client=client)
        await db_session.commit()

        assert not client.analysis_calls, "two datasets must not reach the analysis node"
        assert client.generate_calls, "it should have gone to SQL"
        assert run.status == "ok", run.error


class TestTheProseComesFromTheAnalysis:
    async def test_the_answer_is_the_statistics_own_sentence(self, db_session, world):
        """Not a model paraphrase. `interpretation` is a sentence the
        statistics layer stands behind; rewriting it through a model would put
        a number in the answer that no test guards."""
        client = AnalysisClient(
            classify=[COMPARE],
            analysis=[{"value_col": "revenue", "group_col": "region"}])
        run = await _run(db_session, world, "compare revenue by region", client)
        assert run.answer == run.presentation["result"]["interpretation"]
        assert run.answer
