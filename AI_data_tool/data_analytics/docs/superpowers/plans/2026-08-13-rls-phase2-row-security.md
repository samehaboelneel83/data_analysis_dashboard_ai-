# Row-Level Security Phase 2 — Row Security Proper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `RowSecurityRule` model, admin-only CRUD endpoints for managing roles/users/row-security rules, and wire rule enforcement into the widget-data query path so a non-admin role only ever sees the rows its assigned rule permits.

**Architecture:** One new table (`row_security_rules`, role_id + dataset_id + filter_expr, unique per role/dataset pair), reusing the existing `apply_filter_expr` expression engine both for authoring-time validation (raises on bad syntax) and runtime enforcement (silently no-ops on bad syntax, matching the existing widget-level filter's behavior). A new `admin.py` router exposes CRUD for `Role`/`User`/`RowSecurityRule`, gated by a new `require_org_admin` dependency. Enforcement itself happens in `widget_data.py`'s router: it looks up the caller's rule for the requested dataset (skipped entirely for `is_org_admin` roles) and passes the resulting expression into `get_widget_data`, which now applies it before the widget's own filter and before calculated columns.

**Tech Stack:** FastAPI, async SQLAlchemy, Pydantic v2 — no new dependencies. This phase builds directly on Phase 0 (auth) and Phase 1 (org scoping), both merged to `master`.

## Global Constraints

- Org-scoping checks (an object belongs to another org) always return **404**, using the existing `check_org(obj, current_user, message)` helper from `backend/app/core/org_scope.py` wherever the checked object has its own `org_id` (`Role`, `User`, `Dataset`). `RowSecurityRule` has no `org_id` of its own — its org membership is determined by its `role.org_id`, so its own get/update/delete checks are written inline (`rule is None or rule.role.org_id != current_user.org_id`), not via `check_org`.
- Admin-only endpoints (everything under `/admin/*`) return **403** via a new `require_org_admin` dependency when the caller's role has `is_org_admin=False` — this is a capability check, not an existence check, so 403 (not 404) is correct and matches the design spec's "reject non-admin users" language.
- `filter_expr` validation: **authoring time** (admin CRUD create/update) calls `apply_filter_expr(df, expr, silent=False)` against a real sample of the target dataset's file and surfaces any exception as a 400 with the error message. **Runtime** (query time, in `get_widget_data`) always uses `silent=True` — a malformed rule degrades to "no rule applied" rather than 500ing the widget, exactly like the existing widget-level `filter_expr` already behaves.
- RLS rule ordering in `get_widget_data`: the RLS filter is applied **first** (before the widget's own `filter_expr`, before `calculated_columns`). Nothing downstream can see rows the RLS rule already excluded.
- `RowSecurityRule` has a unique constraint on `(role_id, dataset_id)` — at most one rule per role per dataset. Creating a second rule for the same pair is a 400, not a silent overwrite.
- `is_org_admin=True` roles bypass RLS entirely — no rule lookup happens for them at all.
- No rule found for `(current_user.role_id, dataset_id)` means **unrestricted within the org**, not "no access." Org-level access is already gated separately by `check_org` on the dataset itself.
- Every new router endpoint requires `current_user: User = Depends(require_org_admin)` (admin endpoints) or `current_user: User = Depends(get_current_user)` (the widget-data endpoint, unchanged) — never leave a new endpoint unauthenticated.
- Reuse the existing `two_orgs` / `auth_headers` fixtures from `backend/tests/conftest.py` for every cross-org and admin-permission test — do not write new provisioning fixtures.
- Test file naming and structure follows the existing convention (see `backend/tests/test_data_sources_org_scoping.py`, `backend/tests/test_dependencies.py`): a `_seed_*` async helper at the top, one `async def test_*` per behavior, `db_session`/`client`/`two_orgs`/`auth_headers` fixtures injected by name (no explicit `@pytest.mark.asyncio` needed — `pytest.ini` sets `asyncio_mode = auto`).

---

### Task 1: `RowSecurityRule` model

**Files:**
- Modify: `backend/app/models/models.py`
- Test: `backend/tests/test_row_security_rule_model.py`

**Interfaces:**
- Produces: `RowSecurityRule` (`id`, `role_id`, `dataset_id`, `filter_expr`, `created_at`, relationships `role`/`dataset`), and `Role.rules` (back-populated list). Later tasks query `RowSecurityRule` by `role_id`/`dataset_id` and read `.filter_expr`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_row_security_rule_model.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.models import Organization, Role, Dataset, RowSecurityRule


async def _seed_role_and_dataset(db_session):
    org = Organization(name="Org")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Regional", is_org_admin=False)
    ds = Dataset(name="D", org_id=org.id)
    db_session.add_all([role, ds])
    await db_session.flush()
    return role, ds


async def test_row_security_rule_round_trip(db_session):
    role, ds = await _seed_role_and_dataset(db_session)
    rule = RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    assert rule.id is not None
    assert rule.role.id == role.id
    assert rule.dataset.id == ds.id
    assert rule.filter_expr == "region == 'North'"


async def test_row_security_rule_unique_per_role_and_dataset(db_session):
    role, ds = await _seed_role_and_dataset(db_session)
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="a == 1"))
    await db_session.commit()

    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="b == 2"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_role_cascades_to_its_rules(db_session):
    role, ds = await _seed_role_and_dataset(db_session)
    rule = RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="a == 1")
    db_session.add(rule)
    await db_session.commit()
    rule_id = rule.id

    await db_session.delete(role)
    await db_session.commit()

    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == rule_id))
    assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_row_security_rule_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'RowSecurityRule'`.

- [ ] **Step 3: Add the model**

In `backend/app/models/models.py`, add `UniqueConstraint` to the existing `sqlalchemy` import on line 2:

```python
from sqlalchemy import Column, Integer, String, Text, Float, BigInteger, DateTime, ForeignKey, JSON, Boolean, UniqueConstraint
```

Add `rules = relationship("RowSecurityRule", back_populates="role", cascade="all, delete-orphan")` to the `Role` class (after the existing `users` line, so `Role` reads):

```python
class Role(Base):
    __tablename__ = "roles"
    id           = Column(Integer, primary_key=True)
    org_id       = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(255), nullable=False)
    is_org_admin = Column(Boolean, nullable=False, default=False)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="roles")
    users        = relationship("User", back_populates="role")
    rules        = relationship("RowSecurityRule", back_populates="role", cascade="all, delete-orphan")
