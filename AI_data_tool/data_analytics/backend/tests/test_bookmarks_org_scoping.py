from app.models.models import Report, Bookmark


async def _seed_report(db_session, org_id, name="Test Report"):
    r = Report(name=name, org_id=org_id)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_create_and_list_bookmark(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    report = await _seed_report(db_session, org_id)

    resp = await client.post(f"/api/v1/reports/{report.id}/bookmarks",
        json={"name": "Q1 view", "position": 0,
              "state": {"pageId": 1, "activeFilters": [], "promptValues": {}, "hiddenWidgetIds": []}},
        headers=auth_headers["a"])
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/reports/{report.id}/bookmarks", headers=auth_headers["a"])
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Q1 view"


async def test_bookmark_endpoints_cross_org_report_404(client, db_session, two_orgs, auth_headers):
    org_a_report = await _seed_report(db_session, two_orgs["a"]["org"].id)

    resp = await client.get(f"/api/v1/reports/{org_a_report.id}/bookmarks", headers=auth_headers["b"])
    assert resp.status_code == 404

    resp = await client.post(f"/api/v1/reports/{org_a_report.id}/bookmarks",
        json={"name": "X", "position": 0, "state": {}}, headers=auth_headers["b"])
    assert resp.status_code == 404


async def test_delete_bookmark_cross_org_404(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["b"]["org"].id
    report = await _seed_report(db_session, org_id)
    bm = Bookmark(report_id=report.id, name="Q1 view", position=0, state={})
    db_session.add(bm)
    await db_session.commit()
    await db_session.refresh(bm)

    resp = await client.delete(f"/api/v1/reports/{report.id}/bookmarks/{bm.id}", headers=auth_headers["a"])
    assert resp.status_code == 404
