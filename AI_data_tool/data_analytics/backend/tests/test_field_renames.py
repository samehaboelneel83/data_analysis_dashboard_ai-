"""Renaming a measure or calculated column carries every reference (E05 slice 3).

There was no rename: saving under a new name added a second definition and
left every widget on the old one -- how the demo's "Margin %" came to chart
row counts after its measure became "Margin % (on totals)". The rename
endpoints move the definition and rewrite everything find_dependents reports,
in one transaction.
"""
import pandas as pd

from app.models.models import (CommonFilter, DataAlert, Dataset, DatasetColumn, HierarchyNode,
                               Report, ReportPage, ReportWidget)

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
    report = Report(name="Sales report", org_id=org_id,
                    dataset_id=report_ds if report_ds is not None else ds_id)
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


async def _rename(client, headers, ds_id, kind, old, new):
    path = "measures" if kind == "measure" else "calculated-columns"
    return await client.post(f"/api/v1/datasets/{ds_id}/{path}/{old}/rename",
                             json={"new_name": new}, headers=headers)


class TestRenameAMeasure:
    async def test_widgets_follow_and_keep_their_numbers(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        _, w = await _widget(db_session, org, ds.id, {
            "dimension": "region", "measure": "Margin", "roles": {"measure": "Margin"},
            "measures": ["sales", "Margin"], "sort_col": "Margin",
            "filters": [{"column": "Margin", "op": "gt", "value": 0}]})
        before = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                                   json={"widget_type": "bar", "config": {"dimension": "region", "measure": "Margin"}},
                                   headers=auth_headers["a"])

        r = await _rename(client, auth_headers["a"], ds.id, "measure", "Margin", "Margin %")
        assert r.status_code == 200, r.text
        assert [d["kind"] for d in r.json()["rewritten"]] == ["widget"]

        await db_session.refresh(ds)
        await db_session.refresh(w)
        assert [m["name"] for m in ds.measures] == ["Margin %"]
        cfg = w.config
        assert cfg["measure"] == "Margin %" and cfg["roles"]["measure"] == "Margin %"
        assert cfg["measures"] == ["sales", "Margin %"] and cfg["sort_col"] == "Margin %"
        assert cfg["filters"][0]["column"] == "Margin %"
        after = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                                  json={"widget_type": "bar", "config": {"dimension": "region", "measure": "Margin %"}},
                                  headers=auth_headers["a"])
        assert after.json()["rows"] == before.json()["rows"]     # same margins, not counts

    async def test_expressions_that_build_on_it_follow(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path, measures=[
            MARGIN, {"name": "Margin2", "expression": "Margin * 2"},
            {"name": "Margins", "expression": "SUM(profit)"}])
        r = await _rename(client, auth_headers["a"], ds.id, "measure", "Margin", "M")
        assert r.status_code == 200, r.text
        await db_session.refresh(ds)
        by = {m["name"]: m["expression"] for m in ds.measures}
        assert by["Margin2"] == "M * 2"
        assert "Margins" in by                     # a longer name is not a reference

    async def test_other_datasets_and_orgs_are_untouched(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        other = Dataset(name="Other", org_id=org, mode="import")
        db_session.add(other)
        await db_session.flush()
        _, same_name_elsewhere = await _widget(db_session, org, ds.id, {"measure": "Margin"},
                                               report_ds=other.id)
        _, other_org = await _widget(db_session, two_orgs["b"]["org"].id, ds.id, {"measure": "Margin"})
        r = await _rename(client, auth_headers["a"], ds.id, "measure", "Margin", "M")
        assert r.status_code == 200 and r.json()["rewritten"] == []
        for w in (same_name_elsewhere, other_org):
            await db_session.refresh(w)
            assert w.config["measure"] == "Margin"


class TestRenameACalculatedColumn:
    async def test_every_referencer_kind_follows(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path,
                            calculated_columns=[{"name": "unit", "expression": "[profit] / [sales]"},
                                                {"name": "unit2", "expression": "[unit] * 2"}],
                            measures=[{"name": "U", "expression": "SUM(unit)"}],
                            default_filter_expr="unit > 0",
                            column_formats={"unit": {"type": "percent"}})
        report, w = await _widget(db_session, org, ds.id, {"dimension": "region", "measure": "unit"})
        alert = DataAlert(org_id=org, dataset_id=ds.id, creator_user_id=two_orgs["a"]["user"].id,
                          name="Low unit", expression="AVG(unit) < 0.1")
        level = HierarchyNode(dataset_id=ds.id, name="Unit level", node_type="level", column_name="unit")
        cf = CommonFilter(report_id=report.id, column="unit", op="gt", value=0)
        agg = Dataset(name="Unit by region", org_id=org, mode="import", aggregate_of_dataset_id=ds.id,
                      aggregate_spec={"grain": ["region"],
                                      "measures": [{"column": "unit", "agg": "avg", "name": "u"}]})
        db_session.add_all([alert, level, cf, agg])
        await db_session.commit()

        r = await _rename(client, auth_headers["a"], ds.id, "calculated_column", "unit", "unit_margin")
        assert r.status_code == 200, r.text
        assert sorted(d["kind"] for d in r.json()["rewritten"]) == [
            "aggregate", "alert", "calculated_column", "common_filter", "dataset_filter",
            "hierarchy", "measure", "widget"]

        for obj in (ds, w, alert, level, cf, agg):
            await db_session.refresh(obj)
        assert [c["name"] for c in ds.calculated_columns] == ["unit_margin", "unit2"]
        assert ds.calculated_columns[1]["expression"] == "[unit_margin] * 2"
        assert ds.measures[0]["expression"] == "SUM(unit_margin)"
        assert ds.default_filter_expr == "unit_margin > 0"
        assert ds.column_formats == {"unit_margin": {"type": "percent"}}
        assert w.config["measure"] == "unit_margin"
        assert alert.expression == "AVG(unit_margin) < 0.1"
        assert level.column_name == "unit_margin" and cf.column == "unit_margin"
        assert agg.aggregate_spec["measures"][0]["column"] == "unit_margin"


class TestRefusals:
    async def test_a_clash_or_a_missing_name_changes_nothing(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        ds = await _dataset(db_session, org, tmp_path)
        _, w = await _widget(db_session, org, ds.id, {"measure": "Margin"})
        for new in ("sales", "Margin", "  "):                    # a column, itself, blank
            r = await _rename(client, auth_headers["a"], ds.id, "measure", "Margin", new)
            assert r.status_code == 400, (new, r.text)
        r = await _rename(client, auth_headers["a"], ds.id, "measure", "Nope", "X")
        assert r.status_code == 400
        await db_session.refresh(ds)
        await db_session.refresh(w)
        assert [m["name"] for m in ds.measures] == ["Margin"] and w.config["measure"] == "Margin"

    async def test_another_org_cannot_rename(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        r = await _rename(client, auth_headers["b"], ds.id, "measure", "Margin", "M")
        assert r.status_code == 404
