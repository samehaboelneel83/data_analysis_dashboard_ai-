"""E13: model versions, a model card, promotion and rollback, scoring by version.

A saved model's name was unique per dataset, so improving a model meant
deleting the one a dashboard scored with, and nothing recorded how any model
had been chosen. Training under an existing name now makes its next version;
one version per name is the champion; promoting an older version is the
rollback; a scoring widget can follow the champion; every score names the
version that made it; and each version carries a card of how it was chosen.
"""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import AuditLogEntry, PredictionModel

from .test_prediction_models_api import _dataset, _restricted_user, _train, churnfile  # noqa: F401


async def _versions(client, headers, ds_id):
    r = await client.get(f"/api/v1/datasets/{ds_id}/prediction-models", headers=headers)
    assert r.status_code == 200, r.text
    return sorted(r.json(), key=lambda m: m["version"])


async def _promote(client, headers, ds_id, model_id):
    return await client.post(f"/api/v1/datasets/{ds_id}/prediction-models/{model_id}/promote",
                             headers=headers)


async def _score_widget(client, headers, ds_id, model_id, **config):
    return await client.post(f"/api/v1/datasets/{ds_id}/widget-data",
                             json={"widget_type": "model_score",
                                   "config": {"prediction_model_id": model_id, **config}},
                             headers=headers)


