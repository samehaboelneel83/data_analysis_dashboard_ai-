"""Tests for the demo's feature layer — the app's own features laid over the demo content.

Task 3/4 proved every widget TYPE draws. This file proves the FEATURES do something:
a row-level calculated column, a post-aggregation measure, column formats, all three
kinds of display rule, table chrome, and the interaction artefacts (slicer,
cross-filter, drill hierarchy, bookmark, navigation button).

The load-bearing tests here are the display-rule ones. Display rules fail OPEN by
design (see services/display_rules.py): a rule naming a column the SHAPED result does
not carry is recorded in `rule_errors` and silently stops applying, and the widget
still renders — just unstyled. A broken demo rule therefore looks exactly like a
working one in a screenshot. So every rule is evaluated against a real shaped result
and asserted on BOTH counts:

  * it produced styles, and
  * `rule_errors` came back empty.

Neither alone is sufficient, and the two meta-tests at the bottom of the display-rule
section prove it: a rule pointed at an absent column produces no styles AND an error,
while a rule whose bands miss the data produces no styles AND NO error. Assert only
"no errors" and the second one ships; assert only "styles came back" and you never
learn the first one is being swallowed.

Every widget the feature layer touches is looked up by title and type, never by index
— an earlier task reordering its spec list would otherwise attach a gauge's bands to
whatever now sits in that slot, which is a defect no assertion in this file could see.
"""
import copy

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import Bookmark, HierarchyNode, Report, ReportPage, ReportWidget
from app.services.analytics import load_file
from app.services.demo_content import (
    DEMO_BOOKMARK_NAME,
    DEMO_CALCULATED_COLUMNS,
    DEMO_COLUMN_FORMATS,
    DEMO_DETAIL_PAGE_NAME,
    DEMO_DRILL_FOLDER,
    DEMO_DRILL_LEVELS,
    DEMO_MEASURE_NAME,
    DEMO_MEASURES,
    DEMO_META_KEY,
    DEMO_MARKER,
    DEMO_REPORT_NAMES,
    seed_demo_datasets,
    seed_demo_features,
    seed_demo_reports,
)
from app.services.display_rules import evaluate_rules, result_frame
from app.services.measure_eval import evaluate_measure
from app.services.widget_data import (
    apply_calculated_columns,
    get_widget_data,
    get_widget_data_from_df,
)

SALES_REPORT = DEMO_REPORT_NAMES["sales_overview"]


# ── Fixtures / helpers ────────────────────────────────────────────────────────

async def _seed(db_session, org_id):
    """The whole pipeline, in the order the endpoint (task 7) must call it: the
    feature layer needs both the datasets it decorates and the reports it patches."""
    datasets = await seed_demo_datasets(db_session, org_id)
    reports = await seed_demo_reports(db_session, org_id, datasets)
    await seed_demo_features(db_session, org_id, datasets, reports)
    return datasets, reports


async def _loaded_reports(db_session, org_id) -> list[Report]:
    result = await db_session.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org_id)
        .order_by(Report.id)
    )
    return result.scalars().unique().all()


async def _report(db_session, org_id, name: str) -> Report:
    reports = [r for r in await _loaded_reports(db_session, org_id) if r.name == name]
    assert len(reports) == 1, f"expected exactly one report named {name!r}, got {len(reports)}"
    return reports[0]


def _find_widget(report: Report, *, widget_type: str, title: str | None = None) -> ReportWidget:
    """Look a widget up by what it IS, never by where it sits.

    Positional lookup is the failure this guards: task 3/4 own the spec lists, and an
    insertion there would silently move a feature onto a different widget while every
    assertion in this file still passed."""
    matches = [
        w for page in report.pages for w in page.widgets
        if w.widget_type == widget_type and (title is None or w.title == title)
    ]
    assert len(matches) == 1, (
        f"expected exactly one {widget_type} widget"
        + (f" titled {title!r}" if title else "")
        + f" on {report.name!r}, found {[(w.widget_type, w.title) for w in matches]}"
    )
    return matches[0]


def _page(report: Report, name: str) -> ReportPage:
    pages = [p for p in report.pages if p.name == name]
    assert len(pages) == 1, f"expected one page named {name!r}, got {[p.name for p in report.pages]}"
    return pages[0]


