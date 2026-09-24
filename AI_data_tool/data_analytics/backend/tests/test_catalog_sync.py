"""Describing a database from its CONNECTION, with no datasets involved.

This is the distinction the whole module exists for. `sync.py` describes the
Datasets a person created — usually one table out of eighty, sometimes a
hand-written join matching no table at all. This describes what the connection
can actually see.

A description assembled from datasets describes the part of the database
somebody already knew to import. For the person who has just connected a source,
the tables they have NOT imported are precisely the ones they need told about.

So every test here starts from a bare connection: no Dataset rows exist, and
none are created.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select, text

from app.models.models import (ColumnStats, DataSource, Dataset, Entity,
                               Organization, SourceColumn, SourceObject,
                               SourceRelationship)
from app.services.metadata import catalog_sync


@pytest.fixture
def live_db(tmp_path):
    """A real SQLite database standing in for a customer's source."""
    path = tmp_path / "shop.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                city TEXT
            )"""))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                status TEXT,
                total NUMERIC(10,2)
            )"""))
        conn.execute(text("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, note TEXT)"))
        for i in range(1, 41):
            conn.execute(text("INSERT INTO customers VALUES (:i, :e, :c)"),
                         {"i": i, "e": f"user{i}@corp.com",
                          "c": ["Cairo", "Giza", "Luxor"][i % 3]})
        for i in range(1, 121):
            conn.execute(text("INSERT INTO orders VALUES (:i, :c, :s, :t)"),
                         {"i": i, "c": (i % 40) + 1,
                          "s": ["new", "paid", "shipped"][i % 3], "t": 10.5 * i})
    engine.dispose()
    return str(path)


@pytest.fixture
async def source(db_session, live_db, monkeypatch):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    ds = DataSource(name="shop", type="sqlite", org_id=org.id,
                    config={"filepath": live_db})
    db_session.add(ds)
    await db_session.commit()

    # The catalog pipeline opens the real source through direct_query's pooled
    # engine; point that at the SQLite file this test just built.
    engine = create_engine(f"sqlite:///{live_db}")
    # Sampling uses its own pool (_sampling_engine_for -> get_metadata_engine)
    # so it cannot compete with live widget traffic for connections. Both
    # seams are redirected here, or the sampling tests would quietly open a
    # real second engine against the same file instead of using this one.
    monkeypatch.setattr(catalog_sync, "_engine_for", lambda cfg: engine)
    monkeypatch.setattr(catalog_sync, "_sampling_engine_for", lambda cfg: engine)
    yield {"org": org, "source": ds, "cfg": {"type": "sqlite", "filepath": live_db}}
    engine.dispose()


@pytest.fixture
def cache(tmp_path):
    from app.services.metadata.cache import SampleCache
    c = SampleCache(path=str(tmp_path / "cat.duckdb"), max_mb=32, namespace="o")
    yield c
    c.close()


async def _run(db_session, source, cache, llm=None, allow=False):
    return await catalog_sync.run_catalog_sync(
        db_session, source["source"], cache=cache,
        llm_client=llm, allow_llm=allow, source_config=source["cfg"],
    )


class TestNoDatasetsRequired:
    async def test_the_whole_database_is_catalogued_from_the_connection_alone(
        self, db_session, source, cache
    ):
        run = await _run(db_session, source, cache)
        await db_session.commit()

        assert run.status == "ok"
        objects = (await db_session.execute(select(SourceObject))).scalars().all()
        assert {o.name for o in objects} == {"customers", "orders", "audit_log"}

    async def test_no_datasets_are_created_or_needed(self, db_session, source, cache):
        """A dataset is a person's choice. Cataloguing must not invent one, and
        must not require one."""
        await _run(db_session, source, cache)
        await db_session.commit()
        datasets = (await db_session.execute(select(Dataset))).scalars().all()
        assert datasets == []

    async def test_tables_nobody_imported_are_still_described(
        self, db_session, source, cache
    ):
        """audit_log has no dataset and never will. It is exactly the kind of
        table a newcomer needs told about."""
        await _run(db_session, source, cache)
        await db_session.commit()
        objects = (await db_session.execute(select(SourceObject))).scalars().all()
        assert any(o.name == "audit_log" for o in objects)

    async def test_columns_come_from_the_database_not_a_guess(
        self, db_session, source, cache
    ):
        await _run(db_session, source, cache)
        await db_session.commit()

        orders = (await db_session.execute(
            select(SourceObject).where(SourceObject.name == "orders")
        )).scalar_one()
        columns = (await db_session.execute(
            select(SourceColumn).where(SourceColumn.source_object_id == orders.id)
        )).scalars().all()

        by_name = {c.name: c for c in columns}
        assert set(by_name) == {"id", "customer_id", "status", "total"}
        assert by_name["id"].is_primary_key is True
        assert by_name["email" if "email" in by_name else "total"].dtype == "numeric"
        assert by_name["customer_id"].nullable is False


