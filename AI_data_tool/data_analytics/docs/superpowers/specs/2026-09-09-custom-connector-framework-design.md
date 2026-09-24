# Custom connector framework — design

## Context

This is the third Phase 5 ("Extensibility") slice, after custom
calculated-column functions (shipped,
`docs/superpowers/specs/2026-09-08-custom-calc-functions-design.md`). It lets
an org admin define a **named, pre-configured preset of an existing
connector type** — e.g. "Acme Snowflake" as a preset of the built-in
`snowflake` connector, with the account/warehouse/role fields fixed and only
`user`/`password` left for whoever creates a connection from it — so
non-admin users creating a data source pick a sanctioned tile from the
catalog instead of typing in raw host/account details themselves.

Two designs were considered for how a custom preset resolves at runtime:

1. Register each preset as its own dynamic `ConnectorSpec` in
   `connectors.py`'s registry, keyed by a synthetic type string
   (`"custom:<id>"`), refreshed in-memory on every preset write.
2. Keep `DataSource.type` as a real, existing registry key (e.g.
   `"postgresql"`) and record which preset was used, if any, in a separate
   nullable column — so the connector runtime never learns that presets
   exist at all.

Design 2 is what this spec describes. Design 1 would require either
threading org context through `connectors.py`'s ~25 call sites across 8
files (`services/connections.py`, `routers/data_sources.py`,
`services/direct_query.py`, `services/engines.py`, `services/query_builder.py`,
`services/metadata/catalog_sync.py`, `services/secrets.py`,
`services/metadata/sync.py` — none of which take an `org_id` today), or an
in-memory secondary registry kept in sync with the database. The backend
runs a single `uvicorn` process with no `--workers` flag
(`backend/Dockerfile:11`), so an in-memory cache wouldn't hit the classic
multi-worker staleness bug today — but it's still unnecessary machinery
(startup population, invalidation-on-write, a second lookup path) for a
problem Design 2 avoids by construction. It also mirrors this feature's own
sibling precedent directly: `custom_functions.py` expands a custom thing into
existing safe primitives *before* it reaches the runtime, so the runtime
(`_eval_expr`) never knows custom functions exist. Design 2 applies the same
principle here — "custom-ness" is resolved once, at the moment a
`DataSource` is created or edited, never at query time.

## What a preset is

A preset is a named wrapper around one existing `ConnectorSpec` (a
`connectors.py` registry key — "postgresql", "snowflake", etc., what the
approved design calls "named presets from existing url_kinds"). It is not a
new connector type, a new driver, or arbitrary code — nothing changes in
`connectors.py`, `direct_query.py`, `engines.py`, or `query_builder.py`. A
preset supplies fixed values for some of the base type's `config_fields` and
marks a subset of those as **locked** (not editable by whoever creates a
`DataSource` from the preset).

Example: a `snowflake` preset "Acme Snowflake" with `base_config =
{"account": "acme-prod", "warehouse": "ANALYTICS_WH", "role": "READER"}` and
`locked_fields = ["account", "warehouse", "role"]`. A user creating a
`DataSource` from this preset only supplies `user`/`password`; the three
locked fields are forced to the preset's values regardless of what the
client sends.

## Scope & authorization

- **Authoring** (create/update/delete a preset): **org admins only**
  (`Depends(require_org_admin)`, `app/dependencies.py:97-100` — the same
  dependency `data_sources.py:200,213` already uses to gate admin-only
  endpoints). This is a stricter, separate gate from
  `_administrable_or_404`'s creator-or-admin check
  (`data_sources.py:36-62`), which governs editing a `DataSource`, not a
  preset.
- **Using** a preset (creating a `DataSource` from it): any user who can
  already create a `DataSource` in their org — unchanged from today.
- Presets are **org-scoped**: a preset created in org A must never resolve,
  list, or be usable from org B. This is the one property the whole design
  exists to protect, and it is enforced at exactly two points (both detailed
  below): the catalog listing, and `DataSource` create/update.

## Data model

New table, migration `0023_custom_connectors.py` (head is
`0022_dataset_custom_functions`, per `alembic/versions/`):

