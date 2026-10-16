"""UAT-3 (16 Oct 2026): a widget naming a column the reader's role cannot see
is refused the same way on every path.

The analyst (column rule hiding `salary`) saw on the bar "Avg salary by
department" HTTP 200 with "'salary' is not a column or measure on this
dataset", while a KPI over a measure built on a hidden column got 403
`forbidden_column` and the UI's friendly lock (E-12). Now the column named
directly gets that same 403 wherever the widget cannot be drawn without it
(bar, KPI, crosstab), and the body names nothing. A table or embed listing
several columns still just leaves the hidden one out, as designed.
"""
import pytest

from tests.test_column_security import _setup, salary_ds  # noqa: F401  (fixture)

FORBIDDEN = "This widget references a column your role cannot access"


async def _post(client, ds, headers, widget_type, config):
    return await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                             json={"widget_type": widget_type, "config": config}, headers=headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("widget_type,config", [
    ("bar", {"dimension": "dept", "measure": "salary", "aggregation": "avg"}),
    ("kpi", {"measure": "salary", "aggregation": "sum"}),
    ("line", {"dimension": "dept", "measure": "salary", "aggregation": "avg"}),
    ("bar", {"dimension": "salary", "measure": "headcount", "aggregation": "sum"}),
    ("crosstab", {"dimension": "dept", "dimension2": "headcount", "measure": "salary", "aggregation": "avg"}),
    ("matrix", {"dimension": "dept", "rows_extra": ["headcount"], "measure": "salary", "aggregation": "avg"}),
])
async def test_a_hidden_column_is_refused_like_the_kpi_path(client, db_session, two_orgs, salary_ds,  # noqa: F811
                                                            widget_type, config):
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await _post(client, ds, headers, widget_type, config)
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["code"] == "forbidden_column"
    assert body["detail"] == FORBIDDEN
    assert "90000" not in r.text and "not a column" not in r.text


@pytest.mark.asyncio
async def test_same_answer_as_a_measure_over_the_hidden_column(client, db_session, two_orgs, salary_ds):  # noqa: F811
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    ds.measures = [{"name": "Pay", "expression": "SUM(salary)"}]
    await db_session.commit()
    kpi = await _post(client, ds, headers, "kpi", {"measure": "Pay"})
    bar = await _post(client, ds, headers, "bar", {"dimension": "dept", "measure": "salary", "aggregation": "avg"})
    assert (kpi.status_code, kpi.json()) == (bar.status_code, bar.json())


@pytest.mark.asyncio
async def test_allowed_columns_and_the_admin_are_unaffected(client, auth_headers, db_session, two_orgs, salary_ds):  # noqa: F811
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await _post(client, ds, headers, "bar", {"dimension": "dept", "measure": "headcount", "aggregation": "sum"})
    assert r.status_code == 200
    r = await _post(client, ds, auth_headers["a"], "bar", {"dimension": "dept", "measure": "salary", "aggregation": "avg"})
    assert r.status_code == 200 and len(r.json()["rows"]) == 2


@pytest.mark.asyncio
async def test_a_table_still_just_leaves_the_hidden_column_out(client, db_session, two_orgs, salary_ds):  # noqa: F811
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await _post(client, ds, headers, "table", {"columns": ["dept", "salary"]})
    assert r.status_code == 200, r.text
    assert "90000" not in r.text and "salary" not in str(r.json().get("columns", []))
