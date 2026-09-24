"""Tests for the demo reports.

The load-bearing test in this file is
`test_every_widget_returns_data_the_renderer_can_actually_draw`. A widget whose
config keys are subtly wrong looks fully configured in the database and renders a
blank tile in the browser, and a test that only checks the ReportWidget row exists
would pass. So every data-driven widget is pushed through the real widget-data path
(`get_widget_data` — the same call the HTTP endpoint makes) and the SHAPE of the
result is checked against what that widget's renderer reads:

  * `shape_series` falls back to a raw-table dump when neither `dimension` nor
    `measure` resolves, so a misspelt `dimension` key on a bar chart still returns
    a long, non-empty `rows` list. Asserting only "rows is non-empty" would pass
    that. Asserting `type == "series"` and that each row carries `name`/`value` —
    the two keys BarChartRenderer reads — does not.
  * heatmap/ribbon, correlation_matrix, parallel_coordinates, waterfall and gauge
    return no `rows` key at all; their payload lives under `cells`, `matrix`,
    `lines`, `bars` and `value`. A generic `result["rows"]` check would report
    those as broken even when correct, so each has its own validator.

Four widget types (text, button, shape, image) have no data of their own — they
are never sent to the widget-data path by the renderer. They are listed explicitly
in DATA_EXEMPT so the exemption is a deliberate, reviewable decision rather than a
silent gap, and they get their own test over the content keys WidgetRenderer reads.
"""
import re
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import DatasetColumn, Report, ReportPage, ReportWidget
from app.services.demo_content import (
    DEMO_REPORT_NAMES,
    is_demo_report,
    seed_demo_datasets,
    seed_demo_reports,
)
from app.services.widget_data import get_widget_data

GRID_COLUMNS = 12

# Widget types with no data of their own. WidgetRenderer.tsx returns for these
# before it ever looks at `data`, so there is nothing for the widget-data path to
# return and a data assertion on them would be meaningless.
DATA_EXEMPT = {"text", "button", "shape", "image", "container", "web_content", "custom_visual"}

# The widget types each demo report is required to carry, from the plan. Task 4
# appends its own two reports to this mapping.
EXPECTED_TYPES: dict[str, list[str]] = {
    "Demo — Sales Overview": [
        "kpi", "kpi", "kpi", "card", "bar", "line", "area", "pie", "donut",
        "table", "crosstab", "matrix", "list", "gauge", "funnel", "ribbon",
        "treemap", "heatmap", "slicer", "text", "button", "shape", "image",
        "waterfall", "step", "dot_plot", "needle", "butterfly", "web_content", "custom_visual",
        "script",
        # Six hierarchy layouts, beside the treemap they are cousins of. All
        # six share one shaper, so seeing them together in one report is also
        # the demo of that guarantee: different pictures, identical numbers.
        "tree", "sunburst", "icicle", "dendrogram", "org", "circle_pack",
        "custom_graph",
    ],
    "Demo — Distributions": [
        "histogram", "box_plot", "scatter", "bubble", "correlation_matrix",
        "parallel_coordinates", "numeric_series", "vector_plot",
    ],
    "Demo — Time & Change": [
        "dual_axis_bar", "dual_axis_line", "dual_axis_bar_line",
        "dual_axis_time_series", "comparative_time_series", "bubble_change",
        "forecast", "sankey", "decomposition", "small_multiples",
    ],
    "Demo — Projects & Feedback": [
        "schedule", "word_cloud",
    ],
    "Demo — World Sales Map": ["map_choropleth", "map_points", "map_bubbles",
                               "map_lines", "map_clusters", "network",
                               "map_pie", "map_layers", "map_density", "map_contour",
                               "map_network", "container", "kpi", "kpi"],
    "Demo — Models": ["model_linear", "model_tree", "model_compare", "model_score",
                      "model_logistic", "model_cluster"],
}

# The authority for "every widget type". There is no backend enum to read: the
# backend takes widget_type as a bare `str` in schemas.py, and its two type-shaped
# collections are both deliberate subsets -- widget_data.SHAPERS omits the four
# canvas objects and the slicer (they fall through to shape_series or never reach
# the data path), and direct_query.AGGREGATE_STRATEGY_WIDGET_TYPES is an explicit
# pushdown allowlist that its own comment says must NOT track the full list. The
# `WidgetType` union in the frontend is the one place that enumerates all of them,
# and it is what the widget catalog, ROLE_SPECS and the renderer switch are all
# typed against -- so a 43rd widget type has to appear there first.
_REPORT_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "types" / "report.ts"


def _widget_types_from_the_union() -> set[str]:
    """Parse the `WidgetType` union out of frontend/src/types/report.ts.

    Reading the union rather than copying it is the whole point: a hardcoded list
    of 42 goes stale the moment someone adds a widget, and the demo silently stops
    covering everything the app offers.
    """
    src = _REPORT_TS.read_text(encoding="utf-8")
    match = re.search(r"export type WidgetType\s*=\s*((?:\s*\|\s*'[a-z0-9_]+')+)", src)
    assert match, f"could not find the WidgetType union in {_REPORT_TS}"
    return set(re.findall(r"'([a-z0-9_]+)'", match.group(1)))


