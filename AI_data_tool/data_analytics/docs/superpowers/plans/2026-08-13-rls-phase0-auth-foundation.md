# Row-Level Security — Phase 0 (Auth Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the authentication foundation from `docs/superpowers/specs/2026-08-13-row-level-security-design.md` — `Organization`/`Role`/`User` models, password hashing, JWT login (`POST /auth/login`, `GET /auth/me`), a `get_current_user` FastAPI dependency, and a bootstrap script to provision the first organization/admin — with **no enforcement wired into any existing router yet**. Org scoping (Phase 1) and row-level filtering (Phase 2) build on top of this in their own plans.

**Architecture:** Three new backend modules (`app/core/security.py` for hashing/JWT, `app/dependencies.py` for `get_current_user`, `app/services/auth_provisioning.py` for org/admin creation) plus one new router (`app/routers/auth.py`), four new SQLAlchemy models, and — since none of the codebase's async endpoints have automated tests today — new async test infrastructure (an in-memory SQLite fixture + an `httpx.AsyncClient` wired to the FastAPI app via `dependency_overrides`, following the same conventions the rest of this codebase already uses for its Pydantic schemas and router structure).

**Tech Stack:** FastAPI + SQLAlchemy (async, existing), `passlib[bcrypt]` (new) for hashing, `python-jose[cryptography]` (new) for JWT, `aiosqlite` + `pytest-asyncio` (new, test-only) for the async DB test fixture.

## Global Constraints

