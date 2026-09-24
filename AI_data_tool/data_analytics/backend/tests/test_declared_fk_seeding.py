"""T2 -- declared-FK seeding for DirectQuery datasets: sync.py's Relationship
pipeline (per-Dataset), not catalog_sync.py's SourceRelationship one
(per-connection, whole-database). catalog_sync.py already read real foreign
keys and seeded `declared` rows via `introspect.py` + `_seed_declared_keys`;
this file covers the other pipeline, which had the provenance ladder
(store.upsert_declared_relationship) and the agent join whitelist
(agent/context.py already accepts DECLARED) but never actually called
`inspect(engine).get_foreign_keys(...)` to populate it -- see
`sync._seed_declared_keys` / `sync._read_declared_fks`.

A real FOREIGN KEY in the source's own schema is a fact, not a guess: reading
it and writing it through with `source='declared'` means value-overlap
inference only has to find the joins nobody bothered to declare. Seeding wins
over inference -- an existing inferred row for the same edge is upgraded, and
a declared row is never downgraded by a later inference pass.
"""
import pytest
from sqlalchemy import create_engine, text

from app.models.models import (Dataset, DataSource, DatasetColumn,
                                Organization, Relationship)
from app.services.metadata import sync
from app.services.metadata import store


class RecordingCache:
    """A cache stand-in whose overlap always reads 0.0, so nothing here is
    mistaken for a value-overlap inference result -- every relationship this
    test sees came from declared-FK seeding, not from `infer_keys`."""

    def __init__(self):
        self.samples = {}

    def put_sample(self, dataset_id, rows):
        self.samples[dataset_id] = rows

    def get_sample(self, dataset_id):
        return self.samples.get(dataset_id, [])

    def has_sample(self, dataset_id):
        return dataset_id in self.samples

    def evict_if_over_budget(self):
        return []

    def overlap(self, *a):
        return 0.0

    def distinct_count(self, *a):
        return 0

    def row_count(self, ds):
        return len(self.samples.get(ds, []))


@pytest.fixture
def live_db(tmp_path):
    """A scratch SQLite source with one single-column FK and one composite FK."""
    path = tmp_path / "shop.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL
            )"""))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                status TEXT
            )"""))
        # A composite FK -- out of scope for v1's single-column relationship
        # rows, and must be skipped rather than truncated to one column.
        conn.execute(text("""
            CREATE TABLE order_lines (
                order_id INTEGER NOT NULL,
                line_no INTEGER NOT NULL,
                sku TEXT,
                PRIMARY KEY (order_id, line_no),
                FOREIGN KEY (order_id, line_no) REFERENCES orders(id, id)
            )"""))
        for i in range(1, 6):
            conn.execute(text("INSERT INTO customers VALUES (:i, :e)"),
                         {"i": i, "e": f"user{i}@corp.com"})
        for i in range(1, 6):
            conn.execute(text("INSERT INTO orders VALUES (:i, :c, :s)"),
                         {"i": i, "c": i, "s": "paid"})
    engine.dispose()
    return str(path)


@pytest.fixture
async def scenario(db_session, live_db, monkeypatch):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    source = DataSource(name="shop", type="sqlite", org_id=org.id,
                        config={"filepath": live_db})
    db_session.add(source)
    await db_session.flush()

    customers = Dataset(name="Customers", org_id=org.id, data_source_id=source.id,
                        mode="directquery", source_table="customers")
    orders = Dataset(name="Orders", org_id=org.id, data_source_id=source.id,
                     mode="directquery", source_table="orders")
    # Imported too, so its composite FK is actually READ and rejected by the
    # single-column check -- rather than simply never being looked at because
    # no Dataset points at order_lines at all.
    order_lines = Dataset(name="OrderLines", org_id=org.id, data_source_id=source.id,
                          mode="directquery", source_table="order_lines")
    db_session.add_all([customers, orders, order_lines])
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=customers.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=customers.id, name="email", dtype="text"),
        DatasetColumn(dataset_id=orders.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=orders.id, name="customer_id", dtype="integer"),
        DatasetColumn(dataset_id=orders.id, name="status", dtype="text"),
        DatasetColumn(dataset_id=order_lines.id, name="order_id", dtype="integer"),
        DatasetColumn(dataset_id=order_lines.id, name="line_no", dtype="integer"),
        DatasetColumn(dataset_id=order_lines.id, name="sku", dtype="text"),
    ])
    await db_session.commit()

    engine = create_engine(f"sqlite:///{live_db}")
    # Patch where the call happens: sync/catalog_sync import get_engine from
    # services.engines (layer 1), not through the direct_query re-export.
    monkeypatch.setattr("app.services.engines.get_engine", lambda cfg: engine)

    yield {"org": org, "source": source, "customers": customers, "orders": orders,
           "order_lines": order_lines, "cfg": {"type": "sqlite", "filepath": live_db}}
    engine.dispose()


async def _run(db_session, scenario, cache=None):
    cache = cache or RecordingCache()
    return await sync.run_sync(
        db_session, scenario["source"].id, scenario["org"].id, cache=cache,
        source_config=scenario["cfg"],
    )


