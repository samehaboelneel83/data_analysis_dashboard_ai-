"""Pipeline plan, phase 2: someone hears about it -- once.

A refresh run that changes an item's state is announced: the first failure of
a streak, the success that ends it, and a dataset going past its freshness
target. Retries in between say nothing (alert fatigue is how alerts stop being
read). The owner is the creator, or the org admins when there is none; the
watch's recipients add emails and webhooks.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import (DataSource, Dataset, Notification, PipelineWatch,
                               RefreshRun)
from app.services import pipeline_alerts
from app.services.refresh_runs import finish_run, start_run


@pytest.fixture(autouse=True)
def _no_brief_cache():
    pipeline_alerts._BRIEF_CACHE.clear()
    yield
    pipeline_alerts._BRIEF_CACHE.clear()


async def _dataset(db_session, two_orgs, tmp_path, *, owner=True, name="Orders"):
    org = two_orgs["a"]["org"]
    path = tmp_path / f"{name}.csv"
    pd.DataFrame([{"region": "N", "v": 1}, {"region": "S", "v": 2}]).to_csv(path, index=False)
    src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org.id)
    db_session.add(src)
    await db_session.commit()
    ds = Dataset(name=name, filename=str(path), org_id=org.id, row_count=2, col_count=2,
                 data_source_id=src.id, source_table="t", refresh_interval_minutes=60,
                 created_by=two_orgs["a"]["user"].id if owner else None)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _run(db_session, ds, status, error=None):
    rid = await start_run(db_session, "dataset", ds.id, ds.org_id)
    await finish_run(db_session, rid, status, error=error, rows=2 if status == "ok" else None)


async def _notices(db_session):
    return (await db_session.execute(
        select(Notification).where(Notification.kind == "refresh").order_by(Notification.id)
    )).scalars().all()


class TestOneNoticePerChange:
    async def test_the_first_failure_is_announced_and_retries_are_not(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        await _run(db_session, ds, "failed", "Refresh failed: unable to open database file\n(Background ...)")
        await _run(db_session, ds, "failed", "Refresh failed: unable to open database file")
        await _run(db_session, ds, "failed", "Refresh failed: unable to open database file")

        [n] = await _notices(db_session)
        assert n.user_id == two_orgs["a"]["user"].id
        assert "Orders" in n.text and "unable to open database file" in n.text
        assert "Background" not in n.text
        assert "failed: Refresh failed" not in n.text
        assert n.link == f"/datasets/{ds.id}"

    async def test_recovery_is_announced_once(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        await _run(db_session, ds, "failed", "boom")
        await _run(db_session, ds, "ok")
        await _run(db_session, ds, "ok")

        notices = await _notices(db_session)
        assert len(notices) == 2
        assert "again" in notices[1].text

    async def test_a_healthy_dataset_says_nothing(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        await _run(db_session, ds, "ok")
        assert await _notices(db_session) == []

    async def test_with_no_owner_the_org_admins_are_told(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path, owner=False)
        await _run(db_session, ds, "failed", "boom")
        notices = await _notices(db_session)
        assert notices, "a failure must never be addressed to nobody"
        assert {n.org_id for n in notices} == {ds.org_id}

    async def test_recipients_get_email_and_webhook(self, db_session, two_orgs, tmp_path, monkeypatch):
        sent, posted = [], []
        monkeypatch.setattr("app.services.delivery.send_email",
                            lambda to, subject, body, attachment=None: sent.append((to, subject)) or None)
        monkeypatch.setattr("app.services.alerts.post_webhook",
                            lambda url, text: posted.append(url) or None)
        ds = await _dataset(db_session, two_orgs, tmp_path)
        db_session.add(PipelineWatch(kind="dataset", item_id=ds.id, org_id=ds.org_id, state="ok",
                                     recipients=["ops@example.com", "https://hooks.example.com/x"]))
        await db_session.commit()

        await _run(db_session, ds, "failed", "boom")

        assert sent == [(["ops@example.com"], "Refresh failed: Orders")]
        assert posted == ["https://hooks.example.com/x"]


class TestFreshness:
    async def test_stale_data_is_announced_once_and_cleared_by_a_refresh(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        ds.last_refreshed_at = datetime.utcnow() - timedelta(hours=3)
        db_session.add(PipelineWatch(kind="dataset", item_id=ds.id, org_id=ds.org_id, state="ok",
                                     freshness_hours=2, recipients=[]))
        await db_session.commit()

        assert await pipeline_alerts.check_freshness(db_session) == 1
        assert await pipeline_alerts.check_freshness(db_session) == 0
        [n] = await _notices(db_session)
        assert "3 hours" in n.text and "target is 2 hours" in n.text

        await _run(db_session, ds, "ok")
        watch = await pipeline_alerts.get_watch(db_session, "dataset", ds.id)
        assert watch.stale_alerted_at is None
        assert len(await _notices(db_session)) == 2       # "up to date" again

    async def test_fresh_data_is_not_stale(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        ds.last_refreshed_at = datetime.utcnow() - timedelta(minutes=30)
        db_session.add(PipelineWatch(kind="dataset", item_id=ds.id, org_id=ds.org_id, state="ok",
                                     freshness_hours=2, recipients=[]))
        await db_session.commit()
        assert await pipeline_alerts.check_freshness(db_session) == 0


class TestTheApi:
    async def test_health_and_settings_round_trip(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        await _run(db_session, ds, "failed", "Refresh failed: unable to open database file")

        r = await client.patch(f"/api/v1/datasets/{ds.id}/pipeline-watch",
                               json={"freshness_hours": 26, "recipients": ["ops@example.com"]},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "failing" and body["freshness_hours"] == 26
        assert body["recipients"] == ["ops@example.com"] and body["can_edit"] is True
        assert "unable to open" in body["last_run"]["error"]
        assert body["owners"] == [two_orgs["a"]["user"].email]

        r = await client.get(f"/api/v1/datasets/{ds.id}/pipeline-health", headers=auth_headers["a"])
        assert r.json()["freshness_hours"] == 26

    @pytest.mark.parametrize("payload", [{"freshness_hours": 5}, {"recipients": ["not an address"]},
                                         {"recipients": ["http://insecure.example.com/hook"]}])
    async def test_bad_settings_are_refused(self, client, db_session, two_orgs, auth_headers, tmp_path, payload):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        r = await client.patch(f"/api/v1/datasets/{ds.id}/pipeline-watch", json=payload,
                               headers=auth_headers["a"])
        assert r.status_code == 400

    async def test_another_org_cannot_see_it(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        r = await client.get(f"/api/v1/datasets/{ds.id}/pipeline-health", headers=auth_headers["b"])
        assert r.status_code == 404

    async def test_a_widget_on_failing_data_carries_a_badge_without_the_error(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        body = {"config": {"dimension": "region", "measure": "v", "aggregation": "sum"}, "widget_type": "bar"}
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
        assert "data_health" not in r.json()

        await _run(db_session, ds, "failed", "Refresh failed: host db.internal unreachable")
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
        health = r.json()["data_health"]
        assert health["state"] == "failing"
        assert "db.internal" not in str(health)

    async def test_lineage_marks_the_failing_dataset(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        await _run(db_session, ds, "failed", "boom")
        graph = (await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["a"])).json()
        [node] = [d for d in graph["datasets"] if d["id"] == ds.id]
        assert node["health"] == "failing"


class TestFollowers:
    """Loose end after the pipeline plan: "Notify me" for an editor who is not
    the creator, so a dataset whose creator account nobody reads still reaches
    a person."""

    async def _user(self, db_session, two_orgs, email, *, org="a", active=True):
        from app.models.models import User
        u = User(org_id=two_orgs[org]["org"].id, role_id=two_orgs[org]["role"].id,
                 email=email, password_hash="x", is_active=active)
        db_session.add(u)
        await db_session.commit()
        return u

    async def test_followers_are_told_besides_the_owner(self, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        fan = await self._user(db_session, two_orgs, "fan@example.com")
        gone = await self._user(db_session, two_orgs, "gone@example.com", active=False)
        stranger = await self._user(db_session, two_orgs, "other@example.com", org="b")
        owner = two_orgs["a"]["user"].id
        db_session.add(PipelineWatch(kind="dataset", item_id=ds.id, org_id=ds.org_id, state="ok",
                                     recipients=[], followers=[fan.id, gone.id, stranger.id, owner]))
        await db_session.commit()

        await _run(db_session, ds, "failed", "boom")

        told = [n.user_id for n in await _notices(db_session)]
        assert told == [owner, fan.id], "owner once, then live followers of the same org only"
        assert await pipeline_alerts.owner_emails(db_session, "dataset", ds.id) == [
            two_orgs["a"]["user"].email, "fan@example.com"]

    async def test_follow_and_unfollow_through_the_api(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path, owner=False)
        url = f"/api/v1/datasets/{ds.id}/pipeline-watch"
        r = await client.patch(url, json={"follow": True}, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["following"] is True
        r = await client.patch(url, json={"follow": True}, headers=auth_headers["a"])
        watch = await pipeline_alerts.get_watch(db_session, "dataset", ds.id)
        await db_session.refresh(watch)
        assert watch.followers == [two_orgs["a"]["user"].id], "following twice is still once"
        r = await client.patch(url, json={"follow": False}, headers=auth_headers["a"])
        assert r.json()["following"] is False

    async def test_another_org_cannot_follow(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        r = await client.patch(f"/api/v1/datasets/{ds.id}/pipeline-watch", json={"follow": True},
                               headers=auth_headers["b"])
        assert r.status_code == 404

    @pytest.mark.parametrize("host, ready", [("", False), ("smtp.example.com", True)])
    async def test_health_says_whether_email_can_be_sent(self, client, db_session, two_orgs, auth_headers,
                                                         tmp_path, monkeypatch, host, ready):
        from app.core.config import settings
        monkeypatch.setattr(settings, "smtp_host", host)
        ds = await _dataset(db_session, two_orgs, tmp_path)
        r = await client.get(f"/api/v1/datasets/{ds.id}/pipeline-health", headers=auth_headers["a"])
        assert r.json()["email_ready"] is ready