class TestDeclaredForeignKeys:
    async def test_a_declared_key_is_seeded_as_fact(self, db_session, source, cache):
        """The database enforces it. Re-deriving it by statistics would be both
        slower and less accurate than reading what the schema states."""
        run = await _run(db_session, source, cache)
        await db_session.commit()

        rels = (await db_session.execute(select(SourceRelationship))).scalars().all()
        declared = [r for r in rels if r.source == "declared"]
        assert len(declared) == 1
        assert declared[0].from_column == "customer_id"
        assert declared[0].to_column == "id"
        assert declared[0].confidence == 1.0

        stages = {s["name"]: s for s in run.stages}
        assert stages["discover"]["detail"]["declared_foreign_keys"] == 1

    async def test_inference_never_downgrades_a_declared_key(
        self, db_session, source, cache
    ):
        await _run(db_session, source, cache)
        await db_session.commit()
        await _run(db_session, source, cache)
        await db_session.commit()

        rels = (await db_session.execute(select(SourceRelationship))).scalars().all()
        edge = [r for r in rels if r.from_column == "customer_id"][0]
        assert edge.source == "declared"


class TestProfiling:
    async def test_every_catalog_column_gets_statistics(self, db_session, source, cache):
        run = await _run(db_session, source, cache)
        await db_session.commit()

        stats = (await db_session.execute(select(ColumnStats))).scalars().all()
        # customers (3) + orders (4). audit_log is empty, so there is nothing to
        # compute statistics FROM — a distinct_count of 0 over no rows describes
        # the absence of data rather than the data, and would read as fact.
        assert len(stats) == 7
        assert all(s.source_column_id is not None for s in stats)
        assert all(s.dataset_column_id is None for s in stats)

    async def test_top_k_enumerates_a_low_cardinality_column(
        self, db_session, source, cache
    ):
        await _run(db_session, source, cache)
        await db_session.commit()

        status = (await db_session.execute(
            select(SourceColumn).where(SourceColumn.name == "status")
        )).scalar_one()
        stats = (await db_session.execute(
            select(ColumnStats).where(ColumnStats.source_column_id == status.id)
        )).scalar_one()
        assert {e["value"] for e in stats.top_k} == {"new", "paid", "shipped"}

    async def test_a_small_table_is_actually_sampled(self, db_session, source, cache):
        """The bug this guards: TABLESAMPLE on a 40-row table returns nothing,
        and every later stage then reports success having learned nothing."""
        run = await _run(db_session, source, cache)
        await db_session.commit()
        detail = {s["name"]: s for s in run.stages}["sample"]["detail"]

        # customers (40 rows) and orders (120) — both far below any sensible
        # TABLESAMPLE threshold, and both must still yield real rows.
        assert detail["objects_sampled"] == 2

    async def test_an_empty_table_is_reported_as_empty_not_as_success(
        self, db_session, source, cache
    ):
        """audit_log holds no rows. That is a fact worth surfacing — it feeds the
        deprecation signal — and it must not be indistinguishable from a table
        that was sampled successfully."""
        run = await _run(db_session, source, cache)
        await db_session.commit()
        detail = {s["name"]: s for s in run.stages}["sample"]["detail"]
        assert detail["objects_empty"] == 1
        assert not detail["failures"]


class TestPii:
    async def test_email_is_classified_and_masked_before_caching(
        self, db_session, source, cache
    ):
        await _run(db_session, source, cache)
        await db_session.commit()

        email = (await db_session.execute(
            select(SourceColumn).where(SourceColumn.name == "email")
        )).scalar_one()
        assert email.semantic_type == "email"

        customers = (await db_session.execute(
            select(SourceObject).where(SourceObject.name == "customers")
        )).scalar_one()
        cached = cache.get_sample(customers.id)
        assert cached
        assert not any("user1@corp.com" == r["email"] for r in cached)


