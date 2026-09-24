"""The HTTP surface for customer-supplied map boundaries.

A JSON body, not a multipart upload. There is no non-dataset file-upload
endpoint in this codebase to follow, and inventing one buys nothing here: the
browser has to parse the file anyway to convert TopoJSON to GeoJSON before
sending, so by the time it reaches the wire it is already a JSON document. This
follows `custom_connectors` instead — an org-owned, named reference artifact.

Listing never includes the geometry. A boundary file is megabytes; a picker
that needed all of them to draw a dropdown would download the lot.
"""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import BoundarySet, Role, User


def poly(x=0.0, y=0.0):
    return {"type": "Polygon",
            "coordinates": [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]]}


def region(name, extra=None):
    return {"type": "Feature", "geometry": poly(),
            "properties": {"name": name, **(extra or {})}}


GOVERNORATES = {
    "type": "FeatureCollection",
    "features": [region("Cairo"), region("Giza"), region("Alexandria")],
}

URL = "/api/v1/boundary-sets"


async def _member(db_session, org_id, admin=False):
    role = Role(org_id=org_id, name=f"Member{admin}", is_org_admin=admin)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id,
                email=f"member-{role.id}@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


class TestCreating:
    async def test_a_valid_file_is_stored(self, client, two_orgs, auth_headers):
        r = await client.post(URL, headers=auth_headers["a"],
                              json={"name": "Egypt governorates",
                                    "geometry": GOVERNORATES})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Egypt governorates"
        assert body["feature_count"] == 3

    async def test_it_reports_what_the_file_can_be_matched_on(
            self, client, two_orgs, auth_headers):
        """So the author can see whether their column will match BEFORE
        building a widget and finding out it does not."""
        r = await client.post(URL, headers=auth_headers["a"], json={
            "name": "Bilingual", "geometry": {
                "type": "FeatureCollection",
                "features": [region("Cairo", {"name_ar": "القاهرة"}),
                             region("Giza", {"name_ar": "الجيزة"})]}})
        body = r.json()
        assert set(body["key_properties"]) == {"name", "name_ar"}
        assert body["sample_names"][:2] == ["Cairo", "Giza"]

    async def test_a_file_that_cannot_be_drawn_is_refused_with_a_reason(
            self, client, two_orgs, auth_headers):
        r = await client.post(URL, headers=auth_headers["a"], json={
            "name": "Points", "geometry": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {"name": "x"},
                              "geometry": {"type": "Point", "coordinates": [0, 0]}}]}})
        assert r.status_code == 400
        assert "polygon" in r.json()["detail"].lower()

    async def test_topojson_is_named_in_the_refusal(self, client, two_orgs, auth_headers):
        r = await client.post(URL, headers=auth_headers["a"], json={
            "name": "Topo", "geometry": {"type": "Topology", "objects": {}, "arcs": []}})
        assert r.status_code == 400
        assert "topojson" in r.json()["detail"].lower()

    async def test_a_name_is_required(self, client, two_orgs, auth_headers):
        r = await client.post(URL, headers=auth_headers["a"],
                              json={"name": "  ", "geometry": GOVERNORATES})
        assert r.status_code == 400

    async def test_two_sets_cannot_share_a_name_in_one_org(
            self, client, two_orgs, auth_headers):
        # The name is how an author picks one in the widget config; two the
        # same is a coin flip every time.
        first = await client.post(URL, headers=auth_headers["a"],
                                  json={"name": "States", "geometry": GOVERNORATES})
        assert first.status_code == 201
        again = await client.post(URL, headers=auth_headers["a"],
                                  json={"name": "States", "geometry": GOVERNORATES})
        assert again.status_code == 409

    async def test_the_same_name_in_another_org_is_fine(
            self, client, two_orgs, auth_headers):
        await client.post(URL, headers=auth_headers["a"],
                          json={"name": "States", "geometry": GOVERNORATES})
        other = await client.post(URL, headers=auth_headers["b"],
                                  json={"name": "States", "geometry": GOVERNORATES})
        assert other.status_code == 201

    async def test_an_oversized_file_is_refused(self, client, two_orgs, auth_headers):
        """Every viewer's browser downloads this to draw the map."""
        huge = {"type": "FeatureCollection",
                "features": [region(f"r{i}") for i in range(20_001)]}
        r = await client.post(URL, headers=auth_headers["a"],
                              json={"name": "Everything", "geometry": huge})
        assert r.status_code == 400
        assert "too many" in r.json()["detail"].lower()


