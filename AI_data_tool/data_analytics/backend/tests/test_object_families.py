"""E08: every object family survives the whole authoring journey.

The plan's acceptance for a reliable reporting core: "15-20 object families
pass role -> configure -> filter -> save/reopen -> export". Each family below
goes through all five, through the API a browser uses:

1. **Role**: the config fills every role the type requires, and each of
   those roles is load-bearing (without it, the type reports it missing).
2. **Configure**: the widget is saved on a report page and accepted.
3. **Filter**: a filter on region = North gives exactly the answer the same
   widget gives over a dataset that holds only North's rows. A filter that
   was skipped, applied after aggregation, or applied to the wrong column
   fails this.
4. **Save and reopen**: the report read back carries the config unchanged,
   and the reopened widget draws the same result.
5. **Export**: the CSV is the table the widget shows, totals row included.
"""
import io

import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn
from app.routers.widget_data import _export_frame
from app.services import widget_data as wd
from app.services.widget_roles import REQUIRED_ROLES, config_key_for_role, missing_roles

REGIONS = ["North", "South", "East", "West"]
PRODUCTS = ["A", "B", "C"]
ROWS = [{"region": REGIONS[i % 4], "product": PRODUCTS[i % 3],
         "day": f"2024-{1 + i % 12:02d}-{1 + i % 27:02d}",
         "revenue": float(10 + (i * 37) % 90), "cost": float(5 + (i * 13) % 40),
         "units": 1 + (i * 7) % 9}
        for i in range(48)]
TYPES = {"region": "categorical", "product": "categorical", "day": "datetime",
         "revenue": "numeric", "cost": "numeric", "units": "numeric"}

FAMILIES = {
    "bar": {"dimension": "product", "measure": "revenue", "aggregation": "sum"},
    "line": {"dimension": "day", "dimension_granularity": "month", "measure": "revenue", "aggregation": "sum"},
    "area": {"dimension": "product", "measure": "units", "aggregation": "sum"},
    "step": {"dimension": "day", "dimension_granularity": "quarter", "measure": "units", "aggregation": "sum"},
    "pie": {"dimension": "product", "measure": "revenue", "aggregation": "sum"},
    "donut": {"dimension": "product", "measure": "cost", "aggregation": "avg"},
    "treemap": {"dimension": "product", "measure": "revenue", "aggregation": "sum"},
    "funnel": {"dimension": "product", "measure": "units", "aggregation": "sum"},
    "dot_plot": {"dimension": "product", "measure": "units", "aggregation": "sum"},
    "word_cloud": {"dimension": "product", "measure": "units", "aggregation": "sum"},
    "waterfall": {"dimension": "product", "measure": "revenue", "aggregation": "sum"},
    "table": {"dimension": "product", "measure": "revenue", "aggregation": "sum", "show_totals": True},
    "crosstab": {"dimension": "product", "dimension2": "region", "measure": "revenue",
                 "aggregation": "sum", "show_totals": True},
    "matrix": {"dimension": "product", "dimension2": "region", "measure": "units", "aggregation": "avg"},
    "heatmap": {"dimension": "product", "dimension2": "region", "measure": "revenue", "aggregation": "sum"},
    "list": {"dimension": "product", "measure": "revenue", "aggregation": "sum"},
    "kpi": {"measure": "revenue", "aggregation": "sum"},
    "card": {"measures": ["revenue", "cost"], "aggregation": "sum"},
    "gauge": {"measure": "units", "aggregation": "avg"},
    "histogram": {"measure": "revenue", "bins": 5},
    "box_plot": {"dimension": "product", "measure": "revenue"},
    "butterfly": {"dimension": "product", "measure": "revenue", "measure2": "cost", "aggregation": "sum"},
    "dual_axis_bar": {"dimension": "product", "measure": "revenue", "measure2": "units", "aggregation": "sum"},
    "bubble": {"dimension": "product", "measure": "revenue", "measure2": "cost", "size": "units",
               "aggregation": "sum"},
}
NORTH = [{"column": "region", "op": "eq", "value": "North"}]
#: Keys that describe the request, not the answer. `partial_period` is about
#: the DATASET's coverage (it ends in September, so September is partial),
#: which a filter rightly does not change; a dataset holding only North's
#: rows does end there.
_VOLATILE = {"cached", "cache", "elapsed_ms", "query_ms", "duration_ms", "engine", "sql", "timing",
             "partial_period"}


def test_there_are_enough_families():
    assert len(FAMILIES) >= 20
    assert set(FAMILIES) <= set(REQUIRED_ROLES)


@pytest.fixture(autouse=True)
def _no_cache():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


