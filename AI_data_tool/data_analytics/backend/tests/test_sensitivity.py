"""Phase 7.3: sensitivity labels that propagate and enforce, and batch
authorization decisions that explain themselves."""
import pandas as pd
import pytest

from app.models.models import (Dataset, DatasetColumn, Report, ReportClassification, ReportPage,
                               ReportWidget)


@pytest.fixture
def people(tmp_path):
    p = tmp_path / "people.csv"
    pd.DataFrame({"name": ["A", "B"], "email": ["a@x.com", "b@x.com"], "spend": [1.0, 2.0]}).to_csv(p, index=False)
    return str(p)


async def _world(db, org, path, *, ds_label=None, joined_label=None):
    base = Dataset(name="People", filename=path, org_id=org.id, mode="import",
                   column_meta={"__sensitivity__": ds_label} if ds_label else {})
    db.add(base)
    await db.flush()
    for c, sem in (("name", None), ("email", "email"), ("spend", None)):
        db.add(DatasetColumn(dataset_id=base.id, name=c, dtype="categorical", semantic_type=sem))
    other = None
    if joined_label:
        other = Dataset(name="Payroll", filename=path, org_id=org.id, mode="import",
                        column_meta={"__sensitivity__": joined_label})
        db.add(other)
        await db.flush()
        base.column_meta = {**(base.column_meta or {}), "__prep_steps__": [
            {"kind": "join", "dataset_id": other.id, "how": "left", "left_on": "name", "right_on": "name"}]}
    rep = Report(name="People report", dataset_id=base.id, org_id=org.id)
    db.add(rep)
    await db.flush()
    page = ReportPage(report_id=rep.id, name="P1", position=0)
    db.add(page)
    await db.flush()
    w = ReportWidget(page_id=page.id, widget_type="table", config={"columns": ["name", "email", "spend"]})
    db.add(w)
    await db.commit()
    return base, other, rep, w


@pytest.mark.asyncio
async def test_a_join_carries_its_label_and_the_report_cannot_claim_less(client, auth_headers, db_session, two_orgs, people):
    base, other, rep, _ = await _world(db_session, two_orgs["a"]["org"], people, joined_label="Confidential")
    s = (await client.get(f"/api/v1/datasets/{base.id}/sensitivity", headers=auth_headers["a"])).json()
    assert s["label"] is None and s["effective"] == "Confidential"
    assert "joins data labelled Confidential" in s["reasons"][0]
    assert s["redacted_on_share"] == ["email"]
    r = await client.put(f"/api/v1/reports/{rep.id}/classification", json={"label": "Internal"}, headers=auth_headers["a"])
    assert r.status_code == 400 and "lowest it can carry is Confidential" in r.json()["detail"]
    r = await client.put(f"/api/v1/reports/{rep.id}/classification", json={"label": "Restricted"}, headers=auth_headers["a"])
    assert r.status_code == 200
    c = (await client.get(f"/api/v1/reports/{rep.id}/classification", headers=auth_headers["a"])).json()
    assert c["floor"] == "Confidential" and c["effective"] == "Restricted"