def _widget_types_from_the_catalog() -> set[str]:
    """The types the Add-widget menu offers, from WIDGET_CATALOG in the same file."""
    src = _REPORT_TS.read_text(encoding="utf-8")
    match = re.search(r"export const WIDGET_CATALOG = \[(.*?)^\]", src, re.S | re.M)
    assert match, f"could not find WIDGET_CATALOG in {_REPORT_TS}"
    return set(re.findall(r"type:\s*'([a-z0-9_]+)'\s+as WidgetType", match.group(1)))


# ── Result-shape validators ───────────────────────────────────────────────────
# One per widget type: the contract between the shaper in widget_data.py and the
# renderer that consumes it. Each raises AssertionError describing what is wrong.

def _series(result, *, min_rows=1):
    assert result.get("type") == "series", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= min_rows, f"only {len(rows)} rows"
    for r in rows:
        assert "name" in r and "value" in r, r
    assert any(r["value"] is not None for r in rows), "every value is null"


def _numeric_x_series(result):
    """scatter — ScatterChartRenderer maps rows to {x: r.x ?? r.name} and puts x on a
    `type="number"` axis, so a categorical dimension produces a series that is
    perfectly well-formed and still plots nothing. `_series` alone cannot see that."""
    _series(result, min_rows=10)
    for r in result["rows"]:
        assert isinstance(r["name"], (int, float)) and not isinstance(r["name"], bool), (
            f"x value {r['name']!r} is not numeric — it lands on a numeric axis"
        )


def _scalar(result):
    assert result.get("type") == "scalar", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) == 1, rows
    assert rows[0].get("value") is not None, rows


def _card(result):
    rows = result.get("rows") or []
    assert len(rows) >= 2, f"card shows {len(rows)} value(s)"
    for r in rows:
        assert r.get("value") is not None, r


def _tabular(expected_type):
    def check(result):
        assert result.get("type") == expected_type, result.get("type")
        assert result.get("columns"), "no columns"
        rows = result.get("rows") or []
        assert len(rows) >= 1, "no rows"
        assert len(rows[0]) == len(result["columns"]), "row width != column count"
    return check


def _matrix_shape(result):
    """heatmap / ribbon — the renderers read rows_axis, cols_axis and cells."""
    assert result.get("type") == "heatmap", result.get("type")
    assert result.get("rows_axis"), "no row axis"
    assert result.get("cols_axis"), "no column axis"
    cells = result.get("cells") or []
    assert len(cells) == len(result["rows_axis"]), "cells/rows_axis mismatch"
    assert any(v is not None for row in cells for v in row), "every cell is null"


def _gauge(result):
    assert result.get("type") == "gauge", result.get("type")
    assert result.get("value") is not None, "no value"
    assert result.get("target") is not None, "no target — the arc has nothing to compare against"


def _script(result):
    """A script tile draws whatever its code returned, so what has to be true
    is that the code RAN: an error here means the demo ships a tile showing a
    traceback to everyone evaluating the product."""
    assert result.get("type") == "script", result.get("type")
    assert not result.get("error"), result.get("error")
    assert result.get("columns"), "no columns"
    assert result.get("rows"), "no rows"


def _waterfall(result):
    assert result.get("type") == "waterfall", result.get("type")
    bars = result.get("bars") or []
    assert len(bars) >= 2, f"only {len(bars)} bar(s)"
    for b in bars:
        assert {"name", "start", "delta", "end"} <= set(b), b


def _dual_series(result):
    assert result.get("type") == "dual_series", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= 2, f"only {len(rows)} rows"
    for r in rows:
        assert r.get("value") is not None and r.get("value2") is not None, r


def _box_plot(result):
    assert result.get("type") == "box_plot", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= 2, f"only {len(rows)} box(es)"
    for r in rows:
        assert {"min", "q1", "median", "q3", "max"} <= set(r), r


def _bubble(result):
    assert result.get("type") == "bubble_series", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= 10, f"only {len(rows)} bubbles"
    for r in rows:
        assert r.get("x") is not None and r.get("y") is not None and r.get("size") is not None, r


def _correlation(result):
    assert result.get("type") == "matrix", result.get("type")
    measures = result.get("measures") or []
    matrix = result.get("matrix") or []
    assert len(measures) >= 3, measures
    assert len(matrix) == len(measures), "matrix is not square against measures"
    assert all(len(row) == len(measures) for row in matrix), "ragged matrix"


def _parallel(result):
    assert result.get("type") == "parallel_coordinates", result.get("type")
    axes = result.get("axes") or []
    lines = result.get("lines") or []
    assert len(axes) >= 3, axes
    assert len(lines) >= 10, f"only {len(lines)} lines"
    assert all(len(line) == len(axes) for line in lines), "a line does not cross every axis"


def _xy(result):
    assert result.get("type") == "xy_series", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= 10, f"only {len(rows)} points"
    for r in rows:
        assert r.get("x") is not None and r.get("y") is not None, r


def _vector(result):
    assert result.get("type") == "vector_plot", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= 10, f"only {len(rows)} arrows"
    for r in rows:
        assert {"x", "y", "size", "direction"} <= set(r), r


