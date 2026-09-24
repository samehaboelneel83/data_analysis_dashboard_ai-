"""A data view an admin marks as the default for newly imported datasets.

Data views already snapshot a dataset's semantic layer -- classifications,
default aggregations, formats, calculated columns, measures, filter, prep steps,
hierarchy -- and they were already org-wide, which is most of what SAS means by
"shareable" and "publishable". The piece that was missing is SAS's ADMIN
DEFAULT: every dataset someone uploads arrives raw, and an organisation that has
already decided `amount` is a currency measure and `region` is a dimension has
to say so again on every single import.

Three properties decide whether this helps or surprises:

  * **One default per org.** Two defaults is a coin toss dressed as a setting,
    so marking a view default clears the previous one.

  * **Admin only.** It changes what every future upload looks like for everyone,
    which is exactly the shape of thing that belongs to an admin.

  * **It never fails an upload.** A default view that references columns this
    file does not have applies what it can and skips the rest, exactly as a
    manual apply does. The upload succeeding is worth more than the view
    landing whole, and what was skipped is reported rather than swallowed.
"""
import io

import pandas as pd
import pytest

from app.models.models import DataView


def _csv(rows: list[dict]) -> io.BytesIO:
    buf = io.BytesIO()
    buf.write(pd.DataFrame(rows).to_csv(index=False).encode())
    buf.seek(0)
    return buf