class TestDeclaredSeeding:
    async def test_fk_on_a_scratch_sqlite_source_becomes_a_declared_row(
        self, db_session, scenario
    ):
        run = await _run(db_session, scenario)
        await db_session.commit()

        stages = {s["name"]: s for s in run.stages}
        assert stages["infer_keys"]["status"] == "ok"
        assert stages["infer_keys"]["detail"]["declared"] == 1

        rel = (await db_session.execute(
            Relationship.__table__.select().where(
                Relationship.org_id == scenario["org"].id)
        )).mappings().all()
        assert len(rel) == 1
        row = rel[0]
        assert row["from_dataset_id"] == scenario["orders"].id
        assert row["from_column"] == "customer_id"
        assert row["to_dataset_id"] == scenario["customers"].id
        assert row["to_column"] == "id"
        assert row["source"] == "declared"
        assert row["confidence"] == 1.0

    async def test_composite_fk_is_skipped_not_written(self, db_session, scenario):
        """order_lines' FK is READ (it has a Dataset pointing at it) and
        rejected for being composite -- not silently ignored because nothing
        was looking at it, and not truncated to its first column, which would
        produce a join that looks declared but is wrong."""
        run = await _run(db_session, scenario)
        await db_session.commit()

        stages = {s["name"]: s for s in run.stages}
        # Only orders.customer_id -> customers.id: order_lines' composite key
        # contributed nothing.
        assert stages["infer_keys"]["detail"]["declared"] == 1

        rel = (await db_session.execute(
            Relationship.__table__.select().where(
                Relationship.org_id == scenario["org"].id)
        )).mappings().all()
        assert all(r["from_column"] != "order_id" for r in rel)
        assert len(rel) == 1

    async def test_inferred_row_is_upgraded_to_declared(self, db_session, scenario):
        """An existing inferred proposal for the SAME edge must become
        declared on the next sync, not sit alongside a duplicate declared row."""
        existing = await store.upsert_inferred_relationship(
            db_session, org_id=scenario["org"].id,
            from_dataset_id=scenario["orders"].id, from_column="customer_id",
            to_dataset_id=scenario["customers"].id, to_column="id",
            confidence=0.62, evidence={"overlap": 0.62},
        )
        await db_session.commit()
        assert existing.source == "inferred"
        edge_id = existing.id

        await _run(db_session, scenario)
        await db_session.commit()

        rel = (await db_session.execute(
            Relationship.__table__.select().where(
                Relationship.org_id == scenario["org"].id)
        )).mappings().all()
        assert len(rel) == 1
        assert rel[0]["id"] == edge_id
        assert rel[0]["source"] == "declared"
        assert rel[0]["confidence"] == 1.0

    async def test_a_declared_row_is_never_downgraded_by_inference(
        self, db_session, scenario
    ):
        """The reverse must never happen: once declared, a later inference
        pass proposing the same edge at lower confidence must not win."""
        await _run(db_session, scenario)
        await db_session.commit()

        # A resync-time inference pass proposing the very same edge, at
        # far-from-certain confidence -- the shape a value-overlap re-scan
        # would actually produce, since it has no idea the FK was declared.
        stored = await store.upsert_inferred_relationship(
            db_session, org_id=scenario["org"].id,
            from_dataset_id=scenario["orders"].id, from_column="customer_id",
            to_dataset_id=scenario["customers"].id, to_column="id",
            confidence=0.55, evidence={"overlap": 0.55},
        )
        await db_session.commit()

        assert stored.source == "declared"
        assert stored.confidence == 1.0

    async def test_resync_is_idempotent_no_duplicate_rows(self, db_session, scenario):
        await _run(db_session, scenario)
        await db_session.commit()
        await _run(db_session, scenario)
        await db_session.commit()

        rel = (await db_session.execute(
            Relationship.__table__.select().where(
                Relationship.org_id == scenario["org"].id)
        )).mappings().all()
        assert len(rel) == 1

    async def test_import_mode_datasets_never_reach_the_live_source(
        self, db_session, scenario, monkeypatch
    ):
        """A source with no live table behind any of its datasets (all
        mode='import') must never hand anything to the FK reader -- there is
        nothing there to introspect. Exercised directly against the stage
        (rather than through run_sync) so this is not entangled with whether
        an import-mode dataset with no file happens to produce a sample."""
        scenario["orders"].mode = "import"
        scenario["orders"].source_table = None
        scenario["customers"].mode = "import"
        scenario["customers"].source_table = None
        await db_session.commit()

        def _boom(cfg, names):
            raise AssertionError("should not read FKs when nothing is directquery")

        monkeypatch.setattr(sync, "_read_declared_fks", _boom)

        context = sync.SyncContext(
            db_session, scenario["source"].id, scenario["org"].id,
            cache=RecordingCache(), source_config=scenario["cfg"],
        )
        context.datasets = [scenario["customers"], scenario["orders"]]
        context.columns_by_dataset = {
            scenario["customers"].id: [], scenario["orders"].id: [],
        }

        detail = await sync.stage_infer_keys(context)
        assert detail["declared"] == 0


class TestSeedingFailureDoesNotKillInference:
    async def test_stage_survives_seeding_exception(self, db_session, scenario, monkeypatch):
        """A seeding blow-up (engine build, catalog read) must not take
        value-overlap inference down with it."""
        async def _boom(context):
            raise RuntimeError("source engine unreachable")

        monkeypatch.setattr(sync, "_seed_declared_keys", _boom)

        context = sync.SyncContext(
            db_session, scenario["source"].id, scenario["org"].id,
            cache=RecordingCache(), source_config=scenario["cfg"],
        )
        context.datasets = [scenario["customers"], scenario["orders"]]
        context.columns_by_dataset = {
            scenario["customers"].id: [], scenario["orders"].id: [],
        }

        detail = await sync.stage_infer_keys(context)
        assert detail["declared"] == 0
