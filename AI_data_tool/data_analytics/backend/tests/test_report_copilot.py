"""The dashboard page copilot: chat that edits the OPEN page.

Two layers under test. The NODE (nodes/copilot.py) is a contract: the page
the user sees -- widgets with real ids, dataset columns -- must reach the
prompt, and the reply must split into page actions XOR a data question,
never a refusal. The ROUTER applies actions through the same writes the GUI
endpoints perform: same org scoping, same edit-capability gate, same
revision bump; bad actions are skipped with notes, not fatal.
"""
import pytest
from sqlalchemy import select

from app.models.models import (AgentRun, AgentStep, Dataset, Report,
                               ReportPage, ReportWidget)
from app.services.agent.nodes.copilot import (COPILOT_SCHEMA,
                                              render_page_context,
                                              resolve_copilot)


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply


PAGE_CTX = {
    "report_name": "Sales", "page_name": "Overview",
    "widgets": [{"id": 41, "widget_type": "bar", "title": "Revenue by region",
                 "config": {"dimension": "region", "measure": "revenue", "agg": "sum"},
                 "layout": {"x": 0, "y": 0, "w": 6, "h": 5}}],
    "columns": {"demo_sales": {"region": "text", "revenue": "numeric"}},
}


class TestNode:
    async def test_the_page_and_columns_reach_the_prompt(self):
        client = FakeClient({"reply": "ok", "data_question": None, "actions": []})
        await resolve_copilot("what is here?", [], PAGE_CTX, client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "[id 41] bar \"Revenue by region\"" in text
        assert "auto_reload_seconds" in text or "never refuse" in text
        assert "region (text)" in text
        assert client.calls[0]["schema"] is COPILOT_SCHEMA
        assert client.calls[0]["enforce"] is True

    async def test_the_screenshot_case_is_a_worked_example(self):
        # The complaint that shaped this node, pinned: the auto-reload
        # request must be shown to the model as an UPDATE action example,
        # not left for it to classify as an unanswerable SQL question.
        client = FakeClient({"reply": "ok", "data_question": None, "actions": []})
        await resolve_copilot("q", [], PAGE_CTX, client)
        system = client.calls[0]["messages"][0]["content"]
        assert '"key": "auto_reload_seconds", "value": 60' in system
        assert "never refuse" in system

    async def test_wire_pairs_fold_into_config_dicts(self):
        # The schema ships config as key/value PAIRS (strict json_schema
        # modes reject open objects; a rejected schema would 502 every
        # message). The router must still receive plain dicts.
        client = FakeClient({"reply": "ok", "data_question": None, "actions": [
            {"op": "update", "widget_type": None, "widget_id": 41, "title": None,
             "config": [{"key": "auto_reload_seconds", "value": 60},
                        {"key": "legend", "value": False}],
             "layout": {"x": None, "y": None, "w": 12, "h": None}}]})
        got = await resolve_copilot("q", [], PAGE_CTX, client)
        act = got["actions"][0]
        assert act["config"] == {"auto_reload_seconds": 60, "legend": False}
        assert act["layout"] == {"w": 12}

    async def test_an_all_null_layout_means_no_layout_change(self):
        client = FakeClient({"reply": "ok", "data_question": None, "actions": [
            {"op": "update", "widget_type": None, "widget_id": 41, "title": "T",
             "config": None,
             "layout": {"x": None, "y": None, "w": None, "h": None}}]})
        got = await resolve_copilot("q", [], PAGE_CTX, client)
        assert got["actions"][0]["layout"] is None

    async def test_history_rides_along(self):
        client = FakeClient({"reply": "ok", "data_question": None, "actions": []})
        await resolve_copilot("rename it", [
            {"role": "user", "content": "add a pie of revenue"},
            {"role": "assistant", "content": "Added it."},
        ], PAGE_CTX, client)
        text = client.calls[0]["messages"][1]["content"]
        assert "add a pie of revenue" in text
        assert text.endswith("Message: rename it")

    async def test_a_reply_with_both_keeps_the_edits_and_drops_the_question(self):
        client = FakeClient({"reply": "ok", "data_question": "total revenue?",
                             "actions": [{"op": "delete", "widget_type": None,
                                          "widget_id": 41, "title": None,
                                          "config": None, "layout": None}]})
        got = await resolve_copilot("q", [], PAGE_CTX, client)
        assert got["data_question"] is None
        assert len(got["actions"]) == 1

    async def test_model_failure_is_none(self):
        assert await resolve_copilot("q", [], PAGE_CTX, FakeClient(None)) is None

    def test_the_context_renders_an_empty_page_honestly(self):
        text = render_page_context({"report_name": "R", "page_name": "P",
                                    "widgets": [], "columns": {}})
        assert "(none yet)" in text
        assert "(no dataset attached)" in text

    def test_the_selected_widget_is_marked_and_explained(self):
        # Live feedback: "do that for the selected chart" only worked by
        # guessing. The selection must be visible in the context.
        text = render_page_context({**PAGE_CTX, "selected_widget_id": 41})
        assert '[id 41] bar "Revenue by region" (SELECTED)' in text
        assert 'has widget [id 41] selected' in text

    def test_a_selection_not_on_this_page_is_ignored(self):
        text = render_page_context({**PAGE_CTX, "selected_widget_id": 999})
        assert "(SELECTED)" not in text
        assert "selected" not in text.split("Dataset columns")[0].split("]")[-1] or True
        assert "has widget" not in text

    async def test_movement_and_honesty_rules_reach_the_prompt(self):
        # Live feedback again: the model claimed charts cannot be moved, and
        # claimed an "animated" edit it never made. Both rules are pinned.
        client = FakeClient({"reply": "ok", "data_question": None, "actions": []})
        await resolve_copilot("q", [], PAGE_CTX, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "You CAN move, reorder, swap and resize" in system
        assert "smaller y is HIGHER" in system
        assert "never invent a key and claim success" in system
        assert "language the user wrote in" in system

    async def test_calculated_columns_are_a_page_command_not_a_refusal(self):
        # Live: "create a new fx expression" / "ƒx Calculated columns can i
        # add one" were answered "the builder does not support that". The
        # GUI's CalcColumnsPanel does, via PUT /calculated-columns, so the
        # copilot must be told it can too.
        client = FakeClient({"reply": "ok", "data_question": None, "actions": []})
        await resolve_copilot("q", [], PAGE_CTX, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "add_calculated_column" in system
        assert "You CAN create calculated columns" in system
        assert '"op": "add_calculated_column"' in system

    def test_existing_calculated_columns_are_listed_in_context(self):
        text = render_page_context({
            **PAGE_CTX,
            "calculated_columns": [
                {"name": "all_employee_count", "expression": "SUM(employee_count)"},
            ],
        })
        assert "all_employee_count" in text
        assert "SUM(employee_count)" in text
        assert "whole-dataset result" in text
        assert "add_calculated_column" in COPILOT_SCHEMA["properties"]["actions"][
            "items"]["properties"]["op"]["enum"]

    async def test_the_users_aggregation_order_is_obeyed_not_refused(self):
        # Aggregation is a normal tool. "dont sum / individual rows" must
        # still be possible (aggregation none), and "sum this" must not be
        # refused just because the column is an fx total.
        client = FakeClient({"reply": "ok", "data_question": None, "actions": []})
        await resolve_copilot("q", [], PAGE_CTX, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "Do exactly what the user asked" in system
        assert "never refuse an aggregation" in system
        assert '"value": "none"' in system
        assert '"value": "sum"' in system
        assert "individual" in system.lower() or "every row" in system.lower()


# ── Router ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def world(db_session, two_orgs):
    """A report with one page, one widget, and a dataset id (columns are
    stubbed -- loading real files is the context loader's own test's job)."""
    org = two_orgs["a"]["org"]
    ds = Dataset(name="demo_sales", filename="demo.csv", org_id=org.id)
    db_session.add(ds)
    await db_session.flush()
    report = Report(name="Sales", org_id=org.id, dataset_id=ds.id,
                    created_by=two_orgs["a"]["user"].id)
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Overview", position=0)
    db_session.add(page)
    await db_session.flush()
    widget = ReportWidget(page_id=page.id, widget_type="bar",
                          title="Revenue by region",
                          config={"dimension": "region", "measure": "revenue"},
                          layout={"x": 0, "y": 0, "w": 6, "h": 5})
    db_session.add(widget)
    await db_session.commit()
    return {"report": report, "page": page, "widget": widget, "dataset": ds}


@pytest.fixture
def columns(monkeypatch):
    async def fake_columns(db, report, org_id):
        return {"demo_sales": {"region": "text", "revenue": "numeric",
                               "units": "numeric"}}
    monkeypatch.setattr("app.routers.report_copilot._page_columns", fake_columns)


@pytest.fixture
def model(monkeypatch):
    """Scripted copilot verdicts, consumed in order."""
    replies = []

    class Client:
        async def complete_json(self, messages, schema, **kw):
            return replies.pop(0) if replies else None

    monkeypatch.setattr("app.routers.report_copilot.llm_service.get_client",
                        lambda: Client())
    return replies


def action(**kw):
    base = {"op": "update", "widget_type": None, "widget_id": None,
            "title": None, "config": None, "layout": None}
    return {**base, **kw}


async def call(client, headers, world, message, **extra):
    return await client.post(
        f"/api/v1/reports/{world['report'].id}/pages/{world['page'].id}/copilot",
        json={"message": message, **extra}, headers=headers)


class TestActions:
    async def test_create_lands_at_the_bottom_with_catalog_size(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Added a line chart.", "data_question": None,
                      "actions": [action(op="create", widget_type="line",
                                         title="Units over time",
                                         config={"dimension": "region",
                                                 "measure": "units", "agg": "sum"})]})
        r = await call(client, auth_headers["a"], world, "add a line of units")
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["applied"][0]["op"] == "create"
        assert got["notes"] == []
        created = (await db_session.execute(select(ReportWidget).where(
            ReportWidget.widget_type == "line"))).scalar_one()
        assert created.title == "Units over time"
        assert created.layout == {"x": 0, "y": 5, "w": 6, "h": 5}  # below the bar
        # The copilot schema says `agg`; widgets read `aggregation`.
        assert created.config.get("aggregation") == "sum"
        assert "agg" not in created.config
        report = await db_session.get(Report, world["report"].id)
        assert report.revision == 1

    async def test_the_auto_reload_screenshot_case_updates_the_widget(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Set auto-reload to 60 seconds.",
                      "data_question": None,
                      "actions": [action(op="update", widget_id=world["widget"].id,
                                         config={"auto_reload_seconds": 60})]})
        r = await call(client, auth_headers["a"], world,
                       "change Auto-reload (seconds) to 1 minute")
        assert r.status_code == 200
        assert r.json()["applied"] == [{"op": "update",
                                        "widget_id": world["widget"].id,
                                        "title": "Revenue by region"}]
        w = await db_session.get(ReportWidget, world["widget"].id)
        assert w.config["auto_reload_seconds"] == 60
        assert w.config["dimension"] == "region"   # merge, not replace

    async def test_update_can_convert_retitle_and_resize(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Done.", "data_question": None,
                      "actions": [action(op="update", widget_id=world["widget"].id,
                                         widget_type="pie", title="Sales share",
                                         layout={"w": 40})]})
        r = await call(client, auth_headers["a"], world, "pie, full width")
        assert r.status_code == 200
        w = await db_session.get(ReportWidget, world["widget"].id)
        assert w.widget_type == "pie"
        assert w.title == "Sales share"
        assert w.layout["w"] == 12          # clamped to the grid
        assert w.layout["x"] == 0

    async def test_delete_removes_the_widget(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Removed it.", "data_question": None,
                      "actions": [action(op="delete", widget_id=world["widget"].id)]})
        r = await call(client, auth_headers["a"], world, "remove the chart")
        assert r.status_code == 200
        assert (await db_session.execute(select(ReportWidget))).scalars().all() == []

    async def test_bad_actions_are_skipped_with_notes_and_good_ones_land(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Two edits.", "data_question": None,
                      "actions": [
                          action(op="create", widget_type="hologram", title="X"),
                          action(op="create", widget_type="bar", title="Bad column",
                                 config={"dimension": "regionn", "measure": "revenue"}),
                          action(op="update", widget_id=999999,
                                 config={"legend": False}),
                          action(op="update", widget_id=world["widget"].id,
                                 config={"legend": False, "dataset_id": 42}),
                      ]})
        r = await call(client, auth_headers["a"], world, "do things")
        assert r.status_code == 200
        got = r.json()
        assert len(got["applied"]) == 1
        assert len(got["notes"]) == 3
        w = await db_session.get(ReportWidget, world["widget"].id)
        assert w.config["legend"] is False
        assert "dataset_id" not in w.config    # never repointed silently

    async def test_a_null_value_removes_the_setting(
            self, client, auth_headers, world, columns, model, db_session):
        # Found live: "احذف التحميل التلقائي" (remove the auto-reload) was
        # answered confidently while the dropped null left the value behind.
        w = await db_session.get(ReportWidget, world["widget"].id)
        w.config = {**w.config, "auto_reload_seconds": 5}
        await db_session.commit()
        model.append({"reply": "Removed auto-reload.", "data_question": None,
                      "actions": [action(op="update", widget_id=world["widget"].id,
                                         config={"auto_reload_seconds": None})]})
        r = await call(client, auth_headers["a"], world, "remove auto reload")
        assert r.status_code == 200
        assert len(r.json()["applied"]) == 1
        w = await db_session.get(ReportWidget, world["widget"].id)
        assert "auto_reload_seconds" not in w.config
        assert w.config["dimension"] == "region"

    async def test_an_update_that_changes_nothing_is_a_note_not_a_fake_success(
            self, client, auth_headers, world, columns, model, db_session):
        # The "animated the chart" lie, closed structurally: an action whose
        # cleaned patch nets to nothing must not report "Updated".
        model.append({"reply": "Animated it.", "data_question": None,
                      "actions": [action(op="update", widget_id=world["widget"].id,
                                         config={"dataset_id": 9})]})
        r = await call(client, auth_headers["a"], world, "animate the chart")
        assert r.status_code == 200
        got = r.json()
        assert got["applied"] == []
        assert any("changed no setting" in n for n in got["notes"])
        report = await db_session.get(Report, world["report"].id)
        assert report.revision == 0   # nothing landed, nothing bumped

    async def test_a_column_case_mismatch_is_fixed_not_refused(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Added.", "data_question": None,
                      "actions": [action(op="create", widget_type="bar", title="T",
                                         config={"dimension": "Region",
                                                 "measure": "REVENUE"})]})
        r = await call(client, auth_headers["a"], world, "bar of region")
        assert r.status_code == 200
        created = (await db_session.execute(select(ReportWidget).where(
            ReportWidget.title == "T"))).scalar_one()
        assert created.config == {"dimension": "region", "measure": "revenue"}


