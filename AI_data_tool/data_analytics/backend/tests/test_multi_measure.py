"""Several measures on one value axis (bar, line, area): revenue AND cost per region.

Each measure is resolved through the ordinary single-measure path and the
results are merged into the split-series (`crosstab`) shape the renderers
already draw. So the numbers must be exactly the single-measure numbers, on
every engine, and a measure the viewer may not see must not appear.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.models.models import Dataset, DatasetColumn
from app.services.multi_measure import MULTI_MEASURE_WIDGETS, measure_list, merge_measure_series
from app.services.widget_roles import InvalidWidget, validate_widget_payload

from .test_column_security import _setup as _hr_with_salary_denied


class TestWhichConfigsAreSeveralMeasures:
    def test_a_measure_plus_extras_on_a_bar_line_or_area(self):
        for t in ("bar", "line", "area"):
            assert measure_list(t, {"measure": "a", "extra_measures": ["b", "c"]}) == ["a", "b", "c"]

    def test_one_measure_is_not_several(self):
        assert measure_list("bar", {"measure": "a"}) is None
        assert measure_list("bar", {"measure": "a", "extra_measures": []}) is None
        assert measure_list("bar", {"measure": "a", "extra_measures": ["a"]}) is None   # a repeat is one

    def test_other_widget_types_ignore_the_key(self):
        assert measure_list("pie", {"measure": "a", "extra_measures": ["b"]}) is None

    def test_a_series_split_wins_over_a_stored_extra(self):
        # Save refuses the pair; a stored one draws as the split rather than fail.
        assert measure_list("bar", {"measure": "a", "extra_measures": ["b"], "dimension2": "d"}) is None


def _series(dim, rows, **extra):
    return {"type": "series", "dimension": dim, "aggregation": "sum",
            "rows": [{"name": n, "value": v} for n, v in rows], "rows_scanned": 9, **extra}


class TestMerging:
    def test_one_column_per_measure_in_the_first_measure_s_order(self):
        out = merge_measure_series(
            [_series("region", [("S", 30), ("N", 10)]), _series("region", [("N", 1), ("S", 3)])],
            ["revenue", "cost"])
        assert out["type"] == "crosstab"
        assert out["columns"] == ["region", "revenue", "cost", "__total__"]
        assert out["rows"] == [["S", 30, 3, None], ["N", 10, 1, None]]
        assert out["measures"] == ["revenue", "cost"] and out["rows_scanned"] == 9

    def test_a_category_only_a_later_measure_has_is_appended_and_unmeasured_is_none(self):
        out = merge_measure_series(
            [_series("r", [("A", 1)]), _series("r", [("A", 2), ("B", 5)])], ["x", "y"])
        assert out["rows"] == [["A", 1, 2, None], ["B", None, 5, None]]

    def test_the_first_measure_that_cannot_draw_speaks_for_the_chart(self):
        err = {"type": "error", "code": "unknown_field", "message": "no such field"}
        assert merge_measure_series([_series("r", [("A", 1)]), err], ["x", "y"]) is err


class TestSaving:
    def test_a_list_of_names_on_a_supported_type(self):
        validate_widget_payload("bar", {"dimension": "r", "measure": "a", "extra_measures": ["b"]})

    @pytest.mark.parametrize("bad", ["b", [1], {"b": 1}])
    def test_only_a_list_of_names(self, bad):
        with pytest.raises(InvalidWidget):
            validate_widget_payload("bar", {"dimension": "r", "measure": "a", "extra_measures": bad})

    def test_not_on_a_type_that_draws_one_measure(self):
        with pytest.raises(InvalidWidget, match="takes one measure"):
            validate_widget_payload("pie", {"dimension": "r", "measure": "a", "extra_measures": ["b"]})

    def test_not_together_with_a_series_split(self):
        with pytest.raises(InvalidWidget, match="cannot be drawn together"):
            validate_widget_payload("bar", {"dimension": "r", "dimension2": "c", "measure": "a",
                                            "extra_measures": ["b"]})

    def test_the_types_are_the_ones_whose_renderers_draw_series(self):
        assert MULTI_MEASURE_WIDGETS == {"bar", "line", "area"}


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["N", "N", "S", "S", "E"],
                  "revenue": [10, 20, 100, 200, 7],
                  "cost": [1, 2, 10, 20, 0.5]}).to_csv(p, index=False)
    return str(p)


async def _ds(db, org, path):
    ds = Dataset(name="Sales", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("revenue", "numeric"), ("cost", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


class TestThroughTheWidgetEndpoint:
    @pytest.fixture(params=[True, False], ids=["duckdb-on", "duckdb-off"])
    def engine(self, request, monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param)
        return request.param

    @pytest.mark.parametrize("widget_type", ["bar", "line", "area"])
    async def test_each_series_is_exactly_its_own_single_measure_chart(
            self, client, auth_headers, db_session, two_orgs, salesfile, engine, widget_type):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        base = {"dimension": "region", "aggregation": "sum", "sort": "desc", "sort_by": "value"}
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", headers=auth_headers["a"], json={
            "widget_type": widget_type, "config": {**base, "measure": "revenue", "extra_measures": ["cost"]}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["type"] == "crosstab" and body["columns"] == ["region", "revenue", "cost", "__total__"]
        # Hand-computed: S 300 / 30, N 30 / 3, E 7 / 0.5 -- ordered by revenue, desc.
        assert [row[:3] for row in body["rows"]] == [["S", 300, 30], ["N", 30, 3], ["E", 7, 0.5]]

    async def test_a_measure_the_viewer_may_not_see_never_appears(self, client, db_session, two_orgs, tmp_path):
        p = tmp_path / "hr.csv"
        pd.DataFrame({"dept": ["Eng", "Eng", "Ops"], "headcount": [5, 3, 4],
                      "salary": [90000.0, 85000.0, 60000.0]}).to_csv(p, index=False)
        ds, headers = await _hr_with_salary_denied(db_session, two_orgs["a"]["org"], str(p))
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", headers=headers, json={
            "widget_type": "bar",
            "config": {"dimension": "dept", "measure": "headcount", "extra_measures": ["salary"],
                       "aggregation": "sum"}})
        assert r.status_code == 200
        text = str(r.json())
        assert "175000" not in text and "90000" not in text and "60000" not in text
