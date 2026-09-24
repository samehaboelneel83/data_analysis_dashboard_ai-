"""Conversation history, titles, results and the follow-up context on the
chat API.

The screen this serves showed the gap plainly: the pane resumed a server
conversation but could never read it back, the answer came as prose with the
rows left behind, and "present a table" started a new, context-free question.
The router's job here is plumbing and scoping; `run_agent` is faked, and the
fake records what it was handed."""
import pytest
from sqlalchemy import select

from app.models.models import (AgentMessage, AgentRun, AgentStep,
                               Conversation, DataSource)

SNAPSHOT = {"columns": ["city", "n"], "rows": [["Cairo", 3], ["Giza", 1]],
            "total": 2, "truncated": False}


@pytest.fixture
def scripted(monkeypatch):
    """A deterministic run_agent that answers every question with one sink
    step carrying SQL and a result snapshot, and records the history it was
    given."""
    calls = []

    async def fake_run(db, *, question, user, client, source=None,
                       datasets=None, conversation_id=None, history=None, **kw):
        calls.append({"question": question, "history": history})
        run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                       question=question, status="ok", intent="lookup",
                       answer=f"Answer to {question}",
                       context_objects=["orders"])
        db.add(run)
        await db.flush()
        db.add(AgentStep(agent_run_id=run.id, node="s1", status="ok",
                         sql=f"SELECT city, n FROM t /* {question} */",
                         rows_returned=2, result_rows=SNAPSHOT))
        await db.flush()
        return run
    monkeypatch.setattr("app.routers.agent.run_agent", fake_run)
    return calls


