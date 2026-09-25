"""The six-stage pipeline.

The property under test throughout: STAGES FAIL INDEPENDENTLY. A source that
blocks sampling, a warehouse that times out on one table, a GPU host that is
down — none of these should cost the other stages' output, and none should make
the run disappear. A sync_run row is always written, including when things went
badly, because a run that vanishes on failure is the opposite of observability.
"""
import pytest

from app.models.models import (Dataset, DataSource, DatasetColumn, Organization,
                               Relationship, SchemaVersion, SyncRun)
from app.services.metadata import store, sync


class FakeCache:
    """A sample cache backed by dicts."""

    def __init__(self, samples=None):
        self._samples = samples or {}

    def get_sample(self, dataset_id):
        return self._samples.get(dataset_id, [])

    def has_sample(self, dataset_id):
        return dataset_id in self._samples

    def overlap(self, cds, ccol, pds, pcol):
        child = {str(r.get(ccol)) for r in self._samples.get(cds, []) if r.get(ccol) is not None}
        parent = {str(r.get(pcol)) for r in self._samples.get(pds, []) if r.get(pcol) is not None}
        if not child:
            return 0.0
        return len(child & parent) / len(child)

    def distinct_count(self, dataset_id, column):
        return len({str(r.get(column)) for r in self._samples.get(dataset_id, [])
                    if r.get(column) is not None})

    def row_count(self, dataset_id):
        return len(self._samples.get(dataset_id, []))

    def put_sample(self, dataset_id, rows):
        self._samples[dataset_id] = rows

    def evict_if_over_budget(self):
        return []


