"""The one read path for what a dataset's columns MEAN.

Two metadata stores exist and neither writes to the other: the source catalog
(`source_objects` / `source_columns`, filled by `run_catalog_sync`) and the
dataset's own rows (filled by `run_sync` for uploads). Every chart-choosing
consumer used to read only the second, so a dataset imported from a fully
described table arrived at the dashboard designer as bare names and dtypes.

These tests pin the bridge: `dataset_columns.source_column_id` records where a
column came from, and `services/knowledge.for_dataset` resolves meaning through
it at read time -- never by copying, which is what let `relationships` and
`source_relationships` drift apart.
"""
import pytest
from sqlalchemy import select

from app.models.models import (Dataset, DatasetColumn, DataSource, Entity,
                               GlossaryTerm, Organization, SourceColumn,
                               SourceObject)
from app.services import knowledge


@pytest.fixture
async def catalog(db_session):
    """A connection whose `orders` table is described, and a dataset imported
    from it whose columns carry no descriptions of their own -- the exact shape
    every `DatasetColumn(...)` construction site produces."""
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    src = DataSource(name="warehouse", type="postgresql", config={}, org_id=org.id)
    db_session.add(src)
    await db_session.flush()

    orders = SourceObject(data_source_id=src.id, org_id=org.id, name="orders",
                          kind="table", description="Every order ever placed.",
                          description_source="inferred", is_canonical=True)
    customers = SourceObject(data_source_id=src.id, org_id=org.id, name="customers",
                             kind="table")
    db_session.add_all([orders, customers])
    await db_session.flush()

    status = SourceColumn(
        source_object_id=orders.id, name="status", dtype="integer",
        description="Where the order is in fulfilment.",
        description_source="inferred",
        enum_labels={"1": "new", "2": "paid", "3": "cancelled"},
        enum_labels_source="inferred")
    amount = SourceColumn(source_object_id=orders.id, name="amount", dtype="float",
                          comment="Order total, minor units, excluding tax.")
    order_id = SourceColumn(source_object_id=orders.id, name="id", dtype="integer",
                            is_primary_key=True)
    # Same column NAME on a second table: the ambiguity `link_columns` must
    # refuse rather than guess at.
    cust_id = SourceColumn(source_object_id=customers.id, name="id", dtype="integer")
    db_session.add_all([status, amount, order_id, cust_id])
    await db_session.flush()

    ds = Dataset(name="orders", org_id=org.id, mode="import",
                 data_source_id=src.id, source_table="orders")
    db_session.add(ds)
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=ds.id, name="status", dtype="integer", stats={}),
        DatasetColumn(dataset_id=ds.id, name="amount", dtype="float", stats={}),
        DatasetColumn(dataset_id=ds.id, name="id", dtype="integer", stats={}),
    ])
    await db_session.commit()
    return {"org": org, "src": src, "orders": orders, "customers": customers,
            "ds": ds, "status": status, "amount": amount}


