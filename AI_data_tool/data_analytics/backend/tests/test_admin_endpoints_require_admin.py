import pytest
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.models import Role, User
from tests._routes import served_routes


async def _seed_non_admin_user(db_session, org_id):
    role = Role(org_id=org_id, name="NonAdmin", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email="sweep-non-admin@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _admin_routes():
    routes = []
    for route in served_routes(app):
        path = route.path
        if not path.startswith("/api/v1/admin"):
            continue
        for method in sorted(route.methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            routes.append((method, path))
    return routes


def test_the_sweep_finds_the_admin_routes():
    # An empty list parametrizes nothing, and the sweep below would then pass
    # while checking nothing -- which is what FastAPI 0.137's routing change did
    # to a direct walk of app.routes.
    assert len(_admin_routes()) >= 10


@pytest.mark.parametrize("method,path", _admin_routes())
async def test_admin_route_rejects_non_admin(client, db_session, two_orgs, method, path):
    user = await _seed_non_admin_user(db_session, two_orgs["a"]["org"].id)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    # Substitute any path parameters with a harmless placeholder ID — the admin check
    # must fire before any ID is even looked up, so the specific value never matters.
    concrete_path = path
    for param in ("role_id", "user_id", "rule_id"):
        concrete_path = concrete_path.replace(f"{{{param}}}", "1")

    resp = await client.request(method, concrete_path, headers=headers, json={} if method in ("POST", "PATCH", "PUT") else None)

    assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}, expected 403 for a non-admin caller"