def _bubble_animated(result):
    """bubble_change — BubbleChangePlotRenderer renders `data.frames` as the scrubber
    and shows only the rows whose `frame` equals the selected one. One frame is a
    still picture: a change chart needs at least two to have anything to move
    between, and every frame needs bubbles or scrubbing to it blanks the tile."""
    assert result.get("type") == "bubble_animated_series", result.get("type")
    frames = result.get("frames") or []
    assert len(frames) >= 2, f"{len(frames)} frame(s) — nothing to show change between"
    rows = result.get("rows") or []
    assert len(rows) >= 2 * len(frames), f"only {len(rows)} bubbles across {len(frames)} frames"
    for r in rows:
        assert r.get("x") is not None and r.get("y") is not None and r.get("size") is not None, r
        assert r.get("frame") in frames, f"row frame {r.get('frame')!r} is not in {frames}"
    for f in frames:
        assert [r for r in rows if r["frame"] == f], f"frame {f!r} has no bubbles"


def _gantt(result):
    """schedule — ScheduleChartRenderer runs Date.parse over start/end and DROPS every
    row that does not parse, so an unparseable date column renders "Configure widget
    to see data" rather than an error. It also draws the bar as max(0, end - start),
    so start and end the wrong way round produce a chart of zero-width bars."""
    assert result.get("type") == "gantt", result.get("type")
    rows = result.get("rows") or []
    assert len(rows) >= 10, f"only {len(rows)} task bar(s)"
    for r in rows:
        assert r.get("name") and r.get("start") and r.get("end"), r
        start, end = pd.to_datetime(r["start"], errors="coerce"), pd.to_datetime(r["end"], errors="coerce")
        assert pd.notna(start) and pd.notna(end), f"unparseable dates: {r}"
        assert end > start, f"bar has no width: {r}"
    assert any(r.get("group") for r in rows), "no group — every bar draws in the same colour"


def _word_cloud(result):
    """word_cloud — WordCloudRenderer draws `row.name` verbatim as one word. Pointed at
    a free-text column it lays whole sentences into the cloud, which d3-cloud mostly
    fails to place: non-empty rows, empty picture."""
    _series(result, min_rows=5)
    for r in result["rows"]:
        assert len(str(r["name"]).split()) <= 2, f"{r['name']!r} is a phrase, not a word"


def _geo_series(result):
    """Region-mode maps are series-shaped; every row's name must MATCH a country in the
    frontend atlas, or the demo ships a map with holes. The alias table lives in
    worldGeometry.ts; this asserts the demo's own data stays within it."""
    _series(result)
    known = {"United States", "US", "USA", "Canada", "United Kingdom", "UK", "France",
             "Germany", "Japan", "Australia", "Brazil", "India", "China", "Mexico",
             "Spain", "Italy", "Netherlands", "Chile", "Argentina", "South Korea",
             "Singapore"}
    names = {r["name"] for r in result["rows"]}
    unknown = names - known
    assert not unknown, f"demo map rows outside the known-alias set: {unknown}"


def _forecast(result):
    assert result.get("type") == "forecast"
    assert len(result.get("rows") or []) >= 4, "forecast needs visible history"
    fc = result.get("forecast") or []
    assert len(fc) >= 1, "no forecast points"
    # The band must widen with horizon -- a flat band means the interval is fake.
    assert (fc[-1]["hi"] - fc[-1]["lo"]) > (fc[0]["hi"] - fc[0]["lo"])


def _sankey(result):
    assert result.get("type") == "sankey"
    assert result.get("nodes") and result.get("links"), "sankey needs nodes and links"
    for l in result["links"]:
        assert l["source"] != l["target"], "self-loop would blank the widget"


def _geo_lines(result):
    assert result.get("type") == "geo_lines"
    rows = result.get("rows") or []
    assert rows, "line map needs at least one route"
    for r in rows[:20]:
        assert -90 <= r["lat"] <= 90 and -90 <= r["lat2"] <= 90


def _geo_clusters(result):
    assert result.get("type") == "geo_clusters"
    rows = result.get("rows") or []
    assert rows and all(r.get("count", 0) >= 1 for r in rows)
    # clustering must actually cluster: fewer markers than source rows
    assert len(rows) < result.get("total", 10**9)


def _network(result):
    assert result.get("type") == "network"
    assert result.get("nodes") and result.get("links")
    for n in result["nodes"][:20]:
        assert 0.0 <= n["x"] <= 1.0 and 0.0 <= n["y"] <= 1.0
        assert "betweenness" in n and "closeness" in n


def _geo_pies(result):
    assert result.get("type") == "geo_pies"
    rows = result.get("rows") or []
    assert rows
    for r in rows:
        assert r["slices"], "a pie with no slices draws nothing"
        assert abs(sum(x["value"] for x in r["slices"]) - r["total"]) < 1e-6


def _geo_layers(result):
    assert result.get("type") == "geo_layers"
    assert result.get("regions"), "the demo layered map assigns the region roles"
    assert result.get("points"), "the demo layered map assigns the point roles"


def _geo_network(result):
    assert result.get("type") == "geo_network"
    assert result.get("nodes") and result.get("links")
    for n in result["nodes"]:
        assert -90 <= n["lat"] <= 90 and n["degree"] >= 1


