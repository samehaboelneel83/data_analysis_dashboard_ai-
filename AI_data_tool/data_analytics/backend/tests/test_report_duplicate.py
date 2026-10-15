"""C-20: "Duplicate" on a dashboard card -- a full, independent, private copy."""
import pytest
from sqlalchemy import select

from app.models.models import Bookmark, Report, ReportWidget

pytestmark = pytest.mark.asyncio


async def _report_with_content(client, headers):
    r = await client.post("/api/v1/reports", json={"name": "Sales"}, headers=headers)
    assert r.status_code == 201, r.text
    rep = r.json()
    r = await client.patch(f"/api/v1/reports/{rep['id']}", json={"theme": "ocean"}, headers=headers)
    assert r.status_code == 200, r.text
    page_id = rep["pages"][0]["id"]
    base = f"/api/v1/reports/{rep['id']}/pages/{page_id}/widgets"
    box = (await client.post(base, json={"widget_type": "container", "title": "Box", "config": {},
                                          "layout": {"x": 0, "y": 0, "w": 6, "h": 4}}, headers=headers)).json()
    kid = (await client.post(base, json={"widget_type": "text", "title": "Inside",
                                          "config": {"content": "hi", "container_id": box["id"]},
                                          "layout": {"x": 0, "y": 0, "w": 3, "h": 3}}, headers=headers)).json()
    r = await client.post(f"/api/v1/reports/{rep['id']}/bookmarks",
                          json={"name": "Start", "state": {"pageId": page_id}}, headers=headers)
    assert r.status_code in (200, 201), r.text
    return rep, page_id, box, kid


async def test_the_copy_is_complete_new_and_rewired(client, auth_headers, db_session):
    rep, page_id, box, kid = await _report_with_content(client, auth_headers["a"])
    r = await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={}, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    copy = r.json()
    assert copy["id"] != rep["id"]
    assert copy["name"] == "Sales (copy)"
    assert copy["theme"] == "ocean"
    assert copy["published"] is False
    [page] = copy["pages"]
    assert page["id"] != page_id
    by_title = {w["title"]: w for w in page["widgets"]}
    assert {by_title["Box"]["id"], by_title["Inside"]["id"]}.isdisjoint({box["id"], kid["id"]})
    # The child sits in the COPY's container, not the original's.
    assert by_title["Inside"]["config"]["container_id"] == by_title["Box"]["id"]
    row = await db_session.get(Report, copy["id"])
    assert row.created_by == (await db_session.get(Report, rep["id"])).created_by
    marks = (await db_session.execute(select(Bookmark).where(Bookmark.report_id == copy["id"]))).scalars().all()
    assert [m.state["pageId"] for m in marks] == [page["id"]]
    # The original is untouched.
    orig = (await db_session.execute(select(ReportWidget).where(ReportWidget.id == kid["id"]))).scalar_one()
    assert orig.config["container_id"] == box["id"]


async def test_a_name_can_be_given(client, auth_headers):
    rep, *_ = await _report_with_content(client, auth_headers["a"])
    r = await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={"name": "Q3 draft"},
                          headers=auth_headers["a"])
    assert r.status_code == 201 and r.json()["name"] == "Q3 draft"


async def test_someone_who_cannot_open_it_cannot_copy_it(client, auth_headers):
    rep, *_ = await _report_with_content(client, auth_headers["a"])
    r = await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={}, headers=auth_headers["b"])
    assert r.status_code == 404