@pytest.fixture
async def source(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    ds = DataSource(name="warehouse", type="postgresql", org_id=org.id)
    db_session.add(ds)
    await db_session.flush()

    customers = Dataset(name="customers", org_id=org.id, data_source_id=ds.id)
    orders = Dataset(name="orders", org_id=org.id, data_source_id=ds.id)
    db_session.add_all([customers, orders])
    await db_session.flush()

    db_session.add_all([
        DatasetColumn(dataset_id=customers.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=customers.id, name="status", dtype="categorical"),
        DatasetColumn(dataset_id=orders.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=orders.id, name="customer_id", dtype="integer"),
    ])
    await db_session.commit()
    return {"org": org, "source": ds, "customers": customers, "orders": orders}


def _samples(source):
    return {
        source["customers"].id: [
            {"id": i, "status": "active" if i % 2 else "churned"} for i in range(1, 21)
        ],
        source["orders"].id: [
            {"id": i, "customer_id": (i % 20) + 1} for i in range(1, 51)
        ],
    }


class TestHappyPath:
    async def test_all_stages_run_and_the_run_is_ok(self, db_session, source):
        run = await sync.run_sync(
            db_session, source["source"].id, source["org"].id,
            cache=FakeCache(_samples(source)),
        )
        await db_session.commit()

        assert run.status == "ok"
        names = [s["name"] for s in run.stages]
        assert names == ["discover", "sample", "profile", "infer_keys",
                         "infer_semantic", "drift"]
        assert all(s["status"] == "ok" for s in run.stages)

    async def test_statistics_are_persisted_with_top_k(self, db_session, source):
        await sync.run_sync(db_session, source["source"].id, source["org"].id,
                            cache=FakeCache(_samples(source)))
        await db_session.commit()

        from sqlalchemy import select
        from app.models.models import ColumnStats
        rows = (await db_session.execute(select(ColumnStats))).scalars().all()
        assert rows
        status_stats = [r for r in rows if r.top_k and
                        any(e["value"] in ("active", "churned") for e in r.top_k)]
        assert status_stats, "top_k was not computed for a low-cardinality column"

    async def test_sample_derived_statistics_are_marked_inexact(self, db_session, source):
        """Computed over a sample, not the table. Callers branch on this."""
        from sqlalchemy import select
        from app.models.models import ColumnStats

        await sync.run_sync(db_session, source["source"].id, source["org"].id,
                            cache=FakeCache(_samples(source)))
        await db_session.commit()
        rows = (await db_session.execute(select(ColumnStats))).scalars().all()
        assert all(r.exact is False for r in rows)

    async def test_the_real_foreign_key_is_proposed(self, db_session, source):
        from sqlalchemy import select

        await sync.run_sync(db_session, source["source"].id, source["org"].id,
                            cache=FakeCache(_samples(source)))
        await db_session.commit()

        rels = (await db_session.execute(select(Relationship))).scalars().all()
        assert len(rels) == 1
        assert rels[0].from_column == "customer_id"
        assert rels[0].to_column == "id"
        assert rels[0].source == "inferred"
        assert rels[0].evidence["overlap"] == 1.0

    async def test_the_first_run_records_a_schema_baseline(self, db_session, source):
        from sqlalchemy import select

        await sync.run_sync(db_session, source["source"].id, source["org"].id,
                            cache=FakeCache(_samples(source)))
        await db_session.commit()

        versions = (await db_session.execute(select(SchemaVersion))).scalars().all()
        assert len(versions) == 1
        assert versions[0].diff["is_baseline"] is True

    async def test_a_second_unchanged_run_records_no_new_version(self, db_session, source):
        from sqlalchemy import select

        cache = FakeCache(_samples(source))
        await sync.run_sync(db_session, source["source"].id, source["org"].id, cache=cache)
        await db_session.commit()
        await sync.run_sync(db_session, source["source"].id, source["org"].id, cache=cache)
        await db_session.commit()

        versions = (await db_session.execute(select(SchemaVersion))).scalars().all()
        assert len(versions) == 1, "an unchanged schema must not look like drift"


class TestStageIsolation:
    async def test_one_failing_stage_does_not_abort_the_run(self, db_session, source, monkeypatch):
        async def boom(context):
            raise RuntimeError("warehouse timed out")

        monkeypatch.setattr(sync, "stage_profile", boom)
        run = await sync.run_sync(db_session, source["source"].id, source["org"].id,
                                  cache=FakeCache(_samples(source)))
        await db_session.commit()

        stages = {s["name"]: s for s in run.stages}
        assert stages["profile"]["status"] == "failed"
        assert "warehouse timed out" in stages["profile"]["error"]
        # Everything downstream still ran.
        assert stages["infer_keys"]["status"] == "ok"
        assert stages["drift"]["status"] == "ok"
        assert run.status == "partial"

    async def test_a_failed_run_is_still_persisted(self, db_session, source, monkeypatch):
        from sqlalchemy import select

        async def boom(context):
            raise RuntimeError("no connection")

        monkeypatch.setattr(sync, "stage_discover", boom)
        await sync.run_sync(db_session, source["source"].id, source["org"].id,
                            cache=FakeCache())
        await db_session.commit()

        runs = (await db_session.execute(select(SyncRun))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "no connection" in runs[0].error

    async def test_discover_failing_stops_the_run(self, db_session, source, monkeypatch):
        """Without tables there is nothing for any other stage to describe."""
        async def boom(context):
            raise RuntimeError("permission denied")

        monkeypatch.setattr(sync, "stage_discover", boom)
        run = await sync.run_sync(db_session, source["source"].id, source["org"].id,
                                  cache=FakeCache())
        await db_session.commit()
        assert [s["name"] for s in run.stages] == ["discover"]

    async def test_inference_is_skipped_when_nothing_was_sampled(self, db_session, source):
        """Running it against an empty cache would score every overlap 0.0 and
        report 'no relationships found' — a wrong answer wearing the clothes of
        a real one."""
        run = await sync.run_sync(db_session, source["source"].id, source["org"].id,
                                  cache=FakeCache({}))
        await db_session.commit()

        stages = {s["name"]: s for s in run.stages}
        assert stages["infer_keys"]["status"] == "skipped"
        assert stages["infer_keys"]["detail"]["reason"] == "no cached samples"
        assert stages["drift"]["status"] == "ok", "drift does not depend on samples"

    async def test_every_stage_records_a_duration(self, db_session, source):
        run = await sync.run_sync(db_session, source["source"].id, source["org"].id,
                                  cache=FakeCache(_samples(source)))
        await db_session.commit()
        for stage in run.stages:
            if stage["status"] != "skipped":
                assert "ms" in stage


class TestProvenanceAcrossRuns:
    async def test_a_confirmed_relationship_survives_a_resync(self, db_session, source):
        """The acceptance criterion of the whole layer, exercised end to end."""
        from sqlalchemy import select

        cache = FakeCache(_samples(source))
        await sync.run_sync(db_session, source["source"].id, source["org"].id, cache=cache)
        await db_session.commit()

        rel = (await db_session.execute(select(Relationship))).scalars().one()
        await store.confirm_relationship(db_session, rel.id, org_id=source["org"].id)
        await db_session.commit()

        await sync.run_sync(db_session, source["source"].id, source["org"].id, cache=cache)
        await db_session.commit()

        after = (await db_session.execute(select(Relationship))).scalars().one()
        assert after.source == "confirmed"
        assert after.confidence == 1.0


class TestLlmIsOptional:
    async def test_run_completes_with_no_llm_client(self, db_session, source):
        run = await sync.run_sync(db_session, source["source"].id, source["org"].id,
                                  cache=FakeCache(_samples(source)), llm_client=None)
        await db_session.commit()
        stages = {s["name"]: s for s in run.stages}
        assert stages["infer_semantic"]["status"] == "ok"
        assert stages["infer_semantic"]["detail"]["llm_used"] is False

    async def test_consent_off_means_no_descriptions(self, db_session, source):
        class Client:
            last_error = None

            async def complete_json(self, *a, **kw):
                raise AssertionError("must not be called without consent")

        run = await sync.run_sync(
            db_session, source["source"].id, source["org"].id,
            cache=FakeCache(_samples(source)), llm_client=Client(), allow_llm=False,
        )
        await db_session.commit()
        assert run.status == "ok"

    async def test_an_unreachable_model_does_not_fail_the_stage(self, db_session, source):
        class DeadClient:
            last_error = "ConnectError"

            async def complete_json(self, *a, **kw):
                return None

        run = await sync.run_sync(
            db_session, source["source"].id, source["org"].id,
            cache=FakeCache(_samples(source)), llm_client=DeadClient(), allow_llm=True,
        )
        await db_session.commit()
        stages = {s["name"]: s for s in run.stages}
        assert stages["infer_semantic"]["status"] == "ok"
        assert stages["infer_semantic"]["detail"]["descriptions"] == 0