class FakeLlm:
    def __init__(self):
        self.last_error = None
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        body = messages[1]["content"]
        if "Database connection" in body:
            # The overview call returns ONLY an overview — asking it for a
            # sentence per table is what failed on an 82-table source.
            return {"overview": "A shop database tracking customers and their orders."}
        # The per-table call describes the table AND its columns, so a large
        # database costs no extra requests for the table sentences.
        table = body.split("Table: ")[1].splitlines()[0] if "Table: " in body else "?"
        return {"table": f"One row per {table.rstrip('s')}.",
                "descriptions": {"status": "The order's lifecycle state."}}


class TestDescription:
    async def test_the_database_gets_an_overview(self, db_session, source, cache):
        run = await _run(db_session, source, cache, llm=FakeLlm(), allow=True)
        await db_session.commit()

        await db_session.refresh(source["source"])
        assert source["source"].description == (
            "A shop database tracking customers and their orders.")

        stages = {s["name"]: s for s in run.stages}
        assert stages["describe"]["detail"]["source_overview"] is True

    async def test_tables_get_descriptions(self, db_session, source, cache):
        await _run(db_session, source, cache, llm=FakeLlm(), allow=True)
        await db_session.commit()

        customers = (await db_session.execute(
            select(SourceObject).where(SourceObject.name == "customers")
        )).scalar_one()
        assert customers.description == "One row per customer."

    async def test_the_overview_prompt_carries_the_relationships(
        self, db_session, source, cache
    ):
        """A list of tables reads as a list of tables. The same list with
        'orders.customer_id -> customers.id' reads as a system."""
        llm = FakeLlm()
        await _run(db_session, source, cache, llm=llm, allow=True)
        await db_session.commit()

        overview_prompt = next(
            m for m in llm.calls if "Database connection" in m[1]["content"])
        assert "orders.customer_id -> customers.id" in overview_prompt[1]["content"]

    async def test_no_consent_means_no_model_call(self, db_session, source, cache):
        llm = FakeLlm()
        run = await _run(db_session, source, cache, llm=llm, allow=False)
        await db_session.commit()
        assert llm.calls == []
        stages = {s["name"]: s for s in run.stages}
        assert stages["describe"]["status"] == "ok"
        assert stages["describe"]["detail"]["llm_used"] is False


class LabelAwareFakeLlm(FakeLlm):
    """FakeLlm plus the T2 enum-label call, distinguished by its prompt body
    ("values seen =") from the overview and per-table description calls."""

    async def complete_json(self, messages, schema, **kw):
        body = messages[1]["content"]
        if "values seen" in body:
            self.calls.append(messages)
            return {"labels": {"status": {
                "new": "Just placed", "paid": "Payment received", "shipped": "Shipped"}}}
        return await super().complete_json(messages, schema, **kw)


class TestEnumLabels:
    """T2 / L3 gap #2: top_k already knows `status` holds new/paid/shipped --
    the meaning is what the describe stage's draft pass adds."""

    async def test_an_eligible_column_gets_labelled(self, db_session, source, cache):
        await _run(db_session, source, cache, llm=LabelAwareFakeLlm(), allow=True)
        await db_session.commit()

        status = (await db_session.execute(
            select(SourceColumn).where(SourceColumn.name == "status")
        )).scalar_one()
        assert status.enum_labels == {
            "new": "Just placed", "paid": "Payment received", "shipped": "Shipped"}
        assert status.enum_labels_source == "inferred"

    async def test_a_column_with_no_short_top_k_is_not_asked(self, db_session, source, cache):
        """`total` is a unique numeric per row -- 120 distinct values, so
        _profile_object never even computes a top_k for it. No top_k, no
        eligibility, no call."""
        await _run(db_session, source, cache, llm=LabelAwareFakeLlm(), allow=True)
        await db_session.commit()

        total = (await db_session.execute(
            select(SourceColumn).where(SourceColumn.name == "total")
        )).scalar_one()
        assert total.enum_labels is None

    async def test_no_consent_means_no_labels(self, db_session, source, cache):
        llm = LabelAwareFakeLlm()
        await _run(db_session, source, cache, llm=llm, allow=False)
        await db_session.commit()
        assert llm.calls == []


