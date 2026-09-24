"""T6: drift -> cache invalidation, via a per-source cache epoch.

A drift-changed sync bumps DataSource.cache_epoch; an unchanged sync doesn't.
DirectQuery's cache key folds the epoch in, so a bump makes every existing
cache entry for that source unaddressable (the LRU evicts the orphans
naturally). File datasets with no DataSource behind them are untouched.
"""
import inspect

from sqlalchemy import create_engine, text

from app.models.models import (DataSource, Dataset, DatasetColumn,
                               Organization)
from app.services.direct_query import _directquery_cache_key


# ── DirectQuery cache key ────────────────────────────────────────────────────

class _Dataset:
    def __init__(self, data_source_id=1, source_table="sales", source_query=None):
        self.data_source_id = data_source_id
        self.source_table = source_table
        self.source_query = source_query


class TestDirectQueryCacheKey:
    def test_the_key_differs_between_epoch_0_and_epoch_1(self):
        k0 = _directquery_cache_key({}, _Dataset(), {"dimension": "region"}, "bar", None, 60, cache_epoch=0)
        k1 = _directquery_cache_key({}, _Dataset(), {"dimension": "region"}, "bar", None, 60, cache_epoch=1)
        assert k0 != k1

    def test_the_key_is_stable_for_the_same_epoch(self):
        k1 = _directquery_cache_key({}, _Dataset(), {"dimension": "region"}, "bar", None, 60, cache_epoch=3)
        k2 = _directquery_cache_key({}, _Dataset(), {"dimension": "region"}, "bar", None, 60, cache_epoch=3)
        assert k1 == k2

    def test_cache_epoch_defaults_to_zero(self):
        """Callers that don't know about epochs yet (or a source with no drift
        ever observed) get the same key as an explicit epoch=0."""
        k_default = _directquery_cache_key({}, _Dataset(), {"dimension": "region"}, "bar", None, 60)
        k_explicit = _directquery_cache_key({}, _Dataset(), {"dimension": "region"}, "bar", None, 60, cache_epoch=0)
        assert k_default == k_explicit


class TestFileDatasetCacheKeyUnaffected:
    """widget_data._widget_data_cache_key (the import/pandas path's own key
    builder) is deliberately left untouched -- a file dataset has no
    DataSource, so there is no epoch to fold in. Its signature carrying no
    cache_epoch parameter at all is the actual guarantee: nothing can pass one
    in even by accident."""

    def test_widget_data_cache_key_has_no_epoch_parameter(self):
        from app.services.widget_data import _widget_data_cache_key
        params = inspect.signature(_widget_data_cache_key).parameters
        assert "cache_epoch" not in params

    def test_repeated_calls_for_a_file_dataset_produce_the_same_key(self):
        from app.services.widget_data import _widget_data_cache_key
        k1 = _widget_data_cache_key("f.csv", (1.0, 100), {"a": 1}, "bar", None, None, None)
        k2 = _widget_data_cache_key("f.csv", (1.0, 100), {"a": 1}, "bar", None, None, None)
        assert k1 == k2


# ── Migration ────────────────────────────────────────────────────────────────

class TestMigration:
    def test_the_migrate_statement_adds_cache_epoch(self):
        import re

        text_ = open("app/main.py", encoding="utf-8-sig").read()
        assert re.search(
            r"ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS cache_epoch INTEGER NOT NULL DEFAULT 0",
            text_,
        )

    def test_data_source_model_has_a_zero_default_cache_epoch_column(self):
        col = DataSource.__table__.columns["cache_epoch"]
        assert col.nullable is False
        assert col.default.arg == 0


# ── catalog_sync.py's drift stage (connection-side) ─────────────────────────

