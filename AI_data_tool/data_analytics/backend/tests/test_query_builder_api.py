"""Query-builder routes end to end against a real SQLite connection: column
introspection, compile, preview with join+aggregation, and the injection
attempts that must die at the membership check."""
import sqlite3

import pytest

from app.models.models import DataSource


@pytest.fixture
def sqlite_source(tmp_path, db_session, two_orgs):
    path = tmp_path / "shop.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE orders (id INTEGER, customer_id INTEGER, region TEXT, amount REAL);
        CREATE TABLE customers (id INTEGER, name TEXT, segment TEXT);
        INSERT INTO orders VALUES (1, 1, 'US', 10.0), (2, 1, 'US', 20.0), (3, 2, 'EU', 40.0);
        INSERT INTO customers VALUES (1, 'Acme', 'SMB'), (2, 'Globex', 'ENT');
    """)
    con.commit()
    con.close()
    return path


async def _source(db, org, path):
    src = DataSource(name="Shop DB", type="sqlite", config={"filepath": str(path)}, org_id=org.id)
    db.add(src)
    await db.commit()
    return src


@pytest.mark.asyncio
async def test_columns_introspection(client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    r = await client.get(f"/api/v1/data-sources/{src.id}/tables/orders/columns",
                        headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert {c["name"] for c in r.json()} == {"id", "customer_id", "region", "amount"}


@pytest.mark.asyncio
async def test_unknown_table_is_refused_at_introspection(client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    r = await client.get(f"/api/v1/data-sources/{src.id}/tables/sqlite_master;drop/columns",
                        headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_compile_and_preview_with_join_and_aggregation(client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    model = {
        "table": "orders",
        "joins": [{"table": "customers", "left_column": "customer_id",
                   "right_column": "id", "how": "inner"}],
        "columns": [{"table": "customers", "column": "segment"},
                    {"column": "amount", "aggregation": "sum", "alias": "total"}],
        "filters": [{"column": "amount", "op": "gte", "value": 10}],
        "sort": [{"alias": "total", "dir": "desc"}],
    }
    r = await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert 'INNER JOIN "customers"' in r.json()["sql"]

    r = await client.post(f"/api/v1/data-sources/{src.id}/build-query/preview", json=model,
                          headers=auth_headers["a"])
    body = r.json()
    assert body["columns"] == ["segment", "total"]
    assert {tuple(row) for row in body["rows"]} == {("ENT", 40.0), ("SMB", 30.0)}
    assert body["rows"][0] == ["ENT", 40.0]     # sorted by total desc


@pytest.mark.asyncio
async def test_injection_shaped_model_400s_without_touching_the_db(client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    bad = {"table": "orders",
           "columns": [{"column": 'amount" FROM orders; DROP TABLE orders; --'}]}
    r = await client.post(f"/api/v1/data-sources/{src.id}/build-query/preview", json=bad,
                          headers=auth_headers["a"])
    assert r.status_code == 400
    # the table survives: the identifier died at membership check, not mid-query
    con = sqlite3.connect(sqlite_source)
    assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 3
    con.close()


@pytest.mark.asyncio
async def test_builder_routes_are_org_scoped(client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    r = await client.get(f"/api/v1/data-sources/{src.id}/tables/orders/columns",
                        headers=auth_headers["b"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_built_query_saves_as_a_working_dataset(client, auth_headers, db_session, two_orgs, sqlite_source):
    """The whole point: compile -> import -> the dataset answers widgets."""
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    model = {"table": "orders",
             "columns": [{"column": "region"},
                         {"column": "amount", "aggregation": "sum", "alias": "revenue"}]}
    sql = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                             headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Built revenue", "query": sql, "mode": "import"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ds_id = r.json()["id"]
    r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "region", "measure": "revenue",
                                           "aggregation": "sum"}},
                          headers=auth_headers["a"])
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"US": 30.0, "EU": 40.0}


@pytest.mark.asyncio
async def test_query_model_round_trips_through_create_and_get(client, auth_headers, db_session, two_orgs, sqlite_source):
    """D1: the builder's graph, not just the compiled SQL, survives create -> GET
    so 'Edit query' can reopen the dialog hydrated instead of losing the design."""
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    model = {"table": "orders",
             "columns": [{"column": "region"},
                         {"column": "amount", "aggregation": "sum", "alias": "revenue"}]}
    sql = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                             headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Built revenue", "query": sql, "mode": "import",
                                "query_model": model},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ds_id = r.json()["id"]

    r = await client.get(f"/api/v1/datasets/{ds_id}", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["query_model"] == model


@pytest.mark.asyncio
async def test_import_without_query_model_leaves_it_null(client, auth_headers, db_session, two_orgs, sqlite_source):
    """Uploads and hand-SQL datasets have no builder graph to restore."""
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Hand SQL", "query": "SELECT * FROM orders", "mode": "import"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ds_id = r.json()["id"]
    r = await client.get(f"/api/v1/datasets/{ds_id}", headers=auth_headers["a"])
    assert r.json()["query_model"] is None


@pytest.mark.asyncio
async def test_reimport_with_dataset_id_replaces_rows_and_model_in_place(client, auth_headers, db_session, two_orgs, sqlite_source):
    """D1: re-importing an existing builder dataset (Edit query -> Create) updates
    the same dataset's data and model rather than creating a sibling row."""
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    model = {"table": "orders", "columns": [{"column": "region"}]}
    sql = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                             headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Regions", "query": sql, "mode": "import", "query_model": model},
                          headers=auth_headers["a"])
    ds_id = r.json()["id"]
    assert r.json()["row_count"] == 3

    con = sqlite3.connect(sqlite_source)
    con.execute("INSERT INTO orders VALUES (4, 2, 'EU', 5.0)")
    con.commit()
    con.close()

    model2 = {"table": "orders", "columns": [{"column": "region"}], "filters": [{"column": "region", "op": "eq", "value": "EU"}]}
    sql2 = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model2,
                              headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Regions (EU)", "query": sql2, "mode": "import",
                                "query_model": model2, "dataset_id": ds_id},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["id"] == ds_id          # same dataset, not a new one
    assert r.json()["row_count"] == 2       # EU rows only, post-insert

    r = await client.get(f"/api/v1/datasets/{ds_id}", headers=auth_headers["a"])
    body = r.json()
    assert body["name"] == "Regions (EU)"
    assert body["query_model"] == model2
    assert body["row_count"] == 2

    all_ds = await client.get("/api/v1/datasets", headers=auth_headers["a"])
    assert len([d for d in all_ds.json() if d["id"] == ds_id]) == 1