async def _member_headers(db_session, org_id):
    """A signed-in member of the org whose role is NOT an org admin."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User as UserModel
    role = Role(name="Analyst", org_id=org_id, is_org_admin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    user = UserModel(email="view-analyst@example.com", password_hash=hash_password("x"),
                     org_id=org_id, role_id=role.id, is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _upload(client, headers, name: str, rows: list[dict]):
    return await client.post(
        "/api/v1/datasets",
        files={"file": (f"{name}.csv", _csv(rows), "text/csv")},
        data={"name": name, "description": ""},
        headers=headers)


async def _view_from(client, db_session, headers, org_id, name="Standard layer",
                     rows=None):
    """A dataset with an authored layer, saved as a view."""
    rows = rows or [{"region": "N", "amount": 1.0}, {"region": "S", "amount": 2.0}]
    ds = (await _upload(client, headers, "source", rows)).json()
    # The whole map, wholesale — that is this endpoint's contract.
    meta = await client.put(
        f"/api/v1/datasets/{ds['id']}/column-meta",
        json={"meta": {"amount": {"role": "measure", "label": "Amount (USD)"}}},
        headers=headers)
    assert meta.status_code == 200, meta.text
    saved = await client.post(f"/api/v1/datasets/{ds['id']}/save-data-view",
                              params={"name": name}, headers=headers)
    assert saved.status_code == 201, saved.text
    return saved.json()["id"]


class TestMarkingOneDefault:
    async def test_an_admin_can_mark_a_view_as_the_default(
            self, client, auth_headers, db_session, two_orgs):
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        r = await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                               json={"default": True}, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        listed = (await client.get("/api/v1/datasets/data-views/list",
                                   headers=auth_headers["a"])).json()
        assert [v["is_default"] for v in listed if v["id"] == view_id] == [True]

    async def test_marking_a_second_one_clears_the_first(
            self, client, auth_headers, db_session, two_orgs):
        # Two defaults is a coin toss dressed up as a setting.
        first = await _view_from(client, db_session, auth_headers["a"],
                                 two_orgs["a"]["org"].id, name="First")
        second = await _view_from(client, db_session, auth_headers["a"],
                                  two_orgs["a"]["org"].id, name="Second")
        for vid in (first, second):
            await client.patch(f"/api/v1/datasets/data-views/{vid}/default",
                               json={"default": True}, headers=auth_headers["a"])
        listed = (await client.get("/api/v1/datasets/data-views/list",
                                   headers=auth_headers["a"])).json()
        assert {v["id"] for v in listed if v["is_default"]} == {second}

    async def test_it_can_be_turned_off_again(
            self, client, auth_headers, db_session, two_orgs):
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                           json={"default": True}, headers=auth_headers["a"])
        await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                           json={"default": False}, headers=auth_headers["a"])
        listed = (await client.get("/api/v1/datasets/data-views/list",
                                   headers=auth_headers["a"])).json()
        assert not any(v["is_default"] for v in listed)

    async def test_a_non_admin_cannot_change_it(
            self, client, auth_headers, db_session, two_orgs):
        """It decides what every future upload looks like for everyone in the
        org, which is the shape of thing that belongs to an admin."""
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        member = await _member_headers(db_session, two_orgs["a"]["org"].id)
        r = await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                               json={"default": True}, headers=member)
        assert r.status_code == 403

    async def test_another_org_cannot_see_or_set_it(
            self, client, auth_headers, db_session, two_orgs):
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        r = await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                               json={"default": True}, headers=auth_headers["b"])
        assert r.status_code in (403, 404)


class TestItLandsOnNewUploads:
    async def test_a_new_upload_arrives_with_the_default_applied(
            self, client, auth_headers, db_session, two_orgs):
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                           json={"default": True}, headers=auth_headers["a"])

        fresh = (await _upload(client, auth_headers["a"], "fresh",
                               [{"region": "N", "amount": 5.0}])).json()
        got = (await client.get(f"/api/v1/datasets/{fresh['id']}",
                                headers=auth_headers["a"])).json()
        assert got["column_meta"]["amount"]["role"] == "measure"
        assert got["column_meta"]["amount"]["label"] == "Amount (USD)"

    async def test_without_a_default_an_upload_is_untouched(
            self, client, auth_headers, db_session, two_orgs):
        await _view_from(client, db_session, auth_headers["a"], two_orgs["a"]["org"].id)
        fresh = (await _upload(client, auth_headers["a"], "fresh2",
                               [{"region": "N", "amount": 5.0}])).json()
        got = (await client.get(f"/api/v1/datasets/{fresh['id']}",
                                headers=auth_headers["a"])).json()
        assert not (got["column_meta"] or {}).get("amount")

    async def test_another_org_default_does_not_reach_this_org(
            self, client, auth_headers, db_session, two_orgs):
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                           json={"default": True}, headers=auth_headers["a"])

        theirs = (await _upload(client, auth_headers["b"], "theirs",
                                [{"region": "N", "amount": 5.0}])).json()
        got = (await client.get(f"/api/v1/datasets/{theirs['id']}",
                                headers=auth_headers["b"])).json()
        assert not (got["column_meta"] or {}).get("amount")

    async def test_a_default_that_does_not_fit_never_fails_the_upload(
            self, client, auth_headers, db_session, two_orgs):
        """The property that decides whether this is safe to turn on: a file
        with entirely different columns must still upload. Applying what fits
        and skipping the rest is what a manual apply already does."""
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                           json={"default": True}, headers=auth_headers["a"])

        r = await _upload(client, auth_headers["a"], "unrelated",
                          [{"patient": "A", "bmi": 22.5}])
        assert r.status_code == 200, r.text
        got = (await client.get(f"/api/v1/datasets/{r.json()['id']}",
                                headers=auth_headers["a"])).json()
        assert not (got["column_meta"] or {}).get("amount")

    async def test_a_deleted_default_view_stops_applying(
            self, client, auth_headers, db_session, two_orgs):
        view_id = await _view_from(client, db_session, auth_headers["a"],
                                   two_orgs["a"]["org"].id)
        await client.patch(f"/api/v1/datasets/data-views/{view_id}/default",
                           json={"default": True}, headers=auth_headers["a"])
        await client.delete(f"/api/v1/datasets/data-views/{view_id}",
                            headers=auth_headers["a"])

        fresh = (await _upload(client, auth_headers["a"], "after-delete",
                               [{"region": "N", "amount": 5.0}])).json()
        got = (await client.get(f"/api/v1/datasets/{fresh['id']}",
                                headers=auth_headers["a"])).json()
        assert not (got["column_meta"] or {}).get("amount")


class TestTheModel:
    async def test_the_column_exists_and_defaults_to_false(self, db_session, two_orgs):
        # `create_all` never ALTERs a deployed table, so this ships as an
        # alembic revision; a fresh database gets it from the model.
        view = DataView(org_id=two_orgs["a"]["org"].id, name="V", payload={})
        db_session.add(view)
        await db_session.commit()
        await db_session.refresh(view)
        assert view.is_default is False
