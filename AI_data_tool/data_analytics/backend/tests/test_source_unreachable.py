"""What a reader sees when the customer's database is down.

A DirectQuery dataset queries its source on every render. When that source is
unreachable — the database is down, the network is cut, a firewall changed —
the failure is not a bug in this application, and the error has to say so.

Today it does not. Only `DirectQueryUnsupported` is caught in the widget path,
so a driver-level `OperationalError` escapes to the generic handler and the
reader gets "Internal server error. See server logs for details." on their
widget. That sends them to OUR logs for an outage in THEIR database.

Two properties, and the second is why the generic handler exists at all:

  * The message names the source and says it could not be reached, so the
    person reading it knows where to look.
  * The message never carries the driver's text. A connection error embeds the
    DSN, and a DSN embeds the password — `/health/ready` already refuses to
    quote exception text for exactly this reason.
"""
import pandas as pd
import pytest

from app.models.models import DataSource, Dataset, DatasetColumn


SECRET = "sup3rs3cret-pw"


@pytest.fixture
def dq_dataset():
    """A DirectQuery dataset whose source DSN carries a password."""
    async def _make(db, org):
        src = DataSource(
            name="Warehouse", type="postgresql", org_id=org.id,
            config={"host": "db.internal", "port": 5432, "database": "sales",
                    "user": "reader", "password": SECRET},
        )
        db.add(src)
        await db.flush()
        ds = Dataset(name="Live Orders", org_id=org.id, mode="directquery",
                     data_source_id=src.id, source_table="orders")
        db.add(ds)
        await db.flush()
        for c in ("region", "amount"):
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db.commit()
        await db.refresh(ds)
        return ds
    return _make


def _explode(monkeypatch):
    """The source is unreachable, exactly as the driver reports it."""
    from sqlalchemy.exc import OperationalError

    def _boom(*a, **kw):
        raise OperationalError(
            f"(psycopg2.OperationalError) connection to server at "
            f"db.internal failed: password authentication failed "
            f"for user 'reader' (dsn: postgresql://reader:{SECRET}@db.internal/sales)",
            {}, Exception("unreachable"))

    # Patched INSIDE the wrapper, so the wrapper itself is what runs.
    #
    # Two wrong seams were tried first. Patching the service-module name does
    # nothing, because `routers/widget_data.py` does `from
    # ..services.direct_query import run_direct_query` and binds the object at
    # import time -- these tests passed that way for a while, but only because
    # the fixture host `db.internal` does not resolve, so the REAL call failed
    # with OperationalError and produced the 502 being asserted. Right answer,
    # wrong reason, and blind to the difference between an unreachable source
    # and a bad query. Patching the ROUTER name instead replaces the wrapper
    # under test, so nothing translates and everything becomes a 500.
    #
    # The inner function is looked up as a module global at call time, which
    # makes it the one seam where the translation still happens.
    monkeypatch.setattr(
        "app.services.direct_query._run_direct_query_inner", _boom)


@pytest.mark.asyncio
async def test_a_widget_says_the_source_could_not_be_reached(
        client, auth_headers, db_session, two_orgs, dq_dataset, monkeypatch):
    ds = await dq_dataset(db_session, two_orgs["a"]["org"])
    _explode(monkeypatch)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json={
        "widget_type": "bar",
        "config": {"dimension": "region", "measure": "amount", "aggregation": "sum"},
        "calculated_columns": [], "parameters": {},
    }, headers=auth_headers["a"])

    assert resp.status_code == 502, resp.text
    body = resp.text.lower()
    # Names the source, so the reader knows whose outage this is.
    assert "warehouse" in body or "source" in body
    assert "internal server error" not in body


@pytest.mark.asyncio
async def test_the_error_never_carries_the_connection_string(
        client, auth_headers, db_session, two_orgs, dq_dataset, monkeypatch):
    """The reason the generic handler quotes nothing.

    A driver's connection error embeds the DSN, and the DSN embeds the
    password. `/health/ready` already refuses to quote exception text for this
    reason; a widget is seen by far more people."""
    ds = await dq_dataset(db_session, two_orgs["a"]["org"])
    _explode(monkeypatch)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json={
        "widget_type": "bar",
        "config": {"dimension": "region", "measure": "amount", "aggregation": "sum"},
        "calculated_columns": [], "parameters": {},
    }, headers=auth_headers["a"])

    assert SECRET not in resp.text
    assert "psycopg2" not in resp.text
    assert "dsn" not in resp.text.lower()


