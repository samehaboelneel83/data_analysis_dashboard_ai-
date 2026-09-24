"""Auto-composed reports: placement, ordering, and the grid contract.

The insights engine already ranked findings and mapped each to a runnable
widget config. What did not exist was PLACEMENT -- so acting on a list of
suggestions meant adding widgets one at a time and sizing each by hand.

These test the composer's two claims. First, that the output is a VALID page:
no two widgets overlap, nothing runs past the 12-column grid, and every widget
carries a config the shapers can actually run. A page that renders as a pile of
stacked charts would pass a naive "did it return widgets" test and be useless.

Second, that the ORDER is the narrative one -- summary, then drivers, then
detail -- because that is the order a report is read in, and the opposite of
the order the detectors emit.
"""
import pytest

from app.services.report_composer import (CHART_H, DETAIL_SCORE, GRID_COLS,
                                          MAX_CHARTS, MAX_KPIS, compose_page)


def _finding(kind="correlation", score=0.9, columns=("a", "b")):
    return {"kind": kind, "score": score, "title": f"{kind} finding",
            "detail": "detail text", "columns": list(columns)}


def _suggestion(wt="scatter", score=0.9, measure="a"):
    return {"widget_type": wt, "title": f"{wt} title", "reason": "because",
            "config": {"dimension": "b", "measure": measure, "aggregation": "sum"},
            "score": score}


ROLES = {"a": "numeric", "b": "numeric", "region": "categorical"}


def _rects(widgets):
    return [(w["layout"]["x"], w["layout"]["y"], w["layout"]["w"], w["layout"]["h"])
            for w in widgets]


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


class TestThePageIsValid:
    """A layout is not 'fine' because it returned widgets."""

    def test_no_two_widgets_overlap(self):
        # THE test. Overlapping widgets render on top of each other, and the
        # page silently loses whatever is underneath.
        page = compose_page([_finding() for _ in range(6)],
                            [_suggestion(score=0.9 - i * 0.12) for i in range(6)],
                            "narrative", ROLES)
        rects = _rects(page["widgets"])
        clashes = [(i, j) for i in range(len(rects)) for j in range(i + 1, len(rects))
                   if _overlap(rects[i], rects[j])]
        assert not clashes, f"overlapping widgets at index pairs {clashes}"

    def test_nothing_runs_past_the_grid(self):
        page = compose_page([_finding() for _ in range(6)],
                            [_suggestion(score=0.9 - i * 0.12) for i in range(6)],
                            None, ROLES)
        for w in page["widgets"]:
            lay = w["layout"]
            assert lay["x"] >= 0
            assert lay["x"] + lay["w"] <= GRID_COLS, f"{w['title']} overflows the grid"

    def test_every_widget_carries_a_runnable_config(self):
        page = compose_page([_finding()], [_suggestion()], None, ROLES)
        for w in page["widgets"]:
            assert w["widget_type"]
            assert isinstance(w["config"], dict)
            if w["widget_type"] != "text":
                assert w["config"], "a chart widget with an empty config renders nothing"


