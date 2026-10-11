"""Guided setup v2: Check & discover cleans by itself, and every fix can be undone."""
from app.services.guided_setup import cleaning


def item(kind, column=None, action=None, rows=5, what="x"):
    return {"id": f"{kind}:{column or ''}:0", "kind": kind, "column": column, "tone": "warning",
            "what": what, "rows": rows, "action": action}


ITEMS = [
    item("dups", action={"kind": "dedupe", "label": "Remove the copies"}, rows=420),
    item("spaces", "city", {"kind": "trim", "column": "city", "label": "Remove"}),
    item("useless", "note", {"kind": "drop_column", "column": "note", "label": "Leave out"}),
    item("rule", "a, b", {"kind": "exclude", "expression": "(`a` <= `b`) or `a` != `a`", "rule": "`a` <= `b`",
                          "label": "Leave out"}, what="End before start (55 / 60,000)"),
    item("outliers", "fee"),                       # may be true data: never automatic
    item("future", "created_at"),
]


def test_safe_fixes_are_planned_and_true_looking_data_is_left_alone():
    plan = cleaning.plan(ITEMS, "en")
    assert [a["kind"] for a in plan] == ["spaces", "rule", "useless", "dups"]     # tidy values first, copies last
    assert all(a["step"]["origin"] == "setup" and a["step"]["origin_id"] == a["id"] for a in plan)
    assert plan[-1]["said"] == "removed 420 copied rows"
    assert plan[1]["ai"] is True and "End before start" in plan[1]["said"]


def test_an_undone_fix_is_never_planned_again():
    first = cleaning.plan(ITEMS, "en")
    undone = {a["key"] for a in first if a["kind"] == "dups"}
    assert "dups" not in [a["kind"] for a in cleaning.plan(ITEMS, "en", undone=undone)]


def test_a_column_the_person_named_is_never_left_out():
    assert "useless" not in [a["kind"] for a in cleaning.plan(ITEMS, "en", protect={"Note"})]


def test_undo_removes_exactly_the_steps_the_setup_added():
    plan = cleaning.plan(ITEMS, "en")
    by_hand = {"kind": "trim", "columns": ["name"]}
    steps = cleaning.steps_with([by_hand], plan)
    assert len(steps) == 5 and steps[0] == by_hand
    assert cleaning.steps_with(steps, plan) == steps                  # applying twice adds nothing
    dups = next(a for a in plan if a["kind"] == "dups")
    left = cleaning.steps_without(steps, {dups["id"]})
    assert by_hand in left and len(left) == 4
    assert all(s.get("origin_id") != dups["id"] for s in left)
    assert cleaning.steps_without(steps, {a["id"] for a in plan}) == [by_hand]


def test_the_summary_says_what_was_fixed_and_what_is_left_to_know():
    plan = cleaning.plan(ITEMS, "ar")
    plan[0]["state"] = "undone"
    rest = [ITEMS[4], ITEMS[5]]
    s = cleaning.summary({"actions": plan, "rows_before": 100, "rows_after": 90}, rest)
    assert len(s["fixed"]) == 3 and len(s["know"]) == 2 and s["more"] == 0
    assert (s["rows_before"], s["rows_after"]) == (100, 90)
    assert any("مكرر" in f["said"] for f in s["fixed"])


def test_an_ai_rule_touching_many_rows_is_left_to_the_person():
    late = item("rule", "service, days", {"kind": "exclude", "expression": "e", "rule": "r", "label": "x"}, rows=311)
    typo = item("rule", "a, b", {"kind": "exclude", "expression": "e2", "rule": "r2", "label": "x"}, rows=6)
    kinds = [a["rows"] for a in cleaning.plan([late, typo], "en", rows=7203)]
    assert kinds == [6]                    # 0.08% is applied; 4.3% may be real events