def _query(dataset, widget: ReportWidget, config: dict | None = None) -> dict:
    """Run a widget through the widget-data path with EXACTLY the arguments the HTTP
    endpoint passes (routers/widget_data.py): the dataset's calculated columns and its
    measures. Omitting either is how a measure-backed widget silently degrades to a
    row-count series that still passes a shape check."""
    return get_widget_data(
        dataset.filename,
        config if config is not None else widget.config,
        widget_type=widget.widget_type,
        calculated_columns=dataset.calculated_columns or None,
        measures=dataset.measures or None,
        use_cache=False,
    )


def _styled_rows(styles: dict) -> int:
    return sum(1 for s in styles["rows"] if s)


def _styled_cells(styles: dict) -> int:
    return sum(len(cols) for cols in styles["cells"].values())


def _any_style(result: dict) -> int:
    styles = result.get("rule_styles") or {"rows": [], "cells": {}, "widget": {}}
    return _styled_rows(styles) + _styled_cells(styles) + len(styles["widget"])


def test_looking_a_widget_up_by_title_does_not_depend_on_the_order_they_were_created():
    """The seeder's own lookup, tested where the defect is actually visible.

    Every other test in this file finds the right widget even if the seeder picked the
    first of its type, because the sales report happens to create "Revenue by region"
    before the detail page's two bars. That is luck, and the brief's warning: an
    insertion into task 3's spec list would silently move the display rule onto another
    bar with nothing to show for it. Here the order is reversed on purpose.
    """
    from app.services.demo_content import _one_widget

    bars = [
        ReportWidget(page_id=1, widget_type="bar", title="Profit by region", config={}),
        ReportWidget(page_id=1, widget_type="bar", title="Revenue by region", config={}),
    ]

    assert _one_widget(bars, "bar", "Revenue by region").title == "Revenue by region"
    # And an ambiguous lookup has to raise, not pick one: silently patching the wrong
    # widget is the failure mode no assertion downstream can see.
    with pytest.raises(ValueError):
        _one_widget(bars, "bar")
    with pytest.raises(ValueError):
        _one_widget(bars, "bar", "No such widget")


# ── The calculated column: row-level, before aggregation ──────────────────────

async def test_the_sales_dataset_carries_a_row_level_calculated_column(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)

    calc = datasets["sales"].calculated_columns
    assert calc == DEMO_CALCULATED_COLUMNS
    names = {c["name"] for c in calc}
    assert "profit" in names
    assert {c["name"] for c in calc}.isdisjoint(load_file(datasets["sales"].filename).columns)


async def test_the_calculated_column_agrees_with_the_margin_the_frame_already_derives(db_session, two_orgs):
    """profit = revenue - cost, and the sales frame derives margin_pct from those same
    two columns. Recomputing margin from profit must land back on margin_pct — if it
    does not, the calculated column is not measuring what its name claims."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)

    df = load_file(datasets["sales"].filename)
    df = apply_calculated_columns(df, datasets["sales"].calculated_columns)

    assert "profit" in df.columns, "the calculated column did not evaluate"
    earning = df[df["revenue"] != 0]
    recomputed = earning["profit"] / earning["revenue"] * 100
    # margin_pct is stored rounded to 2dp, so exact equality is not available; a
    # tolerance this tight still fails for any other pair of columns.
    assert (recomputed - earning["margin_pct"]).abs().max() < 0.01


async def test_a_widget_charts_the_calculated_column(db_session, two_orgs):
    """A calculated column nothing charts is invisible: the demo has to show it."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    widget = _find_widget(report, widget_type="bar", title="Profit by region")
    assert widget.config["measure"] == "profit"

    result = _query(datasets["sales"], widget)
    assert result["type"] == "series", result
    assert len(result["rows"]) == 4, result["rows"]
    assert all(r["value"] is not None for r in result["rows"])

    # The row-level engine, not the measure engine: profit summed per region must equal
    # the sum of (revenue - cost) over that region's rows.
    df = apply_calculated_columns(load_file(datasets["sales"].filename), datasets["sales"].calculated_columns)
    expected = df.groupby("region")["profit"].sum()
    for row in result["rows"]:
        assert row["value"] == pytest.approx(expected[row["name"]], rel=1e-9)


# ── The measure: post-aggregation, at the widget's grain ──────────────────────

