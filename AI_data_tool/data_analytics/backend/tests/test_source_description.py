"""The database-level description — the artefact a person actually reads.

Column descriptions serve an agent building a query. They do not answer the
question someone has right after connecting a source: *what is in here?* That
needs a summary of the whole database, which is what Stage 5 now produces
alongside the per-column pass.

Structure only is sent — table names, column names, roles, semantic types and
the inferred relationships. No values. What makes a database comprehensible is
its shape and how the parts connect, and that happens to also be the part with
no disclosure risk.
"""
import pytest
from sqlalchemy import select

from app.models.models import (Dataset, DataSource, DatasetColumn, Organization,
                               Relationship)
from app.services.metadata import infer_semantic, store, sync


class FakeClient:
    def __init__(self, result=None):
        self._result = result
        self.last_error = None
        self.prompts = []

    async def complete_json(self, messages, schema, **kw):
        self.prompts.append(messages)
        return self._result


TABLES = [
    {"name": "orders", "row_count": 200, "columns": [
        {"name": "id", "role": "identifier"},
        {"name": "customer_id", "role": "identifier"},
        {"name": "total", "role": "measure", "semantic_type": "currency"},
    ]},
    {"name": "customers", "row_count": 100, "columns": [
        {"name": "id", "role": "identifier"},
        {"name": "email", "semantic_type": "email"},
    ]},
]

RELS = [{"from_table": "orders", "from_column": "customer_id",
         "to_table": "customers", "to_column": "id"}]


class TestPrompt:
    def test_includes_every_table_and_its_columns(self):
        messages = infer_semantic.build_source_prompt("shop", TABLES)
        body = messages[1]["content"]
        assert "orders" in body and "customers" in body
        assert "total" in body

    def test_includes_relationships(self):
        """A list of tables reads as a list of tables. The same list with
        'orders.customer_id -> customers.id' reads as a system, and the
        description that comes back reflects that difference."""
        body = infer_semantic.build_source_prompt("shop", TABLES, RELS)[1]["content"]
        assert "orders.customer_id -> customers.id" in body

    def test_carries_semantic_types(self):
        """Semantic types survive the trim because they say what a column MEANS,
        which is what an overview is about. Per-column roles do not: they matter
        when composing a query, not when explaining a database."""
        body = infer_semantic.build_source_prompt("shop", TABLES)[1]["content"]
        assert "currency" in body
        assert "email" in body

    def test_sends_no_values(self):
        """Structure is what carries the meaning, and it is the part that is
        safe to send."""
        body = infer_semantic.build_source_prompt("shop", TABLES, RELS)[1]["content"]
        assert "@" not in body

    def test_a_very_wide_table_reports_its_width_rather_than_listing_it(self):
        """60 column names tell a reader nothing an overview can use; the count
        does."""
        wide = [{"name": "t", "columns": [{"name": f"c{i}"} for i in range(60)]}]
        body = infer_semantic.build_source_prompt("s", wide)[1]["content"]
        assert "t (60 columns" in body
        assert "c59" not in body


class TestDescribeSource:
    async def test_returns_only_an_overview(self):
        """One call must not grow with the number of tables. Asking for a
        sentence per table here failed outright on an 82-table source: the
        response could not fit its budget, so every attempt truncated mid-JSON
        and three retries burned 18,384 input tokens for nothing. Per-table
        sentences come from the per-table call instead."""
        client = FakeClient({"overview": "A small commerce database."})
        got = await infer_semantic.describe_source_with_llm(
            "shop", TABLES, client, allow=True, relationships=RELS)
        assert got["overview"] == "A small commerce database."
        assert got["tables"] == {}

    async def test_the_prompt_does_not_ask_for_a_list_of_tables(self):
        client = FakeClient({"overview": "x"})
        await infer_semantic.describe_source_with_llm(
            "shop", TABLES, client, allow=True)
        system = client.prompts[0][0]["content"]
        assert "Do not list every table" in system

    async def test_consent_off_makes_no_call(self):
        client = FakeClient({"overview": "x"})
        assert await infer_semantic.describe_source_with_llm(
            "shop", TABLES, client, allow=False) == {}
        assert client.prompts == []

    async def test_unreachable_endpoint_degrades(self):
        assert await infer_semantic.describe_source_with_llm(
            "shop", TABLES, FakeClient(None), allow=True) == {}

    async def test_the_overview_input_stays_bounded_on_a_wide_schema(self):
        """The overview is about the SHAPE of the database. Listing all 1,354
        columns of an 82-table source would bury that in noise and cost
        thousands of tokens."""
        wide = [{"name": f"t{i}",
                 "columns": [{"name": f"c{j}"} for j in range(40)]}
                for i in range(80)]
        messages = infer_semantic.build_source_prompt("big", wide)
        body = messages[1]["content"]
        assert len(body) < 12_000, f"overview prompt is {len(body)} chars"
        # Every table still gets named, with its column count.
        assert "t79 (40 columns" in body


