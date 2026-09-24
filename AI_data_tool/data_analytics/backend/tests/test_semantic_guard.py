"""Backend half of the semantic veto -- same examples as the frontend's
lib/semanticGuard.test.ts, so the two classifiers cannot drift apart."""
import pandas as pd
import pytest

from app.services.semantic_guard import non_additive_kind, is_quantity


@pytest.mark.parametrize("col,kind", [
    ("latitude", "coordinate"), ("store_lng", "coordinate"),
    ("customer_id", "identifier"), ("zip_code", "identifier"),
    ("year", "year"), ("fiscal_year", "year"),
])
def test_non_additive_columns_are_named(col, kind):
    assert non_additive_kind(col) == kind


@pytest.mark.parametrize("col", ["revenue", "units", "margin_pct", "plateau",
                                 "yearly_revenue", "longevity", "valid"])
def test_quantities_are_left_alone(col):
    assert is_quantity(col)


def test_insights_never_trend_or_correlate_a_year_or_a_coordinate():
    from app.services.insights import generate_insights
    n = 120
    df = pd.DataFrame({
        "month": pd.date_range("2024-01-01", periods=n, freq="D"),
        "region": (["North", "South", "East"] * n)[:n],
        "revenue": [100 + i for i in range(n)],
        "year": [2024 + i // 60 for i in range(n)],
        "latitude": [30.0 + i * 0.01 for i in range(n)],
    })
    types = {"month": "datetime", "region": "categorical", "revenue": "numeric",
             "year": "numeric", "latitude": "numeric"}
    out = generate_insights(df, types)
    text = repr(out)
    assert "latitude" not in text, "a coordinate entered the measure pool"
    assert "'year'" not in text and '"year"' not in text, "a year entered the measure pool"


# ── The veto is ENFORCED, not just advised (MASTER_PLAN Part IV, criterion 4) ──
from app.services.semantic_guard import aggregation_refusal, config_refusal  # noqa: E402


@pytest.mark.parametrize("col,agg", [
    ("year", "sum"), ("fiscal_year", "avg"), ("latitude", "sum"),
    ("customer_id", "sum"), ("customer_id", "avg"), ("order_key", "median"),
])
def test_arithmetic_on_non_quantities_is_refused_with_the_fix(col, agg):
    msg = aggregation_refusal(col, agg)
    assert msg and col in msg and "instead" in msg and "mark it as a measure" in msg


@pytest.mark.parametrize("col,agg", [
    ("year", "max"), ("year", "count"), ("latitude", "avg"), ("customer_id", "countd"),
    ("revenue", "sum"), ("units", "avg"),
])
def test_meaningful_aggregations_pass(col, agg):
    assert aggregation_refusal(col, agg) is None


def test_a_bar_with_no_aggregation_sums_so_it_is_refused():
    v = config_refusal({"dimension": "region", "measure": "year"}, {}, sums_by_default=True)
    assert v and v["column"] == "year" and v["aggregation"] == "sum" and v["safe"] == "max"


def test_a_raw_value_plot_with_a_year_axis_is_fine():
    assert config_refusal({"measure": "year", "measure2": "revenue"}, {}, sums_by_default=False) is None


def test_the_second_measure_is_checked_too():
    v = config_refusal({"measure": "revenue", "measure2": "store_id", "aggregation": "sum"}, {},
                       sums_by_default=True)
    assert v and v["column"] == "store_id" and v["safe"] == "countd"


def test_marking_the_column_a_measure_is_the_override():
    assert config_refusal({"measure": "year", "aggregation": "sum"},
                          {"year": {"role": "measure"}}, sums_by_default=True) is None


@pytest.fixture
def _uploads(tmp_path, monkeypatch):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_the_widget_endpoint_refuses_summing_a_year(client, db_session, two_orgs, auth_headers, _uploads):
    from app.models.models import Dataset, DatasetColumn
    path = _uploads / "sales.csv"
    pd.DataFrame({"region": ["N", "S"], "year": [2024, 2025], "revenue": [1.0, 2.0]}).to_csv(path, index=False)
    ds = Dataset(name="S", filename=str(path), org_id=two_orgs["a"]["org"].id, mode="import",
                 row_count=2, col_count=3)
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("region", "categorical"), ("year", "numeric"), ("revenue", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()

    url = f"/api/v1/datasets/{ds.id}/widget-data"
    r = await client.post(url, json={"config": {"dimension": "region", "measure": "year", "aggregation": "sum"},
                                     "widget_type": "bar"}, headers=auth_headers["a"])
    assert r.status_code == 422
    assert r.json()["code"] == "semantic_veto"
    assert "adds up years" in r.json()["detail"]

    ok = await client.post(url, json={"config": {"dimension": "region", "measure": "year", "aggregation": "max"},
                                      "widget_type": "bar"}, headers=auth_headers["a"])
    assert ok.status_code == 200, ok.text
    fine = await client.post(url, json={"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
                                        "widget_type": "bar"}, headers=auth_headers["a"])
    assert fine.status_code == 200
