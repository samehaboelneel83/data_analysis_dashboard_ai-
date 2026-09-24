"""Tests for the UX Showcase demo report — the second seeded report that tours every
interactive facility the platform has: button actions, all five page types, a
hierarchical drill-down, cross-filter interaction modes, a page prompt and bookmarks.

Task D1 proves the report and its six pages exist with the right `page_type`s and that
the wiring between them (button actions, hierarchy binding) points at real ids in the
same report. Task D2 (`TestShowcaseInteractiveOptions`) extends this with the
interaction-mode contrast, the prompt page and the two bookmarks.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import Bookmark, HierarchyNode, Report, ReportPage, ReportWidget
from app.services.demo_content import (
    DEMO_META_KEY,
    DEMO_MARKER,
    DEMO_SHOWCASE_BOOKMARK_TOP_REGION,
    DEMO_SHOWCASE_BOOKMARK_WEAK_COUNTRY,
    UX_SHOWCASE_REPORT_NAME,
    is_demo_report,
    remove_demo_content,
    seed_demo_datasets,
    seed_demo_features,
    seed_demo_reports,
    seed_demo_ux_showcase,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

async def _seed(db_session, org_id) -> Report:
    """The whole pipeline in the order the endpoint must call it: the showcase needs
    the drill hierarchy, which the feature pass creates."""
    datasets = await seed_demo_datasets(db_session, org_id)
    reports = await seed_demo_reports(db_session, org_id, datasets)
    await seed_demo_features(db_session, org_id, datasets, reports)
    return await seed_demo_ux_showcase(db_session, org_id, datasets)


async def _loaded_report(db_session, org_id, name: str) -> Report:
    result = await db_session.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org_id, Report.name == name)
    )
    reports = result.scalars().unique().all()
    assert len(reports) == 1, f"expected exactly one report named {name!r}, got {len(reports)}"
    return reports[0]


def _page(report: Report, name: str) -> ReportPage:
    pages = [p for p in report.pages if p.name == name]
    assert len(pages) == 1, f"expected one page named {name!r}, got {[p.name for p in report.pages]}"
    return pages[0]


def _widgets(report: Report) -> list[ReportWidget]:
    return [w for page in report.pages for w in page.widgets]


def _widget(report: Report, *, widget_type: str, title: str | None = None) -> ReportWidget:
    matches = [
        w for w in _widgets(report)
        if w.widget_type == widget_type and (title is None or w.title == title)
    ]
    assert len(matches) == 1, (
        f"expected exactly one {widget_type} widget"
        + (f" titled {title!r}" if title else "")
        + f", found {[(w.widget_type, w.title) for w in matches]}"
    )
    return matches[0]


def _buttons(report: Report) -> list[ReportWidget]:
    return [w for w in _widgets(report) if w.widget_type == "button"]


class TestShowcaseSeeds:
    @pytest.mark.asyncio
    async def test_the_report_exists_with_exactly_six_page_types(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        report = await _seed(db_session, org_id)
        assert report.name == UX_SHOWCASE_REPORT_NAME

        loaded = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        page_types = sorted(p.page_type for p in loaded.pages)
        # Three "normal" pages: Start here, Drill-down, and (task D2) the prompt page.
        assert page_types == sorted(
            ["normal", "normal", "normal", "popup", "tooltip", "drillthrough", "hidden"]
        )

    @pytest.mark.asyncio
    async def test_every_widget_carries_the_demo_marker(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        widgets = _widgets(report)
        assert widgets, "the showcase report has no widgets"
        assert all((w.config or {}).get(DEMO_META_KEY) == DEMO_MARKER for w in widgets)
        assert is_demo_report(report)

    @pytest.mark.asyncio
    async def test_the_three_buttons_carry_real_actions(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        page_ids = {p.id for p in report.pages}

        buttons = _buttons(report)
        assert len(buttons) == 3

        navigate = [b for b in buttons if b.config.get("action") == "navigate"]
        url = [b for b in buttons if b.config.get("action") == "url"]
        assert len(navigate) == 2
        assert len(url) == 1

        for b in navigate:
            assert b.config.get("actionPageId") in page_ids

        assert url[0].config.get("actionUrl")

        drilldown_page = _page(report, "Drill-down")
        popup_page = _page(report, "Popup KPIs")
        navigate_targets = {b.config["actionPageId"] for b in navigate}
        assert navigate_targets == {drilldown_page.id, popup_page.id}

    @pytest.mark.asyncio
    async def test_the_drilldown_charts_bind_to_a_real_hierarchy_root(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        drilldown_page = _page(report, "Drill-down")
        bars = [w for w in drilldown_page.widgets if w.widget_type in ("bar", "line", "column")]
        assert len(bars) == 2

        node_ids = {w.config.get("hierarchyNodeId") for w in bars}
        assert None not in node_ids
        assert len(node_ids) == 2, "the two charts must start at different hierarchy levels"

        nodes = (await db_session.execute(
            select(HierarchyNode).where(HierarchyNode.id.in_(node_ids))
        )).scalars().all()
        assert len(nodes) == 2
        assert {n.node_type for n in nodes} == {"dimension"}

        dims = {w.config.get("dimension") for w in bars}
        assert len(dims) == 2, "the two charts must chart different levels' columns"

    @pytest.mark.asyncio
    async def test_the_tooltip_page_is_bound_to_the_drilldown_main_chart(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        tooltip_page = _page(report, "Hover detail")
        assert tooltip_page.page_type == "tooltip"

        drilldown_page = _page(report, "Drill-down")
        bound = [
            w for w in drilldown_page.widgets
            if w.config.get("tooltipPageId") == tooltip_page.id
        ]
        assert bound, "no Drill-down widget references the tooltip page"

        assert tooltip_page.widgets, "the tooltip page itself has no content"

    @pytest.mark.asyncio
    async def test_the_drillthrough_page_is_reached_from_the_drilldown_charts(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        detail_page = _page(report, "Transaction detail")
        assert detail_page.page_type == "drillthrough"

        drilldown_page = _page(report, "Drill-down")
        bound = [
            w for w in drilldown_page.widgets
            if w.config.get("drillthroughPageId") == detail_page.id
        ]
        assert bound, "no Drill-down widget references the drillthrough page"
        assert detail_page.widgets, "the drillthrough page itself has no content"

    @pytest.mark.asyncio
    async def test_the_hidden_page_carries_a_text_widget(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        hidden_page = _page(report, "Hidden notes")
        assert hidden_page.page_type == "hidden"
        assert any(w.widget_type == "text" for w in hidden_page.widgets)

    @pytest.mark.asyncio
    async def test_reseeding_is_idempotent(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)

        # Re-run the whole pipeline, as the endpoint would on a second "Load demo".
        # (SQLite may reuse the deleted row's rowid for the rebuilt report, so id
        # equality proves nothing here -- only the count does.)
        await _seed(db_session, org_id)

        result = await db_session.execute(
            select(Report).where(Report.org_id == org_id, Report.name == UX_SHOWCASE_REPORT_NAME)
        )
        assert len(result.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_calling_the_seeder_twice_directly_is_also_idempotent(self, db_session, two_orgs):
        """Guards against the showcase seeder depending on seed_demo_reports' generic
        marker-based cleanup for its own idempotency -- it must be safe standalone too."""
        org_id = two_orgs["a"]["org"].id
        datasets = await seed_demo_datasets(db_session, org_id)
        reports = await seed_demo_reports(db_session, org_id, datasets)
        await seed_demo_features(db_session, org_id, datasets, reports)

        await seed_demo_ux_showcase(db_session, org_id, datasets)
        await seed_demo_ux_showcase(db_session, org_id, datasets)

        result = await db_session.execute(
            select(Report).where(Report.org_id == org_id, Report.name == UX_SHOWCASE_REPORT_NAME)
        )
        assert len(result.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_remove_demo_content_deletes_the_showcase(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)

        await remove_demo_content(db_session, org_id)

        result = await db_session.execute(
            select(Report).where(Report.org_id == org_id, Report.name == UX_SHOWCASE_REPORT_NAME)
        )
        assert result.scalars().all() == []


class TestShowcaseInteractiveOptions:
    """Task D2: interaction-mode contrast, the prompt page, and the bookmark tour."""

    @pytest.mark.asyncio
    async def test_start_and_drilldown_pages_contrast_interaction_modes(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)

        start_page = _page(report, "Start here")
        drilldown_page = _page(report, "Drill-down")

        start_mode = (start_page.mobile_layout or {}).get("interaction_mode")
        drilldown_mode = (drilldown_page.mobile_layout or {}).get("interaction_mode")

        # Real values PagePropertiesPanel persists: manual/linked/oneway/twoway.
        assert start_mode in {"manual", "linked", "oneway", "twoway"}
        assert drilldown_mode in {"manual", "linked", "oneway", "twoway"}
        assert start_mode != drilldown_mode, "the two pages must demonstrate DIFFERENT modes"
        # Drill-down demonstrates highlight-mode cross-filtering specifically.
        assert drilldown_mode == "linked"

    @pytest.mark.asyncio
    async def test_a_prompt_page_asks_for_a_region_before_rendering(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)

        prompt_page = _page(report, "Choose a region")
        assert prompt_page.page_type == "normal"
        assert prompt_page.prompt_column == "region"
        assert prompt_page.prompt_label

    @pytest.mark.asyncio
    async def test_the_prompt_page_carries_a_data_widget_the_prompt_actually_filters(
        self, db_session, two_orgs,
    ):
        """ReportBuilder builds `promptFilter = {column: prompt_column, value: ...}` and
        passes it to every widget on the page (WidgetRenderer folds it into the same
        WHERE-style filter a cross-filter uses) -- so a page with only a text widget
        has nothing that visibly reacts when a viewer enters a region. At least one
        DATA widget is required for the prompt's filtering to be observable."""
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)
        prompt_page = _page(report, "Choose a region")

        data_widgets = [w for w in prompt_page.widgets if w.widget_type != "text"]
        assert data_widgets, "the prompt page has no data widget for the prompt to filter"

    @pytest.mark.asyncio
    async def test_two_bookmarks_capture_distinct_filter_states(self, db_session, two_orgs):
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)

        result = await db_session.execute(
            select(Bookmark).where(Bookmark.report_id == report.id).order_by(Bookmark.position)
        )
        bookmarks = result.scalars().all()
        assert len(bookmarks) == 2
        names = {b.name for b in bookmarks}
        assert names == {DEMO_SHOWCASE_BOOKMARK_TOP_REGION, DEMO_SHOWCASE_BOOKMARK_WEAK_COUNTRY}

        # BookmarkState (frontend/src/types/report.ts) -- every key ReportBuilder's
        # applyBookmark reads, present on both, and the two states are distinct.
        states = []
        for b in bookmarks:
            assert set(b.state.keys()) >= {"pageId", "activeFilters", "promptValues", "hiddenWidgetIds"}
            assert b.state["activeFilters"], f"bookmark {b.name!r} carries no filter"
            for f in b.state["activeFilters"]:
                assert set(f.keys()) >= {
                    "column", "value", "label", "sourceWidgetId", "sourcePageId",
                }
            states.append((f["column"], f["value"]))
        assert states[0] != states[1], "the two bookmarks must capture DIFFERENT filter states"

    @pytest.mark.asyncio
    async def test_each_bookmarks_filter_column_matches_a_dimension_on_its_page(
        self, db_session, two_orgs,
    ):
        """A bookmark's filter is only observable if some widget on the bookmarked page
        actually charts that column as its `dimension` -- otherwise restoring it changes
        no visible bar/highlight on the page. Guards against a repeat of the earlier
        `month` bookmark, which named a column neither Drill-down chart charted."""
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)
        report = await _loaded_report(db_session, org_id, UX_SHOWCASE_REPORT_NAME)

        result = await db_session.execute(
            select(Bookmark).where(Bookmark.report_id == report.id)
        )
        bookmarks = result.scalars().all()
        assert bookmarks

        for b in bookmarks:
            page = next(p for p in report.pages if p.id == b.state["pageId"])
            page_dimensions = {
                w.config.get("dimension") for w in page.widgets if w.config.get("dimension")
            }
            for f in b.state["activeFilters"]:
                assert f["column"] in page_dimensions, (
                    f"bookmark {b.name!r} filters {f['column']!r}, which no widget on "
                    f"page {page.name!r} charts as its dimension: {page_dimensions}"
                )

    @pytest.mark.asyncio
    async def test_existing_demo_tests_still_pass(self, db_session, two_orgs):
        """Smoke check colocated with the D2 additions: the showcase report must not
        disturb the sales-family reports the generic demo tests assert on."""
        org_id = two_orgs["a"]["org"].id
        await _seed(db_session, org_id)

        result = await db_session.execute(
            select(Report).where(Report.org_id == org_id)
        )
        names = {r.name for r in result.scalars().all()}
        assert "Demo — Sales Overview" in names
        assert UX_SHOWCASE_REPORT_NAME in names
