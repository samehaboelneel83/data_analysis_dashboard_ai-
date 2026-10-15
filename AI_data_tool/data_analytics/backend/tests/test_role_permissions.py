"""QA E-08: a per-role capability matrix, enforced on the server.

Each capability is refused with 403 (and a readable reason) at its one choke
point when the role lacks it; it is allowed when the role has it; an org-admin
role always has it; and a role with nothing stored (every role that predates
revision 0072) keeps every right.
"""
import asyncio
import io
import os

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import role_permissions
from app.core.security import create_access_token, hash_password
from app.models.models import Conversation, Report, Role, User
from tests.test_alembic_migrations import _alembic_config

ALL = list(role_permissions.CAPABILITIES)


async def _member(db, org, *, perms=None, admin=False, email="member@example.com"):
    role = Role(org_id=org.id, name=f"R-{email}", is_org_admin=admin, permissions_raw=perms)
    db.add(role)
    await db.flush()
    user = User(org_id=org.id, role_id=role.id, email=email, password_hash=hash_password("password-m"))
    db.add(user)
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


def _csv():
    return {"file": ("t.csv", io.BytesIO(b"a,b\n1,2\n3,4\n"), "text/csv")}


# ── the stored value and its defaults ───────────────────────────────────────

def test_defaults_keep_every_right_and_admin_has_all():
    assert role_permissions.effective(Role(name="old", is_org_admin=False)) == {c: True for c in ALL}
    assert role_permissions.effective(Role(name="part", is_org_admin=False,
                                           permissions_raw={"export": False})) == \
        {c: c != "export" for c in ALL}
    assert role_permissions.effective(Role(name="adm", is_org_admin=True,
                                           permissions_raw={c: False for c in ALL})) == {c: True for c in ALL}


async def test_auth_me_carries_the_effective_permissions(client, db_session, two_orgs):
    _, h = await _member(db_session, two_orgs["a"]["org"], perms={"use_ai": False})
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    assert me["role"]["permissions"] == {c: c != "use_ai" for c in ALL}


# ── admin API: round trip, validation, audit ────────────────────────────────

async def test_admin_can_set_and_read_permissions(client, db_session, two_orgs, auth_headers):
    r = await client.post("/api/v1/admin/roles", headers=auth_headers["a"],
                          json={"name": "Viewer", "permissions": {"upload_data": False}})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert r.json()["permissions"]["upload_data"] is False
    assert r.json()["permissions"]["export"] is True
    r = await client.patch(f"/api/v1/admin/roles/{rid}", headers=auth_headers["a"],
                           json={"permissions": {"export": False}})
    assert r.status_code == 200
    assert r.json()["permissions"] == {c: c not in ("upload_data", "export") for c in ALL}
    listed = {x["id"]: x for x in (await client.get("/api/v1/admin/roles", headers=auth_headers["a"])).json()}
    assert listed[rid]["permissions"]["export"] is False
    from sqlalchemy import select
    from app.models.models import AdminAudit
    details = (await db_session.execute(select(AdminAudit.detail).where(
        AdminAudit.action == "role.update"))).scalars().all()
    assert any("export denied" in (d or "") for d in details)


async def test_unknown_permission_is_422(client, two_orgs, auth_headers):
    r = await client.post("/api/v1/admin/roles", headers=auth_headers["a"],
                          json={"name": "X", "permissions": {"fly": False}})
    assert r.status_code == 422
    assert "fly" in r.json()["detail"]


async def test_non_admin_cannot_change_permissions(client, db_session, two_orgs):
    user, h = await _member(db_session, two_orgs["a"]["org"])
    r = await client.patch(f"/api/v1/admin/roles/{user.role_id}", headers=h,
                           json={"permissions": {"export": True}})
    assert r.status_code == 403


# ── enforcement, one capability at a time ───────────────────────────────────

