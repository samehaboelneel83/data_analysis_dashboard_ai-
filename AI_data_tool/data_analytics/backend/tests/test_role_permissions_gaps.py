"""QA E-08 follow-up: every OTHER way to make a dataset or a dashboard.

E-08 gated the obvious doors (upload, POST /reports, duplicate, templates).
These are the side doors a role without the right could still use:

  * a NEW dataset made from data already in the app -- materialize, an
    aggregate, a dataflow run that creates an output, batch scoring --
    needs `upload_data` ("Add data"); re-running what exists (a dataflow
    refresh) is not a new dataset and stays allowed;
  * an automated analysis composes a dashboard as the person who started it:
    refused when they start it, and the compose step refuses at run time if
    the role lost the right since;
  * seeding the demo writes org-wide content: org admins only;
  * publishing has no capability of its own (accepted): it stays the
    author's or an admin's, and the approval workflow still applies.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.core import role_permissions
from app.core.config import settings as app_settings
from app.core.security import create_access_token, hash_password
from app.models.models import (Dataflow, DataSource, Dataset, DatasetColumn,
                               OrgReviewSettings, Report, ReportPage, ReportWidget,
                               Role, User)
from app.services import automation_runner as runner
from app.services import quotas

ALL = list(role_permissions.CAPABILITIES)


@pytest.fixture(autouse=True)
def _uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    quotas.invalidate_quota_cache()
    yield tmp_path
    quotas.invalidate_quota_cache()


async def _member(db, org, *, perms=None, email="member@example.com"):
    role = Role(org_id=org.id, name=f"R-{email}", is_org_admin=False, permissions_raw=perms)
    db.add(role)
    await db.flush()
    user = User(org_id=org.id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _csv_dataset(db, org, tmp_path, owner, name="Orders"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"k": ["a", "b", "c"], "n": [1, 2, 3]}).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org.id, mode="import",
                 row_count=3, col_count=2, created_by=owner.id)
    db.add(ds)
    await db.flush()
    db.add_all([DatasetColumn(dataset_id=ds.id, name="k", dtype="categorical"),
                DatasetColumn(dataset_id=ds.id, name="n", dtype="numeric")])
    await db.commit()
    return ds


async def _deny(db, user, **perms):
    role = await db.get(Role, user.role_id)
    role.permissions_raw = {**(role.permissions_raw or {}), **perms}
    await db.commit()


async def _datasets(db, org):
    return (await db.execute(select(Dataset.id).where(Dataset.org_id == org.id))).scalars().all()


# ── new datasets need upload_data ───────────────────────────────────────────

async def test_materialize_needs_add_data(client, db_session, two_orgs, _uploads):
    org = two_orgs["a"]["org"]
    user, h = await _member(db_session, org, perms={"upload_data": False}, email="d@example.com")
    ds = await _csv_dataset(db_session, org, _uploads, user)
    before = await _datasets(db_session, org)
    r = await client.post(f"/api/v1/datasets/{ds.id}/materialize",
                          json={"name": "Copy", "steps": []}, headers=h)
    assert r.status_code == 403, r.text
    assert "upload data" in r.json()["detail"]
    assert await _datasets(db_session, org) == before
    # Allowed when the role has it (permissions NULL keep everything).
    other, h2 = await _member(db_session, org, email="ok@example.com")
    ds2 = await _csv_dataset(db_session, org, _uploads, other, name="Theirs")
    r = await client.post(f"/api/v1/datasets/{ds2.id}/materialize",
                          json={"name": "Copy", "steps": []}, headers=h2)
    assert r.status_code == 200, r.text


async def test_aggregate_needs_add_data(client, db_session, two_orgs, monkeypatch):
    from app.services import dataset_refresh

    def _rewrite(cfg, filename, source_table, source_query, **_kw):
        df = pd.DataFrame([{"region": "N", "amount_sum": 10.0, "row_count": 2}])
        df.to_csv(filename, index=False)
        from app.services.frame_cache import write_parquet_sidecar
        from app.services.ingest import detect_types
        write_parquet_sidecar(filename)
        return df, detect_types(df)
    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _rewrite)

    org = two_orgs["a"]["org"]
    user, h = await _member(db_session, org, email="d@example.com")
    src_conn = DataSource(name="Warehouse", type="postgresql", org_id=org.id,
                          config={"host": "h", "port": 5432, "database": "d",
                                  "username": "u", "password": "p"})
    db_session.add(src_conn)
    await db_session.flush()
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders",
                  data_source_id=src_conn.id, created_by=user.id)
    db_session.add(src)
    await db_session.flush()
    db_session.add_all([DatasetColumn(dataset_id=src.id, name="region", dtype="categorical"),
                        DatasetColumn(dataset_id=src.id, name="amount", dtype="numeric")])
    await db_session.commit()
    body = {"name": "by region", "grain": ["region"], "measures": [{"column": "amount", "agg": "sum"}]}

    await _deny(db_session, user, upload_data=False)
    r = await client.post(f"/api/v1/datasets/{src.id}/aggregates", json=body, headers=h)
    assert r.status_code == 403, r.text
    assert "upload data" in r.json()["detail"]

    await _deny(db_session, user, upload_data=True)
    r = await client.post(f"/api/v1/datasets/{src.id}/aggregates", json=body, headers=h)
    assert r.status_code == 201, r.text


async def test_a_dataflow_run_that_creates_an_output_needs_add_data_a_refresh_does_not(
        client, db_session, two_orgs, _uploads):
    org = two_orgs["a"]["org"]
    user, h = await _member(db_session, org, email="d@example.com")
    ds = await _csv_dataset(db_session, org, _uploads, user)
    made = await client.post("/api/v1/dataflows", headers=h,
                             json={"name": "Nightly", "source_dataset_id": ds.id, "steps": []})
    assert made.status_code == 201, made.text
    fid = made.json()["id"]
    first = await client.post(f"/api/v1/dataflows/{fid}/run", json={"output_name": "Out"}, headers=h)
    assert first.status_code == 200, first.text

    await _deny(db_session, user, upload_data=False)
    before = await _datasets(db_session, org)
    r = await client.post(f"/api/v1/dataflows/{fid}/run", json={"output_name": "Another"}, headers=h)
    assert r.status_code == 403, r.text
    assert "upload data" in r.json()["detail"]
    assert await _datasets(db_session, org) == before
    # Re-running what is already authored is not a new dataset.
    r = await client.post(f"/api/v1/dataflows/{fid}/run", json={}, headers=h)
    assert r.status_code == 200, r.text
    assert await _datasets(db_session, org) == before


async def test_batch_scoring_into_a_new_dataset_needs_add_data(client, db_session, two_orgs, tmp_path):
    import numpy as np
    org = two_orgs["a"]["org"]
    user, h = await _member(db_session, org, email="d@example.com")
    rng = np.random.default_rng(0)
    region = rng.choice(["North", "South", "East"], 300)
    spend = rng.normal(100, 20, 300).round(2)
    churn = np.where((region == "North") | (spend > 120), "yes", "no")
    p = tmp_path / "churn.csv"
    pd.DataFrame({"region": region, "spend": spend, "churn": churn}).to_csv(p, index=False)
    ds = Dataset(name="Churn", filename=str(p), org_id=org.id, mode="import", created_by=user.id)
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("region", "categorical"), ("spend", "numeric"), ("churn", "categorical")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()
    model = await client.post(f"/api/v1/datasets/{ds.id}/prediction-models",
                              json={"name": "M", "target": "churn"}, headers=h)
    assert model.status_code == 201, model.text
    await _deny(db_session, user, upload_data=False)
    r = await client.post(f"/api/v1/datasets/{ds.id}/prediction-models/{model.json()['id']}/score-jobs",
                          headers=h)
    assert r.status_code == 403, r.text
    assert "upload data" in r.json()["detail"]


# ── automation-composed dashboards need create_dashboard ────────────────────

async def test_an_automated_analysis_is_refused_at_start_without_create_dashboard(
        client, db_session, two_orgs, _uploads):
    org = two_orgs["a"]["org"]
    user, h = await _member(db_session, org, perms={"create_dashboard": False}, email="d@example.com")
    ds = await _csv_dataset(db_session, org, _uploads, user)
    r = await client.post("/api/v1/automation/runs", json={"dataset_id": ds.id}, headers=h)
    assert r.status_code == 403, r.text
    assert "create dashboards" in r.json()["detail"]
    # An allowed role starts one as before.
    other, h2 = await _member(db_session, org, perms={"export": False}, email="ok@example.com")
    ds2 = await _csv_dataset(db_session, org, _uploads, other, name="Theirs")
    assert (await client.post("/api/v1/automation/runs", json={"dataset_id": ds2.id},
                              headers=h2)).status_code == 201


async def test_the_compose_step_checks_the_creators_role_at_run_time(db_session, two_orgs, _uploads):
    """Started while allowed, the role lost the right before step 6: the
    step fails with the readable reason and writes no dashboard."""
    org = two_orgs["a"]["org"]
    user, _ = await _member(db_session, org, email="d@example.com")
    ds = await _csv_dataset(db_session, org, _uploads, user)
    run = await runner.create_run(db_session, org_id=org.id, created_by=user.id, trigger="manual",
                                  subject_type="dataset", subject_id=ds.id)
    await _deny(db_session, user, create_dashboard=False)
    ctx = runner.StepContext(run_id=run.id, org_id=org.id, user_id=user.id, user_email=user.email,
                             trigger="manual", subject_type="dataset", subject_id=ds.id,
                             step_name="compose")
    with pytest.raises(runner.StepRefused) as e:
        await runner._compose_step(ctx, db_session)
    assert "not allowed to create dashboards" in str(e.value)
    assert (await db_session.execute(select(Report).where(Report.org_id == org.id))).first() is None


# ── demo seeding is an org-admin action ─────────────────────────────────────

async def test_demo_seeding_is_for_org_admins_only(client, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    _, h = await _member(db_session, org, email="m@example.com")   # every capability
    assert (await client.post("/api/v1/demo/seed", headers=h)).status_code == 403
    assert (await client.delete("/api/v1/demo/seed", headers=h)).status_code == 403
    assert await _datasets(db_session, org) == []


# ── publishing: no capability of its own (accepted limitation) ──────────────

async def test_publishing_stays_with_the_author_and_honours_approval_whatever_the_role(
        client, db_session, two_orgs, auth_headers):
    """A role stripped of every capability can still publish a dashboard it
    authored (e.g. made before the change, or handed to it) -- there is no
    publish capability -- but only its own, and only through approval where
    the organisation asks for it."""
    org = two_orgs["a"]["org"]
    author, ha = await _member(db_session, org, perms={c: False for c in ALL}, email="au@example.com")
    editor, he = await _member(db_session, org, email="ed@example.com")
    rep = Report(name="Mine", org_id=org.id, created_by=author.id)
    db_session.add(rep)
    await db_session.flush()
    page = ReportPage(report_id=rep.id, name="P", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=page.id, widget_type="text", title="t", config={}, layout={}))
    db_session.add(OrgReviewSettings(org_id=org.id, require_approval=True))
    await db_session.commit()
    g = await client.post(f"/api/v1/reports/{rep.id}/grants", json={"email": editor.email, "level": "edit"},
                          headers=ha)
    assert g.status_code in (200, 201), g.text

    pub = {"published": True}
    # Edit rights are not publishing rights.
    assert (await client.post(f"/api/v1/reports/{rep.id}/publish", json=pub, headers=he)).status_code == 403
    # The author waits for an administrator's approval.
    r = await client.post(f"/api/v1/reports/{rep.id}/publish", json=pub, headers=ha)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "approval_needed"
    assert (await client.post(f"/api/v1/reports/{rep.id}/review/request", json={"note": "ready"},
                              headers=ha)).status_code == 200
    assert (await client.post(f"/api/v1/reports/{rep.id}/review/decision", json={"approve": True},
                              headers=auth_headers["a"])).json()["state"] == "approved"
    r = await client.post(f"/api/v1/reports/{rep.id}/publish", json=pub, headers=ha)
    assert r.status_code == 200 and r.json()["published"] is True