async def test_the_sales_dataset_carries_a_post_aggregation_measure(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    sales = datasets["sales"]

    assert sales.measures == DEMO_MEASURES
    names = {m["name"] for m in sales.measures}
    assert DEMO_MEASURE_NAME in names
    # The measures API refuses a name that collides with a real column or a calculated
    # column (routers/datasets.py), because shape_series resolves a real column FIRST
    # and the measure would never run. A seeded measure has to obey the same rule.
    columns = set(load_file(sales.filename).columns) | {c["name"] for c in sales.calculated_columns}
    assert names.isdisjoint(columns), f"measure name collides with a column: {names & columns}"


async def test_the_measure_is_evaluated_on_group_totals_not_averaged_per_row(db_session, two_orgs):
    """The whole reason the two engines are not interchangeable.

    A row-level margin averaged per region is the mean of 500 ratios; the measure is
    one ratio of two group totals. Refunds (negative revenue against a positive cost)
    pull those far apart, so the demo shows a number a calculated column cannot
    produce — and a measure secretly defined as AVG(margin_pct) fails here.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    widget = _find_widget(report, widget_type="bar", title="Margin % by region")
    assert widget.config["measure"] == DEMO_MEASURE_NAME

    result = _query(datasets["sales"], widget)
    assert result["type"] == "series", result
    served = {r["name"]: r["value"] for r in result["rows"]}
    assert len(served) == 4, served

    df = load_file(datasets["sales"].filename)
    grouped = df.groupby("region")
    on_totals = (grouped["revenue"].sum() - grouped["cost"].sum()) / grouped["revenue"].sum() * 100
    per_row = grouped["margin_pct"].mean()

    for region, value in served.items():
        assert value == pytest.approx(on_totals[region], rel=1e-9), region
        # Not a rounding difference — a different statistic entirely.
        assert abs(value - per_row[region]) > 5.0, (
            f"{region}: margin on totals ({value}) is indistinguishable from the mean of "
            f"row-level margins ({per_row[region]}) — the demo no longer shows why the "
            f"two engines differ"
        )


async def test_the_measure_recomputes_at_whatever_grain_the_widget_groups_by(db_session, two_orgs):
    """A calculated column is fixed at definition time; a measure is not. Grouping the
    same measure by country must give country-level ratios, not the region's value
    copied down — that is the property `TOTAL()`/group-aware SUM exists for."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)

    df = load_file(datasets["sales"].filename)
    expression = next(m["expression"] for m in datasets["sales"].measures if m["name"] == DEMO_MEASURE_NAME)

    by_region = evaluate_measure(expression, df, ["region"])
    by_country = evaluate_measure(expression, df, ["country"])

    assert len(by_region) == 4 and len(by_country) == 14
    # Every country carries its own number rather than inheriting its region's.
    region_of = df.drop_duplicates("country").set_index("country")["region"].to_dict()
    inherited = sum(
        1 for country, value in by_country.items()
        if value == pytest.approx(by_region[region_of[country]], rel=1e-9)
    )
    assert inherited == 0, f"{inherited} countries just repeat their region's value"


# ── Column formats ────────────────────────────────────────────────────────────

async def test_revenue_is_formatted_as_currency_and_margin_as_a_percent(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)

    formats = datasets["sales"].column_formats
    assert formats == DEMO_COLUMN_FORMATS
    assert formats["revenue"]["type"] == "currency"
    assert formats["revenue"].get("symbol")
    assert formats["margin_pct"]["type"] == "percent"


async def test_every_formatted_column_is_one_a_demo_widget_actually_displays(db_session, two_orgs):
    """WidgetRenderer looks a format up by the widget's measure/dimension name, and a
    table looks one up per column. A format on a column no widget shows is a row in the
    database that changes nothing on screen."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)

    roles = (
        "measure", "measure2", "dimension", "dimension2", "size", "color",
        "group", "animation", "start", "end", "target", "direction",
    )
    displayed: set[str] = set()
    for report in await _loaded_reports(db_session, org_id):
        for page in report.pages:
            for w in page.widgets:
                for key in roles:
                    if w.config.get(key):
                        displayed.add(w.config[key])
                displayed.update(w.config.get("columns") or [])
                displayed.update(w.config.get("measures") or [])

    formatted = set(datasets["sales"].column_formats)
    unread = formatted - displayed
    assert not unread, f"formatted but never displayed: {sorted(unread)}"
    # And a format keyed on something that is not a column at all is dead weight the
    # renderer will never look up.
    unknown = formatted - set(load_file(datasets["sales"].filename).columns)
    assert not unknown, f"formatted but not a column of the dataset: {sorted(unknown)}"


# ── Display rules ─────────────────────────────────────────────────────────────
# Each rule is evaluated against a REAL shaped result, and asserted on both counts:
# styles produced AND rule_errors empty. See the module docstring.

async def test_the_gauge_carries_an_interval_rule_that_paints_it(db_session, two_orgs):
    """The gauge's shaped result has `value` and `target` — not the source dataframe's
    columns. A bands rule pointed at `revenue` here would land in rule_errors and the
    gauge would render in its default colour, looking entirely fine."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    gauge = _find_widget(report, widget_type="gauge")
    rules = gauge.config["display_rules"]
    assert [r["kind"] for r in rules] == ["interval"], rules
    assert rules[0]["column"] in ("value", "target")

    result = _query(datasets["sales"], gauge)
    assert result["type"] == "gauge"
    assert result["rule_errors"] == [], result["rule_errors"]
    # GaugeRenderer reads ruleStyles.rows[0].fill — the only row a gauge has.
    assert result["rule_styles"]["rows"][0], "the bands produced no fill for the gauge"
    assert result["rule_styles"]["rows"][0].get("fill")


async def test_the_gauge_bands_bracket_the_value_the_gauge_actually_shows(db_session, two_orgs):
    """Bands hardcoded against yesterday's data stop matching the moment the frame
    changes — which already happened once, when task 4 added 18% year-on-year growth."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    gauge = _find_widget(report, widget_type="gauge")
    result = _query(datasets["sales"], gauge)
    bands = gauge.config["display_rules"][0]["bands"]

    assert len(bands) >= 3, bands
    assert bands[0]["min"] <= result["value"] < bands[-1]["max"], (
        f"gauge value {result['value']} falls outside its bands "
        f"[{bands[0]['min']}, {bands[-1]['max']})"
    )
    # End to end, no gaps: a hole between two bands leaves values in it unstyled.
    for lower, upper in zip(bands, bands[1:]):
        assert lower["max"] == upper["min"], bands
    assert all(b.get("color") for b in bands)


async def test_the_table_carries_a_value_map_that_paints_real_cells(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    table = _find_widget(report, widget_type="table")
    rules = [r for r in table.config["display_rules"] if r["kind"] == "value_map"]
    assert len(rules) == 1, table.config["display_rules"]
    rule = rules[0]

    result = _query(datasets["sales"], table)
    assert result["type"] == "table"
    # The column a value_map READS must exist in the SHAPED result, which for a raw
    # table is its configured column list — not the dataset's full set of columns.
    assert rule["column"] in result["columns"], (rule["column"], result["columns"])
    assert result["rule_errors"] == [], result["rule_errors"]

    cells = result["rule_styles"]["cells"]
    assert cells, "the colour map painted no cells"
    painted_columns = {col for row in cells.values() for col in row}
    assert painted_columns == {rule["column"]}, painted_columns
    # Every mapping in the rule names a value that is really in the column, so no
    # mapping is dead weight.
    values_shown = {row[result["columns"].index(rule["column"])] for row in result["rows"]}
    assert {m["value"] for m in rule["mappings"]} >= values_shown, (
        "a value on screen has no mapping"
    )
    assert all(m.get("color") for m in rule["mappings"])


async def test_an_expression_rule_highlights_some_marks_and_leaves_others(db_session, two_orgs):
    """A rule that paints every mark is as uninformative as one that paints none, and
    both come back with an empty rule_errors."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    bar = _find_widget(report, widget_type="bar", title="Revenue by region")
    rules = bar.config["display_rules"]
    assert [r["kind"] for r in rules] == ["expression"], rules

    result = _query(datasets["sales"], bar)
    assert result["rule_errors"] == [], result["rule_errors"]

    painted = _styled_rows(result["rule_styles"])
    assert 0 < painted < len(result["rows"]), (
        f"{painted} of {len(result['rows'])} marks painted — the rule is not discriminating"
    )


async def test_the_demo_authors_one_rule_of_every_kind_the_engine_supports(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)

    kinds = [
        rule.get("kind")
        for report in await _loaded_reports(db_session, org_id)
        for page in report.pages
        for w in page.widgets
        for rule in (w.config.get("display_rules") or [])
    ]
    assert set(kinds) == {"expression", "value_map", "interval"}, kinds


async def test_every_demo_rule_produces_styles_and_no_rule_errors(db_session, two_orgs):
    """The sweep, so a rule added later cannot ship broken.

    Both halves are required. A rule naming a missing column errors and produces no
    styles; a rule whose condition matches nothing produces no styles and NO error.
    The two meta-tests below prove each half bites.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    seen = 0
    for report in await _loaded_reports(db_session, org_id):
        for page in report.pages:
            for w in page.widgets:
                if not w.config.get("display_rules"):
                    continue
                dataset = by_id[w.config.get("dataset_id") or report.dataset_id]
                result = _query(dataset, w)
                assert result.get("rule_errors") == [], (
                    f"{report.name}/{w.title!r}: {result.get('rule_errors')}"
                )
                assert _any_style(result) > 0, (
                    f"{report.name}/{w.title!r}: rules evaluated without error but "
                    f"styled nothing — they are not reaching the data"
                )
                seen += 1

    assert seen >= 3, "fewer than three widgets in the demo carry display rules"


async def test_a_rule_naming_a_column_the_shaped_result_lacks_errors_and_stops_applying(db_session, two_orgs):
    """Meta-test: proves the `rule_errors == []` half of the assertion above bites.

    `revenue` is a real column of the sales dataset and NOT a column of a gauge's
    shaped result, which is exactly the mistake this whole file exists to catch.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)
    gauge = _find_widget(report, widget_type="gauge")

    broken = copy.deepcopy(gauge.config)
    broken["display_rules"][0]["column"] = "revenue"
    result = _query(datasets["sales"], gauge, config=broken)

    assert result["type"] == "gauge", "a broken rule must never break the widget"
    assert result["rule_errors"], "the mis-pointed rule was not recorded"
    assert _any_style(result) == 0


