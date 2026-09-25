"""What depends on a dataset field or measure, and the guarded delete (E05 slice 1).

Nothing could answer "what uses this name?", and deleting a measure removed
the definition and committed: every widget that named it fell through
shape_series to the no-measure branch and silently became a row count. Now
`find_dependents` resolves every stored referencer, GET /dependents exposes it,
and a delete of a referenced measure or calculated column is refused with the
list unless the caller says ?force=true.

Uses the router-test fixtures from conftest: `client`, `db_session`,
`two_orgs`, `auth_headers`.
"""
import pandas as pd
import pytest

from app.models.models import (CommonFilter, DataAlert, Dataset, DatasetColumn, HierarchyNode,
                               Report, ReportPage, ReportWidget)
from app.services.dependencies import config_references, find_dependents

MARGIN = {"name": "Margin", "expression": "SUM(profit) / SUM(sales) * 100", "default_aggregation": "sum"}


async def _dataset(db_session, org_id, tmp_path, **fields):
    path = tmp_path / "d.csv"
    pd.DataFrame([{"region": "East", "sales": 100.0, "profit": 10.0},
                  {"region": "West", "sales": 300.0, "profit": 60.0}]).to_csv(path, index=False)
    fields.setdefault("measures", [MARGIN])
    ds = Dataset(name="Sales", filename=str(path), org_id=org_id, mode="import",
                 row_count=2, col_count=3, **fields)
    db_session.add(ds)
    await db_session.flush()
    for col, dtype in (("region", "categorical"), ("sales", "numeric"), ("profit", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype, missing_pct=0, stats={}))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _widget(db_session, org_id, ds_id, config, title="Margin by region", report_ds=None):
    report = Report(name="Sales report", org_id=org_id, dataset_id=report_ds if report_ds is not None else ds_id)
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="P", position=0)
    db_session.add(page)
    await db_session.flush()
    w = ReportWidget(page_id=page.id, widget_type="bar", title=title, config=config,
                     layout={"x": 0, "y": 0, "w": 6, "h": 4})
    db_session.add(w)
    await db_session.commit()
    return report, w


class TestConfigReferences:
    @pytest.mark.parametrize("config,keys", [
        ({"dimension": "region", "measure": "Margin"}, ["measure"]),
        ({"measures": ["sales", "Margin"]}, ["measures"]),
        ({"roles": {"measure": "Margin", "category": "region"}}, ["roles.measure"]),
        ({"columns": ["region", "Margin"], "sort_col": "Margin"}, ["sort_col", "columns"]),
        ({"filters": [{"column": "region", "op": "eq", "value": "E"}, {"column": "Margin", "op": "gt", "value": 1}]},
         ["filters[1]"]),
        ({"dimension": "region", "measure": "sales"}, []),
        ({"title": "Margin"}, []),      # a title is not a reference
    ])
    def test_names_the_keys_that_reference_it(self, config, keys):
        assert config_references(config, "Margin") == keys


