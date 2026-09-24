"""A dataflow's permissions are ITS OWN -- the point of the whole object.

The hole this closes is concrete, and it is in `core/capability.py`:

    async def max_dataset_capability(...):
        ...
        if not report_ids:
            return "data"      # a dataset no report uses is unrestricted

A materialized result is, by definition, used by no report the moment it is
created. So under the old inheritance every member of the org could author a
freshly built transformation -- and two endpoints (DELETE /datasets/{id} and
PATCH /refresh-schedule) consulted no capability at all, so anyone could delete
or reschedule anybody's pipeline.

The tests below are split along the line that matters:

  * AUTHORING is gated -- edit, schedule, run, delete, grant.
  * READING is NOT. An output is an ordinary dataset, readable org-wide with RLS
    narrowing rows per identity. That is the platform's existing model, and a
    test proves the restriction genuinely stops at the recipe rather than
    quietly becoming a read control.
"""
import pandas as pd
import pytest

from app.core.security import create_access_token
from app.models.models import (Dataflow, DataflowCapability, Dataset,
                               DatasetColumn, Role, User)


@pytest.fixture(autouse=True)
def _uploads(tmp_path, monkeypatch):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    return tmp_path


async def _member(db, org_id, email="member@example.com"):
    """A NON-admin user. Admins are always 'data', so every restriction test
    needs an ordinary role or it would prove nothing."""
    role = Role(org_id=org_id, name="Analyst", is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org_id, role_id=role.id, email=email,
                password_hash="x", is_active=True)
    db.add(user)
    await db.flush()
    return role, user, {"Authorization": f"Bearer {create_access_token(user.id, org_id)}"}


