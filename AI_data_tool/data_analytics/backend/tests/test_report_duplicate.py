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


# ── C-20 round 2: the copy is filed beside the original ──────────────────────
async def _folder(client, headers, name="Team", **extra):
    r = await client.post("/api/v1/workspace/nodes", json={"node_type": "folder", "name": name}, headers=headers)
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    if extra:
        r = await client.patch(f"/api/v1/workspace/nodes/{fid}", json=extra, headers=headers)
        assert r.status_code == 200, r.text
    return fid


async def _file(client, headers, report_id, folder_id):
    r = await client.post("/api/v1/workspace/nodes", json={"node_type": "report", "report_id": report_id,
                                                           "parent_id": folder_id}, headers=headers)
    assert r.status_code == 201, r.text


async def _node_of(db_session, report_id):
    from app.models.models import WorkspaceNode
    return (await db_session.execute(select(WorkspaceNode).where(WorkspaceNode.report_id == report_id))).scalars().first()


async def test_the_copy_lands_in_the_originals_folder(client, auth_headers, db_session):
    h = auth_headers["a"]
    rep, *_ = await _report_with_content(client, h)
    fid = await _folder(client, h)
    await _file(client, h, rep["id"], fid)
    copy = (await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={}, headers=h)).json()
    node = await _node_of(db_session, copy["id"])
    assert node is not None and node.parent_id == fid


async def test_an_unfiled_original_gives_an_unfiled_copy(client, auth_headers, db_session):
    h = auth_headers["a"]
    rep, *_ = await _report_with_content(client, h)
    copy = (await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={}, headers=h)).json()
    assert await _node_of(db_session, copy["id"]) is None


async def test_a_published_folder_does_not_publish_the_private_copy(client, auth_headers, db_session):
    # Filing under a published folder publishes what is filed: the copy is a
    # private draft, so it stays unfiled (at the root) instead.
    h = auth_headers["a"]
    rep, *_ = await _report_with_content(client, h)
    fid = await _folder(client, h, published=True)
    await _file(client, h, rep["id"], fid)
    copy = (await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={}, headers=h)).json()
    assert await _node_of(db_session, copy["id"]) is None


async def test_a_shared_folder_does_not_share_the_private_copy(client, auth_headers, db_session):
    from app.models.models import WorkspaceFolderGrant, WorkspaceNode, User
    h = auth_headers["a"]
    rep, *_ = await _report_with_content(client, h)
    fid = await _folder(client, h)
    await _file(client, h, rep["id"], fid)
    other = (await db_session.execute(select(User).where(User.id != rep.get("created_by", 0)))).scalars().first()
    folder = await db_session.get(WorkspaceNode, fid)
    db_session.add(WorkspaceFolderGrant(org_id=folder.org_id, node_id=fid, user_id=other.id, level="view"))
    await db_session.commit()
    copy = (await client.post(f"/api/v1/reports/{rep['id']}/duplicate", json={}, headers=h)).json()
    assert await _node_of(db_session, copy["id"]) is None
