"""Frontend copies of backend limits must not drift.

The widget config panel has to know the shaper's limits to build an honest
form: it cannot offer `avg` on a sunburst, or an eighth nesting level, when the
shaper will refuse them. Those limits therefore exist twice -- once in Python,
once in `types/report.ts`.

A silently-drifted copy is worse than no copy. If the frontend still believes
the depth cap is 8 after Python lowers it to 6, the panel promises something
the shaper then rejects, and the user meets an error the UI told them was fine.

So this reads the TypeScript source and asserts each mirrored value against the
real Python one. Same technique `test_registry.py` uses to pin the analysis
catalogue, and the same reason: two sources of truth are acceptable only when
something enforces that they agree.
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TS = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                   "frontend", "src", "types", "report.ts")


@pytest.fixture(scope="module")
def ts() -> str:
    """The frontend constants file, or a skip.

    Not copied into the backend image, so this suite skips when run inside the
    container -- the same stance `test_compose_defaults.py` takes. On a
    developer checkout and in CI the file is present and every assertion runs.
    """
    if not os.path.exists(_TS):
        pytest.skip("frontend/src/types/report.ts not reachable")
    with open(_TS, encoding="utf-8") as fh:
        return fh.read()


def _number(ts: str, name: str) -> int:
    m = re.search(rf"export const {name}\s*=\s*(\d+)", ts)
    assert m, f"{name} is not exported from report.ts"
    return int(m.group(1))


def _string_list(ts: str, name: str) -> set[str]:
    m = re.search(rf"export const {name}[^=]*=\s*\[(.*?)\]", ts, re.S)
    assert m, f"{name} is not exported from report.ts"
    return set(re.findall(r"'([^']+)'", m.group(1)))


class TestHierarchyLimits:
    def test_depth_cap_matches(self, ts):
        from app.services.widget_data import HIER_MAX_DEPTH
        assert _number(ts, "HIER_MAX_DEPTH") == HIER_MAX_DEPTH

    def test_the_additive_aggregation_set_matches(self, ts):
        """THE one that must not drift. If the frontend's set is wider than the
        backend's, the panel offers an aggregation that makes a sunburst draw a
        falsehood -- and the refusal arrives only after the user has chosen."""
        from app.services.widget_data import ADDITIVE_AGGREGATIONS
        assert _string_list(ts, "ADDITIVE_AGGREGATIONS") == set(ADDITIVE_AGGREGATIONS)

    def test_the_partition_widgets_match(self, ts):
        from app.services.widget_data import PARTITION_WIDGETS
        assert _string_list(ts, "PARTITION_WIDGETS") == set(PARTITION_WIDGETS)

    def test_the_graph_marks_match(self, ts):
        """A composed graph's layer offers these marks. An entry the shaper
        does not know is silently drawn as a bar, so the panel must not offer
        one the backend has never heard of."""
        from app.services.widget_data import GRAPH_MARKS
        assert _string_list(ts, "GRAPH_MARKS") == set(GRAPH_MARKS)

    def test_every_hierarchy_widget_has_a_shaper(self, ts):
        """The list drives the panel's options block; a name with no shaper
        would render a form for a widget that cannot be computed."""
        from app.services.widget_data import SHAPERS
        for name in _string_list(ts, "HIERARCHY_WIDGETS"):
            assert name in SHAPERS, name


class TestRankingCapabilityMirror:
    """The Ranking group is gated per widget type on BOTH sides.

    Backend truth is DERIVED (RANKED_WIDGETS reads the dispatch table for the
    shapers that call _rank_selection); the frontend set is hand-mirrored in
    widgetCapabilities.ts. If they drift in either direction the failure is a
    dead control (offered, ignored) or a hidden capability (honoured, never
    offered) -- the two defects the capability file exists to prevent.
    """

    def _frontend_set(self) -> set[str]:
        path = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                            "frontend", "src", "components", "report",
                            "widgetCapabilities.ts")
        if not os.path.exists(path):
            pytest.skip("widgetCapabilities.ts not reachable")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r"RANKING_WIDGETS = new Set\(\[(.*?)\]\)", src, re.S)
        assert m, "RANKING_WIDGETS is not exported from widgetCapabilities.ts"
        return set(re.findall(r"'([^']+)'", m.group(1)))

    def test_the_sets_match_exactly(self):
        from app.services.widget_data import RANKED_WIDGETS
        assert self._frontend_set() == set(RANKED_WIDGETS)

    def test_the_backend_set_is_derived_not_stale(self):
        """Every listed type's shaper must actually be one of the ranking
        shapers -- the guard against RANKED_WIDGETS being edited by hand."""
        from app.services.widget_data import (RANKED_WIDGETS, SHAPERS,
                                              _RANKING_SHAPERS)
        for wt in RANKED_WIDGETS:
            assert SHAPERS[wt].__name__ in _RANKING_SHAPERS, wt


class TestSmallMultiples:
    def test_panel_cap_matches(self, ts):
        from app.services.widget_data import FACET_MAX_PANELS
        assert _number(ts, "FACET_MAX_PANELS") == FACET_MAX_PANELS

    def test_every_facetable_widget_is_a_real_shaper(self, ts):
        from app.services.widget_data import SHAPERS
        for name in _string_list(ts, "FACETABLE_WIDGETS"):
            assert name in SHAPERS, name

    def test_a_small_multiple_cannot_face_itself(self, ts):
        """Recursion here would be an infinite request, not a clever feature --
        the shaper guards it, and the panel must not offer it either."""
        assert "small_multiples" not in _string_list(ts, "FACETABLE_WIDGETS")


class TestForecastBounds:
    def test_max_periods_matches(self, ts):
        from app.services.widget_data import MAX_FORECAST_PERIODS
        assert _number(ts, "FORECAST_MAX_PERIODS") == MAX_FORECAST_PERIODS

    def test_default_periods_matches(self, ts):
        from app.services.widget_data import DEFAULT_FORECAST_PERIODS
        assert _number(ts, "FORECAST_DEFAULT_PERIODS") == DEFAULT_FORECAST_PERIODS


class TestEveryRunnableAnalysisIsReachable:
    """A registered analysis with no way to reach it is invisible to users.

    This is the trap this codebase has now hit five times: a capability lands
    with working endpoints, passing tests and no caller, and nothing notices
    because the backend suite only ever asks whether the endpoint works.

    It used to be checked by mirroring `STATISTICS_ROUTES`, a hand-written
    name-to-slug map in api.ts: registering a ninth statistical analysis failed
    here until somebody added an entry. That map is gone, and so is the class of
    problem it guarded -- the panel posts every analysis to ONE dispatch route,
    so a newly runnable analysis is reachable the moment it is registered, with
    no frontend edit to forget.

    What still needs pinning is the wiring that replaced it: the route exists,
    the frontend calls THAT route, and the panel offers what the catalogue says
    is runnable. Plus the typed statistics endpoints, which remain the public
    API even though the UI no longer calls them.
    """

    #: Registry name -> the slug its typed endpoint is served under. Not a
    #: mechanical transform of the name (`test_independence` is `independence`,
    #: `pairwise_comparisons` is `pairwise`), so it is written out and checked.
    TYPED_SLUGS = {
        "compare_groups": "compare-groups",
        "test_independence": "independence",
        "correlation_test": "correlation",
        "regression": "regression",
        "glm_logistic": "glm-logistic",
        "mixed_model": "mixed-model",
        "survival": "survival",
        "pairwise_comparisons": "pairwise",
    }

    @pytest.fixture(scope="class")
    def ts_api(self) -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                            "frontend", "src", "services", "api.ts")
        if not os.path.exists(path):
            pytest.skip("frontend/src/services/api.ts not reachable")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    @pytest.fixture(scope="class")
    def ts_panel(self) -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "frontend",
                            "src", "components", "StatisticsPanel.tsx")
        if not os.path.exists(path):
            pytest.skip("StatisticsPanel.tsx not reachable")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_the_dispatch_route_is_served(self):
        from app.main import app
        from tests._routes import served_paths
        served = served_paths(app)
        assert "/api/v1/datasets/{dataset_id}/analysis/run" in served

    def test_the_frontend_posts_to_the_dispatch_route(self, ts_api):
        """The half a backend test can still see: if this path drifts, every
        analysis becomes unreachable at once rather than one at a time."""
        assert "/analysis/run" in ts_api, (
            "api.ts no longer posts to the analysis dispatch route -- the panel "
            "is calling something else, or nothing")

    def test_the_panel_offers_what_the_catalogue_calls_runnable(self, ts_panel):
        """Filtering on `result_kind` instead is what kept this screen at eight
        analyses while eleven others sat finished and unreachable."""
        assert "runnable" in ts_panel, (
            "StatisticsPanel no longer filters on `runnable` -- newly "
            "registered analyses will not appear")

    def test_the_schema_hint_the_form_depends_on_is_read(self, ts_panel):
        """Without `format: 'column'` the form cannot tell a column reference
        from a number to type, and goal seek's target renders as a column
        dropdown nobody can enter a number into."""
        assert "'column'" in ts_panel

    def test_every_statistical_analysis_keeps_its_typed_endpoint(self):
        """The typed routes stay: a hand-written caller gets a 422 naming the
        field it got wrong, which a dispatcher can never give."""
        from app.main import app
        from app.services.analysis.registry import all_analyses
        from tests._routes import served_paths
        served = served_paths(app)
        registered = {s.name for s in all_analyses()
                      if s.result_kind == "statistical_test"}
        assert registered == set(self.TYPED_SLUGS), (
            f"the statistical analyses changed: {sorted(registered)} -- update "
            f"TYPED_SLUGS, and give any new one its typed endpoint")
        for name, slug in self.TYPED_SLUGS.items():
            path = f"/api/v1/datasets/{{dataset_id}}/statistics/{slug}"
            assert path in served, f"no endpoint for '{name}' at slug '{slug}'"

    def test_every_runnable_analysis_can_actually_be_dispatched(self):
        """The dispatcher's promise, checked against the catalogue rather than
        against a frontend constant: everything it advertises resolves."""
        from app.services.analysis.registry import all_analyses, resolve_handler
        for spec in all_analyses():
            if spec.to_dict()["runnable"]:
                assert callable(resolve_handler(spec)), spec.name


class TestCellEditLimit:
    """The cell editor refuses at the keystroke what the backend refuses at the
    save. If the frontend's copy drifts above the real limit, the user loses an
    edit to a 400 they had no warning of; below it, they are stopped early for
    no reason."""

    @pytest.fixture(scope="class")
    def ts_edits(self) -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                            "frontend", "src", "lib", "cellEdits.ts")
        if not os.path.exists(path):
            pytest.skip("frontend/src/lib/cellEdits.ts not reachable")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_the_edit_cap_matches(self, ts_edits):
        from app.services.prep import MAX_CELL_EDITS
        m = re.search(r"export const MAX_CELL_EDITS\s*=\s*(\d+)", ts_edits)
        assert m, "MAX_CELL_EDITS is not exported from cellEdits.ts"
        assert int(m.group(1)) == MAX_CELL_EDITS


class TestQuickCalcExpressions:
    """Every one-click calculation the field list offers must actually evaluate.

    The generator is TypeScript (`lib/quickCalcs.ts`) and the engine is Python
    (`measure_eval`), so nothing but this test stands between the two. The whole
    value of a one-click calculation is that it cannot be typed wrong; one that
    saves and then fails to evaluate is worse than no offer at all.

    The expressions are read out of the source and run for real, rather than
    re-listed here -- a copy would drift exactly as silently as the frontend
    constants this file already pins.
    """

    @pytest.fixture(scope="class")
    def expressions(self) -> list[str]:
        path = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                            "frontend", "src", "lib", "quickCalcs.ts")
        if not os.path.exists(path):
            pytest.skip("frontend/src/lib/quickCalcs.ts not reachable")
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        found = re.findall(r"expression:\s*`([^`]+)`", source)
        assert found, "no expressions found in quickCalcs.ts"
        return found

    @pytest.fixture
    def frame(self):
        import pandas as pd
        return pd.DataFrame({
            "region": ["N", "S", "N", "E"],
            "revenue": [10.0, 20.0, 30.0, 40.0],
        })

    def test_the_generator_offers_something(self, expressions):
        # Both branches of quickCalcsFor are read, not just the numeric one.
        assert len(expressions) >= 6

    def test_every_expression_evaluates_at_a_grain(self, expressions, frame):
        from app.services.measure_eval import evaluate_measure
        for template in expressions:
            # `${c}` is the field the menu was opened on.
            column = "revenue" if "SUM(" in template or "AVG(" in template \
                or "MEDIAN(" in template or "STDEV(" in template else "region"
            expr = template.replace("${c}", column)
            result = evaluate_measure(expr, frame, ["region"])
            assert result is not None, expr

    def test_every_expression_evaluates_with_no_grain(self, expressions, frame):
        """A measure is also evaluated ungrouped -- a KPI tile has no dimension,
        and TOTAL(...) inside one must not divide by a Series."""
        from app.services.measure_eval import evaluate_measure
        for template in expressions:
            column = "revenue" if "SUM(" in template or "AVG(" in template \
                or "MEDIAN(" in template or "STDEV(" in template else "region"
            expr = template.replace("${c}", column)
            evaluate_measure(expr, frame, [])

    def test_a_percent_of_total_really_sums_to_a_hundred(self, expressions, frame):
        # The one whose arithmetic is worth checking rather than merely running:
        # a percent-of-total that re-bases on the visible groups would not.
        from app.services.measure_eval import evaluate_measure
        template = next(e for e in expressions if "TOTAL(SUM(" in e)
        series = evaluate_measure(template.replace("${c}", "revenue"), frame, ["region"])
        assert round(float(series.sum()), 6) == 100.0


class TestEveryOfferedAggregationWorks:
    """The panel's aggregation menu, pinned against the engine that runs them.

    An aggregation offered in a dropdown and refused by the shaper is the exact
    drift this file exists to catch: the author picks it, the widget renders a
    fallback sum, and nothing anywhere says so. Checked both ways -- the router
    accepts the name at write time, and `_agg_series` actually computes it.
    """

    @pytest.fixture(scope="class")
    def offered(self, ts) -> list[str]:
        block = re.search(r"export const AGGREGATIONS\s*=\s*\[(.*?)\n\]", ts, re.S)
        assert block, "AGGREGATIONS is not exported from report.ts"
        values = re.findall(r"value:\s*'([^']+)'", block.group(1))
        assert len(values) >= 16, f"only {len(values)} aggregations parsed"
        return values

    def test_the_router_accepts_every_one(self, offered):
        from app.routers.datasets import _VALID_AGGREGATIONS
        missing = [a for a in offered if a not in _VALID_AGGREGATIONS]
        assert not missing, f"offered in the panel, refused on save: {missing}"

    def test_the_engine_computes_every_one(self, offered):
        """Not just 'is in the allowlist' -- run it. `_agg_series` falls back to
        sum for a name it does not know, so an unimplemented aggregation would
        return a plausible number and never raise."""
        import pandas as pd
        from app.services.widget_data import _agg_series

        sample = pd.Series([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        summed = _agg_series(sample, "sum")
        for agg in offered:
            if agg in ("sum", "frequency", "pct"):
                continue          # sum IS the fallback; pct is shaped elsewhere
            got = _agg_series(sample, agg)
            assert got != summed, (
                f"'{agg}' returned the sum -- it fell through to the default "
                f"instead of being implemented")