@pytest.fixture
async def source(db_session, two_orgs):
    src = DataSource(name="wh-a", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    return src


@pytest.fixture
async def other_user(db_session, two_orgs):
    """A second user in org A: same org, so check_org alone would let them
    through -- ownership is the property under test."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import User

    org_a = two_orgs["a"]["org"]
    user = User(org_id=org_a.id, role_id=two_orgs["a"]["role"].id,
                email="second@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def new_conv(client, headers, source, title=None):
    body = {"data_source_id": source.id}
    if title is not None:
        body["title"] = title
    r = await client.post("/api/v1/agent/conversations", json=body, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


async def ask(client, headers, cid, question):
    r = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                          json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


class TestResultsTravelWithTheAnswer:
    async def test_ask_returns_the_sink_rows_and_sql(self, client, auth_headers,
                                                    source, scripted):
        cid = await new_conv(client, auth_headers["a"], source)
        got = await ask(client, auth_headers["a"], cid, "orders per city")
        assert got["results"] == [{"step": "s1", "source": "query", **SNAPSHOT}]
        assert got["sql"] == ["SELECT city, n FROM t /* orders per city */"]
        assert got["presentation"] is None

    async def test_run_detail_carries_the_snapshot_and_the_tables_considered(
            self, client, auth_headers, source, scripted):
        cid = await new_conv(client, auth_headers["a"], source)
        run_id = (await ask(client, auth_headers["a"], cid, "q"))["run_id"]
        detail = (await client.get(f"/api/v1/agent/runs/{run_id}",
                                   headers=auth_headers["a"])).json()
        assert detail["steps"][0]["result_rows"] == SNAPSHOT
        assert detail["context_objects"] == ["orders"]
        assert detail["presentation"] is None


class TestTitles:
    async def test_the_first_question_titles_a_new_conversation(
            self, client, auth_headers, source, scripted):
        cid = await new_conv(client, auth_headers["a"], source)
        await ask(client, auth_headers["a"], cid, "how many orders per city?")
        await ask(client, auth_headers["a"], cid, "and per region?")
        listed = (await client.get("/api/v1/agent/conversations",
                                   headers=auth_headers["a"])).json()
        assert listed[0]["title"] == "how many orders per city?"

    async def test_a_long_first_question_is_trimmed(self, client, auth_headers,
                                                    source, scripted):
        cid = await new_conv(client, auth_headers["a"], source)
        await ask(client, auth_headers["a"], cid, "x" * 300)
        listed = (await client.get("/api/v1/agent/conversations",
                                   headers=auth_headers["a"])).json()
        assert len(listed[0]["title"]) <= 80

    async def test_an_explicit_title_is_kept(self, client, auth_headers,
                                             source, scripted):
        cid = await new_conv(client, auth_headers["a"], source, title="Sales review")
        await ask(client, auth_headers["a"], cid, "orders per city")
        listed = (await client.get("/api/v1/agent/conversations",
                                   headers=auth_headers["a"])).json()
        assert listed[0]["title"] == "Sales review"

    async def test_the_list_carries_created_at(self, client, auth_headers, source):
        await new_conv(client, auth_headers["a"], source)
        listed = (await client.get("/api/v1/agent/conversations",
                                   headers=auth_headers["a"])).json()
        assert listed[0]["created_at"]


class TestMessages:
    async def test_messages_come_back_in_order_with_their_runs(
            self, client, auth_headers, source, scripted):
        cid = await new_conv(client, auth_headers["a"], source)
        await ask(client, auth_headers["a"], cid, "q1")
        await ask(client, auth_headers["a"], cid, "q2")
        got = await client.get(f"/api/v1/agent/conversations/{cid}/messages",
                               headers=auth_headers["a"])
        assert got.status_code == 200
        msgs = got.json()
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
        assert [m["content"] for m in msgs][::2] == ["q1", "q2"]
        assert [m["id"] for m in msgs] == sorted(m["id"] for m in msgs)
        assert msgs[0]["run"] is None
        run = msgs[1]["run"]
        assert run["status"] == "ok"
        assert run["results"] == [{"step": "s1", "source": "query", **SNAPSHOT}]
        assert run["sql"] == ["SELECT city, n FROM t /* q1 */"]
        assert run["context_objects"] == ["orders"]
        assert msgs[0]["created_at"]

    async def test_messages_are_owner_only(self, client, auth_headers, source,
                                           scripted, other_user):
        cid = await new_conv(client, auth_headers["a"], source)
        await ask(client, auth_headers["a"], cid, "q1")
        assert (await client.get(f"/api/v1/agent/conversations/{cid}/messages",
                                 headers=other_user)).status_code == 404
        assert (await client.get(f"/api/v1/agent/conversations/{cid}/messages",
                                 headers=auth_headers["b"])).status_code == 404


class TestRenameAndDelete:
    async def test_rename_then_delete(self, client, auth_headers, source,
                                      scripted, db_session):
        cid = await new_conv(client, auth_headers["a"], source)
        await ask(client, auth_headers["a"], cid, "q1")
        renamed = await client.patch(f"/api/v1/agent/conversations/{cid}",
                                     json={"title": "  Orders by city  "},
                                     headers=auth_headers["a"])
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Orders by city"

        gone = await client.delete(f"/api/v1/agent/conversations/{cid}",
                                   headers=auth_headers["a"])
        assert gone.status_code == 204
        assert (await client.get(f"/api/v1/agent/conversations/{cid}/messages",
                                 headers=auth_headers["a"])).status_code == 404
        assert (await db_session.execute(select(AgentMessage))).scalars().all() == []
        assert (await db_session.execute(select(Conversation))).scalars().all() == []
        # The run's evidence survives for the eval gate; it just loses its thread.
        run = (await db_session.execute(select(AgentRun))).scalar_one()
        assert run.conversation_id is None

    async def test_a_blank_title_is_422(self, client, auth_headers, source):
        cid = await new_conv(client, auth_headers["a"], source)
        r = await client.patch(f"/api/v1/agent/conversations/{cid}",
                               json={"title": "   "}, headers=auth_headers["a"])
        assert r.status_code == 422

    async def test_rename_and_delete_are_owner_only(self, client, auth_headers,
                                                    source, other_user):
        cid = await new_conv(client, auth_headers["a"], source)
        assert (await client.patch(f"/api/v1/agent/conversations/{cid}",
                                   json={"title": "x"},
                                   headers=other_user)).status_code == 404
        assert (await client.delete(f"/api/v1/agent/conversations/{cid}",
                                    headers=other_user)).status_code == 404
        assert (await client.delete(f"/api/v1/agent/conversations/{cid}",
                                    headers=auth_headers["b"])).status_code == 404
        # Still there for its owner.
        assert (await client.get(f"/api/v1/agent/conversations/{cid}/messages",
                                 headers=auth_headers["a"])).status_code == 200


class TestHistoryReachesTheAgent:
    async def test_the_agent_sees_earlier_turns_but_not_the_current_question(
            self, client, auth_headers, source, scripted):
        cid = await new_conv(client, auth_headers["a"], source)
        await ask(client, auth_headers["a"], cid, "orders per city")
        await ask(client, auth_headers["a"], cid, "as a table")
        first, second = scripted
        assert first["history"] == []
        roles = [h["role"] for h in second["history"]]
        assert roles == ["user", "assistant"]
        assert second["history"][0]["content"] == "orders per city"
        assert second["history"][1]["sql"] == ["SELECT city, n FROM t /* orders per city */"]
        assert second["history"][1]["results"] == [{"step": "s1", "source": "query", **SNAPSHOT}]
        assert all(h["content"] != "as a table" for h in second["history"])

    async def test_history_is_bounded_to_the_last_turns(self, client, auth_headers,
                                                        source, scripted):
        from app.routers import agent as agent_router
        cid = await new_conv(client, auth_headers["a"], source)
        for i in range(agent_router.HISTORY_TURNS):
            await ask(client, auth_headers["a"], cid, f"q{i}")
        await ask(client, auth_headers["a"], cid, "last")
        assert len(scripted[-1]["history"]) == agent_router.HISTORY_TURNS
        # The most recent turns, not the oldest.
        assert scripted[-1]["history"][-1]["role"] == "assistant"
        assert scripted[-1]["history"][-2]["content"] == f"q{agent_router.HISTORY_TURNS - 1}"


@pytest.fixture
async def dq_dataset(db_session, two_orgs):
    """A DirectQuery dataset: its rows stay in the connection, so `filename`
    is NULL -- the shape that used to reach the frame loader as None."""
    from app.models.models import Dataset

    src = DataSource(name="wh-dq", type="postgresql",
                     org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="live_orders", org_id=two_orgs["a"]["org"].id,
                 mode="directquery", filename=None, data_source_id=src.id,
                 source_table="public.orders")
    db_session.add(ds)
    await db_session.commit()
    return ds


class TestDirectQueryDatasetsAreRefused:
    """Dataset mode answers out of a FILE frame (`run_agent`'s dataset_frames).
    A DirectQuery dataset has no file, so it used to reach `abspath(None)` and
    raise -- a 500 the browser then reported as a CORS violation, which sends
    whoever is reading it to the wrong file entirely. The connection is the
    supported way to ask about live data and the same picker already offers
    it, so the refusal names the dataset it is refusing."""

    async def test_a_conversation_cannot_be_scoped_to_a_directquery_dataset(
            self, client, auth_headers, dq_dataset):
        r = await client.post("/api/v1/agent/conversations",
                              json={"dataset_ids": [dq_dataset.id]},
                              headers=auth_headers["a"])
        assert r.status_code == 400, r.text
        assert "live_orders" in r.json()["detail"]

    async def test_asking_in_a_stored_directquery_conversation_is_refused(
            self, client, auth_headers, db_session, two_orgs, dq_dataset,
            scripted):
        """Conversations bound before this guard existed must not 500 either:
        a create-time check alone leaves every stored one crashing."""
        conv = Conversation(org_id=two_orgs["a"]["org"].id,
                            user_id=two_orgs["a"]["user"].id,
                            dataset_ids=[dq_dataset.id], title="stored")
        db_session.add(conv)
        await db_session.commit()
        r = await client.post(f"/api/v1/agent/conversations/{conv.id}/ask",
                              json={"question": "hi"}, headers=auth_headers["a"])
        assert r.status_code == 400, r.text
        assert scripted == []  # refused before the agent ran at all