async def _source(db, org_id, tmp_path, rows=6):
    path = tmp_path / "src.csv"
    pd.DataFrame({"k": [f"v{i}" for i in range(rows)],
                  "n": range(rows)}).to_csv(path, index=False)
    ds = Dataset(name="Source", filename=str(path), org_id=org_id, mode="import",
                 row_count=rows, col_count=2)
    db.add(ds)
    await db.flush()
    for c in ("k", "n"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db.flush()
    return ds


async def _flow(db, org_id, src_id, creator_id, steps=None):
    flow = Dataflow(org_id=org_id, name="Nightly", source_dataset_id=src_id,
                    steps=steps or [], join_dataset_ids=[], created_by=creator_id)
    db.add(flow)
    await db.flush()
    return flow


async def _grant(db, flow_id, role_id, level):
    db.add(DataflowCapability(dataflow_id=flow_id, role_id=role_id, level=level))
    await db.commit()


class TestTheDefaultIsOpen:
    """A deny-by-default table would break every existing workflow on the day it
    ships. Grants RESTRICT; they are not a licence somebody must be issued."""

    @pytest.mark.asyncio
    async def test_no_grants_at_all_means_full_access(
            self, client, db_session, two_orgs, _uploads):
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        _, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()

        r = await client.put(f"/api/v1/dataflows/{flow.id}",
                             json={"name": "Renamed"}, headers=hdr)

        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_an_admin_is_always_data_even_when_restricted(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """An admin locked out could not administer the restriction that locked
        them out."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, two_orgs["a"]["role"].id, "view")

        r = await client.delete(f"/api/v1/dataflows/{flow.id}",
                                headers=auth_headers["a"])

        assert r.status_code == 204, r.text


class TestAuthoringIsGated:
    """The feature itself: a role restricted to 'view' cannot change anything."""

    @pytest.mark.asyncio
    async def test_view_cannot_edit_the_recipe(
            self, client, db_session, two_orgs, _uploads):
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, role.id, "view")

        r = await client.put(f"/api/v1/dataflows/{flow.id}",
                             json={"name": "Hijacked"}, headers=hdr)

        assert r.status_code == 403
        assert "view-level" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_view_cannot_run_it(self, client, db_session, two_orgs, _uploads):
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, role.id, "view")

        r = await client.post(f"/api/v1/dataflows/{flow.id}/run",
                              json={"output_name": "Out"}, headers=hdr)

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_can_run_but_cannot_delete(
            self, client, db_session, two_orgs, _uploads):
        """The levels are additive and distinct -- otherwise 'edit' would be
        indistinguishable from 'data' and the middle tier would be decoration."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, role.id, "edit")

        ran = await client.post(f"/api/v1/dataflows/{flow.id}/run",
                                json={"output_name": "Out"}, headers=hdr)
        deleted = await client.delete(f"/api/v1/dataflows/{flow.id}", headers=hdr)

        assert ran.status_code == 200, ran.text
        assert deleted.status_code == 403

    @pytest.mark.asyncio
    async def test_view_cannot_grant_itself_more(
            self, client, db_session, two_orgs, _uploads):
        """If a restricted role could rewrite the grants, the restriction would
        be advisory."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, role.id, "view")

        r = await client.put(f"/api/v1/dataflows/{flow.id}/capabilities",
                             json={"grants": [{"role_id": role.id, "level": "data"}]},
                             headers=hdr)

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_a_role_with_no_row_among_others_is_restricted(
            self, client, db_session, two_orgs, _uploads):
        """Once ANY grant exists the dataflow is governed, so an unlisted role
        falls to 'view'. Otherwise granting one team access would restrict
        nobody and the grant would mean nothing."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        other = Role(org_id=org.id, name="Other", is_org_admin=False)
        db_session.add(other)
        await db_session.flush()
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, other.id, "data")   # someone ELSE

        r = await client.put(f"/api/v1/dataflows/{flow.id}",
                             json={"name": "Hijacked"}, headers=hdr)

        assert r.status_code == 403


class TestReadingIsNotGated:
    """The restriction must stop at the recipe. If it quietly became a read
    control it would contradict every other read path in the platform."""

    @pytest.mark.asyncio
    async def test_view_still_sees_the_dataflow_and_its_run_history(
            self, client, db_session, two_orgs, _uploads):
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()
        await _grant(db_session, flow.id, role.id, "view")

        r = await client.get(f"/api/v1/dataflows/{flow.id}", headers=hdr)

        assert r.status_code == 200
        assert r.json()["your_capability"] == "view"

    @pytest.mark.asyncio
    async def test_view_still_reads_the_output_data_in_full(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """The whole authoring-only decision, proven rather than asserted: a
        user who cannot touch the recipe still sees every row it produced."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()

        made = await client.post(f"/api/v1/dataflows/{flow.id}/run",
                                 json={"output_name": "Out"},
                                 headers=auth_headers["a"])
        assert made.status_code == 200, made.text
        out_id = made.json()["outputs"][0]["id"]
        await _grant(db_session, flow.id, role.id, "view")

        seen = await client.post(
            f"/api/v1/datasets/{out_id}/widget-data",
            json={"widget_type": "bar",
                  "config": {"dimension": "k", "measure": "n", "aggregation": "sum"}},
            headers=hdr)

        assert seen.status_code == 200, seen.text
        assert len(seen.json()["rows"]) == 6, "the reader lost rows to a permission"


class TestTheOutputCannotRouteAroundTheDataflow:
    """Operating on what a pipeline produced must not bypass the pipeline's own
    permissions -- otherwise the grants protect the recipe and nothing else."""

    async def _flow_with_output(self, client, db_session, org, auth_headers, tmp_path):
        src = await _source(db_session, org.id, tmp_path)
        flow = await _flow(db_session, org.id, src.id, None)
        await db_session.commit()
        made = await client.post(f"/api/v1/dataflows/{flow.id}/run",
                                 json={"output_name": "Out"}, headers=auth_headers["a"])
        assert made.status_code == 200, made.text
        return flow, made.json()["outputs"][0]["id"]

    @pytest.mark.asyncio
    async def test_view_cannot_delete_the_output_dataset(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        org = two_orgs["a"]["org"]
        flow, out_id = await self._flow_with_output(
            client, db_session, org, auth_headers, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        await _grant(db_session, flow.id, role.id, "view")

        r = await client.delete(f"/api/v1/datasets/{out_id}", headers=hdr)

        assert r.status_code == 403, "deleting the output bypassed the dataflow"

    @pytest.mark.asyncio
    async def test_view_cannot_reschedule_the_output_dataset(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        org = two_orgs["a"]["org"]
        flow, out_id = await self._flow_with_output(
            client, db_session, org, auth_headers, _uploads)
        role, _, hdr = await _member(db_session, org.id)
        await _grant(db_session, flow.id, role.id, "view")

        r = await client.patch(f"/api/v1/datasets/{out_id}/refresh-schedule",
                               json={"interval_minutes": 60}, headers=hdr)

        assert r.status_code == 403


class TestOrgIsolation:
    @pytest.mark.asyncio
    async def test_another_org_gets_404_not_403(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """404, never 403: a 403 would confirm the dataflow exists, which is
        itself the leak."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        flow = await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()

        r = await client.get(f"/api/v1/dataflows/{flow.id}", headers=auth_headers["b"])

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_the_list_never_crosses_orgs(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        await _flow(db_session, org.id, src.id, two_orgs["a"]["user"].id)
        await db_session.commit()

        r = await client.get("/api/v1/dataflows", headers=auth_headers["b"])

        assert r.status_code == 200
        assert r.json() == []