@pytest.fixture
async def two_versions(client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    v1 = await _train(client, auth_headers["a"], ds.id)
    v2 = await _train(client, auth_headers["a"], ds.id, predictors=["spend"])
    assert v1.status_code == 201 and v2.status_code == 201, (v1.text, v2.text)
    return {"ds": ds, "v1": v1.json(), "v2": v2.json(), "h": auth_headers["a"]}


class TestVersions:
    async def test_retraining_a_name_makes_its_next_version_beside_the_champion(self, client, two_versions):
        v1, v2 = two_versions["v1"], two_versions["v2"]
        assert (v1["version"], v1["status"]) == (1, "champion")
        assert (v2["version"], v2["status"]) == (2, "candidate")
        assert v1["name"] == v2["name"] and v1["id"] != v2["id"]
        listed = await _versions(client, two_versions["h"], two_versions["ds"].id)
        assert [(m["version"], m["status"]) for m in listed] == [(1, "champion"), (2, "candidate")]

    async def test_a_new_name_starts_at_version_one_as_its_own_champion(self, client, two_versions):
        other = (await _train(client, two_versions["h"], two_versions["ds"].id, name="Another")).json()
        assert (other["version"], other["status"]) == (1, "champion")

    async def test_each_score_names_the_version_that_made_it(self, client, two_versions):
        ds, h = two_versions["ds"], two_versions["h"]
        for v in ("v1", "v2"):
            m = two_versions[v]
            r = await client.post(f"/api/v1/datasets/{ds.id}/prediction-models/{m['id']}/score",
                                  json={"from_dataset": True}, headers=h)
            assert r.status_code == 200, r.text
            assert r.json()["model"] == {"id": m["id"], "name": m["name"], "version": m["version"],
                                         "status": m["status"]}


class TestPromotionAndRollback:
    async def test_promoting_makes_one_champion_and_rolling_back_is_promoting_the_old_one(
            self, client, db_session, two_versions):
        ds, h, v1, v2 = two_versions["ds"], two_versions["h"], two_versions["v1"], two_versions["v2"]
        r = await _promote(client, h, ds.id, v2["id"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "champion" and r.json()["promoted_at"]
        assert [(m["version"], m["status"]) for m in await _versions(client, h, ds.id)] == \
            [(1, "candidate"), (2, "champion")]
        # Rollback.
        assert (await _promote(client, h, ds.id, v1["id"])).status_code == 200
        assert [(m["version"], m["status"]) for m in await _versions(client, h, ds.id)] == \
            [(1, "champion"), (2, "candidate")]
        audits = (await db_session.execute(select(AuditLogEntry).where(
            AuditLogEntry.action == "model.promote"))).scalars().all()
        assert [a.detail for a in audits] == [f"{v1['name']} v2 replaces v1", f"{v1['name']} v1 replaces v2"]

    async def test_a_widget_following_the_champion_scores_with_whichever_is_champion(self, client, two_versions):
        ds, h, v1, v2 = two_versions["ds"], two_versions["h"], two_versions["v1"], two_versions["v2"]
        follow = await _score_widget(client, h, ds.id, v1["id"], model_follows="champion")
        pinned = await _score_widget(client, h, ds.id, v1["id"])
        assert follow.json()["saved"]["version"] == 1 and pinned.json()["saved"]["version"] == 1
        await _promote(client, h, ds.id, v2["id"])
        follow = await _score_widget(client, h, ds.id, v1["id"], model_follows="champion")
        pinned = await _score_widget(client, h, ds.id, v1["id"])
        assert (follow.json()["saved"]["id"], follow.json()["saved"]["version"]) == (v2["id"], 2)
        assert follow.json()["predictors"] == ["spend"]
        assert (pinned.json()["saved"]["id"], pinned.json()["saved"]["version"]) == (v1["id"], 1)

    async def test_promoting_is_authoring_like_training(self, client, db_session, two_orgs, two_versions):
        """Same gate as training (see test_training_is_gated_as_authoring_not_reading):
        it bites once a report holds the role below 'data' on the dataset."""
        from app.models.models import Report, ReportCapability, User
        org, ds = two_orgs["a"]["org"], two_versions["ds"]
        viewer = await _restricted_user(db_session, org, ds, email="looker@example.com")
        role_id = (await db_session.execute(select(User.role_id).where(
            User.email == "looker@example.com"))).scalar_one()
        report = Report(name="R", dataset_id=ds.id, org_id=org.id)
        db_session.add(report)
        await db_session.flush()
        db_session.add(ReportCapability(report_id=report.id, role_id=role_id, level="view"))
        await db_session.commit()
        r = await _promote(client, viewer, ds.id, two_versions["v2"]["id"])
        assert r.status_code == 403, r.text
        assert (await _promote(client, two_versions["h"], ds.id, 999_999)).status_code == 404

    async def test_another_org_cannot_promote(self, client, auth_headers, two_versions):
        r = await _promote(client, auth_headers["b"], two_versions["ds"].id, two_versions["v2"]["id"])
        assert r.status_code == 404

    async def test_deleting_the_champion_hands_the_title_to_the_newest_version(self, client, two_versions):
        ds, h, v1 = two_versions["ds"], two_versions["h"], two_versions["v1"]
        v3 = (await _train(client, h, ds.id)).json()
        r = await client.delete(f"/api/v1/datasets/{ds.id}/prediction-models/{v1['id']}", headers=h)
        assert r.status_code == 204
        assert [(m["version"], m["status"]) for m in await _versions(client, h, ds.id)] == \
            [(2, "candidate"), (3, "champion")]
        assert v3["version"] == 3


class TestModelCard:
    async def test_the_card_says_how_the_model_was_chosen_and_on_what(self, client, two_versions):
        card = two_versions["v1"]["card"]
        assert card["target"] == "churn" and card["task"] == "classification"
        assert card["model_family"] == two_versions["v1"]["model_family"]
        assert card["score"] == two_versions["v1"]["score"]
        assert any(c["model"] == card["model_family"] for c in card["candidates"])
        assert len(card["candidates"]) >= 2
        assert card["baseline_score"] is not None and card["beats_baseline"] is True
        assert set(card["predictors_used"]) == {"region", "spend"}
        assert card["n_train"] + card["n_test"] == 300 and card["n_fitted"] == 300
        assert card["split"]["kind"] == "random"
        assert card["row_scope"] == "every row"
        assert card["dataset"]["name"] == "Churn" and card["trained_by"] == "admin-a@example.com"
        assert two_versions["v2"]["card"]["predictors_used"] == ["spend"]

    async def test_the_card_says_a_row_rule_applied_without_disclosing_it(
            self, client, auth_headers, db_session, two_orgs, churnfile, monkeypatch):
        """A row rule's text belongs to the administrators who wrote it."""
        ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)

        async def north_only(db, user, dataset_id):
            return "region == 'North' or spend > 0"
        monkeypatch.setattr("app.routers.prediction_models.resolve_rls_expr", north_only)
        r = await _train(client, auth_headers["a"], ds.id)
        assert r.status_code == 201, r.text
        card = r.json()["card"]
        assert card["row_scope"] == "restricted by a row rule"
        assert "North" not in str(card) and "spend > 0" not in str(card)

    async def test_a_model_saved_before_cards_is_still_listed(self, client, db_session, two_versions):
        row = await db_session.get(PredictionModel, two_versions["v1"]["id"])
        row.card = None
        await db_session.commit()
        listed = await _versions(client, two_versions["h"], two_versions["ds"].id)
        assert listed[0]["card"] is None and listed[0]["status"] == "champion"
