# Custom Connector Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an org admin define named, org-scoped presets of an existing
connector type ("Acme Snowflake" = `snowflake` with `account`/`warehouse`/
`role` fixed and locked), so other users pick a sanctioned tile instead of
typing raw connection details.

**Architecture:** A new `custom_connectors` table holds presets. A
`DataSource` created from a preset stores the preset's real base type in its
existing `type` column and records which preset it used in a new nullable
`custom_connector_id` FK. `connectors.py` is never modified to know presets
exist — every one of its ~25 existing call sites keeps working unchanged
because `DataSource.type` is always an ordinary registry key. Locking is
applied once, at `DataSource` create/update time, in the router layer.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic, Pydantic schemas,
React + TypeScript frontend, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-09-custom-connector-framework-design.md`

## Global Constraints

- `connectors.py` gains exactly one changed function (`catalog_payload`) and
  zero new DB access — it stays synchronous and DB-free. Presets are passed
  in as already-loaded data, never fetched by `connectors.py` itself.
- `DataSource.type` is **always** a real `connectors.py` registry key, never
  a synthetic string — this is the property that keeps every existing
  `connectors.*` call site unchanged.
- Preset authoring (`POST`/`PUT`/`DELETE /custom-connectors`) is **org-admin
  only**, via `Depends(require_org_admin)` (`app/dependencies.py:97-100`).
- A preset lookup by id is **always** filtered by the caller's `org_id` in
  the same query — never `db.get(CustomConnector, id)` alone. A miss (wrong
  org or wrong id) is a 404, and the two cases must be indistinguishable to
  the caller.
- Deleting an in-use preset is rejected (409) — never silently unlinked.
- All secret fields in `CustomConnector.base_config` are encrypted via the
  existing `services/secrets.py` (`encrypt_config`/`decrypt_config`), keyed
  by `connectors.secret_field_names(base_type)` — the identical mechanism
  `DataSource.config` already uses.

---

### Task 1: Data model — `custom_connectors` table and `DataSource.custom_connector_id`

**Files:**
- Modify: `backend/app/models/models.py` (new `CustomConnector` class after
  `DataSource`, ~line 271; one new column on `DataSource`)
- Create: `backend/alembic/versions/0023_custom_connectors.py`
- Modify: `backend/app/main.py` (one new line in the `_migrate` statement
  list, alongside the other `data_sources` ALTERs around line 160)
- Test: `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: `CustomConnector` ORM class (`id, org_id, key, label, base_type,
  base_config, locked_fields, created_by, created_at, updated_at`) and
  `DataSource.custom_connector_id` (nullable int). Later tasks import
  `CustomConnector` from `app.models.models`.

- [ ] **Step 1: Add the `CustomConnector` model and `DataSource`'s new column**

In `backend/app/models/models.py`, immediately after the `DataSource` class
(which ends at line 270 with `cache_epoch = Column(...)`), add:

```python
    # Phase 5: custom connector presets. NULL for every DataSource created
    # before this feature and for any plain (non-preset) connection.
    # ondelete="RESTRICT": deleting a preset that is still in use must fail
    # loudly, not silently turn a locked-down connection into an unlocked one.
    custom_connector_id = Column(Integer, ForeignKey("custom_connectors.id", ondelete="RESTRICT"),
                                  nullable=True, index=True)


class CustomConnector(Base):
    """A named, org-scoped preset of an existing connectors.py base type.
    `base_config` holds fixed field values (secrets encrypted, same as
    DataSource.config); `locked_fields` is the subset of those keys a
    DataSource created from this preset may not override. See
    docs/superpowers/specs/2026-09-09-custom-connector-framework-design.md."""
    __tablename__ = "custom_connectors"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    key           = Column(String(100), nullable=False)
    label         = Column(String(255), nullable=False)
    base_type     = Column(String(50), nullable=False)
    base_config   = Column(JSON, default=dict)
    locked_fields = Column(JSON, default=list)
    created_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at    = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_custom_connectors_org_key"),)
```

Note: `custom_connector_id` is added to the *existing* `DataSource` class
body (before its closing, i.e. as the new last column), not as a separate
class. `CustomConnector` is a brand-new class placed after it.

- [ ] **Step 2: Write the Alembic migration**

Current head is `0022_dataset_custom_functions` (`alembic/versions/`). Create
`backend/alembic/versions/0023_custom_connectors.py`:

```python
"""Custom connector presets: `custom_connectors` table and
`data_sources.custom_connector_id`.

Chained on 0022_dataset_custom_functions.

Revision ID: 0023_custom_connectors
Revises: 0022_dataset_custom_functions
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0023_custom_connectors'
down_revision: Union[str, None] = '0022_dataset_custom_functions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custom_connectors',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE', name='fk_custom_connectors_org_id_organizations'),
                  nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('base_type', sa.String(50), nullable=False),
        sa.Column('base_config', sa.JSON(), nullable=True),
        sa.Column('locked_fields', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_custom_connectors_created_by_users'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('org_id', 'key', name='uq_custom_connectors_org_key'),
    )
    op.create_index('ix_custom_connectors_org_id', 'custom_connectors', ['org_id'])
    op.create_index('ix_custom_connectors_created_by', 'custom_connectors', ['created_by'])

    with op.batch_alter_table('data_sources') as batch_op:
        batch_op.add_column(sa.Column(
            'custom_connector_id', sa.Integer(),
            sa.ForeignKey('custom_connectors.id', ondelete='RESTRICT',
                           name='fk_data_sources_custom_connector_id_custom_connectors'),
            nullable=True))
        batch_op.create_index('ix_data_sources_custom_connector_id', ['custom_connector_id'])


def downgrade() -> None:
    with op.batch_alter_table('data_sources') as batch_op:
        batch_op.drop_index('ix_data_sources_custom_connector_id')
        batch_op.drop_column('custom_connector_id')
    op.drop_index('ix_custom_connectors_created_by', table_name='custom_connectors')
    op.drop_index('ix_custom_connectors_org_id', table_name='custom_connectors')
    op.drop_table('custom_connectors')
```

- [ ] **Step 3: Add the dev/prod startup ALTER for `data_sources.custom_connector_id`**

`custom_connectors` is a brand-new table — `Base.metadata.create_all()`
(already run at startup) provisions it for free, exactly as
`main.py`'s comments document for every other brand-new table (search
`main.py` for "brand-new table so create_all"). Only the new column on the
*existing* `data_sources` table needs an explicit statement, because
`create_all` never alters existing tables. In `backend/app/main.py`, in the
`_migrate` statement list, add this line immediately after the line reading
`"ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL"`:

```python
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS custom_connector_id INTEGER REFERENCES custom_connectors(id) ON DELETE RESTRICT",
```

- [ ] **Step 4: Write the failing test pinning the new statement**

In `backend/tests/test_migrations.py`, in the same test class as
`test_datasets_gets_custom_functions_column`, add:

```python
    async def test_data_sources_gets_custom_connector_id_column(self):
        """Custom connector framework: data_sources.custom_connector_id must be
        added to an already-deployed database via _migrate, the same way
        created_by was (see main.py's _migrate docstring)."""
        conn = _RecordingConn()
        await _migrate(conn)
        assert any(
            "data_sources" in s and "custom_connector_id" in s and "IF NOT EXISTS" in s
            for s in conn.statements
        )
```