@pytest.mark.asyncio
async def test_an_import_dataset_is_unaffected_by_a_dead_source(
        client, auth_headers, db_session, two_orgs, tmp_path, monkeypatch):
    """One dependency failing must not break what does not depend on it.

    An import-mode dataset reads a file on this server; somebody else's
    database being down is none of its business."""
    _explode(monkeypatch)
    path = tmp_path / "s.csv"
    pd.DataFrame({"region": ["N", "S"], "amount": [1.0, 2.0]}).to_csv(path, index=False)
    ds = Dataset(name="Imported", filename=str(path),
                 org_id=two_orgs["a"]["org"].id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for c in ("region", "amount"):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db_session.commit()
    await db_session.refresh(ds)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json={
        "widget_type": "bar",
        "config": {"dimension": "region", "measure": "amount", "aggregation": "sum"},
        "calculated_columns": [], "parameters": {},
    }, headers=auth_headers["a"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["rows"]


def _bad_table(monkeypatch):
    """The source is perfectly reachable; the QUERY is wrong.

    A table renamed or dropped on the customer side, which is an ordinary
    thing to happen to a DirectQuery dataset."""
    from sqlalchemy.exc import ProgrammingError

    def _boom(*a, **kw):
        raise ProgrammingError(
            'SELECT "region" FROM "orders"', {},
            Exception('relation "orders" does not exist'))

    # Patched INSIDE the wrapper, so the wrapper itself is what runs.
    #
    # Two wrong seams were tried first. Patching the service-module name does
    # nothing, because `routers/widget_data.py` does `from
    # ..services.direct_query import run_direct_query` and binds the object at
    # import time -- these tests passed that way for a while, but only because
    # the fixture host `db.internal` does not resolve, so the REAL call failed
    # with OperationalError and produced the 502 being asserted. Right answer,
    # wrong reason, and blind to the difference between an unreachable source
    # and a bad query. Patching the ROUTER name instead replaces the wrapper
    # under test, so nothing translates and everything becomes a 500.
    #
    # The inner function is looked up as a module global at call time, which
    # makes it the one seam where the translation still happens.
    monkeypatch.setattr(
        "app.services.direct_query._run_direct_query_inner", _boom)


@pytest.mark.asyncio
async def test_a_bad_query_is_not_blamed_on_the_source(
        client, auth_headers, db_session, two_orgs, dq_dataset, monkeypatch):
    """The wrapper docstring promises only DRIVER-level failures are caught.

    `DBAPIError` is the PARENT of ProgrammingError, DataError and
    IntegrityError, so catching it swept up every SQL fault as well: a renamed
    table told the reader their database could not be reached, and they would
    go and check a database that was answering perfectly.

    Found while benchmarking DirectQuery -- a mistyped schema in the bench
    script came back as "could not reach the data source".

    A query fault is ours or the schema changing, so it keeps the behaviour it
    had before SourceUnavailable existed rather than acquiring a comfortable
    explanation that points at somebody else."""
    ds = await dq_dataset(db_session, two_orgs["a"]["org"])
    _bad_table(monkeypatch)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json={
        "widget_type": "bar",
        "config": {"dimension": "region", "measure": "amount", "aggregation": "sum"},
        "calculated_columns": [], "parameters": {},
    }, headers=auth_headers["a"])

    assert resp.status_code != 502, (
        "a query fault was reported as an unreachable source")
    assert "could not be reached" not in resp.text.lower()


@pytest.mark.asyncio
async def test_liveness_stays_up_while_a_source_is_down(client, monkeypatch):
    """A customer database outage is not this process failing.

    Liveness must not follow it, or an orchestrator restarts every replica over
    somebody else's network."""
    _explode(monkeypatch)
    assert (await client.get("/health")).status_code == 200
