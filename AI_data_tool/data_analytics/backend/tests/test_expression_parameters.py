"""Expression-based parameters (gap row 370).

An `expression` parameter's value is computed over the whole source at query time
(RLS-scoped, immune to report/widget filters), so a benchmark like AVG(revenue) or a
self-updating slider bound to max(revenue) reflects the data, not a typed constant.
"""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn


@pytest.fixture
def sales_ds(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({
        "region": ["US", "US", "CA", "CA"],
        "revenue": [100.0, 50.0, 30.0, 20.0],   # avg = 50, max = 100
    }).to_csv(p, index=False)
    return str(p)


async def _setup(client, headers, db, org_id, path, exprs):
    ds = Dataset(name="S", filename=path, org_id=org_id, mode="import")
    db.add(ds)
    await db.flush()
    db.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"))
    db.add(DatasetColumn(dataset_id=ds.id, name="revenue", dtype="numeric"))
    await db.commit()
    r = await client.post("/api/v1/reports", json={"name": "P", "dataset_id": ds.id}, headers=headers)
    report_id = r.json()["id"]
    await client.put(f"/api/v1/reports/{report_id}/parameters", json=exprs, headers=headers)
    return ds, report_id


@pytest.mark.asyncio
async def test_expression_parameter_is_computed_over_the_whole_source(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds,
                                 [{"name": "avg_rev", "param_type": "expression", "default_value": "AVG(revenue)"}])
    # A calc column comparing each row to the computed benchmark (avg = 50):
    body = {"widget_type": "kpi",
            "config": {"measure": "above", "aggregation": "sum"},
            "calculated_columns": [{"name": "above", "expression": "IF(revenue > @avg_rev, 1, 0)"}],
            "report_id": report_id, "parameters": {}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["value"] == 1.0    # only revenue=100 exceeds the avg of 50


@pytest.mark.asyncio
async def test_expression_value_is_immune_to_a_widget_filter(client, auth_headers, db_session, two_orgs, sales_ds):
    """The benchmark is the WHOLE-source avg (50), even though the widget filters to CA
    (whose own avg is 25). A filtered benchmark would defeat the point."""
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds,
                                 [{"name": "avg_rev", "param_type": "expression", "default_value": "AVG(revenue)"}])
    body = {"widget_type": "kpi",
            "config": {"measure": "above", "aggregation": "sum",
                       "filters": [{"column": "region", "op": "eq", "value": "CA"}]},
            "calculated_columns": [{"name": "above", "expression": "IF(revenue > @avg_rev, 1, 0)"}],
            "report_id": report_id, "parameters": {}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    # CA rows are 30 and 20, both below the whole-source avg of 50 → none exceed it.
    assert r.json()["rows"][0]["value"] == 0.0


@pytest.mark.asyncio
async def test_a_viewer_cannot_override_a_computed_expression(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds,
                                 [{"name": "avg_rev", "param_type": "expression", "default_value": "AVG(revenue)"}])
    body = {"widget_type": "kpi",
            "config": {"measure": "above", "aggregation": "sum"},
            "calculated_columns": [{"name": "above", "expression": "IF(revenue > @avg_rev, 1, 0)"}],
            "report_id": report_id, "parameters": {"avg_rev": "1000"}}   # try to force it high
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["value"] == 1.0    # still the computed avg of 50, so 100 exceeds it


@pytest.mark.asyncio
async def test_a_broken_expression_is_a_clear_400(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds,
                                 [{"name": "bad", "param_type": "expression", "default_value": "AVG(nonexistent)"}])
    body = {"widget_type": "kpi",
            "config": {"measure": "x", "aggregation": "sum"},
            "calculated_columns": [{"name": "x", "expression": "revenue + @bad"}],
            "report_id": report_id, "parameters": {}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 400


def test_expression_type_encodes_as_a_number():
    from app.services.parameters import encode_literal
    assert encode_literal("expression", 50.0) == "50.0"
