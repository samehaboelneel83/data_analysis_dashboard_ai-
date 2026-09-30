"""End to end: on Auto, the answer to a question says which model REALLY
answered each step, and the top bar's data carries it.

Three real HTTP servers stand in for the three vLLM boxes (the same
/v1/models and /v1/chat/completions shape, including max_model_len), so the
whole path runs for real: the X-LLM-Endpoint header, get_client(), Auto's
routing, the HTTP calls, the X-LLM-Used response header and the per-person
history /llm/endpoints returns.
"""
import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request

from app.core.config import settings
from app.models.models import AgentRun, DataSource
from app.services import llm_endpoints as le


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fake_vllm(model: str, max_len: int, hits: list) -> FastAPI:
    app = FastAPI()

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": model, "object": "model", "max_model_len": max_len}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        hits.append((model, body["model"], body["max_tokens"]))
        return {"choices": [{"message": {"content": f"answered by {model}"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
    return app


@pytest.fixture(scope="module")
def three_servers():
    hits: list = []
    specs = [("big", "qwen3.8_27b", 32768, 8), ("mid", "qwen3.5", 32768, 6), ("small", "qwen3.5_9b", 16384, 4)]
    servers, endpoints = [], []
    for eid, model, max_len, strength in specs:
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(_fake_vllm(model, max_len, hits), host="127.0.0.1",
                                               port=port, log_level="warning"))
        threading.Thread(target=server.run, daemon=True).start()
        servers.append(server)
        endpoints.append({"id": eid, "name": model, "base_url": f"http://127.0.0.1:{port}/v1",
                          "model": model, "strength": strength})
    deadline = time.time() + 10
    while not all(s.started for s in servers) and time.time() < deadline:
        time.sleep(0.05)
    yield endpoints, hits
    for s in servers:
        s.should_exit = True


@pytest.fixture
def auto_list(three_servers, monkeypatch):
    endpoints, hits = three_servers
    monkeypatch.setattr(settings, "llm_endpoints", json.dumps(endpoints))
    monkeypatch.setattr(settings, "llm_endpoints_default", "auto")
    monkeypatch.setattr(settings, "llm_enabled", True)
    le.apply_stored(None)
    le._health.clear(); le._meta.clear(); le._last_by_user.clear()
    hits.clear()
    yield hits
    le._health.clear(); le._meta.clear(); le._last_by_user.clear()


@pytest.fixture
def two_step_agent(monkeypatch):
    """The agent's two kinds of call, made with the client the route builds:
    classify the question (light) then write the SQL (heavy, the 'ask' meter)."""
    async def fake_run(db, *, question, source, user, client, conversation_id=None, **kw):
        intent = await client.complete([{"role": "user", "content": "classify: " + question}],
                                       max_tokens=50, weight="light")
        sql = await client.complete([{"role": "user", "content": "write SQL for: " + question}],
                                    max_tokens=600)
        run = AgentRun(org_id=user.org_id, conversation_id=conversation_id, question=question,
                       status="ok", intent="aggregate", answer=f"{intent} / {sql}")
        db.add(run)
        await db.flush()
        return run
    monkeypatch.setattr("app.routers.agent.run_agent", fake_run)


async def _conversation(client, db_session, two_orgs, headers):
    src = DataSource(name="wh", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    r = await client.post("/api/v1/agent/conversations", headers=headers, json={"data_source_id": src.id})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


class TestAutoTellsWhichModelAnswered:
    async def test_each_step_goes_to_its_model_and_the_answer_says_so(
            self, client, db_session, two_orgs, auth_headers, auto_list, two_step_agent):
        await le.probe_all()                                   # the lights, and each context size
        assert all(le.is_up(e) for e in ("big", "mid", "small"))
        assert le.context_of(le.find("small")) == 16384

        cid = await _conversation(client, db_session, two_orgs, auth_headers["a"])
        r = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                              headers={**auth_headers["a"], "X-LLM-Endpoint": "auto"},
                              json={"question": "total sales by region"})
        assert r.status_code == 200, r.text
        # The light step went to the fast 9B, the SQL to the strongest 27B...
        assert [h[0] for h in auto_list] == ["qwen3.5_9b", "qwen3.8_27b"]
        assert r.json()["answer"] == "answered by qwen3.5_9b / answered by qwen3.8_27b"
        # ...and the response says exactly that, for the top bar.
        assert r.headers["x-llm-used"] == "small=light,big=heavy"

        # After a reload the top bar still knows: /llm/endpoints returns it.
        r = await client.get("/api/v1/llm/endpoints", headers=auth_headers["a"])
        last = r.json()["last_used"]
        assert [(u["id"], u["weight"], u["auto"]) for u in last] == [("small", "light", True), ("big", "heavy", True)]
        assert "x-llm-used" not in r.headers                   # listing the models used none

    async def test_a_named_model_is_used_for_every_step(
            self, client, db_session, two_orgs, auth_headers, auto_list, two_step_agent):
        await le.probe_all()
        cid = await _conversation(client, db_session, two_orgs, auth_headers["a"])
        r = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                              headers={**auth_headers["a"], "X-LLM-Endpoint": "mid"},
                              json={"question": "q"})
        assert [h[0] for h in auto_list] == ["qwen3.5", "qwen3.5"]
        assert r.headers["x-llm-used"] == "mid=light,mid=heavy"

    async def test_when_the_strong_model_dies_auto_moves_and_says_where(
            self, client, db_session, two_orgs, auth_headers, auto_list, two_step_agent, monkeypatch):
        await le.probe_all()
        endpoints = json.loads(settings.llm_endpoints)
        endpoints[0]["base_url"] = f"http://127.0.0.1:{_free_port()}/v1"   # nothing listens there
        monkeypatch.setattr(settings, "llm_endpoints", json.dumps(endpoints))
        cid = await _conversation(client, db_session, two_orgs, auth_headers["a"])
        r = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                              headers={**auth_headers["a"], "X-LLM-Endpoint": "auto"},
                              json={"question": "q"})
        assert r.status_code == 200, r.text
        assert r.headers["x-llm-used"] == "small=light,mid=heavy"
        assert le.is_up("big") is False                        # and its light turned red
