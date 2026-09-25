"""Insight-driven widget suggestions, steered by the report description."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn
from app.services.insights import suggest_widgets_from_findings


FINDINGS = [
    {"kind": "standout", "score": 0.6, "title": "A carries 80% of revenue",
     "columns": ["region", "revenue"]},
    {"kind": "correlation", "score": 0.55, "title": "cost moves with weight (r = 0.9)",
     "columns": ["cost", "weight"]},
    {"kind": "trend", "score": 0.4, "title": "revenue in 2026-05 ran 30% above its monthly average",
     "columns": ["revenue", "order_date"]},
    {"kind": "data_quality", "score": 0.9, "title": "notes is 60% missing", "columns": ["notes"]},
]
ROLES = {"region": "categorical", "revenue": "numeric", "cost": "numeric",
         "weight": "numeric", "order_date": "datetime", "notes": "categorical"}


def test_findings_map_to_the_right_widget_types():
    out = suggest_widgets_from_findings(FINDINGS, ROLES)
    by_kind = {s["kind"]: s for s in out}
    assert by_kind["standout"]["widget_type"] == "bar"
    assert by_kind["standout"]["config"] == {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
    assert by_kind["correlation"]["widget_type"] == "scatter"
    # shape_series semantics: dimension = x numeric, measure = y, averaged
    assert by_kind["correlation"]["config"] == {
        "dimension": "cost", "measure": "weight", "aggregation": "avg",
        "limit": 250, "sort": "asc", "sort_by": "name"}
    assert by_kind["trend"]["widget_type"] == "line"
    assert by_kind["trend"]["config"]["dimension_granularity"] == "month"
    # data_quality is prose, never a chart
    assert "data_quality" not in by_kind


def test_description_alignment_boosts_and_reorders():
    """Without a description the standout (0.6) outranks the correlation
    (0.55). A description about cost and weight flips the order."""
    plain = suggest_widgets_from_findings(FINDINGS, ROLES)
    assert plain[0]["kind"] == "standout"

    steered = suggest_widgets_from_findings(
        FINDINGS, ROLES, description="Logistics: how shipping cost relates to package weight")
    assert steered[0]["kind"] == "correlation"
    assert steered[0]["aligned"] is True
    assert "report description" in steered[0]["reason"]
    assert plain[0]["aligned"] is False


def test_snake_case_columns_match_description_words():
    steered = suggest_widgets_from_findings(
        FINDINGS, ROLES, description="orders by date")
    trend = next(s for s in steered if s["kind"] == "trend")
    assert trend["aligned"] is True  # order_date matches "date"


def test_duplicate_configs_collapse():
    doubled = FINDINGS + [dict(FINDINGS[0], score=0.3)]
    out = suggest_widgets_from_findings(doubled, ROLES)
    bars = [s for s in out if s["widget_type"] == "bar"]
    assert len(bars) == 1


@pytest.mark.asyncio
async def test_endpoint_round_trip(client, auth_headers, db_session, two_orgs, tmp_path):
    p = tmp_path / "sug.csv"
    pd.DataFrame({
        "region": ["A"] * 60 + ["B"] * 20 + ["C"] * 20,
        "revenue": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    }).to_csv(p, index=False)
    ds = Dataset(name="S", org_id=two_orgs["a"]["org"].id, filename=str(p))
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("region", "categorical"), ("revenue", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()

    r = await client.post("/api/v1/reports", json={
        "name": "Revenue concentration", "description": "which region carries revenue",
        "dataset_id": ds.id}, headers=auth_headers["a"])
    rid = r.json()["id"]

    resp = await client.post(f"/api/v1/reports/{rid}/suggest-widgets", headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) >= 1
    top = suggestions[0]
    assert top["widget_type"] == "bar"
    assert top["config"]["dimension"] == "region"
    # both its columns appear in the report name/description -> aligned
    assert top["aligned"] is True


@pytest.mark.asyncio
async def test_endpoint_requires_a_dataset(client, auth_headers, two_orgs):
    r = await client.post("/api/v1/reports", json={"name": "No data"}, headers=auth_headers["a"])
    rid = r.json()["id"]
    resp = await client.post(f"/api/v1/reports/{rid}/suggest-widgets", headers=auth_headers["a"])
    assert resp.status_code == 400