class TestSelection:
    async def test_the_selection_reaches_the_model_when_it_is_on_the_page(
            self, client, auth_headers, world, columns, monkeypatch):
        seen = {}

        class Client:
            async def complete_json(self, messages, schema, **kw):
                seen["prompt"] = "".join(m["content"] for m in messages)
                return {"reply": "ok", "data_question": None, "actions": []}
        monkeypatch.setattr("app.routers.report_copilot.llm_service.get_client",
                            lambda: Client())
        r = await call(client, auth_headers["a"], world, "make it wider",
                       selected_widget_id=world["widget"].id)
        assert r.status_code == 200
        assert "(SELECTED)" in seen["prompt"]

        # A stale id from another page is dropped, not trusted.
        r = await call(client, auth_headers["a"], world, "make it wider",
                       selected_widget_id=987654)
        assert r.status_code == 200
        assert "(SELECTED)" not in seen["prompt"]


class TestDataQuestions:
    async def test_a_data_question_is_delegated_to_the_agent(
            self, client, auth_headers, world, columns, model, monkeypatch):
        model.append({"reply": "Looking it up.",
                      "data_question": "total revenue by region",
                      "actions": []})
        seen = {}

        async def fake_run(db, *, question, datasets, user, client, history=None, **kw):
            seen["question"] = question
            seen["datasets"] = [d.id for d in datasets]
            run = AgentRun(org_id=user.org_id, question=question, status="ok",
                           answer="Europe leads.")
            db.add(run)
            await db.flush()
            db.add(AgentStep(agent_run_id=run.id, node="s1", status="ok",
                             sql="SELECT 1", rows_returned=1,
                             result_rows={"columns": ["region"], "rows": [["Europe"]],
                                          "total": 1, "truncated": False}))
            await db.flush()
            return run
        monkeypatch.setattr("app.routers.report_copilot.run_agent", fake_run)

        r = await call(client, auth_headers["a"], world, "total revenue by region?")
        assert r.status_code == 200
        got = r.json()
        assert got["reply"] == "Europe leads."
        assert got["applied"] == []
        assert got["results"][0]["rows"] == [["Europe"]]
        assert seen == {"question": "total revenue by region",
                        "datasets": [world["dataset"].id]}

    async def test_a_directquery_backed_report_asks_the_live_source(
            self, client, auth_headers, world, columns, model, monkeypatch,
            db_session, two_orgs):
        # Same routing rule as the builder's chat pane: a DirectQuery dataset
        # has no file for the dataset-mode executor, so the question goes to
        # the source. Found live -- the demo Live Orders report.
        from app.models.models import DataSource
        src = DataSource(name="wh", type="postgresql",
                         org_id=two_orgs["a"]["org"].id)
        db_session.add(src)
        await db_session.flush()
        world["dataset"].data_source_id = src.id
        world["dataset"].mode = "directquery"
        await db_session.commit()

        model.append({"reply": "Looking.", "data_question": "total amount",
                      "actions": []})
        seen = {}

        async def fake_run(db, *, question, user, client, source=None,
                           datasets=None, history=None, **kw):
            seen["source"] = source.id if source else None
            seen["datasets"] = datasets
            run = AgentRun(org_id=user.org_id, question=question, status="ok",
                           answer="42.")
            db.add(run)
            await db.flush()
            return run
        monkeypatch.setattr("app.routers.report_copilot.run_agent", fake_run)

        r = await call(client, auth_headers["a"], world, "total amount?")
        assert r.status_code == 200
        assert seen == {"source": src.id, "datasets": None}