class TestCatalogSyncDriftBumpsEpoch:
    async def test_a_drift_changed_sync_bumps_the_epoch(self, db_session, tmp_path, monkeypatch):
        from app.services.metadata import catalog_sync
        from app.services.metadata.cache import SampleCache

        db_path = tmp_path / "shop.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT)"))
            conn.execute(text("INSERT INTO customers VALUES (1, 'a@b.com')"))

        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        ds = DataSource(name="shop", type="sqlite", org_id=org.id, config={"filepath": str(db_path)})
        db_session.add(ds)
        await db_session.commit()

        monkeypatch.setattr(catalog_sync, "_engine_for", lambda cfg: engine)
        monkeypatch.setattr(catalog_sync, "_sampling_engine_for", lambda cfg: engine)
        cache = SampleCache(path=str(tmp_path / "cat.duckdb"), max_mb=32, namespace="o")
        cfg = {"type": "sqlite", "filepath": str(db_path)}

        assert ds.cache_epoch == 0
        # First run against a source with no prior SchemaVersion is itself a
        # (baseline) drift event -- see test_catalog_sync's own
        # test_a_second_unchanged_run_is_not_drift, which shows the FIRST run
        # writes a SchemaVersion row and a second identical run does not.
        await catalog_sync.run_catalog_sync(db_session, ds, cache=cache, source_config=cfg)
        await db_session.commit()
        after_first = ds.cache_epoch
        assert after_first == 1

        # Second run, unchanged schema: no drift, no bump.
        await catalog_sync.run_catalog_sync(db_session, ds, cache=cache, source_config=cfg)
        await db_session.commit()
        assert ds.cache_epoch == after_first

        # Change the schema, then sync again: drift, bump.
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE customers ADD COLUMN city TEXT"))
        await catalog_sync.run_catalog_sync(db_session, ds, cache=cache, source_config=cfg)
        await db_session.commit()
        assert ds.cache_epoch == after_first + 1

        cache.close()
        engine.dispose()


# ── sync.py's drift stage (dataset-side) ────────────────────────────────────

class FakeCache:
    def __init__(self, samples=None):
        self._samples = samples or {}

    def get_sample(self, dataset_id):
        return self._samples.get(dataset_id, [])

    def has_sample(self, dataset_id):
        return dataset_id in self._samples

    def overlap(self, cds, ccol, pds, pcol):
        return 0.0

    def distinct_count(self, dataset_id, column):
        return len({str(r.get(column)) for r in self._samples.get(dataset_id, [])
                    if r.get(column) is not None})

    def row_count(self, dataset_id):
        return len(self._samples.get(dataset_id, []))

    def put_sample(self, dataset_id, rows):
        self._samples[dataset_id] = rows

    def evict_if_over_budget(self):
        return []


class TestDatasetSyncDriftBumpsEpoch:
    async def test_a_drift_changed_sync_bumps_the_epoch(self, db_session):
        from app.services.metadata import sync

        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        ds = DataSource(name="warehouse", type="postgresql", org_id=org.id)
        db_session.add(ds)
        await db_session.flush()
        dataset = Dataset(name="customers", org_id=org.id, data_source_id=ds.id)
        db_session.add(dataset)
        await db_session.flush()
        db_session.add(DatasetColumn(dataset_id=dataset.id, name="id", dtype="integer"))
        await db_session.commit()

        assert ds.cache_epoch == 0
        await sync.run_sync(db_session, ds.id, org.id, cache=FakeCache())
        await db_session.commit()
        after_first = ds.cache_epoch
        assert after_first == 1

        await sync.run_sync(db_session, ds.id, org.id, cache=FakeCache())
        await db_session.commit()
        assert ds.cache_epoch == after_first

        db_session.add(DatasetColumn(dataset_id=dataset.id, name="email", dtype="text"))
        await db_session.commit()

        await sync.run_sync(db_session, ds.id, org.id, cache=FakeCache())
        await db_session.commit()
        assert ds.cache_epoch == after_first + 1

    async def test_a_dataset_with_no_data_source_is_unaffected(self, db_session):
        """A file (import-mode) dataset has no DataSource row behind it, so
        there is nothing for stage_drift's epoch-bump to touch -- calling it
        directly (bypassing discover, which would otherwise fail loudly on a
        data_source_id that points at nothing) must not raise."""
        from app.services.metadata.sync import SyncContext, stage_drift

        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()

        # A real DataSource row, because schema_versions.data_source_id is a
        # foreign key the test database now enforces (matching Postgres). The
        # POINT of this test is a dataset with nothing behind it, so the source
        # exists only to satisfy the constraint -- stage_drift never reads it,
        # and passing a dangling id instead would fail on the insert rather than
        # exercising the branch under test.
        source = DataSource(org_id=org.id, name="orphan", type="postgresql", config={})
        db_session.add(source)
        await db_session.flush()

        context = SyncContext(db_session, source.id, org.id, cache=FakeCache())
        context.schema_columns = [
            {"table": "customers", "name": "id", "dtype": "integer", "nullable": False},
        ]
        result = await stage_drift(context)
        assert result["changed"] is True   # baseline drift, no prior SchemaVersion
