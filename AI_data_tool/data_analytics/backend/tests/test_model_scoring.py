"""E13: batch scoring as a durable job, and drift against the training rows.

A saved version can now score every row its user may see, as a job that keeps
the result as a new dataset traced to the version that made it; and a version
can be compared with today's rows (a population stability index per
predictor) to say whether its training still describes the data.
"""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.models import Dataset, Job, PredictionModel, RowSecurityRule, User
from app.services import jobs
from app.services.model_scoring import MODEL_SCORE_KIND

from .test_prediction_models_api import _dataset, _restricted_user, _train, churnfile  # noqa: F401


@pytest.fixture(autouse=True)
def _uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


async def _queue(client, headers, ds_id, model_id):
    return await client.post(f"/api/v1/datasets/{ds_id}/prediction-models/{model_id}/score-jobs",
                             headers=headers)


async def _drift(client, headers, ds_id, model_id):
    return await client.get(f"/api/v1/datasets/{ds_id}/prediction-models/{model_id}/drift", headers=headers)


async def _scored(db_session, job_id):
    job = await db_session.get(Job, job_id)
    await db_session.refresh(job)
    return job


class TestBatchScoring:
    async def test_a_version_scores_every_row_into_a_new_dataset_named_after_it(
            self, client, auth_headers, db_session, two_orgs, churnfile, factory):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        r = await _queue(client, auth_headers["a"], ds.id, model["id"])
        assert r.status_code == 202, r.text
        assert r.json()["kind"] == MODEL_SCORE_KIND and "v1" in r.json()["subject"]
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        job = await _scored(db_session, r.json()["id"])
        res = job.result
        assert res["rows"] == 300 and res["column"] == "predicted_churn"
        assert res["model"] == {"id": model["id"], "name": "Churn model", "version": 1}
        out = await db_session.get(Dataset, res["dataset_id"])
        assert out.name == "Churn scored by Churn model v1"
        assert out.created_by == two_orgs["a"]["user"].id and out.row_count == 300
        assert out.column_meta["__scored_by__"] | {"job_id": 0} == {
            "source_dataset_id": ds.id, "model_id": model["id"], "model_name": "Churn model", "version": 1, "job_id": 0}
        frame = pd.read_csv(out.filename)
        assert list(frame.columns) == ["region", "spend", "churn", "predicted_churn"]
        # A good model on its own training rows: nearly all right.
        assert (frame["churn"] == frame["predicted_churn"]).mean() > 0.9

    async def test_a_restricted_person_scores_their_own_rows_only(
            self, client, db_session, two_orgs, churnfile, factory):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        headers = await _restricted_user(db_session, two_orgs["a"]["org"], ds, rls="`region` != 'North'",
                                         email="north@example.com")
        trained = await _train(client, headers, ds.id)
        assert trained.status_code == 201, trained.text
        model = trained.json()
        r = await _queue(client, headers, ds.id, model["id"])
        assert r.status_code == 202, r.text
        assert await jobs.run_next(factory, "w1") == jobs.SUCCEEDED
        out = await db_session.get(Dataset, (await _scored(db_session, r.json()["id"])).result["dataset_id"])
        assert set(pd.read_csv(out.filename)["region"]) == {"South", "East"}

    async def test_the_job_checks_again_when_it_runs(
            self, client, db_session, two_orgs, churnfile, factory):
        """Access changed after queuing: a row rule now narrows what this
        person sees, so the model (trained on every row) is no longer theirs."""
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org, churnfile)
        headers = await _restricted_user(db_session, org, ds, email="later@example.com")
        model = (await _train(client, headers, ds.id)).json()
        r = await _queue(client, headers, ds.id, model["id"])
        role_id = (await db_session.execute(select(User.role_id).where(
            User.email == "later@example.com"))).scalar_one()
        db_session.add(RowSecurityRule(role_id=role_id, dataset_id=ds.id, filter_expr="region == 'South'"))
        await db_session.commit()
        assert await jobs.run_next(factory, "w1") == jobs.FAILED
        job = await _scored(db_session, r.json()["id"])
        assert job.error_code == "refused" and "different set of rows" in job.error
        assert (await db_session.execute(select(Dataset).where(
            Dataset.name.like("%scored by%")))).scalars().all() == []

    async def test_a_worker_that_lost_its_lease_leaves_no_dataset(
            self, client, auth_headers, db_session, two_orgs, churnfile, factory, tmp_path):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        await _queue(client, auth_headers["a"], ds.id, model["id"])
        async with factory() as s:
            job_id, token = await jobs.claim(s, "w1")
        await db_session.execute(update(Job).where(Job.id == job_id).values(lease_owner="other"))
        await db_session.commit()
        assert await jobs.execute(factory, job_id, token) is None
        assert (await db_session.execute(select(Dataset).where(
            Dataset.name.like("%scored by%")))).scalars().all() == []
        uploads = tmp_path / "uploads"
        assert not any(p.name.startswith("scored") for p in uploads.rglob("*")) if uploads.exists() else True

    async def test_a_lease_lost_while_writing_leaves_no_dataset_and_no_file(
            self, client, auth_headers, db_session, two_orgs, churnfile, factory, monkeypatch, tmp_path):
        """Taken over after the rows were scored: the new dataset is created in
        the same transaction as the fenced success, so it rolls back with it."""
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        await _queue(client, auth_headers["a"], ds.id, model["id"])
        original = jobs.JobContext.checkpoint

        async def checkpoint(self, stage, **detail):
            await original(self, stage, **detail)
            if stage == "writing":
                async with factory() as s2:
                    await s2.execute(update(Job).where(Job.id == self.job_id).values(lease_owner="other"))
                    await s2.commit()
        monkeypatch.setattr(jobs.JobContext, "checkpoint", checkpoint)
        assert await jobs.run_next(factory, "w1") is None
        assert (await db_session.execute(select(Dataset).where(
            Dataset.name.like("%scored by%")))).scalars().all() == []
        assert not [p for p in (tmp_path / "uploads").rglob("scored*")]

    async def test_a_live_connection_dataset_is_refused(self, client, auth_headers, db_session, two_orgs, churnfile):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        ds.mode = "directquery"
        await db_session.commit()
        r = await _queue(client, auth_headers["a"], ds.id, model["id"])
        assert r.status_code == 400


