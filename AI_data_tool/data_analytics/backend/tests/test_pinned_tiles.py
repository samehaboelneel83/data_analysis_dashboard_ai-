"""Pinned tiles: any chart on a personal, live home dashboard.

A pin is a REFERENCE to a report widget, so the properties worth testing are
the ones that follow from that: the tile carries the widget's LIVE config (no
copy to drift), visibility is re-checked on every read (a pin must never
become a keyhole into a page the viewer has since lost), and a deleted widget
takes its pins with it (a tile pointing at nothing is not worth a tombstone).

Every failure mode returns the same 404. A cross-org widget id, a restricted
page and a genuinely absent widget must be indistinguishable, or the response
itself confirms what exists.
"""
import pytest

from app.models.models import (PageRoleVisibility, PinnedTile, Report,
                               ReportPage, ReportWidget)


async def _report_with_widget(db, org, name="R"):
    report = Report(name=name, org_id=org.id)
    db.add(report)
    await db.flush()
    page = ReportPage(report_id=report.id, name="Page 1", position=0)
    db.add(page)
    await db.flush()
    widget = ReportWidget(page_id=page.id, widget_type="bar", title="Sales",
                          config={"dimension": "region", "measure": "revenue",
                                  "aggregation": "sum"},
                          layout={"x": 0, "y": 0, "w": 6, "h": 4})
    db.add(widget)
    await db.commit()
    return report, page, widget


class TestPinAndList:
    @pytest.mark.asyncio
    async def test_a_pin_lists_with_the_widgets_live_config(
            self, client, auth_headers, db_session, two_orgs):
        _, _, widget = await _report_with_widget(db_session, two_orgs["a"]["org"])
        r = await client.post("/api/v1/pins", json={"widget_id": widget.id},
                              headers=auth_headers["a"])
        assert r.status_code == 201

        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        pins = listed.json()["pins"]
        assert len(pins) == 1
        tile = pins[0]
        # The whole point: the tile carries everything the client needs to
        # render LIVE through the existing secured widget-data path -- and
        # nothing else. No rows, no values, no snapshot.
        assert tile["widget_type"] == "bar"
        assert tile["config"]["measure"] == "revenue"
        assert tile["report_name"] == "R"
        assert "rows" not in tile and "data" not in tile

    @pytest.mark.asyncio
    async def test_the_tile_follows_a_widget_edit(
            self, client, auth_headers, db_session, two_orgs):
        """Reference, not copy. An author retuning the chart inside the report
        retunes every dashboard it was pinned to -- there is no stored config
        to drift."""
        _, _, widget = await _report_with_widget(db_session, two_orgs["a"]["org"])
        await client.post("/api/v1/pins", json={"widget_id": widget.id},
                          headers=auth_headers["a"])
        widget.config = {"dimension": "country", "measure": "cost",
                         "aggregation": "avg"}
        await db_session.commit()

        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        assert listed.json()["pins"][0]["config"]["measure"] == "cost"

    @pytest.mark.asyncio
    async def test_pinning_twice_is_a_double_click_not_an_error(
            self, client, auth_headers, db_session, two_orgs):
        _, _, widget = await _report_with_widget(db_session, two_orgs["a"]["org"])
        first = await client.post("/api/v1/pins", json={"widget_id": widget.id},
                                  headers=auth_headers["a"])
        second = await client.post("/api/v1/pins", json={"widget_id": widget.id},
                                   headers=auth_headers["a"])
        assert second.json()["already_pinned"] is True
        assert second.json()["id"] == first.json()["id"]
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        assert len(listed.json()["pins"]) == 1


