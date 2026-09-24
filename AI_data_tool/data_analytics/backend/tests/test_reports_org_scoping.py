from sqlalchemy import select
from app.models.models import Report, ReportPage, ReportWidget


async def _seed_report(db_session, org_id, name="Test Report"):
    r = Report(name=name, org_id=org_id)
    db_session.add(r)
    await db_session.flush()
    db_session.add(ReportPage(report_id=r.id, name="Page 1", position=0))
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def _seed_widget(db_session, report_id, widget_type="bar"):
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == report_id))
    page = result.scalars().first()
    w = ReportWidget(page_id=page.id, widget_type=widget_type, config={})
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def test_list_reports_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    await _seed_report(db_session, two_orgs["a"]["org"].id, "A's report")
    await _seed_report(db_session, two_orgs["b"]["org"].id, "B's report")

    resp = await client.get("/api/v1/reports", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert names == ["A's report"]


async def test_get_report_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_create_report_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers):
    resp = await client.post("/api/v1/reports", json={"name": "New Report"}, headers=auth_headers["a"])

    assert resp.status_code == 201
    result = await db_session.execute(select(Report).where(Report.id == resp.json()["id"]))
    r = result.scalar_one()
    assert r.org_id == two_orgs["a"]["org"].id


async def test_delete_report_cross_org_returns_404_and_does_not_delete(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)

    resp = await client.delete(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
    result = await db_session.execute(select(Report).where(Report.id == r.id))
    assert result.scalar_one_or_none() is not None


async def test_add_page_to_cross_org_report_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/reports/{r.id}/pages", json={"name": "Page 2"}, headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_update_page_on_cross_org_report_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.patch(
        f"/api/v1/reports/{r.id}/pages/{page.id}", json={"name": "Renamed"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_add_widget_to_cross_org_report_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.post(
        f"/api/v1/reports/{r.id}/pages/{page.id}/widgets",
        json={"widget_type": "bar", "config": {}},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_same_org_page_and_widget_operations_still_work(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["a"]["org"].id)

    page_resp = await client.post(f"/api/v1/reports/{r.id}/pages", json={"name": "Page 2"}, headers=auth_headers["a"])
    assert page_resp.status_code == 201
    page_id = page_resp.json()["id"]

    widget_resp = await client.post(
        f"/api/v1/reports/{r.id}/pages/{page_id}/widgets",
        json={"widget_type": "bar", "config": {}},
        headers=auth_headers["a"],
    )
    assert widget_resp.status_code == 201


async def test_delete_page_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.delete(f"/api/v1/reports/{r.id}/pages/{page.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_update_widget_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    widget = await _seed_widget(db_session, r.id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.patch(
        f"/api/v1/reports/{r.id}/pages/{page.id}/widgets/{widget.id}",
        json={"title": "Renamed"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_delete_widget_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    r = await _seed_report(db_session, two_orgs["b"]["org"].id)
    widget = await _seed_widget(db_session, r.id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r.id))
    page = result.scalar_one()

    resp = await client.delete(
        f"/api/v1/reports/{r.id}/pages/{page.id}/widgets/{widget.id}",
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_widget_mismatched_page_and_report_ids_returns_404(client, db_session, two_orgs, auth_headers):
    """Reproduces the specific IDOR: org A supplies THEIR OWN report_id (which
    passes check_org on the parent Report) in the URL, but pairs it with org B's
    REAL page_id/widget_id (a validly-related page+widget, just under a
    different report). Without verifying that page_id is actually a descendant
    of report_id, a query that only filters by ReportWidget.page_id ==
    page_id (ignoring report_id) would incorrectly find and mutate/delete the
    victim's widget."""
    r_a = await _seed_report(db_session, two_orgs["a"]["org"].id)

    r_b = await _seed_report(db_session, two_orgs["b"]["org"].id)
    result = await db_session.execute(select(ReportPage).where(ReportPage.report_id == r_b.id))
    page_b = result.scalar_one()
    widget_b = await _seed_widget(db_session, r_b.id)

    update_resp = await client.patch(
        f"/api/v1/reports/{r_a.id}/pages/{page_b.id}/widgets/{widget_b.id}",
        json={"title": "Hijacked"},
        headers=auth_headers["a"],
    )
    assert update_resp.status_code == 404

    delete_resp = await client.delete(
        f"/api/v1/reports/{r_a.id}/pages/{page_b.id}/widgets/{widget_b.id}",
        headers=auth_headers["a"],
    )
    assert delete_resp.status_code == 404

    # the victim's widget must genuinely survive both attempts
    result = await db_session.execute(select(ReportWidget).where(ReportWidget.id == widget_b.id))
    assert result.scalar_one_or_none() is not None