class TestListingAndFetching:
    async def test_the_list_does_not_carry_the_geometry(
            self, client, two_orgs, auth_headers):
        """A picker that needed every file's polygons to draw a dropdown would
        download megabytes to show three words."""
        await client.post(URL, headers=auth_headers["a"],
                          json={"name": "Egypt", "geometry": GOVERNORATES})
        listed = await client.get(URL, headers=auth_headers["a"])
        assert listed.status_code == 200
        row = listed.json()[0]
        assert row["name"] == "Egypt"
        assert row["feature_count"] == 3
        assert "geometry" not in row

    async def test_fetching_one_returns_the_geometry_verbatim(
            self, client, two_orgs, auth_headers):
        made = await client.post(URL, headers=auth_headers["a"],
                                 json={"name": "Egypt", "geometry": GOVERNORATES})
        got = await client.get(f"{URL}/{made.json()['id']}", headers=auth_headers["a"])
        assert got.status_code == 200
        assert got.json()["geometry"] == GOVERNORATES

    async def test_another_orgs_set_is_a_404(self, client, two_orgs, auth_headers):
        made = await client.post(URL, headers=auth_headers["a"],
                                 json={"name": "Egypt", "geometry": GOVERNORATES})
        got = await client.get(f"{URL}/{made.json()['id']}", headers=auth_headers["b"])
        assert got.status_code == 404

    async def test_another_orgs_sets_are_not_listed(self, client, two_orgs, auth_headers):
        await client.post(URL, headers=auth_headers["a"],
                          json={"name": "Egypt", "geometry": GOVERNORATES})
        assert (await client.get(URL, headers=auth_headers["b"])).json() == []

    async def test_any_member_of_the_org_can_read_them(
            self, client, db_session, two_orgs, auth_headers):
        """Reference data, not private data: a colleague opening a dashboard
        that uses the set must be able to draw it."""
        await client.post(URL, headers=auth_headers["a"],
                          json={"name": "Egypt", "geometry": GOVERNORATES})
        headers = await _member(db_session, two_orgs["a"]["org"].id)
        assert len((await client.get(URL, headers=headers)).json()) == 1


class TestDeleting:
    async def test_the_creator_can_delete(self, client, two_orgs, auth_headers):
        made = await client.post(URL, headers=auth_headers["a"],
                                 json={"name": "Egypt", "geometry": GOVERNORATES})
        gone = await client.delete(f"{URL}/{made.json()['id']}", headers=auth_headers["a"])
        assert gone.status_code == 204
        assert (await client.get(URL, headers=auth_headers["a"])).json() == []

    async def test_another_member_cannot_delete_it(
            self, client, db_session, two_orgs, auth_headers):
        """Reading is org-wide; removing is not. A set may be behind widgets on
        dashboards the deleter has never seen."""
        made = await client.post(URL, headers=auth_headers["a"],
                                 json={"name": "Egypt", "geometry": GOVERNORATES})
        headers = await _member(db_session, two_orgs["a"]["org"].id)
        r = await client.delete(f"{URL}/{made.json()['id']}", headers=headers)
        assert r.status_code == 403

    async def test_an_org_admin_can_delete_it(
            self, client, db_session, two_orgs, auth_headers):
        made = await client.post(URL, headers=auth_headers["a"],
                                 json={"name": "Egypt", "geometry": GOVERNORATES})
        headers = await _member(db_session, two_orgs["a"]["org"].id, admin=True)
        r = await client.delete(f"{URL}/{made.json()['id']}", headers=headers)
        assert r.status_code == 204

    async def test_another_orgs_set_is_a_404_not_a_403(
            self, client, two_orgs, auth_headers):
        # A 403 on an id from another org confirms it exists.
        made = await client.post(URL, headers=auth_headers["a"],
                                 json={"name": "Egypt", "geometry": GOVERNORATES})
        r = await client.delete(f"{URL}/{made.json()['id']}", headers=auth_headers["b"])
        assert r.status_code == 404
