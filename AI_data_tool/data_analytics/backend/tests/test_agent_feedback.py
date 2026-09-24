"""T4: 👍/👎 feedback on an agent answer. Owner-only (same-org, different-user
is a 404, matching /ask and /runs/{id}'s existing scoping), and upserted per
(run_id, user) rather than accumulating a new row on every re-rate.
"""
import pytest
from sqlalchemy import select

from app.models.models import AgentFeedback, AgentRun, DataSource, User


@pytest.fixture
def scripted_ok(monkeypatch):
    """Replace run_agent with a deterministic stand-in -- the router's job
    under test is feedback plumbing/scoping, not the graph."""
    async def fake_run(db, *, question, source, user, client,
                       conversation_id=None, **kw):
        run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                       question=question, status="ok", intent="aggregate",
                       answer="Total is 30.")
        db.add(run)
        await db.flush()
        return run
    monkeypatch.setattr("app.routers.agent.run_agent", fake_run)
    return fake_run


@pytest.fixture
async def seeded_source(db_session, two_orgs):
    src = DataSource(name="wh-a", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    return src


@pytest.fixture
async def same_org_second_user(db_session, two_orgs):
    from app.core.security import create_access_token, hash_password

    org_a = two_orgs["a"]["org"]
    role_a = two_orgs["a"]["role"]
    user = User(org_id=org_a.id, role_id=role_a.id, email="second@example.com",
               password_hash=hash_password("password-2"))
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    return {"user": user, "headers": headers}


async def _conversation_and_run(client, auth_headers, seeded_source):
    r = await client.post("/api/v1/agent/conversations",
                          json={"data_source_id": seeded_source.id},
                          headers=auth_headers)
    cid = r.json()["id"]
    asked = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                              json={"question": "total sales"},
                              headers=auth_headers)
    return cid, asked.json()["run_id"]


class TestOwnerScoping:
    async def test_owner_can_rate(self, client, auth_headers, seeded_source,
                                  scripted_ok, db_session):
        cid, run_id = await _conversation_and_run(client, auth_headers["a"], seeded_source)

        r = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                              json={"run_id": run_id, "rating": "up"},
                              headers=auth_headers["a"])

        assert r.status_code == 200
        assert r.json()["rating"] == "up"
        rows = (await db_session.execute(select(AgentFeedback))).scalars().all()
        assert len(rows) == 1
        assert rows[0].run_id == run_id
        assert rows[0].rating == "up"

    async def test_cross_org_is_404(self, client, auth_headers, seeded_source,
                                    scripted_ok):
        cid, run_id = await _conversation_and_run(client, auth_headers["a"], seeded_source)

        r = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                              json={"run_id": run_id, "rating": "up"},
                              headers=auth_headers["b"])

        assert r.status_code == 404

    async def test_same_org_different_user_is_404(self, client, auth_headers,
                                                    seeded_source, scripted_ok,
                                                    same_org_second_user):
        cid, run_id = await _conversation_and_run(client, auth_headers["a"], seeded_source)

        r = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                              json={"run_id": run_id, "rating": "down"},
                              headers=same_org_second_user["headers"])

        assert r.status_code == 404

    async def test_run_from_a_different_conversation_is_404(
            self, client, auth_headers, seeded_source, scripted_ok):
        # Two conversations, both owned by user A -- rating conversation 1
        # with conversation 2's run id must not silently succeed.
        cid1, _ = await _conversation_and_run(client, auth_headers["a"], seeded_source)
        cid2, run_id_2 = await _conversation_and_run(client, auth_headers["a"], seeded_source)
        assert cid1 != cid2

        r = await client.post(f"/api/v1/agent/conversations/{cid1}/feedback",
                              json={"run_id": run_id_2, "rating": "up"},
                              headers=auth_headers["a"])

        assert r.status_code == 404


class TestValidationAndUpsert:
    async def test_invalid_rating_is_422(self, client, auth_headers,
                                         seeded_source, scripted_ok):
        cid, run_id = await _conversation_and_run(client, auth_headers["a"], seeded_source)

        r = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                              json={"run_id": run_id, "rating": "sideways"},
                              headers=auth_headers["a"])

        assert r.status_code == 422

    async def test_re_rating_the_same_run_upserts_not_dupes(
            self, client, auth_headers, seeded_source, scripted_ok, db_session):
        cid, run_id = await _conversation_and_run(client, auth_headers["a"], seeded_source)

        first = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                                  json={"run_id": run_id, "rating": "up"},
                                  headers=auth_headers["a"])
        second = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                                   json={"run_id": run_id, "rating": "down",
                                         "comment": "actually wrong"},
                                   headers=auth_headers["a"])

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        rows = (await db_session.execute(select(AgentFeedback))).scalars().all()
        assert len(rows) == 1
        assert rows[0].rating == "down"
        assert rows[0].comment == "actually wrong"

    async def test_feedback_without_a_run_id_targets_the_conversation(
            self, client, auth_headers, seeded_source, scripted_ok, db_session):
        cid, _run_id = await _conversation_and_run(client, auth_headers["a"], seeded_source)

        r = await client.post(f"/api/v1/agent/conversations/{cid}/feedback",
                              json={"rating": "up"},
                              headers=auth_headers["a"])

        assert r.status_code == 200
        assert r.json()["run_id"] is None
        rows = (await db_session.execute(select(AgentFeedback))).scalars().all()
        assert len(rows) == 1
        assert rows[0].run_id is None
