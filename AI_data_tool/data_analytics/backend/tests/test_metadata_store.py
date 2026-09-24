"""The provenance rule, which is the whole point of the metadata store.

ARCHITECTURE.md principle 5: "Inference is a proposal, never a fact. Everything
derived carries confidence and source. Human confirmation outranks inference
permanently."

"Permanently" is the load-bearing word, and it is why every inference stage
writes through store.upsert_inferred_relationship rather than touching the ORM
directly. If a resync could silently revert a human's confirmation, the review
UI would be a lie: a user would confirm a join, come back the next morning, and
find their answer replaced by whatever the sampler guessed that night.
"""
import pytest

from app.models.models import Dataset, Organization, Relationship
from app.services.metadata import store


@pytest.fixture
async def org_and_datasets(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    orders = Dataset(name="orders", org_id=org.id)
    customers = Dataset(name="customers", org_id=org.id)
    db_session.add_all([orders, customers])
    await db_session.flush()
    await db_session.commit()
    return org, orders, customers


async def _get(db_session, rel_id):
    return await db_session.get(Relationship, rel_id)


class TestConfirmedIsNeverOverwritten:
    """The rule. Every other behaviour in this module is subordinate to it."""

    async def test_resync_cannot_downgrade_a_confirmed_relationship(self, db_session, org_and_datasets):
        org, orders, customers = org_and_datasets

        rel = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.82, evidence={"overlap": 0.82}, cardinality="many_to_one",
        )
        await db_session.commit()

        await store.confirm_relationship(db_session, rel.id, org_id=org.id)
        await db_session.commit()

        # A later sync re-derives the same edge, less confidently this time.
        await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.71, evidence={"overlap": 0.71}, cardinality="one_to_one",
        )
        await db_session.commit()

        after = await _get(db_session, rel.id)
        assert after.source == "confirmed"
        assert after.confidence == 1.0
        # Not just the flag — the payload the human implicitly approved is intact too.
        assert after.cardinality == "many_to_one"
        assert after.evidence == {"overlap": 0.82}

    async def test_confirmed_survives_a_lower_confidence_and_a_higher_one(self, db_session, org_and_datasets):
        """A resync that is MORE confident is still not allowed to win. Confidence
        does not outrank a human; nothing does."""
        org, orders, customers = org_and_datasets
        rel = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.80, evidence={"overlap": 0.80},
        )
        await db_session.commit()
        await store.confirm_relationship(db_session, rel.id, org_id=org.id)
        await db_session.commit()

        await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.99, evidence={"overlap": 0.99},
        )
        await db_session.commit()

        after = await _get(db_session, rel.id)
        assert after.source == "confirmed"
        assert after.evidence == {"overlap": 0.80}

    async def test_declared_is_not_overwritten_by_inference_either(self, db_session, org_and_datasets):
        """A real foreign key read from the source catalog is a fact, not a guess.
        Inference may not contradict it."""
        org, orders, customers = org_and_datasets
        rel = await store.upsert_declared_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
        )
        await db_session.commit()

        await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.73, evidence={"overlap": 0.73},
        )
        await db_session.commit()

        after = await _get(db_session, rel.id)
        assert after.source == "declared"
        assert after.confidence == 1.0


class TestInferenceUpdatesItself:
    """Inference must still be able to correct its own earlier guesses, or the
    metadata model would freeze at whatever the first sync happened to produce."""

    async def test_resync_updates_an_inferred_row_in_place(self, db_session, org_and_datasets):
        org, orders, customers = org_and_datasets
        rel = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.75, evidence={"overlap": 0.75},
        )
        await db_session.commit()

        again = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
            confidence=0.97, evidence={"overlap": 0.97}, cardinality="many_to_one",
        )
        await db_session.commit()

        assert again.id == rel.id, "should update in place, not create a duplicate edge"
        assert again.confidence == 0.97
        assert again.evidence == {"overlap": 0.97}
        assert again.cardinality == "many_to_one"

    async def test_upsert_is_keyed_on_the_edge_not_the_row(self, db_session, org_and_datasets):
        """Two different columns between the same pair of tables are two edges."""
        org, orders, customers = org_and_datasets
        a = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id", confidence=0.9,
        )
        b = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="billing_customer_id",
            to_dataset_id=customers.id, to_column="id", confidence=0.9,
        )
        await db_session.commit()
        assert a.id != b.id