class TestLinking:
    async def test_a_table_import_links_every_column_it_recognises(self, db_session, catalog):
        linked = await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()
        assert linked == 3
        cols = (await db_session.execute(
            select(DatasetColumn).where(
                DatasetColumn.dataset_id == catalog["ds"].id))).scalars().all()
        assert all(c.source_column_id is not None for c in cols)

    async def test_linking_twice_changes_nothing(self, db_session, catalog):
        """Idempotent: a re-import must not be able to downgrade a link a
        better-informed earlier run made."""
        first = await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()
        second = await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()
        assert (first, second) == (3, 0)

    async def test_an_upload_links_nothing_and_does_not_raise(self, db_session, catalog):
        upload = Dataset(name="sheet", org_id=catalog["org"].id, mode="import")
        db_session.add(upload)
        await db_session.flush()
        db_session.add(DatasetColumn(dataset_id=upload.id, name="status", dtype="text"))
        await db_session.commit()
        assert await knowledge.link_columns(db_session, upload) == 0

    async def test_an_ambiguous_name_is_left_unlinked_rather_than_guessed(
            self, db_session, catalog):
        """A dataset built from hand-written SQL that names no table. `id` exists
        on two tables, so it stays NULL -- a wrong link would print the
        customers table's sentence beside the orders table's numbers, which is a
        confident lie rather than a missing fact."""
        adhoc = Dataset(name="adhoc", org_id=catalog["org"].id, mode="import",
                        data_source_id=catalog["src"].id,
                        source_query="SELECT id, status FROM something_else")
        db_session.add(adhoc)
        await db_session.flush()
        db_session.add_all([
            DatasetColumn(dataset_id=adhoc.id, name="id", dtype="integer"),
            DatasetColumn(dataset_id=adhoc.id, name="status", dtype="integer"),
        ])
        await db_session.commit()

        assert await knowledge.link_columns(db_session, adhoc) == 1
        await db_session.commit()
        cols = {c.name: c for c in (await db_session.execute(
            select(DatasetColumn).where(
                DatasetColumn.dataset_id == adhoc.id))).scalars().all()}
        assert cols["status"].source_column_id == catalog["status"].id
        assert cols["id"].source_column_id is None

    async def test_sql_that_names_a_table_narrows_the_ambiguity_away(
            self, db_session, catalog):
        """The AI-built path: a proposal is imported as a QUERY with no table.
        The SQL names `orders`, so `id` is no longer ambiguous."""
        adhoc = Dataset(name="proposal", org_id=catalog["org"].id, mode="import",
                        data_source_id=catalog["src"].id,
                        source_query="SELECT id, amount FROM orders WHERE amount > 0")
        db_session.add(adhoc)
        await db_session.flush()
        db_session.add_all([
            DatasetColumn(dataset_id=adhoc.id, name="id", dtype="integer"),
            DatasetColumn(dataset_id=adhoc.id, name="amount", dtype="float"),
        ])
        await db_session.commit()

        assert await knowledge.link_columns(db_session, adhoc) == 2

    async def test_a_table_import_never_reaches_past_its_own_table(
            self, db_session, catalog):
        """The catalog's copy of `orders` has no `segment` column -- a stale
        sync, or a column added since. `customers` has one, and it is the only
        other match in the database.

        It must still stay NULL. "Unique in the catalog" is good enough evidence
        only when the dataset could have come from anywhere; a plain table import
        could not, so linking here would attach the customers table's meaning to
        an orders column, which is the confident lie this function exists to
        refuse.
        """
        ds = Dataset(name="orders again", org_id=catalog["org"].id, mode="import",
                     data_source_id=catalog["src"].id, source_table="orders")
        db_session.add(ds)
        await db_session.flush()
        db_session.add_all([
            DatasetColumn(dataset_id=ds.id, name="status", dtype="integer"),
            DatasetColumn(dataset_id=ds.id, name="segment", dtype="text"),
        ])
        db_session.add(SourceColumn(
            source_object_id=catalog["customers"].id, name="segment", dtype="text",
            description="How big the customer is."))
        await db_session.commit()

        assert await knowledge.link_columns(db_session, ds) == 1
        await db_session.commit()
        cols = {c.name: c for c in (await db_session.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
        )).scalars().all()}
        assert cols["status"].source_column_id is not None
        assert cols["segment"].source_column_id is None