class TestDrift:
    async def test_the_training_rows_are_stable_against_themselves(
            self, client, auth_headers, db_session, two_orgs, churnfile):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        # Kept for drift, never sent: it describes the training rows.
        assert "feature_profile" not in model["card"] and model["has_training_profile"] is True
        row = await db_session.get(PredictionModel, model["id"])
        assert set(row.card["feature_profile"]) == {"region", "spend"}
        r = await _drift(client, auth_headers["a"], ds.id, model["id"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["overall"] == "stable" and body["rows"] == 300
        assert {f["feature"] for f in body["features"]} == {"region", "spend"}
        assert all(f["psi"] < 0.1 for f in body["features"])
        assert body["model"]["version"] == 1

    async def test_moved_data_is_named_feature_by_feature(
            self, client, auth_headers, db_session, two_orgs, churnfile):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        rng = np.random.default_rng(1)
        n = 300
        # The same columns, a year later: spend up by half, a new region.
        pd.DataFrame({"region": rng.choice(["North", "West"], n), "spend": rng.normal(150, 20, n).round(2),
                      "churn": rng.choice(["yes", "no"], n)}).to_csv(ds.filename, index=False)
        body = (await _drift(client, auth_headers["a"], ds.id, model["id"])).json()
        by = {f["feature"]: f for f in body["features"]}
        assert body["overall"] == "major"
        assert by["spend"]["level"] == "major" and by["region"]["level"] == "major"
        assert by["region"]["new_values"] == ["West"]

    async def test_a_version_saved_before_profiles_says_so(
            self, client, auth_headers, db_session, two_orgs, churnfile):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        row = await db_session.get(PredictionModel, model["id"])
        row.card = {k: v for k, v in (row.card or {}).items() if k != "feature_profile"}
        await db_session.commit()
        r = await _drift(client, auth_headers["a"], ds.id, model["id"])
        assert r.status_code == 409 and "Retrain" in r.json()["detail"]

    async def test_drift_is_refused_to_someone_denied_a_feature(
            self, client, auth_headers, db_session, two_orgs, churnfile):
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
        model = (await _train(client, auth_headers["a"], ds.id)).json()
        headers = await _restricted_user(db_session, two_orgs["a"]["org"], ds, denied=["spend"],
                                         email="nospend@example.com")
        r = await _drift(client, headers, ds.id, model["id"])
        assert r.status_code == 400 and "spend" in r.json()["detail"]