class TestFindDependents:
    async def test_every_referencer_is_found(self, db_session, two_orgs, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path,
                            calculated_columns=[{"name": "unit_profit", "expression": "[profit] / [sales]"}],
                            default_filter_expr="sales > 0")
        ds.measures = [MARGIN, {"name": "Margin2", "expression": "Margin * 2"}]
        report, _ = await _widget(db_session, org, ds.id, {"dimension": "region", "measure": "sales"})
        db_session.add(DataAlert(org_id=org, dataset_id=ds.id, creator_user_id=two_orgs["a"]["user"].id,
                                 name="Low sales", expression="SUM(sales) < 100"))
        db_session.add(HierarchyNode(dataset_id=ds.id, name="Sales level", node_type="level",
                                     column_name="sales"))
        db_session.add(CommonFilter(report_id=report.id, column="sales", op="gt", value=0))
        db_session.add(Dataset(name="Sales by region", org_id=org, mode="import",
                               aggregate_of_dataset_id=ds.id,
                               aggregate_spec={"grain": ["region"],
                                               "measures": [{"column": "sales", "agg": "sum", "name": "total"}]}))
        await db_session.commit()
        await db_session.refresh(ds)

        found = await find_dependents(db_session, ds, "sales")
        kinds = sorted(d["kind"] for d in found)
        assert kinds == ["aggregate", "alert", "calculated_column", "common_filter", "dataset_filter",
                         "hierarchy", "measure", "widget"]
        widget = next(d for d in found if d["kind"] == "widget")
        assert widget["where"] == "measure" and widget["report_id"] == report.id
        assert next(d for d in found if d["kind"] == "measure")["label"] == "Margin"
        assert next(d for d in found if d["kind"] == "aggregate")["where"] == "measures"

    async def test_an_identifier_matches_whole_not_as_a_prefix(self, db_session, two_orgs, tmp_path):
        org = two_orgs["a"]["org"].id
        # No Margin measure here: its expression genuinely names `sales`.
        ds = await _dataset(db_session, org, tmp_path, measures=[],
                            calculated_columns=[{"name": "c", "expression": "sales_tax * 2"}])
        await db_session.refresh(ds)
        assert await find_dependents(db_session, ds, "sales") == []

    async def test_a_widget_on_another_dataset_does_not_count(self, db_session, two_orgs, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        other = Dataset(name="Other", org_id=org, mode="import")
        db_session.add(other)
        await db_session.flush()
        # Same measure NAME on a report whose dataset is `other`.
        await _widget(db_session, org, ds.id, {"measure": "Margin"}, report_ds=other.id)
        # ...but a widget OVERRIDING its dataset to `ds` does count.
        await _widget(db_session, org, ds.id, {"dataset_id": ds.id, "measure": "Margin"},
                      title="Override", report_ds=other.id)
        await db_session.refresh(ds)
        found = await find_dependents(db_session, ds, "Margin")
        assert [d["label"] for d in found] == ["Override on Sales report"]

    async def test_another_orgs_reports_are_invisible(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        await _widget(db_session, two_orgs["b"]["org"].id, ds.id, {"measure": "Margin"})
        await db_session.refresh(ds)
        assert await find_dependents(db_session, ds, "Margin") == []


class TestTheEndpoint:
    async def test_lists_dependents_for_a_reader(self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        await _widget(db_session, org, ds.id, {"dimension": "region", "measure": "Margin"})
        r = await client.get(f"/api/v1/datasets/{ds.id}/dependents", params={"name": "Margin"},
                             headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert [d["kind"] for d in r.json()["dependents"]] == ["widget"]

    async def test_another_org_gets_404(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        r = await client.get(f"/api/v1/datasets/{ds.id}/dependents", params={"name": "Margin"},
                             headers=auth_headers["b"])
        assert r.status_code == 404


class TestGuardedDelete:
    async def test_a_referenced_measure_is_refused_with_the_list(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        await _widget(db_session, org, ds.id, {"dimension": "region", "measure": "Margin"})
        r = await client.delete(f"/api/v1/datasets/{ds.id}/measures/Margin", headers=auth_headers["a"])
        assert r.status_code == 409, r.text
        body = r.json()
        assert "Margin by region" in body["detail"] and "force=true" in body["detail"]
        assert body["dependents"][0]["kind"] == "widget"
        # Still there -- and the chart that names it still draws its margin,
        # not a row count.
        await db_session.refresh(ds)
        assert [m["name"] for m in ds.measures] == ["Margin"]
        w = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                              json={"widget_type": "bar", "config": {"dimension": "region", "measure": "Margin"}},
                              headers=auth_headers["a"])
        assert {x["name"]: x["value"] for x in w.json()["rows"]} == {"East": 10.0, "West": 20.0}

    async def test_force_deletes_anyway(self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        await _widget(db_session, org, ds.id, {"dimension": "region", "measure": "Margin"})
        r = await client.delete(f"/api/v1/datasets/{ds.id}/measures/Margin", params={"force": "true"},
                                headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json() == []

    async def test_an_unreferenced_measure_deletes_as_before(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        r = await client.delete(f"/api/v1/datasets/{ds.id}/measures/Margin", headers=auth_headers["a"])
        assert r.status_code == 200 and r.json() == []

    async def test_a_referenced_calculated_column_is_refused_too(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path,
                            calculated_columns=[{"name": "unit_profit", "expression": "[profit] / [sales]"}])
        await _widget(db_session, org, ds.id, {"dimension": "region", "measure": "unit_profit"})
        r = await client.delete(f"/api/v1/datasets/{ds.id}/calculated-columns/unit_profit",
                                headers=auth_headers["a"])
        assert r.status_code == 409
        r = await client.delete(f"/api/v1/datasets/{ds.id}/calculated-columns/unit_profit",
                                params={"force": "true"}, headers=auth_headers["a"])
        assert r.status_code == 200 and r.json() == []
