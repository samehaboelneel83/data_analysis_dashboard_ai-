"""The model store over HTTP: train, list, score, delete — and who may.

A saved model is a new kind of object in this codebase, and it carries a
security property nothing else here has: **it contains the influence of every
column it was trained on**. A user denied one of those columns must not be able
to score with it, because the answer it gives is derived from data they are not
allowed to read. Dropping the column at score time would not help — the model
was already fitted on it.

The rest is the security every dataset endpoint here has: org scoping, a 404
rather than a 403 for a dataset you cannot see, row security applied to the rows
being scored, and authoring gated separately from reading.
"""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn, Role,
                               RowSecurityRule, User)


@pytest.fixture
def churnfile(tmp_path):
    """Enough rows, and a real signal, so a champion can beat the baseline."""
    rng = np.random.default_rng(0)
    n = 300
    region = rng.choice(["North", "South", "East"], n)
    spend = rng.normal(100, 20, n).round(2)
    churn = np.where((region == "North") | (spend > 120), "yes", "no")
    p = tmp_path / "churn.csv"
    pd.DataFrame({"region": region, "spend": spend, "churn": churn}).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path):
    ds = Dataset(name="Churn", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("spend", "numeric"), ("churn", "categorical")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    await db.refresh(ds)
    return ds


async def _restricted_user(db, org, ds, *, denied=None, rls=None, email="r@example.com"):
    """A non-admin whose role carries the given column/row rules."""
    role = Role(org_id=org.id, name=f"role-{email}", is_org_admin=False)
    db.add(role)
    await db.flush()
    if denied:
        db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=denied))
    if rls:
        db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr=rls))
    user = User(org_id=org.id, role_id=role.id, email=email,
                password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def _train(client, headers, ds_id, name="Churn model", **body):
    return await client.post(f"/api/v1/datasets/{ds_id}/prediction-models",
                             json={"name": name, "target": "churn", **body},
                             headers=headers)


@pytest.mark.asyncio
async def test_train_list_score_round_trip(client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)

    trained = await _train(client, auth_headers["a"], ds.id)
    assert trained.status_code == 201, trained.text
    model = trained.json()
    assert model["target"] == "churn"
    assert set(model["features"]) == {"region", "spend"}
    assert model["score"] is not None
    # The artifact itself never travels: it is a pickle, and nothing downstream
    # has any use for it.
    assert "artifact" not in model

    listed = await client.get(f"/api/v1/datasets/{ds.id}/prediction-models",
                              headers=auth_headers["a"])
    assert [m["id"] for m in listed.json()] == [model["id"]]

    scored = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{model['id']}/score",
        json={"rows": [{"region": "North", "spend": 50.0},
                       {"region": "South", "spend": 200.0}]},
        headers=auth_headers["a"])
    assert scored.status_code == 200, scored.text
    body = scored.json()
    assert len(body["predictions"]) == 2
    assert all(p in ("yes", "no") for p in body["predictions"])


@pytest.mark.asyncio
async def test_an_unseen_category_is_reported(client, auth_headers, db_session, two_orgs, churnfile):
    """Scoring a value the model never saw is legal and must be declared.

    It encodes as zero across that column's dummies -- the model has no opinion
    -- and returning the prediction without a word would let somebody score a
    year of new data the model recognises none of."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()

    scored = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{model['id']}/score",
        json={"rows": [{"region": "West", "spend": 90.0}]}, headers=auth_headers["a"])

    assert scored.status_code == 200, scored.text
    assert "West" in scored.json()["unseen_values"]["region"]


@pytest.mark.asyncio
async def test_a_denied_feature_column_blocks_scoring(
        client, auth_headers, db_session, two_orgs, churnfile):
    """THE property this table exists to be careful about.

    The model was fitted on `spend`, so its answers are derived from `spend`
    whether or not the caller supplies it. A user denied that column must be
    refused -- dropping the column at score time would change nothing, because
    the influence is already inside the fitted model."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()
    headers = await _restricted_user(db_session, org, ds, denied=["spend"],
                                     email="nospend@example.com")

    scored = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{model['id']}/score",
        json={"rows": [{"region": "North", "spend": 50.0}]}, headers=headers)

    assert scored.status_code == 400, scored.text
    assert "spend" in scored.text


