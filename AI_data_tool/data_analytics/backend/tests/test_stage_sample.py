"""Stage 3 — the stage that actually reads rows from a source.

This is the connective tissue: profile, infer_keys and infer_semantic all read
the sample cache, so if nothing populates it from a real source the rest of the
pipeline is a correct implementation of nothing.

Two properties matter most:

  * masking happens BEFORE caching, and classification happens before masking.
    Get that order wrong and either raw personal data lands on disk, or the
    classifier ends up classifying the mask (a masked email no longer looks like
    an email, so every PII column would come back unclassified);

  * one unreadable table must not cost the other nineteen their metadata.
"""
import pandas as pd
import pytest

from app.models.models import Dataset, DataSource, DatasetColumn, Organization
from app.services.metadata import sync


class RecordingCache:
    def __init__(self):
        self.samples = {}
        self.evicted = []

    def put_sample(self, dataset_id, rows):
        self.samples[dataset_id] = rows

    def get_sample(self, dataset_id):
        return self.samples.get(dataset_id, [])

    def has_sample(self, dataset_id):
        return dataset_id in self.samples

    def evict_if_over_budget(self):
        return self.evicted

    def overlap(self, *a):
        return 0.0

    def distinct_count(self, *a):
        return 0

    def row_count(self, ds):
        return len(self.samples.get(ds, []))


@pytest.fixture
async def import_dataset(db_session, tmp_path, monkeypatch):
    """An uploaded dataset whose file holds real personal data."""
    from app.core.config import settings

    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    df = pd.DataFrame({
        "id": range(1, 31),
        "email": [f"user{i}@corp.com" for i in range(1, 31)],
        "city": ["Cairo", "Giza", "Luxor"] * 10,
    })
    path = tmp_path / "people.csv"
    df.to_csv(path, index=False)

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    ds = DataSource(name="files", type="postgresql", org_id=org.id)
    db_session.add(ds)
    await db_session.flush()

    dataset = Dataset(name="people", org_id=org.id, data_source_id=ds.id,
                      filename="people.csv", mode="import")
    db_session.add(dataset)
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=dataset.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=dataset.id, name="email", dtype="text"),
        DatasetColumn(dataset_id=dataset.id, name="city", dtype="categorical"),
    ])
    await db_session.commit()
    return {"org": org, "source": ds, "dataset": dataset}


class TestImportSampling:
    async def test_rows_reach_the_cache(self, db_session, import_dataset):
        cache = RecordingCache()
        await sync.run_sync(db_session, import_dataset["source"].id,
                            import_dataset["org"].id, cache=cache)
        await db_session.commit()

        rows = cache.samples[import_dataset["dataset"].id]
        assert len(rows) == 30
        assert set(rows[0]) == {"id", "email", "city"}

    async def test_personal_data_is_masked_before_it_is_cached(
        self, db_session, import_dataset
    ):
        """Nothing unmasked may be written to disk. This is the assertion that
        would fail if masking were moved after caching."""
        cache = RecordingCache()
        await sync.run_sync(db_session, import_dataset["source"].id,
                            import_dataset["org"].id, cache=cache)
        await db_session.commit()

        emails = [r["email"] for r in cache.samples[import_dataset["dataset"].id]]
        assert not any("user1@corp.com" == e for e in emails)
        assert all("@" in e for e in emails), "shape should survive masking"

    async def test_masking_preserves_cardinality(self, db_session, import_dataset):
        """30 distinct emails must stay 30 distinct tokens, or foreign-key
        overlap on this column would be meaningless."""
        cache = RecordingCache()
        await sync.run_sync(db_session, import_dataset["source"].id,
                            import_dataset["org"].id, cache=cache)
        await db_session.commit()

        emails = {r["email"] for r in cache.samples[import_dataset["dataset"].id]}
        assert len(emails) == 30

    async def test_non_personal_columns_are_untouched(self, db_session, import_dataset):
        cache = RecordingCache()
        await sync.run_sync(db_session, import_dataset["source"].id,
                            import_dataset["org"].id, cache=cache)
        await db_session.commit()

        cities = {r["city"] for r in cache.samples[import_dataset["dataset"].id]}
        assert cities == {"Cairo", "Giza", "Luxor"}

    async def test_the_email_column_is_classified_from_the_real_values(
        self, db_session, import_dataset
    ):
        """Classification runs BEFORE masking. Re-running it on the cached rows
        would classify the mask instead, and this column would come back with no
        semantic type at all."""
        cache = RecordingCache()
        await sync.run_sync(db_session, import_dataset["source"].id,
                            import_dataset["org"].id, cache=cache)
        await db_session.commit()

        from sqlalchemy import select
        columns = (await db_session.execute(
            select(DatasetColumn).where(
                DatasetColumn.dataset_id == import_dataset["dataset"].id)
        )).scalars().all()
        by_name = {c.name: c for c in columns}
        assert by_name["email"].semantic_type == "email"

    async def test_the_sample_stage_is_reported(self, db_session, import_dataset):
        cache = RecordingCache()
        run = await sync.run_sync(db_session, import_dataset["source"].id,
                                  import_dataset["org"].id, cache=cache)
        await db_session.commit()

        stages = {s["name"]: s for s in run.stages}
        assert stages["sample"]["status"] == "ok"
        assert stages["sample"]["detail"]["datasets_sampled"] == 1
        assert stages["sample"]["detail"]["pii_columns_masked"] == 1

    async def test_sample_runs_before_profile(self, db_session, import_dataset):
        """Statistics are computed FROM the cached rows, so profiling first
        would describe an empty cache."""
        cache = RecordingCache()
        run = await sync.run_sync(db_session, import_dataset["source"].id,
                                  import_dataset["org"].id, cache=cache)
        await db_session.commit()
        names = [s["name"] for s in run.stages]
        assert names.index("sample") < names.index("profile")

    async def test_statistics_are_produced_end_to_end(self, db_session, import_dataset):
        """The whole point: an upload becomes a profiled, typed catalog entry
        with no test seeding the cache by hand."""
        from sqlalchemy import select
        from app.models.models import ColumnStats

        cache = RecordingCache()
        await sync.run_sync(db_session, import_dataset["source"].id,
                            import_dataset["org"].id, cache=cache)
        await db_session.commit()

        stats = (await db_session.execute(select(ColumnStats))).scalars().all()
        assert len(stats) == 3
        city = [s for s in stats if s.top_k and
                any(e["value"] == "Cairo" for e in s.top_k)]
        assert city, "top_k should enumerate a low-cardinality column"