class TestResolvedMeaning:
    async def test_a_linked_column_carries_the_catalogs_sentence_and_labels(
            self, db_session, catalog):
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        status = k.column("status")
        assert status.description == "Where the order is in fulfilment."
        assert status.description_origin == "source"
        assert status.enum_labels == {"1": "new", "2": "paid", "3": "cancelled"}
        assert k.linked_columns == 3
        assert k.has_meaning

    async def test_a_database_comment_outranks_an_inference(self, db_session, catalog):
        """`COMMENT ON COLUMN` is documentation somebody wrote, not a guess."""
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        amount = k.column("amount")
        assert amount.description == "Order total, minor units, excluding tax."
        assert amount.description_source == "declared"
        assert amount.comment == "Order total, minor units, excluding tax."

    async def test_a_confirmed_source_description_beats_an_inferred_dataset_one(
            self, db_session, catalog):
        await knowledge.link_columns(db_session, catalog["ds"])
        catalog["status"].description = "Fulfilment state, confirmed by the DBA."
        catalog["status"].description_source = "confirmed"
        col = (await db_session.execute(
            select(DatasetColumn).where(
                DatasetColumn.dataset_id == catalog["ds"].id,
                DatasetColumn.name == "status"))).scalar_one()
        col.description = "A guess made from the imported file."
        col.description_source = "inferred"
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert k.column("status").description == "Fulfilment state, confirmed by the DBA."

    async def test_an_unlinked_dataset_still_uses_its_own_description(
            self, db_session, catalog):
        """Uploads keep working exactly as before -- `run_sync` writes their
        descriptions onto the dataset rows and nothing else can."""
        upload = Dataset(name="sheet", org_id=catalog["org"].id, mode="import",
                         description="A spreadsheet somebody mailed in.")
        db_session.add(upload)
        await db_session.flush()
        db_session.add(DatasetColumn(
            dataset_id=upload.id, name="total", dtype="float",
            description="Sum of the row.", description_source="inferred"))
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, upload)
        assert k.column("total").description == "Sum of the row."
        assert k.column("total").description_origin == "dataset"
        assert k.linked_columns == 0

    async def test_what_the_rows_ARE_comes_through(self, db_session, catalog):
        """Canonical marker and the entity's grain -- the two facts that most
        often stop a model aggregating the wrong table."""
        db_session.add(Entity(
            org_id=catalog["org"].id, data_source_id=catalog["src"].id,
            name="order", business_name="Order",
            grain="One row per order placed.", primary_object="orders",
            source="confirmed"))
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert k.object.is_canonical is True
        assert k.object.grain == "One row per order placed."
        assert k.object.business_name == "Order"
        assert k.object.description == "Every order ever placed."

    async def test_a_denied_column_is_absent_entirely(self, db_session, catalog):
        """Not described-but-hidden. A prompt must never mention a column the
        viewer's role may not see, which is the same rule
        `SchemaContext.denied_columns` enforces for the agent."""
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"], denied={"amount"})
        assert "amount" not in k.columns
        assert "status" in k.columns


class TestGlossary:
    async def test_org_wide_and_this_sources_terms_arrive_and_others_do_not(
            self, db_session, catalog):
        other = DataSource(name="other", type="postgresql", config={},
                           org_id=catalog["org"].id)
        db_session.add(other)
        await db_session.flush()
        db_session.add_all([
            GlossaryTerm(org_id=catalog["org"].id, data_source_id=None, term="GMV",
                         definition="Gross merchandise value.",
                         synonyms=["إجمالي المبيعات"]),
            GlossaryTerm(org_id=catalog["org"].id, data_source_id=catalog["src"].id,
                         term="paid order", definition="status = 2.", synonyms=[]),
            GlossaryTerm(org_id=catalog["org"].id, data_source_id=other.id,
                         term="churn", definition="Not this source's term.",
                         synonyms=[]),
        ])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert {g.term for g in k.glossary} == {"GMV", "paid order"}

    async def test_a_term_is_found_by_its_arabic_synonym(self, db_session, catalog):
        db_session.add(GlossaryTerm(
            org_id=catalog["org"].id, data_source_id=None, term="GMV",
            definition="Gross merchandise value.", synonyms=["إجمالي المبيعات"]))
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert [g.term for g in k.terms_for("ما هو إجمالي المبيعات؟")] == ["GMV"]