class EntityAwareFakeLlm(FakeLlm):
    """FakeLlm plus Task R3's entity-drafting call, distinguished by its
    prompt body ("Tables:") from the overview/per-table/enum-label calls."""

    async def complete_json(self, messages, schema, **kw):
        body = messages[1]["content"]
        if body.startswith("Database:") and "Tables:" in body:
            self.calls.append(messages)
            return {"entities": [
                {"name": "customer", "business_name": "Customer",
                 "grain": "One row per customer.",
                 "description": "A person who has placed orders.",
                 "primary_object": "customers"},
                {"name": "order", "business_name": "Order",
                 "grain": "One row per order.",
                 "description": "A purchase a customer made.",
                 "primary_object": "orders"},
                # An entity naming a table that does not exist -- the model
                # inventing a catalog entry, which this pass must not trust.
                {"name": "shipment", "business_name": "Shipment",
                 "grain": "One row per shipment.",
                 "description": "Not backed by any real table.",
                 "primary_object": "shipments"},
            ]}
        return await super().complete_json(messages, schema, **kw)


class TestEntities:
    """Task R3 / spec section 5 (E2): named business objects, drafted the
    same way enum labels are (one complete_json pass, `source='inferred'`
    unless a human already confirmed the row)."""

    async def test_draft_creates_inferred_rows(self, db_session, source, cache):
        from app.models.models import Entity

        await _run(db_session, source, cache, llm=EntityAwareFakeLlm(), allow=True)
        await db_session.commit()

        rows = (await db_session.execute(select(Entity))).scalars().all()
        by_name = {e.name: e for e in rows}
        assert by_name["customer"].source == "inferred"
        assert by_name["customer"].grain == "One row per customer."
        assert by_name["customer"].primary_object == "customers"
        assert by_name["order"].primary_object == "orders"

    async def test_an_invented_primary_object_is_dropped(self, db_session, source, cache):
        """`shipments` is not a real table on this source -- inventing that
        cross-reference is exactly what draft_entities must refuse to trust,
        the same discipline describe_with_llm applies to invented columns."""
        from app.models.models import Entity

        await _run(db_session, source, cache, llm=EntityAwareFakeLlm(), allow=True)
        await db_session.commit()

        shipment = (await db_session.execute(
            select(Entity).where(Entity.name == "shipment")
        )).scalar_one()
        assert shipment.primary_object is None

    async def test_no_consent_means_no_entities(self, db_session, source, cache):
        from app.models.models import Entity

        llm = EntityAwareFakeLlm()
        run = await _run(db_session, source, cache, llm=llm, allow=False)
        await db_session.commit()
        assert llm.calls == []
        rows = (await db_session.execute(select(Entity))).scalars().all()
        assert rows == []
        stages = {s["name"]: s for s in run.stages}
        assert stages["entities"]["status"] == "ok"
        assert stages["entities"]["detail"]["llm_used"] is False

    async def test_confirming_an_entity_flips_provenance(self, db_session, source, cache):
        from app.models.models import Entity

        await _run(db_session, source, cache, llm=EntityAwareFakeLlm(), allow=True)
        await db_session.commit()

        customer = (await db_session.execute(
            select(Entity).where(Entity.name == "customer")
        )).scalar_one()
        customer.business_name = "Buyer"
        customer.source = "confirmed"
        await db_session.commit()

        await db_session.refresh(customer)
        assert customer.source == "confirmed"
        assert customer.business_name == "Buyer"

    async def test_a_confirmed_entity_survives_a_resync(self, db_session, source, cache):
        """THE core rule of this layer, applied to entities: a human
        correction is never reverted by the next sync's draft pass."""
        from app.models.models import Entity

        await _run(db_session, source, cache, llm=EntityAwareFakeLlm(), allow=True)
        await db_session.commit()

        customer = (await db_session.execute(
            select(Entity).where(Entity.name == "customer")
        )).scalar_one()
        customer.business_name = "Mine, and correct."
        customer.grain = "One row per confirmed customer."
        customer.source = "confirmed"
        await db_session.commit()

        await _run(db_session, source, cache, llm=EntityAwareFakeLlm(), allow=True)
        await db_session.commit()

        await db_session.refresh(customer)
        assert customer.business_name == "Mine, and correct."
        assert customer.grain == "One row per confirmed customer."
        assert customer.source == "confirmed"

    async def test_isolated_failure_does_not_abort_the_run(self, db_session, source, cache):
        """A stage that raises must become a recorded failure, not a
        cancelled run -- same isolation `_run_stage` gives every other
        stage."""
        class BoomLlm(EntityAwareFakeLlm):
            async def complete_json(self, messages, schema, **kw):
                body = messages[1]["content"]
                if body.startswith("Database:") and "Tables:" in body:
                    raise RuntimeError("boom")
                return await super().complete_json(messages, schema, **kw)

        run = await _run(db_session, source, cache, llm=BoomLlm(), allow=True)
        await db_session.commit()

        stages = {s["name"]: s for s in run.stages}
        assert stages["entities"]["status"] == "failed"
        assert run.status == "partial"
        # The rest of the run still completed.
        assert stages["describe"]["status"] == "ok"
        assert stages["drift"]["status"] == "ok"