Run: `pytest tests/test_migrations.py -k custom_connector -v` (in the
project's Docker test container — see `docker-compose.yml` and the
`backend-test-interpreter` note for the exact invocation). Expected: FAIL —
the statement doesn't exist yet.

- [ ] **Step 5: Add the model/migration, run the test, verify it passes**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/models.py backend/alembic/versions/0023_custom_connectors.py backend/app/main.py backend/tests/test_migrations.py
git commit -m "feat: add custom_connectors table and DataSource.custom_connector_id"
```

---

### Task 2: Backend schemas

**Files:**
- Modify: `backend/app/schemas/schemas.py` (new `CustomConnectorCreate`/
  `CustomConnectorUpdate`/`CustomConnectorOut`; extend `DataSourceCreate`/
  `DataSourceUpdate`/`DataSourceOut`, lines 421-439)

**Interfaces:**
- Consumes: nothing new.
- Produces: the four Pydantic models later tasks import from
  `app.schemas.schemas`.

- [ ] **Step 1: Extend the `DataSource*` schemas**

Replace lines 421-439 of `backend/app/schemas/schemas.py`:

```python
class DataSourceCreate(BaseModel):
    name: str
    type: str
    config: dict = {}
    custom_connector_id: Optional[int] = None

class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    config: Optional[dict] = None
    cache_ttl_seconds: Optional[int] = None
    custom_connector_id: Optional[int] = None

class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    config: dict = {}
    cache_ttl_seconds: int = 60
    created_at: datetime
    custom_connector_id: Optional[int] = None
    custom_connector_label: Optional[str] = None
```

- [ ] **Step 2: Add the `CustomConnector*` schemas**

Immediately after the block above, add:

```python
class CustomConnectorCreate(BaseModel):
    key: str
    label: str
    base_type: str
    base_config: dict = {}
    locked_fields: list[str] = []

class CustomConnectorUpdate(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    base_type: Optional[str] = None
    base_config: Optional[dict] = None
    locked_fields: Optional[list[str]] = None

class CustomConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    label: str
    base_type: str
    base_config: dict = {}
    locked_fields: list[str] = []
    created_at: datetime
```

- [ ] **Step 3: Verify the module still imports cleanly**

Run: `python -c "import app.schemas.schemas"` inside the backend container
(or `pytest tests/test_data_source_secrets.py -v`, which already imports
`DataSourceOut` transitively — any existing green test file suffices as a
smoke check here since this task adds no new test file of its own).
Expected: no error.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat: add custom connector schemas, extend DataSource schemas"
```

---

### Task 3: Service layer — validation and config merging

**Files:**
- Create: `backend/app/services/custom_connectors.py`
- Test: `backend/tests/test_custom_connectors.py` (created here; Task 5
  appends the API-level tests to the same file)

**Interfaces:**
- Consumes: `connectors.is_known`, `connectors.resolve`,
  `connectors.secret_field_names` (`app/services/connectors.py`);
  `secrets.decrypt_config` (`app/services/secrets.py`); the `CustomConnector`
  model (Task 1).
- Produces: `CustomConnectorError`, `validate_custom_connector_def(base_type,
  base_config, locked_fields) -> None`, `apply_preset_locks(config: dict,
  preset: CustomConnector) -> dict` — both imported by the routers in
  Tasks 5 and 6.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_custom_connectors.py`:

```python
import pytest

from app.models.models import CustomConnector
from app.services.custom_connectors import (
    CustomConnectorError, validate_custom_connector_def, apply_preset_locks,
)


class TestValidateCustomConnectorDef:
    def test_unknown_base_type_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="Unknown connector type"):
            validate_custom_connector_def("not-a-real-type", {}, [])

    def test_base_config_key_not_on_the_base_type_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="Unknown config field"):
            validate_custom_connector_def("postgresql", {"not_a_field": "x"}, [])

    def test_locked_field_not_on_the_base_type_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="Unknown locked field"):
            validate_custom_connector_def("postgresql", {"host": "h"}, ["not_a_field"])

    def test_locked_field_with_no_base_config_value_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="no value to lock"):
            validate_custom_connector_def("postgresql", {"host": "h"}, ["port"])

    def test_a_valid_definition_passes(self):
        validate_custom_connector_def("postgresql", {"host": "db.acme.internal", "port": 5432},
                                       ["host", "port"])


class TestApplyPresetLocks:
    def _preset(self, base_type="postgresql", base_config=None, locked_fields=None):
        return CustomConnector(id=1, org_id=1, key="acme-pg", label="Acme Postgres",
                                base_type=base_type, base_config=base_config or {},
                                locked_fields=locked_fields or [])

    def test_locked_field_overrides_a_client_supplied_value(self):
        preset = self._preset(base_config={"host": "acme-prod.internal"}, locked_fields=["host"])

        result = apply_preset_locks({"host": "attacker-supplied", "user": "alice"}, preset)

        assert result == {"host": "acme-prod.internal", "user": "alice"}

    def test_non_locked_preset_value_is_a_default_only(self):
        preset = self._preset(base_config={"port": 5432}, locked_fields=[])

        with_override = apply_preset_locks({"port": 9999}, preset)
        without_override = apply_preset_locks({}, preset)

        assert with_override == {"port": 9999}
        assert without_override == {"port": 5432}
```

Run: `pytest tests/test_custom_connectors.py -v`. Expected: FAIL — the
`app.services.custom_connectors` module doesn't exist yet.

- [ ] **Step 2: Implement the service**

Create `backend/app/services/custom_connectors.py`:

```python
"""Custom connector presets: save-time validation and config merging.

A preset wraps one existing `connectors.py` base type (see that module) with
fixed field values, some of which are locked. This module never touches the
database and never talks to `connectors.py`'s registry beyond the read-only
lookups it already exposes -- see
docs/superpowers/specs/2026-09-09-custom-connector-framework-design.md.
"""
from __future__ import annotations

from . import connectors
from . import secrets
from ..models.models import CustomConnector


class CustomConnectorError(ValueError):
    """Raised when a custom connector preset definition fails validation."""


def validate_custom_connector_def(base_type: str, base_config: dict, locked_fields: list[str]) -> None:
    if not connectors.is_known(base_type):
        raise CustomConnectorError(f"Unknown connector type '{base_type}'")
    field_names = {f.name for f in connectors.resolve(base_type).config_fields}

    unknown_base = set(base_config or {}) - field_names
    if unknown_base:
        raise CustomConnectorError(
            f"Unknown config field(s) for '{base_type}': {', '.join(sorted(unknown_base))}")

    unknown_locked = set(locked_fields or []) - field_names
    if unknown_locked:
        raise CustomConnectorError(
            f"Unknown locked field(s) for '{base_type}': {', '.join(sorted(unknown_locked))}")

    not_in_base = set(locked_fields or []) - set(base_config or {})
    if not_in_base:
        raise CustomConnectorError(
            f"Locked field(s) have no value to lock: {', '.join(sorted(not_in_base))}")


