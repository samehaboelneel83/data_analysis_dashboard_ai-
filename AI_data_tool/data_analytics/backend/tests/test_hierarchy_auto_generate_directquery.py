from app.models.models import DataSource, Dataset, DatasetColumn


async def _seed_directquery_dataset(db_session, org_id, columns):
    """columns: list of (name, dtype) tuples, mirroring what the schema-probe at
    dataset-creation time stores in DatasetColumn."""
    src = DataSource(name="Live DB", type="sqlite", config={}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="DQ Dataset", org_id=org_id, mode="directquery",
                  data_source_id=src.id, source_table="sales")
    db_session.add(ds)
    await db_session.flush()
    for name, dtype in columns:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_auto_generate_works_for_directquery_dataset_without_a_file(client, db_session, two_orgs, auth_headers):
    """This is the exact 404 seen in production: auto_generate required
    ds.filename unconditionally, so every DirectQuery dataset (which never has
    one) 404'd here. It must instead build the hierarchy from the DatasetColumn
    rows populated at dataset-creation time (the schema probe)."""
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id, [
        ("region", "categorical"), ("revenue", "numeric"), ("order_date", "datetime"),
    ])

    resp = await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])

    assert resp.status_code == 200
    nodes = {n["id"]: n for n in resp.json()}
    dims_folder = next(n for n in nodes.values() if n["node_type"] == "folder" and n["name"] == "Dimensions")
    region_node = next(n for n in nodes.values() if n["parent_id"] == dims_folder["id"])
    assert region_node["name"] == "region"

    measures_folder = next(n for n in nodes.values() if n["node_type"] == "folder" and n["name"] == "Measures")
    revenue_node = next(n for n in nodes.values() if n["parent_id"] == measures_folder["id"])
    assert revenue_node["name"] == "revenue"
    assert revenue_node["aggregation"] == "sum"

    dates_folder = next(n for n in nodes.values() if n["node_type"] == "folder" and n["name"] == "Dates")
    date_node = next(n for n in nodes.values() if n["parent_id"] == dates_folder["id"])
    assert date_node["name"] == "order_date"
    # date drill chain (Year/Quarter/Month/Day) still gets built the same way as import mode
    year_node = next(n for n in nodes.values() if n["parent_id"] == date_node["id"])
    assert year_node["name"] == "Year" and year_node["format"] == "year"
