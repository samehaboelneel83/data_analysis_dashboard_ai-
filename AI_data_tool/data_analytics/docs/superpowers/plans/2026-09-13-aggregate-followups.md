# Aggregate Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the ten follow-ups recorded against aggregate datasets and add the row-security overlap notice, so an author sees what an aggregate is, an admin sees what a rule reads, and nothing an aggregate leaves behind outlives it.

**Architecture:** Backend changes stay inside the existing seams: `routers/datasets.py` (aggregate endpoints, delete), `routers/data_sources.py` (delete), `routers/admin.py` (preflight), `services/refresh_scheduler.py` (refresh checks, reaper), one new pure service `services/dataset_cleanup.py`. Frontend changes touch `AggregatesPanel.tsx`, `AdminRowSecurityRules.tsx`, `WidgetConfigPanel.tsx`, `ReportBuilder.tsx` and `services/api.ts`, plus one pure helper `lib/aggregateDisclosure.ts`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, pandas, DuckDB, pytest; React 18, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-12-aggregate-datasets-design.md`, section "Follow-up design (approved 2026-09-13)". Ticket numbers below refer to that section.

## Global Constraints

- Services never import FastAPI (`tests/test_layer_conformance.py`). A helper shared by two routers lives in `app/services/` and raises plain exceptions.
- `apply_rls_filter` call sites are allowlisted by `tests/test_rls_base_frame_choke_point.py`; do not add one.
- The doc-count audit (`tests/test_architecture_doc.py`) pins the number of backend test modules, frontend test files and Alembic revisions in BOTH `ARCHITECTURE.md` and `ARCHITECTURE.html`. A task that adds a test FILE bumps both documents in the same commit. Prefer adding tests to existing modules.
- Line endings: check the blob before editing (`git ls-files --eol <path>`); write the file back in the index's convention. `routers/datasets.py`, `routers/admin.py`, `core/rls.py`, `services/refresh_scheduler.py`, `tests/test_scheduler_backoff.py`, `tests/test_aggregate_refresh.py`, docs and every frontend file are LF; most other backend files are CRLF. A commit that rewrites every line of a file is a defect.
- No exception text from a customer database reaches an HTTP response; report the exception TYPE only (existing rule in `create_aggregate`).
- The security invariant: nothing ever shows a row or a column the source would have hidden. Every endpoint touched keeps `check_org` → `require_dataset_read` → `require_dataset_capability(..., "data")` in that order.
- Frontend tests that `vi.mock('../../services/api', () => ({...}))` wholesale must list every api function the page now calls, or the page throws at runtime.
- Run the covering tests named in each task; run `tests/test_layer_conformance.py` and `tests/test_architecture_doc.py` before every commit.

---

### Task 1: Test-only pins — `row_count` grain and migration round trip (tickets 6, 7)

**Files:**
- Modify: `backend/tests/test_aggregates_compile.py` (CRLF)
- Modify: `backend/tests/test_alembic_migrations.py` (CRLF)
- Possibly modify: `backend/alembic/versions/*.py` if a `downgrade()` is broken (report which)

**Interfaces:**
- Consumes: `aggregates.normalise_spec(spec, known_columns)`, `alembic.command.upgrade/downgrade`, `_alembic_config()`, `scratch_url` fixture.
- Produces: nothing for later tasks.

- [ ] **Step 1: Write the `row_count` grain pin**

Add to `TestNormalise` in `test_aggregates_compile.py`:

```python
    def test_a_source_with_a_real_row_count_column_still_cannot_use_it_as_grain(self):
        """The reservation must be unconditional. The parametrised case above
        proves 'reserved beats unknown column'; this proves 'reserved beats a
        column the source really has', which is the fail-open core/rls.py's
        unconditional row_count strip depends on."""
        with pytest.raises(AggregateSpecError, match="reserved"):
            aggregates.normalise_spec(
                {"grain": ["row_count"], "measures": [{"column": "amount", "agg": "sum"}]},
                COLS | {"row_count"})
```

- [ ] **Step 2: Run it; expected PASS (this pins existing behaviour; the RED proof is a sabotage)**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_aggregates_compile.py -q -p no:cacheprovider`
Then temporarily change `if g == ROW_COUNT:` in `services/aggregates.py` to `if g == ROW_COUNT and g not in known_columns:`, rerun, expect this test to FAIL, revert. Record both outputs in the report.

- [ ] **Step 3: Write the migration round-trip and column-set tests**

In `test_alembic_migrations.py`, add beside `_table_names`:

```python
async def _table_columns(engine) -> set[tuple[str, str]]:
    """Every (table, column) pair -- the comparison table names alone missed:
    a migration that creates the table but forgets a column matched."""
    async with engine.connect() as conn:
        def _read(sync_conn):
            insp = sa_inspect(sync_conn)
            return {(t, c["name"]) for t in insp.get_table_names()
                    for c in insp.get_columns(t)}
        return await conn.run_sync(_read)
```

Add to `TestFreshDatabase`:

```python
    async def test_upgrade_head_matches_create_all_columns(self, tmp_path, scratch_url):
        create_all_engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'create_all_cols.db'}")
        async with create_all_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        expected = await _table_columns(create_all_engine)
        await create_all_engine.dispose()

        await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
        alembic_engine = create_async_engine(scratch_url)
        actual = await _table_columns(alembic_engine)
        await alembic_engine.dispose()

        actual = {tc for tc in actual if tc[0] != "alembic_version"}
        assert actual == expected, (
            f"missing from alembic: {sorted(expected - actual)}; "
            f"extra in alembic: {sorted(actual - expected)}")

    async def test_downgrade_to_base_and_back_is_clean(self, scratch_url):
        """Every revision's downgrade() has to run, on SQLite, in batch mode
        where it alters a table. Nothing exercised them before."""
        cfg = _alembic_config()
        await asyncio.to_thread(command.upgrade, cfg, "head")
        await asyncio.to_thread(command.downgrade, cfg, "base")
        engine = create_async_engine(scratch_url)
        after_down = await _table_names(engine)
        await engine.dispose()
        assert after_down <= {"alembic_version"}, sorted(after_down)

        await asyncio.to_thread(command.upgrade, cfg, "head")
        engine = create_async_engine(scratch_url)
        after_up = await _table_names(engine)
        await engine.dispose()
        assert "datasets" in after_up
```

- [ ] **Step 4: Run them**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_alembic_migrations.py -q -p no:cacheprovider`
Expected: both new tests PASS. If `test_downgrade_to_base_and_back_is_clean` fails inside a revision's `downgrade()`, fix THAT revision's downgrade (batch mode for SQLite, matching its upgrade) and say so in the report. If `0001_baseline`'s downgrade leaves the app tables in place by design, change the `after_down` assertion to compare against what `0001_baseline.downgrade` documents, and say so. If `test_upgrade_head_matches_create_all_columns` reports missing columns, do NOT write a new migration in this task: report the exact pairs and mark the test `xfail(strict=True, reason=...)` naming them; the controller rules on the follow-up.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_aggregates_compile.py backend/tests/test_alembic_migrations.py
git commit -m "test(aggregates): pin row_count grain reservation and migration round trip"
```

---

### Task 2: Nothing an aggregate leaves behind outlives it (tickets 8, 9)

**Files:**
- Create: `backend/app/services/dataset_cleanup.py` (write as CRLF, the service-tree convention)
- Modify: `backend/app/routers/datasets.py:584-608` (`delete_dataset`, LF)
- Modify: `backend/app/routers/data_sources.py:281-287` (`delete_data_source`, check blob)
- Modify: `backend/app/services/refresh_scheduler.py` (LF): add `reap_orphaned_failures` after `reap_stuck_sync_runs`
- Modify: `backend/app/main.py:366-368` (check blob): call the reaper
- Test: `backend/tests/test_aggregate_endpoints.py` (CRLF), `backend/tests/test_scheduler_backoff.py` (LF)

**Interfaces:**
- Produces: `services.dataset_cleanup.discard_dataset_artifacts(db, datasets: Iterable[Dataset]) -> int` — unlinks each dataset's file and parquet sidecar and deletes its `ScheduleFailure` rows (`kind="dataset"`); returns the number of files removed. Does not commit.
- Produces: `refresh_scheduler.reap_orphaned_failures(session) -> int`.

- [ ] **Step 1: Write the failing tests**

In `test_aggregate_endpoints.py`, after the existing source-delete test (`test_deleting_the_source_removes_the_aggregate_file`, around line 263), add:

```python
@pytest.mark.asyncio
async def test_deleting_the_source_removes_its_and_its_aggregates_failure_rows(
        client, auth_headers, db_session, source, fake_refresh):
    from app.services.refresh_scheduler import record_failure
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    await record_failure(db_session, "dataset", agg_id, "grain no longer covers tenant")
    await record_failure(db_session, "dataset", source.id, "source unreachable")

    r = await client.delete(f"/api/v1/datasets/{source.id}", headers=auth_headers["a"])
    assert r.status_code == 204
    left = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id.in_([source.id, agg_id])))).scalars().all()
    assert left == []


@pytest.mark.asyncio
async def test_deleting_the_data_source_removes_every_datasets_file(
        client, auth_headers, db_session, source, fake_refresh):
    """routers/data_sources.py cascades every dataset with no file cleanup at
    all -- wider than the dataset delete, which now cleans up after itself."""
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    filename = r.json()["filename"]
    assert Path(filename).exists()
    assert Path(filename).with_suffix(".parquet").exists()

    r = await client.delete(f"/api/v1/data-sources/{source.data_source_id}", headers=auth_headers["a"])
    assert r.status_code == 204
    assert not Path(filename).exists()
    assert not Path(filename).with_suffix(".parquet").exists()
    assert (await db_session.get(Dataset, source.id)) is None
```

Check first how `DatasetOut` names the file field (`filename`). The sidecar path is `frame_cache.sidecar_path(csv_path)`; use it in the test instead of `.with_suffix(".parquet")`. The data-source router's prefix is `/data-sources` under `/api/v1` (verified).

In `test_scheduler_backoff.py` add:

```python
@pytest.mark.asyncio
async def test_startup_reaps_failure_rows_whose_dataset_is_gone(db_session, two_orgs):
    from app.models.models import Dataset, ScheduleFailure
    from app.services.refresh_scheduler import reap_orphaned_failures, record_failure
    org = two_orgs["a"]["org"]
    live = Dataset(name="live", org_id=org.id, mode="import", filename=None)
    db_session.add(live)
    await db_session.flush()
    await record_failure(db_session, "dataset", live.id, "still here")
    await record_failure(db_session, "dataset", 999_999, "dataset deleted long ago")
    await record_failure(db_session, "schedule", 999_999, "not a dataset row; untouched")

    assert await reap_orphaned_failures(db_session) == 1
    rows = (await db_session.execute(select(ScheduleFailure))).scalars().all()
    assert {(r.kind, r.item_id) for r in rows} == {("dataset", live.id), ("schedule", 999_999)}
```

- [ ] **Step 2: Run them; expected FAIL** (`ImportError` for the reaper; failure rows / files still present for the deletes)

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_aggregate_endpoints.py tests/test_scheduler_backoff.py -q -p no:cacheprovider`

- [ ] **Step 3: Write the service**

`backend/app/services/dataset_cleanup.py`:

```python
"""What a dataset leaves behind, removed in one place.

A dataset row cascades at the database (aggregates, columns, manifests), but
two things do not: its CSV and parquet sidecar on disk, and its
`ScheduleFailure` rows, which are keyed (kind, item_id) with no FK. Both the
dataset delete and the data-source delete need the same sweep, and a router
cannot import another router, so it lives here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, select

from .frame_cache import remove_parquet_sidecar


async def discard_dataset_artifacts(db, datasets: Iterable) -> int:
    """Unlink each dataset's file and sidecar and delete its failure rows.
    Does not commit. Returns how many files were removed."""
    from ..models.models import ScheduleFailure
    removed = 0
    ids = []
    for ds in datasets:
        ids.append(ds.id)
        if ds.filename:
            if Path(ds.filename).exists():
                removed += 1
            Path(ds.filename).unlink(missing_ok=True)
            remove_parquet_sidecar(ds.filename)
    if ids:
        await db.execute(delete(ScheduleFailure).where(
            ScheduleFailure.kind == "dataset", ScheduleFailure.item_id.in_(ids)))
    return removed
```

- [ ] **Step 4: Use it from both deletes**

`delete_dataset` (`routers/datasets.py:591-608`) becomes:

```python
    from ..services.dataset_cleanup import discard_dataset_artifacts
    # Aggregate datasets are the first dataset -> dataset cascade
    # (aggregate_of_dataset_id, ondelete=CASCADE): the DB removes their ROWS
    # with no application code running, so their files and failure rows are
    # only cleaned up because this sweeps them first.
    aggregates = (await db.execute(
        select(Dataset).where(Dataset.aggregate_of_dataset_id == ds.id))).scalars().all()
    await discard_dataset_artifacts(db, [ds, *aggregates])
    await audit(db, current_user, "dataset.delete", "dataset", ds.id, ds.name)
    await db.delete(ds)
    await db.commit()
```

`delete_data_source` (`routers/data_sources.py`):

```python
    from ..models.models import Dataset
    from ..services.dataset_cleanup import discard_dataset_artifacts
    owned = (await db.execute(select(Dataset).where(Dataset.data_source_id == ds.id))).scalars().all()
    # Every dataset of this source cascades with it -- imports pulled from it,
    # DirectQuery definitions, and their aggregates (which carry the source's
    # data_source_id). Their files and failure rows would otherwise be orphaned.
    await discard_dataset_artifacts(db, owned)
    await db.delete(ds)
    await db.commit()
```

Confirm `select` is imported in `data_sources.py`; add if not.

- [ ] **Step 5: The reaper**

In `refresh_scheduler.py`, after `reap_stuck_sync_runs`:

```python
async def reap_orphaned_failures(session) -> int:
    """Delete `kind="dataset"` failure rows whose dataset no longer exists.

    ScheduleFailure is keyed (kind, item_id) with no foreign key, so a dataset
    deleted before dataset_cleanup existed left its row behind, and so does
    any delete that bypasses the routers. Nothing reads an orphan (the tick
    scans datasets), but nothing removed them either. Called once at startup.
    """
    from sqlalchemy import delete
    from ..models.models import Dataset, ScheduleFailure
    live = select(Dataset.id)
    result = await session.execute(
        delete(ScheduleFailure).where(ScheduleFailure.kind == "dataset",
                                      ScheduleFailure.item_id.not_in(live)))
    if result.rowcount:
        await session.commit()
        log.warning("Reaped %s scheduler failure row(s) for deleted datasets", result.rowcount)
    return result.rowcount or 0
```

In `main.py` next to the `reap_stuck_sync_runs` call:

```python
                from .services.refresh_scheduler import reap_orphaned_failures, reap_stuck_sync_runs
                await reap_stuck_sync_runs(session)
                await reap_orphaned_failures(session)
```

- [ ] **Step 6: Run the covering tests; expected PASS**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_aggregate_endpoints.py tests/test_scheduler_backoff.py tests/test_aggregate_refresh.py tests/test_data_sources*.py tests/test_layer_conformance.py tests/test_architecture_doc.py -q -p no:cacheprovider`

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dataset_cleanup.py backend/app/routers/datasets.py backend/app/routers/data_sources.py backend/app/services/refresh_scheduler.py backend/app/main.py backend/tests/test_aggregate_endpoints.py backend/tests/test_scheduler_backoff.py
git commit -m "fix(aggregates): files and failure rows do not outlive their dataset or source"
```

---

### Task 3: Export policy resolves; a source with a default filter is refused (tickets 2, 3)

**Files:**
- Modify: `backend/app/routers/datasets.py` (LF): `export_dataset` (~796), `materialize` export check (~1992), `create_aggregate` (2223-2280)
- Modify: `backend/app/services/refresh_scheduler.py` (LF): aggregate branch of `refresh_one` (~618-662)
- Test: `backend/tests/test_aggregate_endpoints.py` (CRLF), `backend/tests/test_aggregate_refresh.py` (LF)

**Interfaces:**
- Consumes: `core.rls._aggregate_source(db, dataset_id) -> (source_id_or_self, spec|None)`; `_exports_disabled(ds, fmt, has_security)`; `record_failure`.
- Produces: `_policy_dataset(db, ds) -> Dataset` in `routers/datasets.py` — the dataset whose export policy governs `ds`.

- [ ] **Step 1: Write the failing tests**

`test_aggregate_endpoints.py`:

```python
@pytest.mark.asyncio
async def test_the_export_policy_is_not_copied_onto_the_aggregate(
        client, auth_headers, db_session, source, fake_refresh):
    """The source already carries the policy when the aggregate is created --
    the only case in which the old code copied it -- and the aggregate row
    must still carry nothing: the policy is resolved, never copied."""
    src = await db_session.get(Dataset, source.id)
    src.column_meta = {**(src.column_meta or {}), "__exports_disabled__": True}
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    agg = await db_session.get(Dataset, r.json()["id"])
    assert "__exports_disabled__" not in (agg.column_meta or {})


@pytest.mark.asyncio
async def test_disabling_exports_on_the_source_later_bites_on_the_aggregate(
        client, auth_headers, db_session, source, fake_refresh):
    """A copy taken at creation would not notice this; a resolved policy does."""
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    src = await db_session.get(Dataset, source.id)
    src.column_meta = {**(src.column_meta or {}), "__exports_disabled__": True}
    await db_session.commit()
    r = await client.get(f"/api/v1/datasets/{agg_id}/export", headers=auth_headers["a"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_source_with_a_default_filter_cannot_be_aggregated(
        client, auth_headers, db_session, source, fake_refresh):
    src = await db_session.get(Dataset, source.id)
    src.default_filter_expr = "region == 'N'"
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "filter expression" in r.json()["detail"]
    assert fake_refresh == []
```

`test_aggregate_refresh.py` (uses the `pair` and `rewrites` fixtures already there):

```python
@pytest.mark.asyncio
async def test_a_default_filter_added_to_the_source_stops_the_refresh(db_session, pair, rewrites, monkeypatch):
    src, agg, role = pair
    src.default_filter_expr = "region == 'N'"
    await db_session.commit()
    monkeypatch.setattr(refresh_scheduler, "rescan_insights", _noop_async)
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == []
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    assert "filter expression" in failure.last_error
```

- [ ] **Step 2: Run; expected FAIL** (copy present / 200 on export; 201 on create; a rewrite happened)

- [ ] **Step 3: Resolve the policy through the source**

In `routers/datasets.py`, next to `_dataset_has_security`:

```python
async def _policy_dataset(db: AsyncSession, ds: Dataset) -> Dataset:
    """The dataset whose export policy governs `ds`: its SOURCE for an
    aggregate, itself otherwise. Resolved, never copied -- the same rule the
    security resolvers follow, so a policy change on the source applies to
    every aggregate at once."""
    from ..core.rls import _aggregate_source
    source_id, _spec = await _aggregate_source(db, ds.id)
    if source_id == ds.id:
        return ds
    return (await db.get(Dataset, source_id)) or ds
```

`export_dataset`:

```python
    policy_ds = await _policy_dataset(db, ds)
    if _exports_disabled(policy_ds, fmt, await _dataset_has_security(db, dataset_id)):
        raise HTTPException(403, "Exports are disabled for this dataset")
```

The materialize check (~1992) likewise: `if _exports_disabled(await _policy_dataset(db, src), "csv", False):`.

In `create_aggregate`, delete the three lines that build `inherited` from `__exports_disabled__` and pass `column_meta={}`. Add, right after the DirectQuery-mode check:

```python
    if ds.default_filter_expr:
        raise HTTPException(400, "The source has a report-level filter expression; an aggregate "
                                 "would ignore it. Remove the filter or aggregate a source without one.")
```

- [ ] **Step 4: The refresh re-check**

In `refresh_one`'s aggregate branch, right after the grain check's `return True` and before the recompile block, insert (the `source` load already happens in the recompile block; load it once above both):

```python
            source = await session.get(Dataset, ds.aggregate_of_dataset_id)
            if source is not None and source.default_filter_expr:
                await record_failure(
                    session, "dataset", ds.id,
                    "Not refreshed: the source now has a report-level filter expression, "
                    "which an aggregate would ignore. Remove it or rebuild the aggregate.")
                ds.last_refreshed_at = datetime.utcnow()
                await session.commit()
                return True
```

and change the recompile block to reuse `source` instead of loading it again.

- [ ] **Step 5: Run the covering tests; expected PASS**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_aggregate_endpoints.py tests/test_aggregate_refresh.py tests/test_aggregate_security.py tests/test_dataset_materialize.py tests/test_export_policy*.py tests/test_layer_conformance.py -q -p no:cacheprovider`

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/datasets.py backend/app/services/refresh_scheduler.py backend/tests/test_aggregate_endpoints.py backend/tests/test_aggregate_refresh.py
git commit -m "fix(aggregates): export policy resolves from the source; a default filter is refused"
```

---

### Task 4: The security value tests also run on the DuckDB path (ticket 4)

**Files:**
- Modify: `backend/tests/test_aggregate_security.py` (CRLF)

**Interfaces:**
- Consumes: `frame_cache.write_parquet_sidecar(csv_path)`, `settings.widget_duckdb_pushdown`, `duck_agg.try_aggregate` (spy pattern from `tests/test_duck_agg_governed.py:47-68`), `widget_data.clear_widget_data_cache`, `frame_cache.clear_frame_cache`.

- [ ] **Step 1: Parametrise the fixture**

Change `source_and_aggregate` to a parametrised fixture, `params=["pandas", "duckdb"]`, and add a spy:

```python
@pytest.fixture(params=["pandas", "duckdb"])
def engine(request, monkeypatch):
    """Both engines, because production reads an aggregate through DuckDB
    (every refresh writes a sidecar) and the first version of these tests
    only ever exercised pandas."""
    from app.core.config import settings
    from app.services import duck_agg
    from app.services.frame_cache import clear_frame_cache
    from app.services.widget_data import clear_widget_data_cache
    clear_widget_data_cache(); clear_frame_cache()
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param == "duckdb")
    seen = {"ran": False, "reason": "not consulted"}
    real = duck_agg.try_aggregate

    def _spy(*a, **kw):
        frame, reason = real(*a, **kw)
        seen["ran"] = frame is not None
        seen["reason"] = reason
        return frame, reason
    monkeypatch.setattr(duck_agg, "try_aggregate", _spy)
    seen["name"] = request.param
    yield seen
    clear_widget_data_cache(); clear_frame_cache()
```

Make `source_and_aggregate` depend on `engine` and, when `engine["name"] == "duckdb"`, call `write_parquet_sidecar(str(path))` after writing the CSV and assert it returned True.

- [ ] **Step 2: Assert the engine in the value tests**

In `test_a_restricted_user_sees_only_their_tenant_on_the_aggregate`, `test_an_admin_sees_everything`, and every other test in the module that posts to `/widget-data`, add the fixture and after the response:

```python
    if engine["name"] == "duckdb":
        assert engine["ran"], engine["reason"]
```

The sabotage test (removing the redirect in `resolve_rls_expr`) must still fail under both engines; run it once with the sabotage applied and record the output.

- [ ] **Step 3: Run; expected PASS for both params, double the test count**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_aggregate_security.py -q -p no:cacheprovider -v | tail -30`
If a DuckDB variant declines (`engine["reason"]` says why), that is a real finding about the production path: report it, do not weaken the assertion.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_aggregate_security.py
git commit -m "test(aggregates): security value tests run on the DuckDB path too"
```

---

### Task 5: Edit and rebuild an aggregate (ticket 5, closes 10)

**Files:**
- Modify: `backend/app/schemas/schemas.py` (check blob): `AggregateUpdateRequest`
- Modify: `backend/app/routers/datasets.py` (LF): extract `_build_aggregate_file`, add `update_aggregate`
- Modify: `frontend/src/services/api.ts` (LF): `aggregatesApi.update`
- Modify: `frontend/src/components/dataset/AggregatesPanel.tsx` (LF)
- Test: `backend/tests/test_aggregate_endpoints.py` (CRLF), `frontend/src/components/dataset/AggregatesPanel.test.tsx` (LF)

**Interfaces:**
- Produces: `PUT /datasets/{source_id}/aggregates/{agg_id}` body `{grain?: string[], measures?: AggregateMeasure[], refresh_interval_minutes?: int|null}` → `DatasetOut`. Omitted fields keep the stored value; an omitted interval keeps it, an explicit `null` unschedules.
- Produces: `aggregatesApi.update(sourceId, aggId, body)`.

- [ ] **Step 1: Write the failing backend tests**

`test_aggregate_endpoints.py`:

```python
@pytest.mark.asyncio
async def test_editing_an_aggregate_recompiles_rewrites_and_clears_the_failure(
        client, auth_headers, db_session, source, fake_refresh):
    from app.services.refresh_scheduler import record_failure
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    old_file = r.json()["filename"]
    await record_failure(db_session, "dataset", agg_id, "the source's query changed")

    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}",
                         json={"measures": [{"column": "amount", "agg": "sum"}, {"column": "units", "agg": "max"}]},
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aggregate_spec"]["grain"] == ["tenant", "region"]          # kept
    assert [m["name"] for m in body["aggregate_spec"]["measures"]] == ["amount_sum", "units_max"]
    assert body["refresh_interval_minutes"] == 60                             # kept
    assert len(fake_refresh) == 2 and '"units"' in fake_refresh[-1]           # recompiled and rewritten
    assert body["filename"] != old_file                                       # a new file was allocated
    assert not Path(old_file).exists()                                        # and the old one is gone
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg_id))).scalar_one_or_none()
    assert failure is None
    agg = (await db_session.execute(select(Dataset).options(selectinload(Dataset.columns))
                                    .where(Dataset.id == agg_id))).scalar_one()
    # fake_refresh writes a fixed frame whatever the SQL asked for; the columns
    # are replaced from THAT frame, so this is what the row must now carry.
    assert {c.name for c in agg.columns} == {"tenant", "region", "amount_sum", "row_count"}
```

Add `from sqlalchemy.orm import selectinload` at the top of the module.

```python
@pytest.mark.asyncio
async def test_an_empty_edit_is_a_rebuild(client, auth_headers, db_session, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=auth_headers["a"])
    assert r.status_code == 200
    assert len(fake_refresh) == 2 and fake_refresh[0] == fake_refresh[1]


@pytest.mark.asyncio
async def test_an_edit_re_runs_the_grain_check(client, auth_headers, db_session, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}",
                         json={"grain": ["region"]}, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "tenant" in r.json()["detail"] and "Tenant" in r.json()["detail"]
    assert len(fake_refresh) == 1


@pytest.mark.asyncio
async def test_an_edit_needs_the_data_capability_and_the_right_source(
        client, auth_headers, db_session, source, colleague, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=colleague)
    assert r.status_code in (403, 404)
    r = await client.put(f"/api/v1/datasets/{source.id + 1000}/aggregates/{agg_id}", json={}, headers=auth_headers["a"])
    assert r.status_code == 404
```

- [ ] **Step 2: Run; expected FAIL with 405/404 (no route)**

- [ ] **Step 3: Schema**

In `schemas.py` after `AggregateCreateRequest`:

```python
class AggregateUpdateRequest(BaseModel):
    """Edit or rebuild an aggregate. Every field is optional; an omitted field
    keeps the stored value. An empty body is a rebuild: recompile the stored
    spec against the source as it is NOW and rewrite the file."""
    grain: list[str] | None = None
    measures: list[AggregateMeasure] | None = None
    refresh_interval_minutes: int | None = None
```

- [ ] **Step 4: Extract the build and add the endpoint**

In `routers/datasets.py`, above `create_aggregate`, extract everything from `known = {...}` through the quota check into:

```python
async def _build_aggregate_file(db: AsyncSession, current_user: User, ds: Dataset,
                                grain: list[str], measures: list[dict]):
    """Validate a spec against the source AS IT IS NOW, compile, run the
    query, write the file, enforce the row cap and the storage quota.
    Returns (spec, sql, path, df, type_map, size). Raises HTTPException with
    the file already removed on every refusal after the write."""
    from ..services.aggregates import (AggregateSpecError, compile_aggregate_sql,
                                       normalise_spec, rls_columns_outside_grain)
    from ..services.dataset_refresh import rewrite_dataset_file
    from ..services.prep import MATERIALIZE_MAX_ROWS

    if ds.default_filter_expr:
        raise HTTPException(400, "The source has a report-level filter expression; an aggregate "
                                 "would ignore it. Remove the filter or aggregate a source without one.")
    known = {c.name for c in ds.columns}
    try:
        spec = normalise_spec({"grain": grain, "measures": measures}, known)
    except AggregateSpecError as e:
        raise HTTPException(400, str(e))
    rules = await _source_rules(db, ds.id)
    bad = rls_columns_outside_grain([r for r, _ in rules], spec["grain"], known)
    if bad:
        raise HTTPException(400, _uncovered_message(bad, rules))

    source = await db.get(DataSource, ds.data_source_id)
    check_org(source, current_user, "Data source not found")
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    sql = compile_aggregate_sql(ds, spec)
    path = upload_store.allocate_path(current_user.org_id, "aggregate.csv")
    try:
        df, type_map = await asyncio.to_thread(rewrite_dataset_file, cfg, str(path), None, sql)
    except Exception as e:  # noqa: BLE001 -- type only: the driver's text can embed a DSN
        path.unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise HTTPException(400, f"The source rejected the aggregate query: {type(e).__name__}")
    if len(df) > MATERIALIZE_MAX_ROWS:
        path.unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise HTTPException(
            400, f"The grain is too fine: this aggregate has {len(df):,} rows, over the "
                 f"{MATERIALIZE_MAX_ROWS:,} limit for a saved dataset. Add a coarser grain "
                 "column or fewer measures.")
    size = path.stat().st_size
    try:
        await quotas.enforce_storage_quota(db, current_user.org_id, size)
    except (HTTPException, quotas.QuotaExceeded) as e:
        path.unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise HTTPException(getattr(e, "status_code", 413), str(e.detail))
    return spec, sql, path, df, type_map, size
```

`create_aggregate` keeps its gates, name and interval checks, then calls `_build_aggregate_file(db, current_user, ds, req.grain, [m.model_dump() for m in req.measures])` and continues from `new = Dataset(...)` with `column_meta={}` (Task 3 removed the copy; keep the existing comments about `created_by`).

Then:

```python
@router.put("/{dataset_id}/aggregates/{agg_id}", response_model=DatasetOut)
async def update_aggregate(
    dataset_id: int, agg_id: int, req: AggregateUpdateRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Edit an aggregate's grain, measures or schedule, or -- with an empty
    body -- rebuild it against the source as it is now. Every creation check
    runs again: rules and the source's query can have changed since. The old
    file is replaced only after the new one is fully written and accepted."""
    from ..services.dataset_refresh import write_materialization
    from ..services.refresh_scheduler import MIN_INTERVAL_MINUTES, clear_failure

    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    agg = await db.get(Dataset, agg_id)
    if agg is None or agg.aggregate_of_dataset_id != ds.id or agg.org_id != current_user.org_id:
        raise HTTPException(404, "Aggregate not found")
    stored = agg.aggregate_spec or {}
    grain = req.grain if req.grain is not None else list(stored.get("grain") or [])
    measures = ([m.model_dump() for m in req.measures] if req.measures is not None
                else list(stored.get("measures") or []))
    interval = agg.refresh_interval_minutes
    if "refresh_interval_minutes" in req.model_fields_set:
        interval = req.refresh_interval_minutes
        if interval is not None and interval < MIN_INTERVAL_MINUTES:
            raise HTTPException(400, f"Minimum refresh interval is {MIN_INTERVAL_MINUTES} minutes")

    spec, sql, path, df, type_map, size = await _build_aggregate_file(db, current_user, ds, grain, measures)

    old_file = agg.filename
    agg.filename = str(path)
    agg.source_query = sql
    agg.aggregate_spec = spec
    agg.refresh_interval_minutes = interval
    agg.row_count, agg.col_count, agg.file_size = len(df), len(df.columns), size
    agg.last_refreshed_at = datetime.utcnow()
    for col in (await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == agg.id))).scalars().all():
        await db.delete(col)
    # Flush the deletes before the inserts: SQLAlchemy orders INSERT before
    # DELETE within one flush, so a column that keeps its name (tenant,
    # region, row_count) would otherwise briefly exist twice. dataset_columns
    # has no unique constraint on (dataset_id, name) today; the flush keeps
    # this correct if one is ever added.
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(dataset_id=agg.id, name=col_name, dtype=dtype,
                             missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={}))
    await write_materialization(db, agg.id, str(path), "full", len(df), list(df.columns), None)
    await clear_failure(db, "dataset", agg.id)
    await audit(db, current_user, "dataset.aggregate.update", "dataset", agg.id,
                f"grain {spec['grain']}, {len(df)} rows")
    await db.commit()
    if old_file and old_file != str(path):
        Path(old_file).unlink(missing_ok=True)
        remove_parquet_sidecar(old_file)
    from ..services.frame_cache import clear_frame_cache
    from ..services.widget_data import clear_widget_data_cache
    clear_widget_data_cache(); clear_frame_cache()
    return (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                             .where(Dataset.id == agg.id))).scalar_one()
```

Check how `write_materialization` behaves when a manifest row already exists for the dataset (it is called on every scheduled refresh, so it must upsert); and check whether `clear_frame_cache`/`clear_widget_data_cache` take arguments (use the module-level "clear all" if no per-file form exists; a rewritten file must not be served from the old memo).

- [ ] **Step 5: Run the backend tests; expected PASS**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_aggregate_endpoints.py tests/test_aggregate_refresh.py tests/test_aggregate_security.py tests/test_layer_conformance.py -q -p no:cacheprovider`

- [ ] **Step 6: Commit the backend**

```bash
git add backend/app/schemas/schemas.py backend/app/routers/datasets.py backend/tests/test_aggregate_endpoints.py
git commit -m "feat(aggregates): PUT edits or rebuilds an aggregate against the source as it is now"
```

- [ ] **Step 7: Frontend failing tests**

`AggregatesPanel.test.tsx`: extend the mock to `aggregatesApi: { preflight: vi.fn(), list: vi.fn(), create: vi.fn(), update: vi.fn() }` and add:

```tsx
  const ITEM = {
    dataset: { id: 9, name: 'by region', row_count: 720, refresh_interval_minutes: 60,
      aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } },
    last_error: null, attempts: 0,
  }

  it('edits an existing aggregate through PUT with the form prefilled', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([ITEM as never])
    vi.mocked(aggregatesApi.update).mockResolvedValue({} as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    fireEvent.click(await screen.findByRole('button', { name: /edit/i }))
    expect((screen.getByLabelText('region') as HTMLInputElement).checked).toBe(true)
    expect(screen.getByText(/sum\(amount\)/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Refresh every (minutes)'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
    await waitFor(() => expect(aggregatesApi.update).toHaveBeenCalledWith(5, 9, {
      grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum' }], refresh_interval_minutes: 30,
    }))
  })

  it('offers Rebuild on a "query changed" failure and sends an empty PUT', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([{ ...ITEM,
      last_error: "Not refreshed: the source's query changed since this aggregate was built; rebuild the aggregate to pick it up." } as never])
    vi.mocked(aggregatesApi.update).mockResolvedValue({} as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    fireEvent.click(await screen.findByRole('button', { name: /rebuild/i }))
    await waitFor(() => expect(aggregatesApi.update).toHaveBeenCalledWith(5, 9, {}))
  })
```

- [ ] **Step 8: Implement**

`api.ts`, in `aggregatesApi`:

```ts
  update: (datasetId: number, aggId: number, body: { grain?: string[];
    measures?: { column: string; agg: string; name?: string }[]; refresh_interval_minutes?: number | null }) =>
    api.put<Dataset>(`/datasets/${datasetId}/aggregates/${aggId}`, body).then(r => r.data),
```

`AggregatesPanel.tsx`: add `const [editing, setEditing] = useState<AggregateListItem | null>(null)`. An `Edit` button per row sets `editing`, `grain` (from `aggregate_spec.grain`), `measures` (`{column, agg}` from the spec), `every` (interval or ''), and `name` (display only; the name input is disabled while editing). The submit button reads `Save changes` while editing and calls `aggregatesApi.update(datasetId, editing.dataset.id, { grain, measures, refresh_interval_minutes: every ? Number(every) : null })`; a `Cancel` button clears the edit state. A `Rebuild` button appears on a row whose `last_error` matches `/query changed|filter expression/` and calls `aggregatesApi.update(datasetId, it.dataset.id, {})`, then `load()`. Errors surface through the existing `error` state.

- [ ] **Step 9: Run; expected PASS**

Run: `cd frontend && npx vitest run src/components/dataset/AggregatesPanel.test.tsx`
Then `npx tsc --noEmit -p .` (or the project's typecheck script) must be clean.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/components/dataset/AggregatesPanel.tsx frontend/src/components/dataset/AggregatesPanel.test.tsx
git commit -m "feat(aggregates): edit and rebuild from the Aggregates tab"
```

---

### Task 6: Overlap notice on the Row security form (ticket 11)

**Files:**
- Modify: `backend/app/routers/admin.py` (LF): `rule_preflight`
- Modify: `frontend/src/services/api.ts` (LF): `adminRlsRulesApi.preflight`
- Modify: `frontend/src/pages/admin/AdminRowSecurityRules.tsx` (check blob)
- Test: `backend/tests/test_column_security.py` (LF) or `backend/tests/test_rls_admin*.py` if one exists (check; prefer the existing admin-rules module); `frontend/src/pages/admin/AdminRowSecurityRules.test.tsx`

**Interfaces:**
- Produces: `GET /admin/row-security-rules/preflight?role_id=&dataset_id=&filter_expr=` → `{"columns": [str], "denied": [str]}`. Org admin only. Declared ABOVE `/row-security-rules/{rule_id}` routes (literal before param; see the memory on route order).
- Produces: `adminRlsRulesApi.preflight(role_id, dataset_id, filter_expr)`.

- [ ] **Step 1: Failing backend test**

```python
@pytest.mark.asyncio
async def test_rule_preflight_names_the_columns_a_rule_reads_that_the_role_cannot_see(
        client, auth_headers, db_session, two_orgs, salary_ds):
    ds, _ = await _setup(db_session, two_orgs["a"]["org"], salary_ds)   # role 'no-salary' denied ['salary']
    from sqlalchemy import select
    role = (await db_session.execute(select(Role).where(Role.name == "no-salary"))).scalar_one()
    r = await client.get("/api/v1/admin/row-security-rules/preflight",
                         params={"role_id": role.id, "dataset_id": ds.id,
                                 "filter_expr": "salary >= 85000 and dept == 'Eng'"},
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json() == {"columns": ["dept", "salary"], "denied": ["salary"]}


@pytest.mark.asyncio
async def test_rule_preflight_is_admin_only_and_org_scoped(client, db_session, two_orgs, salary_ds, auth_headers):
    ds, restricted_headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await client.get("/api/v1/admin/row-security-rules/preflight",
                         params={"role_id": 1, "dataset_id": ds.id, "filter_expr": "dept == 'Eng'"},
                         headers=restricted_headers)
    assert r.status_code in (401, 403)
    r = await client.get("/api/v1/admin/row-security-rules/preflight",
                         params={"role_id": 1, "dataset_id": ds.id, "filter_expr": "dept == 'Eng'"},
                         headers=auth_headers["b"])
    assert r.status_code == 404
```

- [ ] **Step 2: Run; expected FAIL (404 / 405)**

- [ ] **Step 3: Endpoint**

In `routers/admin.py`, placed before any `/row-security-rules/{rule_id}` route:

```python
@router.get("/row-security-rules/preflight")
async def rule_preflight(
    role_id: int, dataset_id: int, filter_expr: str,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin),
):
    """What a rule reads, and which of those columns the role cannot see.

    Informational: the row rule is still evaluated over every column and the
    role receives the rows it selects, never the column itself (widget_data
    applies RLS before column security). This tells the admin that at the
    moment they type it. Same parser as evaluation, so it cannot drift."""
    from ..core.rls import apply_user_context
    from ..models.models import ColumnSecurityRule
    from ..services.sql_expr import expression_columns
    role = await db.get(Role, role_id)
    check_org(role, current_user, "Role not found")
    dataset = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                                .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(dataset, current_user, "Dataset not found")
    expr = apply_user_context(filter_expr, email="validator@example.com", user_id=0,
                              org_id=0, org_name="validator-org") or filter_expr
    known = {c.name for c in dataset.columns}
    try:
        columns = sorted(expression_columns(expr, known))
    except Exception:  # noqa: BLE001 -- an unparsable draft reads nothing yet
        columns = []
    rule = (await db.execute(select(ColumnSecurityRule).where(
        ColumnSecurityRule.role_id == role_id, ColumnSecurityRule.dataset_id == dataset_id))).scalar_one_or_none()
    denied = set(rule.denied_columns or []) if rule else set()
    return {"columns": columns, "denied": sorted(c for c in columns if c in denied)}
```

Verify `expression_columns`'s real signature and return type in `services/sql_expr.py` before use.

- [ ] **Step 4: Run; expected PASS**, then commit the backend:

```bash
git add backend/app/routers/admin.py backend/tests/test_column_security.py
git commit -m "feat(admin): row-security preflight names the columns a rule reads and which the role cannot see"
```

- [ ] **Step 5: Frontend failing test**

In `AdminRowSecurityRules.test.tsx`, add `preflight: vi.fn().mockResolvedValue({ columns: [], denied: [] })` to the `adminRlsRulesApi` mock, then:

```tsx
describe('overlap notice', () => {
  it('tells the admin when the rule reads a column the role cannot see', async () => {
    vi.mocked(adminRlsRulesApi.preflight).mockResolvedValue({ columns: ['region'], denied: ['region'] })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /new rule/i }))
    fireEvent.change(screen.getByPlaceholderText("region == 'North'"), { target: { value: "region == 'North'" } })
    // 300 ms debounce inside a 1 s default findBy is the load-flake shape; give it room.
    expect(await screen.findByText(/reads region, which this role cannot see/i, {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText(/the rule still applies/i)).toBeInTheDocument()
    await waitFor(() => expect(adminRlsRulesApi.preflight).toHaveBeenCalledWith(1, 1, "region == 'North'"))
  })
})
```

Check the real "new rule" button label in the page and adjust the query.

- [ ] **Step 6: Implement**

`api.ts`:

```ts
  preflight: (role_id: number, dataset_id: number, filter_expr: string) =>
    api.get<{ columns: string[]; denied: string[] }>('/admin/row-security-rules/preflight',
      { params: { role_id, dataset_id, filter_expr } }).then(r => r.data),
```

`RuleModal`: a `const [overlap, setOverlap] = useState<string[]>([])` and an effect on `[roleId, datasetId, filterExpr]` that, when all three are set, debounces 300 ms, calls `adminRlsRulesApi.preflight(roleId, datasetId, filterExpr)`, and stores `denied`; errors leave the notice empty (the save validates anyway). Render under the textarea, before the help text:

```tsx
{overlap.length > 0 && (
  <div role="note" style={{ fontSize: 11, padding: '6px 8px', borderRadius: 6, marginBottom: 8,
    background: 'color-mix(in srgb, var(--accent) 12%, transparent)', border: '1px solid var(--border)' }}>
    This rule reads {overlap.join(', ')}, which this role cannot see. The rule still applies:
    the role gets the rows it selects and never the column.
  </div>
)}
```

- [ ] **Step 7: Run; expected PASS**

Run: `cd frontend && npx vitest run src/pages/admin/AdminRowSecurityRules.test.tsx` and the typecheck.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/pages/admin/AdminRowSecurityRules.tsx frontend/src/pages/admin/AdminRowSecurityRules.test.tsx
git commit -m "feat(admin): notice when a row rule reads a column the role cannot see"
```

---

### Task 7: Disclosure in the report builder (ticket 1)

**Files:**
- Create: `frontend/src/lib/aggregateDisclosure.ts` (LF)
- Create: `frontend/src/lib/aggregateDisclosure.test.ts` (LF) — a new test FILE: bump the frontend test file count in `ARCHITECTURE.md` and `ARCHITECTURE.html` in the same commit
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx` (check blob): dataset select options (~968-980), aggregation hint (~1705-1708)
- Modify: `frontend/src/pages/ReportBuilder.tsx` (check blob): Datasets sidebar (~2025-2046)

**Interfaces:**
- Consumes: `Dataset.aggregate_of_dataset_id`, `Dataset.aggregate_spec` (`services/api.ts:168-169`), `roleValues.measure`, `agg`.
- Produces: `aggregationWarning(ds: Dataset | undefined, measure: string, aggregation: string): string | null` and `PRE_AGGREGATED_HINT` (the tooltip copy).

- [ ] **Step 1: Failing helper tests**

```ts
import { describe, it, expect } from 'vitest'
import { aggregationWarning, PRE_AGGREGATED_HINT } from './aggregateDisclosure'
import type { Dataset } from '../services/api'

const agg = { id: 9, name: 'by region', aggregate_of_dataset_id: 5,
  aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } } as unknown as Dataset
const plain = { id: 5, name: 'orders' } as unknown as Dataset

describe('aggregationWarning', () => {
  it('is silent on an ordinary dataset', () => {
    expect(aggregationWarning(plain, 'amount', 'avg')).toBeNull()
    expect(aggregationWarning(undefined, 'amount', 'count')).toBeNull()
  })
  it('warns that avg over a derived measure averages sums', () => {
    expect(aggregationWarning(agg, 'amount_sum', 'avg')).toMatch(/average of sums.*sum\(amount_sum\) \/ sum\(row_count\)/)
  })
  it('warns that count counts groups, with or without a measure', () => {
    expect(aggregationWarning(agg, '', 'count')).toMatch(/counts groups, not rows.*sum\(row_count\)/)
    expect(aggregationWarning(agg, 'amount_sum', 'count_distinct')).toMatch(/counts groups/)
  })
  it('is silent for sum, min and max, which re-aggregate correctly', () => {
    expect(aggregationWarning(agg, 'amount_sum', 'sum')).toBeNull()
    expect(aggregationWarning(agg, 'row_count', 'sum')).toBeNull()
  })
  it('has one sentence of hint copy', () => {
    expect(PRE_AGGREGATED_HINT).toMatch(/row_count/)
  })
})
```

- [ ] **Step 2: Run; expected FAIL (module not found)**

- [ ] **Step 3: Helper**

```ts
import type { Dataset } from '../services/api'

/** Shown wherever an aggregate dataset is named in the builder. */
export const PRE_AGGREGATED_HINT =
  'Pre-aggregated: each row is a group. Measures are already summed; an average is x_sum / row_count.'

