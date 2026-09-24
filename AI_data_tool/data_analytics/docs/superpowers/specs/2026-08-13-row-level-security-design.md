# Row-Level Security (Multi-Tenant Auth Foundation)

**Date:** 2026-08-13
**Status:** Phase 2 (Row-Level Security) Complete

## Overview

This app currently has **no authentication and no multi-tenancy at all** — every router in `backend/app/routers/` is unauthenticated, and `Dataset`/`Report`/`DataSource` are global, visible to anyone who can reach the API. This spec adds:

1. **Multi-tenant isolation** — separate organizations, each with their own datasets/reports/data sources, never visible to another organization.
2. **Row-level security within an organization** — individual users (via their assigned role) can be further restricted to a filtered subset of rows within a dataset their org owns, e.g. a regional manager sees only their region's rows.

Both are needed: org isolation is the outer boundary (hard, all-or-nothing), row-level security is the inner one (per-role, per-dataset, expression-based).

This is sub-project 1 of `docs/superpowers/specs/2026-08-13-platform-roadmap.md`'s remaining-work roadmap — the only one not sourced from the SAS VA course transcripts, requested directly and prioritized first because every later sub-project on that roadmap (sharing/permissions, alerts recipients, viewer capabilities) assumes a user system already exists.

## Current State

- `backend/app/models/models.py`: `Dataset`, `DatasetColumn`, `AnalysisResult`, `Report`, `ReportPage`, `ReportWidget`, `HierarchyNode`, `DataSource` — none scoped to any owner.
- `backend/app/core/database.py`: async SQLAlchemy (`postgresql+asyncpg`), no migration framework — `main.py` calls `Base.metadata.create_all` on startup, which creates missing tables but cannot alter existing ones.
- `backend/app/core/config.py`: already has an unused `secret_key` setting — reused here for JWT signing, no new secret to provision.
- `backend/app/services/widget_data.py`: already has a working, tested filter-expression engine — `apply_filter_expr(df, expr, silent=True)` (row `AND`/`OR`/`NOT`/comparison filtering) and `_eval_expr` (the underlying `df.eval()`-or-safe-Python-eval evaluator). This is reused directly for row-level security rather than building a second filter mechanism.
- `backend/requirements.txt`: no auth-related packages at all (`passlib`, `python-jose`/`pyjwt`, etc. all absent).

## Data Model

Four new tables, plus one new column on three existing tables. Follows the existing `models.py` conventions (explicit `Column`/`relationship`, `datetime.utcnow` defaults, `ondelete` cascades).

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
    is_org_admin = Column(Boolean, nullable=False, default=False)   # bypasses all RowSecurityRules for this org
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="roles")
    users        = relationship("User", back_populates="role")
    rules        = relationship("RowSecurityRule", back_populates="role", cascade="all, delete-orphan")


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
    role         = relationship("Role", back_populates="users")   # current_user.role.is_org_admin drives RLS bypass


class RowSecurityRule(Base):
    __tablename__ = "row_security_rules"
    id          = Column(Integer, primary_key=True)
    role_id     = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    filter_expr = Column(Text, nullable=False)   # same expression syntax as widget/calculated-column filters
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("role_id", "dataset_id", name="uq_role_dataset_rule"),)

    role    = relationship("Role", back_populates="rules")
    dataset = relationship("Dataset")