def apply_preset_locks(config: dict, preset: CustomConnector) -> dict:
    """`config` with the preset's locked fields forced to the preset's values,
    and its non-locked fields used only as defaults for keys `config` omits.
    `preset.base_config` is stored encrypted (same convention as
    DataSource.config), so it is decrypted here before merging."""
    base = secrets.decrypt_config(preset.base_config or {}, connectors.secret_field_names(preset.base_type))
    locked = set(preset.locked_fields or [])
    merged = dict(config or {})
    for key, value in base.items():
        if key in locked or key not in merged:
            merged[key] = value
    return merged
```

- [ ] **Step 3: Run the tests, verify they pass**

Run: `pytest tests/test_custom_connectors.py -v`. Expected: PASS (8 tests).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/custom_connectors.py backend/tests/test_custom_connectors.py
git commit -m "feat: add custom connector validation and config-merge service"
```

---

### Task 4: `connectors.py` — preset tiles in the catalog

**Files:**
- Modify: `backend/app/services/connectors.py:466-482` (`catalog_payload`)
- Test: `backend/tests/test_custom_connectors.py` (append)

**Interfaces:**
- Consumes: nothing new — no DB access is added to this module. Callers
  (Task 5's router) pass in already-loaded `CustomConnector` rows.
- Produces: `catalog_payload(custom_connectors: list | None = None) ->
  list[dict]` — the new optional parameter. Existing zero-arg calls are
  unaffected (default `None` reproduces exactly today's output).

**Design note (refinement over the spec):** the spec's "Catalog listing"
section describes this as `catalog_payload(org_id=...)`. Implementing it
that way would require `connectors.py` to run a database query itself,
which breaks this module's one deliberate invariant (synchronous, in-memory,
DB-independent — see the spec's "Context" section). Passing the caller's
already-loaded preset rows in directly avoids that entirely and mirrors how
`custom_functions.py`'s `expand_custom_functions` receives its custom
functions as a plain parameter rather than querying for them itself. The
observable behavior described in the spec (an org's presets appear as
catalog tiles with locked fields filtered out) is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_custom_connectors.py`:

```python
from app.services import connectors


class TestCatalogPayloadWithPresets:
    def test_no_presets_argument_reproduces_todays_output(self):
        assert connectors.catalog_payload() == connectors.catalog_payload(None)

    def test_a_preset_appears_as_a_custom_tile_with_locked_fields_filtered(self):
        preset = CustomConnector(id=7, org_id=1, key="acme-pg", label="Acme Postgres",
                                  base_type="postgresql", base_config={"host": "h", "port": 5432},
                                  locked_fields=["host"])

        payload = connectors.catalog_payload([preset])

        tile = next(t for t in payload if t.get("is_custom"))
        assert tile["key"] == "custom:7"
        assert tile["label"] == "Acme Postgres"
        assert tile["base_type"] == "postgresql"
        assert tile["custom_connector_id"] == 7
        field_names = {f["name"] for f in tile["config_fields"]}
        assert "host" not in field_names   # locked -- not shown
        assert "port" in field_names       # not locked -- still editable/visible

    def test_a_preset_with_an_unknown_base_type_is_skipped_not_crashed(self):
        preset = CustomConnector(id=8, org_id=1, key="stale", label="Stale",
                                  base_type="not-a-real-type", base_config={}, locked_fields=[])

        payload = connectors.catalog_payload([preset])

        assert not any(t.get("custom_connector_id") == 8 for t in payload)
```

Run: `pytest tests/test_custom_connectors.py -k CatalogPayload -v`.
Expected: FAIL — `catalog_payload` doesn't accept an argument yet.

- [ ] **Step 2: Implement the change**

Replace `catalog_payload` (`backend/app/services/connectors.py:466-482`)
with:

```python
def catalog_payload(custom_connectors: list | None = None) -> list[dict]:
    """The catalog for the frontend — no secrets, no dialect internals.
    `custom_connectors`, when given, is a list of already-loaded
    CustomConnector rows (or anything with the same attributes) whose org
    the caller has already scoped -- this function does no DB access and no
    org filtering of its own."""
    out = []
    for s in _ALL_SPECS:
        out.append({
            "key": s.key, "label": s.label, "icon": s.icon, "category": s.category,
            "default_port": s.default_port,
            "driver_installed": s.driver_installed,
            "supports_directquery": s.supports_directquery,
            "is_custom": False,
            "config_fields": [
                {"name": f.name, "label": f.label, "kind": f.kind, "required": f.required,
                 "default": f.default, "placeholder": f.placeholder, "options": list(f.options),
                 "secret": f.secret, "show_if": list(f.show_if) if f.show_if else None}
                for f in s.config_fields
            ],
        })
    for cc in (custom_connectors or []):
        spec = _REGISTRY.get(cc.base_type)
        if spec is None:
            continue  # the preset's base type was removed from the registry -- skip, don't crash the catalog
        locked = set(cc.locked_fields or [])
        out.append({
            "key": f"custom:{cc.id}", "label": cc.label, "icon": spec.icon, "category": "Custom",
            "default_port": spec.default_port,
            "driver_installed": spec.driver_installed,
            "supports_directquery": spec.supports_directquery,
            "is_custom": True, "base_type": cc.base_type, "custom_connector_id": cc.id,
            "config_fields": [
                {"name": f.name, "label": f.label, "kind": f.kind, "required": f.required,
                 "default": f.default, "placeholder": f.placeholder, "options": list(f.options),
                 "secret": f.secret, "show_if": list(f.show_if) if f.show_if else None}
                for f in spec.config_fields if f.name not in locked
            ],
        })
    return out
```

- [ ] **Step 3: Run the tests, verify they pass**

Run: `pytest tests/test_custom_connectors.py -v`. Expected: PASS (11 tests
total for this file so far).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/connectors.py backend/tests/test_custom_connectors.py
git commit -m "feat: catalog_payload includes org custom connector preset tiles"
```

---

### Task 5: `custom_connectors` router (org-admin CRUD)

**Files:**
- Create: `backend/app/routers/custom_connectors.py`
- Modify: `backend/app/main.py` (import + `include_router`, near line 15/497)
- Test: `backend/tests/test_custom_connectors.py` (append)

**Interfaces:**
- Consumes: `validate_custom_connector_def` (Task 3), `CustomConnector`
  model (Task 1), `CustomConnectorCreate/Update/Out` schemas (Task 2),
  `require_org_admin` (`app/dependencies.py:97-100`).
- Produces: `GET/POST /api/v1/custom-connectors`,
  `PUT/DELETE /api/v1/custom-connectors/{id}` — consumed by the frontend in
  Task 8.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_custom_connectors.py`:

```python
async def _create_preset(client, headers, **overrides):
    body = {"key": "acme-pg", "label": "Acme Postgres", "base_type": "postgresql",
            "base_config": {"host": "acme-prod.internal", "port": 5432}, "locked_fields": ["host"]}
    body.update(overrides)
    return await client.post("/api/v1/custom-connectors", json=body, headers=headers)


class TestCustomConnectorsApi:
    async def test_create_requires_org_admin(self, client, db_session, two_orgs):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User

        role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=two_orgs["a"]["org"].id, role_id=role.id,
                    email="viewer-cc@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

        resp = await _create_preset(client, headers)

        assert resp.status_code == 403

    async def test_create_rejects_invalid_definition(self, client, db_session, two_orgs, auth_headers):
        resp = await _create_preset(client, auth_headers["a"], base_config={"not_a_field": "x"})
        assert resp.status_code == 400

    async def test_create_then_list_round_trips(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()
        # "host" is not one of postgresql's secret fields (only "password" is),
        # so it round-trips in plaintext -- unlike DataSource.config, nothing
        # here needs redacting for a non-secret field.
        assert created["base_config"]["host"] == "acme-prod.internal"

        resp = await client.get("/api/v1/custom-connectors", headers=auth_headers["a"])

        assert resp.status_code == 200
        assert [p["key"] for p in resp.json()] == ["acme-pg"]

    async def test_duplicate_key_in_same_org_is_rejected(self, client, db_session, two_orgs, auth_headers):
        await _create_preset(client, auth_headers["a"])

        resp = await _create_preset(client, auth_headers["a"])

        assert resp.status_code == 409

    async def test_same_key_in_different_orgs_is_allowed(self, client, db_session, two_orgs, auth_headers):
        await _create_preset(client, auth_headers["a"])

        resp = await _create_preset(client, auth_headers["b"])

        assert resp.status_code == 200

    async def test_org_b_cannot_see_org_a_presets(self, client, db_session, two_orgs, auth_headers):
        await _create_preset(client, auth_headers["a"])

        resp = await client.get("/api/v1/custom-connectors", headers=auth_headers["b"])

        assert resp.json() == []

    async def test_update_cross_org_returns_404(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()

        resp = await client.put(f"/api/v1/custom-connectors/{created['id']}",
                                 json={"label": "Hijacked"}, headers=auth_headers["b"])

        assert resp.status_code == 404

    async def test_delete_with_no_referencing_data_source_succeeds(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()

        resp = await client.delete(f"/api/v1/custom-connectors/{created['id']}", headers=auth_headers["a"])

        assert resp.status_code == 204

    async def test_delete_with_a_referencing_data_source_is_rejected(self, client, db_session, two_orgs, auth_headers):
        from app.models.models import DataSource

        created = (await _create_preset(client, auth_headers["a"])).json()
        ds = DataSource(name="uses preset", type="postgresql", config={},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=created["id"])
        db_session.add(ds)
        await db_session.commit()

        resp = await client.delete(f"/api/v1/custom-connectors/{created['id']}", headers=auth_headers["a"])

        assert resp.status_code == 409
        assert "1" in resp.json()["detail"]
```

Run: `pytest tests/test_custom_connectors.py -k CustomConnectorsApi -v`.
Expected: FAIL — `/api/v1/custom-connectors` doesn't exist yet (404s where
the assertions expect other codes).

- [ ] **Step 2: Implement the router**

Create `backend/app/routers/custom_connectors.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db
from ..dependencies import require_org_admin
from ..models.models import CustomConnector, DataSource, User
from ..schemas.schemas import CustomConnectorCreate, CustomConnectorOut, CustomConnectorUpdate
from ..services import connectors, secrets
from ..services.custom_connectors import CustomConnectorError, validate_custom_connector_def

router = APIRouter(prefix="/custom-connectors", tags=["custom-connectors"])


def _redacted(cc: CustomConnector) -> CustomConnectorOut:
    out = CustomConnectorOut.model_validate(cc)
    out.base_config = secrets.redact_config(cc.base_config or {}, connectors.secret_field_names(cc.base_type))
    return out


async def _owned_or_404(db: AsyncSession, cc_id: int, org_id: int) -> CustomConnector:
    cc = (await db.execute(
        select(CustomConnector).where(CustomConnector.id == cc_id, CustomConnector.org_id == org_id)
    )).scalar_one_or_none()
    if cc is None:
        raise HTTPException(404, "Custom connector not found")
    return cc


@router.get("", response_model=list[CustomConnectorOut])
async def list_custom_connectors(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(
        select(CustomConnector).where(CustomConnector.org_id == current_user.org_id).order_by(CustomConnector.created_at.desc())
    )
    return [_redacted(cc) for cc in result.scalars().all()]


@router.post("", response_model=CustomConnectorOut)
async def create_custom_connector(body: CustomConnectorCreate, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_org_admin)):
    try:
        validate_custom_connector_def(body.base_type, body.base_config, body.locked_fields)
    except CustomConnectorError as e:
        raise HTTPException(400, str(e))

    dupe = (await db.execute(
        select(CustomConnector).where(CustomConnector.org_id == current_user.org_id, CustomConnector.key == body.key)
    )).scalar_one_or_none()
    if dupe is not None:
        raise HTTPException(409, f"A custom connector with key '{body.key}' already exists")

    encrypted = secrets.encrypt_config(body.base_config or {}, connectors.secret_field_names(body.base_type))
    cc = CustomConnector(org_id=current_user.org_id, key=body.key, label=body.label, base_type=body.base_type,
                          base_config=encrypted, locked_fields=body.locked_fields or [], created_by=current_user.id)
    db.add(cc)
    await db.commit()
    await db.refresh(cc)
    return _redacted(cc)


@router.put("/{cc_id}", response_model=CustomConnectorOut)
async def update_custom_connector(cc_id: int, body: CustomConnectorUpdate, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_org_admin)):
    cc = await _owned_or_404(db, cc_id, current_user.org_id)

    new_base_type = body.base_type if body.base_type is not None else cc.base_type
    new_base_config = (body.base_config if body.base_config is not None
                        else secrets.decrypt_config(cc.base_config or {}, connectors.secret_field_names(cc.base_type)))
    new_locked = body.locked_fields if body.locked_fields is not None else (cc.locked_fields or [])
    try:
        validate_custom_connector_def(new_base_type, new_base_config, new_locked)
    except CustomConnectorError as e:
        raise HTTPException(400, str(e))

    if body.key is not None and body.key != cc.key:
        dupe = (await db.execute(
            select(CustomConnector).where(CustomConnector.org_id == current_user.org_id,
                                           CustomConnector.key == body.key, CustomConnector.id != cc.id)
        )).scalar_one_or_none()
        if dupe is not None:
            raise HTTPException(409, f"A custom connector with key '{body.key}' already exists")
        cc.key = body.key
    if body.label is not None:
        cc.label = body.label
    cc.base_type = new_base_type
    cc.base_config = secrets.encrypt_config(new_base_config, connectors.secret_field_names(new_base_type))
    cc.locked_fields = new_locked
    flag_modified(cc, "base_config")
    await db.commit()
    await db.refresh(cc)
    return _redacted(cc)


@router.delete("/{cc_id}", status_code=204)
async def delete_custom_connector(cc_id: int, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_org_admin)):
    cc = await _owned_or_404(db, cc_id, current_user.org_id)
    count = (await db.execute(
        select(func.count()).select_from(DataSource).where(DataSource.custom_connector_id == cc.id)
    )).scalar_one()
    if count:
        raise HTTPException(409, f"{count} connection(s) still use this preset; update or delete them first")
    await db.delete(cc)
    await db.commit()
```

- [ ] **Step 3: Register the router**

In `backend/app/main.py`, add `custom_connectors` to the existing import
line (line 15, alongside `data_sources`):

```python
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources, custom_connectors, auth, admin, relationships, demo, notifications, shared, widget_templates, platform, sso, metadata, embed, report_copilot
```

And add, near the other `include_router` calls (alongside line 497's
`app.include_router(data_sources.router, prefix="/api/v1")`):

```python
app.include_router(custom_connectors.router, prefix="/api/v1")
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pytest tests/test_custom_connectors.py -v`. Expected: PASS (20 tests
total for this file so far).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/custom_connectors.py backend/app/main.py backend/tests/test_custom_connectors.py
git commit -m "feat: add org-admin CRUD API for custom connector presets"
```

---

### Task 6: Wire presets into `DataSource` create/update

**Files:**
- Modify: `backend/app/routers/data_sources.py` (imports; `_redacted`;
  `create_data_source`; `update_data_source`; `list_connectors`;
  `list_data_sources`; `get_data_source`)
- Test: `backend/tests/test_data_sources_custom_connector.py` (new)

**Interfaces:**
- Consumes: `apply_preset_locks` (Task 3), `CustomConnector` model (Task 1),
  `catalog_payload(custom_connectors=...)` (Task 4).
- Produces: the org-scoped preset-resolution behavior other tests and the
  frontend (Task 9) depend on.

This is the security-load-bearing task: a preset lookup that is not scoped
to `current_user.org_id` in the same query would let one org attach, and
see the locked values of, another org's preset.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_data_sources_custom_connector.py`:

```python
from sqlalchemy import select

from app.models.models import CustomConnector, DataSource


async def _seed_preset(db_session, org_id, *, base_config=None, locked_fields=None):
    cc = CustomConnector(org_id=org_id, key="acme-pg", label="Acme Postgres", base_type="postgresql",
                          base_config=base_config or {"host": "acme-prod.internal", "port": 5432},
                          locked_fields=locked_fields if locked_fields is not None else ["host"])
    db_session.add(cc)
    await db_session.commit()
    await db_session.refresh(cc)
    return cc


class TestCreateFromPreset:
    async def test_locked_field_overrides_client_supplied_value(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)

        resp = await client.post("/api/v1/data-sources", headers=auth_headers["a"], json={
            "name": "Via preset", "type": "ignored-should-not-matter",
            "custom_connector_id": preset.id, "config": {"host": "attacker-supplied", "user": "alice"},
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "postgresql"
        assert body["custom_connector_id"] == preset.id
        assert body["custom_connector_label"] == "Acme Postgres"
        result = await db_session.execute(select(DataSource).where(DataSource.id == body["id"]))
        ds = result.scalar_one()
        assert ds.config["host"] == "acme-prod.internal"
        assert ds.config["user"] == "alice"

    async def test_cross_org_preset_id_is_rejected_and_does_not_leak_base_config(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)

        resp = await client.post("/api/v1/data-sources", headers=auth_headers["b"], json={
            "name": "Hijack attempt", "type": "postgresql", "custom_connector_id": preset.id, "config": {},
        })

        assert resp.status_code == 404
        assert "acme-prod.internal" not in resp.text

    async def test_non_locked_preset_value_is_a_default_only(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id, locked_fields=[])

        resp = await client.post("/api/v1/data-sources", headers=auth_headers["a"], json={
            "name": "Custom port", "type": "postgresql",
            "custom_connector_id": preset.id, "config": {"port": 9999},
        })

        result = await db_session.execute(select(DataSource).where(DataSource.id == resp.json()["id"]))
        assert result.scalar_one().config["port"] == 9999


class TestUpdateWithPreset:
    async def test_omitting_custom_connector_id_still_reapplies_existing_locks(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)
        ds = DataSource(name="Via preset", type="postgresql", config={"host": "acme-prod.internal", "user": "alice"},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=preset.id)
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        resp = await client.put(f"/api/v1/data-sources/{ds.id}", headers=auth_headers["a"], json={
            "config": {"host": "attacker-supplied", "user": "bob"},
        })

        assert resp.status_code == 200
        result = await db_session.execute(select(DataSource).where(DataSource.id == ds.id))
        refreshed = result.scalar_one()
        assert refreshed.config["host"] == "acme-prod.internal"
        assert refreshed.config["user"] == "bob"

    async def test_switching_to_a_cross_org_preset_is_rejected(self, client, db_session, two_orgs, auth_headers):
        preset_b = await _seed_preset(db_session, two_orgs["b"]["org"].id)
        ds = DataSource(name="A's connection", type="postgresql", config={}, org_id=two_orgs["a"]["org"].id)
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        resp = await client.put(f"/api/v1/data-sources/{ds.id}", headers=auth_headers["a"], json={
            "custom_connector_id": preset_b.id,
        })

        assert resp.status_code == 404


class TestListConnectorsIncludesOrgPresets:
    async def test_catalog_includes_the_callers_org_preset(self, client, db_session, two_orgs, auth_headers):
        await _seed_preset(db_session, two_orgs["a"]["org"].id)

        resp = await client.get("/api/v1/data-sources/connectors", headers=auth_headers["a"])

        assert any(t.get("is_custom") for t in resp.json())

    async def test_catalog_excludes_other_orgs_presets(self, client, db_session, two_orgs, auth_headers):
        await _seed_preset(db_session, two_orgs["b"]["org"].id)

        resp = await client.get("/api/v1/data-sources/connectors", headers=auth_headers["a"])

        assert not any(t.get("is_custom") for t in resp.json())
```

Run: `pytest tests/test_data_sources_custom_connector.py -v`. Expected: FAIL
— `custom_connector_id` isn't understood by the create/update endpoints yet.

- [ ] **Step 2: Implement the router changes**

In `backend/app/routers/data_sources.py`:

Add to the imports (line 15 and line 18):

```python
from ..services import connectors, secrets
from ..services.custom_connectors import apply_preset_locks
```

```python
from ..models.models import CustomConnector, DataSource, Dataset, DatasetColumn, User
```

Replace `_redacted` (lines 27-33) to accept an optional label, and update
its one pre-existing caller pattern (every call site below is updated to
pass the label it looked up):

```python
def _redacted(ds: DataSource, custom_connector_label: str | None = None) -> DataSourceOut:
    """A DataSourceOut whose secret config fields are the redaction sentinel, so
    ciphertext never leaves the server. Built as a fresh response model rather than by
    mutating the ORM row, so the stored (encrypted) config is never touched."""
    out = DataSourceOut.model_validate(ds)
    out.config = secrets.redact_config(ds.config or {}, connectors.secret_field_names(ds.type))
    out.custom_connector_label = custom_connector_label
    return out


async def _label_for(db: AsyncSession, ds: DataSource) -> str | None:
    if ds.custom_connector_id is None:
        return None
    return (await db.execute(
        select(CustomConnector.label).where(CustomConnector.id == ds.custom_connector_id)
    )).scalar_one_or_none()
```

Replace `list_data_sources` (lines 90-99):

```python
@router.get("", response_model=list[DataSourceOut])
async def list_data_sources(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(DataSource).where(DataSource.org_id == current_user.org_id).order_by(DataSource.created_at.desc())
    )
    sources = list(result.scalars().all())
    visible = await _visible_source_ids(db, current_user)
    if visible is not None:
        sources = [ds for ds in sources if ds.id in visible]
    cc_ids = {ds.custom_connector_id for ds in sources if ds.custom_connector_id is not None}
    labels: dict[int, str] = {}
    if cc_ids:
        rows = (await db.execute(
            select(CustomConnector.id, CustomConnector.label).where(CustomConnector.id.in_(cc_ids))
        )).all()
        labels = {i: lbl for i, lbl in rows}
    return [_redacted(ds, labels.get(ds.custom_connector_id)) for ds in sources]
```

Replace `create_data_source` (lines 102-111):

```python
@router.post("", response_model=DataSourceOut)
async def create_data_source(body: DataSourceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    preset = None
    if body.custom_connector_id is not None:
        preset = (await db.execute(
            select(CustomConnector).where(CustomConnector.id == body.custom_connector_id,
                                           CustomConnector.org_id == current_user.org_id)
        )).scalar_one_or_none()
        if preset is None:
            raise HTTPException(404, "Custom connector not found")
        ds_type = preset.base_type
    else:
        ds_type = body.type
    _require_known_connector(ds_type)
    config = apply_preset_locks(body.config or {}, preset) if preset is not None else (body.config or {})
    config = secrets.encrypt_config(config, connectors.secret_field_names(ds_type))
    ds = DataSource(name=body.name, type=ds_type, config=config,
                    custom_connector_id=(preset.id if preset else None),
                    org_id=current_user.org_id, created_by=current_user.id)
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return _redacted(ds, preset.label if preset else None)
```

Replace `list_connectors` (lines 114-119):

```python
@router.get("/connectors")
async def list_connectors(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The connector catalog for the connection UI — labels, icons, categories and
    per-connector config-field specs, plus this org's custom connector presets.
    The single source of truth the frontend renders from. No secrets, no dialects."""
    presets = (await db.execute(
        select(CustomConnector).where(CustomConnector.org_id == current_user.org_id)
    )).scalars().all()
    return connectors.catalog_payload(presets)
```

Replace `get_data_source` (lines 127-134):

```python
@router.get("/{ds_id}", response_model=DataSourceOut)
async def get_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    visible = await _visible_source_ids(db, current_user)
    if visible is not None and ds.id not in visible:
        raise HTTPException(404, "Data source not found")
    return _redacted(ds, await _label_for(db, ds))
```

Replace `update_data_source` (lines 137-162):

```python
@router.put("/{ds_id}", response_model=DataSourceOut)
async def update_data_source(ds_id: int, body: DataSourceUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    await _administrable_or_404(ds, db, current_user)
    if body.name is not None:
        ds.name = body.name

    preset = None
    if body.custom_connector_id is not None:
        preset = (await db.execute(
            select(CustomConnector).where(CustomConnector.id == body.custom_connector_id,
                                           CustomConnector.org_id == current_user.org_id)
        )).scalar_one_or_none()
        if preset is None:
            raise HTTPException(404, "Custom connector not found")
        ds.type = preset.base_type
        ds.custom_connector_id = preset.id
    elif body.type is not None:
        _require_known_connector(body.type)
        ds.type = body.type

    if preset is None and ds.custom_connector_id is not None:
        # No new preset was supplied, but one is already attached -- its locks
        # must still apply to whatever config ends up stored below.
        preset = await db.get(CustomConnector, ds.custom_connector_id)

    if body.config is not None or preset is not None:
        secret_names = connectors.secret_field_names(ds.type)
        stored = ds.config or {}
        if body.config is not None:
            # A secret field sent back as the redaction sentinel means "unchanged" — keep the
            # stored (encrypted) value; anything else is a new secret to encrypt.
            merged = dict(body.config)
            for name in secret_names:
                if merged.get(name) == secrets.REDACTED:
                    merged[name] = stored.get(name)
        else:
            merged = secrets.decrypt_config(stored, secret_names)
        if preset is not None:
            merged = apply_preset_locks(merged, preset)
        ds.config = secrets.encrypt_config(merged, secret_names)
        flag_modified(ds, 'config')

    if body.cache_ttl_seconds is not None:
        ds.cache_ttl_seconds = body.cache_ttl_seconds
    await db.commit()
    await db.refresh(ds)
    return _redacted(ds, await _label_for(db, ds))
```

- [ ] **Step 3: Run the tests, verify they pass**

Run: `pytest tests/test_data_sources_custom_connector.py
tests/test_data_sources_org_scoping.py tests/test_data_source_secrets.py
tests/test_data_source_cache_ttl.py -v` — the last three are the existing
`data_sources.py` test files, run alongside the new one specifically
because this task rewrites every function in that router; a regression in
`_redacted`'s new signature or in the unrelated `cache_ttl_seconds`/secret-
redaction paths would show up there, not in the new file. Expected: PASS,
all files.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/data_sources.py backend/tests/test_data_sources_custom_connector.py
git commit -m "feat: wire custom connector presets into DataSource create/update"
```

---

### Task 7: Frontend — API types and client functions

**Files:**
- Modify: `frontend/src/services/api.ts` (`DataSource`, `ConnectorSpec`
  interfaces around lines 1296-1314; `dataSourcesApi.create`/`.update`
  around lines 1319-1322; new `customConnectorsApi` export)

**Interfaces:**
- Produces: `CustomConnector` type, `customConnectorsApi.{list,create,update,delete}`,
  extended `DataSource`/`ConnectorSpec`/`dataSourcesApi.create`/`.update` —
  consumed by Tasks 8 and 9.

- [ ] **Step 1: Extend `DataSource` and `ConnectorSpec`, add `CustomConnector`**

Replace the `DataSource` interface (lines 1296-1303):

```typescript
export interface DataSource {
  id: number
  name: string
  type: string
  config: Record<string, unknown>
  created_at: string
  custom_connector_id: number | null
  custom_connector_label: string | null
}

export interface CustomConnector {
  id: number
  key: string
  label: string
  base_type: string
  base_config: Record<string, unknown>
  locked_fields: string[]
  created_at: string
}
```

Replace `ConnectorSpec` (lines 1310-1314):

```typescript
export interface ConnectorSpec {
  key: string; label: string; icon: string; category: string
  default_port: number | null; driver_installed: boolean; supports_directquery: boolean
  config_fields: ConnectorConfigField[]
  is_custom?: boolean
  base_type?: string
  custom_connector_id?: number
}
```

- [ ] **Step 2: Extend `dataSourcesApi.create`/`.update`, add `customConnectorsApi`**

Replace the `create`/`update` lines inside `dataSourcesApi` (lines 1319-1322):

```typescript
  create:  (body: { name: string; type: string; config: Record<string, unknown>; custom_connector_id?: number | null }) =>
    api.post<DataSource>('/data-sources', body).then(r => r.data),
  update:  (id: number, body: Partial<{ name: string; type: string; config: Record<string, unknown>; custom_connector_id: number | null }>) =>
    api.put<DataSource>(`/data-sources/${id}`, body).then(r => r.data),
```

Immediately after the `dataSourcesApi` object's closing `}`, add:

```typescript
export const customConnectorsApi = {
  list:   () => api.get<CustomConnector[]>('/custom-connectors').then(r => r.data),
  create: (body: { key: string; label: string; base_type: string; base_config: Record<string, unknown>; locked_fields: string[] }) =>
    api.post<CustomConnector>('/custom-connectors', body).then(r => r.data),
  update: (id: number, body: Partial<{ key: string; label: string; base_type: string; base_config: Record<string, unknown>; locked_fields: string[] }>) =>
    api.put<CustomConnector>(`/custom-connectors/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/custom-connectors/${id}`),
}
```

- [ ] **Step 3: Verify the frontend still typechecks**

Run: `npx tsc --noEmit` from `frontend/`. Expected: no new errors (existing
call sites of `dataSourcesApi.create`/`.update` already only pass the
previously-required fields, which remain valid since the new field is
optional).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add custom connector API types and client functions"
```

---

### Task 8: Frontend — admin management page

**Files:**
- Create: `frontend/src/pages/admin/AdminCustomConnectors.tsx`
- Create: `frontend/src/pages/admin/AdminCustomConnectors.test.tsx`
- Modify: `frontend/src/App.tsx` (lazy import + route, alongside `AdminRoles`)
- Modify: `frontend/src/components/navigation.ts` (new nav entry)

**Interfaces:**
- Consumes: `customConnectorsApi`, `dataSourcesApi.connectors` (for the
  base-type picker and its `config_fields`), `CustomConnector`,
  `ConnectorSpec` (Task 7); `useConfirm`, `useModalDialog`, `EmptyState`,
  `LoadError`, `LoadingState` (existing, used identically to
  `AdminRoles.tsx`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/admin/AdminCustomConnectors.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AdminCustomConnectors from './AdminCustomConnectors'
import { customConnectorsApi, dataSourcesApi } from '../../services/api'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'

vi.mock('../../services/api', () => ({
  customConnectorsApi: {
    list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(),
  },
  dataSourcesApi: { connectors: vi.fn() },
}))

const BASE_CATALOG = [{
  key: 'postgresql', label: 'PostgreSQL', icon: '🐘', category: 'SQL',
  default_port: 5432, driver_installed: true, supports_directquery: true,
  config_fields: [
    { name: 'host', label: 'Host', kind: 'text', required: true, default: null, placeholder: '', options: [], secret: false, show_if: null },
    { name: 'port', label: 'Port', kind: 'number', required: false, default: 5432, placeholder: '', options: [], secret: false, show_if: null },
  ],
}]

function renderPage() {
  return render(<ConfirmProvider><AdminCustomConnectors /></ConfirmProvider>)
}

describe('AdminCustomConnectors', () => {
  beforeEach(() => {
    vi.mocked(dataSourcesApi.connectors).mockResolvedValue(BASE_CATALOG as any)
  })

  it('lists existing presets', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([
      { id: 1, key: 'acme-pg', label: 'Acme Postgres', base_type: 'postgresql',
        base_config: { host: '***REDACTED***' }, locked_fields: ['host'], created_at: '2026-01-01' },
    ])

    renderPage()

    expect(await screen.findByText('Acme Postgres')).toBeInTheDocument()
  })

  it('shows an empty state when there are no presets', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([])

    renderPage()

    expect(await screen.findByText(/no custom connectors/i)).toBeInTheDocument()
  })

  it('deletes a preset after confirming', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([
      { id: 1, key: 'acme-pg', label: 'Acme Postgres', base_type: 'postgresql',
        base_config: {}, locked_fields: [], created_at: '2026-01-01' },
    ])
    vi.mocked(customConnectorsApi.delete).mockResolvedValue(undefined as any)

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /delete/i }))
    // ConfirmDialog's own confirm button defaults to "Delete" too (see
    // ConfirmDialog.tsx's `confirmLabel ?? 'Delete'`) -- findAllByRole avoids
    // ambiguity between the row's button and the dialog's once both exist.
    const deleteButtons = await screen.findAllByRole('button', { name: /delete/i })
    fireEvent.click(deleteButtons[deleteButtons.length - 1])

    await waitFor(() => expect(customConnectorsApi.delete).toHaveBeenCalledWith(1))
  })
})
```

Run: `npx vitest run src/pages/admin/AdminCustomConnectors.test.tsx`.
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 2: Implement the page**

Create `frontend/src/pages/admin/AdminCustomConnectors.tsx`, following
`AdminRoles.tsx`'s exact list/modal/delete-confirm structure:

```tsx
import { useEffect, useState } from 'react'
import { Plug } from 'lucide-react'
import { customConnectorsApi, dataSourcesApi } from '../../services/api'
import type { CustomConnector, ConnectorSpec } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useModalDialog } from '../../components/ui/useModalDialog'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

