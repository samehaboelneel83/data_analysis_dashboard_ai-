"""A tile that runs server-side Python and shows what it returns.

SAS's Job content object runs code on the server and embeds the output. This is
the same feature and it is exactly as dangerous, so the honesty of the
implementation is the whole point:

  * **A subprocess, never `exec()` in the worker.** The API process holds
    database credentials and API keys in `os.environ`; running author code in it
    is not a weak sandbox, it is handing over the secrets.

  * **A scrubbed environment.** The child gets PATH and the OS essentials and
    nothing else, so a script that reads `os.environ` finds no connection
    string. This is asserted below, because it is the property most likely to
    rot silently.

  * **A timeout and a row cap**, because a tile that never returns takes a
    worker with it.

  * **This is NOT a sandbox, and the docstring says so.** The child can still
    read files the server can read and open sockets. Authoring is therefore an
    ADMIN-ONLY act, gated in the router and tested there -- the equivalent of
    handing someone a shell, which is what this feature is in every product
    that offers it.
"""
import os

import pandas as pd
import pytest

from app.services.script_tile import (MAX_CODE_CHARS, MAX_OUTPUT_ROWS,
                                      ScriptError, run_script)


@pytest.fixture
def sales():
    return pd.DataFrame({"region": ["N", "S", "N", "E"],
                         "amount": [10.0, 20.0, 30.0, 40.0]})


class TestItRunsTheScript:
    def test_a_frame_comes_back_as_columns_and_rows(self, sales):
        got = run_script(sales, "result = df.groupby('region', as_index=False)['amount'].sum()")
        assert got["columns"] == ["region", "amount"]
        assert sorted(r[0] for r in got["rows"]) == ["E", "N", "S"]

    def test_the_script_sees_the_frame_it_was_given(self, sales):
        # The frame arrives already secured by the caller: RLS, column rules and
        # filters are applied before this is ever called.
        got = run_script(sales.head(2), "result = df")
        assert len(got["rows"]) == 2

    def test_a_series_result_is_accepted(self, sales):
        got = run_script(sales, "result = df.groupby('region')['amount'].sum()")
        assert len(got["columns"]) == 2
        assert len(got["rows"]) == 3

    def test_a_scalar_result_is_accepted(self, sales):
        got = run_script(sales, "result = df['amount'].sum()")
        assert got["rows"] == [[100.0]]

    def test_printed_output_comes_back(self, sales):
        # print() is how anyone debugs a script; swallowing it makes the tile
        # unusable for the person writing it.
        got = run_script(sales, "print('checked', len(df))\nresult = df")
        assert "checked 4" in got["stdout"]

    def test_it_reports_how_long_it_took(self, sales):
        got = run_script(sales, "result = df")
        assert got["duration_ms"] >= 0


class TestTheLimits:
    def test_the_output_is_capped_and_the_cap_is_declared(self, sales):
        got = run_script(sales, f"import pandas as pd\n"
                                f"result = pd.DataFrame({{'n': range({MAX_OUTPUT_ROWS + 50})}})")
        assert len(got["rows"]) == MAX_OUTPUT_ROWS
        assert got["truncated"] is True

    def test_output_within_the_cap_is_not_flagged(self, sales):
        got = run_script(sales, "result = df")
        assert got["truncated"] is False

    def test_a_script_that_never_finishes_is_killed(self, sales):
        with pytest.raises(ScriptError) as e:
            run_script(sales, "while True:\n    pass", timeout=2)
        assert "second" in str(e.value).lower() or "time" in str(e.value).lower()

    def test_code_past_the_length_cap_is_refused(self, sales):
        with pytest.raises(ScriptError):
            run_script(sales, "result = df\n" + "# pad\n" * MAX_CODE_CHARS)

    def test_empty_code_is_refused(self, sales):
        with pytest.raises(ScriptError):
            run_script(sales, "   ")