@pytest.mark.asyncio
async def test_script_mode_reimport_clears_the_stored_model(client, auth_headers, db_session, two_orgs, sqlite_source):
    """D2: a hand-edited-SQL save (script mode) sends no query_model. Re-importing
    a builder dataset that way must clear query_model in place, not leave the
    stale graph behind -- a hand-edited dataset is no longer visually re-editable,
    which is exactly what the absence of query_model signals to the frontend's
    'Edit query' gating."""
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    model = {"table": "orders", "columns": [{"column": "region"}]}
    sql = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                             headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Regions", "query": sql, "mode": "import", "query_model": model},
                          headers=auth_headers["a"])
    ds_id = r.json()["id"]
    r = await client.get(f"/api/v1/datasets/{ds_id}", headers=auth_headers["a"])
    assert r.json()["query_model"] == model

    hand_sql = "SELECT * FROM orders WHERE region = 'US'"
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Regions (hand-tuned)", "query": hand_sql, "mode": "import",
                                "dataset_id": ds_id},   # no query_model -- script mode
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["id"] == ds_id

    r = await client.get(f"/api/v1/datasets/{ds_id}", headers=auth_headers["a"])
    body = r.json()
    assert body["query_model"] is None
    assert body["source_query"] == hand_sql


@pytest.mark.asyncio
async def test_reimport_with_dataset_id_is_org_scoped(client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    model = {"table": "orders", "columns": [{"column": "region"}]}
    sql = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                             headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Regions", "query": sql, "mode": "import", "query_model": model},
                          headers=auth_headers["a"])
    ds_id = r.json()["id"]

    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Hijack", "query": sql, "mode": "import",
                                "query_model": model, "dataset_id": ds_id},
                          headers=auth_headers["b"])
    assert r.status_code == 404


# ── Provenance: an imported column remembers where its meaning lives ──────────
#
# The defect these pin: every `DatasetColumn(...)` site wrote name/dtype/stats
# and nothing else, so a dataset imported from a described table arrived at the
# dashboard designer and the dataset-mode agent as bare names. The catalog's
# sentences, semantic types and enum labels sat one table away, unreachable.
#
# Tested through the HTTP endpoint on purpose. The service being right has twice
# in this repository not meant the endpoint was.

async def _catalog(db, org, src):
    """A synced catalog for the sqlite_source fixture's two tables."""
    from app.models.models import SourceColumn, SourceObject

    orders = SourceObject(data_source_id=src.id, org_id=org.id, name="orders",
                          kind="table", description="Every order placed.",
                          description_source="inferred")
    customers = SourceObject(data_source_id=src.id, org_id=org.id, name="customers",
                             kind="table")
    db.add_all([orders, customers])
    await db.flush()
    db.add_all([
        SourceColumn(source_object_id=orders.id, name="id", dtype="integer"),
        SourceColumn(source_object_id=orders.id, name="customer_id", dtype="integer"),
        SourceColumn(source_object_id=orders.id, name="region", dtype="text",
                     description="Sales region the order was booked in.",
                     description_source="inferred",
                     enum_labels={"US": "United States", "EU": "Europe"}),
        SourceColumn(source_object_id=orders.id, name="amount", dtype="float",
                     comment="Order total, excluding tax."),
        SourceColumn(source_object_id=customers.id, name="id", dtype="integer"),
        SourceColumn(source_object_id=customers.id, name="segment", dtype="text",
                     description="How big the customer is."),
    ])
    await db.commit()
    return orders