- This phase is purely additive: no existing router, model, or endpoint changes behavior. `Dataset`/`Report`/`DataSource`/`ReportPage`/`ReportWidget`/`HierarchyNode` are untouched — org scoping is Phase 1's job, not this one's.
- Follow existing codebase conventions exactly: Pydantic v2 schemas with `model_config = ConfigDict(from_attributes=True)` (see `backend/app/schemas/schemas.py`), async SQLAlchemy `select()`/`db.get()` patterns and `HTTPException(status_code, "message")` error style (see `backend/app/routers/datasets.py`), `APIRouter(prefix=..., tags=[...])` registered in `backend/app/main.py` with the `/api/v1` prefix.
- **New tables only** this phase (`organizations`, `roles`, `users`) — `Base.metadata.create_all` (already called in `main.py`'s `lifespan`) picks these up automatically on the real Postgres dev DB, exactly like every prior new table in this project (e.g. `DataSource`). No raw `ALTER TABLE` statements needed in `_migrate()` this phase, since nothing existing is being altered.
- Test DB: an in-memory SQLite database created fresh per test via `Base.metadata.create_all`, **not** the real dev Postgres — keeps tests fast, isolated, and safe to run without touching real data. `aiosqlite` + `pytest-asyncio` (`asyncio_mode = auto` in `pytest.ini`, so async test functions need no per-test decorator) are added as new dev/test-only dependencies.
- Passwords are never logged, returned in any response body, or compared with `==` — always through `passlib`'s `verify()`.
- JWT payload carries `sub` (user id, as a string per JWT convention) and `org_id`; signed with `settings.secret_key` (already exists in `backend/app/core/config.py`, currently unused — no new secret to provision) using `HS256`. Access tokens are long-lived (7 days) with no refresh-token flow, per the approved design's explicit v1 exclusion.
- No self-service signup endpoint this phase (or ever, per the design) — the only way to create the first user in an org is the bootstrap script (Task 8), which is a thin CLI wrapper around a reusable, independently-tested service function.

---

## Task 1: Add dependencies and async test DB infrastructure

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/pytest.ini`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_conftest_smoke.py`

**Interfaces:**
- Produces: `db_session` (pytest-asyncio fixture) — an `AsyncSession` bound to a fresh in-memory SQLite database with all of `Base.metadata`'s tables created.
- Produces: `client` (pytest-asyncio fixture) — an `httpx.AsyncClient` wired to the FastAPI `app` via `ASGITransport`, with `get_db` overridden to yield the same `db_session` so a test can both use the HTTP client and directly inspect/seed the DB through the ORM in the same test.
- Consumes (by Tasks 2, 6, 7): both fixtures.

- [ ] **Step 1: Add the new dependencies**

In `backend/requirements.txt`, add:
```
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
aiosqlite==0.20.0
pytest-asyncio==0.23.7
```

Install them:
```bash
pip install passlib[bcrypt]==1.7.4 python-jose[cryptography]==3.3.0 aiosqlite==0.20.0 pytest-asyncio==0.23.7
```

- [ ] **Step 2: Enable auto async test mode**

In `backend/pytest.ini`, change:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```
to:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
asyncio_mode = auto
```
(`asyncio_mode = auto` lets `async def test_...` functions run directly, with no `@pytest.mark.asyncio` needed on each one — matching this project's existing plain `def test_...` style as closely as an async test can.)

- [ ] **Step 3: Create the async test DB fixture**

Create `backend/tests/conftest.py`:
```python
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def db_session():
    """A fresh in-memory SQLite DB per test, with every model's table created.
    StaticPool keeps a single connection alive for the engine's lifetime — SQLite
    in-memory databases are otherwise per-connection and would vanish between
    queries under the default pool."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """An httpx.AsyncClient wired to the FastAPI app, with get_db overridden to
    yield the same db_session — lets a test seed data via the ORM and then hit
    the real HTTP endpoints against that same in-memory database."""
    async def _override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

- [ ] **Step 4: Write a smoke test proving both fixtures work**

Create `backend/tests/test_conftest_smoke.py`:
```python
from sqlalchemy import text


async def test_db_session_fixture_creates_tables_and_queries(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_client_fixture_hits_the_real_app(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 5: Run to verify both fixtures work**

Run (from `backend/`):
```bash
pytest tests/test_conftest_smoke.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing (existing 119 + 2 new), no regressions — the new `asyncio_mode = auto` setting must not affect any of the existing plain synchronous `def test_...` functions.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/pytest.ini backend/tests/conftest.py backend/tests/test_conftest_smoke.py
git commit -m "feat: add async test DB infrastructure (in-memory SQLite + httpx AsyncClient) for RLS Phase 0"
```

---

## Task 2: `Organization`, `Role`, `User` models

**Files:**
- Modify: `backend/app/models/models.py`
- Test: `backend/tests/test_auth_models.py`

**Interfaces:**
- Produces: `Organization(id, name, created_at)`, `Role(id, org_id, name, is_org_admin, created_at)`, `User(id, org_id, role_id, email, password_hash, is_active, created_at)` SQLAlchemy models, each with `relationship()`s wired per the design spec (`Organization.roles`/`.users`, `Role.organization`/`.users`/`.rules`, `User.organization`/`.role`).
- Consumes (by Tasks 5, 6, 7): `User.role.is_org_admin` (via eager `selectinload`, not lazy access, to stay safe under async SQLAlchemy).
- Note: `RowSecurityRule` (referenced by `Role.rules` in the design spec) is **not** created this phase — it's Phase 2's model. Omit the `Role.rules` relationship for now; Phase 2 adds both the model and this relationship together.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_models.py`:
```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.models import Organization, Role, User


async def test_creates_organization_role_and_user_with_relationships(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()

    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()

    user = User(org_id=org.id, role_id=role.id, email="admin@acme.com", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization)).where(User.id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.email == "admin@acme.com"
    assert fetched.is_active is True
    assert fetched.role.is_org_admin is True
    assert fetched.organization.name == "Acme Corp"


async def test_user_email_is_unique(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()

    db_session.add(User(org_id=org.id, role_id=role.id, email="dup@acme.com", password_hash="x"))
    await db_session.commit()

    db_session.add(User(org_id=org.id, role_id=role.id, email="dup@acme.com", password_hash="y"))
    with __import__("pytest").raises(Exception):
        await db_session.commit()


async def test_organization_roles_and_users_relationships(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    db_session.add(User(org_id=org.id, role_id=role.id, email="a@acme.com", password_hash="x"))
    await db_session.commit()

    result = await db_session.execute(
        select(Organization).options(selectinload(Organization.roles), selectinload(Organization.users)).where(Organization.id == org.id)
    )
    fetched = result.scalar_one()
    assert len(fetched.roles) == 1
    assert len(fetched.users) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_auth_models.py -v
```
Expected: FAIL — `ImportError: cannot import name 'Organization'`.

- [ ] **Step 3: Add the models**

In `backend/app/models/models.py`, change the import line:
```python
from sqlalchemy import Column, Integer, String, Text, Float, BigInteger, DateTime, ForeignKey, JSON
```
to:
```python
from sqlalchemy import Column, Integer, String, Text, Float, BigInteger, DateTime, ForeignKey, JSON, Boolean
```

Then add, after the last existing class (`DataSource`):
```python
class Organization(Base):
    __tablename__ = "organizations"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    roles = relationship("Role", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id           = Column(Integer, primary_key=True)
    org_id       = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(255), nullable=False)
    is_org_admin = Column(Boolean, nullable=False, default=False)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="roles")
    users        = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role_id       = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    email         = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
    role         = relationship("Role", back_populates="users")
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_auth_models.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/models.py backend/tests/test_auth_models.py
git commit -m "feat: add Organization, Role, User models for auth foundation"
```

---

## Task 3: Password hashing utilities

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`.
- Consumes (by Task 6): both, for `create_organization_with_admin`.
- Consumes (by Task 7): `verify_password`, for `POST /auth/login`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_security.py`:
```python
from app.core.security import hash_password, verify_password


def test_hash_password_does_not_return_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert len(hashed) > 20


def test_verify_password_accepts_the_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_the_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hashing_the_same_password_twice_produces_different_hashes():
    """bcrypt salts each hash — this guards against someone 'optimizing' by
    caching or reusing a hash, which would defeat the salt's purpose."""
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a) is True
    assert verify_password("same password", b) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_security.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.security'`.

- [ ] **Step 3: Implement the hashing utilities**

Create `backend/app/core/security.py`:
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_security.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat: add password hashing utilities (hash_password/verify_password)"
```

---

## Task 4: JWT utilities

**Files:**
- Modify: `backend/app/core/security.py`
- Modify: `backend/tests/test_security.py`

**Interfaces:**
- Produces: `create_access_token(user_id: int, org_id: int) -> str`, `decode_access_token(token: str) -> dict | None` (returns the decoded payload, or `None` for any invalid/expired/malformed token — never raises, so callers get one simple check).
- Consumes (by Task 5): `decode_access_token`, in `get_current_user`.
- Consumes (by Task 7): `create_access_token`, in `POST /auth/login`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_security.py`:
```python
from datetime import timedelta
from freezegun import freeze_time
from app.core.security import create_access_token, decode_access_token


def test_create_and_decode_access_token_round_trips():
    token = create_access_token(user_id=42, org_id=7)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["org_id"] == 7


def test_decode_access_token_rejects_garbage():
    assert decode_access_token("not.a.valid.jwt") is None


def test_decode_access_token_rejects_a_token_signed_with_a_different_key():
    from jose import jwt as _jwt
    bad_token = _jwt.encode({"sub": "1", "org_id": 1}, "wrong-secret-key", algorithm="HS256")
    assert decode_access_token(bad_token) is None


def test_decode_access_token_rejects_an_expired_token():
    with freeze_time("2026-01-01"):
        token = create_access_token(user_id=1, org_id=1)
    with freeze_time("2026-01-01") as frozen:
        frozen.move_to("2026-01-09")   # ACCESS_TOKEN_EXPIRE_DAYS is 7
        assert decode_access_token(token) is None
```

Add `freezegun` to `backend/requirements.txt` (test-only, for controlling token expiry in tests without real 7-day waits):
```
freezegun==1.5.1
```
Install it:
```bash
pip install freezegun==1.5.1
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_security.py -v
```
Expected: FAIL — `ImportError: cannot import name 'create_access_token'`.

- [ ] **Step 3: Implement the JWT utilities**

In `backend/app/core/security.py`, add imports at the top:
```python
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from .config import settings
```
Then append:
```python
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def create_access_token(user_id: int, org_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "org_id": org_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_security.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py backend/requirements.txt
git commit -m "feat: add JWT create/decode utilities (create_access_token/decode_access_token)"
```

---

## Task 5: `get_current_user` dependency

**Files:**
- Create: `backend/app/dependencies.py`
- Test: `backend/tests/test_dependencies.py`

**Interfaces:**
- Produces: `get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User` — a FastAPI dependency. Decodes the bearer token, re-fetches the `User` row fresh from the DB (with `role`/`organization` eagerly loaded via `selectinload`, never lazy-loaded), and raises `HTTPException(401)` for any invalid token, missing user, or inactive user.
- Produces: `oauth2_scheme` (`OAuth2PasswordBearer`), reused by Task 7's router registration and by Swagger UI's "Authorize" button (`tokenUrl` points at the login endpoint this phase adds).
- Consumes (by Task 7): both, directly.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_dependencies.py`:
```python
import pytest
from fastapi import HTTPException
from app.core.security import create_access_token, hash_password
from app.dependencies import get_current_user
from app.models.models import Organization, Role, User


async def _seed_user(db_session, is_active=True) -> User:
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="a@acme.com",
                password_hash=hash_password("secret"), is_active=is_active)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_valid_token_resolves_to_the_user_with_role_and_org_loaded(db_session):
    user = await _seed_user(db_session)
    token = create_access_token(user.id, user.org_id)

    resolved = await get_current_user(token=token, db=db_session)

    assert resolved.id == user.id
    assert resolved.role.is_org_admin is True
    assert resolved.organization.name == "Acme Corp"


async def test_garbage_token_raises_401(db_session):
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="not-a-real-token", db=db_session)
    assert exc_info.value.status_code == 401


async def test_token_for_a_deleted_user_raises_401(db_session):
    token = create_access_token(user_id=999999, org_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == 401


async def test_token_for_an_inactive_user_raises_401(db_session):
    user = await _seed_user(db_session, is_active=False)
    token = create_access_token(user.id, user.org_id)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_dependencies.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dependencies'`.

- [ ] **Step 3: Implement the dependency**

Create `backend/app/dependencies.py`:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .core.database import get_db
from .core.security import decode_access_token
from .models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    result = await db.execute(
        select(User)
        .options(selectinload(User.role), selectinload(User.organization))
        .where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_error
    return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_dependencies.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/dependencies.py backend/tests/test_dependencies.py
git commit -m "feat: add get_current_user FastAPI dependency"
```

---

## Task 6: `create_organization_with_admin` provisioning service

**Files:**
- Create: `backend/app/services/auth_provisioning.py`
- Test: `backend/tests/test_auth_provisioning.py`

**Interfaces:**
- Produces: `async def create_organization_with_admin(db: AsyncSession, org_name: str, admin_email: str, admin_password: str) -> tuple[Organization, Role, User]` — creates an `Organization`, an implicit `is_org_admin=True` `Role` named `"Admin"`, and the first `User` in that org/role, with the password hashed. **Does not commit** — the caller controls the transaction (so both the bootstrap script and a future admin-API endpoint can reuse it inside their own transaction boundaries).
- Consumes (by Task 8): directly, from the CLI bootstrap script.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_provisioning.py`:
```python
from sqlalchemy import select
from app.core.security import verify_password
from app.models.models import Organization, Role, User
from app.services.auth_provisioning import create_organization_with_admin


async def test_creates_org_admin_role_and_user(db_session):
    org, role, user = await create_organization_with_admin(
        db_session, "Acme Corp", "admin@acme.com", "supersecret"
    )
    await db_session.commit()

    assert org.name == "Acme Corp"
    assert role.name == "Admin"
    assert role.is_org_admin is True
    assert role.org_id == org.id
    assert user.email == "admin@acme.com"
    assert user.org_id == org.id
    assert user.role_id == role.id


async def test_password_is_hashed_not_stored_in_plaintext(db_session):
    _, _, user = await create_organization_with_admin(
        db_session, "Acme Corp", "admin@acme.com", "supersecret"
    )
    await db_session.commit()

    assert user.password_hash != "supersecret"
    assert verify_password("supersecret", user.password_hash) is True


async def test_created_rows_are_queryable_after_commit(db_session):
    await create_organization_with_admin(db_session, "Acme Corp", "admin@acme.com", "supersecret")
    await db_session.commit()

    org_result = await db_session.execute(select(Organization).where(Organization.name == "Acme Corp"))
    assert org_result.scalar_one() is not None
    role_result = await db_session.execute(select(Role).where(Role.name == "Admin"))
    assert role_result.scalar_one().is_org_admin is True
    user_result = await db_session.execute(select(User).where(User.email == "admin@acme.com"))
    assert user_result.scalar_one() is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_auth_provisioning.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.auth_provisioning'`.

- [ ] **Step 3: Implement the provisioning service**

Create `backend/app/services/auth_provisioning.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password
from ..models.models import Organization, Role, User


async def create_organization_with_admin(
    db: AsyncSession, org_name: str, admin_email: str, admin_password: str,
) -> tuple[Organization, Role, User]:
    """Create a new Organization, its implicit Admin role (is_org_admin=True), and the
    first User in that org/role. Does not commit — caller controls the transaction."""
    org = Organization(name=org_name)
    db.add(org)
    await db.flush()

    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db.add(role)
    await db.flush()

    user = User(
        org_id=org.id,
        role_id=role.id,
        email=admin_email,
        password_hash=hash_password(admin_password),
    )
    db.add(user)
    await db.flush()

    return org, role, user
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_auth_provisioning.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/auth_provisioning.py backend/tests/test_auth_provisioning.py
git commit -m "feat: add create_organization_with_admin provisioning service"
```

---

## Task 7: `POST /auth/login` and `GET /auth/me`

**Files:**
- Modify: `backend/app/schemas/schemas.py`
- Create: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_router.py`

**Interfaces:**
- Produces: `POST /api/v1/auth/login` — body `{email, password}`, returns `{access_token, token_type: "bearer"}` on success, `401` with a generic "Invalid email or password" message on any failure (wrong password, unknown email, or inactive user — all identical, so a caller can't distinguish which).
- Produces: `GET /api/v1/auth/me` — requires a valid bearer token (via `get_current_user`), returns the current user's `id`/`email`/`is_active`/`organization`/`role`.
- Produces Pydantic schemas: `OrganizationOut`, `RoleOut`, `UserOut`, `LoginRequest`, `TokenOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_router.py`:
```python
from app.services.auth_provisioning import create_organization_with_admin


async def _seed_admin(db_session, email="admin@acme.com", password="supersecret"):
    org, role, user = await create_organization_with_admin(db_session, "Acme Corp", email, password)
    await db_session.commit()
    return org, role, user


async def test_login_with_correct_credentials_returns_a_token(client, db_session):
    await _seed_admin(db_session)

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


async def test_login_with_wrong_password_returns_401(client, db_session):
    await _seed_admin(db_session)

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "wrong"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


async def test_login_with_unknown_email_returns_the_same_generic_401(client, db_session):
    resp = await client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.com", "password": "x"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


async def test_login_with_inactive_user_returns_the_same_generic_401(client, db_session):
    org, role, user = await _seed_admin(db_session)
    user.is_active = False
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


async def test_me_with_valid_token_returns_the_current_user(client, db_session):
    await _seed_admin(db_session)
    login_resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@acme.com"
    assert body["organization"]["name"] == "Acme Corp"
    assert body["role"]["is_org_admin"] is True


async def test_me_without_a_token_returns_401(client, db_session):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_an_invalid_token_returns_401(client, db_session):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_auth_router.py -v
```
Expected: FAIL — 404s from `/api/v1/auth/login` and `/api/v1/auth/me` not existing yet.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/schemas.py`, append:
```python
class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_org_admin: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    is_active: bool
    organization: OrganizationOut
    role: RoleOut


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 4: Implement the router**

Create `backend/app/routers/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.security import create_access_token, verify_password
from ..dependencies import get_current_user
from ..models.models import User
from ..schemas.schemas import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(user.id, user.org_id)
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, change:
```python
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources
```
to:
```python
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources, auth
```
and add, alongside the other `app.include_router(...)` calls:
```python
app.include_router(auth.router, prefix="/api/v1")
```

- [ ] **Step 6: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_auth_router.py -v
```
Expected: 8 passed.

Note: `test_me_with_valid_token_returns_the_current_user` exercises `UserOut`'s nested `organization`/`role` serialization from a `User` object whose `role`/`organization` are loaded via `get_current_user`'s `selectinload` — if this fails with a `MissingGreenlet`/lazy-load error instead of a clean assertion failure, it means some code path is accessing `.role`/`.organization` without eager loading; re-check `get_current_user`'s query.

- [ ] **Step 7: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/schemas.py backend/app/routers/auth.py backend/app/main.py backend/tests/test_auth_router.py
git commit -m "feat: add POST /auth/login and GET /auth/me endpoints"
```

---

## Task 8: Bootstrap CLI script

**Files:**
- Create: `backend/scripts/create_org_admin.py`

**Interfaces:**
- Produces: a CLI entry point, `python scripts/create_org_admin.py <org_name> <admin_email> <admin_password>`, that provisions the first organization and admin user against the **real** configured database (`settings.database_url`) — not the test DB. Thin wrapper around Task 6's already-tested `create_organization_with_admin`; no new business logic, so no new automated test — verified by actually running it (Step 3 below).

- [ ] **Step 1: Create the script**

Create `backend/scripts/create_org_admin.py`:
```python
"""Bootstrap script: create the first Organization and its admin User.

There is no self-service signup in this app (by design — see
docs/superpowers/specs/2026-08-13-row-level-security-design.md) — this script
is the only way to create an organization's first user.

Usage:
    python scripts/create_org_admin.py "Acme Corp" admin@acme.com supersecret
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.auth_provisioning import create_organization_with_admin  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_org_admin.py <org_name> <admin_email> <admin_password>")
        sys.exit(1)
    org_name, email, password = sys.argv[1], sys.argv[2], sys.argv[3]

    async with AsyncSessionLocal() as db:
        org, role, user = await create_organization_with_admin(db, org_name, email, password)
        await db.commit()

    print(f"Created organization '{org.name}' (id={org.id}) with admin user '{user.email}' (id={user.id}, role='{role.name}')")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify the module imports cleanly**

Run (from `backend/`):
```bash
python -c "import ast; ast.parse(open('scripts/create_org_admin.py').read())"
```
Expected: no output (syntax is valid) — this does not touch the real database, it only confirms the file parses.

- [ ] **Step 3: Run it against the real running dev stack**

This project's docker-compose stack (`datalytics_backend`, `datalytics_db`) is expected to already be running for this verification step. From the repo root:
```bash
docker compose exec backend python scripts/create_org_admin.py "Test Organization" test-admin@example.com test-password-123
```
Expected output: `Created organization 'Test Organization' (id=1) with admin user 'test-admin@example.com' (id=1, role='Admin')` (ids may differ if run more than once — re-running with the same email will fail on the `User.email` unique constraint, which is correct behavior, not a bug to fix).

If the backend container's image doesn't yet have Task 1's new dependencies installed (the Dockerfile installs `requirements.txt` at build time, and the running container was built before this task's `requirements.txt` changes), rebuild first: `docker compose up -d --build backend`.

Confirm the row exists by querying the real dev database directly:
```bash
docker compose exec postgres psql -U datalytics -d datalytics -c "SELECT id, name FROM organizations; SELECT id, email, org_id, role_id FROM users;"
```

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/create_org_admin.py
git commit -m "feat: add create_org_admin bootstrap CLI script"
```

---

## Task 9: Full regression pass and Phase 0 close-out

**Files:** none (verification only), plus the design spec status line.

- [ ] **Step 1: Run the full automated test suite**

Run (from `backend/`):
```bash
pytest -v
```
Expected: all tests pass — the pre-existing 119, plus this phase's new ones (2 conftest smoke + 3 model + 4 hashing + 4 JWT + 4 dependency + 3 provisioning + 8 router = 28 new, ~147 total; exact count isn't the point, zero failures is).

- [ ] **Step 2: Full manual regression read**

Read through `backend/app/main.py` and confirm: the `auth` router is registered alongside the existing five; `_migrate()` is unchanged (Phase 0 introduces no altered columns on any existing table); `Base.metadata.create_all` will pick up `organizations`/`roles`/`users` automatically the next time the real app starts against the real Postgres DB (already effectively verified by Task 8's live run against the running dev stack, which required exactly this).

Confirm no existing router (`datasets.py`, `reports.py`, `hierarchy.py`, `widget_data.py`, `data_sources.py`, `analysis.py`) was touched — org scoping is explicitly Phase 1's job.

- [ ] **Step 3: Update the design spec status**

In `docs/superpowers/specs/2026-08-13-row-level-security-design.md`, change the `**Status:**` line from `Design approved, not yet implemented` to `Phase 0 (Auth Foundation) Complete`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-13-row-level-security-design.md
git commit -m "docs: mark Row-Level Security Phase 0 (Auth Foundation) complete"
```

**Phase 0 is now done — Organization/Role/User models exist, password hashing and JWT login work end-to-end, `get_current_user` is a ready-to-use FastAPI dependency, and a bootstrap script can provision the first organization.** Nothing is enforced yet: every existing endpoint remains fully open, by design — Phase 1 (org scoping across `Dataset`/`Report`/`DataSource` and every existing router) gets its own plan document, written fresh against this foundation, before enforcement begins.