class TestResync:
    async def test_a_dropped_table_leaves_the_catalog(
        self, db_session, source, cache, live_db
    ):
        await _run(db_session, source, cache)
        await db_session.commit()

        engine = create_engine(f"sqlite:///{live_db}")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE audit_log"))
        engine.dispose()

        await _run(db_session, source, cache)
        await db_session.commit()

        objects = (await db_session.execute(select(SourceObject))).scalars().all()
        assert "audit_log" not in {o.name for o in objects}

    async def test_a_confirmed_description_survives_a_resync(
        self, db_session, source, cache
    ):
        await _run(db_session, source, cache, llm=FakeLlm(), allow=True)
        await db_session.commit()

        customers = (await db_session.execute(
            select(SourceObject).where(SourceObject.name == "customers")
        )).scalar_one()
        customers.description = "Mine, and correct."
        customers.description_source = "confirmed"
        await db_session.commit()

        await _run(db_session, source, cache, llm=FakeLlm(), allow=True)
        await db_session.commit()

        await db_session.refresh(customers)
        assert customers.description == "Mine, and correct."

    async def test_a_confirmed_enum_label_survives_a_resync(self, db_session, source, cache):
        """THE core rule of this layer (spec/ARCHITECTURE.md principle 5),
        applied to enum labels: a human correction is never reverted by the
        next sync's draft pass."""
        await _run(db_session, source, cache, llm=LabelAwareFakeLlm(), allow=True)
        await db_session.commit()

        status = (await db_session.execute(
            select(SourceColumn).where(SourceColumn.name == "status")
        )).scalar_one()
        status.enum_labels = {"new": "Mine, and correct.", "paid": "Paid", "shipped": "Shipped"}
        status.enum_labels_source = "confirmed"
        await db_session.commit()

        await _run(db_session, source, cache, llm=LabelAwareFakeLlm(), allow=True)
        await db_session.commit()

        await db_session.refresh(status)
        assert status.enum_labels == {
            "new": "Mine, and correct.", "paid": "Paid", "shipped": "Shipped"}

    async def test_a_second_unchanged_run_is_not_drift(self, db_session, source, cache):
        from app.models.models import SchemaVersion

        await _run(db_session, source, cache)
        await db_session.commit()
        await _run(db_session, source, cache)
        await db_session.commit()

        versions = (await db_session.execute(select(SchemaVersion))).scalars().all()
        assert len(versions) == 1


class TestFailure:
    async def test_no_connection_config_fails_the_run_loudly(
        self, db_session, source, cache
    ):
        """Without a catalog there is nothing for any later stage to describe,
        so this is one of the few genuinely fatal conditions."""
        run = await catalog_sync.run_catalog_sync(
            db_session, source["source"], cache=cache, source_config=None)
        await db_session.commit()
        assert run.status == "failed"
        assert "introspect" in (run.error or "")