function PresetModal({ initial, catalog, onSave, onClose }: {
  initial?: CustomConnector | null
  catalog: ConnectorSpec[]
  onSave: (cc: CustomConnector) => void
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [key, setKey] = useState(initial?.key ?? '')
  const [label, setLabel] = useState(initial?.label ?? '')
  const [baseType, setBaseType] = useState(initial?.base_type ?? catalog[0]?.key ?? '')
  const [values, setValues] = useState<Record<string, unknown>>(initial?.base_config ?? {})
  const [locked, setLocked] = useState<Set<string>>(new Set(initial?.locked_fields ?? []))
  const [saving, setSaving] = useState(false)

  const spec = catalog.find(s => s.key === baseType)
  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const toggleLocked = (name: string) => setLocked(prev => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  const handleSave = async () => {
    if (!key.trim() || !label.trim()) { toast.error('Key and label are required'); return }
    setSaving(true)
    try {
      const body = { key, label, base_type: baseType, base_config: values, locked_fields: [...locked] }
      const result = isEdit ? await customConnectorsApi.update(initial!.id, body) : await customConnectorsApi.create(body)
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Custom connector created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={isEdit ? 'Edit custom connector' : 'New custom connector'}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Custom Connector' : 'New Custom Connector'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Label *</div>
          <input value={label} onChange={e => setLabel(e.target.value)} placeholder="Acme Snowflake" {...inp} />
        </label>
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Key *</div>
          <input value={key} onChange={e => setKey(e.target.value)} placeholder="acme-snowflake" {...inp} disabled={isEdit} />
        </label>
        <label style={{ display: 'block', marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Base connector type</div>
          <select value={baseType} onChange={e => { setBaseType(e.target.value); setValues({}); setLocked(new Set()) }} {...inp} disabled={isEdit}>
            {catalog.filter(s => !s.is_custom).map(s => <option key={s.key} value={s.key}>{s.icon} {s.label}</option>)}
          </select>
        </label>

        {spec?.config_fields.map(f => (
          <div key={f.name} style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginBottom: 10 }}>
            <label style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{f.label}</div>
              <input value={(values[f.name] as string) ?? ''} onChange={e => setValues(p => ({ ...p, [f.name]: e.target.value }))}
                type={f.kind === 'password' ? 'password' : 'text'} {...inp} />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)', paddingBottom: 6 }}>
              <input type="checkbox" checked={locked.has(f.name)} onChange={() => toggleLocked(f.name)} />
              Locked
            </label>
          </div>
        ))}

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminCustomConnectors() {
  const [presets, setPresets] = useState<CustomConnector[]>([])
  const [catalog, setCatalog] = useState<ConnectorSpec[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal, setModal] = useState<'add' | CustomConnector | null>(null)

  const load = () => {
    setLoadError(null)
    return Promise.all([customConnectorsApi.list(), dataSourcesApi.connectors()])
      .then(([p, c]) => { setPresets(p); setCatalog(c) })
      .catch(setLoadError)
  }

  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const handleSaved = (cc: CustomConnector) => {
    setPresets(prev => {
      const idx = prev.findIndex(x => x.id === cc.id)
      return idx >= 0 ? prev.map(x => x.id === cc.id ? cc : x) : [cc, ...prev]
    })
    setModal(null)
  }

  const confirm = useConfirm()
  const handleDelete = async (cc: CustomConnector) => {
    if (!await confirm({ title: `Delete "${cc.label}"?`, body: 'Connections using this preset must be updated or removed first.' })) return
    try {
      await customConnectorsApi.delete(cc.id)
      setPresets(prev => prev.filter(x => x.id !== cc.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Custom Connectors</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')}>+ New Custom Connector</button>
      </div>

      {loading && <LoadingState />}
      {!loading && loadError != null && (
        <LoadError what="custom connectors" error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}
      {!loading && loadError == null && presets.length === 0 && (
        <EmptyState icon={Plug} title="No custom connectors yet"
          description="Create a sanctioned, pre-configured preset of a connector type for the rest of your org to use." />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {presets.map(cc => (
          <div key={cc.id} style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{cc.label}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>{cc.base_type} · {cc.locked_fields.length} locked field(s)</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(cc)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(cc)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <PresetModal initial={modal === 'add' ? null : modal} catalog={catalog} onSave={handleSaved} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Register the route and nav entry**

In `frontend/src/App.tsx`, add alongside the other admin lazy imports
(near line 26):

```typescript
const AdminCustomConnectors = lazy(() => import('./pages/admin/AdminCustomConnectors'))
```

And alongside the other `RequireAdmin`-wrapped routes (near line 94):

```tsx
<Route path="admin/custom-connectors" element={<AdminCustomConnectors />} />
```

In `frontend/src/components/navigation.ts`, in the `'Admin'` section's
`items` array, immediately after the `'/admin/api-keys'` entry:

```typescript
      { to: '/admin/custom-connectors', label: 'Custom connectors', icon: Plug, permission: 'org_admin' },
```

(`Plug` is already imported at the top of `navigation.ts`.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `npx vitest run src/pages/admin/AdminCustomConnectors.test.tsx`.
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/AdminCustomConnectors.tsx frontend/src/pages/admin/AdminCustomConnectors.test.tsx frontend/src/App.tsx frontend/src/components/navigation.ts
git commit -m "feat: add admin custom connectors management page"
```

---

### Task 9: Frontend — preset tiles in the connection catalog

**Files:**
- Modify: `frontend/src/pages/Connections.tsx` (`ConnectionModal`'s
  `handleSave`, lines 77-89; the two `TYPE_LABEL[ds.type]` render sites,
  lines 253 and 474)
- Test: `frontend/src/pages/Connections.test.tsx` (extend if it exists;
  otherwise this step is skipped and covered by Task 8's page-level test
  plus the manual verification in Step 3 below — check for the file's
  existence before writing a new one, to avoid duplicating an existing
  suite's setup)

**Interfaces:**
- Consumes: `spec.is_custom`, `spec.base_type`, `spec.custom_connector_id`
  (Task 7's extended `ConnectorSpec`); `DataSource.custom_connector_label`
  (Task 7).

- [ ] **Step 1: Update `handleSave` to resolve the real type for a custom tile**

`type` (component state) holds whatever catalog `key` the user picked —
for a custom tile this is the synthetic `"custom:<id>"` key `catalog_payload`
now emits (Task 4), never a real `connectors.py` key. Replace
`handleSave` (`frontend/src/pages/Connections.tsx:77-89`):

```typescript
  const handleSave = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const submitType = spec?.is_custom ? spec.base_type! : type
      const customConnectorId = spec?.is_custom ? spec.custom_connector_id : undefined
      const result = isEdit
        ? await dataSourcesApi.update(initial!.id, { name, type: submitType, custom_connector_id: customConnectorId, config: cfg })
        : await dataSourcesApi.create({ name, type: submitType, custom_connector_id: customConnectorId, config: cfg })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Connection created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }
```

- [ ] **Step 2: Show the preset label in the connections list and detail header**

Replace line 474 (inside the list row):

```tsx
                  {TYPE_LABEL[ds.type]}
                  {ds.custom_connector_label ? ` · ${ds.custom_connector_label}` : ''}
```

Replace line 253 (inside the detail header):

```tsx
            <div style={{ fontSize: 11, color: 'var(--muted)' }}>
              {TYPE_LABEL[ds.type]}{ds.custom_connector_label ? ` · ${ds.custom_connector_label}` : ''}
            </div>
```

- [ ] **Step 3: Manually verify in the running app**

Per the `run` skill: `docker compose up -d` from
`AI_data_tool/data_analytics`, log in as an org admin, create a custom
connector preset at `/admin/custom-connectors` with one locked field, then
open Connections → New Connection and confirm the preset appears grouped
under "Custom", that its locked field does not appear in the form, and that
the created connection's list row shows the preset's label. This is a UI
integration point `tsc`/unit tests cannot fully confirm (the `<select>`'s
grouped rendering and the real round trip through the running backend).

- [ ] **Step 4: Run the full frontend suite**

Run: `npx vitest run` from `frontend/`. Expected: no regressions (existing
`Connections.test.tsx`, if present, still passes — `spec?.is_custom` is
`undefined` for every ordinary catalog entry, so `submitType` falls back to
`type` exactly as before for every non-custom flow).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Connections.tsx
git commit -m "feat: support creating connections from custom connector presets"
```

---

## Final Verification

After all tasks are complete:

1. Full backend suite (Docker container, per `backend-test-interpreter`):
   confirm 0 failures and that the new file count matches
   `test_architecture_doc.py`'s derived expectations (it recomputes counts
   from the tree — no hardcoded number to update by hand, but a stale
   doc claim elsewhere in `ARCHITECTURE.md`/`.html` about "the connector
   registry has no DB dependency" or router-module counts should be
   re-checked against the real, current tree the way past merges in this
   project have needed to).
2. Full frontend suite (`npx vitest run` and `npx tsc --noEmit`).
3. Re-read the spec's "Testing plan" section end to end and confirm every
   bullet has a corresponding test in this plan's tasks — if a gap turns
   up, add it before considering the branch done.