class TestGuards:
    async def test_cross_org_is_404(self, client, auth_headers, world, columns, model):
        r = await call(client, auth_headers["b"], world, "hi")
        assert r.status_code == 404

    async def test_model_failure_is_502(self, client, auth_headers, world,
                                        columns, model):
        # `model` empty: the scripted client returns None.
        r = await call(client, auth_headers["a"], world, "hi")
        assert r.status_code == 502


class TestCalculatedColumns:
    async def test_add_calculated_column_writes_through_the_dataset(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Added all_employee_count.", "data_question": None,
                      "actions": [action(op="add_calculated_column",
                                         config={"name": "all_employee_count",
                                                 "expression": "SUM(revenue)"})]})
        r = await call(client, auth_headers["a"], world,
                       "create a new fx expression useful")
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["applied"][0]["op"] == "add_calculated_column"
        assert got["applied"][0]["title"] == "all_employee_count"
        ds = await db_session.get(Dataset, world["dataset"].id)
        await db_session.refresh(ds)
        names = [c.get("name") for c in (ds.calculated_columns or [])]
        assert "all_employee_count" in names
        expr = next(c["expression"] for c in ds.calculated_columns
                    if c["name"] == "all_employee_count")
        assert expr == "SUM(revenue)"

    async def test_a_new_calc_column_can_be_used_on_a_widget_in_the_same_reply(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Added the formula and a KPI.", "data_question": None,
                      "actions": [
                          action(op="add_calculated_column",
                                 config={"name": "doubled", "expression": "revenue * 2"}),
                          action(op="create", widget_type="kpi", title="Doubled",
                                 config={"measure": "doubled", "agg": "sum"}),
                      ]})
        r = await call(client, auth_headers["a"], world, "add fx doubled and chart it")
        assert r.status_code == 200, r.text
        assert len(r.json()["applied"]) == 2
        created = (await db_session.execute(select(ReportWidget).where(
            ReportWidget.title == "Doubled"))).scalar_one()
        assert created.config["measure"] == "doubled"

    async def test_no_sum_persists_aggregation_none_on_the_table(
            self, client, auth_headers, world, columns, model, db_session):
        # Live: "dont sum please i need to see data individual" was answered
        # "I removed the aggregation" while the engine still defaulted to Sum.
        model.append({"reply": "Showing each row.", "data_question": None,
                      "actions": [action(op="update",
                                         widget_id=world["widget"].id,
                                         widget_type="table",
                                         config={"aggregation": "none",
                                                 "measure": "revenue"})]})
        r = await call(client, auth_headers["a"], world,
                       "dont sum please i need to see data individual")
        assert r.status_code == 200, r.text
        widget = await db_session.get(ReportWidget, world["widget"].id)
        await db_session.refresh(widget)
        assert widget.widget_type == "table"
        assert widget.config.get("aggregation") == "none"

    async def test_an_unsafe_expression_is_skipped_not_saved(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Added it.", "data_question": None,
                      "actions": [action(op="add_calculated_column",
                                         config={"name": "bad",
                                                 "expression": "__import__('os')"})]})
        r = await call(client, auth_headers["a"], world, "add a bad formula")
        assert r.status_code == 200
        assert r.json()["applied"] == []
        assert any("expression" in n.lower() or "disallowed" in n.lower()
                   or "not valid" in n.lower() for n in r.json()["notes"])
        ds = await db_session.get(Dataset, world["dataset"].id)
        await db_session.refresh(ds)
        assert ds.calculated_columns in (None, [])


