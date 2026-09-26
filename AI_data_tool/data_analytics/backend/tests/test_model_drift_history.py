"""E13: drift over time -- each champion checked daily, every check kept.

A drift check used to be computed on demand and forgotten. Now each check is
kept on the version's card (the last 90), the scheduler queues one a day for
every champion, run as the person who trained it, and the panel can show
the trend.
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.models import Job, PredictionModel, RowSecurityRule, User
from app.services import jobs
from app.services.model_drift import HISTORY_CAP, MODEL_DRIFT_KIND, enqueue_daily, record, snapshot

from .test_prediction_models_api import _dataset, _restricted_user, _train, churnfile  # noqa: F401


@pytest.fixture(autouse=True)
def _uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _url(ds_id, model_id, tail):
    return f"/api/v1/datasets/{ds_id}/prediction-models/{model_id}/{tail}"


def _move(path):
    rng = np.random.default_rng(1)
    n = 300
    pd.DataFrame({"region": rng.choice(["North", "West"], n), "spend": rng.normal(150, 20, n).round(2),
                  "churn": rng.choice(["yes", "no"], n)}).to_csv(path, index=False)


class TestKeepingChecks:
    async def test_a_check_someone_asks_for_is_kept(self, client, auth_headers, db_session, two_orgs, churnfile):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        r = await client.post(_url(ds.id, model["id"], "drift-checks"), headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        assert r.json()["overall"] == "stable" and len(r.json()["history"]) == 1
        _move(ds.filename)
        r2 = (await client.post(_url(ds.id, model["id"], "drift-checks"), headers=auth_headers["a"])).json()
        assert [h["overall"] for h in r2["history"]] == ["stable", "major"]
        assert r2["history"][-1]["max_psi"] > 0.25 and set(r2["history"][-1]["features"]) == {"region", "spend"}
        got = (await client.get(_url(ds.id, model["id"], "drift-history"), headers=auth_headers["a"])).json()
        assert got["history"] == r2["history"]
        # The list names the latest level, not the checks themselves.
        listed = next(m for m in (await client.get(f"/api/v1/datasets/{ds.id}/prediction-models",
                                                   headers=auth_headers["a"])).json() if m["id"] == model["id"])
        assert listed["last_drift"]["overall"] == "major" and "drift_history" not in listed["card"]

    def test_the_history_keeps_the_last_ninety(self):
        m = PredictionModel(card={"feature_profile": {}})
        for i in range(HISTORY_CAP + 5):
            record(m, snapshot({"overall": "stable", "rows": i, "features": []}))
        h = m.card["drift_history"]
        assert len(h) == HISTORY_CAP and h[0]["rows"] == 5 and h[-1]["rows"] == HISTORY_CAP + 4
        assert m.card["feature_profile"] == {}

    async def test_a_reader_with_other_rows_cannot_read_the_history(self, client, auth_headers, db_session, two_orgs, churnfile):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org, churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        headers = await _restricted_user(db_session, org, ds, rls="`region` == 'North'", email="north-dh@example.com")
        r = await client.get(_url(ds.id, model["id"], "drift-history"), headers=headers)
        assert r.status_code == 400 and "different set of rows" in r.json()["detail"]


class TestTheDailyCheck:
    async def test_every_champion_is_queued_once_a_day_and_run_as_its_trainer(
            self, client, auth_headers, db_session, two_orgs, churnfile, factory):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        now = datetime.utcnow()
        assert await enqueue_daily(factory, now) == 1
        assert await enqueue_daily(factory, now) == 0            # the same day: the same job
        job = (await db_session.execute(select(Job).where(Job.kind == MODEL_DRIFT_KIND))).scalar_one()
        assert job.created_by == two_orgs["a"]["user"].id
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        row = await db_session.get(PredictionModel, model["id"])
        await db_session.refresh(row)
        assert [h["overall"] for h in row.card["drift_history"]] == ["stable"]
        # Checked within the day: not queued again until it is a day old.
        assert await enqueue_daily(factory, now + timedelta(hours=2)) == 0
        assert await enqueue_daily(factory, now + timedelta(hours=25)) == 1

    async def test_a_candidate_is_not_checked_daily(self, client, auth_headers, db_session, two_orgs, churnfile, factory):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        await _train(client, auth_headers["a"], ds.id)
        await _train(client, auth_headers["a"], ds.id)            # v2, a candidate
        assert await enqueue_daily(factory) == 1

    async def test_a_trainer_who_no_longer_sees_those_rows_records_nothing(
            self, client, db_session, two_orgs, churnfile, factory):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org, churnfile)
        headers = await _restricted_user(db_session, org, ds, email="later-dh@example.com")
        model = (await _train(client, headers, ds.id)).json()
        role_id = (await db_session.execute(select(User.role_id).where(User.email == "later-dh@example.com"))).scalar_one()
        db_session.add(RowSecurityRule(role_id=role_id, dataset_id=ds.id, filter_expr="region == 'South'"))
        await db_session.commit()
        await enqueue_daily(factory)
        assert await jobs.run_next(factory, "w1") == jobs.FAILED
        job = (await db_session.execute(select(Job).where(Job.kind == MODEL_DRIFT_KIND))).scalar_one()
        await db_session.refresh(job)
        assert job.error_code == "refused"
        row = await db_session.get(PredictionModel, model["id"])
        await db_session.refresh(row)
        assert not (row.card or {}).get("drift_history")
