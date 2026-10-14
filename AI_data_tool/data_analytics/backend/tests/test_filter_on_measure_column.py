"""A filter on the very column a chart sums must filter the ROWS, not the totals.

Dashboard 213: "price between 100 and 200" on a line of SUM(price) by month
kept only the months whose TOTAL fell between 100 and 200 (1 of 25), because
the grouped result was filtered a second time after the SQL had filtered it.
"""
import pytest
from tests.test_auto_bin import _dq_ds, _import_ds, _post, sqlite_orders, ordersfile, engine  # noqa: F401

FILTERS = [{"column": "price", "op": "gte", "value": 100}, {"column": "price", "op": "lte", "value": 200}]


def _expected(df):
    sel = df[(df["price"] >= 100) & (df["price"] <= 200)]
    by_month = sel.groupby(sel["d"].dt.strftime("%Y-%m"))["price"].sum()
    return {k: round(float(v), 2) for k, v in by_month.items()}


@pytest.mark.parametrize("grain", [{"dimension_granularity": "month"}, {}], ids=["author-month", "auto"])
async def test_live_source(client, db_session, two_orgs, auth_headers, sqlite_orders, grain):  # noqa: F811
    db_path, df = sqlite_orders
    ds = await _dq_ds(db_session, two_orgs["a"]["org"], db_path)
    out = await _post(client, auth_headers, ds.id, "bar",
                      {"dimension": "d", "measure": "price", "aggregation": "sum",
                       "dimension_granularity": "month", "filters": FILTERS, **grain})
    got = {r["name"]: round(float(r["value"]), 2) for r in out["rows"]}
    assert got == _expected(df)


async def test_uploaded_file(client, db_session, two_orgs, auth_headers, ordersfile, engine):  # noqa: F811
    path, df = ordersfile
    ds = await _import_ds(db_session, two_orgs["a"]["org"], path)
    out = await _post(client, auth_headers, ds.id, "line",
                      {"dimension": "d", "measure": "price", "aggregation": "sum",
                       "dimension_granularity": "month", "filters": FILTERS})
    # A time axis may list the empty months too (a line fills its gaps); only
    # the months with rows carry a value.
    got = {r["name"]: round(float(r["value"]), 2) for r in out["rows"] if r["value"] not in (None, 0)}
    assert got == _expected(df)


async def test_live_source_without_a_grain(client, db_session, two_orgs, auth_headers, sqlite_orders):  # noqa: F811
    db_path, df = sqlite_orders
    ds = await _dq_ds(db_session, two_orgs["a"]["org"], db_path)
    out = await _post(client, auth_headers, ds.id, "bar",
                      {"dimension": "status", "measure": "price", "aggregation": "sum", "filters": FILTERS})
    sel = df[(df["price"] >= 100) & (df["price"] <= 200)]
    want = {k: round(float(v), 2) for k, v in sel.groupby("status")["price"].sum().items()}
    assert {r["name"]: round(float(r["value"]), 2) for r in out["rows"]} == want