@pytest.mark.asyncio
async def test_a_denied_column_also_hides_the_model_from_the_list(
        client, auth_headers, db_session, two_orgs, churnfile):
    """Listing a model whose features include a denied column tells the user
    that column exists and is worth predicting from. The model is simply not
    theirs to see."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    await _train(client, auth_headers["a"], ds.id)
    headers = await _restricted_user(db_session, org, ds, denied=["spend"],
                                     email="nolist@example.com")

    listed = await client.get(f"/api/v1/datasets/{ds.id}/prediction-models", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.asyncio
async def test_another_org_cannot_see_or_score_the_model(
        client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()

    # 404 rather than 403: whether this dataset exists is not org B's business.
    assert (await client.get(f"/api/v1/datasets/{ds.id}/prediction-models",
                             headers=auth_headers["b"])).status_code == 404
    assert (await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{model['id']}/score",
        json={"rows": [{"region": "North", "spend": 50.0}]},
        headers=auth_headers["b"])).status_code == 404


@pytest.mark.asyncio
async def test_training_is_gated_as_authoring_not_reading(
        client, auth_headers, db_session, two_orgs, churnfile):
    """Fitting a model reads every row and column and stores a derivative
    of them that outlives the request. That is authoring.

    Constructing the refusal takes a report, because this platform
    deliberately treats a dataset NO REPORT USES as unrestricted
    (`max_dataset_capability`: "a report with no capability row for the
    role grants the 'data' default"). Asserting a bare viewer is blocked
    would have been asserting a rule this codebase does not have -- the
    gate only bites when every report on the dataset holds the role below
    'data'."""
    from app.models.models import Report, ReportCapability

    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    headers = await _restricted_user(db_session, org, ds, email="viewer@example.com")
    user_role_id = (await db_session.execute(
        select(User.role_id).where(User.email == "viewer@example.com")
    )).scalar_one()

    report = Report(name="R", dataset_id=ds.id, org_id=org.id)
    db_session.add(report)
    await db_session.flush()
    db_session.add(ReportCapability(report_id=report.id, role_id=user_role_id,
                                    level="view"))
    await db_session.commit()

    trained = await _train(client, headers, ds.id, name="Sneaky")
    assert trained.status_code == 403, trained.text


@pytest.mark.asyncio
async def test_a_viewer_of_an_unreported_dataset_may_train(
        client, auth_headers, db_session, two_orgs, churnfile):
    """The other half of the same rule, stated so the line is visible: a
    dataset no report governs is unrestricted here, by design."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    headers = await _restricted_user(db_session, org, ds, email="open@example.com")

    trained = await _train(client, headers, ds.id, name="Allowed")
    assert trained.status_code == 201, trained.text


@pytest.mark.asyncio
async def test_scoring_rows_from_the_dataset_respects_row_security(
        client, auth_headers, db_session, two_orgs, churnfile):
    """Scoring the DATASET scores the caller's rows, not the table's.

    Each side uses its OWN model, because a model may only be used by
    somebody who sees the rows it was fitted on -- so the comparison is
    between two people's frames, which is exactly the thing being checked."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    headers = await _restricted_user(db_session, org, ds, rls="`region` != 'North'",
                                     email="notnorth@example.com")

    wide = (await _train(client, auth_headers["a"], ds.id, name="All rows")).json()
    narrow = (await _train(client, headers, ds.id, name="My rows")).json()

    mine = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{narrow['id']}/score",
        json={"from_dataset": True}, headers=headers)
    everyone = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{wide['id']}/score",
        json={"from_dataset": True}, headers=auth_headers["a"])

    assert mine.status_code == 200, mine.text
    assert everyone.status_code == 200, everyone.text
    assert mine.json()["n_scored"] < everyone.json()["n_scored"]


@pytest.mark.asyncio
async def test_a_model_can_be_deleted(client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()

    gone = await client.delete(
        f"/api/v1/datasets/{ds.id}/prediction-models/{model['id']}", headers=auth_headers["a"])
    assert gone.status_code == 204
    assert (await client.get(f"/api/v1/datasets/{ds.id}/prediction-models",
                             headers=auth_headers["a"])).json() == []


@pytest.mark.asyncio
async def test_a_model_may_only_be_used_by_someone_who_sees_the_same_rows(
        client, auth_headers, db_session, two_orgs, churnfile):
    """A fitted model is a derivative of the rows it was trained on.

    `materialize` refuses a governed dataset outright for the neighbouring
    reason: a snapshot written under one person's RLS carries no rules of its
    own, and colleagues then read a silently truncated table. A model is the
    same shape of object -- a decision tree's leaves and a forest's splits are
    built from the rows it saw -- so a reader restricted to fewer rows than the
    trainer would be getting answers derived from rows they cannot read.

    The rule kept here is narrower than materialize's blanket refusal, because
    it can afford to be: the model records the row filter it was trained under,
    and is usable by anyone who sees exactly those rows. An admin's model is
    for admins; an EMEA analyst's model is for EMEA analysts."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()
    headers = await _restricted_user(db_session, org, ds, rls="`region` == 'North'",
                                     email="narrow@example.com")

    scored = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{model['id']}/score",
        json={"rows": [{"region": "North", "spend": 50.0}]}, headers=headers)

    assert scored.status_code == 400, scored.text
    assert "rows" in scored.text.lower()


