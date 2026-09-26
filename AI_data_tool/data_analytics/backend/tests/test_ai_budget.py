"""E11: per-org AI budgets.

Every model completion is metered against the org it is made for (the
request's user, or a background run's org), whichever service makes it, and
recorded in `ai_usage`. An org's tokens per UTC day and per month can be
capped: a question or a copilot message is then refused up front with a 429,
and the features where the model only polishes (narratives, suggestions,
column descriptions) fall back as they do when the model is down.
"""
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.models.models import AgentRun, AgentStep, AiUsage, DataSource, Organization, Quota
from app.services import llm as llm_service
from app.services import quotas
from app.services.llm import BUDGET_SPENT, LLMClient, UsageMeter, release_meter, use_meter


@pytest.fixture(autouse=True)
def _clean_quota_state():
    quotas.invalidate_quota_cache()
    yield
    quotas.invalidate_quota_cache()


def _reply(content="ok", prompt_tokens=100, completion_tokens=20):
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


class _Model:
    """A model endpoint that counts the requests it receives."""
    def __init__(self, content="ok", prompt_tokens=100, completion_tokens=20):
        self.hits = 0
        self.content, self.pin, self.pout = content, prompt_tokens, completion_tokens

    def client(self) -> LLMClient:
        def handler(request):
            self.hits += 1
            return _reply(self.content, self.pin, self.pout)
        return LLMClient(base_url="http://model.test/v1", model="m", enabled=True,
                         transport=httpx.MockTransport(handler))


async def _set_quota(db_session, org_id: int, **fields):
    row = (await db_session.execute(select(Quota).where(Quota.org_id == org_id))).scalar_one_or_none()
    if row is None:
        row = Quota(org_id=org_id)
        db_session.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    await db_session.commit()
    quotas.invalidate_quota_cache(org_id)


async def _usage(db_session, org_id):
    return (await db_session.execute(
        select(AiUsage).where(AiUsage.org_id == org_id).order_by(AiUsage.id))).scalars().all()


# ── The meter in the client ──────────────────────────────────────────────────

class TestMeter:
    async def test_counts_every_completion_made_while_it_is_current(self):
        model = _Model(prompt_tokens=100, completion_tokens=20)
        meter = UsageMeter(org_id=1, user_id=2, feature="ask")
        token = use_meter(meter)
        try:
            await model.client().complete([{"role": "user", "content": "q"}])
            # A second client, as a different service would build: same meter.
            await model.client().complete([{"role": "user", "content": "q"}])
        finally:
            release_meter(token)
        assert (meter.calls, meter.tokens_in, meter.tokens_out) == (2, 200, 40)
        # Released: a later call is not counted.
        await model.client().complete([{"role": "user", "content": "q"}])
        assert meter.calls == 2

    async def test_a_spent_budget_refuses_the_call_without_reaching_the_model(self):
        model = _Model()
        meter = UsageMeter(org_id=1, user_id=None, feature="narrate", remaining=0)
        token = use_meter(meter)
        try:
            client = model.client()
            assert await client.complete([{"role": "user", "content": "q"}]) is None
            assert client.last_error == BUDGET_SPENT
        finally:
            release_meter(token)
        assert model.hits == 0
        assert (meter.calls, meter.refused) == (0, 1)

    async def test_the_last_call_may_overshoot_but_the_next_is_refused(self):
        model = _Model(prompt_tokens=100, completion_tokens=20)
        meter = UsageMeter(org_id=1, user_id=None, feature="ask", remaining=50)
        token = use_meter(meter)
        try:
            assert await model.client().complete([{"role": "user", "content": "q"}]) == "ok"
            assert meter.remaining == -70
            assert await model.client().complete([{"role": "user", "content": "q"}]) is None
        finally:
            release_meter(token)
        assert (model.hits, meter.calls, meter.refused) == (1, 1, 1)

    async def test_complete_json_does_not_retry_into_a_spent_budget(self):
        model = _Model()
        meter = UsageMeter(org_id=1, user_id=None, feature="ask", remaining=0)
        token = use_meter(meter)
        try:
            got = await model.client().complete_json(
                [{"role": "user", "content": "q"}], {"type": "object", "properties": {}})
        finally:
            release_meter(token)
        assert got is None and meter.refused == 1


