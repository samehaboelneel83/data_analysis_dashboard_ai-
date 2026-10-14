"""Step 3 of the analyst panel (2026-10-02): a benchmark against the
hand-picked HR visuals. The live number comes from running the panel on the
real dataset; here, the measure itself and a floor on synthetic HR data."""
import asyncio
import json
import os

from app.services.panel_benchmark import coverage, question

REF = json.load(open(os.path.join(os.path.dirname(__file__), "data", "hr_reference_visuals.json")))
COLS = set(REF["columns"])
IDS = {"emp_no"}


def test_a_question_is_its_columns_not_its_chart():
    bar = question("bar", {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd"}, COLS, IDS)
    tree = question("treemap", {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd"}, COLS, IDS)
    assert bar == tree == ("compare", frozenset({"dept_name"}))
    pay = question("bar", {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}, COLS, IDS)
    box = question("box_plot", {"dimension": "dept_name", "measure": "salary"}, COLS, IDS)
    assert pay[1] == box[1] and pay[0] != box[0]
    assert question("kpi", {"measure": "emp_no", "aggregation": "countd"}, COLS, IDS) == ("summary", frozenset())


def test_coverage_counts_strict_and_loose_hits():
    ref = REF["visuals"]
    assert len(ref) == 49
    full = coverage(ref, ref, COLS, IDS)
    assert full["strict_recall"] == 1.0 and full["missed"] == []
    one = coverage([{"widget_type": "box_plot", "title": "x",
                     "config": {"dimension": "dept_name", "measure": "salary"}}], ref, COLS, IDS)
    assert one["loose"] > one["strict"] >= 1


def test_the_panel_without_a_model_still_finds_a_fair_share():
    """A floor, not a target: the statistics engine alone, on synthetic HR
    data shaped like the real one. The live run with the analysts is the
    real benchmark."""
    from tests.test_analyst_panel import _run
    out, _ = _run(size=50, client=None)
    picks = [w for p in out["proposals"] for w in p["widgets"]]
    cov = coverage(picks, REF["visuals"], COLS, IDS)
    assert cov["loose_recall"] >= 0.3, cov