async def test_upload_data(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"]
    _, denied = await _member(db_session, org, perms={"upload_data": False}, email="d@example.com")
    _, allowed = await _member(db_session, org, perms={"export": False}, email="a@example.com")
    r = await client.post("/api/v1/datasets", files=_csv(), data={"name": "t"}, headers=denied)
    assert r.status_code == 403
    assert "upload data" in r.json()["detail"]
    r = await client.post("/api/v1/datasets/batch", files=[("files", ("t.csv", b"a\n1\n", "text/csv"))],
                          data={"name": "t"}, headers=denied)
    assert r.status_code == 403
    assert (await client.post("/api/v1/datasets", files=_csv(), data={"name": "t"},
                              headers=allowed)).status_code == 200
    assert (await client.post("/api/v1/datasets", files=_csv(), data={"name": "t2"},
                              headers=auth_headers["a"])).status_code == 200


async def test_create_connection(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"]
    _, denied = await _member(db_session, org, perms={"create_connection": False}, email="d@example.com")
    _, allowed = await _member(db_session, org, email="a@example.com")
    body = {"name": "wh", "type": "postgresql", "config": {"host": "db.invalid"}}
    r = await client.post("/api/v1/data-sources", json=body, headers=denied)
    assert r.status_code == 403
    assert "add connections" in r.json()["detail"]
    assert (await client.post("/api/v1/data-sources", json=body, headers=allowed)).status_code == 200


async def test_create_dashboard(client, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    denied_user, denied = await _member(db_session, org, perms={"create_dashboard": False}, email="d@example.com")
    _, allowed = await _member(db_session, org, email="a@example.com")
    r = await client.post("/api/v1/reports", json={"name": "x"}, headers=denied)
    assert r.status_code == 403
    assert "create dashboards" in r.json()["detail"]
    made = await client.post("/api/v1/reports", json={"name": "x"}, headers=allowed)
    assert made.status_code == 201
    # A copy is a new dashboard too (of one they own and can see).
    own = Report(name="mine", org_id=org.id, created_by=denied_user.id)
    db_session.add(own)
    await db_session.commit()
    r = await client.post(f"/api/v1/reports/{own.id}/duplicate", json={}, headers=denied)
    assert r.status_code == 403


async def test_export(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"]
    denied_user, denied = await _member(db_session, org, perms={"export": False}, email="d@example.com")
    did = (await client.post("/api/v1/datasets", files=_csv(), data={"name": "t"}, headers=denied)).json()["id"]
    r = await client.get(f"/api/v1/datasets/{did}/export", headers=denied)
    assert r.status_code == 403
    assert "download or export" in r.json()["detail"]
    # The shared download gate (dashboards, widgets, semantic) refuses too.
    from fastapi import HTTPException
    from app.routers.shared import download_gate
    await db_session.refresh(denied_user, ["role"])
    with pytest.raises(HTTPException) as e:
        await download_gate(db_session, denied_user, dataset_id=did)
    assert e.value.status_code == 403
    _, allowed = await _member(db_session, org, email="a@example.com")
    own = (await client.post("/api/v1/datasets", files=_csv(), data={"name": "u"}, headers=allowed)).json()["id"]
    assert (await client.get(f"/api/v1/datasets/{own}/export", headers=allowed)).status_code == 200


async def test_use_ai_ask_is_403_and_model_calls_are_refused(client, db_session, two_orgs, monkeypatch):
    org = two_orgs["a"]["org"]
    user, denied = await _member(db_session, org, perms={"use_ai": False}, email="d@example.com")
    conv = Conversation(org_id=org.id, user_id=user.id, dataset_ids=[])
    db_session.add(conv)
    await db_session.commit()
    r = await client.post(f"/api/v1/agent/conversations/{conv.id}/ask", json={"question": "q"}, headers=denied)
    assert r.status_code == 403
    assert "use AI" in r.json()["detail"]

    # A feature where the model only embellishes falls back: no request leaves.
    from app.services import llm, quotas
    meter = await quotas.open_ai_meter(db_session, org.id, user.id, "insights")
    assert meter.denied
    client_ = llm.LLMClient(base_url="http://model.invalid", model="m", enabled=True)
    sent = []

    async def _no_post(*a, **k):
        sent.append(1)
        return "x"
    monkeypatch.setattr(client_, "_post", _no_post)
    token = llm.use_meter(meter)
    try:
        assert await client_.complete([{"role": "user", "content": "hi"}]) is None
    finally:
        llm._meter.reset(token)
    assert sent == []


async def test_use_ai_allowed_role_and_admin_are_not_denied(db_session, two_orgs):
    from app.services import quotas
    org = two_orgs["a"]["org"]
    user, _ = await _member(db_session, org, perms={"export": False})
    assert (await quotas.open_ai_meter(db_session, org.id, user.id, "ask")).denied is None
    admin = two_orgs["a"]["user"]
    assert (await quotas.open_ai_meter(db_session, org.id, admin.id, "ask")).denied is None
    # Scheduled work with nobody behind it is not refused.
    assert (await quotas.open_ai_meter(db_session, org.id, None, "ask")).denied is None


async def test_admin_role_always_allowed_whatever_is_stored(client, db_session, two_orgs):
    _, h = await _member(db_session, two_orgs["a"]["org"], admin=True,
                         perms={c: False for c in ALL}, email="boss@example.com")
    assert (await client.post("/api/v1/reports", json={"name": "x"}, headers=h)).status_code == 201
    assert (await client.post("/api/v1/datasets", files=_csv(), data={"name": "t"},
                              headers=h)).status_code == 200


# ── migration ───────────────────────────────────────────────────────────────

PREV = "0070_roles_org_name_unique"


@pytest.fixture
def scratch_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'perms.db'}"
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield url
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


async def test_migration_adds_column_existing_roles_keep_every_right(scratch_url):
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, PREV)
    engine = create_async_engine(scratch_url)
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'A')"))
        await conn.execute(text("INSERT INTO roles (id, org_id, name, is_org_admin) "
                                "VALUES (1, 1, 'Analyst', 0), (2, 1, 'Admin', 1)"))
    await asyncio.to_thread(command.upgrade, cfg, "0072_role_capabilities")
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, name, is_org_admin, permissions FROM roles ORDER BY id"))).fetchall()
    assert [r[3] for r in rows] == [None, None]
    for _id, name, is_admin, raw in rows:
        assert role_permissions.effective(Role(name=name, is_org_admin=bool(is_admin),
                                               permissions_raw=raw)) == {c: True for c in ALL}
    await asyncio.to_thread(command.downgrade, cfg, PREV)
    async with engine.connect() as conn:
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(roles)"))).fetchall()]
    assert "permissions" not in cols
    await asyncio.to_thread(command.upgrade, cfg, "0072_role_capabilities")
    await engine.dispose()


async def test_download_decision_says_no_for_a_role_without_export(client, db_session, two_orgs):
    """The UI greys export from /authz/decisions; it must give the same answer."""
    org = two_orgs["a"]["org"]
    user, denied = await _member(db_session, org, perms={"export": False}, email="d@example.com")
    rep = Report(name="mine", org_id=org.id, created_by=user.id)
    db_session.add(rep)
    await db_session.commit()
    r = await client.post("/api/v1/authz/decisions", headers=denied,
                          json={"checks": [{"resource": "report", "id": rep.id, "action": "download"}]})
    assert r.status_code == 200
    d = r.json()["decisions"][0] if isinstance(r.json(), dict) else r.json()[0]
    assert d["allowed"] is False
    assert "download or export" in d["reason"]