@pytest.mark.asyncio
async def test_confidential_links_need_a_signed_in_member_and_redact_personal_data(
        client, auth_headers, db_session, two_orgs, people):
    base, _, rep, w = await _world(db_session, two_orgs["a"]["org"], people)
    token = (await client.post(f"/api/v1/reports/{rep.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    # Unlabelled, but it holds an email column: personal data makes it
    # Confidential by itself (live QA 2026-09-28 -- a call log's national IDs
    # sat under no label at all).
    s = (await client.get(f"/api/v1/datasets/{base.id}/sensitivity", headers=auth_headers["a"])).json()
    assert s["label"] is None and s["effective"] == "Confidential"
    assert s["reasons"] == ["People holds personal data (email)"]
    r = await client.put(f"/api/v1/datasets/{base.id}/sensitivity", json={"label": "Confidential"},
                         headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["effective"] == "Confidential"
    assert (await client.get(f"/api/v1/shared/{token}")).status_code == 403
    assert (await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")).status_code == 403
    member = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}", headers=auth_headers["a"])
    assert member.status_code == 200
    body = str(member.json())
    assert "a@x.com" not in body and "spend" in body


@pytest.mark.asyncio
async def test_data_without_personal_columns_stays_openable_by_link(client, auth_headers, db_session, two_orgs, tmp_path):
    path = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["N", "S"], "spend": [1.0, 2.0]}).to_csv(path, index=False)
    org = two_orgs["a"]["org"]
    ds = Dataset(name="Sales", filename=str(path), org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for c in ("region", "spend"):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    rep = Report(name="Sales report", dataset_id=ds.id, org_id=org.id)
    db_session.add(rep)
    await db_session.flush()
    page = ReportPage(report_id=rep.id, name="P1", position=0)
    db_session.add(page)
    await db_session.flush()
    w = ReportWidget(page_id=page.id, widget_type="table", config={"columns": ["region", "spend"]})
    db_session.add(w)
    await db_session.commit()
    s = (await client.get(f"/api/v1/datasets/{ds.id}/sensitivity", headers=auth_headers["a"])).json()
    assert s["effective"] is None and s["redacted_on_share"] == []
    token = (await client.post(f"/api/v1/reports/{rep.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    anon = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")
    assert anon.status_code == 200 and "spend" in str(anon.json())


@pytest.mark.asyncio
async def test_restricted_blocks_links_and_says_why(client, auth_headers, db_session, two_orgs, people):
    _, _, rep, _ = await _world(db_session, two_orgs["a"]["org"], people, ds_label="Restricted")
    r = await client.post(f"/api/v1/reports/{rep.id}/share-links", json={}, headers=auth_headers["a"])
    assert r.status_code == 403 and "People is labelled Restricted" in r.json()["detail"]


@pytest.mark.asyncio
async def test_batch_decisions_explain_themselves(client, auth_headers, db_session, two_orgs, people):
    base, _, rep, _ = await _world(db_session, two_orgs["a"]["org"], people, ds_label="Restricted")
    checks = [{"resource": "report", "id": rep.id, "action": "edit"},
              {"resource": "report", "id": rep.id, "action": "share_link"},
              {"resource": "report", "id": rep.id, "action": "download"},
              {"resource": "dataset", "id": base.id, "action": "read_column", "column": "email"}]
    got = (await client.post("/api/v1/authz/decisions", json={"checks": checks}, headers=auth_headers["a"])).json()["decisions"]
    assert [d["allowed"] for d in got] == [True, False, True, True]
    assert "organisation admin" in got[0]["reason"]
    assert "Restricted" in got[1]["reason"] and got[1]["sensitivity"] == "Restricted"
    other = (await client.post("/api/v1/authz/decisions", json={"checks": checks[:1]}, headers=auth_headers["b"])).json()
    assert other["decisions"][0]["allowed"] is False
    too_many = await client.post("/api/v1/authz/decisions", json={"checks": checks * 13}, headers=auth_headers["a"])
    assert too_many.status_code == 400


@pytest.mark.asyncio
async def test_analysis_rows_mask_personal_columns_for_an_analyst_not_for_an_admin(
        client, auth_headers, db_session, two_orgs, tmp_path):
    """Live QA 2026-09-28: an analyst's outlier drill-down on a call log
    returned its callers' names, addresses and national IDs in full."""
    from .test_prediction_models_api import _restricted_user
    path = tmp_path / "calls.csv"
    n = 40
    pd.DataFrame({
        "B_NUMBER_FIRST_NAME": [f"Name{i}" for i in range(n)],
        "B_NUMBER_NATIONAL_ID": [f"2901028140{i:04d}" for i in range(n)],
        "SITE_ADDRESS": [f"Tower {i}" for i in range(n)],               # a place, not a person
        "RATED_AMOUNT": [1.0] * (n - 1) + [500.0],
    }).to_csv(path, index=False)
    org = two_orgs["a"]["org"]
    ds = Dataset(name="Calls", filename=str(path), org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("B_NUMBER_FIRST_NAME", "categorical"), ("B_NUMBER_NATIONAL_ID", "categorical"),
                 ("SITE_ADDRESS", "categorical"), ("RATED_AMOUNT", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()
    analyst = await _restricted_user(db_session, org, ds, email="analyst@example.com")

    def outlier_row(body):
        cols, [row] = body["outliers"]["columns"], body["outliers"]["rows"]
        return dict(zip(cols, row))

    url = f"/api/v1/datasets/{ds.id}/outlier-details?column=RATED_AMOUNT"
    seen = outlier_row((await client.post(url, headers=analyst)).json())
    assert seen["B_NUMBER_FIRST_NAME"] != "Name39" and seen["B_NUMBER_FIRST_NAME"].startswith("masked_")
    assert seen["B_NUMBER_NATIONAL_ID"] != "29010281400039"
    assert seen["SITE_ADDRESS"] == "Tower 39" and seen["RATED_AMOUNT"] == 500.0
    admin = outlier_row((await client.post(url, headers=auth_headers["a"])).json())
    assert admin["B_NUMBER_FIRST_NAME"] == "Name39"

    r = await client.post(f"/api/v1/datasets/{ds.id}/quality", json={"rules": ["RATED_AMOUNT < 100"]},
                          headers=analyst)
    [example] = r.json()["rules"][0]["examples"]
    assert example["B_NUMBER_FIRST_NAME"].startswith("masked_") and example["RATED_AMOUNT"] == 500.0