class TestSlowObjectsAreNotPaidForTwice:
    """Sampling gives each object a fixed deadline and moves on. On the measured
    source the SAME eight views hit that deadline on every run — 160 seconds of
    deterministically repeated failure against the customer's database, every
    sync, forever.

    So a timeout is REMEMBERED. These tests pin the two halves of that: the
    remembering must actually skip work next time, and it must never become a
    way for a table to disappear without anyone being able to see or undo it.
    """

    async def test_an_object_that_timed_out_is_not_sampled_again(
        self, db_session, source, cache, monkeypatch
    ):
        await _run(db_session, source, cache)
        await db_session.commit()

        orders = (await db_session.execute(
            select(SourceObject).where(SourceObject.name == "orders")
        )).scalar_one()
        orders.sample_timed_out_at = datetime.utcnow()
        await db_session.commit()

        attempted = []
        original = catalog_sync._sample_object

        def record(spec, *a, **k):
            attempted.append(spec["name"])
            return original(spec, *a, **k)

        monkeypatch.setattr(catalog_sync, "_sample_object", record)

        run = await _run(db_session, source, cache)
        await db_session.commit()

        assert "orders" not in attempted, (
            "a known-too-slow object was sampled again; the whole point of "
            "remembering the timeout is to stop paying for it"
        )
        detail = {s["name"]: s for s in run.stages}["sample"]["detail"]
        assert detail["objects_skipped_slow"] == 1
        assert detail["skipped_slow"] == ["orders"]

    async def test_a_skipped_object_keeps_its_earlier_sample(
        self, db_session, source, cache
    ):
        """Skipping must cost freshness, never coverage. The previously cached
        sample stays, so profiling and inference still see the object — the
        worst case is a staler sample, never a missing one."""
        await _run(db_session, source, cache)
        await db_session.commit()

        orders = (await db_session.execute(
            select(SourceObject).where(SourceObject.name == "orders")
        )).scalar_one()
        orders.sample_timed_out_at = datetime.utcnow()
        await db_session.commit()

        await _run(db_session, source, cache)
        await db_session.commit()

        assert cache.get_sample(orders.id), (
            "skipping an object dropped its cached sample, so the object is now "
            "invisible to every later stage"
        )

    async def test_a_timeout_is_recorded_rather_than_merely_counted(
        self, db_session, source, cache, monkeypatch
    ):
        def always_times_out(spec, cfg, n, cache_):
            return {"id": spec["id"], "name": spec["name"], "outcome": "timeout",
                    "column_types": None, "masked": 0, "error": "timeout"}

        monkeypatch.setattr(catalog_sync, "_sample_object", always_times_out)

        run = await _run(db_session, source, cache)
        await db_session.commit()

        detail = {s["name"]: s for s in run.stages}["sample"]["detail"]
        assert detail["objects_timed_out"] == 3

        objects = (await db_session.execute(select(SourceObject))).scalars().all()
        assert all(o.sample_timed_out_at is not None for o in objects), (
            "the run counted the timeouts but did not remember them, so the next "
            "sync pays the same deadlines again"
        )

    async def test_a_failure_that_is_not_a_timeout_is_not_remembered(
        self, db_session, source, cache, monkeypatch
    ):
        """A transient error must not permanently sideline a table. Only the
        deadline — the one failure mode that is a property of the object rather
        than of the moment — earns the flag."""
        def always_errors(spec, cfg, n, cache_):
            return {"id": spec["id"], "name": spec["name"], "outcome": "error",
                    "column_types": None, "masked": 0, "error": "OperationalError"}

        monkeypatch.setattr(catalog_sync, "_sample_object", always_errors)

        await _run(db_session, source, cache)
        await db_session.commit()

        objects = (await db_session.execute(select(SourceObject))).scalars().all()
        assert all(o.sample_timed_out_at is None for o in objects)


class TestSamplingIsBounded:
    async def test_objects_are_sampled_concurrently(self, db_session, source, cache,
                                                    monkeypatch):
        """Asserted as OVERLAP, not as elapsed time: a timing threshold passes on
        a fast machine while the loop is still serial."""
        import threading
        import time as _time

        live = []
        peak = [0]
        lock = threading.Lock()

        def slow(spec, cfg, n, cache_):
            with lock:
                live.append(spec["name"])
                peak[0] = max(peak[0], len(live))
            _time.sleep(0.2)
            with lock:
                live.remove(spec["name"])
            return {"id": spec["id"], "name": spec["name"], "outcome": "empty",
                    "column_types": None, "masked": 0, "error": None}

        monkeypatch.setattr(catalog_sync, "_sample_object", slow)

        await _run(db_session, source, cache)
        await db_session.commit()

        assert peak[0] > 1, "objects were sampled one at a time"

    async def test_concurrency_never_exceeds_the_configured_bound(
        self, db_session, source, cache, monkeypatch
    ):
        """The bound is a promise made to the customer's database — their source
        sees exactly this many connections from a sync and no more."""
        import threading
        import time as _time

        from app.core.config import settings

        monkeypatch.setattr(settings, "metadata_sample_concurrency", 2)

        live = []
        peak = [0]
        lock = threading.Lock()

        def slow(spec, cfg, n, cache_):
            with lock:
                live.append(spec["name"])
                peak[0] = max(peak[0], len(live))
            _time.sleep(0.2)
            with lock:
                live.remove(spec["name"])
            return {"id": spec["id"], "name": spec["name"], "outcome": "empty",
                    "column_types": None, "masked": 0, "error": None}

        monkeypatch.setattr(catalog_sync, "_sample_object", slow)

        run = await _run(db_session, source, cache)
        await db_session.commit()

        assert peak[0] <= 2, f"{peak[0]} objects were sampled at once, bound is 2"
        assert {s["name"]: s for s in run.stages}["sample"]["detail"]["concurrency"] == 2

    async def test_no_orm_instance_crosses_the_thread_boundary(
        self, db_session, source, cache, monkeypatch
    ):
        """A worker thread must receive plain data.

        The session runs with `expire_on_commit=False`, so passing an instance
        happens to work today — which is exactly why this needs a test rather
        than a comment. A lazy attribute load from another thread would be a
        race, not an error, and it would surface as corrupt metadata rather than
        as a traceback.
        """
        from app.models.models import SourceObject as SO

        seen = []
        original = catalog_sync._sample_object

        def record(spec, *a, **k):
            seen.append(spec)
            return original(spec, *a, **k)

        monkeypatch.setattr(catalog_sync, "_sample_object", record)
        await _run(db_session, source, cache)
        await db_session.commit()

        assert seen
        for spec in seen:
            assert not isinstance(spec, SO)
            assert isinstance(spec, dict)
            assert set(spec) == {"id", "name", "kind", "row_count_estimate"}


