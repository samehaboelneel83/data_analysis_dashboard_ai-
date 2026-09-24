"""Page templates: serialise, rehydrate, and the import that is both at once."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import ReportPage


async def _page_widgets(db, page_id):
    page = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.id == page_id)
    )).scalar_one()
    return sorted(page.widgets, key=lambda w: w.id)


async def _report_with_container_page(client, headers):
    r = await client.post("/api/v1/reports", json={"name": "Tpl src"}, headers=headers)
    rid = r.json()["id"]
    page_id = (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"][0]["id"]

    cont = await client.post(f"/api/v1/reports/{rid}/pages/{page_id}/widgets",
                             json={"widget_type": "container", "title": "Tabs",
                                   "config": {"container_mode": "tabs"},
                                   "layout": {"x": 0, "y": 0, "w": 6, "h": 6}}, headers=headers)
    cont_id = cont.json()["id"]
    await client.post(f"/api/v1/reports/{rid}/pages/{page_id}/widgets",
                      json={"widget_type": "text", "title": "Child",
                            "config": {"content": "inside", "container_id": cont_id},
                            "layout": {"x": 0, "y": 0, "w": 6, "h": 3}}, headers=headers)
    return rid, page_id, cont_id


@pytest.mark.asyncio
async def test_template_round_trip_remaps_container_references(client, auth_headers, db_session):
    """THE template correctness case: a child's container_id must point at the NEW
    container after instantiation, not at the source page's widget id -- ids are
    meaningless outside the page they came from."""
    rid, page_id, old_cont_id = await _report_with_container_page(client, auth_headers["a"])

    saved = await client.post(f"/api/v1/reports/{rid}/pages/{page_id}/save-as-template",
                              json={"name": "My layout"}, headers=auth_headers["a"])
    assert saved.status_code == 201, saved.text

    made = await client.post(f"/api/v1/reports/{rid}/pages/from-template",
                             json={"template_id": saved.json()["id"]}, headers=auth_headers["a"])
    assert made.status_code == 201, made.text

    widgets = await _page_widgets(db_session, made.json()["page_id"])
    new_cont = next(w for w in widgets if w.widget_type == "container")
    new_child = next(w for w in widgets if w.widget_type == "text")
    assert new_child.config["container_id"] == new_cont.id
    assert new_child.config["container_id"] != old_cont_id


@pytest.mark.asyncio
async def test_importing_a_page_from_another_report(client, auth_headers, db_session):
    rid_src, page_src, _ = await _report_with_container_page(client, auth_headers["a"])
    r = await client.post("/api/v1/reports", json={"name": "Tpl dst"}, headers=auth_headers["a"])
    rid_dst = r.json()["id"]

    made = await client.post(f"/api/v1/reports/{rid_dst}/pages/from-template",
                             json={"source_report_id": rid_src, "source_page_id": page_src},
                             headers=auth_headers["a"])
    assert made.status_code == 201, made.text
    widgets = await _page_widgets(db_session, made.json()["page_id"])
    assert {w.widget_type for w in widgets} == {"container", "text"}


@pytest.mark.asyncio
async def test_a_builtin_template_instantiates(client, auth_headers, db_session):
    r = await client.post("/api/v1/reports", json={"name": "B"}, headers=auth_headers["a"])
    rid = r.json()["id"]
    listed = (await client.get("/api/v1/reports/templates/builtin", headers=auth_headers["a"])).json()
    assert any(t["key"] == "kpi-strip" for t in listed)

    made = await client.post(f"/api/v1/reports/{rid}/pages/from-template",
                             json={"builtin": "kpi-strip"}, headers=auth_headers["a"])
    assert made.status_code == 201
    widgets = await _page_widgets(db_session, made.json()["page_id"])
    assert len(widgets) == 6


@pytest.mark.asyncio
async def test_another_orgs_report_cannot_be_imported_from(client, auth_headers):
    """Both ends are org-checked: the import path must not become a cross-org read."""
    rid_src, page_src, _ = await _report_with_container_page(client, auth_headers["a"])
    r = await client.post("/api/v1/reports", json={"name": "B side"}, headers=auth_headers["b"])
    rid_b = r.json()["id"]

    made = await client.post(f"/api/v1/reports/{rid_b}/pages/from-template",
                             json={"source_report_id": rid_src, "source_page_id": page_src},
                             headers=auth_headers["b"])
    assert made.status_code == 404


@pytest.mark.asyncio
async def test_templates_are_org_scoped(client, auth_headers):
    rid, page_id, _ = await _report_with_container_page(client, auth_headers["a"])
    await client.post(f"/api/v1/reports/{rid}/pages/{page_id}/save-as-template",
                      json={"name": "A only"}, headers=auth_headers["a"])
    listed_b = (await client.get("/api/v1/reports/templates/page", headers=auth_headers["b"])).json()
    assert listed_b == []


# ── Managing them ────────────────────────────────────────────────────────────
#
# A saved page template had no way out: no delete endpoint, no delete control,
# nothing. A name typed wrong, a layout that turned out to be a bad idea, a
# template built from a page that has since changed -- all of them permanent,
# in a list every author in the org sees. SAS's template dialog has "Manage
# Templates" for exactly this.

async def _template_from_a_page(client, headers) -> int:
    report_id, page_id, _ = await _report_with_container_page(client, headers)
    saved = await client.post(
        f"/api/v1/reports/{report_id}/pages/{page_id}/save-as-template",
        json={"name": "Quarterly layout"}, headers=headers)
    assert saved.status_code == 201, saved.text
    return saved.json()["id"]


@pytest.mark.asyncio
async def test_a_saved_template_can_be_deleted(client, auth_headers):
    tpl = await _template_from_a_page(client, auth_headers["a"])
    r = await client.delete(f"/api/v1/reports/templates/page/{tpl}", headers=auth_headers["a"])
    assert r.status_code == 204, r.text

    listed = (await client.get("/api/v1/reports/templates/page",
                               headers=auth_headers["a"])).json()
    assert tpl not in [t["id"] for t in listed]


@pytest.mark.asyncio
async def test_deleting_a_template_leaves_the_pages_built_from_it(client, auth_headers, db_session):
    """A template is a stamp, not a link. Pages already stamped from it are
    ordinary pages and must not vanish with it."""
    tpl = await _template_from_a_page(client, auth_headers["a"])
    report_id, _page, _c = await _report_with_container_page(client, auth_headers["a"])
    made = await client.post(f"/api/v1/reports/{report_id}/pages/from-template",
                             json={"template_id": tpl}, headers=auth_headers["a"])
    assert made.status_code == 201, made.text
    page_id = made.json()["page_id"]

    await client.delete(f"/api/v1/reports/templates/page/{tpl}", headers=auth_headers["a"])
    assert await _page_widgets(db_session, page_id)


@pytest.mark.asyncio
async def test_another_org_cannot_delete_this_org_s_template(client, auth_headers):
    tpl = await _template_from_a_page(client, auth_headers["a"])
    r = await client.delete(f"/api/v1/reports/templates/page/{tpl}", headers=auth_headers["b"])
    assert r.status_code == 404

    listed = (await client.get("/api/v1/reports/templates/page",
                               headers=auth_headers["a"])).json()
    assert tpl in [t["id"] for t in listed]


@pytest.mark.asyncio
async def test_deleting_a_template_that_is_already_gone_reads_as_gone(client, auth_headers):
    tpl = await _template_from_a_page(client, auth_headers["a"])
    await client.delete(f"/api/v1/reports/templates/page/{tpl}", headers=auth_headers["a"])
    again = await client.delete(f"/api/v1/reports/templates/page/{tpl}", headers=auth_headers["a"])
    assert again.status_code == 404