```

`Dataset`, `Report`, `DataSource` each gain:
```python
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
```

`ReportPage`, `ReportWidget`, `HierarchyNode`, `DatasetColumn` are **not** given their own `org_id` — they're only ever reached through their org-scoped parent (`Report`/`Dataset`), so the org check happens once at the parent lookup, not repeated at every child level.

Email is globally unique (not unique-per-org) — a user belongs to exactly one org, and this app has no cross-org user concept in v1 (no self-service signup, no SSO).

## Auth Flow

- **Password hashing:** `passlib[bcrypt]` (new dependency).
- **Tokens:** JWT (`python-jose[cryptography]`, new dependency), signed with `settings.secret_key`. Payload: `{"sub": user.id, "org_id": user.org_id, "exp": ...}`. A single long-lived access token (7 days) — no refresh-token flow in v1; re-login after expiry is an acceptable v1 trade-off given this isn't a consumer-facing product.
- **`POST /auth/login`** — body `{email, password}`, verifies against `password_hash`, returns `{access_token, token_type: "bearer"}`. Generic "invalid email or password" error on any failure (wrong password, unknown email, or `is_active=False`) — never reveals which.
- **`GET /auth/me`** — returns the current user's `id`/`email`/`org_id`/`role` (name + `is_org_admin`), for the frontend to render "who am I."
- **`get_current_user` dependency** — decodes the bearer token, then re-fetches the `User` row from the DB on every request (not just trusting JWT claims) so a deactivated user or a role reassignment takes effect on their very next request, not after token expiry. Raises 401 on missing/invalid/expired token or `is_active=False`.
- Every existing router gains `current_user: User = Depends(get_current_user)`.

## Org Scoping Enforcement

Every list/get/create/update/delete endpoint on `datasets`, `reports`, `data_sources`, `hierarchy`, `widget_data`, `analysis` filters or validates against `current_user.org_id`:
- List endpoints: `WHERE org_id = current_user.org_id`.
- Get/update/delete by ID: load the row, then `if row.org_id != current_user.org_id: raise HTTPException(404)` — **404, not 403**, so a user can't distinguish "doesn't exist" from "exists but isn't yours."
- Create endpoints: set `org_id = current_user.org_id` server-side, ignoring any client-supplied value.

## Row-Level Security Enforcement

`get_widget_data(file_path, config, widget_type, calculated_columns, filter_expr)` in `backend/app/services/widget_data.py` gains a `current_user: User` parameter (threaded from the router through `get_widget_data_from_df`'s caller). Before any other filtering:

```python
if not current_user.role.is_org_admin:
    rule = <look up RowSecurityRule for (current_user.role_id, dataset_id)>
    if rule:
        df = apply_filter_expr(df, rule.filter_expr, silent=True)
```

This runs **before** `apply_filter_expr(df, filter_expr, silent=True)` (the widget's own report-level filter) and before `apply_calculated_columns`. Ordering matters: the RLS rule is an unconditional floor — a widget's own filters and calculated columns can narrow the result further, but nothing downstream of this point can see rows the RLS rule already excluded. `silent=True` is deliberate (matches the existing report-level filter's own behavior): a malformed RLS rule degrades to "no rule applied" rather than 500ing every widget in the report, and rule validity is checked at admin-authoring time (see API surface below), not at every query.

No rule for `(role, dataset)` means "unrestricted within the org" — not "no access." Access to the dataset at all is still gated by org scoping above.

## API Surface (new)

- `POST /auth/login`, `GET /auth/me`
- `GET/POST /admin/roles`, `PATCH/DELETE /admin/roles/{id}` — org-admin-only (`current_user.role.is_org_admin`), scoped to `current_user.org_id`.
- `GET/POST /admin/users`, `PATCH/DELETE /admin/users/{id}` — org-admin-only, scoped to `current_user.org_id`. Create requires `email`, `password`, `role_id` (must belong to the same org).
- `GET/POST /admin/row-security-rules`, `PATCH/DELETE /admin/row-security-rules/{id}` — org-admin-only. Create/update validates `filter_expr` by running `apply_filter_expr` against a sample of the target dataset and surfacing any error immediately, rather than letting a broken rule silently no-op for every affected user later.

## Migrations

**Correction from the originally-approved design:** this section initially proposed introducing Alembic. Reading `backend/app/main.py` while writing the implementation plan showed the codebase already has a working, established migration convention that Alembic would duplicate rather than improve: a `_migrate(conn)` function in `main.py`'s `lifespan` handler that runs idempotent raw `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements on every startup, after `Base.metadata.create_all` creates any brand-new tables. Every prior schema change in this project (columns added to `report_pages`, `datasets`, `reports`) went through this pattern, not a migration framework. Per this project's own "follow existing patterns" norm, this spec now follows it too rather than introducing Alembic as new, redundant machinery:

1. `Base.metadata.create_all` picks up the four brand-new tables (`organizations`, `roles`, `users`, `row_security_rules`) automatically — no manual step needed, exactly like every other new table this project has added.
2. `_migrate(conn)` gains three new statements: `ALTER TABLE datasets ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE` (and the same for `reports`, `data_sources`) — added nullable, matching the existing style (none of the current `_migrate` statements add `NOT NULL` columns to tables that may already have rows).
3. A backfill step runs once, also inside `lifespan`, after `_migrate`: if no `Organization` row exists yet, create a "Default Organization" and a matching `is_org_admin=True` "Admin" `Role`, then `UPDATE datasets/reports/data_sources SET org_id = :default_org_id WHERE org_id IS NULL`. This is idempotent (guarded by "no `Organization` row exists yet") exactly like the rest of `lifespan`'s startup migration.
4. `org_id` is enforced `NOT NULL` at the **application layer** (every create endpoint always sets it; org-scoping checks treat a `NULL` as "belongs to no one, so 404" defensively) rather than an actual `NOT NULL` SQL constraint — adding one retroactively on a live table with existing rows needs more ceremony (`ALTER COLUMN ... SET NOT NULL` only succeeds after every row is backfilled, which is a two-step ordering concern this project's simple `_migrate` runner doesn't currently express) and isn't worth introducing for a column that's always backfilled by step 3 before the app is used further.

## Testing

- **Backend (pytest):** password hashing round-trip; login success/failure (wrong password, unknown email, inactive user — all get the same generic error); `get_current_user` accepts a valid token and rejects missing/expired/malformed ones; org-scoping (a user from org A gets 404 on org B's dataset/report/data-source, at each of list/get/update/delete); RLS enforcement (a role with a rule sees only matching rows; `is_org_admin` bypasses the rule entirely; a role with no rule for that dataset sees all org-scoped rows); admin-only endpoints reject non-admin users; `RowSecurityRule` create/update rejects an invalid expression at authoring time.
- **Frontend:** no new component tests planned for Phase 0-2 (backend-only phases); Phase 3 adds minimal coverage for the auth-aware API client's 401-redirect behavior, consistent with this project's existing "diff-based review over exhaustive component tests" convention.

## Explicit v1 Exclusions

- No self-service org signup — orgs and their first admin user are provisioned directly (seed script or an admin-only creation path), not from a public form.
- No SSO/OAuth — email+password only.
- No refresh tokens — single long-lived access token, re-login on expiry.
- One role per user (no many-to-many role assignment).
- No audit log of who viewed what (could be a future addition once this foundation exists).
- No column-level security (hiding entire columns per role) — only row filtering. Column-level restriction is a plausible future extension of the same `RowSecurityRule` idea but isn't part of this spec.

## Rollout (phases — each gets its own implementation plan)

1. **Phase 0 — Auth foundation:** `Organization`/`User`/`Role` models, Alembic setup + initial migration, password hashing, JWT login (`/auth/login`, `/auth/me`), `get_current_user` dependency. Nothing enforces it yet.
2. **Phase 1 — Org scoping:** `org_id` on `Dataset`/`Report`/`DataSource` (migration + backfill), every router enforces `current_user.org_id`.
3. **Phase 2 — Row-level security:** `RowSecurityRule` model + admin CRUD endpoints, enforcement wired into `get_widget_data`'s query path.
4. **Phase 3 — Frontend:** login page, auth-aware API client (attach bearer token, redirect to login on 401), admin screens for managing users/roles/row-security rules.

## Files Changed (representative, grows per phase)

| File | Change |
|---|---|
| `backend/app/models/models.py` | `Organization`, `Role`, `User`, `RowSecurityRule`; `org_id` on `Dataset`/`Report`/`DataSource` |
| `backend/app/core/security.py` | New — password hashing, JWT encode/decode |
| `backend/app/routers/auth.py` | New — `/auth/login`, `/auth/me` |
| `backend/app/routers/admin.py` | New — role/user/row-security-rule CRUD |
| `backend/app/dependencies.py` | New — `get_current_user` |
| `backend/app/routers/*.py` (existing) | Add `current_user` dependency + org-scoping checks |
| `backend/app/services/widget_data.py` | `get_widget_data`/`get_widget_data_from_df` gain `current_user`; RLS rule lookup + application |
| `backend/app/main.py` | `_migrate()` gains `org_id` column statements; `lifespan` gains the default-org/admin-role backfill step |
| `backend/requirements.txt` | `passlib[bcrypt]`, `python-jose[cryptography]` |
| `frontend/src/pages/Login.tsx` | New (Phase 3) |
| `frontend/src/services/api.ts` | Attach bearer token, handle 401 (Phase 3) |
| `frontend/src/pages/Admin/*` | New — user/role/RLS-rule management screens (Phase 3) |
