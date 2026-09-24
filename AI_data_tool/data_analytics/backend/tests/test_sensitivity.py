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
    # Unlabelled: the anonymous link works and shows the email column.
    anon = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")
    assert anon.status_code == 200 and "email" in str(anon.json())
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