def _hierarchy(result):
    """Tree, sunburst, icicle, dendrogram, org and circle pack share one shaper, so one
    validator states what all five need to be drawable."""
    assert result.get("root"), "a hierarchy with no root draws nothing"
    root = result["root"]
    assert root.get("children"), "a root with no children draws nothing"

    # THE property, the same one decomposition pins: the parts must add up to
    # the whole at EVERY level. A sunburst divides its parent's angle among its
    # children, so children that do not sum to their parent draw a picture the
    # data does not support -- and the reader cannot see that it is wrong.
    def reconciles(node):
        kids = node.get("children") or []
        if kids and node.get("value") is not None:
            total = sum(c["value"] or 0 for c in kids)
            assert abs(node["value"] - total) < 1e-6, (
                f"{node['name']} does not reconcile with its children")
        for c in kids:
            reconciles(c)
    reconciles(root)

    # A partition layout must not be showing a non-additive aggregation: the
    # shaper refuses it, and the demo must not be configured around the refusal.
    if result.get("type") in ("sunburst", "icicle"):
        assert result.get("additive"), (
            "a partition chart drawing a non-additive aggregation states "
            "something false about the data")


def _decomposition(result):
    assert result.get("type") == "decomposition"
    children = result.get("children") or []
    assert children, "a decomposition with no children draws nothing"
    # THE property: the parts must add up to the whole. A drill-down whose
    # children do not reconcile is worse than none, because the reader trusts
    # the parts anyway and cannot see what is missing.
    total = result.get("total")
    assert abs(sum(c["value"] for c in children) - total) < 1e-6
    assert result.get("split_by"), "the level has to say what it split by"


def _small_multiples(result):
    assert result.get("type") == "small_multiples"
    panels = result.get("panels") or []
    assert panels, "small multiples with no panels draws nothing"
    assert any(p["result"].get("rows") for p in panels), "every panel is empty"
    # The shared scale is the point of the visual; without it the panels are
    # three unrelated charts that happen to sit together.
    assert result.get("max_value"), "no shared scale across the panels"


def _custom_graph(payload: dict) -> None:
    """Every layer the config asked for is present and keyed."""
    layers = payload.get("layers") or []
    assert layers, "a composed graph returned no layers"
    keys = {lyr["key"] for lyr in layers}
    assert len(keys) == len(layers), "two layers share a key"
    for row in payload.get("rows") or []:
        for key in keys:
            assert key in row, f"row is missing layer {key}"


def _geo_contour(result):
    assert result.get("type") == "geo_contour", result.get("type")
    assert result.get("levels"), "a contour map with no levels draws nothing"
    assert result.get("points_used"), "no points reached the density estimate"


def _model(result):
    """A model widget that FITTED: a named fit statistic, a population that
    says which rows it used, and something for the renderer to draw."""
    assert result.get("type") == "model", result.get("type")
    assert result.get("status") == "ok", result.get("message") or result.get("status")
    if result.get("model") != "compare":
        assert (result.get("fit") or {}).get("name"), "the fit statistic is unnamed"
        assert (result.get("population") or {}).get("rows_used"), "no population disclosed"


VALIDATORS = {
    "model_linear": _model, "model_logistic": _model, "model_tree": _model,
    "model_cluster": _model, "model_compare": _model, "model_score": _model,
    "map_contour": _geo_contour,
    "small_multiples": _small_multiples,
    "decomposition": _decomposition,
    # One validator for six layouts, matching the one shaper behind them.
    "tree": _hierarchy, "sunburst": _hierarchy, "icicle": _hierarchy,
    "dendrogram": _hierarchy, "org": _hierarchy, "circle_pack": _hierarchy,
    # A composed graph is checked by its LAYERS: rows keyed s0/s1 mean nothing
    # without the layer list that names them.
    "custom_graph": _custom_graph,
    "kpi": _scalar,
    "forecast": _forecast, "sankey": _sankey,
    "map_choropleth": _geo_series, "map_points": _geo_series, "map_bubbles": _geo_series,
    "map_lines": _geo_lines, "map_clusters": _geo_clusters, "network": _network,
    "map_pie": _geo_pies, "map_layers": _geo_layers, "map_density": _geo_clusters,
    "map_network": _geo_network,
    "card": _card,
    "script": _script,
    "bar": _series, "line": _series, "area": _series, "pie": _series,
    "donut": _series, "treemap": _series, "funnel": _series, "list": _series,
    "slicer": _series, "step": _series, "dot_plot": _series, "needle": _series,
    "histogram": _series,
    "scatter": _numeric_x_series,
    "table": _tabular("table"),
    "crosstab": _tabular("crosstab"),
    "matrix": _tabular("crosstab"),
    "heatmap": _matrix_shape,
    "ribbon": _matrix_shape,
    "gauge": _gauge,
    "waterfall": _waterfall,
    "butterfly": _dual_series,
    "box_plot": _box_plot,
    "bubble": _bubble,
    "correlation_matrix": _correlation,
    "parallel_coordinates": _parallel,
    "numeric_series": _xy,
    "vector_plot": _vector,
    # All five share shape_dual_series — they differ only in how they are drawn, and
    # every one of their renderers reads rows[].value / rows[].value2.
    "dual_axis_bar": _dual_series,
    "dual_axis_line": _dual_series,
    "dual_axis_bar_line": _dual_series,
    "dual_axis_time_series": _dual_series,
    "comparative_time_series": _dual_series,
    "bubble_change": _bubble_animated,
    "schedule": _gantt,
    "word_cloud": _word_cloud,
}


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    from app.core.config import settings as app_settings

    target = tmp_path / "uploads"
    monkeypatch.setattr(app_settings, "upload_dir", str(target))
    return target