@pytest.fixture
async def seeded(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    src = DataSource(name="shop", type="postgresql", org_id=org.id,
                     allow_llm_sampling=True)
    db_session.add(src)
    await db_session.flush()
    orders = Dataset(name="orders", org_id=org.id, data_source_id=src.id)
    db_session.add(orders)
    await db_session.flush()
    db_session.add(DatasetColumn(dataset_id=orders.id, name="id", dtype="integer"))
    await db_session.commit()
    return {"org": org, "source": src, "orders": orders}


class Cache:
    def get_sample(self, _): return [{"id": 1}]
    def has_sample(self, _): return True
    def put_sample(self, *a): pass
    def evict_if_over_budget(self): return []
    def overlap(self, *a): return 0.0
    def distinct_count(self, *a): return 1
    def row_count(self, _): return 1


class TestPersisted:
    async def test_the_overview_is_written_to_the_source(self, db_session, seeded):
        client = FakeClient({"overview": "Tracks orders for a small shop."})
        run = await sync.run_sync(
            db_session, seeded["source"].id, seeded["org"].id,
            cache=Cache(), llm_client=client, allow_llm=True)
        await db_session.commit()

        await db_session.refresh(seeded["source"])
        assert seeded["source"].description == "Tracks orders for a small shop."
        assert seeded["source"].description_source == "inferred"

        stages = {s["name"]: s for s in run.stages}
        assert stages["infer_semantic"]["detail"]["source_overview"] is True

    async def test_a_table_sentence_rides_on_the_per_table_call(self):
        """The table's own description comes back from the call that was already
        being made for its columns, so a large database costs no extra
        requests for it."""
        client = FakeClient({
            "table": "One row per order.",
            "descriptions": {"total": "The order total."},
        })
        got = await infer_semantic.describe_with_llm(
            "orders", [{"name": "total", "dtype": "numeric"}], client, allow=True)
        assert got[infer_semantic.TABLE_DESCRIPTION_KEY] == "One row per order."
        assert got["total"] == "The order total."

    async def test_a_confirmed_overview_survives_a_resync(self, db_session, seeded):
        """The provenance rule, applied to the description a human edited."""
        seeded["source"].description = "Hand-written, and correct."
        seeded["source"].description_source = store.CONFIRMED
        await db_session.commit()

        client = FakeClient({"overview": "Generated replacement."})
        await sync.run_sync(db_session, seeded["source"].id, seeded["org"].id,
                            cache=Cache(), llm_client=client, allow_llm=True)
        await db_session.commit()

        await db_session.refresh(seeded["source"])
        assert seeded["source"].description == "Hand-written, and correct."

    async def test_no_llm_means_no_overview_but_the_sync_still_succeeds(
        self, db_session, seeded
    ):
        run = await sync.run_sync(db_session, seeded["source"].id, seeded["org"].id,
                                  cache=Cache(), llm_client=None, allow_llm=False)
        await db_session.commit()
        stages = {s["name"]: s for s in run.stages}
        assert stages["infer_semantic"]["status"] == "ok"
        assert stages["infer_semantic"]["detail"]["source_overview"] is False


class TestApi:
    async def test_review_returns_the_source_overview(self, client, auth_headers,
                                                      db_session, two_orgs):
        src = DataSource(name="shop", type="postgresql", org_id=two_orgs["a"]["org"].id,
                         description="What this database holds.",
                         description_source="inferred")
        db_session.add(src)
        await db_session.commit()

        r = await client.get(f"/api/v1/data-sources/{src.id}/review",
                             headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json()["source"]["description"] == "What this database holds."

    async def test_consent_can_be_turned_on(self, client, auth_headers,
                                            db_session, two_orgs):
        src = DataSource(name="shop", type="postgresql", org_id=two_orgs["a"]["org"].id)
        db_session.add(src)
        await db_session.commit()

        r = await client.patch(f"/api/v1/data-sources/{src.id}/metadata-settings",
                               json={"allow_llm_sampling": True},
                               headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json()["allow_llm_sampling"] is True

    async def test_editing_the_description_marks_it_confirmed(
        self, client, auth_headers, db_session, two_orgs
    ):
        src = DataSource(name="shop", type="postgresql", org_id=two_orgs["a"]["org"].id,
                         description="generated", description_source="inferred")
        db_session.add(src)
        await db_session.commit()

        r = await client.patch(f"/api/v1/data-sources/{src.id}/metadata-settings",
                               json={"description": "Mine, and correct."},
                               headers=auth_headers["a"])
        assert r.json()["description_source"] == "confirmed"

    async def test_settings_require_admin(self, client, auth_headers, db_session, two_orgs):
        from app.models.models import Role

        src = DataSource(name="shop", type="postgresql", org_id=two_orgs["a"]["org"].id)
        db_session.add(src)
        role = await db_session.get(Role, two_orgs["a"]["user"].role_id)
        role.is_org_admin = False
        await db_session.commit()

        r = await client.patch(f"/api/v1/data-sources/{src.id}/metadata-settings",
                               json={"allow_llm_sampling": True},
                               headers=auth_headers["a"])
        assert r.status_code == 403

    async def test_another_orgs_source_is_404(self, client, auth_headers,
                                              db_session, two_orgs):
        src = DataSource(name="theirs", type="postgresql",
                         org_id=two_orgs["b"]["org"].id)
        db_session.add(src)
        await db_session.commit()

        r = await client.patch(f"/api/v1/data-sources/{src.id}/metadata-settings",
                               json={"allow_llm_sampling": True},
                               headers=auth_headers["a"])
        assert r.status_code == 404