class TestAlreadyHaveOneLikeThis:
    """The step the AI path never had. Asked to build a dashboard, the platform
    imported a fresh dataset every time -- a shelf of near-identical datasets
    nobody chose, each refreshing on its own schedule and drifting apart.

    Answerable only because provenance says which SOURCE COLUMNS a dataset is
    built from: two datasets naming a column `id` are not similar, two built
    from `orders.id` are.
    """

    async def test_it_finds_the_dataset_that_already_covers_the_columns(
            self, db_session, catalog):
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        got = await knowledge.similar_datasets(
            db_session, source_id=catalog["src"].id, org_id=catalog["org"].id,
            column_names=["status", "amount"], table="orders")
        assert [m.dataset_id for m in got] == [catalog["ds"].id]
        assert got[0].coverage == 1.0
        assert got[0].by_name is False
        assert got[0].matched_columns == ["amount", "status"]

    async def test_a_dataset_sharing_only_incidental_columns_is_not_similar(
            self, db_session, catalog):
        """Two datasets out of one warehouse share `id` without being about
        remotely the same thing. Below the coverage floor, that is noise."""
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        got = await knowledge.similar_datasets(
            db_session, source_id=catalog["src"].id, org_id=catalog["org"].id,
            column_names=["id", "shipped_at", "carrier", "tracking_number",
                          "weight_kg"],
            table="orders")
        assert got == []

    async def test_the_dataset_being_replaced_can_be_excluded(
            self, db_session, catalog):
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        got = await knowledge.similar_datasets(
            db_session, source_id=catalog["src"].id, org_id=catalog["org"].id,
            column_names=["status", "amount"], table="orders",
            exclude_dataset_id=catalog["ds"].id)
        assert got == []

    async def test_an_unlinked_dataset_still_matches_but_says_it_is_weaker(
            self, db_session, catalog):
        """No provenance on either side, so names are all there is. Answered,
        and labelled, rather than silently presented with the same confidence as
        a real match."""
        legacy = Dataset(name="old orders", org_id=catalog["org"].id,
                         mode="import", data_source_id=catalog["src"].id)
        db_session.add(legacy)
        await db_session.flush()
        db_session.add_all([
            DatasetColumn(dataset_id=legacy.id, name="status", dtype="integer"),
            DatasetColumn(dataset_id=legacy.id, name="amount", dtype="float"),
        ])
        await db_session.commit()

        got = await knowledge.similar_datasets(
            db_session, source_id=catalog["src"].id, org_id=catalog["org"].id,
            column_names=["status", "amount"], table="orders")
        weak = [m for m in got if m.dataset_id == legacy.id]
        assert weak and weak[0].by_name is True

    async def test_asking_about_nothing_answers_nothing(self, db_session, catalog):
        assert await knowledge.similar_datasets(
            db_session, source_id=catalog["src"].id, org_id=catalog["org"].id,
            column_names=[]) == []


class TestOutcomesWorthExplaining:
    """`key_influencers`, `decision_tree` and `automated_prediction` all answer
    "what drives X" and all need somebody to say what X is. A heuristic over
    flag-shaped columns cannot know that `readmitted_30d` is the question this
    hospital cares about while `is_active` is a housekeeping bit.

    Recorded on the SOURCE column, so it is a target in every dataset built from
    that table — with a per-dataset override for the case where one dataset has
    a different question in mind.
    """

    async def test_a_target_recorded_on_the_catalog_reaches_every_dataset(
            self, db_session, catalog):
        catalog["status"].target_candidate_priority = 10
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert k.column("status").target_priority == 10
        assert [c.name for c in k.targets()] == ["status"]

    async def test_this_dataset_may_disagree_with_the_catalog(
            self, db_session, catalog):
        """One dataset genuinely having a different question in mind is the
        reason the override exists."""
        catalog["status"].target_candidate_priority = 10
        await knowledge.link_columns(db_session, catalog["ds"])
        catalog["ds"].column_meta = {"amount": {"target_candidate_priority": 50}}
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        # Strongest first, and the dataset's own answer outranks nothing here --
        # it simply adds one the catalog never named.
        assert [c.name for c in k.targets()] == ["amount", "status"]

    async def test_most_columns_are_not_targets_and_that_is_the_default(
            self, db_session, catalog):
        """A platform that treats every column as an outcome worth explaining
        produces a great deal of confident noise."""
        await knowledge.link_columns(db_session, catalog["ds"])
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert k.targets() == []
        assert all(c.target_priority is None for c in k.columns.values())

    async def test_an_ineligible_column_is_not_offered_as_a_target(
            self, db_session, catalog):
        """Eligibility and target-hood interact exactly once, here: a column the
        author will not let the platform volunteer must not become the thing it
        volunteers a whole dashboard about."""
        catalog["status"].target_candidate_priority = 10
        await knowledge.link_columns(db_session, catalog["ds"])
        catalog["ds"].column_meta = {"status": {"eligible_for_suggestion": False}}
        await db_session.commit()

        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert k.column("status").target_priority == 10     # still recorded
        assert k.targets() == []                            # never offered
        assert "status" not in k.suggestable()

    async def test_eligibility_defaults_to_true_because_absence_is_not_a_rule(
            self, db_session, catalog):
        k = await knowledge.for_dataset(db_session, catalog["ds"])
        assert all(c.eligible_for_suggestion for c in k.columns.values())
        assert set(k.suggestable()) == set(k.columns)