@pytest.fixture
async def world(client, db_session, two_orgs, auth_headers, tmp_path):
    org_id = two_orgs["a"]["org"].id
    frame = pd.DataFrame(ROWS)
    ids = {}
    for name, rows in (("all", frame), ("north", frame[frame["region"] == "North"])):
        path = tmp_path / f"{name}.csv"
        rows.to_csv(path, index=False)
        ds = Dataset(name=f"Families {name}", filename=str(path), org_id=org_id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        for col, dtype in TYPES.items():
            db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype))
        ids[name] = ds.id
    await db_session.commit()
    headers = auth_headers["a"]
    rid = (await client.post("/api/v1/reports", json={"name": "Families", "dataset_id": ids["all"]},
                             headers=headers)).json()["id"]
    page_id = (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"][0]["id"]
    return {"client": client, "headers": headers, "datasets": ids, "report": rid, "page": page_id}


async def _data(world, dataset, widget_type, config):
    r = await world["client"].post(
        f"/api/v1/datasets/{world['datasets'][dataset]}/widget-data",
        json={"widget_type": widget_type, "config": config, "report_id": world["report"]},
        headers=world["headers"])
    assert r.status_code == 200, f"{widget_type}: {r.text}"
    return {k: v for k, v in r.json().items() if k not in _VOLATILE}


@pytest.mark.parametrize("widget_type", sorted(FAMILIES))
async def test_the_authoring_journey(world, widget_type):
    config = FAMILIES[widget_type]
    client, headers = world["client"], world["headers"]

    # 1. Role: every required role is filled, and each one is needed.
    assert missing_roles(widget_type, config) == []
    for role in REQUIRED_ROLES[widget_type]:
        key = config_key_for_role(role)
        assert missing_roles(widget_type, {k: v for k, v in config.items() if k != key}), \
            f"{widget_type}: {key} is required but nothing notices it missing"

    # 2. Configure: saved on a page, with the filter.
    filtered = {**config, "filters": NORTH}
    r = await client.post(f"/api/v1/reports/{world['report']}/pages/{world['page']}/widgets",
                          json={"widget_type": widget_type, "title": widget_type, "config": filtered,
                                "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
                          headers=headers)
    assert r.status_code == 201, f"{widget_type}: {r.text}"
    widget_id = r.json()["id"]
    stored = r.json()["config"]
    # The server may add its defaults for a new widget, never change ours.
    assert {k: stored.get(k) for k in filtered} == filtered

    # 3. Filter: the same answer as the widget over North's rows alone.
    shown = await _data(world, "all", widget_type, stored)
    assert shown.get("type") != "empty", f"{widget_type} drew nothing"
    unfiltered_config = {k: v for k, v in stored.items() if k != "filters"}
    assert shown == await _data(world, "north", widget_type, unfiltered_config), \
        f"{widget_type}: the filter does not equal the data it describes"
    assert await _data(world, "all", widget_type, unfiltered_config) != shown, \
        f"{widget_type}: the filter changed nothing"

    # 4. Save and reopen.
    report = (await client.get(f"/api/v1/reports/{world['report']}", headers=headers)).json()
    saved = next(w for p in report["pages"] for w in p["widgets"] if w["id"] == widget_id)
    assert saved["widget_type"] == widget_type
    assert saved["config"] == stored
    assert await _data(world, "all", saved["widget_type"], saved["config"]) == shown

    # 5. Export: the table the widget shows.
    r = await client.post(f"/api/v1/datasets/{world['datasets']['all']}/widget-data/export?format=csv",
                          json={"widget_type": widget_type, "config": saved["config"],
                                "report_id": world["report"]},
                          headers=headers)
    assert r.status_code == 200, f"{widget_type}: {r.text}"
    exported = pd.read_csv(io.BytesIO(r.content))
    expected = pd.read_csv(io.StringIO(_export_frame(shown, saved["config"]).to_csv(index=False)))
    pd.testing.assert_frame_equal(exported, expected, check_dtype=False)
    if shown.get("totals"):
        assert str(exported.iloc[-1, 0]) == "Total"


# --------------------------------------------------------------------------
# No visible no-op controls: "Sort & limit" is offered exactly where it works
# --------------------------------------------------------------------------

def _option_frame():
    rows, i = [], 0
    for region, n in {"North": 9, "South": 6, "East": 4, "West": 2, "Mid": 1}.items():
        for k in range(n):
            rows.append({"region": region, "product": "ABC"[k % 3],
                         "day": f"2024-{1 + i % 12:02d}-{1 + i % 27:02d}",
                         "revenue": float(10 + (i * 37) % 90), "cost": float(5 + (i * 13) % 40),
                         "units": 1 + (i * 7) % 9, "lat": 30 + i % 5, "lon": 31 + i % 3})
            i += 1
    frame = pd.DataFrame(rows)
    frame["day"] = pd.to_datetime(frame["day"])
    return frame


_FILL = {"category": "region", "category2": "product", "measure": "revenue", "measure2": "cost",
         "size": "units", "measures": ["revenue", "cost"], "start": "day", "animation": "day",
         "color": "product", "lat": "lat", "lon": "lon"}
#: Each option, set against a baseline, on a fixture where it must change the answer.
_OPTION_CASES = {
    "sort": ({"sort_by": "value", "sort": "asc"}, {"sort_by": "value", "sort": "desc"}),
    "sort_col": ({"sort_col": "units", "sort": "asc"}, {"sort": "asc"}),
    "sort_custom": ({"sort_custom": ["West", "Mid"]}, {}),
    "having": ({"having": [{"op": "gt", "value": 300}]}, {}),
    "quick_calc": ({"quick_calc": "percent_of_total"}, {}),
    "suppress_below": ({"suppress_below": 3}, {}),
    "limit": ({"limit": 2}, {}),
}
_NO_DATA = {"script", "text", "button", "image", "shape", "web_content", "container", "custom_visual"}


def _data_types():
    return sorted(t for t in wd.SHAPERS if t not in _NO_DATA and not t.startswith("model_"))


@pytest.mark.parametrize("widget_type", _data_types())
def test_each_sort_and_limit_option_is_offered_exactly_where_it_works(widget_type):
    """SORTABLE_WIDGETS and LIMIT_ONLY_WIDGETS decide which of these controls
    the panel shows. An option declared for a type must change its answer;
    one not declared must not -- otherwise the panel either offers a control
    that does nothing (as butterflies, heatmaps and KPIs used to get the whole
    group) or hides one that works."""
    import json
    frame = _option_frame()
    config = {"aggregation": "sum"}
    for role in REQUIRED_ROLES.get(widget_type, ()):
        config[config_key_for_role(role)] = _FILL.get(role, "region")
    config.setdefault("dimension", "region")
    config.setdefault("measure", "revenue")
    if widget_type in ("kpi", "card", "gauge", "histogram", "correlation_matrix", "parallel_coordinates"):
        config.pop("dimension", None)
    declared = set(wd.sort_limit_options(widget_type))
    for option, (on, off) in _OPTION_CASES.items():
        a = wd.get_widget_data_from_df(frame, {**config, **on}, widget_type, None, False)
        b = wd.get_widget_data_from_df(frame, {**config, **off}, widget_type, None, False)
        works = json.dumps(a, sort_keys=True, default=str) != json.dumps(b, sort_keys=True, default=str)
        assert works == (option in declared), \
            f"{widget_type}: '{option}' {'works but is not offered' if works else 'is offered but does nothing'}"


def _values(result):
    """A result without the aggregation name it echoes back."""
    if isinstance(result, dict):
        return {k: _values(v) for k, v in result.items() if k not in ("aggregation", "aggregation2")}
    if isinstance(result, list):
        return [_values(v) for v in result]
    return result


@pytest.mark.parametrize("widget_type", _data_types())
def test_percentage_is_offered_exactly_where_it_is_computed(widget_type):
    """E03: PERCENT_WIDGETS decides where the panel offers "Percentage %" and
    where a save accepts it. Declared: it must turn the values into shares,
    not echo a sum or refuse. Not declared: it must not work there."""
    import json
    frame = _option_frame()
    config = {}
    for role in REQUIRED_ROLES.get(widget_type, ()):
        config[config_key_for_role(role)] = _FILL.get(role, "region")
    config.setdefault("dimension", "region")
    config.setdefault("measure", "revenue")
    if widget_type in ("kpi", "card", "gauge", "histogram", "correlation_matrix", "parallel_coordinates"):
        config.pop("dimension", None)
    pct = wd.get_widget_data_from_df(frame, {**config, "aggregation": "pct"}, widget_type, None, False)
    summed = wd.get_widget_data_from_df(frame, {**config, "aggregation": "sum"}, widget_type, None, False)
    refused = isinstance(pct, dict) and pct.get("type") == "error"
    works = not refused and (json.dumps(_values(pct), sort_keys=True, default=str)
                             != json.dumps(_values(summed), sort_keys=True, default=str))
    assert works == (widget_type in wd.PERCENT_WIDGETS), \
        f"{widget_type}: 'pct' {'works but is not offered' if works else 'is offered but does not compute shares'}"