class TestTheOrderIsNarrative:
    def test_kpis_come_first(self):
        page = compose_page([_finding()], [_suggestion()], None, ROLES)
        assert page["widgets"][0]["widget_type"] == "kpi"

    def test_the_narrative_is_last(self):
        # A summary paragraph belongs after the evidence, not before it.
        page = compose_page([_finding()], [_suggestion()], "the story", ROLES)
        last = page["widgets"][-1]
        assert last["widget_type"] == "text"
        assert last["config"]["content"] == "the story"

    def test_a_stronger_finding_gets_a_wider_widget(self):
        # Width encodes rank, so scanning the layout and reading the ranking
        # give the same answer.
        page = compose_page([_finding()],
                            [_suggestion(score=0.95), _suggestion(score=0.4)],
                            None, ROLES)
        charts = [w for w in page["widgets"] if w["widget_type"] != "kpi"]
        assert charts[0]["layout"]["w"] > charts[1]["layout"]["w"]

    def test_drivers_are_placed_above_detail(self):
        page = compose_page([_finding()],
                            [_suggestion(score=0.95), _suggestion(score=0.2)],
                            None, ROLES)
        charts = [w for w in page["widgets"] if w["widget_type"] not in ("kpi", "text")]
        wide = [c for c in charts if c["layout"]["w"] >= GRID_COLS // 2]
        narrow = [c for c in charts if c["layout"]["w"] < GRID_COLS // 2]
        if wide and narrow:
            assert max(c["layout"]["y"] for c in wide) <= min(c["layout"]["y"] for c in narrow)


class TestItStaysReadable:
    def test_the_widget_count_is_capped(self):
        # Findings are ranked, so the cut takes the weakest -- a page of forty
        # charts is scrolled, not read.
        page = compose_page([_finding() for _ in range(40)],
                            [_suggestion(score=0.9) for _ in range(40)], None, ROLES)
        charts = [w for w in page["widgets"] if w["widget_type"] not in ("kpi", "text")]
        assert len(charts) <= MAX_CHARTS

    def test_the_kpi_row_is_capped(self):
        many = {f"m{i}": "numeric" for i in range(12)}
        page = compose_page([_finding(columns=[f"m{i}"]) for i in range(12)],
                            [_suggestion()], None, many)
        assert len([w for w in page["widgets"] if w["widget_type"] == "kpi"]) <= MAX_KPIS

    def test_the_kpi_row_fits_on_one_line(self):
        many = {f"m{i}": "numeric" for i in range(4)}
        page = compose_page([_finding(columns=[f"m{i}"]) for i in range(4)],
                            [_suggestion()], None, many)
        kpis = [w for w in page["widgets"] if w["widget_type"] == "kpi"]
        assert sum(k["layout"]["w"] for k in kpis) <= GRID_COLS


class TestItRespectsTheAuthorsRoles:
    def test_a_column_marked_categorical_never_becomes_a_kpi(self):
        """`effective_roles` applies the Fields-pane overrides, and the engine's
        own docstring names this case: a numeric `year` reclassified as a
        category must stop being a measure, "or the engine reports trends on a
        label". Summing a year would be exactly that."""
        roles = {"year": "categorical", "revenue": "numeric"}
        page = compose_page([_finding(columns=["year", "revenue"])],
                            [_suggestion()], None, roles)
        kpi_measures = [w["config"]["measure"] for w in page["widgets"]
                        if w["widget_type"] == "kpi"]
        assert "year" not in kpi_measures
        assert "revenue" in kpi_measures


class TestDegenerateInput:
    def test_no_findings_yields_no_widgets(self):
        # A tiny or uniform dataset genuinely has nothing to report; the
        # endpoint turns this into a 400 rather than an empty page.
        assert compose_page([], [], None, ROLES)["widgets"] == []

    def test_a_narrative_alone_still_composes(self):
        page = compose_page([], [], "only prose", ROLES)
        assert [w["widget_type"] for w in page["widgets"]] == ["text"]


class TestTheGridMirrorsTheBuilder:
    def test_grid_cols_matches_the_frontend(self):
        """`ReportBuilder.tsx` positions widgets against `COLS = 12`. If these
        drift, the composer produces layouts the canvas cannot represent -- and
        the failure is silent, appearing as widgets running off the page."""
        import os
        import re
        here = os.path.dirname(os.path.abspath(__file__))
        # The builder's grid constants moved into their own module; ReportBuilder
        # imports COLS from it.
        tsx = os.path.join(os.path.dirname(os.path.dirname(here)),
                           "frontend", "src", "pages", "reportBuilder", "grid.ts")
        if not os.path.exists(tsx):
            pytest.skip("frontend/src/pages/reportBuilder/grid.ts not reachable")
        with open(tsx, encoding="utf-8") as fh:
            m = re.search(r"const COLS\s*=\s*(\d+)", fh.read())
        assert m, "COLS is no longer declared in reportBuilder/grid.ts"
        assert int(m.group(1)) == GRID_COLS