async def _seed(db_session, org_id):
    datasets = await seed_demo_datasets(db_session, org_id)
    reports = await seed_demo_reports(db_session, org_id, datasets)
    return datasets, reports


async def _loaded_reports(db_session, org_id):
    result = await db_session.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org_id)
        .order_by(Report.id)
    )
    return result.scalars().unique().all()


def _widgets(report) -> list[ReportWidget]:
    return [w for page in report.pages for w in page.widgets]


# ── Structure ─────────────────────────────────────────────────────────────────

async def test_seed_creates_the_demo_reports_in_the_callers_org(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    _, reports = await _seed(db_session, org_id)

    assert [r.name for r in reports] == list(EXPECTED_TYPES)
    assert {r.org_id for r in reports} == {org_id}
    assert set(DEMO_REPORT_NAMES.values()) >= set(EXPECTED_TYPES)


async def test_each_report_is_bound_to_the_demo_dataset_it_charts(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    datasets, reports = await _seed(db_session, org_id)

    by_name = {r.name: r for r in reports}
    assert by_name["Demo — Sales Overview"].dataset_id == datasets["sales"].id
    assert by_name["Demo — Distributions"].dataset_id == datasets["metrics"].id
    assert by_name["Demo — Time & Change"].dataset_id == datasets["sales"].id
    assert by_name["Demo — Projects & Feedback"].dataset_id == datasets["projects"].id
    # The word cloud on that last report charts a SECOND dataset. A report that does
    # not list it cannot resolve it: ReportBuilder builds its dataset map from
    # dataset_id + additional_dataset_ids, so the widget's per-widget override lands
    # on `undefined` and the tile renders nothing.
    assert by_name["Demo — Projects & Feedback"].additional_dataset_ids == [datasets["feedback"].id]


async def test_each_report_carries_exactly_the_widget_types_the_plan_assigns_it(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    for report in await _loaded_reports(db_session, org_id):
        expected = EXPECTED_TYPES.get(report.name)
        if expected is None:
            continue
        actual = sorted(w.widget_type for w in _widgets(report))
        assert actual == sorted(expected), report.name


def test_the_widget_type_list_really_comes_from_the_type_definitions():
    """Guard the parser, not the demo.

    If the regex above stopped matching, `_widget_types_from_the_union()` would
    return an empty set and the coverage test below would pass over nothing at all.
    Cross-checking it against WIDGET_CATALOG — a second, independently written
    declaration in the same file — makes that impossible to miss, and catches the
    other rot too: a widget type that exists in the union but is missing from the
    Add-widget menu can never be placed on a report by hand.
    """
    from_union = _widget_types_from_the_union()

    assert "bar" in from_union and "word_cloud" in from_union, sorted(from_union)
    assert from_union == _widget_types_from_the_catalog(), (
        "the WidgetType union and WIDGET_CATALOG disagree: "
        f"union only={sorted(from_union - _widget_types_from_the_catalog())}, "
        f"catalog only={sorted(_widget_types_from_the_catalog() - from_union)}"
    )


async def test_the_demo_covers_every_widget_type_the_app_offers(db_session, two_orgs):
    """The point of the demo: one live example of every widget type there is.

    Derived from the real `WidgetType` union, never from a copy of it — a hardcoded
    list of 42 silently rots the moment someone adds a 43rd widget, which is exactly
    the day this test is supposed to fail.
    """
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    covered = {
        w.widget_type
        for report in await _loaded_reports(db_session, org_id)
        for w in _widgets(report)
    }
    declared = _widget_types_from_the_union()

    assert declared - covered == set(), (
        f"the demo has no example of: {sorted(declared - covered)}"
    )
    assert covered - declared == set(), (
        f"the demo seeds widget types the app does not declare: {sorted(covered - declared)}"
    )


async def test_every_widget_has_a_title_so_the_demo_reads_as_a_report(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            assert (w.title or "").strip(), f"{report.name}/{w.widget_type} has no title"


# ── The load-bearing test ─────────────────────────────────────────────────────

async def _with_scoring_model(db, config: dict) -> dict:
    from app.models.models import PredictionModel
    from app.services.analysis.model_store import PackagedModel
    from app.services.model_widgets import register_scoring_model
    row = await db.get(PredictionModel, int(config["prediction_model_id"]))
    assert row is not None, "the demo's scoring widget points at no saved model"
    pkg = PackagedModel(artifact=bytes(row.artifact), target=row.target,
                        features=list(row.features or []), feature_columns=list(row.feature_columns or []),
                        categories=dict(row.categories or {}), task=row.task,
                        model_family=row.model_family, score=row.score, score_name=row.score_name or "")
    key = f"demo:{row.id}"
    register_scoring_model(key, pkg, row.name)
    return {**config, "__model__": key}


async def test_every_widget_returns_data_the_renderer_can_actually_draw(db_session, two_orgs):
    """Push every data-driven widget through the real widget-data path.

    Not just "the row exists" and not just "rows is non-empty": the result TYPE and
    the per-row keys are checked against what the widget's renderer reads, because
    shape_series answers a misspelt `dimension` key with a raw-table dump that is
    non-empty and undrawable.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    checked = 0
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            if w.widget_type in DATA_EXEMPT:
                continue
            dataset_id = w.config.get("dataset_id") or report.dataset_id
            path = by_id[dataset_id].filename
            config = w.config
            if w.widget_type == "model_score":
                # The endpoint loads and security-checks the saved model, then
                # hands the shaper a key to it; this is that hand-off.
                config = await _with_scoring_model(db_session, config)
            result = get_widget_data(path, config, widget_type=w.widget_type, use_cache=False)
            validator = VALIDATORS.get(w.widget_type)
            assert validator is not None, f"no validator for {w.widget_type}"
            try:
                validator(result)
            except AssertionError as e:
                raise AssertionError(
                    f"{report.name} / {w.widget_type} ({w.title!r}) returned something the "
                    f"renderer cannot draw: {e}\nconfig={w.config}\nresult keys={sorted(result)}"
                ) from None
            checked += 1

    expected_checked = sum(
        len([t for t in types if t not in DATA_EXEMPT]) for types in EXPECTED_TYPES.values()
    )
    assert checked == expected_checked


async def test_a_configured_column_list_is_the_column_list_that_comes_back(db_session, two_orgs):
    """shape_series answers an unrecognised `columns` key by dumping every column in
    the file. The result is a perfectly valid, non-empty table — of the wrong thing —
    so the shape validators above cannot tell the two apart.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    seen = 0
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            configured = w.config.get("columns")
            if not configured:
                continue
            path = by_id[w.config.get("dataset_id") or report.dataset_id].filename
            result = get_widget_data(path, w.config, widget_type=w.widget_type, use_cache=False)
            assert result["columns"] == configured, (report.name, w.title)
            seen += 1

    assert seen >= 1, "no widget in the demo configures an explicit column list"


async def test_the_time_series_widgets_group_by_the_granularity_they_ask_for(db_session, two_orgs):
    """An unrecognised `dimension_granularity` key is not an error: shape_series just
    groups by the raw timestamp instead. `limit` then truncates the thousands of
    resulting groups back to a plausible-looking handful of {name, value} rows, so
    the chart draws — with one point per transaction instead of one per month.
    """
    patterns = {"month": r"^\d{4}-\d{2}$", "quarter": r"^\d{4}-Q[1-4]$"}
    expected_buckets = {"month": 24, "quarter": 8}  # the sales frame spans 24 months
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    # Driven off the column's detected dtype, not off the presence of the config key:
    # a test that only inspects widgets which already declare a granularity skips
    # exactly the widget that lost it.
    dtypes: dict[int, dict[str, str]] = {}
    for ds in datasets.values():
        result = await db_session.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
        )
        dtypes[ds.id] = {c.name: c.dtype for c in result.scalars().all()}

    seen = 0
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            dim = w.config.get("dimension")
            dataset_id = w.config.get("dataset_id") or report.dataset_id
            if not dim or dtypes[dataset_id].get(dim) != "datetime":
                continue
            granularity = w.config.get("dimension_granularity")
            assert granularity in patterns, (
                f"{w.title!r} groups by the datetime column {dim!r} with granularity "
                f"{granularity!r} — one group per raw timestamp, not per period"
            )
            path = by_id[dataset_id].filename
            rows = get_widget_data(
                path, w.config, widget_type=w.widget_type, use_cache=False
            )["rows"]
            assert len(rows) == expected_buckets[granularity], (w.title, len(rows))
            for r in rows:
                assert re.match(patterns[granularity], str(r["name"])), (w.title, r["name"])
            seen += 1

    # 4 since the forecast widget joined: its history rows are the same monthly
    # buckets, so the sweep checks it too.
    assert seen == 4, f"expected 4 time-bucketed widgets, checked {seen}"


async def test_the_time_axis_widgets_plot_one_point_per_month_across_both_years(db_session, two_orgs):
    """The `start` role's twin of the granularity test above.

    shape_dual_series has no `dimension_granularity` handling at all — it groups by the
    raw column. A `start` pointing at the date column therefore yields one point per
    calendar day, and `limit` trims that to a series that is exactly as long, as
    well-formed and as drawable as the right one, covering the first few weeks of 2024
    instead of two years. `_dual_series` cannot tell the two apart; this can.
    """
    time_axis_types = {"dual_axis_time_series", "comparative_time_series"}
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    seen = 0
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            if w.widget_type not in time_axis_types:
                continue
            path = by_id[w.config.get("dataset_id") or report.dataset_id].filename
            result = get_widget_data(path, w.config, widget_type=w.widget_type, use_cache=False)
            names = [str(r["name"]) for r in result["rows"]]
            assert len(names) == 24, f"{w.title!r} plots {len(names)} points, not 24 months"
            for n in names:
                assert re.match(r"^\d{4}-\d{2}$", n), f"{w.title!r} plots {n!r}, not a month"
            assert names == sorted(names), f"{w.title!r} runs out of chronological order"
            assert {n[:4] for n in names} == {"2024", "2025"}, (
                f"{w.title!r} covers only {sorted({n[:4] for n in names})}"
            )
            seen += 1

    assert seen == len(time_axis_types), f"expected {len(time_axis_types)} time-axis widgets, checked {seen}"


async def test_no_widget_totals_a_rate(db_session, two_orgs):
    """Summing a percentage column produces a number with no meaning that still draws
    a perfectly convincing bar — the failure mode a shape validator cannot see. Rates
    have to be averaged (or taken at a percentile), never totalled."""
    rate_columns = {"margin_pct", "progress_pct"}
    totalling = {"sum", "cumulative", "running_sum"}
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    seen = 0
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            used = {w.config.get(k) for k in ("measure", "measure2", "size", "color")}
            if not (used & rate_columns):
                continue
            agg = (w.config.get("aggregation") or "sum").lower()
            assert agg not in totalling, (
                f"{report.name}/{w.title!r} aggregates a rate "
                f"({sorted(used & rate_columns)}) with {agg!r}"
            )
            seen += 1

    assert seen >= 1, "no demo widget charts a rate column"


async def test_the_change_chart_actually_changes_between_its_frames(db_session, two_orgs):
    """A bubble_change whose frames are identical is a still picture with a play button.

    The frames come from the `animation` role, so this fails both ways it can break:
    animating over a column with no year-on-year movement, and animating over
    something that is not a time dimension at all.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    checked = 0
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            if w.widget_type != "bubble_change":
                continue
            path = by_id[w.config.get("dataset_id") or report.dataset_id].filename
            result = get_widget_data(path, w.config, widget_type=w.widget_type, use_cache=False)
            first, last = result["frames"][0], result["frames"][-1]
            xs_first = {r["name"]: r["x"] for r in result["rows"] if r["frame"] == first}
            xs_last = {r["name"]: r["x"] for r in result["rows"] if r["frame"] == last}
            shared = set(xs_first) & set(xs_last)
            assert shared, "no bubble appears in both the first and the last frame"
            moves = [abs(xs_last[n] - xs_first[n]) / abs(xs_first[n]) for n in shared if xs_first[n]]
            # EVERY bubble, not the biggest mover: two frames drawn from the same
            # distribution still jitter apart by a few percent on 250-odd rows each, so
            # "at least one bubble moved" is satisfied by pure noise (measured: 5.7% on
            # the largest of four regions with the trend removed). Requiring all of them
            # to move by more than 8% is the difference between sampling noise and a real
            # year-on-year trend (measured: 11.3% on the smallest mover, with it).
            assert min(moves) > 0.08, (
                f"bubble movement from {first} to {last} runs as low as {min(moves):.1%} — "
                "the chart animates, but the frames say the same thing"
            )
            checked += 1

    assert checked == 1, f"expected one change chart in the demo, found {checked}"


async def test_a_widget_charting_another_dataset_charts_one_its_report_carries(db_session, two_orgs):
    """A per-widget `dataset_id` the report does not list resolves to nothing in
    ReportBuilder, which builds its dataset map from dataset_id + additional_dataset_ids.
    The widget still fetches, so no error is raised — the tile just never draws."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    seen = 0
    for report in await _loaded_reports(db_session, org_id):
        carried = {report.dataset_id, *(report.additional_dataset_ids or [])}
        for w in _widgets(report):
            override = w.config.get("dataset_id")
            if not override:
                continue
            assert override in carried, (
                f"{report.name}/{w.title!r} charts dataset {override}, which the report "
                f"does not carry ({sorted(c for c in carried if c)})"
            )
            seen += 1

    assert seen >= 1, "no demo widget charts a second dataset"


async def test_the_data_exempt_widgets_carry_the_content_their_renderer_reads(db_session, two_orgs):
    """text/button/shape/image never call the widget-data path, so their content
    config is the only thing standing between them and an empty tile."""
    required_keys = {
        "container": set(),      # a container's content IS its children
        "text": {"content"},
        "button": {"label"},
        "shape": {"shape", "fill", "stroke"},
        "image": {"url", "fit"},
        "web_content": {"url"},   # the embedded page's URL
        "custom_visual": {"url"},  # the visualisation page's URL
    }
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    seen = set()
    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            if w.widget_type not in DATA_EXEMPT:
                continue
            seen.add(w.widget_type)
            for key in required_keys[w.widget_type]:
                assert w.config.get(key), f"{w.widget_type}.config[{key!r}] is empty"

    assert seen == DATA_EXEMPT


async def test_the_image_widget_needs_no_network_to_render(db_session, two_orgs):
    """An <img> pointed at a remote host shows a broken icon on an offline or
    firewalled deployment, which is exactly where a demo is most often opened."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    urls = [
        w.config["url"]
        for report in await _loaded_reports(db_session, org_id)
        for w in _widgets(report)
        if w.widget_type == "image"
    ]
    assert urls
    for url in urls:
        assert url.startswith("data:"), url


# ── Layout ────────────────────────────────────────────────────────────────────

async def test_every_widget_sits_inside_the_grid(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    for report in await _loaded_reports(db_session, org_id):
        for w in _widgets(report):
            layout = w.layout
            assert set(layout) == {"x", "y", "w", "h"}, layout
            assert layout["w"] >= 1 and layout["h"] >= 1, layout
            assert layout["x"] >= 0 and layout["y"] >= 0, layout
            assert layout["x"] + layout["w"] <= GRID_COLUMNS, (report.name, w.widget_type, layout)


async def test_no_two_widgets_on_a_page_overlap(db_session, two_orgs):
    """Overlapping tiles render on top of each other and make the demo look broken."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    for report in await _loaded_reports(db_session, org_id):
        for page in report.pages:
            widgets = page.widgets
            for i, a in enumerate(widgets):
                for b in widgets[i + 1:]:
                    la, lb = a.layout, b.layout
                    overlaps = (
                        la["x"] < lb["x"] + lb["w"] and lb["x"] < la["x"] + la["w"]
                        and la["y"] < lb["y"] + lb["h"] and lb["y"] < la["y"] + la["h"]
                    )
                    assert not overlaps, (
                        f"{report.name}: {a.widget_type}{la} overlaps {b.widget_type}{lb}"
                    )


async def test_the_page_has_no_empty_band_between_rows(db_session, two_orgs):
    """A gap means a row was laid out taller than anything in it — a packer bug that
    leaves a visible hole rather than an overlap, so the overlap test cannot see it."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    for report in await _loaded_reports(db_session, org_id):
        for page in report.pages:
            covered = set()
            for w in page.widgets:
                covered.update(range(w.layout["y"], w.layout["y"] + w.layout["h"]))
            assert covered == set(range(0, max(covered) + 1)), f"{report.name} has an empty band"


# ── Transaction / idempotency / isolation ─────────────────────────────────────

async def test_seed_does_not_commit_so_the_caller_owns_the_transaction(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    await db_session.rollback()

    assert await _loaded_reports(db_session, org_id) == []


async def test_seeding_twice_leaves_one_set_of_reports_not_two(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    await _seed(db_session, org_id)

    reports = await _loaded_reports(db_session, org_id)
    assert [r.name for r in reports] == list(EXPECTED_TYPES)


async def test_reseeding_does_not_leave_orphaned_pages_or_widgets(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    pages_after_one = len((await db_session.execute(select(ReportPage))).scalars().all())
    widgets_after_one = len((await db_session.execute(select(ReportWidget))).scalars().all())
    await _seed(db_session, org_id)

    assert pages_after_one > 0 and widgets_after_one > 0
    assert len((await db_session.execute(select(ReportPage))).scalars().all()) == pages_after_one
    assert len((await db_session.execute(select(ReportWidget))).scalars().all()) == widgets_after_one


async def test_a_users_own_report_survives_a_reseed(db_session, two_orgs):
    """Cleanup must identify demo reports by their marker, never by name — a user is
    entitled to a report called "Demo — Sales Overview" and a re-seed must not eat it.
    An implementation that deletes by name passes every other test in this file.
    """
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    mine = Report(name="Demo — Sales Overview", org_id=org_id, description="mine")
    db_session.add(mine)
    await db_session.flush()
    page = ReportPage(report_id=mine.id, name="Page 1", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add(ReportWidget(
        page_id=page.id, widget_type="bar", title="Mine",
        config={"dimension": "region", "measure": "revenue"},
        layout={"x": 0, "y": 0, "w": 6, "h": 5},
    ))
    await db_session.flush()
    mine_id = mine.id

    await _seed(db_session, org_id)

    survivor = await db_session.get(Report, mine_id)
    assert survivor is not None, "a user's own report was deleted by the re-seed"
    assert survivor.description == "mine"


async def test_demo_reports_are_identified_by_marker_not_by_name(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    reports = await _loaded_reports(db_session, org_id)
    assert reports
    for report in reports:
        assert is_demo_report(report), report.name


async def test_reports_seeded_in_one_org_are_invisible_from_another(db_session, two_orgs):
    await _seed(db_session, two_orgs["a"]["org"].id)

    assert await _loaded_reports(db_session, two_orgs["b"]["org"].id) == []


async def test_seeding_one_org_leaves_another_orgs_demo_reports_alone(db_session, two_orgs):
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id
    await _seed(db_session, org_a)
    _, b_reports = await _seed(db_session, org_b)
    b_ids = {r.id for r in b_reports}

    await _seed(db_session, org_a)

    assert {r.id for r in await _loaded_reports(db_session, org_b)} == b_ids


async def test_the_demo_datasets_the_reports_chart_exist_on_disk(db_session, two_orgs):
    """A report bound to a dataset whose file is missing renders every tile as an
    error, which is indistinguishable from a mis-keyed config in a screenshot."""
    org_id = two_orgs["a"]["org"].id
    datasets, reports = await _seed(db_session, org_id)

    for report in reports:
        ds = next(d for d in datasets.values() if d.id == report.dataset_id)
        assert Path(ds.filename).exists(), report.name