/**
 * The consumption-side half of the aggregate design: the Aggregates tab says
 * measures are pre-aggregated, and now the builder does too, at the moment an
 * author picks an aggregation that does not re-aggregate correctly. `avg` over
 * `amount_sum` is an average of sums; `count` counts groups, not rows -- a KPI
 * can read "2 orders" where the truth is 5, with no error anywhere.
 */
export function aggregationWarning(ds: Dataset | undefined, measure: string, aggregation: string): string | null {
  const spec = ds?.aggregate_spec
  if (!ds?.aggregate_of_dataset_id || !spec) return null
  if (aggregation === 'count' || aggregation === 'count_distinct') {
    return 'On a pre-aggregated dataset this counts groups, not rows. For the row count use sum(row_count).'
  }
  const derived = new Set(spec.measures.map(m => m.name))
  if (aggregation === 'avg' && derived.has(measure)) {
    return `On a pre-aggregated dataset this is an average of sums, not of rows. For the true average use sum(${measure}) / sum(row_count).`
  }
  return null
}
```

- [ ] **Step 4: Wire it**

`WidgetConfigPanel.tsx`: compute `const activeDs = (datasetId && datasets?.[datasetId]) ? datasets[datasetId] : (primaryDatasetId && datasets?.[primaryDatasetId]) ? datasets[primaryDatasetId] : undefined` near `effectiveCols`; in the Dataset select, append ` · pre-aggregated` to the option label when `ds.aggregate_of_dataset_id`; under the aggregation hint `<div>` (line ~1705) add:

```tsx
{aggregationWarning(activeDs, roleValues.measure ?? '', agg) && (
  <div role="note" style={{ fontSize:10, color:'var(--accent)', marginTop:4 }}>
    {aggregationWarning(activeDs, roleValues.measure ?? '', agg)}
  </div>
)}
```

`ReportBuilder.tsx`: in both sidebar rows, after the name span, when `datasets[id]?.aggregate_of_dataset_id`:

```tsx
<span title={PRE_AGGREGATED_HINT} style={{ fontSize:9, color:'var(--accent)', background:'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>Σ pre-aggregated</span>
```

- [ ] **Step 5: A render test on the panel**

In the existing `frontend/src/components/report/settingsTabs.test.tsx`, which already renders `WidgetConfigPanel` through a helper (read its `renderPanel`/`render(...)` call and the props it passes; reuse them, adding the two props below), add:

```tsx
describe('pre-aggregated disclosure', () => {
  const aggregateDataset = {
    id: 9, name: 'orders by region', row_count: 720, col_count: 4, file_size: 0,
    created_at: '', updated_at: '', calculated_columns: [], measures: [],
    column_meta: {}, column_formats: {}, mode: 'import', aggregate_of_dataset_id: 5,
    aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] },
    columns: [
      { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {}, semantic_type: null },
      { id: 2, name: 'amount_sum', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
      { id: 3, name: 'row_count', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
    ],
  } as unknown as Dataset

  const renderBar = (aggregation: string) => renderPanel({
    widget: { id: 'w1', type: 'bar', title: '', config: { dimension: 'region', measure: 'amount_sum', aggregation } },
    datasets: { 9: aggregateDataset }, primaryDatasetId: 9, columns: aggregateDataset.columns,
  })

  it('warns when avg is chosen over a derived measure', () => {
    renderBar('avg')
    expect(screen.getByRole('note')).toHaveTextContent(/average of sums/)
  })
  it('is silent for sum', () => {
    renderBar('sum')
    expect(screen.queryByRole('note')).toBeNull()
  })
})
```

If the file's existing render helper has a different name or prop shape, adapt the two calls above to it; the assertions stay.

- [ ] **Step 6: Run everything; bump the doc counts**

Run: `cd frontend && npx vitest run src/lib/aggregateDisclosure.test.ts src/components/report/settingsTabs.test.tsx` and the typecheck. Then `cd backend && .venv/Scripts/python -m pytest tests/test_architecture_doc.py -q` — it will name the stale frontend-test-file count; update the number in both `ARCHITECTURE.md` and `ARCHITECTURE.html` (both LF) and rerun until green.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/aggregateDisclosure.ts frontend/src/lib/aggregateDisclosure.test.ts frontend/src/components/report/WidgetConfigPanel.tsx frontend/src/pages/ReportBuilder.tsx frontend/src/components/report/settingsTabs.test.tsx ARCHITECTURE.md ARCHITECTURE.html
git commit -m "feat(builder): say when a dataset is pre-aggregated and when an aggregation would mislead"
```

---

## Self-review

- **Spec coverage:** tickets 1 (Task 7), 2 and 3 (Task 3), 4 (Task 4), 5 and 10 (Task 5), 6 and 7 (Task 1), 8 and 9 (Task 2), 11 (Task 6). Every item in the approved section has a task.
- **Placeholders:** the only open-ended instructions are verification steps ("check the real signature", "check the button label") where the plan cannot see the file; each names exactly what to check.
- **Type consistency:** `discard_dataset_artifacts(db, datasets)` (Task 2) is called with lists of `Dataset` in both routers; `_build_aggregate_file` (Task 5) returns the six-tuple its two callers unpack; `aggregatesApi.update(datasetId, aggId, body)` matches both frontend tests; `adminRlsRulesApi.preflight(role_id, dataset_id, filter_expr)` matches the test's `toHaveBeenCalledWith(1, 1, ...)`; `aggregationWarning(ds, measure, aggregation)` matches the helper tests and the panel wiring.
- **Ordering:** Task 3 removes the export-policy copy before Task 5 extracts the builder, so the extracted helper never carries the copy. Task 2's helper is what Task 5's old-file cleanup could reuse, but a single unlink pair is clearer inline there.
