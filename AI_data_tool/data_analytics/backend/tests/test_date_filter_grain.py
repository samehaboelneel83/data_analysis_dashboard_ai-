"""A clicked date bucket filters the other visuals by that bucket.

Live QA 2026-09-28: clicking 20 Aug on a daily line sent
`{"column": "FULL_DATE", "op": "eq", "value": "2026-08-20"}` -- the label the
chart drew, with no grain. Compared with the stored timestamps it matched no
row, so every KPI, bar and heatmap on the dashboard went blank; a drill step
("2026", "2026-Q2") did the same. The server now reads the grain off the
label's shape before any engine sees the filter.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.models.models import Dataset, DatasetColumn
from app.services.widget_data import _apply_filters, infer_date_filter_grains

DATES = {"d"}


class TestInference:
    @pytest.mark.parametrize("value,grain", [
        ("2026-08-20", "day"), ("2026-05", "month"), ("2026-W20", "week"),
        ("2026-Q2", "quarter"), ("2026", "year"), (2026, "year"),
    ])
    def test_each_label_names_its_grain(self, value, grain):
        [f] = infer_date_filter_grains([{"column": "d", "op": "eq", "value": value}], DATES)
        assert f["granularity"] == grain and f["value"] == str(value)

    def test_a_list_of_labels_of_one_grain(self):
        [f] = infer_date_filter_grains([{"column": "d", "op": "in", "value": ["2026-04", "2026-05"]}], DATES)
        assert f["granularity"] == "month"

    @pytest.mark.parametrize("f", [
        {"column": "d", "op": "eq", "value": "2026-05", "granularity": "fiscal_quarter"},  # already named
        {"column": "d", "op": "eq", "value": "2026-08-20 13:45:00"},                        # a timestamp
        {"column": "d", "op": "in", "value": ["2026-04", "2026-Q2"]},                       # mixed grains
        {"column": "d", "op": "gte", "value": "2026-04-01"},                                # a range bound
        {"column": "region", "op": "eq", "value": "2026"},                                  # not a date column
        {"column": "d", "op": "eq", "value": True},
    ])
    def test_everything_else_is_left_alone(self, f):
        assert infer_date_filter_grains([f], DATES) == [f]

    def test_no_filters_is_returned_as_it_came(self):
        assert infer_date_filter_grains(None, DATES) is None


def test_pandas_in_filter_honours_a_grain():
    df = pd.DataFrame({"d": pd.to_datetime(["2026-04-03", "2026-05-09", "2026-06-01"]), "v": [1, 2, 3]})
    out = _apply_filters(df, [{"column": "d", "op": "in", "value": ["2026-04", "2026-06"], "granularity": "month"}])
    assert list(out["v"]) == [1, 3]


@pytest.fixture
def callsfile(tmp_path):
    p = tmp_path / "calls.csv"
    pd.DataFrame({"d": ["2026-04-03", "2026-05-09", "2026-05-20", "2026-05-20", "2026-08-20", "2026-08-20"],
                  "service": ["voice", "data", "voice", "data", "voice", "voice"],
                  "amount": [1, 10, 100, 1000, 10000, 100000]}).to_csv(p, index=False)
    return str(p)


async def _ds(db, org, path):
    ds = Dataset(name="Calls", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("d", "datetime"), ("service", "categorical"), ("amount", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


class TestTheDashboardSeam:
    @pytest.fixture(params=[True, False], ids=["duckdb-on", "duckdb-off"])
    def engine(self, request, monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param)

    async def _post(self, client, headers, ds_id, widget_type, config):
        r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", headers=headers,
                              json={"widget_type": widget_type, "config": config})
        assert r.status_code == 200, r.text
        return r.json()

    @pytest.mark.parametrize("value,total", [
        ("2026-08-20", 110000), ("2026-05", 1110), ("2026-Q2", 1111), ("2026", 111111), ("2026-W21", 1100),
    ])
    async def test_a_kpi_filters_to_the_clicked_bucket(self, client, auth_headers, db_session, two_orgs,
                                                       callsfile, engine, value, total):
        ds = await _ds(db_session, two_orgs["a"]["org"], callsfile)
        data = await self._post(client, auth_headers["a"], ds.id, "kpi", {
            "measure": "amount", "aggregation": "sum",
            "filters": [{"column": "d", "op": "eq", "value": value}]})
        assert data["rows"][0]["value"] == total

    async def test_a_bar_filters_to_the_clicked_day(self, client, auth_headers, db_session, two_orgs,
                                                    callsfile, engine):
        ds = await _ds(db_session, two_orgs["a"]["org"], callsfile)
        data = await self._post(client, auth_headers["a"], ds.id, "bar", {
            "dimension": "service", "aggregation": "count",
            "filters": [{"column": "d", "op": "eq", "value": "2026-05-20"}]})
        assert {r["name"]: r["value"] for r in data["rows"]} == {"voice": 1, "data": 1}


class TestTimeOfDay:
    """Live QA 2026-09-28: a call log's CALL_TIME ("04:50:31 PM") had no hour
    grain, so "activity by hour" needed a hand-written HOUR() formula, and a
    heatmap filtered to incoming calls dropped the hours that had none."""

    calls = pd.DataFrame({
        "t": ["00:10:00 AM", "01:15:00 AM", "01:20:00 AM", "04:50:31 PM", "04:59:00 PM", "11:00:00 PM"],
        "kind": ["OUT", "OUT", "INC", "INC", "OUT", "OUT"],
        "amount": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    })

    def test_hour_labels(self):
        from app.services.widget_data import _dimension_granularity_label
        assert list(_dimension_granularity_label(self.calls["t"], "hour_of_day")) == ["00", "01", "01", "16", "16", "23"]
        stamps = pd.Series(pd.to_datetime(["2026-08-20 13:45", "2026-08-20 13:05"]))
        assert list(_dimension_granularity_label(stamps, "hour")) == ["2026-08-20 13:00"] * 2

    def test_a_clicked_hour_is_read_as_its_grain(self):
        [f] = infer_date_filter_grains([{"column": "d", "op": "eq", "value": "16"}], DATES)
        assert f["granularity"] == "hour_of_day"
        [f] = infer_date_filter_grains([{"column": "d", "op": "eq", "value": "2026-08-20 13:00"}], DATES)
        assert f["granularity"] == "hour"

    def test_the_heatmap_keeps_every_hour_and_counts_empty_cells_as_zero(self):
        from app.services.widget_data import get_widget_data_from_df
        r = get_widget_data_from_df(self.calls, {
            "dimension": "t", "dimension_granularity": "hour_of_day", "dimension2": "kind",
            "measure": "amount", "aggregation": "count",
            "filters": [{"column": "kind", "op": "eq", "value": "INC"}]}, "heatmap")
        assert r["rows_axis"] == [f"{h:02d}" for h in range(24)]
        by_hour = dict(zip(r["rows_axis"], (row[0] for row in r["cells"])))
        assert by_hour["01"] == 1 and by_hour["16"] == 1 and by_hour["02"] == 0 and by_hour["23"] == 0

    def test_an_average_of_no_rows_stays_empty(self):
        from app.services.widget_data import get_widget_data_from_df
        r = get_widget_data_from_df(self.calls, {
            "dimension": "t", "dimension_granularity": "hour_of_day", "dimension2": "kind",
            "measure": "amount", "aggregation": "avg"}, "heatmap")
        cols = r["cols_axis"]
        cell = r["cells"][r["rows_axis"].index("00")][cols.index("INC")]
        assert cell is None

    def test_a_time_only_column_is_recognised(self):
        from app.services.ingest import is_time_only
        assert is_time_only(self.calls["t"])
        assert not is_time_only(pd.Series(["2026-03-04", "2026-03-05"]))
        assert not is_time_only(pd.Series([1, 2, 3]))
        parsed = pd.to_datetime(pd.Series(["04:50:31 PM", "11:00:00 PM"]), format="%I:%M:%S %p")  # one day
        assert is_time_only(parsed)
        assert not is_time_only(pd.Series(pd.to_datetime(["2026-03-04 10:00", "2026-03-05 11:00"])))


def test_a_filter_on_a_column_the_data_lacks_is_disclosed():
    """Live QA 2026-09-28: every row came back under a filter on a column that
    did not exist, with nothing to tell it from a filtered answer. It still
    changes nothing -- a cross-filter from another dataset is meant to -- but
    the result now says which filters did not apply."""
    from app.services.widget_data import get_widget_data_from_df
    df = pd.DataFrame({"service": ["a", "b", "a"], "amount": [1.0, 2.0, 3.0]})
    r = get_widget_data_from_df(df, {"dimension": "service", "aggregation": "count", "filters": [
        {"column": "NOT_A_COLUMN", "op": "eq", "value": "x"},
        {"column": "service", "op": "eq", "value": "a"}]}, "bar")
    assert r["ignored_filters"] == ["NOT_A_COLUMN"]
    assert {x["name"]: x["value"] for x in r["rows"]} == {"a": 2}
    clean = get_widget_data_from_df(df, {"dimension": "service", "aggregation": "count"}, "bar")
    assert "ignored_filters" not in clean
