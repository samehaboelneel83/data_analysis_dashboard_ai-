import pandas as pd
from app.models.models import Dataset


async def _seed_dataset_with_file(db_session, org_id, tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    ds = Dataset(name="D", org_id=org_id, filename=str(path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_auto_generate_creates_year_quarter_month_day_chain_for_date_column(
    client, db_session, two_orgs, auth_headers, tmp_path
):
    ds = await _seed_dataset_with_file(db_session, two_orgs["a"]["org"].id, tmp_path, [
        {"order_date": "2024-01-01", "region": "East", "sales": 10},
        {"order_date": "2024-02-01", "region": "West", "sales": 20},
    ])

    resp = await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    assert resp.status_code == 200
    nodes = {n["id"]: n for n in resp.json()}

    dates_folder = next(n for n in nodes.values() if n["node_type"] == "folder" and n["name"] == "Dates")
    date_col_node = next(n for n in nodes.values() if n["parent_id"] == dates_folder["id"])
    assert date_col_node["name"] == "order_date"
    assert date_col_node["column_name"] == "order_date"

    year_node = next(n for n in nodes.values() if n["parent_id"] == date_col_node["id"])
    assert year_node["name"] == "Year" and year_node["format"] == "year"
    quarter_node = next(n for n in nodes.values() if n["parent_id"] == year_node["id"])
    assert quarter_node["name"] == "Quarter" and quarter_node["format"] == "quarter"
    month_node = next(n for n in nodes.values() if n["parent_id"] == quarter_node["id"])
    assert month_node["name"] == "Month" and month_node["format"] == "month"
    day_node = next(n for n in nodes.values() if n["parent_id"] == month_node["id"])
    assert day_node["name"] == "Day" and day_node["format"] == "day"
    # every drill level points back at the same raw column, none has its own aggregation
    for n in (year_node, quarter_node, month_node, day_node):
        assert n["column_name"] == "order_date"
        assert n["aggregation"] is None


async def test_auto_generate_leaves_non_date_columns_flat(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, two_orgs["a"]["org"].id, tmp_path, [
        {"region": "East", "sales": 10}, {"region": "West", "sales": 20},
    ], name="d2.csv")

    resp = await client.post(f"/api/v1/datasets/{ds.id}/hierarchy/auto-generate", headers=auth_headers["a"])
    nodes = resp.json()

    region_node = next(n for n in nodes if n["name"] == "region")
    sales_node = next(n for n in nodes if n["name"] == "sales")
    assert not any(n["parent_id"] == region_node["id"] for n in nodes)  # still a flat leaf
    assert not any(n["parent_id"] == sales_node["id"] for n in nodes)
    assert sales_node["aggregation"] == "sum"