class TestItRunsOutsideTheWorker:
    def test_the_child_cannot_read_the_server_environment(self, sales, monkeypatch):
        """THE property this design exists for. The API process holds the
        database URL and the model API keys in its environment; if the child
        inherited it, a three-line script would exfiltrate every credential."""
        monkeypatch.setenv("DATALYTICS_FAKE_SECRET", "hunter2")
        got = run_script(sales,
                         "import os\nresult = os.environ.get('DATALYTICS_FAKE_SECRET', 'absent')")
        assert got["rows"] == [["absent"]]

    def test_a_script_cannot_change_this_process(self, sales):
        run_script(sales, "import os\nos.environ['DATALYTICS_CHILD_ONLY'] = 'x'\nresult = df")
        assert "DATALYTICS_CHILD_ONLY" not in os.environ

    def test_a_script_cannot_alter_the_frame_the_caller_holds(self, sales):
        run_script(sales, "df['amount'] = 0\nresult = df")
        assert list(sales["amount"]) == [10.0, 20.0, 30.0, 40.0]


class TestItFailsUsefully:
    def test_a_syntax_error_names_the_line(self, sales):
        with pytest.raises(ScriptError) as e:
            run_script(sales, "result = (df")
        assert "syntax" in str(e.value).lower()

    def test_a_runtime_error_comes_back_as_the_message(self, sales):
        with pytest.raises(ScriptError) as e:
            run_script(sales, "result = df['nope']")
        assert "nope" in str(e.value)

    def test_a_script_that_sets_no_result_is_told_what_is_missing(self, sales):
        with pytest.raises(ScriptError) as e:
            run_script(sales, "x = df.sum()")
        assert "result" in str(e.value)

    def test_a_result_that_is_not_tabular_is_refused(self, sales):
        with pytest.raises(ScriptError) as e:
            run_script(sales, "result = {'a': object()}")
        assert "result" in str(e.value).lower()


class TestTheShaper:
    """The widget-data half. `run_script` being right says nothing about
    whether a tile on a dashboard reaches it -- which is how three features in
    this codebase shipped with no caller."""

    def test_the_widget_type_is_dispatched(self):
        from app.services.widget_data import SHAPERS
        assert "script" in SHAPERS

    def test_it_returns_what_the_script_produced(self, sales):
        from app.services.widget_data import shape_script
        got = shape_script(sales, {"code": "result = df['amount'].sum()"})
        assert got["rows"] == [[100.0]]

    def test_the_widget_filters_are_applied_before_the_script_sees_the_frame(self, sales):
        # A filtered tile that runs over the unfiltered frame would silently
        # ignore every slicer and page prompt on the dashboard.
        from app.services.widget_data import shape_script
        got = shape_script(sales, {
            "code": "result = df['amount'].sum()",
            "filters": [{"column": "region", "op": "eq", "value": "N"}]})
        assert got["rows"] == [[40.0]]

    def test_a_failing_script_reports_the_error_in_the_tile(self, sales):
        # Not an exception: the person looking at this is usually the person
        # who wrote it, and the message is the whole point.
        from app.services.widget_data import shape_script
        got = shape_script(sales, {"code": "result = df['nope']"})
        assert got["error"] and "nope" in got["error"]
        assert got["rows"] == []

    def test_a_tile_with_no_code_says_so_rather_than_failing(self, sales):
        from app.services.widget_data import shape_script
        got = shape_script(sales, {})
        assert got["error"]


# ── Who may write one ────────────────────────────────────────────────────────
#
# A script tile is a shell. The execution model keeps credentials out of the
# child and stops a runaway one, but it does not stop the code from doing
# whatever the server user can do -- so the only honest gate is on WHO may
# author one. Admins write them; everyone else runs what an admin wrote, which
# is the same trust model as a saved SQL view.

async def _report_with_page(db_session, client, headers, org_id, tmp_path):
    from app.models.models import Dataset, Report
    path = tmp_path / "s.csv"
    pd.DataFrame([{"region": "East", "sales": 1}]).to_csv(path, index=False)
    ds = Dataset(name="ds", filename=str(path), org_id=org_id, row_count=1, col_count=2)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    report = Report(name="R", dataset_id=ds.id, org_id=org_id)
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    page = (await client.post(f"/api/v1/reports/{report.id}/pages",
                              json={"name": "P", "position": 0}, headers=headers)).json()
    return report, page


