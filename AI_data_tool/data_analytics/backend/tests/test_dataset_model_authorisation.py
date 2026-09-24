"""Who may change a dataset's shared model.

Found by sweeping all 267 API operations as all five personas. The permission
model held everywhere it was asked — no non-admin reached an `/admin/*` route,
and nothing returned a 500 in 1,335 calls. What the sweep exposed instead is a
handful of endpoints that change state shared by the whole organisation and ask
no permission question at all beyond "are you in this org".

`POST /datasets/{id}/export-policy` looked like one, because its dependency is
`get_current_user` and only its docstring mentions admins. It turned out to be
enforced properly inside the function body — these tests were written expecting a
failure, passed immediately, and are kept as regression guards for a rule that is
currently only stated in one place.

The real one is `PUT /datasets/{id}/column-meta`, proven against the running app:
a Guest wrote `{"student": {"label": "GUEST WAS HERE"}}` onto the instructor's
dataset and it landed in the database.

These endpoints write the dataset's visible model: column labels, roles, formats, a
duplicated column, the saved data-view hierarchy. Those are *authoring*, which
this platform deliberately leaves open to members by default
(`core/capability.py`), so the fix there is not to close them but to route them
through `require_dataset_capability` — the platform's own authoring gate — so an
admin who restricts a role actually restricts it. Today those endpoints never ask,
so the control cannot be applied at all.
"""
import pytest
from sqlalchemy import select

from app.models.models import Dataset, Report, ReportCapability, Role, User


async def _member(db_session, org_id, email="viewer@a.invalid"):
    """A plain member — no admin flag. What the product calls a Guest."""
    role = Role(org_id=org_id, name="Guest", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email,
                password_hash="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    return user, role


def _headers(user):
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _dataset(db_session, org_id, owner_id=None):
    ds = Dataset(name="Grades", org_id=org_id, filename=None,
                 created_by=owner_id, column_meta={})
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


class TestExportPolicy:
    """The docstring's own rule, now enforced."""

    async def test_a_plain_member_cannot_change_the_export_policy(
            self, client, db_session, two_orgs, auth_headers):
        org = two_orgs["a"]["org"]
        user, _ = await _member(db_session, org.id)
        ds = await _dataset(db_session, org.id, two_orgs["a"]["user"].id)

        r = await client.post(
            f"/api/v1/datasets/{ds.id}/export-policy?disabled=true",
            headers=_headers(user))

        assert r.status_code == 403, (
            "a governance control any member can flip is not a control")

    async def test_an_admin_still_can(self, client, db_session, two_orgs, auth_headers):
        org = two_orgs["a"]["org"]
        ds = await _dataset(db_session, org.id, two_orgs["a"]["user"].id)

        r = await client.post(
            f"/api/v1/datasets/{ds.id}/export-policy?disabled=true",
            headers=auth_headers["a"])

        assert r.status_code == 200, r.text

    async def test_another_organisation_still_gets_404(
            self, client, db_session, two_orgs, auth_headers):
        """Org scoping first: a dataset you cannot see is absent, not forbidden."""
        ds = await _dataset(db_session, two_orgs["a"]["org"].id)
        r = await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true",
                              headers=auth_headers["b"])
        assert r.status_code == 404


class TestTheModelEditingEndpoints:
    """These stay open by default — authoring is deliberately permissive here —
    but they must ASK, so that an admin who restricts a role is obeyed."""

    async def _restricted(self, db_session, org_id):
        """A member whose role is held below `data` on every report using the
        dataset, which is what `max_dataset_capability` reads."""
        user, role = await _member(db_session, org_id, "restricted@a.invalid")
        ds = await _dataset(db_session, org_id)
        report = Report(name="R", org_id=org_id, dataset_id=ds.id)
        db_session.add(report)
        await db_session.flush()
        db_session.add(ReportCapability(report_id=report.id, role_id=role.id,
                                        level="view"))
        await db_session.commit()
        return user, ds

    async def test_column_meta_obeys_a_restriction(self, client, db_session, two_orgs):
        user, ds = await self._restricted(db_session, two_orgs["a"]["org"].id)
        r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                             json={"meta": {}}, headers=_headers(user))
        assert r.status_code == 403, r.text

    async def test_column_formats_obeys_a_restriction(self, client, db_session, two_orgs):
        user, ds = await self._restricted(db_session, two_orgs["a"]["org"].id)
        r = await client.put(f"/api/v1/datasets/{ds.id}/column-formats",
                             # `format: null` clears it -- a valid body, so the
                             # request reaches the authorisation check rather than
                             # being turned away by FastAPI's own validation first.
                             json={"column": "grade", "format": None},
                             headers=_headers(user))
        assert r.status_code == 403, r.text

    async def test_duplicating_a_column_obeys_a_restriction(self, client, db_session,
                                                            two_orgs):
        user, ds = await self._restricted(db_session, two_orgs["a"]["org"].id)
        r = await client.post(f"/api/v1/datasets/{ds.id}/columns/grade/duplicate",
                              headers=_headers(user))
        assert r.status_code == 403, r.text

    async def test_an_unrestricted_member_is_still_allowed(
            self, client, db_session, two_orgs):
        """The default stays open. This is an authoring gate, not a lockout —
        closing it by default would break every existing installation."""
        user, _ = await _member(db_session, two_orgs["a"]["org"].id, "open@a.invalid")
        ds = await _dataset(db_session, two_orgs["a"]["org"].id)

        r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                             json={"meta": {}}, headers=_headers(user))

        assert r.status_code == 200, r.text