```python
class CustomConnector(Base):
    __tablename__ = "custom_connectors"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    key           = Column(String(100), nullable=False)   # UI slug, unique per org
    label         = Column(String(255), nullable=False)   # "Acme Snowflake"
    base_type     = Column(String(50), nullable=False)     # a connectors.py registry key
    base_config   = Column(JSON, default=dict)             # {field_name: value}, secrets encrypted
    locked_fields = Column(JSON, default=list)              # subset of base_config's keys
    created_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                            nullable=True, index=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at    = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_custom_connectors_org_key"),)
```

Follows `DataSource`'s own FK conventions exactly (`models.py:256,260`):
`org_id` cascades on org deletion, `created_by` nulls out rather than
blocking on user deletion.

`DataSource` (`app/models/models.py:236-270`) gains one nullable column and
one relationship, added in the same migration:

```python
custom_connector_id = Column(Integer, ForeignKey("custom_connectors.id", ondelete="RESTRICT"),
                              nullable=True, index=True)
custom_connector = relationship("CustomConnector")
```

`DataSource.type` is **never** set to anything but a real `connectors.py`
registry key — a preset-created `DataSource` has `type="snowflake"` and
`custom_connector_id=<preset id>`, both fields populated. Every one of the
~25 existing `connectors.*` call sites (`resolve`, `build_url`,
`connect_args`, `secret_field_names`, `sql_family_of`, ...) keeps calling
`connectors.resolve(ds.type)` etc. exactly as it does today, with zero
changes, because `ds.type` is always a value that API already understands.

**Why `ondelete="RESTRICT"`, not `SET NULL`:** a preset exists to be the
sanctioned, locked-down way to connect to a system. If deleting it silently
turned every `DataSource` that used it into a plain, unlocked connection
(what `SET NULL` would do), that's a governance regression disguised as
cleanup. `RESTRICT` means deleting an in-use preset fails at the database
level; the delete endpoint surfaces this as `409 Conflict` with the count of
`DataSource` rows still referencing it, so an admin must first migrate or
delete those connections before removing the preset.

## Save-time validation (preset create/update)

1. `base_type` must satisfy `connectors.is_known(base_type)` — reuses the
   exact check `data_sources.py`'s `_require_known_connector` already runs
   (`data_sources.py:122-124`).
2. Every key in `base_config` and every entry in `locked_fields` must be one
   of that base type's `config_fields[].name` (from
   `connectors.resolve(base_type).config_fields`) — rejects typos and
   fields that don't exist for the chosen connector type.
3. `locked_fields` must be a subset of `base_config`'s keys — locking a
   field with no fixed value to lock it to is meaningless.
4. `key` must be unique per org (`uq_custom_connectors_org_key`, a 409 on
   collision, not a 500) — it doesn't need to be globally unique, and
   doesn't need to avoid colliding with built-in connector keys, since it is
   never written into `DataSource.type` (see Data model above).
5. Secret fields in `base_config` (`connectors.secret_field_names(base_type)`
   — the identical, type-driven set `DataSource.config` already uses) are
   encrypted with the existing `secrets.encrypt_config`/`decrypt_config`
   (`services/secrets.py:156,162`) before being persisted to
   `CustomConnector.base_config`, exactly as `DataSource.config` already is.
   A locked secret (e.g. a shared service-account password an admin wants
   fixed org-wide) is supported without inventing a new encryption path.

## Runtime resolution: how a preset reaches a `DataSource`

This is the section the two-design comparison above exists to settle. There
is no "resolve a custom connector type" step anywhere at query time — all
resolution happens once, inside the `DataSource` create/update endpoints
(`routers/data_sources.py:102-111,137-162`), which already have `db` and
`current_user` in scope.

`DataSourceCreate`/`DataSourceUpdate` (`schemas/schemas.py:421-430`) gain one
new optional field: `custom_connector_id: int | None = None`.

**On create**, when `custom_connector_id` is supplied:

1. Load the preset filtered by **both** id and the caller's org:
   `db.get` won't do this in one call, so:
   `select(CustomConnector).where(CustomConnector.id == body.custom_connector_id,
   CustomConnector.org_id == current_user.org_id)`. **Not found → 404**,
   identically worded to "Data source not found" elsewhere in this router.
   This is the cross-org guard: an org-B user supplying org-A's preset id
   gets the same 404 as supplying an id that doesn't exist at all — they
   can't distinguish "wrong org" from "no such preset," and they never see
   org-A's `base_config` (hostnames, account names — the very values the
   preset locks).