```

Append the new model at the end of the file, after `User`:

```python
class RowSecurityRule(Base):
    __tablename__ = "row_security_rules"
    id          = Column(Integer, primary_key=True)
    role_id     = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    filter_expr = Column(Text, nullable=False)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("role_id", "dataset_id", name="uq_role_dataset_rule"),)

    role    = relationship("Role", back_populates="rules")
    dataset = relationship("Dataset")
```

No `_migrate()` change is needed in `backend/app/main.py` — `row_security_rules` is a brand-new table, picked up automatically by `Base.metadata.create_all` on startup, exactly like `organizations`/`roles`/`users` were in Phase 0.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_row_security_rule_model.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/tests/test_row_security_rule_model.py
git commit -m "feat: add RowSecurityRule model"
```

---

### Task 2: `require_org_admin` dependency + admin CRUD schemas

**Files:**
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/schemas/schemas.py`
- Test: `backend/tests/test_require_org_admin.py`

**Interfaces:**
- Consumes: `User.role.is_org_admin` (Phase 0/1, already loaded by `get_current_user`'s `selectinload`).
- Produces: `require_org_admin(current_user: User = Depends(get_current_user)) -> User` — later tasks depend on this for every `/admin/*` endpoint. Schema classes `RoleCreate`, `RoleUpdate`, `UserCreate`, `UserUpdate`, `RowSecurityRuleCreate`, `RowSecurityRuleUpdate`, `RowSecurityRuleOut` — later tasks' request/response models.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_require_org_admin.py`:

```python
import pytest
from fastapi import HTTPException
from app.core.security import hash_password
from app.dependencies import require_org_admin
from app.models.models import Organization, Role, User


async def _seed_user(db_session, is_org_admin: bool) -> User:
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Some Role", is_org_admin=is_org_admin)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="u@acme.com", password_hash=hash_password("secret"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user.role = role
    return user


async def test_require_org_admin_allows_org_admin(db_session):
    user = await _seed_user(db_session, is_org_admin=True)

    result = await require_org_admin(current_user=user)

    assert result is user


async def test_require_org_admin_rejects_non_admin(db_session):
    user = await _seed_user(db_session, is_org_admin=False)

    with pytest.raises(HTTPException) as exc_info:
        await require_org_admin(current_user=user)

    assert exc_info.value.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_require_org_admin.py -v`
Expected: FAIL — `ImportError: cannot import name 'require_org_admin'`.

- [ ] **Step 3: Add the dependency**

Append to `backend/app/dependencies.py`:

```python
async def require_org_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.role.is_org_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return current_user
```

(`status` and `HTTPException` are already imported at the top of this file from Phase 0.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_require_org_admin.py -v`
Expected: 2 passed.

- [ ] **Step 5: Add the admin CRUD schemas**

Append to `backend/app/schemas/schemas.py` (after the existing `TokenOut` class at the end of the file):

```python
class RoleCreate(BaseModel):
    name: str
    is_org_admin: bool = False


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    is_org_admin: Optional[bool] = None


class UserCreate(BaseModel):
    email: str
    password: str
    role_id: int


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None


class RowSecurityRuleCreate(BaseModel):
    role_id: int
    dataset_id: int
    filter_expr: str


class RowSecurityRuleUpdate(BaseModel):
    filter_expr: str


class RowSecurityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role_id: int
    dataset_id: int
    filter_expr: str
    created_at: datetime
```

These have no dedicated test — they're exercised end-to-end by Tasks 3-5's endpoint tests, consistent with how `WidgetCreate`/`DatasetOut`/etc. have no standalone schema tests elsewhere in this codebase.

- [ ] **Step 6: Verify the app still imports cleanly**

Run: `cd backend && python -c "from app.main import app"`
Expected: no output, exit code 0.

- [ ] **Step 7: Commit**

```bash
git add backend/app/dependencies.py backend/app/schemas/schemas.py backend/tests/test_require_org_admin.py
git commit -m "feat: add require_org_admin dependency and admin CRUD schemas"
```

---

### Task 3: Admin router — Role CRUD

**Files:**
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_admin_roles.py`

**Interfaces:**
- Consumes: `require_org_admin` (Task 2), `check_org` (`backend/app/core/org_scope.py`, Phase 1), `RoleCreate`/`RoleUpdate`/`RoleOut` (Task 2 + Phase 0).
- Produces: `router = APIRouter(prefix="/admin", tags=["admin"])` in `admin.py` — Tasks 4 and 5 add more endpoints to this same router object.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_roles.py`:

```python
from sqlalchemy import select
from app.models.models import Role


async def test_list_roles_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    resp = await client.get("/api/v1/admin/roles", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert names == ["Admin"]  # only org A's auto-created Admin role, not org B's


async def test_create_role_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/roles", json={"name": "Regional Manager", "is_org_admin": False}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(Role).where(Role.id == resp.json()["id"]))
    role = result.scalar_one()
    assert role.org_id == two_orgs["a"]["org"].id
    assert role.is_org_admin is False


async def test_update_role_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    resp = await client.patch(
        f"/api/v1/admin/roles/{two_orgs['b']['role'].id}", json={"name": "Hacked"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_delete_role_with_assigned_users_is_rejected(client, db_session, two_orgs, auth_headers):
    # two_orgs["a"]["role"] already has two_orgs["a"]["user"] assigned to it.
    resp = await client.delete(f"/api/v1/admin/roles/{two_orgs['a']['role'].id}", headers=auth_headers["a"])

    assert resp.status_code == 400


async def test_non_admin_cannot_list_roles(client, db_session, two_orgs):
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User

    non_admin_role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
    db_session.add(non_admin_role)
    await db_session.flush()
    non_admin_user = User(
        org_id=two_orgs["a"]["org"].id, role_id=non_admin_role.id,
        email="viewer@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(non_admin_user)
    await db_session.commit()
    await db_session.refresh(non_admin_user)
    headers = {"Authorization": f"Bearer {create_access_token(non_admin_user.id, non_admin_user.org_id)}"}

    resp = await client.get("/api/v1/admin/roles", headers=headers)

    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_admin_roles.py -v`
Expected: FAIL — 404s on every request (no `/api/v1/admin/roles` route registered yet).

- [ ] **Step 3: Create the admin router with Role endpoints**

Create `backend/app/routers/admin.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import require_org_admin
from ..models.models import Role, User
from ..schemas.schemas import RoleCreate, RoleUpdate, RoleOut

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Roles ────────────────────────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(select(Role).where(Role.org_id == current_user.org_id))
    return result.scalars().all()


@router.post("/roles", response_model=RoleOut)
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = Role(org_id=current_user.org_id, name=body.name, is_org_admin=body.is_org_admin)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(role_id: int, body: RoleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, role_id)
    check_org(role, current_user, "Role not found")
    if body.name is not None:
        role.name = body.name
    if body.is_org_admin is not None:
        role.is_org_admin = body.is_org_admin
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, role_id)
    check_org(role, current_user, "Role not found")
    result = await db.execute(select(User).where(User.role_id == role_id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(400, "Cannot delete a role that still has users assigned")
    await db.delete(role)
    await db.commit()
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, change the router import (line 9) to include `admin`:

```python
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources, auth, admin
```

Add the include line after the existing `auth.router` line (line 79):

```python
app.include_router(admin.router,        prefix="/api/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_admin_roles.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass (no regressions from the router registration).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/admin.py backend/app/main.py backend/tests/test_admin_roles.py
git commit -m "feat: add admin role CRUD endpoints"
```

---

### Task 4: Admin router — User CRUD

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_users.py`

**Interfaces:**
- Consumes: everything from Task 3, plus `UserCreate`/`UserUpdate`/`UserOut` (Task 2 + Phase 0), `hash_password` (`backend/app/core/security.py`, Phase 0).
- Produces: `/admin/users` CRUD endpoints on the same `router`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_users.py`:

```python
from sqlalchemy import select
from app.models.models import User


async def test_list_users_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    resp = await client.get("/api/v1/admin/users", headers=auth_headers["a"])

    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert emails == ["admin-a@example.com"]


async def test_create_user_sets_org_id_and_hashes_password(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "new@example.com", "password": "s3cret", "role_id": two_orgs["a"]["role"].id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(User).where(User.email == "new@example.com"))
    user = result.scalar_one()
    assert user.org_id == two_orgs["a"]["org"].id
    assert user.password_hash != "s3cret"


async def test_create_user_with_role_from_another_org_returns_404(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "new2@example.com", "password": "s3cret", "role_id": two_orgs["b"]["role"].id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_create_user_with_duplicate_email_returns_400(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "admin-a@example.com", "password": "s3cret", "role_id": two_orgs["a"]["role"].id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_update_user_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    resp = await client.patch(
        f"/api/v1/admin/users/{two_orgs['b']['user'].id}", json={"is_active": False}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_delete_user_cannot_delete_self(client, db_session, two_orgs, auth_headers):
    resp = await client.delete(f"/api/v1/admin/users/{two_orgs['a']['user'].id}", headers=auth_headers["a"])

    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_admin_users.py -v`
Expected: FAIL — 404s (no `/api/v1/admin/users` route registered yet).

- [ ] **Step 3: Add User endpoints to the admin router**

In `backend/app/routers/admin.py`, update the imports at the top:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.security import hash_password
from ..dependencies import require_org_admin
from ..models.models import Role, User
from ..schemas.schemas import RoleCreate, RoleUpdate, RoleOut, UserCreate, UserUpdate, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])
```

Append after the Role endpoints (before the final blank line):

```python
# ── Users ────────────────────────────────────────────────────────────────────

async def _load_user_out(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization)).where(User.id == user_id)
    )
    return result.scalar_one()


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization))
        .where(User.org_id == current_user.org_id)
    )
    return result.scalars().all()


@router.post("/users", response_model=UserOut)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, body.role_id)
    check_org(role, current_user, "Role not found")
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(400, "Email already in use")
    user = User(
        org_id=current_user.org_id, role_id=body.role_id,
        email=body.email, password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    return await _load_user_out(db, user.id)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    user = await db.get(User, user_id)
    check_org(user, current_user, "User not found")
    if body.email is not None:
        user.email = body.email
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role_id is not None:
        role = await db.get(Role, body.role_id)
        check_org(role, current_user, "Role not found")
        user.role_id = body.role_id
    if body.is_active is not None:
        user.is_active = body.is_active
    await db.commit()
    return await _load_user_out(db, user.id)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    user = await db.get(User, user_id)
    check_org(user, current_user, "User not found")
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    await db.delete(user)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_admin_users.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_users.py
git commit -m "feat: add admin user CRUD endpoints"
```

---

### Task 5: Admin router — RowSecurityRule CRUD with filter_expr validation

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_row_security_rules.py`

**Interfaces:**
- Consumes: everything from Tasks 3-4, plus `RowSecurityRule` (Task 1), `RowSecurityRuleCreate`/`RowSecurityRuleUpdate`/`RowSecurityRuleOut` (Task 2), `apply_filter_expr` (`backend/app/services/widget_data.py`, existing), `load_file` (`backend/app/services/analytics.py`, existing).
- Produces: `/admin/row-security-rules` CRUD endpoints on the same `router`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_row_security_rules.py`:

```python
import pandas as pd
from sqlalchemy import select
from app.models.models import Dataset, RowSecurityRule


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_create_rule_valid_expression(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == resp.json()["id"]))
    assert result.scalar_one() is not None


async def test_create_rule_invalid_expression_returns_400(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "not a valid expr((("},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.dataset_id == ds.id))
    assert result.scalar_one_or_none() is None


async def test_create_rule_with_dataset_from_another_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["b"]["org"].id, [{"region": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_create_duplicate_rule_for_same_role_and_dataset_returns_400(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )
    db_session.add(RowSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'"))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'South'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_update_rule_cross_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["b"]["org"].id, [{"region": "North", "sales": 100}],
    )
    rule = RowSecurityRule(role_id=two_orgs["b"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    resp = await client.patch(
        f"/api/v1/admin/row-security-rules/{rule.id}", json={"filter_expr": "region == 'South'"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_delete_rule(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )
    rule = RowSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    resp = await client.delete(f"/api/v1/admin/row-security-rules/{rule.id}", headers=auth_headers["a"])

    assert resp.status_code == 204
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == rule.id))
    assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_admin_row_security_rules.py -v`
Expected: FAIL — 404s (no `/api/v1/admin/row-security-rules` route registered yet).

- [ ] **Step 3: Add RowSecurityRule endpoints to the admin router**

In `backend/app/routers/admin.py`, update the imports at the top:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.security import hash_password
from ..dependencies import require_org_admin
from ..models.models import Dataset, Role, RowSecurityRule, User
from ..schemas.schemas import (
    RoleCreate, RoleUpdate, RoleOut,
    UserCreate, UserUpdate, UserOut,
    RowSecurityRuleCreate, RowSecurityRuleUpdate, RowSecurityRuleOut,
)
from ..services.analytics import load_file
from ..services.widget_data import apply_filter_expr

router = APIRouter(prefix="/admin", tags=["admin"])
```

Append after the User endpoints (before the final blank line):

```python
# ── Row Security Rules ─────────────────────────────────────────────────────

async def _validate_filter_expr(dataset: Dataset, filter_expr: str) -> None:
    if not dataset.filename:
        raise HTTPException(400, "Dataset has no data file to validate the expression against")
    try:
        df = load_file(dataset.filename)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, f"Could not load dataset file to validate the expression: {e}")
    try:
        apply_filter_expr(df, filter_expr, silent=False)
    except Exception as e:
        raise HTTPException(400, f"Invalid filter expression: {e}")


@router.get("/row-security-rules", response_model=list[RowSecurityRuleOut])
async def list_rules(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(
        select(RowSecurityRule).join(Role, RowSecurityRule.role_id == Role.id)
        .where(Role.org_id == current_user.org_id)
    )
    return result.scalars().all()


@router.post("/row-security-rules", response_model=RowSecurityRuleOut)
async def create_rule(body: RowSecurityRuleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, body.role_id)
    check_org(role, current_user, "Role not found")
    dataset = await db.get(Dataset, body.dataset_id)
    check_org(dataset, current_user, "Dataset not found")
    await _validate_filter_expr(dataset, body.filter_expr)

    existing = await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == body.role_id, RowSecurityRule.dataset_id == body.dataset_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(400, "A rule for this role and dataset already exists")

    rule = RowSecurityRule(role_id=body.role_id, dataset_id=body.dataset_id, filter_expr=body.filter_expr)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def _get_rule_in_org(db: AsyncSession, rule_id: int, current_user: User) -> RowSecurityRule:
    result = await db.execute(
        select(RowSecurityRule).options(selectinload(RowSecurityRule.role)).where(RowSecurityRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None or rule.role.org_id != current_user.org_id:
        raise HTTPException(404, "Rule not found")
    return rule


@router.patch("/row-security-rules/{rule_id}", response_model=RowSecurityRuleOut)
async def update_rule(rule_id: int, body: RowSecurityRuleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    rule = await _get_rule_in_org(db, rule_id, current_user)
    dataset = await db.get(Dataset, rule.dataset_id)
    await _validate_filter_expr(dataset, body.filter_expr)
    rule.filter_expr = body.filter_expr
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/row-security-rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    rule = await _get_rule_in_org(db, rule_id, current_user)
    await db.delete(rule)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_admin_row_security_rules.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_row_security_rules.py
git commit -m "feat: add admin row-security-rule CRUD endpoints with expr validation"
```

---

### Task 6: Wire RLS enforcement into the widget-data query path

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Modify: `backend/app/routers/widget_data.py`
- Test: `backend/tests/test_get_widget_data_rls.py` (service-level)
- Test: `backend/tests/test_widget_data_rls_enforcement.py` (router-level, end-to-end)
- Modify: `docs/superpowers/specs/2026-08-13-row-level-security-design.md` (status line)

**Interfaces:**
- Consumes: `RowSecurityRule` (Task 1), `apply_filter_expr` (existing).
- Produces: `get_widget_data(..., rls_filter_expr: str | None = None)` — the RLS-specific parameter, kept separate from the widget's own `filter_expr` so ordering (RLS first) is explicit at the call site rather than relying on caller-side string concatenation.

**Design note (deviation from the spec's literal pseudocode):** the design spec's Section "Row-Level Security Enforcement" sketches the rule lookup happening inside `get_widget_data` itself, with a `current_user: User` parameter. `widget_data.py` is a synchronous, DB-free module (it only reads files via pandas) — every other function in it takes `df`/`file_path`/`config`, never a live DB session or ORM model. Importing `User`/`RowSecurityRule`/an `AsyncSession` into it to do the lookup there would introduce the file's first DB dependency and force it async. The router (`backend/app/routers/widget_data.py`) already holds `db` and `current_user` for the org-scoping check that runs immediately before this — it does the rule lookup itself and passes the resolved expression string down as `rls_filter_expr`. Behavior matches the spec exactly (rule applied first, `is_org_admin` bypasses, silent at runtime); only the lookup's location differs.

- [ ] **Step 1: Write the failing service-level test**

Create `backend/tests/test_get_widget_data_rls.py`:

```python
import pandas as pd
from app.services.widget_data import get_widget_data


def _write_csv(tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def test_rls_filter_applied_before_widget_filter_and_calculated_columns(tmp_path):
    path = _write_csv(tmp_path, [
        {"region": "North", "sales": 100}, {"region": "North", "sales": 50},
        {"region": "South", "sales": 200},
    ])

    result = get_widget_data(
        path, {"dimension": "region", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
        rls_filter_expr="region == 'North'",
    )

    assert [r["name"] for r in result["rows"]] == ["North"]
    assert result["rows"][0]["value"] == 150


def test_no_rls_filter_means_unrestricted(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])

    result = get_widget_data(
        path, {"dimension": "region", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
    )

    assert {r["name"] for r in result["rows"]} == {"North", "South"}


def test_malformed_rls_filter_degrades_to_unrestricted(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])

    result = get_widget_data(
        path, {"dimension": "region", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
        rls_filter_expr="not a valid expr(((",
    )

    assert {r["name"] for r in result["rows"]} == {"North", "South"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_get_widget_data_rls.py -v`
Expected: FAIL — `TypeError: get_widget_data() got an unexpected keyword argument 'rls_filter_expr'`.

- [ ] **Step 3: Update `get_widget_data`**

In `backend/app/services/widget_data.py`, replace the final function (currently lines 900-906):

```python
def get_widget_data(file_path: str, config: dict, widget_type: str = "bar", calculated_columns: list[dict] | None = None, filter_expr: str | None = None) -> dict:
    df = load_file(file_path)
    if filter_expr:
        df = apply_filter_expr(df, filter_expr, silent=True)
    if calculated_columns:
        df = apply_calculated_columns(df, calculated_columns)
    return get_widget_data_from_df(df, config, widget_type)
```

with:

```python
def get_widget_data(file_path: str, config: dict, widget_type: str = "bar", calculated_columns: list[dict] | None = None, filter_expr: str | None = None, rls_filter_expr: str | None = None) -> dict:
    df = load_file(file_path)
    if rls_filter_expr:
        df = apply_filter_expr(df, rls_filter_expr, silent=True)
    if filter_expr:
        df = apply_filter_expr(df, filter_expr, silent=True)
    if calculated_columns:
        df = apply_calculated_columns(df, calculated_columns)
    return get_widget_data_from_df(df, config, widget_type)
```

- [ ] **Step 4: Run the service-level tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_get_widget_data_rls.py -v`
Expected: 3 passed.

- [ ] **Step 5: Write the failing router-level (end-to-end) tests**

Create `backend/tests/test_widget_data_rls_enforcement.py`:

```python
import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id=None, rule_filter_expr=None):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    if rule_dataset_id is not None:
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


def _headers_for(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_rls_rule_filters_rows_for_restricted_role(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}, {"region": "North", "sales": 50}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert [r["name"] for r in rows] == ["North"]
    assert rows[0]["value"] == 150


async def test_org_admin_bypasses_rls_rule_entirely(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    # A rule exists for a different (non-admin) role in the same org and dataset —
    # the org-admin's own role has no rule and is exempt from lookup regardless.
    await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    assert {r["name"] for r in resp.json()["rows"]} == {"North", "South"}


async def test_no_matching_rule_means_unrestricted_within_org(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    # Restricted role exists but has no rule for this dataset.
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    assert {r["name"] for r in resp.json()["rows"]} == {"North", "South"}
```

This file has 3 test functions: `test_rls_rule_filters_rows_for_restricted_role`, `test_org_admin_bypasses_rls_rule_entirely`, `test_no_matching_rule_means_unrestricted_within_org`.

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_widget_data_rls_enforcement.py -v`
Expected: FAIL — `test_rls_rule_filters_rows_for_restricted_role` returns unfiltered rows (both North and South), since nothing looks up the rule yet.

- [ ] **Step 7: Wire the rule lookup into the widget_data router**

Replace the full contents of `backend/app/routers/widget_data.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, RowSecurityRule, User
from ..schemas.schemas import WidgetDataRequest
from ..services.widget_data import get_widget_data

router = APIRouter(prefix="/datasets", tags=["widget-data"])


@router.post("/{dataset_id}/widget-data")
async def query_widget(dataset_id: int, req: WidgetDataRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    rls_filter_expr = None
    if not current_user.role.is_org_admin:
        result = await db.execute(
            select(RowSecurityRule).where(
                RowSecurityRule.role_id == current_user.role_id, RowSecurityRule.dataset_id == dataset_id,
            )
        )
        rule = result.scalar_one_or_none()
        if rule:
            rls_filter_expr = rule.filter_expr

    calc_cols = list(req.calculated_columns or []) + list(ds.calculated_columns or [])
    try:
        return get_widget_data(
            ds.filename, req.config, widget_type=req.widget_type,
            calculated_columns=calc_cols or None, filter_expr=ds.default_filter_expr or None,
            rls_filter_expr=rls_filter_expr,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_widget_data_rls_enforcement.py -v`
Expected: 3 passed.

- [ ] **Step 9: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass, 0 failures.

- [ ] **Step 10: Update the design spec status line**

In `docs/superpowers/specs/2026-08-13-row-level-security-design.md`, change line 4 from:

```
**Status:** Phase 1 (Org Scoping) Complete
```

to:

```
**Status:** Phase 2 (Row-Level Security) Complete
```

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/widget_data.py backend/app/routers/widget_data.py \
        backend/tests/test_get_widget_data_rls.py backend/tests/test_widget_data_rls_enforcement.py \
        docs/superpowers/specs/2026-08-13-row-level-security-design.md
git commit -m "feat: enforce RowSecurityRule filtering in the widget-data query path"
```

---

### Task 7: Close the RLS bypass in data-preview, filter-preview, and analysis

**Why this task exists:** Task 6's final review found that while the widget-data path correctly enforces RLS (verified with adversarial cross-role/cross-org tests), three other endpoints on the same `Dataset` resource still return raw, unfiltered rows to any authenticated org member regardless of their role's `RowSecurityRule`: `POST /datasets/{id}/data-preview`, `POST /datasets/{id}/filter-preview` (a row-count oracle over the full dataset), and `POST /datasets/{id}/analysis` + `GET /datasets/{id}/analysis` (leaks excluded rows' aggregates and distinct values through `AnalysisResult`). A restricted role can trivially see everything their rule was meant to hide just by calling these instead of widget-data. This task closes all three so "Phase 2 (Row-Level Security) Complete" is actually true.

**Files:**
- Create: `backend/app/core/rls.py`
- Modify: `backend/app/routers/widget_data.py` (refactor Task 6's inline lookup to use the new shared helper — no behavior change, dedupes logic now that three call sites need it)
- Modify: `backend/app/routers/datasets.py` (`data_preview`, `preview_filter_expr`)
- Modify: `backend/app/routers/analysis.py` (`run_analysis`, `get_analysis`)
- Test: `backend/tests/test_data_preview_rls.py`
- Test: `backend/tests/test_filter_preview_rls.py`
- Test: `backend/tests/test_analysis_rls.py`

**Interfaces:**
- Produces: `resolve_rls_expr(db: AsyncSession, current_user: User, dataset_id: int) -> str | None` in `backend/app/core/rls.py` — returns `None` immediately for `is_org_admin` roles (no query executed), otherwise looks up the `RowSecurityRule` for `(current_user.role_id, dataset_id)` and returns its `filter_expr`, or `None` if no rule exists. Every RLS call site in this task uses this one function — no duplicate lookup logic.

**Global Constraints for this task (extends the plan's original Global Constraints section — same rules, applied to three more call sites):**
- RLS is always the floor: applied before any dataset-level `default_filter_expr`, before calculated columns, before user-supplied filters/search/sort, using `apply_filter_expr(df, rls_expr, silent=True)` — same silent-degrade-to-unrestricted behavior as Task 6.
- `is_org_admin` bypasses the lookup itself (`resolve_rls_expr` returns `None` before querying) — not just an unused result.
- **Analysis caching is incompatible with per-role RLS as currently modeled** (`AnalysisResult` is keyed only by `dataset_id` + `analysis_type`, shared org-wide, with no per-role dimension) — introducing a per-role cache key is out of scope for this task (too large a change for a follow-up fix). Instead: a restricted caller (any role where `resolve_rls_expr` returns non-`None`) never reads or writes the shared `AnalysisResult` cache. `POST /analysis` for a restricted caller always computes fresh over the RLS-filtered data and returns it without touching the `analysis_results` table. `GET /analysis` for a restricted caller never returns the cached row (which may have been computed unrestricted) — it returns 404 with the same "No analysis found — run POST first" message used for "no analysis yet," forcing the client through the live RLS-aware `POST` path instead. Unrestricted callers (`is_org_admin`, or a role with no rule for this dataset) keep the exact existing cache read/write behavior — no behavior change for them.
- `filter-preview`'s `total` and `passing` counts must both be computed within the RLS-restricted row set, not the full dataset — otherwise the endpoint remains a count oracle for excluded rows even after RLS is technically "applied."

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_data_preview_rls.py`:

```python
import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id=None, rule_filter_expr=None):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    if rule_dataset_id is not None:
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


def _headers_for(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_data_preview_applies_rls_rule(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}, {"region": "North", "sales": 50}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=_headers_for(user),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    regions = {row[0] for row in body["rows"]}
    assert regions == {"North"}


async def test_data_preview_org_admin_sees_all_rows(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json()["total"] == 2
```

Create `backend/tests/test_filter_preview_rls.py`:

```python
import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id, rule_filter_expr):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


async def test_filter_preview_total_and_passing_reflect_rls_restricted_set(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}, {"region": "North", "sales": 50}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/filter-preview", json={"expression": "sales > 0"}, headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2   # not 3 — the South row must not count toward total either
    assert body["passing"] == 2
```

Create `backend/tests/test_analysis_rls.py`:

```python
import pandas as pd
from sqlalchemy import select
from app.core.security import create_access_token, hash_password
from app.models.models import AnalysisResult, Dataset, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id, rule_filter_expr):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


async def test_post_analysis_restricted_user_gets_filtered_result_not_cached(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 999}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={}, headers=headers)

    assert resp.status_code == 200
    # The restricted result must not contain any trace of the excluded 999 value.
    assert "999" not in resp.text
    result = await db_session.execute(select(AnalysisResult).where(AnalysisResult.dataset_id == ds.id))
    assert result.scalar_one_or_none() is None  # never written to the shared cache


async def test_get_analysis_restricted_user_never_sees_unrestricted_cache(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 999}],
    )
    # Org admin computes and caches the full, unrestricted analysis first.
    post_resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={}, headers=auth_headers["a"])
    assert post_resp.status_code == 200

    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=headers)

    assert resp.status_code == 404


async def test_get_analysis_unrestricted_user_still_uses_cache(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )
    post_resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={}, headers=auth_headers["a"])
    assert post_resp.status_code == 200

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json() == post_resp.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_data_preview_rls.py tests/test_filter_preview_rls.py tests/test_analysis_rls.py -v`
Expected: FAIL — `test_data_preview_applies_rls_rule` sees both regions (`total == 3`, not 2); `test_filter_preview_total_and_passing_reflect_rls_restricted_set` gets `total == 3`; `test_post_analysis_restricted_user_gets_filtered_result_not_cached` finds `"999"` in the response text and/or a cached `AnalysisResult` row exists; `test_get_analysis_restricted_user_never_sees_unrestricted_cache` gets 200, not 404.

- [ ] **Step 3: Create the shared `resolve_rls_expr` helper**

Create `backend/app/core/rls.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import RowSecurityRule, User


async def resolve_rls_expr(db: AsyncSession, current_user: User, dataset_id: int) -> str | None:
    """Return the calling user's RowSecurityRule.filter_expr for this dataset, or None if
    unrestricted (is_org_admin roles bypass the lookup entirely; a role with no rule for
    this dataset is also None — unrestricted within the org, not "no access")."""
    if current_user.role.is_org_admin:
        return None
    result = await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == current_user.role_id, RowSecurityRule.dataset_id == dataset_id,
        )
    )
    rule = result.scalar_one_or_none()
    return rule.filter_expr if rule else None
```

- [ ] **Step 4: Refactor `widget_data.py`'s router to use the shared helper**

Replace the full contents of `backend/app/routers/widget_data.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.rls import resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import Dataset, User
from ..schemas.schemas import WidgetDataRequest
from ..services.widget_data import get_widget_data

router = APIRouter(prefix="/datasets", tags=["widget-data"])


@router.post("/{dataset_id}/widget-data")
async def query_widget(dataset_id: int, req: WidgetDataRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    rls_filter_expr = await resolve_rls_expr(db, current_user, dataset_id)

    calc_cols = list(req.calculated_columns or []) + list(ds.calculated_columns or [])
    try:
        return get_widget_data(
            ds.filename, req.config, widget_type=req.widget_type,
            calculated_columns=calc_cols or None, filter_expr=ds.default_filter_expr or None,
            rls_filter_expr=rls_filter_expr,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")
```

This is a pure refactor (identical behavior to the already-reviewed Task 6 code, just deduplicated) — the existing Task 6 tests (`backend/tests/test_widget_data_rls_enforcement.py`) must still pass unmodified after this change; that's your regression signal for this step.

- [ ] **Step 5: Apply RLS to `data_preview` and `preview_filter_expr` in `datasets.py`**

In `backend/app/routers/datasets.py`, add this import alongside the existing ones near the top of the file:

```python
from ..core.rls import resolve_rls_expr
```

Replace the `data_preview` function (currently starting at `@router.post("/{dataset_id}/data-preview")`) with:

```python
@router.post("/{dataset_id}/data-preview")
async def data_preview(dataset_id: int, req: DataPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)

    def _run():
        import pandas as pd
        from ..services.analytics import load_file
        from ..services.widget_data import apply_calculated_columns, apply_filter_expr as _afe, _safe

        df = load_file(ds.filename)

        # RLS floor — applied before anything else, exactly like the widget-data path
        if rls_expr:
            df = _afe(df, rls_expr, silent=True)

        # Apply dataset-level global filter first
        if ds.default_filter_expr:
            df = _afe(df, ds.default_filter_expr, silent=True)

        # Apply calculated columns
        if req.calculated_columns:
            calc_defs = [c for c in req.calculated_columns if c.get('name') and c.get('expression')]
            if calc_defs:
                df = apply_calculated_columns(df, calc_defs)

        # Apply filters
        for f in req.filters:
            col = f.get('column')
            op  = f.get('op', 'eq')
            val = f.get('value', '')
            if not col or col not in df.columns:
                continue
            try:
                series = df[col]
                is_num = pd.api.types.is_numeric_dtype(series)
                nv = float(val) if is_num else None
                if op == 'eq':          df = df[series == (nv if is_num else val)]
                elif op == 'ne':        df = df[series != (nv if is_num else val)]
                elif op == 'gt':        df = df[series >  float(val)]
                elif op == 'lt':        df = df[series <  float(val)]
                elif op == 'gte':       df = df[series >= float(val)]
                elif op == 'lte':       df = df[series <= float(val)]
                elif op == 'contains':  df = df[series.astype(str).str.contains(str(val), case=False, na=False)]
                elif op == 'startswith':df = df[series.astype(str).str.startswith(str(val), na=False)]
            except Exception:
                pass

        # Global search across all columns
        if req.search:
            mask = df.astype(str).apply(lambda col: col.str.contains(req.search, case=False, na=False)).any(axis=1)
            df = df[mask]

        total = len(df)

        # Sort
        if req.sort_by and req.sort_by in df.columns:
            df = df.sort_values(req.sort_by, ascending=(req.sort_dir == 'asc'), na_position='last')

        paged  = df.iloc[req.offset: req.offset + req.limit]
        return {'columns': list(paged.columns), 'rows': [[_safe(v) for v in r] for r in paged.values.tolist()], 'total': total}

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")
```

(Only two changes from the original: the new `rls_expr = await resolve_rls_expr(...)` line before `_run` is defined, and the new "RLS floor" block as the first thing `_run` does to the loaded dataframe. Everything else — filters, search, sort, paging — is byte-for-byte unchanged.)

Replace the `preview_filter_expr` function (currently starting at `@router.post("/{dataset_id}/filter-preview")`) with:

```python
@router.post("/{dataset_id}/filter-preview")
async def preview_filter_expr(dataset_id: int, req: FilterPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)

    def _run():
        from ..services.analytics import load_file
        from ..services.widget_data import apply_calculated_columns, apply_filter_expr as _afe

        df = load_file(ds.filename)
        if rls_expr:
            df = _afe(df, rls_expr, silent=True)
        total = len(df)

        if req.calculated_columns:
            calc_defs = [c for c in req.calculated_columns if c.get('name') and c.get('expression')]
            if calc_defs:
                df = apply_calculated_columns(df, calc_defs)

        try:
            filtered = _afe(df, req.expression)
            return {'ok': True, 'passing': len(filtered), 'total': total}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'total': total}

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")
```

`total` is now computed AFTER the RLS filter (so both `total` and `passing` reflect the restricted row set) — this is the fix for the count-oracle finding.

- [ ] **Step 6: Apply RLS to `run_analysis` and `get_analysis` in `analysis.py`**

Replace the full contents of `backend/app/routers/analysis.py`:

```python
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.rls import resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import Dataset, AnalysisResult, User
from ..schemas.schemas import AnalysisRequest
from ..services.analytics import load_file, run_full_analysis
from ..services.widget_data import apply_filter_expr

router = APIRouter(prefix="/datasets", tags=["analysis"])


@router.post("/{dataset_id}/analysis")
async def run_analysis(dataset_id: int, req: AnalysisRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)

    def _load_and_analyze():
        df = load_file(ds.filename)
        if rls_expr:
            df = apply_filter_expr(df, rls_expr, silent=True)
        return run_full_analysis(df)

    result = await asyncio.to_thread(_load_and_analyze)

    if rls_expr:
        # A restricted role's result must never be written to the shared, org-wide
        # AnalysisResult cache (keyed only by dataset_id + analysis_type, with no
        # per-role dimension) — an unrestricted GET would otherwise read back a
        # restricted-shaped result, or a restricted GET could read back an
        # unrestricted admin's cached full result. Restricted callers always get a
        # freshly computed, uncached result instead.
        return result

    existing = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.dataset_id == dataset_id,
            AnalysisResult.analysis_type == req.analysis_type,
        )
    )
    ar = existing.scalar_one_or_none()
    if ar:
        ar.result = result
    else:
        ar = AnalysisResult(dataset_id=dataset_id, analysis_type=req.analysis_type, result=result)
        db.add(ar)

    await db.commit()
    return result


@router.get("/{dataset_id}/analysis")
async def get_analysis(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    if rls_expr:
        # The cached AnalysisResult (if any) was only ever written by an unrestricted
        # caller — see run_analysis — so it may reflect the full, unrestricted dataset.
        # Serving it to a restricted caller would leak excluded rows' values, so
        # restricted callers never read the shared cache; they must POST for a live,
        # RLS-filtered result instead.
        raise HTTPException(404, "No analysis found — run POST first")

    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.dataset_id == dataset_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    ar = result.scalar_one_or_none()
    if not ar:
        raise HTTPException(404, "No analysis found — run POST first")
    return ar.result
```

- [ ] **Step 7: Run the task's tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_data_preview_rls.py tests/test_filter_preview_rls.py tests/test_analysis_rls.py -v`
Expected: all pass (5 tests total: 2 in `test_data_preview_rls.py`, 1 in `test_filter_preview_rls.py`, 3 in `test_analysis_rls.py`).

- [ ] **Step 8: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass, 0 failures — in particular, confirm `tests/test_widget_data_rls_enforcement.py` and `tests/test_get_widget_data_rls.py` (Task 6's tests) still pass unmodified after the `widget_data.py` router refactor in Step 4, and confirm the pre-existing `tests/test_hierarchy_widget_analysis_org_scoping.py` (which exercises `run_analysis`/`get_analysis`'s org-scoping, unrelated to RLS) still passes.

- [ ] **Step 9: Correct the design spec status line**

In `docs/superpowers/specs/2026-08-13-row-level-security-design.md`, line 4 currently reads (from Task 6):

```
**Status:** Phase 2 (Row-Level Security) Complete
```

This is accurate now that this task closes the data-preview/filter-preview/analysis gap — leave it as-is. (If a future task discovers another endpoint that bypasses RLS, that task should revert this line until it's fixed — but as of this task, every dataset-reading endpoint that returns row-level data enforces RLS.)

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/rls.py backend/app/routers/widget_data.py backend/app/routers/datasets.py backend/app/routers/analysis.py \
        backend/tests/test_data_preview_rls.py backend/tests/test_filter_preview_rls.py backend/tests/test_analysis_rls.py
git commit -m "fix: close RLS bypass in data-preview, filter-preview, and analysis endpoints"
```

---

### Task 8: Close the RLS bypass in calculated-column preview

**Why this task exists:** Task 7's final review found one more endpoint sharing the same class of bug it was fixing: `POST /datasets/{id}/calculated-columns/preview` (`preview_calculated_column` in `backend/app/routers/datasets.py`) calls `preview_expression(ds.filename, req.expression)` (in `backend/app/services/widget_data.py`), which loads the dataset's raw file and evaluates the caller-supplied expression against it directly — with zero RLS involvement. A restricted role can submit an expression as simple as a raw column name (e.g. `"region"`) and receive up to 8 sample values straight from the unfiltered dataset, including rows their `RowSecurityRule` excludes. `backend/app/routers/admin.py`'s own `load_file` call (inside `_validate_filter_expr`) is NOT a bypass — it's reached only through `require_org_admin`-gated endpoints, and org admins are exempt from RLS by design — so this task's only target is `preview_calculated_column`.

**Files:**
- Modify: `backend/app/services/widget_data.py` (`preview_expression` gains an optional `rls_filter_expr` parameter)
- Modify: `backend/app/routers/datasets.py` (`preview_calculated_column`)
- Test: `backend/tests/test_calculated_column_preview_rls.py`

**Interfaces:**
- Consumes: `resolve_rls_expr` (`backend/app/core/rls.py`, Task 7).
- Modifies: `preview_expression(file_path: str, expression: str, n: int = 8, rls_filter_expr: str | None = None) -> dict` — when `rls_filter_expr` is truthy, applies `apply_filter_expr(df, rls_filter_expr, silent=True)` to `df` immediately after `load_file`, before `_eval_expr(expression, df)` runs. `None` (the default) preserves the exact current behavior for every other caller of this function (there are none today besides this one router endpoint, but the signature must stay backward-compatible — this is a shared service function, not local to one router).

**Global Constraints for this task (same RLS-floor rule as Tasks 6-7, applied to one more call site):**
- RLS is applied before the calculated-column expression is evaluated — a restricted role must never be able to reference an excluded row's values through `req.expression`, no matter what expression they submit.
- `is_org_admin` roles and roles with no matching rule for this dataset see the exact same (unfiltered-by-RLS) result as before this task — no behavior change for them.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_calculated_column_preview_rls.py`:

```python
import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id, rule_filter_expr):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


async def test_calculated_column_preview_applies_rls_rule(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 999}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/calculated-columns/preview", json={"expression": "region"}, headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "South" not in body["sample"]
    assert body["sample"] == ["North"]


async def test_calculated_column_preview_org_admin_sees_all_rows(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 999}],
    )
    await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/calculated-columns/preview", json={"expression": "region"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    assert set(resp.json()["sample"]) == {"North", "South"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_calculated_column_preview_rls.py -v`
Expected: FAIL — `test_calculated_column_preview_applies_rls_rule` gets `body["sample"] == ["North", "South"]`, so `"South" not in body["sample"]` fails.

- [ ] **Step 3: Add the `rls_filter_expr` parameter to `preview_expression`**

In `backend/app/services/widget_data.py`, replace the `preview_expression` function (currently at line 874):

```python
def preview_expression(file_path: str, expression: str, n: int = 8, rls_filter_expr: str | None = None) -> dict:
    """Evaluate an expression against the dataset and return sample values."""
    try:
        df = load_file(file_path)
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    if rls_filter_expr:
        df = apply_filter_expr(df, rls_filter_expr, silent=True)
    try:
        result = _eval_expr(expression, df)
    except Exception as e:
        return {'ok': False, 'error': str(e)}
    try:
        if hasattr(result, 'head'):          # pandas Series
            sample = result.head(n).tolist()
        elif hasattr(result, '__len__'):     # numpy array or list
            sample = list(result[:n])
        else:
            sample = [result]
        try:
            dtype = 'numeric' if pd.api.types.is_numeric_dtype(result) else 'text'
        except Exception:
            dtype = 'text'
        return {'ok': True, 'dtype': dtype, 'sample': [_safe(v) for v in sample]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
```

(Only two lines added: the new parameter in the signature, and the `if rls_filter_expr:` block right after `load_file` succeeds, before `_eval_expr` runs. `apply_filter_expr` is already defined earlier in this same file, no new import needed.)

- [ ] **Step 4: Wire RLS into the router endpoint**

In `backend/app/routers/datasets.py`, add this import alongside the existing ones near the top of the file (if Task 7 already added it, skip this — check first):

```python
from ..core.rls import resolve_rls_expr
```

Replace `preview_calculated_column` (currently at `@router.post("/{dataset_id}/calculated-columns/preview")`):

```python
@router.post("/{dataset_id}/calculated-columns/preview")
async def preview_calculated_column(dataset_id: int, req: CalcColumnPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    return await asyncio.to_thread(preview_expression, ds.filename, req.expression, 8, rls_expr)
```

- [ ] **Step 5: Run the task's test to verify it passes**

Run: `cd backend && python -m pytest tests/test_calculated_column_preview_rls.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py backend/app/routers/datasets.py backend/tests/test_calculated_column_preview_rls.py
git commit -m "fix: close RLS bypass in calculated-column preview endpoint"
```

---

## Post-Plan State

After Task 8, RLS Phase 2 is functionally complete: `RowSecurityRule` exists, org admins can manage roles/users/rules via `/admin/*`, and non-admin roles are transparently filtered to only the rows their assigned rule permits on every dataset-reading endpoint that returns row-level data, row-derived aggregates, or row-derived sample values (widget-data, data-preview, filter-preview, analysis, calculated-column preview) — with `is_org_admin` roles and roles with no matching rule seeing everything within their org (org isolation from Phase 1 still applies underneath). `AnalysisResult` caching is deliberately disabled for restricted callers (see Task 7's Global Constraints) since the cache has no per-role dimension — a reasonable, documented trade-off rather than a gap. Nothing in the frontend consumes any of this yet — that's Phase 3 (login page, auth-aware API client, admin screens for users/roles/RLS rules), the next item in the rollout per the design spec.
