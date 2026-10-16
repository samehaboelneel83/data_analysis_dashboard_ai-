"""No background task a request starts may outlive its test.

POST /data-sources/{id}/sync detaches the sync (`asyncio.create_task`) on the
app's OWN session factory, not the test's in-memory database. On a machine
where the configured Postgres is reachable that task kept running after the
test ended; its event loop closed under it, and when the garbage collector
finally destroyed it -- in whichever test happened to be running -- the
`GeneratorExit` it raised failed THAT test (seen 2026-10-15: test_dataflow_
permissions failed once in a full run, "Task was destroyed but it is pending!
coro=<run_metered()>", and passed alone).

The `client` fixture now cancels every task started during the test before
the loop closes (tests/_task_guard.py).
"""
import asyncio

from app.models.models import DataSource
from tests._task_guard import cancel_tasks_started_since


async def test_a_sync_detached_by_a_request_is_cancelled_at_the_end(client, auth_headers,
                                                                   db_session, two_orgs):
    src = DataSource(name="wh", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    before = set(asyncio.all_tasks())

    r = await client.post(f"/api/v1/data-sources/{src.id}/sync", headers=auth_headers["a"])
    assert r.status_code == 200
    started = [t for t in asyncio.all_tasks() - before]

    await cancel_tasks_started_since(before)

    assert all(t.done() for t in started)
    assert not [t for t in asyncio.all_tasks() - before if not t.done()]


async def test_the_guard_leaves_tasks_that_were_already_running():
    keep = asyncio.create_task(asyncio.sleep(30))
    before = set(asyncio.all_tasks())
    new = asyncio.create_task(asyncio.sleep(30))

    cancelled = await cancel_tasks_started_since(before)

    assert new.cancelled() and cancelled == 1
    assert not keep.done()
    keep.cancel()