class TestPiiWorkStaysOffTheLoop:
    async def test_masking_and_caching_happen_in_the_worker_thread(
        self, db_session, source, cache, monkeypatch
    ):
        """Masking ~1000 rows and writing them to DuckDB is synchronous work. On
        the event loop it froze every other request — and, worse for this stage,
        it would have serialised the fan-out on whichever object finished first,
        making the concurrency largely theatre."""
        import threading

        main = threading.get_ident()
        threads = []

        original = catalog_sync.pii.mask_rows

        def record(*a, **k):
            threads.append(threading.get_ident())
            return original(*a, **k)

        monkeypatch.setattr(catalog_sync.pii, "mask_rows", record)

        await _run(db_session, source, cache)
        await db_session.commit()

        assert threads, "nothing was masked"
        assert all(t != main for t in threads), (
            "PII masking ran on the event loop"
        )



class TestAFailureSaysWhy:
    """`InternalError` is not a diagnosis.

    The live source reported `v_maps_state_student_solution: InternalError` on
    every single run. Finding out what that meant took a hand-written probe
    against the customer's database, and the answer was sitting in the
    exception all along:

        ModuleNotFoundError: No module named 'requests'
        PL/Python function "get_image_size_from_url", line 2

    A permanently broken view, fixable only by the person reading the sync
    record -- who was being told nothing.
    """

    def test_the_cause_survives_into_the_record(self):
        from app.services.metadata.catalog_sync import _error_summary

        exc = RuntimeError(
            'ModuleNotFoundError: No module named \'requests\'\n'
            'CONTEXT:  Traceback (most recent call last):\n'
            '  PL/Python function "get_image_size_from_url", line 2')
        assert "No module named" in _error_summary(exc)

    def test_only_the_first_line_is_kept(self):
        """Driver messages append the failing SQL and a docs link. The SQL can
        carry literal values from the query, which is how a run record quietly
        becomes somewhere personal data lives."""
        from app.services.metadata.catalog_sync import _error_summary

        exc = RuntimeError(
            "permission denied for table customers\n"
            "[SQL: SELECT * FROM customers WHERE email = 'ada@corp.com']\n"
            "(Background on this error at: https://sqlalche.me/e/20/f405)")
        summary = _error_summary(exc)
        assert "permission denied" in summary
        assert "ada@corp.com" not in summary
        assert "sqlalche.me" not in summary

    def test_a_long_first_line_is_bounded(self):
        from app.services.metadata.catalog_sync import (ERROR_DETAIL_CHARS,
                                                        _error_summary)

        summary = _error_summary(RuntimeError("x" * 5_000))
        assert len(summary) < ERROR_DETAIL_CHARS + 60

    def test_the_class_is_still_there(self):
        """It was the only thing recorded before, and it is still the fastest
        way to tell one kind of failure from another at a glance."""
        from app.services.metadata.catalog_sync import _error_summary

        assert _error_summary(ValueError("bad")).startswith("ValueError")

    def test_a_silent_exception_still_names_itself(self):
        from app.services.metadata.catalog_sync import _error_summary

        assert _error_summary(TimeoutError()) == "TimeoutError"
        assert _error_summary(TimeoutError("   ")) == "TimeoutError"