@pytest.mark.asyncio
async def test_a_table_import_records_where_each_column_came_from(
        client, auth_headers, db_session, two_orgs, sqlite_source):
    from sqlalchemy import select

    from app.models.models import Dataset, DatasetColumn
    from app.services import knowledge

    org = two_orgs["a"]["org"]
    src = await _source(db_session, org, sqlite_source)
    await _catalog(db_session, org, src)

    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Orders", "table": "orders",
                                "mode": "import"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ds_id = r.json()["id"]

    cols = {c.name: c for c in (await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds_id)
    )).scalars().all()}
    assert all(c.source_column_id is not None for c in cols.values()), \
        {n: c.source_column_id for n, c in cols.items()}

    ds = await db_session.get(Dataset, ds_id)
    k = await knowledge.for_dataset(db_session, ds)
    assert k.column("region").description == "Sales region the order was booked in."
    assert k.column("region").enum_labels == {"US": "United States", "EU": "Europe"}
    # The database's own COMMENT outranks inference, and survives the trip.
    assert k.column("amount").description == "Order total, excluding tax."
    assert k.object.description == "Every order placed."


@pytest.mark.asyncio
async def test_a_joined_builder_dataset_keeps_its_base_tables_columns(
        client, auth_headers, db_session, two_orgs, sqlite_source):
    """`id` exists on both tables. Without the primary-table tier, joining
    `orders` to `customers` would make the base table's own columns ambiguous
    and strip links the dataset deserved."""
    from sqlalchemy import select

    from app.models.models import DatasetColumn

    org = two_orgs["a"]["org"]
    src = await _source(db_session, org, sqlite_source)
    await _catalog(db_session, org, src)

    model = {
        "table": "orders",
        "joins": [{"table": "customers", "left_column": "customer_id",
                   "right_column": "id", "how": "inner"}],
        "columns": [{"column": "id"}, {"column": "region"},
                    {"table": "customers", "column": "segment"}],
    }
    sql = (await client.post(f"/api/v1/data-sources/{src.id}/build-query", json=model,
                             headers=auth_headers["a"])).json()["sql"]
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Orders by segment", "table": "orders",
                                "query": sql, "mode": "import", "query_model": model},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    cols = {c.name: c for c in (await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == r.json()["id"])
    )).scalars().all()}
    assert cols["id"].source_column_id is not None
    assert cols["region"].source_column_id is not None
    # Reached through the join, from the second tier.
    assert cols["segment"].source_column_id is not None


@pytest.mark.asyncio
async def test_a_source_that_was_never_synced_imports_anyway(
        client, auth_headers, db_session, two_orgs, sqlite_source):
    """No catalog, no links, no failure. Missing metadata must never be able to
    fail an import -- that would make describing a database a prerequisite for
    using it."""
    from sqlalchemy import select

    from app.models.models import DatasetColumn

    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Orders", "table": "orders",
                                "mode": "import"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    cols = (await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == r.json()["id"])
    )).scalars().all()
    assert cols and all(c.source_column_id is None for c in cols)


@pytest.mark.asyncio
async def test_similar_datasets_endpoint_answers_before_anything_is_created(
        client, auth_headers, db_session, two_orgs, sqlite_source):
    """Advisory, never a refusal: the endpoint reports what exists and the
    caller still creates whatever the person asked for."""
    org = two_orgs["a"]["org"]
    src = await _source(db_session, org, sqlite_source)
    await _catalog(db_session, org, src)

    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Orders", "table": "orders",
                                "mode": "import"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    existing = r.json()["id"]

    r = await client.post(f"/api/v1/data-sources/{src.id}/similar-datasets",
                          json={"table": "orders",
                                "columns": ["id", "region", "amount"]},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    matches = r.json()["matches"]
    assert [m["dataset_id"] for m in matches] == [existing]
    assert matches[0]["coverage"] == 1.0
    assert matches[0]["by_name"] is False


@pytest.mark.asyncio
async def test_similar_datasets_is_org_scoped(
        client, auth_headers, db_session, two_orgs, sqlite_source):
    src = await _source(db_session, two_orgs["a"]["org"], sqlite_source)
    r = await client.post(f"/api/v1/data-sources/{src.id}/similar-datasets",
                          json={"table": "orders", "columns": ["id"]},
                          headers=auth_headers["b"])
    assert r.status_code == 404