class TestTheSingle404:
    @pytest.mark.asyncio
    async def test_a_cross_org_widget_cannot_be_pinned(
            self, client, auth_headers, db_session, two_orgs):
        _, _, widget = await _report_with_widget(db_session, two_orgs["a"]["org"])
        r = await client.post("/api/v1/pins", json={"widget_id": widget.id},
                              headers=auth_headers["b"])
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_a_missing_widget_reads_identically(
            self, client, auth_headers):
        r = await client.post("/api/v1/pins", json={"widget_id": 99999},
                              headers=auth_headers["a"])
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_someone_elses_pin_cannot_be_deleted(
            self, client, auth_headers, db_session, two_orgs):
        _, _, widget = await _report_with_widget(db_session, two_orgs["a"]["org"])
        pin = (await client.post("/api/v1/pins", json={"widget_id": widget.id},
                                 headers=auth_headers["a"])).json()
        r = await client.delete(f"/api/v1/pins/{pin['id']}",
                                headers=auth_headers["b"])
        assert r.status_code == 404
        # And the pin survives the attempt.
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        assert len(listed.json()["pins"]) == 1


class TestVisibilityIsRecheckedOnEveryRead:
    """THE security property. A page can be role-restricted AFTER someone
    pinned a chart from it, and a pin must not become a keyhole into a page
    the viewer has since lost."""

    @pytest.mark.asyncio
    async def test_a_later_page_restriction_hides_the_tile(
            self, client, db_session, two_orgs):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User
        org = two_orgs["a"]["org"]
        _, page, widget = await _report_with_widget(db_session, org)
        role = Role(org_id=org.id, name="viewer", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=org.id, role_id=role.id, email="v@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

        # Pin while the page is open to everyone...
        assert (await client.post("/api/v1/pins", json={"widget_id": widget.id},
                                  headers=headers)).status_code == 201
        # ...then restrict the page to a DIFFERENT role.
        other = Role(org_id=org.id, name="finance", is_org_admin=False)
        db_session.add(other)
        await db_session.flush()
        db_session.add(PageRoleVisibility(page_id=page.id, role_id=other.id))
        await db_session.commit()

        listed = await client.get("/api/v1/pins", headers=headers)
        assert listed.json()["pins"] == []

        # Dormant, not deleted: access restored means the tile comes back.
        db_session.add(PageRoleVisibility(page_id=page.id, role_id=role.id))
        await db_session.commit()
        listed = await client.get("/api/v1/pins", headers=headers)
        assert len(listed.json()["pins"]) == 1

    @pytest.mark.asyncio
    async def test_a_restricted_page_cannot_be_pinned_from_either(
            self, client, db_session, two_orgs):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User
        org = two_orgs["a"]["org"]
        _, page, widget = await _report_with_widget(db_session, org)
        role = Role(org_id=org.id, name="viewer2", is_org_admin=False)
        other = Role(org_id=org.id, name="finance2", is_org_admin=False)
        db_session.add_all([role, other])
        await db_session.flush()
        db_session.add(PageRoleVisibility(page_id=page.id, role_id=other.id))
        user = User(org_id=org.id, role_id=role.id, email="v2@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

        r = await client.post("/api/v1/pins", json={"widget_id": widget.id},
                              headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_an_org_admin_is_exempt_matching_get_report(
            self, client, auth_headers, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, page, widget = await _report_with_widget(db_session, org)
        from app.models.models import Role
        other = Role(org_id=org.id, name="finance3", is_org_admin=False)
        db_session.add(other)
        await db_session.flush()
        db_session.add(PageRoleVisibility(page_id=page.id, role_id=other.id))
        await db_session.commit()
        # auth_headers["a"] is the org admin.
        r = await client.post("/api/v1/pins", json={"widget_id": widget.id},
                              headers=auth_headers["a"])
        assert r.status_code == 201


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_deleting_the_widget_takes_the_pin_with_it(
            self, client, auth_headers, db_session, two_orgs):
        from sqlalchemy import func, select
        _, _, widget = await _report_with_widget(db_session, two_orgs["a"]["org"])
        await client.post("/api/v1/pins", json={"widget_id": widget.id},
                          headers=auth_headers["a"])
        await db_session.delete(widget)
        await db_session.commit()
        count = (await db_session.execute(
            select(func.count()).select_from(PinnedTile))).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_unpin_removes_only_that_tile(
            self, client, auth_headers, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, _, w1 = await _report_with_widget(db_session, org, "R1")
        _, _, w2 = await _report_with_widget(db_session, org, "R2")
        p1 = (await client.post("/api/v1/pins", json={"widget_id": w1.id},
                                headers=auth_headers["a"])).json()
        await client.post("/api/v1/pins", json={"widget_id": w2.id},
                          headers=auth_headers["a"])
        r = await client.delete(f"/api/v1/pins/{p1['id']}",
                                headers=auth_headers["a"])
        assert r.status_code == 204
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        assert [t["report_name"] for t in listed.json()["pins"]] == ["R2"]


async def _dataset(db, org, name="D"):
    from app.models.models import Dataset
    ds = Dataset(name=name, filename="/tmp/none.csv", org_id=org.id, mode="import")
    db.add(ds)
    await db.commit()
    return ds


class TestLayout:
    """Position and size: the container work. Dense 1-based positions are the
    CLIENT's job (TabOrderPane convention); the server only stores and orders."""

    @pytest.mark.asyncio
    async def test_pins_list_in_position_order_not_recency(
            self, client, auth_headers, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, _, w1 = await _report_with_widget(db_session, org, "R1")
        _, _, w2 = await _report_with_widget(db_session, org, "R2")
        p1 = (await client.post("/api/v1/pins", json={"widget_id": w1.id},
                                headers=auth_headers["a"])).json()
        p2 = (await client.post("/api/v1/pins", json={"widget_id": w2.id},
                                headers=auth_headers["a"])).json()
        # Swap: the OLDER pin moves after the newer one.
        await client.patch(f"/api/v1/pins/{p1['id']}", json={"position": 2},
                           headers=auth_headers["a"])
        await client.patch(f"/api/v1/pins/{p2['id']}", json={"position": 1},
                           headers=auth_headers["a"])
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        assert [t["report_name"] for t in listed.json()["pins"]] == ["R2", "R1"]

    @pytest.mark.asyncio
    async def test_new_pins_append_after_existing_ones(
            self, client, auth_headers, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        _, _, w1 = await _report_with_widget(db_session, org, "R1")
        _, _, w2 = await _report_with_widget(db_session, org, "R2")
        await client.post("/api/v1/pins", json={"widget_id": w1.id},
                          headers=auth_headers["a"])
        await client.post("/api/v1/pins", json={"widget_id": w2.id},
                          headers=auth_headers["a"])
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        positions = [t["position"] for t in listed.json()["pins"]]
        assert positions == sorted(positions)
        assert positions[0] != positions[1]

    @pytest.mark.asyncio
    async def test_size_accepts_only_the_three_tokens(
            self, client, auth_headers, db_session, two_orgs):
        _, _, w = await _report_with_widget(db_session, two_orgs["a"]["org"])
        pin = (await client.post("/api/v1/pins", json={"widget_id": w.id},
                                 headers=auth_headers["a"])).json()
        ok = await client.patch(f"/api/v1/pins/{pin['id']}", json={"size": "l"},
                                headers=auth_headers["a"])
        assert ok.status_code == 200 and ok.json()["size"] == "l"
        bad = await client.patch(f"/api/v1/pins/{pin['id']}",
                                 json={"size": "xl"}, headers=auth_headers["a"])
        assert bad.status_code == 400

    @pytest.mark.asyncio
    async def test_someone_elses_pin_cannot_be_moved(
            self, client, auth_headers, db_session, two_orgs):
        _, _, w = await _report_with_widget(db_session, two_orgs["a"]["org"])
        pin = (await client.post("/api/v1/pins", json={"widget_id": w.id},
                                 headers=auth_headers["a"])).json()
        r = await client.patch(f"/api/v1/pins/{pin['id']}", json={"position": 1},
                               headers=auth_headers["b"])
        assert r.status_code == 404


class TestInsightPins:
    """A Dynamic Pin references a FINDING (dataset + the identity apply_novelty
    uses), never stores its figures or prose, and is listed as metadata only --
    evaluation happens through the secured insights endpoint as the viewer."""

    @pytest.mark.asyncio
    async def test_an_insight_pin_lists_with_its_key_and_no_data(
            self, client, auth_headers, db_session, two_orgs):
        ds = await _dataset(db_session, two_orgs["a"]["org"], "Sales")
        r = await client.post("/api/v1/pins",
                              json={"dataset_id": ds.id,
                                    "finding_key": "trend|date|revenue"},
                              headers=auth_headers["a"])
        assert r.status_code == 201
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        tile = listed.json()["pins"][0]
        assert tile["pin_type"] == "insight"
        assert tile["finding_key"] == "trend|date|revenue"
        assert tile["dataset_name"] == "Sales"
        # Metadata only: no figures, no score, no prose. The card must earn
        # those live, per viewer, through the insights endpoint.
        for absent in ("figures", "score", "title", "narrative", "config"):
            assert absent not in tile

    @pytest.mark.asyncio
    async def test_the_same_finding_pins_once(
            self, client, auth_headers, db_session, two_orgs):
        ds = await _dataset(db_session, two_orgs["a"]["org"])
        body = {"dataset_id": ds.id, "finding_key": "standout|region|revenue"}
        first = (await client.post("/api/v1/pins", json=body,
                                   headers=auth_headers["a"])).json()
        second = (await client.post("/api/v1/pins", json=body,
                                    headers=auth_headers["a"])).json()
        assert second["already_pinned"] is True
        assert second["id"] == first["id"]

    @pytest.mark.asyncio
    async def test_a_cross_org_dataset_cannot_be_pinned(
            self, client, auth_headers, db_session, two_orgs):
        ds = await _dataset(db_session, two_orgs["a"]["org"])
        r = await client.post("/api/v1/pins",
                              json={"dataset_id": ds.id, "finding_key": "trend|x"},
                              headers=auth_headers["b"])
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_a_dataset_leaving_the_org_takes_its_card_dormant(
            self, client, auth_headers, db_session, two_orgs):
        """The keyhole rule, insight-pin edition: visibility is re-checked on
        every read, so a dataset moved out of reach must take its card with it
        -- while the pin itself survives for if access returns."""
        ds = await _dataset(db_session, two_orgs["a"]["org"])
        await client.post("/api/v1/pins",
                          json={"dataset_id": ds.id, "finding_key": "trend|d|r"},
                          headers=auth_headers["a"])
        ds.org_id = two_orgs["b"]["org"].id
        await db_session.commit()
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        assert listed.json()["pins"] == []

    @pytest.mark.asyncio
    async def test_neither_shape_given_is_a_400_not_a_500(
            self, client, auth_headers):
        r = await client.post("/api/v1/pins", json={}, headers=auth_headers["a"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_widget_and_insight_pins_share_one_ordering(
            self, client, auth_headers, db_session, two_orgs):
        """One grid, one position sequence -- the reason both kinds share the
        table instead of getting one each."""
        org = two_orgs["a"]["org"]
        _, _, w = await _report_with_widget(db_session, org)
        ds = await _dataset(db_session, org)
        await client.post("/api/v1/pins", json={"widget_id": w.id},
                          headers=auth_headers["a"])
        await client.post("/api/v1/pins",
                          json={"dataset_id": ds.id, "finding_key": "trend|d|r"},
                          headers=auth_headers["a"])
        listed = await client.get("/api/v1/pins", headers=auth_headers["a"])
        pins = listed.json()["pins"]
        assert [p["pin_type"] for p in pins] == ["widget", "insight"]
        assert pins[0]["position"] < pins[1]["position"]
