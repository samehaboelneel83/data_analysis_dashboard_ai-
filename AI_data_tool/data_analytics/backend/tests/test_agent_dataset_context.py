"""Dataset-mode schema context (Task 16). Same F1 provenance rule as
load_context, except the catalog comes from Dataset/DatasetColumn and joins
from the dataset-level Relationship table — the multi-mode amendment's
single SQL surface starts here.
"""
import pytest

from app.models.models import Dataset, DatasetColumn, Organization, Relationship
from app.services.agent.context import _table_name, load_dataset_context


@pytest.fixture
async def catalog(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    sales = Dataset(name="sales", org_id=org.id, mode="import",
                    description="Sales facts.")
    regions = Dataset(name="regions", org_id=org.id, mode="import")
    db_session.add_all([sales, regions])
    await db_session.flush()

    db_session.add_all([
        DatasetColumn(dataset_id=sales.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=sales.id, name="region_id", dtype="integer"),
        DatasetColumn(dataset_id=regions.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=regions.id, name="name", dtype="text"),
    ])
    db_session.add(Relationship(
        org_id=org.id, from_dataset_id=sales.id, from_column="region_id",
        to_dataset_id=regions.id, to_column="id", source="confirmed"))
    db_session.add(Relationship(
        org_id=org.id, from_dataset_id=sales.id, from_column="id",
        to_dataset_id=regions.id, to_column="id", source="inferred"))
    await db_session.commit()
    return {"org": org, "sales": sales, "regions": regions}


class TestWhatTheAgentKnows:
    async def test_every_dataset_and_column_is_visible(self, db_session, catalog):
        ctx = await load_dataset_context(
            db_session, [catalog["sales"].id, catalog["regions"].id],
            catalog["org"].id)
        assert ctx.family == "duckdb"
        assert ctx.source_id == 0
        assert ctx.has_table("sales")
        assert ctx.has_column("sales", "region_id")
        assert ctx.has_table("regions")
        assert ctx.has_column("regions", "name")

    async def test_kind_is_dataset_and_description_renders(self, db_session, catalog):
        ctx = await load_dataset_context(
            db_session, [catalog["sales"].id], catalog["org"].id)
        assert ctx.objects["sales"].kind == "dataset"
        assert "Sales facts." in ctx.render()


class TestTheProvenanceRule:
    async def test_a_confirmed_join_is_allowed(self, db_session, catalog):
        ctx = await load_dataset_context(
            db_session, [catalog["sales"].id, catalog["regions"].id],
            catalog["org"].id)
        assert ctx.join_allowed("sales", "region_id", "regions", "id")

    async def test_an_inferred_join_never_enters_the_whitelist(self, db_session, catalog):
        """THE most important assertion, per spec F1: inference proposes,
        a human confirms, the agent executes only what survived that ladder."""
        ctx = await load_dataset_context(
            db_session, [catalog["sales"].id, catalog["regions"].id],
            catalog["org"].id)
        assert not ctx.join_allowed("sales", "id", "regions", "id")


class TestOrgScoping:
    async def test_another_orgs_datasets_yield_nothing(self, db_session, catalog):
        other = Organization(name="Rival")
        db_session.add(other)
        await db_session.commit()
        ctx = await load_dataset_context(
            db_session, [catalog["sales"].id, catalog["regions"].id], other.id)
        assert ctx.objects == {}


class TestTableNaming:
    async def test_name_collisions_get_distinct_table_names(self, db_session):
        org = Organization(name="Collide Co")
        db_session.add(org)
        await db_session.flush()
        a = Dataset(name="Sales 2024", org_id=org.id, mode="import")
        b = Dataset(name="Sales-2024", org_id=org.id, mode="import")
        db_session.add_all([a, b])
        await db_session.commit()

        ctx = await load_dataset_context(db_session, [a.id, b.id], org.id)
        assert sorted(ctx.objects) == ["sales_2024", "sales_2024_2"]

    def test_table_name_normalizes(self):
        assert _table_name("Sales 2024") == "sales_2024"
        assert _table_name("Sales-2024") == "sales_2024"
        assert _table_name("") == "table"


# ── What the dataset-mode agent is told the data MEANS ───────────────────────
#
# Dataset mode used to build the agent's whole world from {column: dtype}. The
# glossary was empty by construction, the canonical marker did not exist, coded
# values arrived as bare numbers and no entity's grain was ever mentioned -- all
# of it sitting in the source catalog, one join away, because the loader read a
# different table. These pin that asking through a DATASET now answers from the
# same facts as asking through the CONNECTION.

from app.models.models import (DataSource, Entity, GlossaryTerm, SourceColumn,
                               SourceObject)
from app.services import knowledge


@pytest.fixture
async def described(db_session):
    """A dataset imported from a described table, provenance already linked."""
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    src = DataSource(name="warehouse", type="postgresql", config={}, org_id=org.id)
    db_session.add(src)
    await db_session.flush()

    obj = SourceObject(data_source_id=src.id, org_id=org.id, name="orders",
                       kind="table", description="Every order ever placed.",
                       description_source="inferred", is_canonical=True)
    db_session.add(obj)
    await db_session.flush()
    db_session.add_all([
        SourceColumn(source_object_id=obj.id, name="id", dtype="integer"),
        SourceColumn(source_object_id=obj.id, name="status", dtype="integer",
                     description="Where the order is in fulfilment.",
                     description_source="inferred",
                     enum_labels={"1": "new", "2": "paid", "3": "cancelled"}),
        SourceColumn(source_object_id=obj.id, name="total", dtype="float",
                     comment="Order total, excluding tax."),
    ])
    db_session.add(Entity(org_id=org.id, data_source_id=src.id, name="order",
                          business_name="Order", grain="One row per order placed.",
                          primary_object="orders", source="confirmed"))
    db_session.add(GlossaryTerm(org_id=org.id, data_source_id=None, term="GMV",
                                definition="Gross merchandise value.",
                                synonyms=["إجمالي المبيعات"]))
    await db_session.flush()

    ds = Dataset(name="orders", org_id=org.id, mode="import",
                 data_source_id=src.id, source_table="orders")
    db_session.add(ds)
    await db_session.flush()
    db_session.add_all([
        DatasetColumn(dataset_id=ds.id, name="id", dtype="integer"),
        DatasetColumn(dataset_id=ds.id, name="status", dtype="integer"),
        DatasetColumn(dataset_id=ds.id, name="total", dtype="float"),
    ])
    await db_session.flush()
    await knowledge.link_columns(db_session, ds)
    await db_session.commit()
    return {"org": org, "ds": ds}


class TestDatasetModeKnowsWhatSourceModeKnows:
    async def test_coded_values_arrive_with_their_meanings(self, db_session, described):
        ctx = await load_dataset_context(
            db_session, [described["ds"].id], described["org"].id)
        assert ctx.objects["orders"].enum_labels["status"] == {
            "1": "new", "2": "paid", "3": "cancelled"}

    async def test_each_columns_sentence_arrives(self, db_session, described):
        ctx = await load_dataset_context(
            db_session, [described["ds"].id], described["org"].id)
        descs = ctx.objects["orders"].descriptions
        assert descs["status"] == "Where the order is in fulfilment."
        # The database's own COMMENT, which outranks any inference.
        assert descs["total"] == "Order total, excluding tax."

    async def test_the_canonical_marker_crosses_over(self, db_session, described):
        ctx = await load_dataset_context(
            db_session, [described["ds"].id], described["org"].id)
        assert ctx.objects["orders"].is_canonical is True

    async def test_the_glossary_is_no_longer_empty_by_construction(
            self, db_session, described):
        """The loader's own comment used to say it was. An org's terms apply to
        its data however that data is being asked about."""
        ctx = await load_dataset_context(
            db_session, [described["ds"].id], described["org"].id)
        assert [g.term for g in ctx.glossary] == ["GMV"]
        assert [g.term for g in ctx.glossary_for("what is إجمالي المبيعات")] == ["GMV"]

    async def test_the_entitys_grain_arrives(self, db_session, described):
        """"One row per order placed" is the fact that stops a model
        double-counting, and dataset mode never had it."""
        ctx = await load_dataset_context(
            db_session, [described["ds"].id], described["org"].id)
        assert [(e.business_name, e.grain) for e in ctx.entities] == [
            ("Order", "One row per order placed.")]

    async def test_all_of_it_reaches_the_rendered_prompt(self, db_session, described):
        """The context holding a fact and the model being told it are different
        things -- the render is the only one of those that matters."""
        ctx = await load_dataset_context(
            db_session, [described["ds"].id], described["org"].id)
        text = ctx.render()
        assert "1=new" in text and "2=paid" in text
        assert "Where the order is in fulfilment." in text
        assert "CANONICAL" in text
        assert "One row per order placed." in text

    async def test_a_plain_dataset_renders_as_it_always_did(self, db_session, catalog):
        """No source, no catalog, no decoration. Uploads must not start
        carrying empty markers because a code path grew."""
        ctx = await load_dataset_context(
            db_session, [catalog["sales"].id], catalog["org"].id)
        assert ctx.objects["sales"].descriptions == {}
        assert ctx.objects["sales"].enum_labels == {}
        assert ctx.objects["sales"].is_canonical is False
        assert ctx.entities == []
        assert "CANONICAL" not in ctx.render()
