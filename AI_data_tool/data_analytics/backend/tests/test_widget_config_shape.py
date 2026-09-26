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


# ── E03 slice 3: nested settings and fixed vocabularies ─────────────────────

REFUSED = [
    ({"filters": [{"column": "region", "op": "equals", "value": "N"}]}, "filters[0].op"),
    ({"filters": [{"column": "region", "op": "eq", "value": {"x": 1}}]}, "filters[0].value"),
    ({"filters": [{"column": "day", "op": "relative", "value": {"unit": "fortnight"}}]}, "filters[0]"),
    ({"having": [{"op": "neq", "value": 3}]}, "having[0].op"),
    ({"having": [{"op": "gt", "value": "lots"}]}, "having[0].value"),
    ({"having": "gt 3"}, "having"),
    ({"rank": {"mode": "middle", "n": 5}}, "rank.mode"),
    ({"rank": {"mode": "top", "n": 0}}, "rank.n"),
    ({"rank": {"mode": "top", "n": 5, "other": "yes"}}, "rank.other"),
    ({"sort_keys": [{"col": "region", "dir": "up"}]}, "sort_keys[0].dir"),
    ({"sort_keys": ["region"]}, "sort_keys[0]"),
    ({"display_rules": {"kind": "expression"}}, "display_rules"),
    ({"display_rules": [{"kind": "sparkle"}]}, "display_rules[0].kind"),
    ({"display_rules": ["value > 3"]}, "display_rules[0]"),
    ({"interaction": {"broadcasts": "yes"}}, "interaction.broadcasts"),
    ({"interaction": {"receiveMode": "mirror"}}, "interaction.receiveMode"),
    ({"interaction": {"actions": [{"targetId": "7"}]}}, "interaction.actions[0]"),
    ({"interaction": {"twoWay": True}}, "interaction has no setting"),
    ({"analytics": {"referenceValue": "high"}}, "analytics.referenceValue"),
    ({"analytics": {"trendLine": True}}, "analytics has no setting"),
    ({"sort": "ascending"}, "sort must be one of"),
    ({"sort": 1}, "sort must be one of"),
    ({"bar_mode": "stack"}, "bar_mode must be one of"),
    ({"dimension_granularity": "fortnight"}, "dimension_granularity"),
    ({"limit": -5}, "limit"),
    ({"limit": "ten"}, "limit"),
    ({"suppress_below": 2.5}, "suppress_below"),
]


@pytest.mark.parametrize("config,field", REFUSED, ids=[f for _, f in REFUSED])
def test_an_invalid_nested_setting_is_refused_with_the_field_named(config, field):
    with pytest.raises(InvalidWidget, match=__import__("re").escape(field)):
        validate_widget_payload("bar", config)


#: What the panel and the other editors write (the E03 inventory), each shape
#: at least once. None of it may be refused.
ACCEPTED = [
    {"filters": [{"column": "region", "op": "eq", "value": "North"},
                 {"column": "units", "op": "gt", "value": 3},
                 {"column": "region", "op": "in", "value": ["North", "South"]},
                 {"column": "region", "op": "like", "value": "Nor"},
                 {"column": "day", "op": "relative", "value": {"mode": "last", "n": 30, "unit": "day"}},
                 {"column": "region", "op": "eq", "value": "@region"},
                 {"op": "and"}]},
    {"having": [{"op": "gte", "value": 100}]},
    {"rank": {"mode": "top", "n": 5, "percent": True, "other": True}},
    {"rank": {"mode": "bottom", "n": "@top_n"}},
    {"sort_keys": [{"col": "region", "dir": "asc"}, {"col": "units", "dir": "DESC"}]},
    {"display_rules": [{"id": "r1", "kind": "interval", "target": "mark", "column": "value",
                        "bands": [{"min": 0, "max": 10, "color": "#f00"}]},
                       {"id": "r2", "kind": "value_map", "mappings": [{"value": "N", "color": "#0f0"}]},
                       {"column": "value", "op": "lt", "value": 0, "style": {"color": "#A8443A"}}]},
    {"interaction": {"broadcasts": False, "receives": True, "syncAllPages": True,
                     "receiveMode": "highlight", "actions": [{"targetId": 7, "mode": "filter"}]}},
    {"analytics": {"showAverageLine": True, "referenceValue": 50, "referenceLabel": "Goal",
                   "referenceColor": "#f59e0b"}},
    {"sort": "DESC", "sort_by": "value", "quick_calc": "percent_change", "totals_position": "before",
     "totals_scope": "shown", "bar_mode": "stacked100", "slicer_mode": "dropdown",
     "legend_position": "left", "y_scale": "log", "gauge_shape": "bullet",
     "container_mode": "tabs", "dimension_granularity": "Month", "limit": 0, "suppress_below": 3},
    {"limit": "25", "sort_by": "", "dimension_granularity": ""},
]


