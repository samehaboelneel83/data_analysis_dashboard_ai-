"""E03: legacy widget-config shapes migrate, and "Percentage %" saves where
it is computed.

`migrate_widget_config` (services/widget_roles.py) and the frontend's
`migrateWidgetConfig` (widgetConfigPanel/configShape.ts) are pinned to the
same cases, widgetConfigPanel/widgetConfigMigrations.json (in the frontend,
whose image type-checks its tests with only its own folder; skipped here
when the frontend is not beside the backend, as the other mirror tests are). A migration that
changed what a widget shows would be worse than the legacy shape, so each
flattening case is also rendered both ways through the real shapers.
"""
import json
import sys
from pathlib import Path

import pytest

from app.services import widget_data as wd
from app.services.widget_roles import InvalidWidget, migrate_widget_config, validate_widget_payload

_CASES_FILE = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "report"
               / "widgetConfigPanel" / "widgetConfigMigrations.json")
CASES = (json.loads(_CASES_FILE.read_text(encoding="utf-8"))["cases"]
         if _CASES_FILE.exists() else [])


@pytest.mark.skipif(not CASES, reason="the frontend's widgetConfigMigrations.json is not reachable")
@pytest.mark.parametrize("case", CASES or [{"name": "none", "in": {}, "out": {}}],
                         ids=[c["name"] for c in CASES] or ["none"])
def test_each_legacy_shape_migrates_as_the_frontend_does(case):
    before = json.loads(json.dumps(case["in"]))
    assert migrate_widget_config(case["in"]) == case["out"]
    assert case["in"] == before                                  # a copy
    assert migrate_widget_config(case["out"]) == case["out"]     # idempotent


def _render(widget_type, config):
    sys.path.insert(0, str(Path(__file__).parent))
    from test_object_families import _option_frame
    frame = _option_frame()
    frame["origin_lat"], frame["origin_lon"], frame["shipments"] = frame["lat"], frame["lon"], frame["units"]
    frame["dest_lat"], frame["dest_lon"] = frame["lat"] + 1, frame["lon"] + 1
    frame["from_city"], frame["to_city"] = frame["region"], frame["product"]
    return json.dumps(wd.get_widget_data_from_df(frame, config, widget_type, None, False),
                      sort_keys=True, default=str)


#: The demo's legacy configs (demo_content.py), each on its own widget type.
DEMO_LEGACY = [
    ("card", {"measures": ["revenue", "cost", "units"],
              "roles": {"measures": ["revenue", "cost", "units"]}, "aggregation": "sum"}),
    ("decomposition", {"roles": {"measure": "revenue"}, "aggregation": "sum", "split_by": "region"}),
    ("map_lines", {"roles": {"lat": "origin_lat", "lon": "origin_lon", "lat2": "dest_lat",
                             "lon2": "dest_lon", "category": "to_city", "measure": "shipments"},
                   "limit": 120}),
    ("map_clusters", {"roles": {"lat": "origin_lat", "lon": "origin_lon", "measure": "shipments"},
                      "cluster_cell_degrees": 10}),
    ("map_layers", {"roles": {"category": "region", "measure": "shipments",
                              "lat": "origin_lat", "lon": "origin_lon"}}),
    ("map_network", {"roles": {"category": "from_city", "category2": "to_city",
                               "lat": "origin_lat", "lon": "origin_lon", "lat2": "dest_lat",
                               "lon2": "dest_lon", "measure": "shipments"}}),
    ("map_density", {"roles": {"lat": "origin_lat", "lon": "origin_lon"}, "cluster_cell_degrees": 8}),
    ("map_contour", {"roles": {"lat": "origin_lat", "lon": "origin_lon", "measure": "shipments"}}),
    ("bar", {"dimension": "region", "measure": "revenue", "agg": "avg"}),
]


@pytest.mark.parametrize("widget_type,config", DEMO_LEGACY, ids=[t for t, _ in DEMO_LEGACY])
def test_migrating_does_not_change_what_the_widget_shows(widget_type, config):
    migrated = migrate_widget_config(config)
    assert "roles" not in migrated and "agg" not in migrated
    assert _render(widget_type, migrated) == _render(widget_type, config)


class TestSavingMigrates:
    async def test_a_legacy_config_is_stored_in_the_current_shape(self, client, auth_headers, db_session, two_orgs):
        from app.models.models import Dataset, Report, ReportPage
        org_id = two_orgs["a"]["org"].id
        ds = Dataset(name="d", filename="x.csv", org_id=org_id)
        db_session.add(ds)
        await db_session.flush()
        rep = Report(name="R", org_id=org_id, dataset_id=ds.id)
        db_session.add(rep)
        await db_session.flush()
        page = ReportPage(report_id=rep.id, name="P", position=0)
        db_session.add(page)
        await db_session.commit()
        url = f"/api/v1/reports/{rep.id}/pages/{page.id}/widgets"
        r = await client.post(url, json={"widget_type": "map_clusters", "title": "t",
                                         "config": {"roles": {"lat": "a", "lon": "b"}, "agg": "sum"},
                                         "layout": {"x": 0, "y": 0, "w": 4, "h": 4}},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        assert r.json()["config"] == {"lat": "a", "lon": "b", "aggregation": "sum"}
        r = await client.patch(f"{url}/{r.json()['id']}",
                               json={"config": {"roles": {"lat": "c", "lon": "d"}}},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["config"] == {"lat": "c", "lon": "d"}


class TestPercentage:
    """`pct` was offered by the panel and computed by the grouped shapers,
    and refused on every save."""

    def test_it_saves_where_it_is_computed(self):
        for wt in ("bar", "line", "pie", "table", "crosstab", "treemap"):
            validate_widget_payload(wt, {"aggregation": "pct"})

    @pytest.mark.parametrize("wt", ["kpi", "heatmap", "gauge", "sunburst", "dual_axis_bar"])
    def test_it_is_refused_where_it_would_be_a_sum_or_an_error(self, wt):
        with pytest.raises(InvalidWidget, match="Percentage"):
            validate_widget_payload(wt, {"aggregation": "pct"})

    def test_a_config_without_a_type_is_not_judged_on_it(self):
        validate_widget_payload(None, {"aggregation": "pct"})