class TestConfidenceContract:
    async def test_confidence_is_clamped_to_zero_one(self, db_session, org_and_datasets):
        org, orders, customers = org_and_datasets
        rel = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id", confidence=1.4,
        )
        await db_session.commit()
        assert rel.confidence == 1.0

    async def test_declared_and_confirmed_are_always_full_confidence(self, db_session, org_and_datasets):
        org, orders, customers = org_and_datasets
        rel = await store.upsert_declared_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id",
        )
        await db_session.commit()
        assert rel.confidence == 1.0 and rel.source == "declared"

    async def test_confirm_is_idempotent(self, db_session, org_and_datasets):
        org, orders, customers = org_and_datasets
        rel = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id", confidence=0.9,
        )
        await db_session.commit()
        await store.confirm_relationship(db_session, rel.id, org_id=org.id)
        await store.confirm_relationship(db_session, rel.id, org_id=org.id)
        await db_session.commit()
        after = await _get(db_session, rel.id)
        assert after.source == "confirmed" and after.confidence == 1.0


class TestOrgScoping:
    async def test_confirm_refuses_a_relationship_from_another_org(self, db_session, org_and_datasets):
        """Provenance is per-tenant. Confirming across an org boundary must fail
        closed rather than silently succeed."""
        org, orders, customers = org_and_datasets
        other = Organization(name="Other")
        db_session.add(other)
        await db_session.flush()

        rel = await store.upsert_inferred_relationship(
            db_session, org_id=org.id,
            from_dataset_id=orders.id, from_column="customer_id",
            to_dataset_id=customers.id, to_column="id", confidence=0.9,
        )
        await db_session.commit()

        with pytest.raises(store.ProvenanceError):
            await store.confirm_relationship(db_session, rel.id, org_id=other.id)

        after = await _get(db_session, rel.id)
        assert after.source == "inferred"


class TestColumnStats:
    async def test_upsert_replaces_stats_for_the_same_column(self, db_session, org_and_datasets):
        from app.models.models import DatasetColumn

        org, orders, _ = org_and_datasets
        col = DatasetColumn(dataset_id=orders.id, name="status", dtype="categorical")
        db_session.add(col)
        await db_session.flush()

        first = await store.upsert_column_stats(
            db_session, dataset_column_id=col.id,
            null_ratio=0.1, distinct_count=3,
            top_k=[{"value": "active", "count": 10, "ratio": 0.5}], exact=False,
        )
        await db_session.commit()

        second = await store.upsert_column_stats(
            db_session, dataset_column_id=col.id,
            null_ratio=0.0, distinct_count=2,
            top_k=[{"value": "active", "count": 20, "ratio": 1.0}], exact=True,
        )
        await db_session.commit()

        assert second.id == first.id, "one stats row per column, replaced in place"
        assert second.exact is True
        assert second.distinct_count == 2

    async def test_exact_flag_is_not_lost_between_syncs(self, db_session, org_and_datasets):
        """An estimate must not silently overwrite a measured value with the flag
        still reading True — callers branch on `exact` to decide whether a number
        can be shown to a user as fact."""
        from app.models.models import DatasetColumn

        org, orders, _ = org_and_datasets
        col = DatasetColumn(dataset_id=orders.id, name="amount", dtype="numeric")
        db_session.add(col)
        await db_session.flush()

        await store.upsert_column_stats(db_session, dataset_column_id=col.id,
                                        distinct_count=500, exact=True)
        await db_session.commit()
        row = await store.upsert_column_stats(db_session, dataset_column_id=col.id,
                                              distinct_count=480, exact=False)
        await db_session.commit()
        assert row.exact is False and row.distinct_count == 480