@pytest.mark.parametrize("config", ACCEPTED)
def test_every_shape_the_editors_write_is_accepted(config):
    validate_widget_payload(None, config)


async def test_every_seeded_demo_widget_passes(client, auth_headers, db_session):
    """The demo is the largest body of configs not written by the panel."""
    from sqlalchemy import select
    from app.models.models import ReportWidget
    r = await client.post("/api/v1/demo/seed", json={}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    widgets = (await db_session.execute(select(ReportWidget))).scalars().all()
    assert len(widgets) > 100
    refused = []
    for w in widgets:
        try:
            validate_widget_payload(w.widget_type, migrate_widget_config(w.config))
        except InvalidWidget as e:
            refused.append((w.widget_type, w.title, str(e)))
    assert refused == []


def test_the_panel_vocabularies_are_the_servers():
    """SETTING_VOCABULARIES in the panel's configShape.ts must be VOCABULARIES."""
    import re
    from app.services.widget_roles import VOCABULARIES
    path = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "report"
            / "widgetConfigPanel" / "configShape.ts")
    if not path.exists():
        pytest.skip("configShape.ts not reachable")
    block = re.search(r"SETTING_VOCABULARIES[^=]*=\s*\{(.*?)\n\}", path.read_text(encoding="utf-8"), re.S)
    assert block, "SETTING_VOCABULARIES is not in configShape.ts"
    frontend = {k: set(re.findall(r"'([^']+)'", v))
                for k, v in re.findall(r"(\w+): \[([^\]]*)\]", block.group(1))}
    assert frontend == {k: set(v) for k, v in VOCABULARIES.items()}


class TestAStoredLegacyValueDoesNotBlockEdits:
    async def _widget(self, db_session, two_orgs, config):
        from app.models.models import Dataset, Report, ReportPage, ReportWidget
        org_id = two_orgs["a"]["org"].id
        ds = Dataset(name="d", filename="x.csv", org_id=org_id)
        db_session.add(ds)
        await db_session.flush()
        rep = Report(name="R", org_id=org_id, dataset_id=ds.id)
        db_session.add(rep)
        await db_session.flush()
        page = ReportPage(report_id=rep.id, name="P", position=0)
        db_session.add(page)
        await db_session.flush()
        # Written directly, as the copilot or an old version could have.
        w = ReportWidget(page_id=page.id, widget_type="bar", title="t", config=config,
                         layout={"x": 0, "y": 0, "w": 4, "h": 4})
        db_session.add(w)
        await db_session.commit()
        return f"/api/v1/reports/{rep.id}/pages/{page.id}/widgets/{w.id}"

    async def test_an_edit_that_leaves_it_alone_is_saved(self, client, auth_headers, db_session, two_orgs):
        url = await self._widget(db_session, two_orgs, {"dimension": "region", "sort": "ascending"})
        r = await client.patch(url, json={"config": {"dimension": "country", "sort": "ascending"}},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text

    async def test_an_edit_that_sets_an_invalid_value_is_refused(self, client, auth_headers, db_session, two_orgs):
        url = await self._widget(db_session, two_orgs, {"dimension": "region", "sort": "desc"})
        r = await client.patch(url, json={"config": {"dimension": "region", "sort": "ascending"}},
                               headers=auth_headers["a"])
        assert r.status_code == 400
        assert "sort must be one of" in r.json()["detail"]

    async def test_a_create_is_judged_whole(self, client, auth_headers, db_session, two_orgs):
        url = await self._widget(db_session, two_orgs, {})
        base = url.rsplit("/", 1)[0]
        r = await client.post(base, json={"widget_type": "bar", "title": "t",
                                          "config": {"bar_mode": "stack"},
                                          "layout": {"x": 0, "y": 0, "w": 4, "h": 4}},
                              headers=auth_headers["a"])
        assert r.status_code == 400
