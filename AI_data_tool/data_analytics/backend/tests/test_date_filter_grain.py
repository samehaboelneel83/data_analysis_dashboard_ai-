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
