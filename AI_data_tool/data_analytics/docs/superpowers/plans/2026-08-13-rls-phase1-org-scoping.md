# Row-Level Security — Phase 1 (Org Scoping) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this app safe for multiple separate organizations, before row-level security proper exists. Add an `org_id` column to `Dataset`/`Report`/`DataSource` (with a backfill so existing data isn't orphaned), and enforce it — `current_user: User = Depends(get_current_user)` plus an org-ownership check — on every endpoint in every existing router (`datasets`, `reports`, `hierarchy`, `data_sources`, `widget_data`, `analysis`). This is Phase 1 of `docs/superpowers/specs/2026-08-13-row-level-security-design.md`; Phase 0 (auth foundation — `Organization`/`Role`/`User`, JWT login, `get_current_user`) is already merged. Phase 2 (the actual per-role row-filtering rules) and Phase 3 (frontend) each get their own plan after this one.

**Architecture:** One shared utility, `check_org(obj, current_user, message)` in a new `backend/app/core/org_scope.py`, used identically across all six routers: 404 (never 403 — a 403 would confirm the object exists) when the loaded row's `org_id` doesn't match `current_user.org_id`. List endpoints add a `WHERE org_id = current_user.org_id` filter. Create endpoints set `org_id=current_user.org_id` server-side, ignoring any client input (none of the existing request schemas even have an `org_id` field, so there's no client override to strip — just nothing to trust from the request). Nested resources with no `org_id` of their own (`ReportPage`/`ReportWidget`/`HierarchyNode`/`DatasetColumn`) are protected by checking their org-scoped parent (`Report`/`Dataset`) before ever touching the child — exactly as the design spec specifies. A `_backfill_default_org` function (new, in `main.py`, following the existing `_migrate()` convention already used for prior schema changes) creates a "Default Organization" + "Admin" role on first startup and assigns every pre-existing `org_id`-less row to it, so nothing already in the database becomes inaccessible.

**Tech Stack:** FastAPI + async SQLAlchemy (existing), reusing Phase 0's `get_current_user` dependency and test infrastructure (`db_session`/`client` fixtures, `create_organization_with_admin`).

## Global Constraints

- Purely additive to behavior for a single-org deployment: a user in the (automatically created) Default Organization sees exactly what they saw before this phase — nothing disappears, no new required fields appear in any request body. The only observable behavior change is that a SECOND organization's data becomes invisible to the first, which is the entire point of this phase.
- Every check is **404, not 403**, per the design spec ("a user can't distinguish 'doesn't exist' from 'exists but isn't yours'").
- Every router file gains `current_user: User = Depends(get_current_user)` on every endpoint — no endpoint is left unauthenticated in this phase (Phase 0 built `get_current_user` precisely so this phase could do this).
- Follow the exact code style already established: same `HTTPException(status_code, "message")` calls, same async SQLAlchemy `select()`/`db.get()` patterns, same import ordering conventions per file.
- No raw SQL migration framework introduced (matches Phase 0's precedent) — new columns go through `_migrate()`'s existing `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern in `backend/app/main.py`, and the backfill uses the ORM (testable directly against the `db_session` fixture, unlike raw-SQL `_migrate()` statements which only run at real app startup).
- `org_id` is nullable at the SQL level on `Dataset`/`Report`/`DataSource` (adding `NOT NULL` retroactively to tables with existing rows needs a two-step backfill-then-constrain migration this project's simple `_migrate()` runner doesn't express — see the design spec's Migrations section) — enforced as effectively-always-set at the application layer instead (every create endpoint sets it; `check_org` treats a `None` `org_id` as "doesn't match," so a null row 404s exactly like a foreign-org row would).
- Test isolation and fixtures: reuse Phase 0's `db_session`/`client` fixtures from `backend/tests/conftest.py`. This phase adds two new shared fixtures (`two_orgs`, `auth_headers`) to the SAME `conftest.py` in Task 1, since every subsequent task's tests need "two separate organizations, each with a logged-in admin" as their starting point.
- File-upload tests (`datasets.py`'s `POST /datasets`) must not write to the real `settings.upload_dir` default (`/app/uploads`, a container-only path) when run on this host — monkeypatch `settings.upload_dir` to pytest's `tmp_path` fixture for any test that exercises that endpoint.

---

## Task 1: `org_id` columns, backfill, and shared org-isolation test fixtures

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_migrate_backfill.py`

**Interfaces:**
- Produces: `Dataset.org_id`, `Report.org_id`, `DataSource.org_id` — nullable `Integer` FK columns to `organizations.id`, `ondelete="CASCADE"`.
- Produces: `_backfill_default_org(session: AsyncSession) -> None` in `backend/app/main.py` — idempotent; creates a "Default Organization" + `is_org_admin=True` "Admin" `Role` on first run (guarded by "no `Organization` row exists yet"), then backfills every `org_id IS NULL` row in `Dataset`/`Report`/`DataSource` into it.
- Produces (test fixtures, in `conftest.py`): `two_orgs` — a dict `{"a": {"org", "role", "user"}, "b": {...}}` of two separate, fully-provisioned organizations. `auth_headers` — `{"a": {"Authorization": "Bearer ..."}, "b": {...}}`, ready to pass as `headers=` to any `client` request.
- Consumes (by Tasks 2-5): both new fixtures, in every subsequent task's org-isolation tests.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_migrate_backfill.py`:
```python
from sqlalchemy import select
from app.main import _backfill_default_org
from app.models.models import Organization, Dataset, Report, DataSource
from app.services.auth_provisioning import create_organization_with_admin


async def test_org_id_columns_exist_on_dataset_report_data_source(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    ds = Dataset(name="d1", org_id=org.id)
    rp = Report(name="r1", org_id=org.id)
    src = DataSource(name="s1", type="postgres", org_id=org.id)
    db_session.add_all([ds, rp, src])
    await db_session.commit()

    assert ds.org_id == org.id
    assert rp.org_id == org.id
    assert src.org_id == org.id


async def test_backfill_creates_default_org_and_admin_role_when_none_exists(db_session):
    result = await db_session.execute(select(Organization))
    assert result.scalars().all() == []

    await _backfill_default_org(db_session)

    result = await db_session.execute(select(Organization))
    orgs = result.scalars().all()
    assert len(orgs) == 1
    assert orgs[0].name == "Default Organization"


async def test_backfill_assigns_org_id_less_rows_to_the_default_org(db_session):
    ds = Dataset(name="orphan-dataset")  # org_id defaults to None
    rp = Report(name="orphan-report")
    src = DataSource(name="orphan-source", type="postgres")
    db_session.add_all([ds, rp, src])
    await db_session.commit()
    assert ds.org_id is None and rp.org_id is None and src.org_id is None

    await _backfill_default_org(db_session)

    result = await db_session.execute(select(Organization))
    default_org = result.scalar_one()
    await db_session.refresh(ds)
    await db_session.refresh(rp)
    await db_session.refresh(src)
    assert ds.org_id == default_org.id
    assert rp.org_id == default_org.id
    assert src.org_id == default_org.id


async def test_backfill_does_not_touch_rows_that_already_have_an_org_id(db_session):
    org_a, _, _ = await create_organization_with_admin(db_session, "Org A", "a@example.com", "password-a")
    await db_session.commit()
    ds = Dataset(name="already-scoped", org_id=org_a.id)
    db_session.add(ds)
    await db_session.commit()

    await _backfill_default_org(db_session)

    await db_session.refresh(ds)
    assert ds.org_id == org_a.id  # unchanged — not reassigned to the new default org


async def test_backfill_is_idempotent(db_session):
    await _backfill_default_org(db_session)
    await _backfill_default_org(db_session)

    result = await db_session.execute(select(Organization).where(Organization.name == "Default Organization"))
    assert len(result.scalars().all()) == 1  # still only one, not duplicated
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_migrate_backfill.py -v
```
Expected: FAIL — `AttributeError`/`TypeError` on `Dataset(org_id=...)` (column doesn't exist yet) and `ImportError: cannot import name '_backfill_default_org'`.

- [ ] **Step 3: Add `org_id` to the three models**

In `backend/app/models/models.py`, add to `Dataset` (after `source_query`):
```python
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
```
Add to `Report` (after `additional_dataset_ids`):
```python
    org_id                 = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
```
Add to `DataSource` (after `config`):
```python
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
```

- [ ] **Step 4: Add `_migrate()` statements and `_backfill_default_org`**

In `backend/app/main.py`, change the imports (Phase 0 already added `auth` to the router import — this step only adds the `select`/`update`/`AsyncSession`/`AsyncSessionLocal` and model imports, it does not touch the router list):
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .core.config import settings
from .core.database import engine, Base
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources, auth
```
to:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from .core.config import settings
from .core.database import engine, Base, AsyncSessionLocal
from .models.models import Dataset, Report, DataSource, Organization, Role
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources, auth
```
If the current file's import block doesn't match the "before" text exactly (e.g. a later hotfix changed it), apply the same diff in spirit: add `select`, `update` to the `sqlalchemy` import; add a new `from sqlalchemy.ext.asyncio import AsyncSession` line; add `AsyncSessionLocal` to the `core.database` import; add the new `from .models.models import Dataset, Report, DataSource, Organization, Role` line — and leave the router import list exactly as it already is.

Change the `_migrate` function's `stmts` list — add three new lines at the end, right before the closing `]`:
```python
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
```

Then add, after `_migrate`:
```python
async def _backfill_default_org(session: AsyncSession) -> None:
    """Ensure a default organization + admin role exist, and backfill any org_id-less
    rows in Dataset/Report/DataSource into it. Idempotent — guarded by checking
    whether any Organization row exists yet, so this is a no-op on every startup
    after the first."""
    result = await session.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    if org is None:
        org = Organization(name="Default Organization")
        session.add(org)
        await session.flush()
        session.add(Role(org_id=org.id, name="Admin", is_org_admin=True))
        await session.flush()
    await session.execute(update(Dataset).where(Dataset.org_id.is_(None)).values(org_id=org.id))
    await session.execute(update(Report).where(Report.org_id.is_(None)).values(org_id=org.id))
    await session.execute(update(DataSource).where(DataSource.org_id.is_(None)).values(org_id=org.id))
    await session.commit()
```

Change the `lifespan` function:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)
    yield
```
to:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)
    async with AsyncSessionLocal() as session:
        await _backfill_default_org(session)
    yield
```

- [ ] **Step 5: Add the shared `two_orgs`/`auth_headers` test fixtures**

In `backend/tests/conftest.py`, add (after the existing `client` fixture):
```python
@pytest_asyncio.fixture
async def two_orgs(db_session):
    """Two separate, fully-provisioned organizations for org-isolation tests."""
    from app.services.auth_provisioning import create_organization_with_admin

    org_a, role_a, user_a = await create_organization_with_admin(db_session, "Org A", "admin-a@example.com", "password-a")
    org_b, role_b, user_b = await create_organization_with_admin(db_session, "Org B", "admin-b@example.com", "password-b")
    await db_session.commit()
    return {
        "a": {"org": org_a, "role": role_a, "user": user_a},
        "b": {"org": org_b, "role": role_b, "user": user_b},
    }


@pytest_asyncio.fixture
async def auth_headers(two_orgs):
    """Bearer-token Authorization headers for org A's and org B's admin users."""
    from app.core.security import create_access_token

    return {
        "a": {"Authorization": f"Bearer {create_access_token(two_orgs['a']['user'].id, two_orgs['a']['user'].org_id)}"},
        "b": {"Authorization": f"Bearer {create_access_token(two_orgs['b']['user'].id, two_orgs['b']['user'].org_id)}"},
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_migrate_backfill.py -v
```
Expected: 5 passed.

- [ ] **Step 7: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing (149 pre-existing + 5 new), no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/models.py backend/app/main.py backend/tests/conftest.py backend/tests/test_migrate_backfill.py
git commit -m "feat: add org_id to Dataset/Report/DataSource with default-org backfill"
```

---

## Task 2: `check_org` helper + org-scope `datasets.py`

**Files:**
- Create: `backend/app/core/org_scope.py`
- Modify: `backend/app/routers/datasets.py`
- Test: `backend/tests/test_org_scope.py`
- Test: `backend/tests/test_datasets_org_scoping.py`

**Interfaces:**
- Produces: `check_org(obj, current_user: User, message: str = "Not found") -> None` — raises `HTTPException(404, message)` if `obj` is `None` or `obj.org_id != current_user.org_id`; returns silently otherwise.
- Consumes (by Tasks 3-5): `check_org`, in every remaining router.

- [ ] **Step 1: Write the failing tests for `check_org`**

Create `backend/tests/test_org_scope.py`:
```python
import pytest
from fastapi import HTTPException
from app.core.org_scope import check_org


class _FakeObj:
    def __init__(self, org_id):
        self.org_id = org_id


class _FakeUser:
    def __init__(self, org_id):
        self.org_id = org_id


def test_raises_404_when_obj_is_none():
    with pytest.raises(HTTPException) as exc_info:
        check_org(None, _FakeUser(1), "Thing not found")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Thing not found"


def test_raises_404_when_org_ids_do_not_match():
    with pytest.raises(HTTPException) as exc_info:
        check_org(_FakeObj(org_id=2), _FakeUser(org_id=1), "Thing not found")
    assert exc_info.value.status_code == 404


def test_does_not_raise_when_org_ids_match():
    check_org(_FakeObj(org_id=1), _FakeUser(org_id=1), "Thing not found")  # no exception


def test_default_message_is_not_found():
    with pytest.raises(HTTPException) as exc_info:
        check_org(None, _FakeUser(1))
    assert exc_info.value.detail == "Not found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_org_scope.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.org_scope'`.

- [ ] **Step 3: Implement `check_org`**

Create `backend/app/core/org_scope.py`:
```python
from fastapi import HTTPException


def check_org(obj, current_user, message: str = "Not found") -> None:
    """Raise 404 if obj is missing or doesn't belong to current_user's org.

    Always 404, never 403 — a 403 would reveal that the object exists but isn't
    the caller's, which is itself information leakage. 404 keeps "doesn't exist"
    and "exists but isn't yours" indistinguishable, per the design spec.
    """
    if obj is None or obj.org_id != current_user.org_id:
        raise HTTPException(404, message)
```

- [ ] **Step 4: Run `check_org` tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_org_scope.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Write the failing org-scoping tests for `datasets.py`**

Create `backend/tests/test_datasets_org_scoping.py`:
```python
from sqlalchemy import select
from app.models.models import Dataset


async def _seed_dataset(db_session, org_id, name="Test Dataset"):
    ds = Dataset(name=name, org_id=org_id, filename=None)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_list_datasets_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    await _seed_dataset(db_session, two_orgs["a"]["org"].id, "A's dataset")
    await _seed_dataset(db_session, two_orgs["b"]["org"].id, "B's dataset")

    resp = await client.get("/api/v1/datasets", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert names == ["A's dataset"]


async def test_get_dataset_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_dataset_same_org_succeeds(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json()["id"] == ds.id


async def test_upload_dataset_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    resp = await client.post(
        "/api/v1/datasets",
        files={"file": ("test.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
        data={"name": "Uploaded Dataset", "description": ""},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    dataset_id = resp.json()["id"]
    result = await db_session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ds = result.scalar_one()
    assert ds.org_id == two_orgs["a"]["org"].id


async def test_delete_dataset_cross_org_returns_404_and_does_not_delete(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.delete(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
    result = await db_session.execute(select(Dataset).where(Dataset.id == ds.id))
    assert result.scalar_one_or_none() is not None  # still exists


async def test_sub_resource_endpoints_are_org_scoped(client, db_session, two_orgs, auth_headers):
    """Parametrized-in-spirit check that the identical check_org pattern was actually
    applied to the calculated-columns/column-formats/filter sub-resource endpoints,
    not just copy-pasted incorrectly onto some of them."""
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    save_resp = await client.put(
        f"/api/v1/datasets/{ds.id}/calculated-columns",
        json={"name": "calc1", "expression": "1+1"},
        headers=auth_headers["a"],
    )
    assert save_resp.status_code == 404

    formats_resp = await client.get(f"/api/v1/datasets/{ds.id}/column-formats", headers=auth_headers["a"])
    assert formats_resp.status_code == 404

    filter_resp = await client.patch(
        f"/api/v1/datasets/{ds.id}/filter", json={"expression": "a > 1"}, headers=auth_headers["a"],
    )
    assert filter_resp.status_code == 404


async def test_list_datasets_requires_authentication(client, db_session):
    resp = await client.get("/api/v1/datasets")
    assert resp.status_code == 401
```

- [ ] **Step 6: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_datasets_org_scoping.py -v
```
Expected: FAIL — `datasets.py` doesn't require auth yet, so requests succeed (200) where tests expect 401/404, and `list_datasets` returns both orgs' datasets.

- [ ] **Step 7: Org-scope `datasets.py`**

Replace the full contents of `backend/app/routers/datasets.py` with:
```python
import asyncio
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.config import settings
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, DatasetColumn, DataSource, User
from sqlalchemy.orm.attributes import flag_modified
from ..schemas.schemas import DatasetOut, CalcColumnDef, CalcColumnPreviewRequest, ColumnFormatRequest, DataPreviewRequest, FilterExprUpdate, FilterPreviewRequest
from ..services.analytics import load_file, detect_types
from ..services.widget_data import preview_expression, apply_filter_expr

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetOut])
async def list_datasets(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns))
        .where(Dataset.org_id == current_user.org_id)
        .order_by(Dataset.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    return ds


@router.post("", response_model=DatasetOut)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / (file.filename or "upload")

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = file_path.stat().st_size
    if file_size > settings.max_upload_mb * 1024 * 1024:
        file_path.unlink(missing_ok=True)
        raise HTTPException(400, f"File exceeds {settings.max_upload_mb} MB limit")

    df       = await asyncio.to_thread(load_file, str(file_path))
    type_map = await asyncio.to_thread(detect_types, df)

    ds = Dataset(
        name=name, description=description or None, filename=str(file_path),
        row_count=len(df), col_count=len(df.columns), file_size=file_size,
        org_id=current_user.org_id,
    )
    db.add(ds)
    await db.flush()

    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=ds.id, name=col_name, dtype=dtype,
            missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={},
        ))

    await db.commit()
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == ds.id)
    )
    return result.scalar_one()


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if ds.filename:
        Path(ds.filename).unlink(missing_ok=True)
    await db.delete(ds)
    await db.commit()


