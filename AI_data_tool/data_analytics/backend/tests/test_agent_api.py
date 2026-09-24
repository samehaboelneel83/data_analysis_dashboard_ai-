"""The chat API. Org-scoping is the security property under test: every
cross-org probe answers 404 — a 403 would confirm the resource exists."""
import pytest
from sqlalchemy import select

from app.models.models import (AgentMessage, AgentRun, DataSource,
                               ObjectRowPolicy, Role, SourceObject, User)
from app.services.agent import graph as graph_module


@pytest.fixture
def scripted_ok(monkeypatch):
    """Replace run_agent with a deterministic stand-in: the router's job is
    plumbing and scoping, not the graph (Task 11 owns that)."""
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
    """A data source in org A, to attach conversations to."""
    src = DataSource(name="wh-a", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    return src


@pytest.fixture
async def seeded_object(db_session, seeded_source, two_orgs):
    """A SourceObject on the org-A source, to attach row policies to."""
    obj = SourceObject(data_source_id=seeded_source.id,
                       org_id=two_orgs["a"]["org"].id, name="orders")
    db_session.add(obj)
    await db_session.commit()
    return obj


@pytest.fixture
async def non_admin_user(db_session, two_orgs):
    """A non-admin user in org A, for require_org_admin probes."""
    from app.core.security import create_access_token, hash_password

    org_a = two_orgs["a"]["org"]
    role = Role(org_id=org_a.id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_a.id, role_id=role.id, email="viewer@example.com",
               password_hash=hash_password("password-v"))
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    return {"user": user, "headers": headers}


@pytest.fixture
async def same_org_second_user(db_session, two_orgs):
    """A second user in org A, distinct from two_orgs['a']['user'] — for
    same-org, different-user access-control probes (a 403-style leak that
    check_org's org-only scoping would miss)."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import User

    org_a = two_orgs["a"]["org"]
    role_a = two_orgs["a"]["role"]
    user = User(org_id=org_a.id, role_id=role_a.id, email="second@example.com",
               password_hash=hash_password("password-2"))
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    return {"user": user, "headers": headers}


class TestConversations:
    async def test_create_and_list(self, client, auth_headers, seeded_source):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id,
                                    "title": "Sales"},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        listed = await client.get("/api/v1/agent/conversations",
                                  headers=auth_headers["a"])
        assert [c["title"] for c in listed.json()] == ["Sales"]

    async def test_another_orgs_conversation_is_404(self, client,
                                                    auth_headers,
                                                    seeded_source):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id},
                              headers=auth_headers["a"])
        cid = r.json()["id"]
        probe = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                  json={"question": "q"},
                                  headers=auth_headers["b"])
        assert probe.status_code == 404

    async def test_list_excludes_another_users_conversation_same_org(
            self, client, auth_headers, seeded_source, same_org_second_user):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id,
                                    "title": "User A's chat"},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        listed = await client.get("/api/v1/agent/conversations",
                                  headers=same_org_second_user["headers"])
        assert listed.json() == []

    async def test_another_same_org_users_conversation_ask_is_404(
            self, client, auth_headers, seeded_source, same_org_second_user):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id},
                              headers=auth_headers["a"])
        cid = r.json()["id"]
        probe = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                  json={"question": "q"},
                                  headers=same_org_second_user["headers"])
        assert probe.status_code == 404


class TestAsk:
    async def test_ask_returns_the_answer_and_persists_both_messages(
            self, client, auth_headers, seeded_source, scripted_ok,
            db_session):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id},
                              headers=auth_headers["a"])
        cid = r.json()["id"]
        got = await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                json={"question": "total sales"},
                                headers=auth_headers["a"])
        assert got.status_code == 200
        assert got.json()["answer"] == "Total is 30."
        msgs = (await db_session.execute(select(AgentMessage))).scalars().all()
        assert [m.role for m in msgs] == ["user", "assistant"]

    async def test_a_run_is_readable_with_its_steps(self, client,
                                                    auth_headers,
                                                    seeded_source, scripted_ok):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id},
                              headers=auth_headers["a"])
        cid = r.json()["id"]
        run_id = (await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                    json={"question": "q"},
                                    headers=auth_headers["a"])).json()["run_id"]
        detail = await client.get(f"/api/v1/agent/runs/{run_id}",
                                  headers=auth_headers["a"])
        assert detail.status_code == 200
        assert detail.json()["status"] == "ok"

    async def test_another_same_org_users_run_detail_is_404(
            self, client, auth_headers, seeded_source, scripted_ok,
            same_org_second_user):
        r = await client.post("/api/v1/agent/conversations",
                              json={"data_source_id": seeded_source.id},
                              headers=auth_headers["a"])
        cid = r.json()["id"]
        run_id = (await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                    json={"question": "q"},
                                    headers=auth_headers["a"])).json()["run_id"]
        detail = await client.get(f"/api/v1/agent/runs/{run_id}",
                                  headers=same_org_second_user["headers"])
        assert detail.status_code == 404


class TestRowPolicies:
    async def test_crud_roundtrip(self, client, auth_headers, two_orgs,
                                   seeded_source, seeded_object):
        role_id = two_orgs["a"]["role"].id
        created = await client.post(
            "/api/v1/agent/row-policies",
            json={"source_object_id": seeded_object.id, "role_id": role_id,
                  "predicate": "region = 'us'"},
            headers=auth_headers["a"])
        assert created.status_code == 200
        policy_id = created.json()["id"]

        listed = await client.get(
            f"/api/v1/agent/row-policies?source_id={seeded_source.id}",
            headers=auth_headers["a"])
        assert listed.status_code == 200
        rows = listed.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["source_object_id"] == seeded_object.id
        assert row["object_name"] == "orders"
        assert row["role_id"] == role_id
        assert row["role_name"] == two_orgs["a"]["role"].name
        assert row["predicate"] == "region = 'us'"

        deleted = await client.delete(f"/api/v1/agent/row-policies/{policy_id}",
                                      headers=auth_headers["a"])
        assert deleted.status_code == 204

        listed_after = await client.get(
            f"/api/v1/agent/row-policies?source_id={seeded_source.id}",
            headers=auth_headers["a"])
        assert listed_after.json() == []

    async def test_non_admin_blocked(self, client, non_admin_user,
                                      seeded_source, seeded_object,
                                      two_orgs):
        got = await client.get(
            f"/api/v1/agent/row-policies?source_id={seeded_source.id}",
            headers=non_admin_user["headers"])
        assert got.status_code == 403

        posted = await client.post(
            "/api/v1/agent/row-policies",
            json={"source_object_id": seeded_object.id,
                  "role_id": two_orgs["a"]["role"].id,
                  "predicate": "1=1"},
            headers=non_admin_user["headers"])
        assert posted.status_code == 403

    async def test_list_cross_org_source_is_404(self, client, auth_headers,
                                                 seeded_source):
        r = await client.get(
            f"/api/v1/agent/row-policies?source_id={seeded_source.id}",
            headers=auth_headers["b"])
        assert r.status_code == 404

    async def test_create_cross_org_source_is_404(self, client, auth_headers,
                                                    two_orgs, seeded_object):
        r = await client.post(
            "/api/v1/agent/row-policies",
            json={"source_object_id": seeded_object.id,
                  "role_id": two_orgs["b"]["role"].id,
                  "predicate": "1=1"},
            headers=auth_headers["b"])
        assert r.status_code == 404

    async def test_create_cross_org_role_is_404(self, client, auth_headers,
                                                 two_orgs, seeded_object):
        r = await client.post(
            "/api/v1/agent/row-policies",
            json={"source_object_id": seeded_object.id,
                  "role_id": two_orgs["b"]["role"].id,
                  "predicate": "1=1"},
            headers=auth_headers["a"])
        assert r.status_code == 404

    async def test_delete_cross_org_policy_is_404(self, client, auth_headers,
                                                    two_orgs, seeded_object):
        created = await client.post(
            "/api/v1/agent/row-policies",
            json={"source_object_id": seeded_object.id,
                  "role_id": two_orgs["a"]["role"].id,
                  "predicate": "1=1"},
            headers=auth_headers["a"])
        policy_id = created.json()["id"]

        r = await client.delete(f"/api/v1/agent/row-policies/{policy_id}",
                                headers=auth_headers["b"])
        assert r.status_code == 404

    async def test_unparseable_predicate_is_422(self, client, auth_headers,
                                                 two_orgs, seeded_object):
        r = await client.post(
            "/api/v1/agent/row-policies",
            json={"source_object_id": seeded_object.id,
                  "role_id": two_orgs["a"]["role"].id,
                  "predicate": "region = = 'us'"},
            headers=auth_headers["a"])
        assert r.status_code == 422

    async def test_duplicate_policy_is_409(self, client, auth_headers,
                                            two_orgs, seeded_object):
        body = {"source_object_id": seeded_object.id,
                "role_id": two_orgs["a"]["role"].id, "predicate": "1=1"}
        first = await client.post("/api/v1/agent/row-policies", json=body,
                                  headers=auth_headers["a"])
        assert first.status_code == 200
        second = await client.post("/api/v1/agent/row-policies", json=body,
                                   headers=auth_headers["a"])
        assert second.status_code == 409

    async def test_create_validates_against_the_sources_own_dialect(
            self, client, auth_headers, two_orgs, db_session):
        """apply_policies (agent/policy.py) parses each predicate with the
        source's real dialect via _dialect(family) — validation here must
        use the same dialect, not a hardcoded 'postgres', or a predicate
        valid only in the source's own dialect gets wrongly rejected (or a
        postgres-only one is accepted here and fails closed at query time).
        A backtick-quoted identifier parses under mysql but not postgres, so
        it doubles as proof the mysql source's dialect was actually used."""
        import unittest.mock

        import app.routers.agent as agent_module

        org_a = two_orgs["a"]["org"]
        mysql_source = DataSource(name="wh-a-mysql", type="mysql",
                                  org_id=org_a.id)
        db_session.add(mysql_source)
        await db_session.flush()
        obj = SourceObject(data_source_id=mysql_source.id, org_id=org_a.id,
                           name="orders")
        db_session.add(obj)
        await db_session.commit()

        real_parse_one = agent_module.sqlglot.parse_one
        recorded_dialects = []

        def recording_parse_one(*args, **kwargs):
            recorded_dialects.append(kwargs.get("dialect"))
            return real_parse_one(*args, **kwargs)

        with unittest.mock.patch.object(agent_module.sqlglot, "parse_one",
                                        recording_parse_one):
            r = await client.post(
                "/api/v1/agent/row-policies",
                json={"source_object_id": obj.id,
                      "role_id": two_orgs["a"]["role"].id,
                      "predicate": "`region` = 'us'"},
                headers=auth_headers["a"])

        assert r.status_code == 200
        assert recorded_dialects == ["mysql"]