class TestResilience:
    async def test_a_missing_file_does_not_fail_the_stage(self, db_session, import_dataset):
        import_dataset["dataset"].filename = "gone.csv"
        await db_session.commit()

        cache = RecordingCache()
        run = await sync.run_sync(db_session, import_dataset["source"].id,
                                  import_dataset["org"].id, cache=cache)
        await db_session.commit()
        stages = {s["name"]: s for s in run.stages}
        assert stages["sample"]["status"] == "ok"
        assert stages["sample"]["detail"]["datasets_sampled"] == 0

    async def test_one_unreadable_table_does_not_cost_the_others(
        self, db_session, import_dataset, tmp_path, monkeypatch
    ):
        """A dropped or permission-revoked table is a normal event."""
        org = import_dataset["org"]
        broken = Dataset(name="broken", org_id=org.id,
                         data_source_id=import_dataset["source"].id,
                         filename="nope.csv", mode="import")
        db_session.add(broken)
        await db_session.commit()

        cache = RecordingCache()
        run = await sync.run_sync(db_session, import_dataset["source"].id,
                                  org.id, cache=cache)
        await db_session.commit()

        assert run.status == "ok"
        assert cache.samples[import_dataset["dataset"].id]

    async def test_directquery_without_config_falls_back_rather_than_raising(
        self, db_session, import_dataset
    ):
        """A DirectQuery dataset synced with no connection config (a scheduled
        run that could not resolve credentials) must degrade, not explode."""
        import_dataset["dataset"].mode = "directquery"
        import_dataset["dataset"].source_table = "people"
        await db_session.commit()

        cache = RecordingCache()
        run = await sync.run_sync(db_session, import_dataset["source"].id,
                                  import_dataset["org"].id, cache=cache,
                                  source_config=None)
        await db_session.commit()
        stages = {s["name"]: s for s in run.stages}
        assert stages["sample"]["status"] == "ok"


class TestSqlSampling:
    def test_builds_a_bounded_query_for_the_right_dialect(self, monkeypatch):
        """The SQL path is exercised without a live database by checking the
        query it would send."""
        from app.services.metadata import sample as sample_mod

        captured = {}

        def fake_build(table, *, family, strategy, n, row_count=None, **kw):
            captured.update(table=table, family=family, strategy=strategy, n=n)
            return f"SELECT * FROM {table} LIMIT {n}"

        monkeypatch.setattr(sample_mod, "build_sample_sql", fake_build)

        class FakeConn:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute(self, *a): return []

        class FakeEngine:
            def connect(self): return FakeConn()

        # sync imports get_engine from services.engines (layer 1) -- patching
        # the direct_query re-export would leave the real engine in play.
        monkeypatch.setattr("app.services.engines.get_engine",
                            lambda cfg: FakeEngine())

        dataset = type("D", (), {"source_table": "orders", "row_count": 5000})()
        rows = sync._sample_sql_dataset(dataset, {"type": "postgresql"}, 1000)

        assert rows == []
        assert captured["table"] == "orders"
        assert captured["family"] == "postgresql"
        assert captured["n"] == 1000

    def test_a_dataset_without_a_source_table_returns_none_not_empty(self):
        """None means "could not sample", which is NOT the same as an empty
        table. An empty list would be written to the cache as "this table has no
        rows" and would wrongly trip the deprecation heuristic; None leaves any
        previous sample alone."""
        dataset = type("D", (), {"source_table": None, "row_count": 0})()
        assert sync._sample_sql_dataset(dataset, {"type": "postgresql"}, 100) is None