async def test_a_rule_that_matches_nothing_errors_at_all_and_styles_nothing(db_session, two_orgs):
    """Meta-test: proves the "produced styles" half bites.

    Bands above every possible value are perfectly valid — they simply never match. No
    error is raised, so a suite that only checked rule_errors would pass this.
    """
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)
    gauge = _find_widget(report, widget_type="gauge")

    missing = copy.deepcopy(gauge.config)
    for band in missing["display_rules"][0]["bands"]:
        band["min"] += 1e12
        band["max"] += 1e12
    result = _query(datasets["sales"], gauge, config=missing)

    assert result["rule_errors"] == []
    assert _any_style(result) == 0


# ── Table chrome ──────────────────────────────────────────────────────────────

async def test_the_demo_table_turns_on_totals_banding_and_row_lines(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    table = _find_widget(report, widget_type="table")
    assert table.config["show_totals"] is True
    assert table.config["table_banding"] is True
    assert table.config["table_row_lines"] is True

    result = _query(datasets["sales"], table)
    # show_totals is the only one of the three the backend acts on; the other two are
    # read by WidgetRenderer off the same config. A missing `totals` key means the
    # switch is set on a widget whose shaper never reads it.
    assert isinstance(result.get("totals"), list), sorted(result)
    assert len(result["totals"]) == len(result["columns"])


async def test_the_table_totals_no_column_whose_total_would_be_meaningless(db_session, two_orgs):
    """The raw-table branch totals EVERY numeric column it is given — there is no
    per-column opt-out — so a rate in the column list produces a convincing, meaningless
    number in the footer."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    table = _find_widget(report, widget_type="table")
    result = _query(datasets["sales"], table)

    rates = {"margin_pct", "progress_pct"}
    totalled = {c for c, t in zip(result["columns"], result["totals"]) if t is not None}
    assert not (totalled & rates), f"the table totals a rate: {sorted(totalled & rates)}"
    assert totalled, "show_totals is on but nothing was totalled"


async def test_the_table_shows_the_calculated_column(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    table = _find_widget(report, widget_type="table")
    result = _query(datasets["sales"], table)

    assert "profit" in result["columns"], result["columns"]
    # Configured is served: shape_series silently drops a column the frame lacks, so a
    # calculated column that failed to evaluate would just be absent, not an error.
    assert result["columns"] == table.config["columns"]


# ── Interactions ──────────────────────────────────────────────────────────────

async def test_the_sales_page_carries_a_slicer_over_a_real_column(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    slicer = _find_widget(report, widget_type="slicer")
    result = _query(datasets["sales"], slicer)

    assert result["type"] == "series", result
    names = {r["name"] for r in result["rows"]}
    assert names == set(load_file(datasets["sales"].filename)[slicer.config["dimension"]].unique())


async def test_a_click_on_the_slicer_cross_filters_another_widget_on_the_page(db_session, two_orgs):
    """Cross-filtering is not persisted anywhere: CrossFilterContext holds it in the
    client and every widget broadcasts/receives by default. What the seeder CAN get
    wrong is pairing widgets that cannot filter each other — a slicer over a column the
    target's dataset does not carry emits a filter that matches nothing, and the target
    renders empty. So this replays what WidgetRenderer does with an emitted filter."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    slicer = _find_widget(report, widget_type="slicer")
    target = _find_widget(report, widget_type="line", title="Monthly revenue")
    assert slicer.page_id == target.page_id, "the pair is not on the same page"

    unfiltered = _query(datasets["sales"], target)
    emitted = _query(datasets["sales"], slicer)["rows"][0]["name"]

    # WidgetRenderer.mergedConfig: incoming filters are appended to the widget's own.
    crossed = {**target.config, "filters": [
        *(target.config.get("filters") or []),
        {"column": slicer.config["dimension"], "op": "eq", "value": emitted},
    ]}
    filtered = _query(datasets["sales"], target, config=crossed)

    assert filtered["rows"], f"cross-filtering on {emitted!r} emptied the target widget"
    assert filtered["total"] < unfiltered["total"], "the cross-filter narrowed nothing"


async def test_the_sales_dataset_carries_a_linear_drill_hierarchy(db_session, two_orgs):
    """getChildNode (frontend/src/lib/hierarchyUtils.ts) takes the FIRST node whose
    parent is the current one, so a drill chain has to be linear: one child per level.
    A second child anywhere makes the drill path depend on row order."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)

    nodes = (await db_session.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == datasets["sales"].id)
        .order_by(HierarchyNode.position)
    )).scalars().all()
    assert nodes, "no hierarchy was seeded"

    levels = [n for n in nodes if n.node_type != "folder"]
    assert [(n.name, n.column_name) for n in levels] == list(DEMO_DRILL_LEVELS)

    for parent, child in zip(levels, levels[1:]):
        assert child.parent_id == parent.id
        siblings = [n for n in nodes if n.parent_id == parent.id]
        assert len(siblings) == 1, f"{parent.name} has {len(siblings)} children — the drill is ambiguous"

    folders = [n for n in nodes if n.node_type == "folder"]
    assert [f.name for f in folders] == [DEMO_DRILL_FOLDER]
    assert levels[0].parent_id == folders[0].id

    df = load_file(datasets["sales"].filename)
    columns = [n.column_name for n in levels]
    assert all(df[c].nunique() > 1 for c in columns), columns

    # Each level has to REFINE the one above it, or "drilling" just swaps one chart for
    # another. Comparing the level's own cardinality is not enough — any other
    # categorical column passes that. Two properties that a wrong column does not have:
    #   * region -> country genuinely nests: every country sits in exactly one region.
    assert (df.groupby(columns[1])[columns[0]].nunique() == 1).all(), (
        f"{columns[1]} does not nest inside {columns[0]}"
    )
    #   * every level adds information: the distinct combinations down to it grow.
    combos = [len(df[columns[:i + 1]].drop_duplicates()) for i in range(len(columns))]
    assert combos == sorted(combos) and len(set(combos)) == len(combos), combos


async def test_a_widget_drills_that_hierarchy_and_every_level_shapes(db_session, two_orgs):
    """WidgetRenderer overwrites cfg.dimension with the current node's column at each
    depth. A level naming a column the dataset lacks would leave the shaper with no
    dimension at all — which returns a RAW TABLE, not an error."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    widget = _find_widget(report, widget_type="bar", title="Margin % by region")
    node_id = widget.config["hierarchyNodeId"]

    root = await db_session.get(HierarchyNode, node_id)
    assert root is not None and root.dataset_id == datasets["sales"].id
    assert (root.name, root.column_name) == DEMO_DRILL_LEVELS[0]

    df = load_file(datasets["sales"].filename)
    for _, column in DEMO_DRILL_LEVELS:
        drilled = {**widget.config, "dimension": column}
        result = _query(datasets["sales"], widget, config=drilled)
        assert result["type"] == "series", (column, result)
        assert result["dimension"] == column
        assert len(result["rows"]) == min(df[column].nunique(), int(widget.config.get("limit") or 50))


async def test_the_report_carries_a_bookmark_that_replays_a_real_filter(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    bookmarks = (await db_session.execute(
        select(Bookmark).where(Bookmark.report_id == report.id)
    )).scalars().all()
    assert [b.name for b in bookmarks] == [DEMO_BOOKMARK_NAME]
    state = bookmarks[0].state

    # ReportBuilder.applyBookmark reads exactly these keys; a missing one is a
    # TypeError in the browser, not a styling problem.
    assert set(state) == {"pageId", "activeFilters", "promptValues", "hiddenWidgetIds"}
    page_ids = {p.id for p in report.pages}
    widget_ids = {w.id for p in report.pages for w in p.widgets}
    assert state["pageId"] in page_ids
    assert state["activeFilters"], "the bookmark captures no filter — it restores nothing"

    for f in state["activeFilters"]:
        assert set(f) == {"column", "value", "label", "sourceWidgetId", "sourcePageId"}
        assert f["sourceWidgetId"] in widget_ids, "the bookmark points at a widget that does not exist"
        assert f["sourcePageId"] in page_ids
        assert f["label"]

        target = _find_widget(report, widget_type="line", title="Monthly revenue")
        replayed = {**target.config, "filters": [{"column": f["column"], "op": "eq", "value": f["value"]}]}
        result = _query(datasets["sales"], target, config=replayed)
        assert result["rows"], f"the bookmarked filter {f['label']!r} empties the page"
        assert result["total"] < _query(datasets["sales"], target)["total"]


async def test_the_button_navigates_to_another_page_of_its_own_report(db_session, two_orgs):
    """WidgetRenderer.handleButtonClick needs BOTH keys; `action` alone is a button
    that does nothing when clicked, which looks identical to one that is not wired."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    button = _find_widget(report, widget_type="button")
    assert button.config["action"] == "navigate"

    target_id = button.config["actionPageId"]
    own_page = next(p for p in report.pages if any(w.id == button.id for w in p.widgets))
    assert target_id in {p.id for p in report.pages}, "the button navigates outside its own report"
    assert target_id != own_page.id, "the button navigates to the page it is already on"


async def test_the_detail_page_exists_and_holds_the_two_engines_side_by_side(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    assert [p.position for p in sorted(report.pages, key=lambda p: p.position)] == list(range(len(report.pages)))
    page = _page(report, DEMO_DETAIL_PAGE_NAME)
    titles = {w.title for w in page.widgets}
    assert {"Profit by region", "Margin % by region"} <= titles, titles

    # Same layout invariants task 3 holds the first page to: inside the grid, no
    # overlaps, no empty band.
    covered = set()
    for w in page.widgets:
        assert set(w.layout) == {"x", "y", "w", "h"}
        assert 0 <= w.layout["x"] and w.layout["x"] + w.layout["w"] <= 12, w.layout
        covered.update(range(w.layout["y"], w.layout["y"] + w.layout["h"]))
    assert covered == set(range(max(covered) + 1))
    for i, a in enumerate(page.widgets):
        for b in page.widgets[i + 1:]:
            la, lb = a.layout, b.layout
            assert not (
                la["x"] < lb["x"] + lb["w"] and lb["x"] < la["x"] + la["w"]
                and la["y"] < lb["y"] + lb["h"] and lb["y"] < la["y"] + la["h"]
            ), (a.title, b.title)


async def test_the_patched_configs_are_really_written_not_just_held_in_the_session(db_session, two_orgs):
    """Column(JSON) has no mutation tracking.

    Editing `widget.config` in place leaves the instance clean, so the flush writes
    nothing — and every assertion in this file would still pass, because they read the
    same in-memory object out of the session's identity map. Expiring first is what
    forces the values to come back from the database.
    """
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)
    db_session.expire_all()

    report = await _report(db_session, org_id, SALES_REPORT)
    assert _find_widget(report, widget_type="gauge").config.get("display_rules")
    assert _find_widget(report, widget_type="button").config.get("actionPageId")
    table = _find_widget(report, widget_type="table")
    assert table.config.get("show_totals") is True
    assert "profit" in table.config["columns"]


async def test_the_dataset_feature_columns_are_really_written(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    dataset_id = datasets["sales"].id
    db_session.expire_all()

    from app.models.models import Dataset

    sales = await db_session.get(Dataset, dataset_id)
    assert sales.calculated_columns == DEMO_CALCULATED_COLUMNS
    assert sales.measures == DEMO_MEASURES
    assert sales.column_formats == DEMO_COLUMN_FORMATS


async def test_every_widget_the_feature_layer_adds_carries_the_demo_marker(db_session, two_orgs):
    """Cleanup identifies demo reports by the marker on their widgets, never by name."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)

    for w in _page(report, DEMO_DETAIL_PAGE_NAME).widgets:
        assert (w.config or {}).get(DEMO_META_KEY) == DEMO_MARKER, w.title


async def test_no_widget_still_draws_a_blank_once_the_feature_layer_is_applied(db_session, two_orgs):
    """Task 3/4 validate every widget against a seed with no feature layer. Patching
    configs afterwards can break one — a measure name that resolves to nothing falls
    through to a row-count series that passes every shape check."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    by_id = {ds.id: ds for ds in datasets.values()}

    for report in await _loaded_reports(db_session, org_id):
        for page in report.pages:
            for w in page.widgets:
                if w.widget_type in {"text", "button", "shape", "image"}:
                    continue
                dataset = by_id[w.config.get("dataset_id") or report.dataset_id]
                result = _query(dataset, w)
                assert result.get("type") != "error", (report.name, w.title, result)
                assert result.get("type") != "empty", (report.name, w.title, result)


# ── Transaction / idempotency / org isolation ─────────────────────────────────

async def test_the_feature_layer_does_not_commit(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    await db_session.rollback()

    assert (await db_session.execute(select(Bookmark))).scalars().all() == []
    assert (await db_session.execute(select(HierarchyNode))).scalars().all() == []


async def test_seeding_twice_leaves_one_hierarchy_one_bookmark_and_one_detail_page(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    await _seed(db_session, org_id)

    report = await _report(db_session, org_id, SALES_REPORT)
    assert len([p for p in report.pages if p.name == DEMO_DETAIL_PAGE_NAME]) == 1
    assert len((await db_session.execute(select(Bookmark))).scalars().all()) == 1
    nodes = (await db_session.execute(select(HierarchyNode))).scalars().all()
    assert len(nodes) == len(DEMO_DRILL_LEVELS) + 1  # + the folder


async def test_the_feature_layer_lands_only_in_the_callers_org(db_session, two_orgs):
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id

    datasets_a, _ = await _seed(db_session, org_a)

    assert (await db_session.execute(
        select(Bookmark).join(Report).where(Report.org_id == org_b)
    )).scalars().all() == []
    nodes = (await db_session.execute(select(HierarchyNode))).scalars().all()
    assert {n.dataset_id for n in nodes} == {datasets_a["sales"].id}


async def test_the_feature_layer_refuses_content_belonging_to_another_org(db_session, two_orgs):
    """Nothing the feature layer creates carries an org of its own — a HierarchyNode
    hangs off a Dataset and a Bookmark off a Report. So handing it another org's
    datasets would silently hang org A's drill hierarchy off org B's data, and every
    org-isolation test would still pass because the rows themselves look fine."""
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id

    datasets = await seed_demo_datasets(db_session, org_a)
    reports = await seed_demo_reports(db_session, org_a, datasets)

    with pytest.raises(ValueError, match="another org"):
        await seed_demo_features(db_session, org_b, datasets, reports)


async def test_seeding_one_org_leaves_another_orgs_feature_layer_alone(db_session, two_orgs):
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id
    await _seed(db_session, org_a)
    datasets_b, _ = await _seed(db_session, org_b)
    b_nodes = {
        n.id for n in (await db_session.execute(
            select(HierarchyNode).where(HierarchyNode.dataset_id == datasets_b["sales"].id)
        )).scalars().all()
    }
    b_bookmarks = {
        b.id for b in (await db_session.execute(
            select(Bookmark).join(Report).where(Report.org_id == org_b)
        )).scalars().all()
    }
    assert b_nodes and b_bookmarks

    await _seed(db_session, org_a)

    assert {
        n.id for n in (await db_session.execute(
            select(HierarchyNode).where(HierarchyNode.dataset_id == datasets_b["sales"].id)
        )).scalars().all()
    } == b_nodes
    assert {
        b.id for b in (await db_session.execute(
            select(Bookmark).join(Report).where(Report.org_id == org_b)
        )).scalars().all()
    } == b_bookmarks


async def test_the_feature_layer_survives_the_real_widget_data_endpoint(db_session, two_orgs, client, auth_headers):
    """End to end through the HTTP endpoint the browser calls, which is the only place
    that decides for itself to pass the dataset's calculated columns and measures.
    A feature the service layer resolves but the endpoint does not is still broken."""
    org_id = two_orgs["a"]["org"].id
    datasets, _ = await _seed(db_session, org_id)
    report = await _report(db_session, org_id, SALES_REPORT)
    gauge = _find_widget(report, widget_type="gauge")
    measure_bar = _find_widget(report, widget_type="bar", title="Margin % by region")

    resp = await client.post(
        f"/api/v1/datasets/{datasets['sales'].id}/widget-data",
        json={"config": gauge.config, "widget_type": "gauge"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rule_errors"] == []
    assert body["rule_styles"]["rows"][0]

    resp = await client.post(
        f"/api/v1/datasets/{datasets['sales'].id}/widget-data",
        json={"config": measure_bar.config, "widget_type": "bar"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert len(rows) == 4
    # Percentages, not the row counts a measure that failed to resolve would produce.
    assert all(0 < r["value"] < 100 for r in rows), rows
