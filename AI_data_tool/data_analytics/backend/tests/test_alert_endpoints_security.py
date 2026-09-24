"""Alerts are reachable, and reachable only by people who may read the dataset.

The evaluator has been running on every scheduler tick for months
(`refresh_scheduler.py` calls `check_alert`), firing on the rising edge and
resolving RLS as the alert's creator. Everything worked except the part that
lets anybody create one -- so the feature shipped complete and invisible, the
same pattern as `explain_response` and `goal_seek`.

Two holes had to close before a UI could be pointed at these endpoints:

  * All three gated on `check_org` alone. Datasets are per-user now (the read
    resolver decides who may see one), so org membership is not authorisation --
    any colleague could list, create against, or delete alerts on a dataset they
    were never granted.
  * `delete_alert` looked the alert up by id and checked only its ORG. It never
    checked that the alert belonged to the dataset named in the path, so the
    path segment was decorative: name any dataset you CAN read, pass the id of
    an alert on one you cannot, and it is deleted.

The second is the more interesting one, because adding `require_dataset_read`
alone would not have closed it.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import DataAlert, Dataset, Role, User


async def _dataset(db_session, tmp_path, org_id, owner_id, name="Watched"):
    """A dataset with an OWNER.

    `created_by` matters and is easy to leave off: `readable_dataset_ids`
    treats `created_by IS NULL` as "every member of the org may read it" --
    the compatibility path for datasets that predate per-user visibility. A
    fixture without an owner therefore proves nothing about authorisation,
    because everyone really is authorised.
    """
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"region": ["n", "s"], "revenue": [10, 20]}).to_csv(path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(path), created_by=owner_id)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _other_member(db_session, org_id):
    """Someone in the same org who was never granted this dataset."""
    role = Role(org_id=org_id, name="Bystander", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id,
                email=f"bystander-{role.id}@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


def _url(ds_id, alert_id=None):
    base = f"/api/v1/datasets/{ds_id}/alerts"
    return base if alert_id is None else f"{base}/{alert_id}"


BODY = {"name": "Revenue fell", "expression": "SUM(revenue) < 100",
        "interval_minutes": 60, "recipients": ["ops@example.com"]}


class TestTheOwnerCanUseThem:
    async def test_create_then_list(self, client, db_session, two_orgs,
                                    auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        made = await client.post(_url(ds.id), headers=auth_headers["a"], json=BODY)
        assert made.status_code == 201, made.text

        listed = await client.get(_url(ds.id), headers=auth_headers["a"])
        assert listed.status_code == 200
        assert [a["name"] for a in listed.json()] == ["Revenue fell"]

    async def test_delete_removes_it(self, client, db_session, two_orgs,
                                     auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        made = await client.post(_url(ds.id), headers=auth_headers["a"], json=BODY)
        gone = await client.delete(_url(ds.id, made.json()["id"]),
                                   headers=auth_headers["a"])
        assert gone.status_code == 204
        assert (await client.get(_url(ds.id), headers=auth_headers["a"])).json() == []

    async def test_a_rejected_expression_is_refused_at_creation(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        """An alert that fails the sandbox gate would only ever report
        evaluation errors, every tick, forever."""
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"],
                              json={**BODY, "expression": "__import__('os').system('x')"})
        assert r.status_code == 400

    async def test_a_recipient_that_is_not_an_email_is_refused(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"],
                              json={**BODY, "recipients": ["not-an-address"]})
        assert r.status_code == 400


class TestOrgMembershipIsNotAuthorisation:
    """Datasets are per-user: being in the org says nothing about whether this
    person may see this data. An alert emails its condition to whoever it
    names, so creating one against a dataset you cannot read is a way to have
    the scheduler read it out to you."""

    async def test_listing_is_a_404_for_a_bystander(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        headers = await _other_member(db_session, two_orgs["a"]["org"].id)
        assert (await client.get(_url(ds.id), headers=headers)).status_code == 404

    async def test_creating_is_a_404_for_a_bystander(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        headers = await _other_member(db_session, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=headers, json=BODY)
        assert r.status_code == 404

    async def test_deleting_is_a_404_for_a_bystander(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        made = await client.post(_url(ds.id), headers=auth_headers["a"], json=BODY)
        headers = await _other_member(db_session, two_orgs["a"]["org"].id)
        r = await client.delete(_url(ds.id, made.json()["id"]), headers=headers)
        assert r.status_code == 404

    async def test_another_org_cannot_see_them(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                             two_orgs["a"]["user"].id)
        assert (await client.get(_url(ds.id),
                                 headers=auth_headers["b"])).status_code == 404


class TestTheAlertMustBelongToTheDatasetInThePath:
    """`delete_alert` looked the alert up by ID and checked only its org, so the
    dataset in the path was decorative. `require_dataset_read` alone does not
    fix this: the caller passes a dataset they CAN read and an alert id from one
    they cannot."""

    async def test_deleting_through_the_wrong_dataset_is_refused(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        secret = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                                two_orgs["a"]["user"].id, name="Secret")
        mine = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                              two_orgs["a"]["user"].id, name="Mine")
        made = await client.post(_url(secret.id), headers=auth_headers["a"],
                                 json=BODY)
        alert_id = made.json()["id"]

        r = await client.delete(_url(mine.id, alert_id), headers=auth_headers["a"])
        assert r.status_code == 404

        still = (await db_session.execute(
            select(DataAlert).where(DataAlert.id == alert_id))).scalar_one_or_none()
        assert still is not None, "the alert was deleted through the wrong dataset"

    async def test_listing_never_leaks_another_datasets_alerts(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        a = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                        two_orgs["a"]["user"].id, name="A")
        b = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id,
                        two_orgs["a"]["user"].id, name="B")
        await client.post(_url(a.id), headers=auth_headers["a"],
                          json={**BODY, "name": "on A"})
        listed = await client.get(_url(b.id), headers=auth_headers["a"])
        assert listed.json() == []
