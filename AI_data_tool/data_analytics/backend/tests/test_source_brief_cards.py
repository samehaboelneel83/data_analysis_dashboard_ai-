"""Suggesting from a connection, `cards` mode (settings.source_ai_selection):
the model writes the query -- there are no rows until it has -- and then only
chooses among the charts the platform made from the query's own result."""
import asyncio

from app.services import source_brief as sb

COLS = ["group", "kind", "day", "amount"]
ROWS = [[g, k, f"2025-{m:02d}-01", 10.0 * (i + 1) + m]
        for m in range(1, 9) for i, (g, k) in enumerate([("a", "x"), ("b", "y"), ("c", "x"), ("d", "y")])]
CATALOG = [{"name": "t", "rows": len(ROWS), "columns": [{"name": c, "dtype": "text"} for c in COLS]}]
BRIEF = {"language": "en", "role": "r", "understanding": "u", "cannot_answer": [],
         "questions": [{"question": "Which group has the most?", "tables": ["t"]}],
         "dashboards": [{"title": "T", "questions": [1]}]}
OWN = {"proposals": [{"title": "T", "purpose": "p", "sql": "SELECT * FROM t", "widgets": [
    {"widget_type": "kpi", "title": "the model's own", "measure": "amount", "aggregation": "sum",
     "question": "", "dimension": "", "dimension2": ""},
    {"widget_type": "bar", "title": "the model's own bar", "measure": "amount", "aggregation": "sum",
     "question": "", "dimension": "group", "dimension2": ""}]}]}


def test_the_ready_charts_come_from_the_shape_of_the_result_and_pass_its_check():
    ready = sb.ready_widgets(COLS, ROWS)
    kinds = {w["widget_type"] for w in ready}
    assert {"kpi", "bar"} <= kinds and kinds <= set(sb.WIDGET_TYPES)
    assert any(w["dimension"] == "group" and w["measure"] == "amount" for w in ready)
    assert all(w["aggregation"] in sb.AGGREGATIONS for w in ready)
    assert sb.ready_widgets(COLS, []) == []


def run(picks, selection):
    asked = []

    class Client:
        async def complete_json(self, messages, schema, **kw):
            asked.append(schema)
            if schema is sb.BRIEF_SCHEMA:
                return BRIEF
            if schema is sb.READY_SCHEMA:
                return picks
            return OWN

    async def run_query(sql, limit):
        return {"columns": COLS, "rows": ROWS}
    props, _, why = asyncio.run(sb.design(client=Client(), catalog=CATALOG, persona="p", request="cards-test",
                                          joins=[], run_query=run_query, count=1, fresh=True, enriched=True,
                                          selection=selection))
    return props, asked, why


def test_in_cards_mode_the_dashboard_holds_only_charts_from_the_list():
    ready = sb.ready_widgets(COLS, ROWS)
    a = next(i for i, w in enumerate(ready) if w["widget_type"] == "bar" and w["dimension"] == "group")
    b = next(i for i, w in enumerate(ready) if w["widget_type"] == "kpi")
    props, asked, why = run({"picks": [{"id": a, "question": "Which group has the most?", "title": "By group"},
                                       {"id": b, "question": "How much in all?", "title": "In all"},
                                       {"id": 999, "question": "x", "title": "not in the list"},
                                       {"id": a, "question": "x", "title": "the same chart twice"}]}, "cards")
    assert props, why
    p = props[0]
    assert p["charts_from"] == "ready" and [w["title"] for w in p["widgets"]] == ["By group", "In all"]
    # The chart is the platform's: only its title and its question are the model's.
    assert (p["widgets"][0]["dimension"], p["widgets"][0]["measure"]) == (ready[a]["dimension"], ready[a]["measure"])
    assert p["sql"] == "SELECT * FROM t" and sb.READY_SCHEMA in asked


def test_too_few_chosen_and_the_models_own_checked_charts_stand():
    props, _asked, why = run({"picks": []}, "cards")
    assert props, why
    assert "charts_from" not in props[0] and props[0]["widgets"][0]["title"] == "the model's own"


def test_free_never_asks_for_a_choice():
    props, asked, _ = run({"picks": []}, "free")
    assert props and sb.READY_SCHEMA not in asked


def test_the_mode_is_a_setting_and_free_unless_said(monkeypatch):
    from app.core.config import settings
    assert sb.selection_mode() == "free"
    monkeypatch.setattr(settings, "source_ai_selection", "cards")
    assert sb.selection_mode() == "cards" and sb.selection_mode("free") == "free"


def test_a_column_named_for_its_own_roll_up_is_not_given_the_word_twice():
    cols = ["group", "total_items", "avg_days"]
    rows = [[g, 10 * (i + 1), 1.5 + i] for i, g in enumerate("abcdef")] * 3
    titles = [w["title"] for w in sb.ready_widgets(cols, rows)]
    assert not any("Total total" in t or "Average avg" in t for t in titles), titles
    assert "Avg days" in titles
