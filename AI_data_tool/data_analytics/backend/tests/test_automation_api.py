"""E12: automated analysis runs, started, watched and answered from the product.

The runner could profile, describe, scan, propose, review, compose and notify
-- resumable, backed off, held for a person when review says no -- but no
endpoint could start a run, show one, or answer one, and a held run's
notification linked nowhere. These pin routers/automation.py: who may start,
see and answer a run; one unfinished run per dataset; cancel that the runner
respects; retry that skips the backoff; and the held run's link.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select, update

from app.core.security import create_access_token, hash_password
from app.models.models import (AuditLogEntry, AutomationRun, AutomationStep, Dataset, DatasetShare,
                               Role, User)
from app.services import automation_runner as runner


@pytest.fixture
def csv(tmp_path):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["North", "South", "East"] * 10,
                  "revenue": [float(i) for i in range(30)]}).to_csv(p, index=False)
    return str(p)


@pytest.fixture
async def world(client, db_session, two_orgs, auth_headers, csv):
    org = two_orgs["a"]["org"]
    ds = Dataset(name="Sales", filename=csv, org_id=org.id, mode="import",
                 created_by=two_orgs["a"]["user"].id)
    db_session.add(ds)
    role = Role(org_id=org.id, name="member", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    people = {}
    for who in ("ana", "ben"):
        u = User(org_id=org.id, role_id=role.id, email=f"{who}@example.com",
                 password_hash=hash_password("pw"), is_active=True)
        db_session.add(u)
        await db_session.flush()
        people[who] = {"Authorization": f"Bearer {create_access_token(u.id, org.id)}"}
        # Both may read the dataset: a member sees a dataset shared with them.
        db_session.add(DatasetShare(dataset_id=ds.id, user_id=u.id))
    await db_session.commit()
    return {"c": client, "ds": ds, "admin": auth_headers["a"], "other_org": auth_headers["b"], **people}


async def _start(w, who="ana", ds_id=None):
    return await w["c"].post("/api/v1/automation/runs", json={"dataset_id": ds_id or w["ds"].id},
                             headers=w[who])


async def _set_status(db_session, run_id, status):
    await db_session.execute(update(AutomationRun).where(AutomationRun.id == run_id).values(status=status))
    await db_session.commit()


class TestStarting:
    async def test_starting_lays_down_the_seven_steps_as_the_caller(self, world, db_session):
        r = await _start(world)
        assert r.status_code == 201, r.text
        run = r.json()
        assert run["status"] == "pending" and run["dataset"] == {"id": world["ds"].id, "name": "Sales"}
        assert [s["name"] for s in run["steps"]] == ["profile", "describe", "scan", "propose",
                                                     "review", "compose", "notify"]
        assert all(s["status"] == "pending" and s["label"] for s in run["steps"])
        row = await db_session.get(AutomationRun, run["id"])
        ana = (await db_session.execute(select(User).where(User.email == "ana@example.com"))).scalar_one()
        assert (row.created_by, row.trigger, row.subject_type) == (ana.id, "manual", "dataset")
        assert (await db_session.execute(select(AuditLogEntry).where(
            AuditLogEntry.action == "automation.start"))).scalars().first() is not None

    async def test_one_unfinished_run_per_dataset(self, world):
        first = (await _start(world)).json()
        again = await _start(world, who="ben")
        assert again.status_code == 409
        assert again.json()["detail"]["run_id"] == first["id"]

    async def test_a_finished_run_does_not_block_the_next(self, world, db_session):
        first = (await _start(world)).json()
        await _set_status(db_session, first["id"], "done")
        assert (await _start(world)).status_code == 201

    async def test_a_live_connection_dataset_is_refused_with_the_reason(self, world, db_session):
        world["ds"].mode = "directquery"
        await db_session.commit()
        r = await _start(world)
        assert r.status_code == 400 and "imported datasets only" in r.json()["detail"]

    async def test_another_orgs_dataset_is_not_found(self, world):
        assert (await _start(world, who="other_org")).status_code == 404


class TestSeeing:
    async def test_a_run_is_its_creators_and_an_admins(self, world):
        run = (await _start(world)).json()
        c = world["c"]
        assert [x["id"] for x in (await c.get("/api/v1/automation/runs", headers=world["ana"])).json()] == [run["id"]]
        assert (await c.get("/api/v1/automation/runs", headers=world["ben"])).json() == []
        assert [x["id"] for x in (await c.get("/api/v1/automation/runs", headers=world["admin"])).json()] == [run["id"]]
        assert (await c.get(f"/api/v1/automation/runs/{run['id']}", headers=world["ben"])).status_code == 404
        assert (await c.get(f"/api/v1/automation/runs/{run['id']}", headers=world["other_org"])).status_code == 404
        detail = (await c.get(f"/api/v1/automation/runs/{run['id']}", headers=world["admin"])).json()
        assert detail["rejection_reasons"] == [] and detail["id"] == run["id"]

    async def test_the_list_filters_by_dataset(self, world):
        run = (await _start(world)).json()
        c = world["c"]
        assert [x["id"] for x in (await c.get(f"/api/v1/automation/runs?dataset_id={world['ds'].id}",
                                              headers=world["ana"])).json()] == [run["id"]]
        assert (await c.get("/api/v1/automation/runs?dataset_id=999999", headers=world["ana"])).json() == []


class TestAnswering:
    async def test_a_held_run_can_be_approved_to_continue(self, world, db_session):
        run = (await _start(world)).json()
        c = world["c"]
        assert (await c.post(f"/api/v1/automation/runs/{run['id']}/approve", headers=world["ana"])).status_code == 409
        await _set_status(db_session, run["id"], runner.NEEDS_REVIEW)
        # Found live: nothing passed review -> nothing to build.
        nothing = await c.post(f"/api/v1/automation/runs/{run['id']}/approve", headers=world["ana"])
        assert nothing.status_code == 409 and "no report to build" in nothing.json()["detail"]
        await db_session.execute(update(AutomationRun).where(AutomationRun.id == run["id"]).values(widgets_accepted=3))
        await db_session.commit()
        assert (await c.post(f"/api/v1/automation/runs/{run['id']}/approve", headers=world["ben"])).status_code == 404
        r = await c.post(f"/api/v1/automation/runs/{run['id']}/approve", headers=world["ana"])
        assert r.status_code == 200 and r.json()["status"] == "running"

    async def test_a_held_run_can_be_rejected_with_a_reason(self, world, db_session):
        run = (await _start(world)).json()
        await _set_status(db_session, run["id"], runner.NEEDS_REVIEW)
        r = await world["c"].post(f"/api/v1/automation/runs/{run['id']}/reject",
                                  json={"reason": "wrong measure"}, headers=world["ana"])
        assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["error"] == "wrong measure"

    async def test_a_held_runs_notification_links_to_its_page(self, world, db_session):
        run = (await _start(world)).json()
        await _set_status(db_session, run["id"], runner.NEEDS_REVIEW)
        row = await db_session.get(AutomationRun, run["id"])
        await db_session.refresh(row)
        _text, link = runner.describe_run(row)
        assert link == f"/automation?run={run['id']}"


class TestStopping:
    async def test_cancel_stops_an_unfinished_run_and_is_idempotent(self, world):
        run = (await _start(world)).json()
        c = world["c"]
        r = await c.post(f"/api/v1/automation/runs/{run['id']}/cancel", headers=world["ana"])
        assert r.status_code == 200 and r.json()["status"] == "cancelled"
        assert r.json()["error"] == "cancelled by ana@example.com"
        again = await c.post(f"/api/v1/automation/runs/{run['id']}/cancel", headers=world["ana"])
        assert again.json()["status"] == "cancelled"

    async def test_a_step_finishing_after_a_cancel_does_not_revive_the_run(self, world, db_session):
        """The worker's copy of the run says running; the cancel is a write
        from another request."""
        run = (await _start(world)).json()
        row = await db_session.get(AutomationRun, run["id"])
        row.status = "running"
        await db_session.commit()
        steps = (await db_session.execute(select(AutomationStep).where(
            AutomationStep.run_id == run["id"]).order_by(AutomationStep.order))).scalars().all()
        # The cancel lands without touching this session's copy.
        await db_session.execute(update(AutomationRun).where(AutomationRun.id == run["id"])
                                 .values(status="cancelled").execution_options(synchronize_session=False))
        await db_session.commit()
        # The last step finishing is the case that would write `done` over it.
        for st in steps[:-1]:
            st.output_ref = f"file:///{st.name}.json"
        await db_session.commit()
        await runner._succeed(db_session, row, steps[-1], steps, "file:///notify.json", datetime.utcnow())
        await db_session.refresh(row)
        assert row.status == "cancelled"
        assert steps[-1].output_ref == "file:///notify.json"
        # And a failure after a cancel does not turn it into `failed` (which retries).
        await runner._fail(db_session, row, steps[1], "boom", datetime.utcnow())
        await db_session.refresh(row)
        assert row.status == "cancelled"

    async def test_the_tick_does_not_run_a_cancelled_run(self, world, db_session):
        run = (await _start(world)).json()
        await world["c"].post(f"/api/v1/automation/runs/{run['id']}/cancel", headers=world["ana"])
        assert await runner.tick(db_session) is False

    async def test_retry_skips_the_backoff_of_a_failed_step(self, world, db_session):
        run = (await _start(world)).json()
        c = world["c"]
        assert (await c.post(f"/api/v1/automation/runs/{run['id']}/retry", headers=world["ana"])).status_code == 409
        step = (await db_session.execute(select(AutomationStep).where(
            AutomationStep.run_id == run["id"], AutomationStep.name == "profile"))).scalar_one()
        step.status, step.error, step.attempts = "failed", "source down", 1
        step.next_attempt_at = datetime.utcnow() + timedelta(minutes=15)
        await db_session.commit()
        await _set_status(db_session, run["id"], "failed")
        r = await c.post(f"/api/v1/automation/runs/{run['id']}/retry", headers=world["ana"])
        assert r.status_code == 200
        profile = next(s for s in r.json()["steps"] if s["name"] == "profile")
        assert profile["next_attempt_at"] is None and profile["error"] == "source down"
