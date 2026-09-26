"""E09: the draft/published split.

Every edit to a report persists at once. Before releases, that meant every
edit to a PUBLISHED dashboard reached its viewers the moment it was made. Now
viewers are served the report's latest release, and editors change the draft
until they release it. The acceptance this pins: drafts do not alter released
definitions; access stays current (a release is served under today's rules);
what a viewer exports is what they are served.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, DatasetColumn, Report, ReportRelease, Role, User


def _hdr(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _member(db, org_id, name):
    role = Role(org_id=org_id, name=name, is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org_id, role_id=role.id, email=f"{name}-{role.id}@ex.com",
                password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    return role, user


async def _dataset(db, org_id, owner, tmp_path, name):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"region": ["N", "S"], "revenue": [1.0, 2.0]}).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, mode="import", created_by=owner.id)
    db.add(ds)
    await db.flush()
    for col, dtype in (("region", "categorical"), ("revenue", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype))
    return ds


def _bar(title, dataset_id=None):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
    if dataset_id is not None:
        config["dataset_id"] = dataset_id
    return {"widget_type": "bar", "title": title, "config": config,
            "layout": {"x": 0, "y": 0, "w": 6, "h": 4}}


@pytest.fixture
async def world(client, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    author_role, author = await _member(db_session, org.id, "author")
    viewer_role, viewer = await _member(db_session, org.id, "viewer")
    main = await _dataset(db_session, org.id, author, tmp_path, "main")
    extra = await _dataset(db_session, org.id, author, tmp_path, "extra")
    await db_session.commit()
    a = _hdr(author)
    rid = (await client.post("/api/v1/reports", json={"name": "Sales", "dataset_id": main.id},
                             headers=a)).json()["id"]
    page = (await client.get(f"/api/v1/reports/{rid}", headers=a)).json()["pages"][0]["id"]
    w = (await client.post(f"/api/v1/reports/{rid}/pages/{page}/widgets", json=_bar("Revenue"),
                           headers=a)).json()["id"]
    return {"client": client, "db": db_session, "author": author, "viewer": viewer,
            "author_role": author_role, "viewer_role": viewer_role, "a": a, "v": _hdr(viewer),
            "report": rid, "page": page, "widget": w, "main": main.id, "extra": extra.id}


async def _publish(world):
    r = await world["client"].post(f"/api/v1/reports/{world['report']}/publish",
                                   json={"published": True}, headers=world["a"])
    assert r.status_code == 200, r.text
    return r.json()


async def _get(world, who, **params):
    r = await world["client"].get(f"/api/v1/reports/{world['report']}", params=params, headers=world[who])
    assert r.status_code == 200, r.text
    return r.json()


def _titles(report):
    return sorted(w["title"] for p in report["pages"] for w in p["widgets"])


class TestDraftsDoNotReachViewers:
    async def test_publishing_releases_what_is_there(self, world):
        out = await _publish(world)
        assert out["release"]["reason"] == "publish"
        seen = await _get(world, "v")
        assert seen["showing"] == "released"
        assert _titles(seen) == ["Revenue"]
        assert seen["my_capability"] == "view"

    async def test_edits_go_to_the_draft_until_released(self, world):
        await _publish(world)
        c, a, rid, page = world["client"], world["a"], world["report"], world["page"]
        await c.post(f"/api/v1/reports/{rid}/pages/{page}/widgets", json=_bar("Half-finished"), headers=a)
        await c.patch(f"/api/v1/reports/{rid}/pages/{page}/widgets/{world['widget']}",
                      json={"title": "Renamed"}, headers=a)
        await c.patch(f"/api/v1/reports/{rid}", json={"theme": "dark"}, headers=a)

        # The viewer still sees exactly what was released.
        seen = await _get(world, "v")
        assert _titles(seen) == ["Revenue"]
        assert seen["theme"] == "default"
        assert seen["unreleased_changes"] is False   # not a viewer's concern

        # The author works on the draft and is told it has moved on.
        draft = await _get(world, "a")
        assert draft["showing"] == "draft"
        assert _titles(draft) == ["Half-finished", "Renamed"]
        assert draft["unreleased_changes"] is True
        # ...and can look at what viewers see.
        assert _titles(await _get(world, "a", view="released")) == ["Revenue"]

        r = await c.post(f"/api/v1/reports/{rid}/release", json={"note": "Q3 layout"}, headers=a)
        assert r.status_code == 201, r.text
        assert r.json()["release"]["note"] == "Q3 layout"
        seen = await _get(world, "v")
        assert _titles(seen) == ["Half-finished", "Renamed"]
        assert seen["theme"] == "dark"
        assert (await _get(world, "a"))["unreleased_changes"] is False

    async def test_the_released_ids_are_the_same_objects(self, world):
        await _publish(world)
        seen = await _get(world, "v")
        assert seen["pages"][0]["id"] == world["page"]
        assert seen["pages"][0]["widgets"][0]["id"] == world["widget"]

    async def test_a_published_report_from_before_releases_keeps_what_viewers_saw(self, world):
        # Published before this shipped: no release. Its first edit keeps the
        # content its viewers had as the release, and goes to the draft.
        rep = await world["db"].get(Report, world["report"])
        rep.published = True
        await world["db"].commit()
        assert _titles(await _get(world, "v")) == ["Revenue"]
        assert (await _get(world, "v"))["showing"] == "live"

        c, a, rid = world["client"], world["a"], world["report"]
        await c.patch(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets/{world['widget']}",
                      json={"title": "Edited"}, headers=a)
        releases = (await world["db"].execute(
            select(ReportRelease).where(ReportRelease.report_id == rid))).scalars().all()
        assert [r.reason for r in releases] == ["first_edit"]
        assert _titles(await _get(world, "v")) == ["Revenue"]
        assert _titles(await _get(world, "a")) == ["Edited"]

    async def test_a_private_draft_has_no_release(self, world):
        c, a, rid = world["client"], world["a"], world["report"]
        await c.patch(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets/{world['widget']}",
                      json={"title": "Edited"}, headers=a)
        draft = await _get(world, "a")
        assert draft["release"] is None and draft["showing"] == "live"


class TestOnlyEditorsRelease:
    async def test_a_viewer_can_neither_release_nor_list_releases(self, world):
        await _publish(world)
        c, v, rid = world["client"], world["v"], world["report"]
        r = await c.post(f"/api/v1/reports/{rid}/release", json={}, headers=v)
        assert r.status_code in (403, 404)
        r = await c.get(f"/api/v1/reports/{rid}/releases", headers=v)
        assert r.status_code in (403, 404)
        r = await c.get(f"/api/v1/reports/{rid}/releases", headers=world["a"])
        assert [x["reason"] for x in r.json()] == ["publish"]


class TestAccessIsCurrent:
    async def test_a_page_restricted_at_release_stays_restricted_after_the_draft_deletes_it(self, world):
        c, a, rid = world["client"], world["a"], world["report"]
        secret = (await c.post(f"/api/v1/reports/{rid}/pages", json={"name": "HR", "position": 1},
                               headers=a)).json()["id"]
        await c.post(f"/api/v1/reports/{rid}/pages/{secret}/widgets", json=_bar("Salaries"), headers=a)
        r = await c.put(f"/api/v1/reports/{rid}/pages/{secret}/visibility",
                        json={"role_ids": [world["author_role"].id]}, headers=a)
        assert r.status_code == 200, r.text
        await _publish(world)
        assert _titles(await _get(world, "v")) == ["Revenue"]

        # The draft drops the page, and with it the page's restriction rows.
        assert (await c.delete(f"/api/v1/reports/{rid}/pages/{secret}", headers=a)).status_code == 204
        seen = await _get(world, "v")
        assert _titles(seen) == ["Revenue"], "the frozen restriction still applies"
        # The list is held to the same rule.
        listed = next(x for x in (await c.get("/api/v1/reports", headers=world["v"])).json()
                      if x["id"] == rid)
        assert _titles(listed) == ["Revenue"]

    async def test_a_restriction_added_after_release_applies_at_once(self, world):
        await _publish(world)
        c, a, rid = world["client"], world["a"], world["report"]
        await c.put(f"/api/v1/reports/{rid}/pages/{world['page']}/visibility",
                    json={"role_ids": [world["author_role"].id]}, headers=a)
        assert (await _get(world, "v"))["pages"] == []

    async def test_the_list_no_longer_carries_restricted_pages(self, world):
        # Before E09 the list served every page, restricted or not.
        c, a, rid = world["client"], world["a"], world["report"]
        await c.put(f"/api/v1/reports/{rid}/pages/{world['page']}/visibility",
                    json={"role_ids": [world["author_role"].id]}, headers=a)
        await c.post(f"/api/v1/reports/{rid}/publish", json={"published": True}, headers=a)
        listed = next(x for x in (await c.get("/api/v1/reports", headers=world["v"])).json()
                      if x["id"] == rid)
        assert listed["pages"] == []


class TestDataFollowsTheRelease:
    async def _read(self, world, dataset_id):
        return await world["client"].post(
            f"/api/v1/datasets/{dataset_id}/widget-data",
            json={"widget_type": "bar", "report_id": world["report"],
                  "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}},
            headers=world["v"])

    async def test_a_dataset_added_in_the_draft_is_not_the_viewers(self, world):
        await _publish(world)
        c, a, rid = world["client"], world["a"], world["report"]
        await c.post(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets",
                     json=_bar("Extra", world["extra"]), headers=a)
        assert (await self._read(world, world["main"])).status_code == 200
        assert (await self._read(world, world["extra"])).status_code == 404
        await c.post(f"/api/v1/reports/{rid}/release", json={}, headers=a)
        assert (await self._read(world, world["extra"])).status_code == 200

    async def test_a_dataset_the_draft_dropped_still_draws_the_released_widget(self, world):
        c, a, rid = world["client"], world["a"], world["report"]
        w = (await c.post(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets",
                          json=_bar("Extra", world["extra"]), headers=a)).json()["id"]
        await _publish(world)
        await c.delete(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets/{w}", headers=a)
        assert (await self._read(world, world["extra"])).status_code == 200

    async def test_a_viewers_pdf_is_of_the_release(self, world, monkeypatch):
        await _publish(world)
        c, a, rid = world["client"], world["a"], world["report"]
        await c.patch(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets/{world['widget']}",
                      json={"title": "Draft title"}, headers=a)
        captured = {}

        def fake_pdf(name, description, sections, *args, **kwargs):
            captured["titles"] = [w["title"] for s in sections for w in s["widgets"]]
            return b"%PDF-1.4"
        monkeypatch.setattr("app.services.pdf_export.build_report_pdf", fake_pdf)
        r = await c.get(f"/api/v1/reports/{rid}/pdf", headers=world["v"])
        assert r.status_code == 200, r.text
        assert captured["titles"] == ["Revenue"]
        await c.get(f"/api/v1/reports/{rid}/pdf", headers=a)
        assert captured["titles"] == ["Draft title"]

    async def test_a_guest_link_shows_the_release(self, world):
        await _publish(world)
        c, a, rid = world["client"], world["a"], world["report"]
        r = await c.post(f"/api/v1/reports/{rid}/share-links", json={}, headers=a)
        assert r.status_code == 201, r.text
        token = r.json()["token"]
        await c.patch(f"/api/v1/reports/{rid}/pages/{world['page']}/widgets/{world['widget']}",
                      json={"title": "Draft title"}, headers=a)
        shared = (await c.get(f"/api/v1/shared/{token}")).json()
        assert [w["title"] for p in shared["pages"] for w in p["widgets"]] == ["Revenue"]
        data = await c.post(f"/api/v1/shared/{token}/widget-data/{world['widget']}")
        assert data.status_code == 200, data.text
