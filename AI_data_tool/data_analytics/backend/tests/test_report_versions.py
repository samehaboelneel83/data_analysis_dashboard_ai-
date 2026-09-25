"""Report version history with restore (R2 of the competitive assessment).

The revision counter could already DETECT a concurrent edit; these pin the
way back: every mutation captures the pre-mutation content as a version,
restore puts a chosen version's pages and widgets back (leaving identity —
name, publish state — alone), a restore is itself undoable, and the window
is pruned. Capture must show the state BEFORE the triggering edit, even
though the edit has already dirtied the ORM objects when the bump runs —
the exact trap the core-select capture exists to dodge.
"""
import pytest
from sqlalchemy import select

from app.models.models import ReportVersion, ReportWidget
from app.routers import reports as reports_router


@pytest.fixture
async def report(client, auth_headers):
    r = await client.post("/api/v1/reports", json={"name": "Sales"},
                          headers=auth_headers["a"])
    assert r.status_code in (200, 201)
    return r.json()


async def add_widget(client, headers, rep, title, wtype="bar"):
    r = await client.post(
        f"/api/v1/reports/{rep['id']}/pages/{rep['pages'][0]['id']}/widgets",
        json={"widget_type": wtype, "title": title,
              "config": {"dimension": "region"},
              "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
        headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def versions(client, headers, rid):
    r = await client.get(f"/api/v1/reports/{rid}/versions", headers=headers)
    assert r.status_code in (200, 201)
    return r.json()


class TestCapture:
    async def test_every_mutation_leaves_the_before_state(self, client,
                                                          auth_headers, report):
        await add_widget(client, auth_headers["a"], report, "First")
        await add_widget(client, auth_headers["a"], report, "Second")
        vs = await versions(client, auth_headers["a"], report["id"])
        # Newest first: before-Second (1 widget), before-First (0 widgets).
        assert [v["widgets"] for v in vs] == [1, 0]
        assert [v["revision"] for v in vs] == [1, 0]
        assert vs[0]["created_by"] == "admin-a@example.com"

    async def test_an_update_snapshots_the_old_values_not_the_new(
            self, client, auth_headers, report, db_session):
        w = await add_widget(client, auth_headers["a"], report, "Original title")
        r = await client.patch(
            f"/api/v1/reports/{report['id']}/pages/{report['pages'][0]['id']}"
            f"/widgets/{w['id']}",
            json={"title": "Renamed"}, headers=auth_headers["a"])
        assert r.status_code == 200
        latest = (await db_session.execute(
            select(ReportVersion).where(ReportVersion.report_id == report["id"])
            .order_by(ReportVersion.id.desc()))).scalars().first()
        titles = [wd["title"] for p in latest.snapshot["pages"]
                  for wd in p["widgets"]]
        # The identity-map trap: a naive ORM read here would say "Renamed".
        assert titles == ["Original title"]

    async def test_the_window_is_pruned(self, client, auth_headers, report,
                                        monkeypatch):
        monkeypatch.setattr(reports_router, "VERSIONS_KEPT", 3)
        for i in range(6):
            await add_widget(client, auth_headers["a"], report, f"W{i}")
        vs = await versions(client, auth_headers["a"], report["id"])
        assert len(vs) == 3
        assert vs[0]["widgets"] == 5   # newest capture survived


class TestRestore:
    async def test_restore_brings_the_content_back_and_is_undoable(
            self, client, auth_headers, report, db_session):
        await add_widget(client, auth_headers["a"], report, "Keep me")
        await add_widget(client, auth_headers["a"], report, "Mistake")
        vs = await versions(client, auth_headers["a"], report["id"])
        one_widget_state = vs[0]          # captured before "Mistake"

        r = await client.post(
            f"/api/v1/reports/{report['id']}/versions/{one_widget_state['id']}/restore",
            headers=auth_headers["a"])
        assert r.status_code == 200
        assert "removed" in r.json()["note"]

        widgets = (await db_session.execute(select(ReportWidget))).scalars().all()
        assert [w.title for w in widgets] == ["Keep me"]

        # The restore itself captured the 2-widget state: walk back forward.
        vs2 = await versions(client, auth_headers["a"], report["id"])
        assert vs2[0]["widgets"] == 2
        r = await client.post(
            f"/api/v1/reports/{report['id']}/versions/{vs2[0]['id']}/restore",
            headers=auth_headers["a"])
        assert r.status_code == 200
        widgets = (await db_session.execute(select(ReportWidget))).scalars().all()
        assert sorted(w.title for w in widgets) == ["Keep me", "Mistake"]

    async def test_identity_is_not_restored(self, client, auth_headers,
                                            report, db_session):
        await add_widget(client, auth_headers["a"], report, "W")
        vs = await versions(client, auth_headers["a"], report["id"])
        # Rename the report AFTER the capture, then restore that capture.
        r = await client.patch(f"/api/v1/reports/{report['id']}",
                               json={"name": "New name"},
                               headers=auth_headers["a"])
        assert r.status_code == 200
        r = await client.post(
            f"/api/v1/reports/{report['id']}/versions/{vs[0]['id']}/restore",
            headers=auth_headers["a"])
        assert r.status_code == 200
        got = (await client.get(f"/api/v1/reports/{report['id']}",
                                headers=auth_headers["a"])).json()
        assert got["name"] == "New name"   # charts went back; the name did not

    async def test_restore_rewires_links_between_widgets_pages_and_bookmarks(
            self, client, auth_headers, report, db_session):
        """Restore recreates pages and widgets with NEW ids. The references
        into them -- a container's child, an interaction target, a drill
        page, a bookmark -- used to be copied verbatim and silently point at
        nothing."""
        from app.models.models import Bookmark, ReportPage
        h = auth_headers["a"]
        page_id = report["pages"][0]["id"]
        box = await add_widget(client, h, report, "Box", wtype="container")
        child = await add_widget(client, h, report, "Child")
        base = f"/api/v1/reports/{report['id']}/pages/{page_id}/widgets"
        r = await client.patch(f"{base}/{child['id']}", headers=h, json={"config": {
            "dimension": "region", "container_id": box["id"],
            "drillthroughPageId": page_id,
            "interaction": {"actions": [{"targetId": box["id"], "type": "filter"},
                                        {"targetId": 987654, "type": "filter"}]}}})
        assert r.status_code == 200, r.text
        r = await client.post(f"/api/v1/reports/{report['id']}/bookmarks", headers=h, json={
            "name": "Mine", "state": {
                "pageId": page_id, "hiddenWidgetIds": [box["id"]], "promptValues": {},
                "activeFilters": [{"column": "region", "value": "N", "label": "N",
                                   "sourceWidgetId": child["id"], "sourcePageId": page_id}]}})
        assert r.status_code in (200, 201), r.text
        await add_widget(client, h, report, "Later")      # captures the wired state
        wired = (await versions(client, h, report["id"]))[0]

        r = await client.post(f"/api/v1/reports/{report['id']}/versions/{wired['id']}/restore",
                              headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        # The 987654 target never existed: dropped, and counted.
        assert body["links_dropped"] == 1
        assert body["links_remapped"] >= 6

        db_session.expire_all()
        new_page = (await db_session.execute(select(ReportPage).where(
            ReportPage.report_id == report["id"]))).scalars().one()
        ws = {w.title: w for w in (await db_session.execute(select(ReportWidget).where(
            ReportWidget.page_id == new_page.id))).scalars().all()}
        assert set(ws) == {"Box", "Child"}
        cfg = ws["Child"].config
        # Checked against the RESTORED rows by title, not as "!= old id":
        # SQLite reuses freed ids, so a new id can equal the one it replaced.
        assert cfg["container_id"] == ws["Box"].id
        assert cfg["drillthroughPageId"] == new_page.id
        assert [a["targetId"] for a in cfg["interaction"]["actions"]] == [ws["Box"].id]
        bm = (await db_session.execute(select(Bookmark).where(
            Bookmark.report_id == report["id"]))).scalars().one()
        assert bm.state["pageId"] == new_page.id
        assert bm.state["hiddenWidgetIds"] == [ws["Box"].id]
        assert bm.state["activeFilters"][0]["sourceWidgetId"] == ws["Child"].id
        assert bm.state["activeFilters"][0]["sourcePageId"] == new_page.id

    async def test_a_page_role_restriction_survives_a_restore(
            self, client, auth_headers, report, db_session, two_orgs):
        """Restriction rows cascade with the pages a restore deletes, so a
        restore used to LIFT "Finance only" off a page -- a restore of
        content quietly widening access."""
        from app.models.models import PageRoleVisibility, ReportPage, Role
        h = auth_headers["a"]
        role = Role(org_id=two_orgs["a"]["org"].id, name="Finance", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        role_id = role.id   # read before expire_all(), which would lazy-load it
        db_session.add(PageRoleVisibility(page_id=report["pages"][0]["id"], role_id=role_id))
        await db_session.commit()
        await add_widget(client, h, report, "W")
        vs = await versions(client, h, report["id"])

        r = await client.post(f"/api/v1/reports/{report['id']}/versions/{vs[0]['id']}/restore",
                              headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["pages_restricted"] == 1
        db_session.expire_all()
        new_page = (await db_session.execute(select(ReportPage).where(
            ReportPage.report_id == report["id"]))).scalars().one()
        rows = (await db_session.execute(select(PageRoleVisibility).where(
            PageRoleVisibility.page_id == new_page.id))).scalars().all()
        assert [x.role_id for x in rows] == [role_id]

    async def test_cross_org_and_wrong_report_are_404(self, client,
                                                      auth_headers, report):
        await add_widget(client, auth_headers["a"], report, "W")
        vs = await versions(client, auth_headers["a"], report["id"])
        r = await client.post(
            f"/api/v1/reports/{report['id']}/versions/{vs[0]['id']}/restore",
            headers=auth_headers["b"])
        assert r.status_code == 404
        other = await client.post("/api/v1/reports", json={"name": "Other"},
                                  headers=auth_headers["a"])
        r = await client.post(
            f"/api/v1/reports/{other.json()['id']}/versions/{vs[0]['id']}/restore",
            headers=auth_headers["a"])
        assert r.status_code == 404
