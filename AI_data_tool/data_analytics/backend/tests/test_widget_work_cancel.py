"""E14: work a closed page no longer needs is not done.

Widget queries wait for one of a few work slots. A request whose reader
left while it waited (the page closed, a filter changed) is dropped without
running, so the slots go to the people still reading.
"""
import asyncio
import threading

import pytest

from app.routers import widget_data as wd
from app.services.error_codes import WIDGET_ERROR_CODES


class FakeRequest:
    """The ASGI side of a connection: after the body, `receive` waits until
    the client goes and then says so."""
    def __init__(self, gone_after: float | None = None):
        self._gone_after = gone_after

    async def receive(self) -> dict:
        if self._gone_after is None:
            await asyncio.Event().wait()           # never leaves
        await asyncio.sleep(self._gone_after)
        return {"type": "http.disconnect"}


def _slow(ran: list, release: threading.Event):
    def fn(tag):
        ran.append(tag)
        release.wait(5)
        return tag
    return fn


async def _fill_gate():
    gate = wd._work_gate()
    held = 0
    while not gate.locked():
        await gate.acquire()
        held += 1
    return gate, held


async def test_a_request_whose_reader_left_while_queued_never_runs():
    gate, held = await _fill_gate()
    ran: list = []
    before = wd.abandoned_before_start
    with pytest.raises(Exception) as err:
        await wd._run_gated(FakeRequest(gone_after=0.05), lambda: ran.append("x"))
    assert err.value.status_code == 499 and err.value.code == "client_closed"
    assert ran == [] and wd.abandoned_before_start == before + 1
    # The slot it never took is still there for the next reader.
    for _ in range(held):
        gate.release()
    assert await wd._run_gated(FakeRequest(), lambda: "served") == "served"


async def test_a_reader_still_there_is_served_when_a_slot_frees():
    gate, held = await _fill_gate()
    waiting = asyncio.ensure_future(wd._run_gated(FakeRequest(), lambda: "served"))
    await asyncio.sleep(0.05)
    assert not waiting.done()
    gate.release()
    assert await waiting == "served"
    for _ in range(held - 1):
        gate.release()


async def test_dropping_queued_work_frees_the_queue_for_others():
    """Three readers queue behind a busy slot; two leave. When the slot
    frees, the one who stayed runs next, not after the two who left."""
    gate, held = await _fill_gate()
    ran: list = []
    left = [asyncio.ensure_future(wd._run_gated(FakeRequest(gone_after=0.03), ran.append, f"left{i}"))
            for i in range(2)]
    stayed = asyncio.ensure_future(wd._run_gated(FakeRequest(), ran.append, "stayed"))
    await asyncio.sleep(0.1)
    assert all(t.done() for t in left)
    gate.release()
    await stayed
    assert ran == ["stayed"]
    for _ in range(held - 1):
        gate.release()


async def test_work_already_running_finishes_and_keeps_its_slot():
    """A pandas pipeline cannot be stopped from outside its thread: the slot
    stays taken until it ends, so the gate still bounds real work."""
    ran: list = []
    release = threading.Event()
    gate = wd._work_gate()
    free_before = gate._value
    task = asyncio.ensure_future(wd._run_gated(FakeRequest(gone_after=0.02), _slow(ran, release), "running"))
    await asyncio.sleep(0.1)
    assert ran == ["running"] and gate._value == free_before - 1
    release.set()
    assert await task == "running"
    assert gate._value == free_before


async def test_without_a_request_the_work_always_runs():
    """Exports and background renders have no page to leave."""
    gate, held = await _fill_gate()
    task = asyncio.ensure_future(wd._run_gated(None, lambda: "exported"))
    await asyncio.sleep(0.05)
    gate.release()
    assert await task == "exported"
    for _ in range(held - 1):
        gate.release()


async def test_a_request_cancelled_while_queued_does_not_keep_a_slot():
    """The request task itself cancelled (the server shutting it down): the
    wait it abandoned must not end up holding a slot nobody releases."""
    gate, held = await _fill_gate()
    task = asyncio.ensure_future(wd._run_gated(FakeRequest(), lambda: "never"))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for _ in range(held):
        gate.release()
    await asyncio.sleep(0)
    assert gate._value == held


def test_the_code_is_documented():
    assert "client_closed" in WIDGET_ERROR_CODES


async def test_the_route_serves_a_connected_reader(client, auth_headers, db_session, two_orgs, tmp_path):
    """Through the real route: a test client never disconnects, so this is
    the ordinary path, and it must still answer."""
    import pandas as pd
    from app.models.models import Dataset
    path = tmp_path / "s.csv"
    pd.DataFrame({"region": ["a", "b", "a"], "sales": [1, 2, 3]}).to_csv(path, index=False)
    ds = Dataset(name="S", filename=str(path), row_count=3, col_count=2, file_size=1,
                 org_id=two_orgs["a"]["org"].id, created_by=two_orgs["a"]["user"].id)
    db_session.add(ds)
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", headers=auth_headers["a"],
                          json={"widget_type": "bar", "config": {"dimension": "region", "measure": "sales"}})
    assert r.status_code == 200, r.text
    assert {row["name"]: row["value"] for row in r.json()["rows"]} == {"a": 4, "b": 2}