class TestRunStageRollsBackOnFailure:
    """`_run_stage`'s except branch records a failure -- but before this fix
    it never touched the session, so a stage that raised AFTER adding
    pending rows (a batch half-flushed, an ORM object staged but not yet
    committed) left those rows sitting in the session. The very next thing
    `_run_stage` does either way is publish progress via `context.db.commit()`
    -- which would silently persist that partial write despite the stage
    being recorded as "failed". A rollback in the except branch is what
    keeps a failed stage's half-done writes from surviving into the db."""

    async def test_pending_write_from_a_failed_stage_is_not_committed(self, db_session):
        from app.models.models import Entity, Organization
        from app.services.metadata.sync import SyncContext, _run_stage

        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()

        context = SyncContext(db_session, data_source_id=1, org_id=org.id, cache=None)

        async def bad_stage(ctx):
            # Stages a write, then blows up before it would ever be
            # committed on purpose -- exactly the "half-done batch" shape.
            ctx.db.add(Entity(org_id=org.id, data_source_id=1, name="ghost"))
            await ctx.db.flush()
            raise RuntimeError("boom mid-stage")

        result = await _run_stage(context, "entities", bad_stage)
        assert result.status == "failed"

        # The session must have nothing pending/dirty left over from the
        # failed stage -- rollback cleared it.
        assert not db_session.new
        assert not db_session.dirty

        # And it never reached the database either.
        from sqlalchemy import select
        rows = (await db_session.execute(
            select(Entity).where(Entity.name == "ghost"))).scalars().all()
        assert rows == []


class TestDatasetsImportedBeforeTheSync:
    """The ordinary first run of this product is connect, browse, import, and
    sync afterwards if at all. Linking happens at import time and is idempotent,
    so every dataset made in that window would carry NULL provenance for the
    rest of its life -- the catalog describing its columns perfectly while no
    dashboard ever saw a word of it.

    The sync closes that loop from its own side.
    """

    async def _dataset_imported_first(self, db, source):
        from app.models.models import DatasetColumn

        ds = Dataset(name="Orders", org_id=source["org"].id, mode="import",
                     data_source_id=source["source"].id, source_table="orders")
        db.add(ds)
        await db.flush()
        for name, dtype in (("id", "numeric"), ("customer_id", "numeric"),
                            ("status", "categorical"), ("total", "numeric")):
            db.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
        await db.commit()
        return ds

    async def test_a_sync_links_a_dataset_that_predates_the_catalog(
            self, db_session, source, cache):
        from app.models.models import DatasetColumn

        ds = await self._dataset_imported_first(db_session, source)
        cols = (await db_session.execute(select(DatasetColumn).where(
            DatasetColumn.dataset_id == ds.id))).scalars().all()
        assert all(c.source_column_id is None for c in cols), "precondition"

        run = await _run(db_session, source, cache)
        await db_session.commit()

        assert run.status == "ok"
        cols = (await db_session.execute(select(DatasetColumn).where(
            DatasetColumn.dataset_id == ds.id))).scalars().all()
        assert all(c.source_column_id is not None for c in cols), \
            {c.name: c.source_column_id for c in cols}

    async def test_the_run_reports_what_it_linked(self, db_session, source, cache):
        """Visible in the run's stages, so the review page can say so rather
        than leaving the user to wonder whether anything happened."""
        await self._dataset_imported_first(db_session, source)
        run = await _run(db_session, source, cache)
        await db_session.commit()

        stage = next(s for s in run.stages if s["name"] == "link_datasets")
        assert stage["status"] == "ok"
        assert stage["detail"]["datasets_linked"] == 1
        assert stage["detail"]["columns_linked"] == 4

    async def test_the_meaning_then_resolves_through(self, db_session, source, cache):
        """The point of the stage, not just the pointer: after the sync, the
        dataset's columns answer with what the catalog knows."""
        from app.services import knowledge

        ds = await self._dataset_imported_first(db_session, source)
        await _run(db_session, source, cache)
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, ds)
        assert k.linked_columns == 4
        # `orders.customer_id` is a declared foreign key in the fixture schema,
        # so the catalog has a real row for it to resolve against.
        assert k.column("customer_id") is not None

    async def test_a_source_with_no_datasets_records_a_clean_no_op(
            self, db_session, source, cache):
        run = await _run(db_session, source, cache)
        await db_session.commit()
        stage = next(s for s in run.stages if s["name"] == "link_datasets")
        assert stage["status"] == "ok"
        assert stage["detail"] == {"datasets": 0, "datasets_linked": 0,
                                   "columns_linked": 0}
