"""Phase 7.4: report quality as CI -- server-side review errors, Evaluate
Performance, and the org's optional publish gate."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn, Report, ReportPage, ReportWidget, User
from app.services.report_review import high_findings


def test_high_findings_match_the_panes_errors():
    pages = [{"id": 1, "name": "P1", "widgets": [
        {"id": 10, "widget_type": "bar", "title": "", "config": {"dimension": "r"}},
        {"id": 11, "widget_type": "bar", "title": "Unfinished", "config": {}},
        {"id": 12, "widget_type": "image", "title": "Logo", "config": {}},
        {"id": 13, "widget_type": "bar", "title": "Wired", "config": {"dimension": "r", "interaction": {
            "actions": [{"targetId": 99, "mode": "filter"}, {"targetId": 20, "mode": "filter"}]}}},
    ]}, {"id": 2, "name": "P2", "widgets": [
        {"id": 20, "widget_type": "bar", "title": "Other page", "config": {"dimension": "r"}}]}]
    msgs = [f["message"] for f in high_findings(pages)]
    assert any("Untitled bar has no alt text" in m for m in msgs)
    assert any('"Unfinished" is unfinished' in m for m in msgs)
    assert any(m == "Image has no alt text" for m in msgs)
    assert any("no longer exists (#99)" in m for m in msgs)
    assert any("not set to sync across pages" in m for m in msgs)
    assert not any('"Other page"' in m for m in msgs)


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({"region": ["N", "S"], "amount": [1.0, 2.0]}).to_csv(p, index=False)
    return str(p)


async def _report(db, org, path, user_id, *, broken=True):
    ds = Dataset(name="S", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c in ("region", "amount"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    rep = Report(name="R", dataset_id=ds.id, org_id=org.id, created_by=user_id)
    db.add(rep)
    await db.flush()
    page = ReportPage(report_id=rep.id, name="P1", position=0)
    db.add(page)
    await db.flush()
    db.add(ReportWidget(page_id=page.id, widget_type="bar", title="Sales",
                        config={"dimension": "region", "measure": "amount"}))
    if broken:
        db.add(ReportWidget(page_id=page.id, widget_type="bar", title="", config={}))
    await db.commit()
    return rep


@pytest.mark.asyncio
async def test_the_gate_blocks_publishing_only_when_on_and_errors_are_open(
        client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    admin = (await db_session.execute(User.__table__.select().where(User.org_id == org.id))).first()
    rep = await _report(db_session, org, salesfile, admin.id)
    h = auth_headers["a"]
    review = (await client.get(f"/api/v1/reports/{rep.id}/review", headers=h)).json()
    assert review["publish_gate"] is False and len(review["findings"]) >= 2
    # gate off: publishing works as before
    assert (await client.post(f"/api/v1/reports/{rep.id}/publish", json={"published": True}, headers=h)).status_code == 200
    await client.post(f"/api/v1/reports/{rep.id}/publish", json={"published": False}, headers=h)
    assert (await client.put("/api/v1/review-settings", json={"publish_gate": True}, headers=h)).json() == {"publish_gate": True}
    r = await client.post(f"/api/v1/reports/{rep.id}/publish", json={"published": True}, headers=h)
    assert r.status_code == 409
    assert "review error" in r.json()["detail"]["message"] and r.json()["detail"]["findings"]
    # unpublishing is never blocked
    assert (await client.post(f"/api/v1/reports/{rep.id}/publish", json={"published": False}, headers=h)).status_code == 200
    # another org's admin cannot flip this org's gate, and non-admins cannot at all
    assert (await client.get("/api/v1/review-settings", headers=auth_headers["b"])).json() == {"publish_gate": False}


@pytest.mark.asyncio
async def test_evaluate_performance_ranks_widgets_and_reads_history(
        client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    admin = (await db_session.execute(User.__table__.select().where(User.org_id == org.id))).first()
    rep = await _report(db_session, org, salesfile, admin.id, broken=False)
    got = (await client.post(f"/api/v1/reports/{rep.id}/evaluate-performance", headers=auth_headers["a"])).json()
    assert len(got["widgets"]) == 1 and got["widgets"][0]["title"] == "Sales"
    assert got["widgets"][0]["rows"] == 2 and got["widgets"][0]["error"] is None
    assert str(rep.dataset_id) in got["history"]
    assert (await client.post(f"/api/v1/reports/{rep.id}/evaluate-performance",
                              headers=auth_headers["b"])).status_code == 404


def test_model_widgets_with_their_own_role_keys_are_not_called_unfinished():
    from app.services.widget_roles import missing_roles
    assert missing_roles("model_linear", {"measure": "revenue", "predictors": ["units"]}) == []
    assert missing_roles("model_tree", {"response": "category"}) == []
    assert missing_roles("model_linear", {"measure": "revenue", "predictors": []}) == ["predictors"]