2. `body.type` is **ignored** if `custom_connector_id` is present — the
   preset's `base_type` is authoritative: `ds.type = preset.base_type`.
3. Merge config: start from `body.config or {}` (the client-supplied
   values), then for every key in `preset.locked_fields`, overwrite with
   `preset.base_config[key]` (decrypted). For keys in `preset.base_config`
   but **not** in `locked_fields`, treat them as defaults — use the
   preset's value only if the client didn't supply that key at all. Then
   run the merged dict through the existing
   `secrets.encrypt_config(merged, connectors.secret_field_names(ds.type))`
   exactly as today (`data_sources.py:105`).
4. Set `ds.custom_connector_id = preset.id`.
5. `_require_known_connector(ds.type)` still runs unconditionally — since
   `ds.type` came from an already-validated preset, this can't fail, but
   running it unconditionally means there's exactly one code path for
   "is this DataSource's type valid," not two.

**On update**, the identical org-scoped lookup and lock-reapplication run
whenever `body.custom_connector_id` is present in the request (switching
which preset a `DataSource` uses, or attaching one to a previously
plain — no `custom_connector_id` — connection). If the update omits
`custom_connector_id` entirely, the existing `ds.custom_connector_id` (and
its locks) stay in effect, and locked fields in `body.config` are still
overwritten from the preset the same way, using `ds.custom_connector_id`'s
stored preset rather than a freshly-supplied one — a locked field can't be
silently unlocked by omitting `custom_connector_id` from an update request
that otherwise only touches, say, `name`.

**`connectors.py` itself is not modified in any way.** No new function
signature, no new parameter, no dynamic registry entry. This is the
guarantee the whole design is built around: `resolve`, `build_url`,
`connect_args`, `sql_family_of`, `secret_field_names`, and every other
existing call site work on preset-created `DataSource` rows without knowing
presets exist, because those rows carry a real, ordinary `type` value.

## Catalog listing

