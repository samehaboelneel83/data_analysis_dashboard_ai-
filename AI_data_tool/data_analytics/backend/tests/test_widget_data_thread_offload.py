"""The widget-data hot path runs via asyncio.to_thread: same payloads, same
error mapping, just off the event loop. These tests pin the equivalence and
the exception plumbing across the thread hop."""
import pandas as pd

from app.core.security import create_access_token
from app.models.models import DataSource, Dataset
from app.services.widget_data import get_widget_data

ROWS = [
    {"region": "North", "sales": 100.0},
    {"region": "South", "sales": 200.0},
    {"region": "North", "sales": 50.0},
]


async def _seed(db_session, tmp_path, org_id):
    csv_path = tmp_path / "offload.csv"
    pd.DataFrame(ROWS).to_csv(csv_path, index=False)
    ds = Dataset(name="Offload", org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_router_payload_identical_to_direct_call(client, db_session, two_orgs, auth_headers, tmp_path):
    """The to_thread hop must be invisible: the HTTP payload equals a direct
    get_widget_data call on the same file and config, byte for byte."""
    ds = await _seed(db_session, tmp_path, two_orgs["a"]["org"].id)
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": config, "widget_type": "bar"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200
    direct = get_widget_data(ds.filename, config, widget_type="bar", use_cache=False)
    assert resp.json() == direct


async def test_missing_file_still_maps_to_404_through_the_thread(client, db_session, two_orgs, auth_headers, tmp_path):
    """FileNotFoundError raised inside the worker thread must still surface as
    the router's 404, proving exceptions propagate through to_thread."""
    ds = Dataset(name="Gone", org_id=two_orgs["a"]["org"].id, filename=str(tmp_path / "never_written.csv"))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "x"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 404
    assert "re-upload" in resp.json()["detail"]


async def test_directquery_unsupported_still_maps_to_400(client, db_session, two_orgs, auth_headers):
    """DirectQueryUnsupported raised in the thread keeps its 400 mapping.

    The example had to change with the behaviour. A sankey is no longer refused:
    SQL cannot express it, so DirectQuery fetches the rows and hands them to the
    same shaper import mode uses -- "not pushdown-capable" stopped meaning "not
    available". What still raises is a source whose DIALECT DirectQuery cannot
    speak, because there is then no connection to fall back to either, and that
    is what this pins: the MAPPING from the exception to a 400, not the
    particular widget that once triggered it."""
    org_id = two_orgs["a"]["org"].id
    # A dialect DirectQuery has no pushdown OR fetch path for.
    src = DataSource(org_id=org_id, name="db", type="mongodb", config={"uri": "mongodb://x"})
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="DQ", org_id=org_id, mode="directquery",
                 data_source_id=src.id, source_table="t")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"source": "a", "target": "b", "measure": "v"}, "widget_type": "sankey"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 400