# ── The budget ───────────────────────────────────────────────────────────────

class TestBudget:
    async def test_no_limit_means_no_count_and_no_refusal(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        assert await quotas.ai_budget(db_session, org_id) == (None, None, 0)

    async def test_counts_today_for_the_day_and_this_month_for_the_month(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        db_session.add_all([
            AiUsage(org_id=org_id, feature="ask", calls=1, tokens_in=300, tokens_out=100, created_at=now),
            AiUsage(org_id=org_id, feature="ask", calls=1, tokens_in=5_000, tokens_out=0,
                    created_at=month_start - timedelta(days=3)),     # last month: ignored
            AiUsage(org_id=two_orgs["b"]["org"].id, feature="ask", calls=1,
                    tokens_in=9_999, tokens_out=0, created_at=now),  # another org
        ])
        await db_session.commit()
        await _set_quota(db_session, org_id, max_ai_tokens_per_day=1_000)
        assert await quotas.ai_budget(db_session, org_id) == (
            600, "ai_tokens_per_day", pytest.approx(quotas._seconds_until_next_midnight_utc(), abs=5))

        # A month limit tighter than the day's binds instead.
        await _set_quota(db_session, org_id, max_ai_tokens_per_month=500)
        remaining, kind, resets = await quotas.ai_budget(db_session, org_id)
        assert (remaining, kind) == (100, "ai_tokens_per_month")
        assert resets >= quotas._seconds_until_next_midnight_utc() - 5

    async def test_an_earlier_day_this_month_counts_for_the_month_only(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        now = datetime.utcnow()
        if now.day == 1:
            pytest.skip("no earlier day in this month on the 1st")
        db_session.add(AiUsage(org_id=org_id, feature="ask", calls=1, tokens_in=400, tokens_out=0,
                               created_at=now - timedelta(days=1)))
        await db_session.commit()
        await _set_quota(db_session, org_id, max_ai_tokens_per_day=1_000, max_ai_tokens_per_month=1_000)
        assert (await quotas.ai_budget(db_session, org_id))[:2] == (600, "ai_tokens_per_month")
        await _set_quota(db_session, org_id, max_ai_tokens_per_month=None)
        assert (await quotas.ai_budget(db_session, org_id))[:2] == (1_000, "ai_tokens_per_day")


# ── Through the API ──────────────────────────────────────────────────────────

@pytest.fixture
async def source(db_session, two_orgs):
    src = DataSource(name="wh-a", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    return src


@pytest.fixture
def model(monkeypatch):
    m = _Model(content="Forty-two.", prompt_tokens=700, completion_tokens=50)
    monkeypatch.setattr(llm_service, "get_client", m.client)
    return m


@pytest.fixture
def agent_that_calls_the_model(monkeypatch):
    """run_agent stand-in that asks the model once, as the real one does
    several times, through the client the router hands it."""
    runs = []

    async def fake_run(db, *, question, user, client, source=None, datasets=None,
                       conversation_id=None, history=None, **kw):
        answer = await client.complete([{"role": "user", "content": question}])
        runs.append(question)
        run = AgentRun(org_id=user.org_id, conversation_id=conversation_id, question=question,
                       status="ok" if answer else "error", intent="lookup",
                       answer=answer, error=None if answer else client.last_error)
        db.add(run)
        await db.flush()
        db.add(AgentStep(agent_run_id=run.id, node="s1", status="ok", sql="SELECT 1",
                         rows_returned=0, result_rows={"columns": [], "rows": []}))
        await db.flush()
        return run
    monkeypatch.setattr("app.routers.agent.run_agent", fake_run)
    return runs


async def _conversation(client, headers, source):
    r = await client.post("/api/v1/agent/conversations",
                          json={"data_source_id": source.id}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestAsk:
    async def test_a_question_records_what_it_spent_and_who_asked(
            self, client, db_session, two_orgs, auth_headers, source, model,
            agent_that_calls_the_model):
        cid = await _conversation(client, auth_headers["a"], source)
        r = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                              json={"question": "how many?"}, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["answer"] == "Forty-two."
        [row] = await _usage(db_session, two_orgs["a"]["org"].id)
        assert (row.feature, row.user_id, row.calls, row.refused, row.tokens_in, row.tokens_out) == \
            ("ask", two_orgs["a"]["user"].id, 1, 0, 700, 50)

    async def test_a_spent_budget_refuses_the_question_before_the_model_is_asked(
            self, client, db_session, two_orgs, auth_headers, source, model,
            agent_that_calls_the_model):
        org_id = two_orgs["a"]["org"].id
        await _set_quota(db_session, org_id, max_ai_tokens_per_day=1_000)
        cid = await _conversation(client, auth_headers["a"], source)
        first = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                  json={"question": "one"}, headers=auth_headers["a"])
        assert first.status_code == 200          # 750 of 1,000
        second = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                   json={"question": "two"}, headers=auth_headers["a"])
        assert second.status_code == 200         # allowed while any remains: 1,500
        third = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                  json={"question": "three"}, headers=auth_headers["a"])
        assert third.status_code == 429
        assert "AI budget for today is used up" in third.json()["detail"]
        assert int(third.headers["Retry-After"]) > 0
        assert agent_that_calls_the_model == ["one", "two"]
        assert model.hits == 2

        # Org B has its own budget.
        cid_b = await _conversation(client, auth_headers["b"], await _source_b(db_session, two_orgs))
        other = await client.post(f"/api/v1/agent/conversations/{cid_b}/ask",
                                  json={"question": "b"}, headers=auth_headers["b"])
        assert other.status_code == 200

    async def test_the_month_limit_names_the_month(
            self, client, db_session, two_orgs, auth_headers, source, model,
            agent_that_calls_the_model):
        org_id = two_orgs["a"]["org"].id
        db_session.add(AiUsage(org_id=org_id, feature="ask", calls=1, tokens_in=2_000, tokens_out=0))
        await db_session.commit()
        await _set_quota(db_session, org_id, max_ai_tokens_per_month=2_000)
        cid = await _conversation(client, auth_headers["a"], source)
        r = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                              json={"question": "q"}, headers=auth_headers["a"])
        assert r.status_code == 429 and "this month" in r.json()["detail"]


async def _source_b(db_session, two_orgs):
    src = DataSource(name="wh-b", type="postgresql", org_id=two_orgs["b"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    return src


class TestFallbackFeatures:
    async def test_a_narrative_falls_back_instead_of_failing_when_the_budget_is_spent(
            self, client, db_session, two_orgs, auth_headers, model, monkeypatch):
        from app.services import insights
        monkeypatch.setattr(insights, "_narrative_down_until", 0.0)
        org_id = two_orgs["a"]["org"].id
        finding = {"title": "Sales rose", "detail": "Up 12% on last year", "figures": {"pct": 12}}

        model.content = "Sales rose 12% on last year."
        ok = await client.post("/api/v1/analysis/narrate", json={"finding": finding},
                               headers=auth_headers["a"])
        assert ok.status_code == 200 and ok.json()["sentence"] == "Sales rose 12% on last year."

        await _set_quota(db_session, org_id, max_ai_tokens_per_day=100)   # 750 already spent
        monkeypatch.setattr(insights, "_narrative_down_until", 0.0)
        spent = await client.post("/api/v1/analysis/narrate", json={"finding": finding},
                                  headers=auth_headers["a"])
        assert spent.status_code == 200 and spent.json()["sentence"] is None
        assert model.hits == 1
        rows = await _usage(db_session, org_id)
        assert [(r.feature, r.calls, r.refused) for r in rows] == [("narrate", 1, 0), ("narrate", 0, 1)]

    async def test_a_request_that_never_calls_the_model_records_nothing(
            self, client, db_session, two_orgs, auth_headers, monkeypatch):
        from app.services import insights
        # The breaker is open: narrate_one returns before any call.
        monkeypatch.setattr(insights, "_narrative_down_until", float("inf"))
        r = await client.post("/api/v1/analysis/narrate", json={"finding": {"title": "x"}},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert await _usage(db_session, two_orgs["a"]["org"].id) == []


class TestBackground:
    async def test_a_detached_run_is_metered_on_its_own_sessions(self, tmp_path, monkeypatch):
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/bg.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            org = Organization(name="bg")
            db.add(org)
            await db.commit()
            org_id = org.id
            db.add(Quota(org_id=org_id, max_ai_tokens_per_day=10_000))
            await db.commit()
        quotas.invalidate_quota_cache()
        model = _Model(prompt_tokens=40, completion_tokens=2)

        async def describe_columns():
            for _ in range(3):
                await model.client().complete([{"role": "user", "content": "describe"}],
                                              background=True)
            return "done"

        async with factory() as db:
            meter = await quotas.open_ai_meter(db, org_id, None, "metadata")
        assert meter.remaining == 10_000
        assert await quotas.run_metered(factory, meter, describe_columns()) == "done"
        async with factory() as db:
            [row] = (await db.execute(select(AiUsage))).scalars().all()
        assert (row.org_id, row.user_id, row.feature, row.calls, row.tokens_in, row.tokens_out) == \
            (org_id, None, "metadata", 3, 120, 6)
        await engine.dispose()


# ── Platform administration ──────────────────────────────────────────────────

@pytest.fixture
def _super(monkeypatch):
    monkeypatch.setattr(settings, "super_admin_emails", "admin-a@example.com")


class TestPlatform:
    async def test_limits_are_set_shown_and_reported(self, client, db_session, two_orgs,
                                                     auth_headers, _super):
        org_b = two_orgs["b"]["org"].id
        r = await client.put(f"/api/v1/platform/organizations/{org_b}/quota",
                             json={"max_ai_tokens_per_day": 50_000, "max_ai_tokens_per_month": 900_000},
                             headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert (r.json()["max_ai_tokens_per_day"], r.json()["max_ai_tokens_per_month"]) == (50_000, 900_000)

        user_b = two_orgs["b"]["user"].id
        db_session.add_all([
            AiUsage(org_id=org_b, user_id=user_b, feature="ask", calls=2, tokens_in=1_000, tokens_out=200),
            AiUsage(org_id=org_b, user_id=None, feature="metadata", calls=5, tokens_in=300, tokens_out=50),
            AiUsage(org_id=org_b, user_id=user_b, feature="copilot", calls=0, refused=1),
        ])
        await db_session.commit()

        orgs = (await client.get("/api/v1/platform/organizations", headers=auth_headers["a"])).json()
        b = next(o for o in orgs if o["id"] == org_b)
        assert b["quota"]["max_ai_tokens_per_day"] == 50_000
        assert (b["usage"]["ai_tokens_today"], b["usage"]["ai_tokens_month"]) == (1_550, 1_550)

        rep = (await client.get(f"/api/v1/platform/organizations/{org_b}/ai-usage",
                                headers=auth_headers["a"])).json()
        assert rep["total_tokens"] == 1_550
        assert rep["remaining"] == 50_000 - 1_550 and rep["binding_limit"] == "ai_tokens_per_day"
        assert [(f["feature"], f["tokens"], f["calls"], f["refused"]) for f in rep["by_feature"]] == \
            [("ask", 1_200, 2, 0), ("metadata", 350, 5, 0), ("copilot", 0, 0, 1)]
        by_user = {u["email"]: u["tokens"] for u in rep["by_user"]}
        assert by_user == {"admin-b@example.com": 1_200, None: 350}
        assert len(rep["by_day"]) == 1 and rep["by_day"][0]["tokens"] == 1_550

    async def test_only_a_super_admin_sees_or_sets_them(self, client, two_orgs, auth_headers, _super):
        org_a = two_orgs["a"]["org"].id
        assert (await client.get(f"/api/v1/platform/organizations/{org_a}/ai-usage",
                                 headers=auth_headers["b"])).status_code == 403
        assert (await client.put(f"/api/v1/platform/organizations/{org_a}/quota",
                                 json={"max_ai_tokens_per_day": 1}, headers=auth_headers["b"])).status_code == 403

    async def test_a_negative_limit_is_refused(self, client, two_orgs, auth_headers, _super):
        r = await client.put(f"/api/v1/platform/organizations/{two_orgs['b']['org'].id}/quota",
                             json={"max_ai_tokens_per_day": -1}, headers=auth_headers["a"])
        assert r.status_code == 422