`connectors.catalog_payload()` (`connectors.py:466-482`) gains one new
optional parameter: `catalog_payload(org_id: int | None = None)`. When
`org_id` is given, it appends one tile per `CustomConnector` row in that
org, each marked `"is_custom": true` and carrying the preset's `id` (for the
frontend to send back as `custom_connector_id` on create), `key`, `label`,
`icon` (inherited from the base type's spec), and `base_type`'s
`config_fields` **filtered down to the non-locked fields only** — a user
picking this tile only ever sees the fields they're actually allowed to
fill in. This is the one call site that changes in `connectors.py`, and it
is additive and backward-compatible (existing callers passing no `org_id`
get exactly today's output). The router call site
(`routers/data_sources.py:118-120`, `list_connectors`) passes
`current_user.org_id` through, which it already has from `get_current_user`.

## Response shape

`DataSourceOut` (`schemas/schemas.py:432-439`) gains:

```python
custom_connector_id: int | None = None
custom_connector_label: str | None = None
```

populated in the router from the new `DataSource.custom_connector`
relationship (`ds.custom_connector.label if ds.custom_connector else None`)
so the Connections list can show "Acme Snowflake" instead of the base type
"snowflake" for preset-created connections, without a second query per row
(SQLAlchemy lazy-loads the relationship on access; list endpoints already
iterate `DataSource` rows one at a time for redaction via `_redacted()`, so
this adds one attribute access per row, not a new N+1 pattern beyond what
already exists there).

## Editing or deleting a preset already in use

- **Editing** a preset's `base_config`/`locked_fields` does **not**
  retroactively change any existing `DataSource` that was created from it —
  locks are applied once, at `DataSource` save time (Runtime resolution,
  above), the same way editing a calculated column's expression only
  affects future evaluations, never a cached result. Re-applying a preset's
  current locks to every `DataSource` that references it is a plausible v2
  item, explicitly deferred here to keep this version's behavior simple and
  predictable: what you see in a connection's config is what was locked in
  at the time it was created or last updated with that preset attached.
- **Deleting** a preset that's still referenced by any `DataSource` is
  rejected — see `ondelete="RESTRICT"` above. The delete endpoint catches
  the resulting `IntegrityError` and returns `409` with the count of
  referencing `DataSource` rows, rather than a raw database error.

## Backend API

New router, `app/routers/custom_connectors.py`, mounted at
`/custom-connectors`, mirroring the existing router-per-resource pattern:

- `GET /custom-connectors` — list presets for the caller's org (org-admin
  only, since only admins manage presets; a non-admin sees them already,
  pre-filtered to non-locked fields, via `GET /data-sources/connectors`'s
  now-org-aware `catalog_payload`).
- `POST /custom-connectors` — create (org-admin only, all save-time
  validation above).
- `PUT /custom-connectors/{id}` — update (org-admin only, org-scoped lookup
  identical in shape to the `DataSource` update's, 404 on cross-org).
- `DELETE /custom-connectors/{id}` — delete (org-admin only, `409` if
  `RESTRICT` fires).

`routers/data_sources.py` changes: `DataSourceCreate`/`DataSourceUpdate`
gain `custom_connector_id`; `create_data_source`/`update_data_source` gain
the resolution logic in "Runtime resolution" above; `list_connectors` passes
`current_user.org_id` into `catalog_payload`; `DataSourceOut` gains the two
new fields.

## Frontend

The existing "new connection" catalog view (populated from
`GET /data-sources/connectors`) already renders one tile per entry — preset
tiles need no new rendering path, only a visual `"is_custom"` badge and,
when selected, a config form built from the tile's already-filtered
`config_fields` (locked fields simply aren't in the list, so the existing
dynamic-form-from-`config_fields` renderer needs no changes either — it
already only renders what's in the array it's given).

A small new admin-only management surface (alongside org settings, where
admin-only screens already live): list of presets for the org; "+ New
preset" opens a form — pick a base connector type from the existing catalog
(reusing the existing type-picker), fill in `base_config` values using that
type's `config_fields` renderer, and a checkbox per field marking it
locked; edit and delete, with the delete button surfacing the backend's 409
count-of-connections message inline rather than a generic error.

## Testing plan

**Backend:**
- Save-time validation: unknown `base_type` rejected; `base_config`/
  `locked_fields` keys not in the base type's `config_fields` rejected;
  `locked_fields` not a subset of `base_config` rejected; duplicate `key`
  within an org rejected (409); the same `key` in two different orgs is
  **not** rejected (proves org-scoping of the uniqueness constraint).
- **Cross-org creation is rejected**: org-B user creates a `DataSource`
  with org-A's `custom_connector_id` → 404, and the response never contains
  org-A's `base_config` values — the core security property this design
  exists to protect, pinned the way
  `test_admin_row_security_rules.py` pins the RLS/custom-function boundary.
- Locked fields win: creating a `DataSource` from a preset with a
  client-supplied value for a locked field results in the preset's value
  being stored, not the client's.
- Non-locked preset defaults apply only when the client omits the field,
  and are overridable when the client supplies it.
- Updating a `DataSource` without `custom_connector_id` in the request body
  still re-applies its existing preset's locks (can't unlock a field by
  omission).
- Deleting a preset with zero referencing `DataSource` rows succeeds;
  deleting one with at least one referencing row returns 409 with the
  correct count, and the preset and its `DataSource` rows are unchanged
  afterward.
- Editing a preset's `base_config` does not change any already-created
  `DataSource`'s stored `config`.
- `catalog_payload(org_id=None)` returns exactly today's output (no
  regression for any caller not yet passing org context);
  `catalog_payload(org_id=X)` includes org X's presets with locked fields
  filtered out of each tile's `config_fields`, and never includes another
  org's presets.
- End-to-end: a `DataSource` created from a preset works through the real
  connect/list-tables/preview path (`services/connections.py`) exactly as a
  plain connection of the same base type does — proving `connectors.py`'s
  ~25 call sites needed no changes.

**Frontend:**
- Preset tiles render in the catalog with the `is_custom` badge and only
  their non-locked fields in the config form.
- Admin management screen: create, edit, delete, and the 409-in-use message
  rendered inline on a blocked delete.
- Non-admin users see preset tiles in the connection catalog but do not see
  the preset management screen/entry point.