async def _member_headers(db_session, org_id, report_id=None):
    """A signed-in user of the same org whose role is NOT an org admin.

    Given a report, the role is granted EDIT on it -- otherwise every refusal
    below would be the ordinary view-level one, and the tests would pass
    without the script gate existing at all."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User as UserModel
    role = Role(name="Analyst", org_id=org_id, is_org_admin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    user = UserModel(email="analyst@example.com", password_hash=hash_password("x"),
                     org_id=org_id, role_id=role.id, is_active=True)
    db_session.add(user)
    if report_id is not None:
        from app.models.models import ReportCapability
        db_session.add(ReportCapability(report_id=report_id, role_id=role.id, level="edit"))
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


class TestOnlyAnAdminMayAuthorOne:
    async def test_an_admin_can_create_a_script_tile(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        report, page = await _report_with_page(
            db_session, client, auth_headers["a"], two_orgs["a"]["org"].id, tmp_path)
        r = await client.post(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets",
            json={"widget_type": "script", "title": "Script",
                  "config": {"code": "result = df"},
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=auth_headers["a"])
        assert r.status_code == 201, r.text

    async def test_a_non_admin_cannot_create_one(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        report, page = await _report_with_page(
            db_session, client, auth_headers["a"], two_orgs["a"]["org"].id, tmp_path)
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        r = await client.post(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets",
            json={"widget_type": "script", "title": "Script",
                  "config": {"code": "import os; result = os.listdir('/')"},
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=member)
        assert r.status_code == 403
        assert "admin" in r.json()["detail"].lower()

    async def test_a_non_admin_cannot_edit_the_code_of_an_existing_one(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        """The half that would be easy to miss: gating creation alone leaves an
        admin-made tile as a writable place to put anything."""
        report, page = await _report_with_page(
            db_session, client, auth_headers["a"], two_orgs["a"]["org"].id, tmp_path)
        widget = (await client.post(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets",
            json={"widget_type": "script", "title": "Script",
                  "config": {"code": "result = df"},
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=auth_headers["a"])).json()
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        r = await client.patch(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets/{widget['id']}",
            json={"config": {"code": "result = open('/etc/passwd').read()"}},
            headers=member)
        assert r.status_code == 403

    async def test_a_non_admin_may_still_build_an_ordinary_widget(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        # The gate must be about running code, not about editing reports.
        report, page = await _report_with_page(
            db_session, client, auth_headers["a"], two_orgs["a"]["org"].id, tmp_path)
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        r = await client.post(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets",
            json={"widget_type": "bar", "title": "W", "config": {},
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=member)
        assert r.status_code == 201, r.text

    async def test_a_non_admin_may_move_a_script_tile_without_touching_its_code(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        report, page = await _report_with_page(
            db_session, client, auth_headers["a"], two_orgs["a"]["org"].id, tmp_path)
        widget = (await client.post(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets",
            json={"widget_type": "script", "title": "Script",
                  "config": {"code": "result = df"},
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=auth_headers["a"])).json()
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        r = await client.patch(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets/{widget['id']}",
            json={"layout": {"x": 1, "y": 1, "w": 6, "h": 5}}, headers=member)
        assert r.status_code == 200, r.text


class TestOverTheWire:
    """The route in between. `shape_script` being right and the tile rendering
    right say nothing about whether `POST /widget-data` will carry a script
    widget -- which is the seam features in this codebase have died at before."""

    async def test_a_script_tile_fetches_its_data_like_any_other_widget(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        from app.models.models import Dataset, DatasetColumn
        path = tmp_path / "w.csv"
        pd.DataFrame({"region": ["N", "S", "N"], "amount": [1.0, 2.0, 3.0]}).to_csv(path, index=False)
        ds = Dataset(name="W", filename=str(path), org_id=two_orgs["a"]["org"].id,
                     mode="import", row_count=3, col_count=2)
        db_session.add(ds)
        await db_session.flush()
        for name, dtype in (("region", "categorical"), ("amount", "numeric")):
            db_session.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
        await db_session.commit()

        r = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "script",
                  "config": {"code": "result = df.groupby('region', as_index=False)['amount'].sum()"}},
            headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["columns"] == ["region", "amount"]
        assert sorted(row[0] for row in body["rows"]) == ["N", "S"]


class TestOnlySavedCodeRunsForNonAdmins:
    """The authoring gate says who may WRITE a script tile; /widget-data takes
    the type and config from the caller. Without a gate there too, a member
    could post their own code and run it as the server user."""

    async def _saved_tile(self, db_session, client, headers, org_id, tmp_path, code):
        report, page = await _report_with_page(db_session, client, headers, org_id, tmp_path)
        r = await client.post(
            f"/api/v1/reports/{report.id}/pages/{page['id']}/widgets",
            json={"widget_type": "script", "title": "Script", "config": {"code": code},
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=headers)
        assert r.status_code == 201, r.text
        return report

    async def test_a_non_admin_cannot_run_their_own_code(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        report = await self._saved_tile(db_session, client, auth_headers["a"],
                                        two_orgs["a"]["org"].id, tmp_path, "result = df")
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        for path in ("widget-data", "widget-data/export?format=csv"):
            r = await client.post(
                f"/api/v1/datasets/{report.dataset_id}/{path}",
                json={"widget_type": "script", "report_id": report.id,
                      "config": {"code": "import os; result = os.listdir('/')"}},
                headers=member)
            assert r.status_code == 403, (path, r.text)
            assert "admin" in r.json()["detail"].lower()

    async def test_a_non_admin_can_run_a_tile_an_admin_saved(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        code = "result = df[['region']]"
        report = await self._saved_tile(db_session, client, auth_headers["a"],
                                        two_orgs["a"]["org"].id, tmp_path, code)
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        r = await client.post(
            f"/api/v1/datasets/{report.dataset_id}/widget-data",
            json={"widget_type": "script", "report_id": report.id, "config": {"code": code}},
            headers=member)
        assert r.status_code == 200, r.text
        assert r.json()["columns"] == ["region"]

    async def test_code_saved_in_another_org_does_not_count(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        code = "result = df[['sales']]"
        other = tmp_path / "b"
        other.mkdir()
        await self._saved_tile(db_session, client, auth_headers["b"],
                               two_orgs["b"]["org"].id, other, code)
        report, _ = await _report_with_page(db_session, client, auth_headers["a"],
                                            two_orgs["a"]["org"].id, tmp_path)
        member = await _member_headers(db_session, two_orgs["a"]["org"].id, report.id)
        r = await client.post(
            f"/api/v1/datasets/{report.dataset_id}/widget-data",
            json={"widget_type": "script", "report_id": report.id, "config": {"code": code}},
            headers=member)
        assert r.status_code == 403, r.text


class TestTheInputIsDeclaredToo:
    """Output truncation was flagged from the start; the INPUT cap was silent.
    A script summing a column over the first 200,000 of 900,000 rows returns a
    number that is simply wrong, and nothing on screen said so."""

    def test_a_frame_within_the_cap_is_not_flagged(self, sales):
        got = run_script(sales, "result = df")
        assert got["input_truncated"] is False
        assert got["rows_in"] == 4

    def test_the_script_is_told_how_many_rows_it_saw(self, sales):
        got = run_script(sales, "result = len(df)")
        assert got["rows_in"] == got["rows"][0][0]

    def test_a_frame_over_the_cap_is_flagged(self, monkeypatch, sales):
        # Monkeypatched rather than built: a 200,001-row frame in a unit test
        # costs seconds on every run to prove arithmetic.
        import app.services.script_tile as tile
        monkeypatch.setattr(tile, "MAX_INPUT_ROWS", 2)
        got = tile.run_script(sales, "result = len(df)")
        assert got["input_truncated"] is True
        assert got["rows_in"] == 2
        assert got["rows"][0][0] == 2