# ── Calculated Columns ────────────────────────────────────────────────────────

@router.get("/{dataset_id}/calculated-columns")
async def list_calculated_columns(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.calculated_columns or []


@router.put("/{dataset_id}/calculated-columns")
async def save_calculated_column(dataset_id: int, col: CalcColumnDef, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    cols = [c for c in (ds.calculated_columns or []) if c.get('name') != col.name]
    cols.append(col.model_dump())
    ds.calculated_columns = cols
    flag_modified(ds, 'calculated_columns')
    await db.commit()
    return cols


@router.delete("/{dataset_id}/calculated-columns/{col_name}")
async def delete_calculated_column(dataset_id: int, col_name: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    cols = [c for c in (ds.calculated_columns or []) if c.get('name') != col_name]
    ds.calculated_columns = cols
    flag_modified(ds, 'calculated_columns')
    await db.commit()
    return cols


@router.post("/{dataset_id}/calculated-columns/preview")
async def preview_calculated_column(dataset_id: int, req: CalcColumnPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    return await asyncio.to_thread(preview_expression, ds.filename, req.expression)


# ── Column Formats ────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/column-formats")
async def get_column_formats(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.column_formats or {}


@router.put("/{dataset_id}/column-formats")
async def set_column_format(dataset_id: int, req: ColumnFormatRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    fmts = dict(ds.column_formats or {})
    if req.format is None:
        fmts.pop(req.column, None)
    else:
        fmts[req.column] = req.format.model_dump(exclude_none=True)
    ds.column_formats = fmts
    flag_modified(ds, 'column_formats')
    await db.commit()
    return fmts


@router.post("/{dataset_id}/data-preview")
async def data_preview(dataset_id: int, req: DataPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    def _run():
        import pandas as pd
        from ..services.analytics import load_file
        from ..services.widget_data import apply_calculated_columns, apply_filter_expr as _afe, _safe

        df = load_file(ds.filename)

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


@router.patch("/{dataset_id}/filter", response_model=DatasetOut)
async def update_filter_expr(dataset_id: int, body: FilterExprUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    ds.default_filter_expr = body.expression or None
    await db.commit()
    result = await db.execute(select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id))
    return result.scalar_one()


@router.post("/{dataset_id}/filter-preview")
async def preview_filter_expr(dataset_id: int, req: FilterPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    def _run():
        from ..services.analytics import load_file
        from ..services.widget_data import apply_calculated_columns, apply_filter_expr as _afe

        df = load_file(ds.filename)
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


@router.post("/{dataset_id}/refresh", response_model=DatasetOut)
async def refresh_dataset(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Re-fetch data from the original database connection and overwrite the cached CSV."""
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    check_org(dataset, current_user, "Dataset not found")
    if not dataset.data_source_id:
        raise HTTPException(400, "This dataset was not imported from a database connection")
    if not dataset.source_table and not dataset.source_query:
        raise HTTPException(400, "Source query not recorded — re-import from the Connections page")

    src = await db.get(DataSource, dataset.data_source_id)
    check_org(src, current_user, "Original data source no longer exists")

    cfg = dict(src.config)
    cfg['type'] = src.type

    def _run():
        from ..services.connections import import_to_dataframe
        df = import_to_dataframe(cfg, dataset.source_table, dataset.source_query)
        file_path = Path(dataset.filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(file_path, index=False)
        from ..services.analytics import detect_types
        type_map = detect_types(df)
        return df, type_map

    try:
        df, type_map = await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(400, f"Refresh failed: {e}")

    dataset.row_count = len(df)
    dataset.col_count = len(df.columns)
    dataset.file_size = Path(dataset.filename).stat().st_size

    for col in list(dataset.columns):
        await db.delete(col)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=dataset.id, name=col_name, dtype=dtype,
            missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={},
        ))

    await db.commit()
    result2 = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    return result2.scalar_one()
```
(Every change from the original file is: the two new imports (`check_org`, `get_current_user`, `User`), `current_user: User = Depends(get_current_user)` added to every endpoint signature, `.where(Dataset.org_id == current_user.org_id)` added to `list_datasets`'s query, `check_org(...)` calls replacing every bare `if not ds: raise HTTPException(404, ...)`, `org_id=current_user.org_id` added to the `Dataset(...)` construction in `upload_dataset`, and the new `check_org(src, current_user, ...)` call in `refresh_dataset` for the `DataSource` it loads. No other logic changed.)

- [ ] **Step 8: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_datasets_org_scoping.py -v
```
Expected: 8 passed.

- [ ] **Step 9: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions. Pay attention to whether any OTHER existing test (from Phase 0 or the pre-existing shaper tests) happens to call a `datasets.py` endpoint without auth — if so, it will now fail with 401, and that test needs `headers=` added (grep the full suite for calls to `/api/v1/datasets` before assuming none exist).

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/org_scope.py backend/app/routers/datasets.py backend/tests/test_org_scope.py backend/tests/test_datasets_org_scoping.py
git commit -m "feat: add check_org helper and org-scope datasets.py"
```

---

## Task 3: Org-scope `reports.py` (including nested pages/widgets)

**Files:**
- Modify: `backend/app/routers/reports.py`
- Test: `backend/tests/test_reports_org_scoping.py`

**Interfaces:**
- Modifies: `_get_report`/`_get_page` helpers gain a `current_user` parameter and call `check_org`.
- Consumes: `check_org` (Task 2), `get_current_user` (Phase 0).

**Nested-resource design note:** `ReportPage` and `ReportWidget` have no `org_id` of their own (per the design spec) — every page/widget endpoint takes `report_id` in its URL path, so org access is enforced by loading and `check_org`-ing the parent `Report` FIRST, before ever touching the page/widget row. This is the identical pattern `datasets.py` used for its sub-resources (Task 2), just one level deeper.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reports_org_scoping.py`:
```python
from sqlalchemy import select
from app.models.models import Report, ReportPage


async def _seed_report(db_session, org_id, name="Test Report"):
    r = Report(name=name, org_id=org_id)
    db_session.add(r)
    await db_session.flush()
    db_session.add(ReportPage(report_id=r.id, name="Page 1", position=0))
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_list_reports_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    await _seed_report(db_session, two_orgs["a"]["org"].id, "A's report")
    await _seed_report(db_session, two_orgs["b"]["org"].id, "B's report")

    resp = await client.get("/api/v1/reports", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert names == ["A's report"]


async def test_get_report_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_create_report_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers):
    resp = await client.post("/api/v1/reports", json={"name": "New Report"}, headers=auth_headers["a"])

    assert resp.status_code == 201
    result = await db_session.execute(select(Report).where(Report.id == resp.json()["id"]))
    r = result.scalar_one()
    assert r.org_id == two_orgs["a"]["org"].id


async def test_delete_report_cross_org_returns_404_and_does_not_delete(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)

    resp = await client.delete(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
    result = await db_session.execute(select(Report).where(Report.id == r.id))
    assert result.scalar_one_or_none() is not None


async def test_add_page_to_cross_org_report_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/reports/{r.id}/pages", json={"name": "Page 2"}, headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_update_page_on_cross_org_report_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.patch(
        f"/api/v1/reports/{r.id}/pages/{page.id}", json={"name": "Renamed"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_add_widget_to_cross_org_report_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.post(
        f"/api/v1/reports/{r.id}/pages/{page.id}/widgets",
        json={"widget_type": "bar", "config": {}},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_same_org_page_and_widget_operations_still_work(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["a"]["org"].id)

    page_resp = await client.post(f"/api/v1/reports/{r.id}/pages", json={"name": "Page 2"}, headers=auth_headers["a"])
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    widget_resp = await client.post(
        f"/api/v1/reports/{r.id}/pages/{page_id}/widgets",
        json={"widget_type": "bar", "config": {}},
        headers=auth_headers["a"],
    )
    assert widget_resp.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_reports_org_scoping.py -v
```
Expected: FAIL — no auth required yet, so 401-expecting assertions fail; cross-org requests currently succeed instead of 404ing.

- [ ] **Step 3: Org-scope `reports.py`**

Replace the full contents of `backend/app/routers/reports.py` with:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Report, ReportPage, ReportWidget, User
from ..schemas.schemas import (
    ReportCreate, ReportUpdate, ReportOut,
    PageCreate, PageUpdate, PageOut,
    WidgetCreate, WidgetUpdate, WidgetOut,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_REPORT_OPTS = [selectinload(Report.pages).selectinload(ReportPage.widgets)]
_PAGE_OPTS   = [selectinload(ReportPage.widgets)]


async def _get_page(page_id: int, report_id: int, db: AsyncSession, current_user: User) -> ReportPage:
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(
        select(ReportPage).options(*_PAGE_OPTS)
        .where(ReportPage.id == page_id, ReportPage.report_id == report_id)
    )
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Page not found")
    return obj


async def _get_report(report_id: int, db: AsyncSession, current_user: User) -> Report:
    r = await db.execute(select(Report).options(*_REPORT_OPTS).where(Report.id == report_id))
    obj = r.scalar_one_or_none()
    check_org(obj, current_user, "Report not found")
    return obj


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ReportOut])
async def list_reports(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(Report).options(*_REPORT_OPTS)
        .where(Report.org_id == current_user.org_id)
        .order_by(Report.created_at.desc())
    )
    return r.scalars().all()


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(body: ReportCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = Report(**body.model_dump(), org_id=current_user.org_id)
    db.add(obj)
    await db.flush()
    # Create default first page
    page = ReportPage(report_id=obj.id, name="Page 1", position=0)
    db.add(page)
    await db.commit()
    return await _get_report(obj.id, db, current_user)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await _get_report(report_id, db, current_user)


@router.patch("/{report_id}", response_model=ReportOut)
async def update_report(report_id: int, body: ReportUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy.orm.attributes import flag_modified
    obj = await _get_report(report_id, db, current_user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    if body.additional_dataset_ids is not None:
        flag_modified(obj, 'additional_dataset_ids')
    await db.commit()
    return await _get_report(report_id, db, current_user)


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Report, report_id)
    check_org(obj, current_user, "Report not found")
    await db.delete(obj)
    await db.commit()


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.post("/{report_id}/pages", response_model=PageOut, status_code=201)
async def add_page(report_id: int, body: PageCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    page = ReportPage(report_id=report_id, **body.model_dump())
    db.add(page)
    await db.commit()
    return await _get_page(page.id, report_id, db, current_user)


@router.patch("/{report_id}/pages/{page_id}", response_model=PageOut)
async def update_page(report_id: int, page_id: int, body: PageUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    page = await _get_page(page_id, report_id, db, current_user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(page, k, v)
    await db.commit()
    return await _get_page(page_id, report_id, db, current_user)


@router.delete("/{report_id}/pages/{page_id}", status_code=204)
async def delete_page(report_id: int, page_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(select(ReportPage).where(ReportPage.id == page_id, ReportPage.report_id == report_id))
    page = r.scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Page not found")
    await db.delete(page)
    await db.commit()


# ── Widgets ───────────────────────────────────────────────────────────────────

@router.post("/{report_id}/pages/{page_id}/widgets", response_model=WidgetOut, status_code=201)
async def add_widget(report_id: int, page_id: int, body: WidgetCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    widget = ReportWidget(page_id=page_id, **body.model_dump())
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return widget


@router.patch("/{report_id}/pages/{page_id}/widgets/{widget_id}", response_model=WidgetOut)
async def update_widget(report_id: int, page_id: int, widget_id: int, body: WidgetUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(select(ReportWidget).where(ReportWidget.id == widget_id, ReportWidget.page_id == page_id))
    widget = r.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(widget, k, v)
    await db.commit()
    await db.refresh(widget)
    return widget


@router.delete("/{report_id}/pages/{page_id}/widgets/{widget_id}", status_code=204)
async def delete_widget(report_id: int, page_id: int, widget_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(select(ReportWidget).where(ReportWidget.id == widget_id, ReportWidget.page_id == page_id))
    widget = r.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")
    await db.delete(widget)
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_reports_org_scoping.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/reports.py backend/tests/test_reports_org_scoping.py
git commit -m "feat: org-scope reports.py, including nested pages/widgets via parent report check"
```

---

## Task 4: Org-scope `data_sources.py`

**Files:**
- Modify: `backend/app/routers/data_sources.py`
- Test: `backend/tests/test_data_sources_org_scoping.py`

**Interfaces:**
- Consumes: `check_org` (Task 2), `get_current_user` (Phase 0).
- Note: `import_dataset` creates a `Dataset` row (not just a `DataSource` one) — it must set `org_id=current_user.org_id` on BOTH the `DataSource` it may be reading from (already org-checked via `check_org`) AND the new `Dataset` it creates.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_data_sources_org_scoping.py`:
```python
from sqlalchemy import select
from app.models.models import DataSource, Dataset


async def _seed_data_source(db_session, org_id, name="Test Source"):
    src = DataSource(name=name, type="postgres", config={}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def test_list_data_sources_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    await _seed_data_source(db_session, two_orgs["a"]["org"].id, "A's source")
    await _seed_data_source(db_session, two_orgs["b"]["org"].id, "B's source")

    resp = await client.get("/api/v1/data-sources", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["A's source"]


async def test_get_data_source_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/data-sources/{src.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_create_data_source_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/data-sources", json={"name": "New Source", "type": "postgres", "config": {}}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(DataSource).where(DataSource.id == resp.json()["id"]))
    src = result.scalar_one()
    assert src.org_id == two_orgs["a"]["org"].id


async def test_delete_data_source_cross_org_returns_404_and_does_not_delete(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.delete(f"/api/v1/data-sources/{src.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
    result = await db_session.execute(select(DataSource).where(DataSource.id == src.id))
    assert result.scalar_one_or_none() is not None


async def test_test_connection_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/data-sources/{src.id}/test", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_list_data_sources_requires_authentication(client, db_session):
    resp = await client.get("/api/v1/data-sources")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_data_sources_org_scoping.py -v
```
Expected: FAIL — no auth required yet.

- [ ] **Step 3: Org-scope `data_sources.py`**

Replace the full contents of `backend/app/routers/data_sources.py` with:
```python
import asyncio
import csv
import io
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from ..core.database import get_db
from ..core.config import settings
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import DataSource, Dataset, DatasetColumn, User
from ..schemas.schemas import DataSourceCreate, DataSourceUpdate, DataSourceOut, TablePreviewRequest, ImportRequest
from ..services.connections import test_connection, list_tables, preview_table, import_to_dataframe
from ..services.analytics import detect_types

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("", response_model=list[DataSourceOut])
async def list_data_sources(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(DataSource).where(DataSource.org_id == current_user.org_id).order_by(DataSource.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=DataSourceOut)
async def create_data_source(body: DataSourceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = DataSource(name=body.name, type=body.type, config=body.config, org_id=current_user.org_id)
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


@router.get("/{ds_id}", response_model=DataSourceOut)
async def get_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    return ds


@router.put("/{ds_id}", response_model=DataSourceOut)
async def update_data_source(ds_id: int, body: DataSourceUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    if body.name is not None:
        ds.name = body.name
    if body.type is not None:
        ds.type = body.type
    if body.config is not None:
        ds.config = body.config
        flag_modified(ds, 'config')
    await db.commit()
    await db.refresh(ds)
    return ds


@router.delete("/{ds_id}", status_code=204)
async def delete_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    await db.delete(ds)
    await db.commit()


@router.post("/{ds_id}/test")
async def test_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    result = await asyncio.to_thread(test_connection, cfg)
    return result


@router.get("/{ds_id}/schema")
async def get_schema(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    try:
        tables = await asyncio.to_thread(list_tables, cfg)
        return {'tables': tables}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{ds_id}/preview")
async def preview_data(ds_id: int, req: TablePreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    try:
        result = await asyncio.to_thread(preview_table, cfg, req.table, req.query, req.limit)
        return result
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{ds_id}/import")
async def import_dataset(ds_id: int, req: ImportRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type

    def _run():
        df = import_to_dataframe(cfg, req.table, req.query)
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = req.dataset_name.replace(' ', '_').replace('/', '_')
        file_path = upload_dir / f"{safe_name}.csv"
        df.to_csv(file_path, index=False)
        type_map = detect_types(df)
        return df, str(file_path), type_map

    try:
        df, file_path, type_map = await asyncio.to_thread(_run)
    except Exception as e:
        raise HTTPException(400, str(e))

    dataset = Dataset(
        name=req.dataset_name,
        description=f"Imported from {ds.name} ({ds.type})",
        filename=file_path,
        row_count=len(df),
        col_count=len(df.columns),
        file_size=Path(file_path).stat().st_size,
        data_source_id=ds_id,
        source_table=req.table,
        source_query=req.query,
        org_id=current_user.org_id,
    )
    db.add(dataset)
    await db.flush()

    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=dataset.id, name=col_name, dtype=dtype,
            missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={},
        ))

    await db.commit()
    await db.refresh(dataset)
    return {'id': dataset.id, 'name': dataset.name, 'row_count': dataset.row_count, 'col_count': dataset.col_count}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_data_sources_org_scoping.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/data_sources.py backend/tests/test_data_sources_org_scoping.py
git commit -m "feat: org-scope data_sources.py, including org_id on imported datasets"
```

---

## Task 5: Org-scope `hierarchy.py`, `widget_data.py`, `analysis.py`

**Files:**
- Modify: `backend/app/routers/hierarchy.py`
- Modify: `backend/app/routers/widget_data.py`
- Modify: `backend/app/routers/analysis.py`
- Test: `backend/tests/test_hierarchy_widget_analysis_org_scoping.py`

**Interfaces:**
- Consumes: `check_org` (Task 2), `get_current_user` (Phase 0).
- Behavior note (flagged, not a bug to avoid): `analysis.py`'s existing `get_analysis` endpoint currently does NOT verify the dataset exists at all — it queries `AnalysisResult` directly by `dataset_id` with no ownership check whatsoever. This task adds a `Dataset` lookup + `check_org` to `get_analysis` that wasn't there before, which is a genuine, required behavior change (without it, org scoping would be meaningless here — any user could query analysis results for any `dataset_id`, including other orgs', if one happened to exist). This is the one router change in this phase that adds a check where literally none existed, rather than converting an existing "not found" check into an org-aware one.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hierarchy_widget_analysis_org_scoping.py`:
```python
from app.models.models import Dataset, HierarchyNode, AnalysisResult


async def _seed_dataset(db_session, org_id, name="Test Dataset"):
    ds = Dataset(name=name, org_id=org_id)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


# ── hierarchy.py ────────────────────────────────────────────────────────────

async def test_get_hierarchy_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}/hierarchy", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_create_hierarchy_node_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/hierarchy", json={"name": "Node 1", "node_type": "folder"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_hierarchy_endpoints_same_org_still_work(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}/hierarchy", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json() == []


# ── widget_data.py ────────────────────────────────────────────────────────────

async def test_query_widget_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data", json={"config": {}, "widget_type": "bar"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


# ── analysis.py ───────────────────────────────────────────────────────────────

async def test_run_analysis_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={"analysis_type": "full"}, headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_analysis_cross_org_returns_404_even_when_a_result_exists(client, db_session, two_orgs, auth_headers):
    """This is the specific case the task brief flags: get_analysis previously did
    zero ownership checking at all, so a pre-existing AnalysisResult for another
    org's dataset must now be unreachable, not just a dataset-not-found short-circuit."""
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)
    db_session.add(AnalysisResult(dataset_id=ds.id, analysis_type="full", result={"some": "data"}))
    await db_session.commit()

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_analysis_same_org_returns_the_result(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)
    db_session.add(AnalysisResult(dataset_id=ds.id, analysis_type="full", result={"some": "data"}))
    await db_session.commit()

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json() == {"some": "data"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_hierarchy_widget_analysis_org_scoping.py -v
```
Expected: FAIL — no auth required yet, no org checks yet.

- [ ] **Step 3: Org-scope `hierarchy.py`**

Replace the full contents of `backend/app/routers/hierarchy.py` with:
```python
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, HierarchyNode, User
from ..schemas.schemas import HierarchyNodeCreate, HierarchyNodeUpdate, HierarchyNodeOut
from ..services.analytics import load_file, detect_types

router = APIRouter(prefix="/datasets", tags=["hierarchy"])


async def _get_dataset(dataset_id: int, db: AsyncSession, current_user: User) -> Dataset:
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds


@router.get("/{dataset_id}/hierarchy", response_model=list[HierarchyNodeOut])
async def get_hierarchy(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    r = await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id).order_by(HierarchyNode.position)
    )
    return r.scalars().all()


@router.post("/{dataset_id}/hierarchy", response_model=HierarchyNodeOut, status_code=201)
async def create_node(dataset_id: int, body: HierarchyNodeCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    node = HierarchyNode(dataset_id=dataset_id, **body.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.patch("/{dataset_id}/hierarchy/{node_id}", response_model=HierarchyNodeOut)
async def update_node(dataset_id: int, node_id: int, body: HierarchyNodeUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    r = await db.execute(select(HierarchyNode).where(HierarchyNode.id == node_id, HierarchyNode.dataset_id == dataset_id))
    node = r.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(node, k, v)
    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/{dataset_id}/hierarchy/{node_id}", status_code=204)
async def delete_node(dataset_id: int, node_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    r = await db.execute(select(HierarchyNode).where(HierarchyNode.id == node_id, HierarchyNode.dataset_id == dataset_id))
    node = r.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    await db.delete(node)
    await db.commit()


@router.post("/{dataset_id}/hierarchy/auto-generate", response_model=list[HierarchyNodeOut])
async def auto_generate(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await _get_dataset(dataset_id, db, current_user)
    if not ds.filename:
        raise HTTPException(404, "Dataset not found or no file")

    try:
        df       = await asyncio.to_thread(load_file, ds.filename)
        type_map = await asyncio.to_thread(detect_types, df)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    await db.execute(delete(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id))

    folder_info = [
        ("Dimensions", "categorical", "dimension"),
        ("Measures",   "numeric",     "measure"),
        ("Dates",      "datetime",    "date"),
        ("Text",       "text",        "text"),
    ]
    folder_ids: dict[str, int] = {}
    for pos, (fname, fkey, _) in enumerate(folder_info):
        folder = HierarchyNode(dataset_id=dataset_id, name=fname, node_type="folder", position=pos)
        db.add(folder)
        await db.flush()
        folder_ids[fkey] = folder.id

    counters: dict[str, int] = {k: 0 for k in folder_ids}
    for col_name, col_type in type_map.items():
        if col_type not in folder_ids:
            continue
        _, _, ntype = next(x for x in folder_info if x[1] == col_type)
        node = HierarchyNode(
            dataset_id=dataset_id,
            parent_id=folder_ids[col_type],
            name=col_name,
            node_type=ntype,
            column_name=col_name,
            aggregation="sum" if col_type == "numeric" else None,
            position=counters[col_type],
        )
        db.add(node)
        counters[col_type] += 1

    await db.commit()
    r = await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id).order_by(HierarchyNode.position)
    )
    return r.scalars().all()
```

- [ ] **Step 4: Org-scope `widget_data.py`**

Replace the full contents of `backend/app/routers/widget_data.py` with:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..core.org_scope import check_org
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
    calc_cols = list(req.calculated_columns or []) + list(ds.calculated_columns or [])
    try:
        return get_widget_data(
            ds.filename, req.config, widget_type=req.widget_type,
            calculated_columns=calc_cols or None, filter_expr=ds.default_filter_expr or None,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")
```

- [ ] **Step 5: Org-scope `analysis.py`**

Replace the full contents of `backend/app/routers/analysis.py` with:
```python
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, AnalysisResult, User
from ..schemas.schemas import AnalysisRequest
from ..services.analytics import load_file, run_full_analysis

router = APIRouter(prefix="/datasets", tags=["analysis"])


@router.post("/{dataset_id}/analysis")
async def run_analysis(dataset_id: int, req: AnalysisRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    df     = await asyncio.to_thread(load_file, ds.filename)
    result = await asyncio.to_thread(run_full_analysis, df)

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
(`get_analysis` gains a `Dataset` lookup + `check_org` that did not exist in any form before — see this task's Interfaces note above.)

- [ ] **Step 6: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_hierarchy_widget_analysis_org_scoping.py -v
```
Expected: 8 passed.

- [ ] **Step 7: Run the full backend suite**

```bash
pytest -q
```
Expected: all passing, no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/hierarchy.py backend/app/routers/widget_data.py backend/app/routers/analysis.py backend/tests/test_hierarchy_widget_analysis_org_scoping.py
git commit -m "feat: org-scope hierarchy.py, widget_data.py, and analysis.py"
```

---

## Task 6: Full regression pass and Phase 1 close-out

**Files:** none (verification only), plus the design spec status line.

- [ ] **Step 1: Run the full automated test suite**

Run (from `backend/`):
```bash
pytest -v
```
Expected: all tests pass — the pre-existing 149, plus this phase's new ones (5 migrate/backfill + 4 org_scope + 8 datasets + 8 reports + 6 data_sources + 8 hierarchy/widget/analysis = 39 new, ~188 total; exact count isn't the point, zero failures is).

- [ ] **Step 2: Full manual regression read — confirm every router is actually covered**

Run (from `backend/`):
```bash
grep -L "get_current_user" app/routers/*.py
```
Expected: only `app/routers/auth.py` (login/me are intentionally unauthenticated — you need `/auth/login` to work without a token) and `app/routers/__init__.py` (if it has content) should appear, if anything. Every OTHER router file (`datasets.py`, `reports.py`, `hierarchy.py`, `widget_data.py`, `data_sources.py`, `analysis.py`) must NOT appear in this output — if one does, that router was missed and this task is not actually done; go back and fix it before proceeding.

Also confirm:
```bash
grep -c "check_org" app/routers/*.py
```
Every router file except `auth.py` should show a non-zero count.

- [ ] **Step 3: Confirm the backfill actually runs correctly against a real startup**

This step exercises `_backfill_default_org` the way it will really run — at app startup — rather than only via the direct-call tests from Task 1. If the docker-compose dev stack is running (check with `docker ps` for `datalytics_backend`/`datalytics_db`), rebuild and restart it (`docker compose up -d --build backend`, from the directory containing `docker-compose.yml`) and check its startup logs for successful completion (no unhandled exception during `lifespan`). This is a real-infrastructure step like Phase 0's Task 8 — if you do this, note in your report exactly what you observed (log output, whether it succeeded), and do not leave any test-only artifacts behind beyond what a normal successful startup would produce (the backfill itself, run against real data, is the intended production behavior — not something to revert).

If the dev stack isn't running or this step can't be completed safely, note that explicitly rather than skipping silently — this is a "nice to have, real-world confirmation" step, not a blocking requirement for the task suite to pass, since Task 1's direct-call tests already prove the function's logic works.

- [ ] **Step 4: Update the design spec status**

In `docs/superpowers/specs/2026-08-13-row-level-security-design.md`, change the `**Status:**` line from `Phase 0 (Auth Foundation) Complete` to `Phase 1 (Org Scoping) Complete`.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-13-row-level-security-design.md
git commit -m "docs: mark Row-Level Security Phase 1 (Org Scoping) complete"
```

**Phase 1 is now done — every existing endpoint requires authentication and enforces organization boundaries.** The app is now safe for multiple separate organizations sharing one deployment, though within an organization every user still sees everything (no per-role row filtering yet). Phase 2 (the `RowSecurityRule` model, admin CRUD endpoints, and enforcement wired into `get_widget_data`'s query path) gets its own plan document, written fresh against this foundation.