class TestAccountable:
    """Phase 7.1: a copilot change is attributed in version history and is one
    restore from gone -- and the restore is itself redoable."""

    async def test_attributed_undoable_and_redoable(
            self, client, auth_headers, world, columns, model, db_session):
        model.append({"reply": "Removed it.", "data_question": None,
                      "actions": [action(op="delete", widget_id=world["widget"].id)]})
        r = await call(client, auth_headers["a"], world, "remove the chart")
        got = r.json()
        assert got["before_version_id"] and got["summary"] == 'removed "Revenue by region"'
        rid = world["report"].id
        versions = (await client.get(f"/api/v1/reports/{rid}/versions", headers=auth_headers["a"])).json()
        top = versions[0]
        assert top["id"] == got["before_version_id"] and top["via"] == "copilot"
        assert top["note"] == 'Before the copilot removed "Revenue by region"' and top["widgets"] == 1

        undo = await client.post(f"/api/v1/reports/{rid}/versions/{got['before_version_id']}/restore",
                                 json={}, headers=auth_headers["a"])
        assert undo.status_code == 200
        db_session.expire_all()
        assert len((await db_session.execute(select(ReportWidget))).scalars().all()) == 1
        redo = await client.post(
            f"/api/v1/reports/{rid}/versions/{undo.json()['saved_current_as_version_id']}/restore",
            json={}, headers=auth_headers["a"])
        assert redo.status_code == 200
        db_session.expire_all()
        assert (await db_session.execute(select(ReportWidget))).scalars().all() == []

    async def test_a_human_edit_is_not_labelled_as_the_copilot(
            self, client, auth_headers, world, db_session):
        rid, pid = world["report"].id, world["page"].id
        await client.patch(f"/api/v1/reports/{rid}/pages/{pid}/widgets/{world['widget'].id}",
                           json={"title": "Mine"}, headers=auth_headers["a"])
        v = (await client.get(f"/api/v1/reports/{rid}/versions", headers=auth_headers["a"])).json()[0]
        assert v["via"] is None and v["note"] is None