@pytest.mark.asyncio
async def test_a_model_trained_under_the_same_rules_is_usable(
        client, auth_headers, db_session, two_orgs, churnfile):
    """The other half: the restriction is on DIFFERING visibility, not on
    having any. Two people under the same rule share their models."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, churnfile)
    trainer = await _restricted_user(db_session, org, ds, rls="`region` != 'North'",
                                     email="north1@example.com")
    reader = await _restricted_user(db_session, org, ds, rls="`region` != 'North'",
                                    email="north2@example.com")

    trained = await _train(client, trainer, ds.id, name="North model")
    assert trained.status_code == 201, trained.text

    scored = await client.post(
        f"/api/v1/datasets/{ds.id}/prediction-models/{trained.json()['id']}/score",
        json={"rows": [{"region": "South", "spend": 50.0}]}, headers=reader)
    assert scored.status_code == 200, scored.text


# ── The canvas scoring widget (MASTER_PLAN Phase 3 item 5) ──────────────────

async def _score_widget(client, headers, ds_id, model_id, **config):
    return await client.post(f"/api/v1/datasets/{ds_id}/widget-data", headers=headers,
                             json={"widget_type": "model_score",
                                   "config": {"prediction_model_id": model_id, **config}})


@pytest.mark.asyncio
async def test_a_scoring_widget_predicts_the_page_rows_and_grades_itself(
        client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()
    r = await _score_widget(client, auth_headers["a"], ds.id, model["id"], dimension="region",
                            event_value="yes")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "ok" and out["model"] == "score"
    assert out["population"]["rows_used"] == 300
    assert out["event"] == "yes" and out["breakdown"] == "region"
    north = next(row for row in out["rows"] if row["name"] == "North")
    assert north["value"] > 0.9  # every North row churns in this data
    # The real outcome is in the frame, so it is graded on these rows too.
    assert "accuracy on these rows" in out["fit"]["secondary"]


@pytest.mark.asyncio
async def test_a_scoring_widget_follows_the_page_filters(client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()
    r = await _score_widget(client, auth_headers["a"], ds.id, model["id"],
                            filters=[{"column": "region", "op": "eq", "value": "South"}])
    assert r.status_code == 200, r.text
    assert r.json()["population"]["rows_used"] < 300


@pytest.mark.asyncio
async def test_a_scoring_widget_refuses_a_model_trained_on_a_denied_column(
        client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()
    headers = await _restricted_user(db_session, two_orgs["a"]["org"], ds, denied=["spend"], email="w@example.com")
    r = await _score_widget(client, headers, ds.id, model["id"])
    assert r.status_code in (400, 403, 404)
    assert "spend" in r.text or r.status_code == 404


@pytest.mark.asyncio
async def test_a_scoring_widget_refuses_a_model_trained_on_other_rows(
        client, auth_headers, db_session, two_orgs, churnfile):
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    model = (await _train(client, auth_headers["a"], ds.id)).json()
    headers = await _restricted_user(db_session, two_orgs["a"]["org"], ds, rls="region == 'North'", email="n@example.com")
    r = await _score_widget(client, headers, ds.id, model["id"])
    assert r.status_code in (400, 403, 404)
    assert "different set of rows" in r.text or r.status_code == 404


@pytest.mark.asyncio
async def test_training_never_uses_a_partition_column_and_can_train_on_its_training_rows(
        client, auth_headers, db_session, two_orgs, churnfile):
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.prep import PREP_STEPS_KEY
    ds = await _dataset(db_session, two_orgs["a"]["org"], churnfile)
    ds.column_meta = {PREP_STEPS_KEY: [{"kind": "partition", "name": "split", "train_pct": 70, "seed": 1}]}
    flag_modified(ds, "column_meta")
    await db_session.commit()
    r = await _train(client, auth_headers["a"], ds.id, partition="split")
    assert r.status_code == 201, r.text
    assert "split" not in r.json()["features"]
    bad = await _train(client, auth_headers["a"], ds.id, name="other", partition="nope")
    assert bad.status_code == 400 and "nope" in bad.text
