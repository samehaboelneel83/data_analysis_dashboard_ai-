"""Dataflows: the object itself -- CRUD, multiple outputs, and the refusals it
must not become a way around.

The safety half matters more than the CRUD half. `POST /datasets/{id}/materialize`
refuses to snapshot governed data (a snapshot would freeze one person's
row-security slice as everyone's data) and refuses when exports are disabled
(materializing writes a downloadable copy, so treating it as anything but an
export makes the control bypassable). A dataflow runs the same machinery, so both
refusals must carry over -- otherwise "make a dataflow instead" is the documented
bypass for both controls.
"""
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.models.models import (ColumnSecurityRule, Dataflow, Dataset,
                               DatasetColumn, Role, RowSecurityRule)
from app.routers.dataflows import _out
from app.services.prep import derived_from_of


@pytest.fixture(autouse=True)
def _uploads(tmp_path, monkeypatch):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    return tmp_path


async def _source(db, org_id, tmp_path, rows=6, name="Source"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"k": [f"v{i}" for i in range(rows)],
                  "n": range(rows)}).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, mode="import",
                 row_count=rows, col_count=2)
    db.add(ds)
    await db.flush()
    for c in ("k", "n"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db.commit()
    return ds


async def _create(client, headers, src_id, **over):
    body = {"name": "Nightly", "source_dataset_id": src_id, "steps": []}
    body.update(over)
    return await client.post("/api/v1/dataflows", json=body, headers=headers)


class TestTheObject:
    @pytest.mark.asyncio
    async def test_create_then_read_it_back(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)

        made = await _create(client, auth_headers["a"], src.id)
        assert made.status_code == 201, made.text

        got = await client.get(f"/api/v1/dataflows/{made.json()['id']}",
                               headers=auth_headers["a"])
        assert got.status_code == 200
        assert got.json()["source_dataset_id"] == src.id

    @pytest.mark.asyncio
    async def test_a_recipe_that_cannot_run_is_refused_at_create(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """A structurally invalid step should fail while its author is looking
        at it, not silently at 3am on a schedule."""
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)

        r = await _create(client, auth_headers["a"], src.id,
                          steps=[{"kind": "filter_rows"}])

        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_editing_the_recipe_revalidates_it(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]

        r = await client.put(f"/api/v1/dataflows/{fid}",
                             json={"steps": [{"kind": "not_a_real_step"}]},
                             headers=auth_headers["a"])

        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_deleting_a_dataflow_keeps_its_outputs(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """Outputs are ordinary datasets reports may already point at. Deleting
        a recipe is not a statement about the data it produced -- removing them
        would turn a tidy-up into data loss."""
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]
        ran = await client.post(f"/api/v1/dataflows/{fid}/run",
                                json={"output_name": "Out"}, headers=auth_headers["a"])
        out_id = ran.json()["outputs"][0]["id"]

        gone = await client.delete(f"/api/v1/dataflows/{fid}", headers=auth_headers["a"])
        still = await client.get(f"/api/v1/datasets/{out_id}", headers=auth_headers["a"])

        assert gone.status_code == 204
        assert still.status_code == 200, "deleting the recipe destroyed the data"


class TestRunningIt:
    @pytest.mark.asyncio
    async def test_a_run_creates_an_output_carrying_provenance(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]

        r = await client.post(f"/api/v1/dataflows/{fid}/run",
                              json={"output_name": "Out"}, headers=auth_headers["a"])

        assert r.status_code == 200, r.text
        assert r.json()["rows"] == 6
        out = await db_session.get(Dataset, r.json()["outputs"][0]["id"])
        assert (derived_from_of(out) or {}).get("dataflow_id") == fid

    @pytest.mark.asyncio
    async def test_one_dataflow_can_own_several_outputs(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """The difference from materialize: a recipe is no longer trapped as one
        dataset's tail."""
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]

        for name in ("First", "Second"):
            r = await client.post(f"/api/v1/dataflows/{fid}/run",
                                  json={"output_name": name}, headers=auth_headers["a"])
            assert r.status_code == 200, r.text

        got = await client.get(f"/api/v1/dataflows/{fid}", headers=auth_headers["a"])
        assert len(got.json()["outputs"]) == 2

    @pytest.mark.asyncio
    async def test_a_nameless_run_refreshes_every_output_in_place(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """What the scheduler calls. Written in place so reports pointing at an
        output pick the new rows up with no rewiring."""
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]
        made = await client.post(f"/api/v1/dataflows/{fid}/run",
                                 json={"output_name": "Out"}, headers=auth_headers["a"])
        out_id = made.json()["outputs"][0]["id"]
        before = (await db_session.get(Dataset, out_id)).filename

        pd.DataFrame({"k": list("abcdefghij"), "n": range(10)}).to_csv(
            src.filename, index=False)
        again = await client.post(f"/api/v1/dataflows/{fid}/run", json={},
                                  headers=auth_headers["a"])

        assert again.status_code == 200, again.text
        assert again.json()["rows"] == 10
        after = await db_session.get(Dataset, out_id)
        await db_session.refresh(after)
        assert after.filename == before, "the output moved; reports would break"

    @pytest.mark.asyncio
    async def test_a_run_records_its_status(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]

        await client.post(f"/api/v1/dataflows/{fid}/run",
                          json={"output_name": "Out"}, headers=auth_headers["a"])

        flow = await db_session.get(Dataflow, fid)
        await db_session.refresh(flow)
        assert flow.last_run_status == "ok"
        assert flow.last_run_rows == 6

    @pytest.mark.asyncio
    async def test_a_missing_source_is_a_409_not_a_crash(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        src = await _source(db_session, two_orgs["a"]["org"].id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]
        await client.delete(f"/api/v1/datasets/{src.id}", headers=auth_headers["a"])

        r = await client.post(f"/api/v1/dataflows/{fid}/run",
                              json={"output_name": "Out"}, headers=auth_headers["a"])

        assert r.status_code == 409


class TestItIsNotAWayAroundTheRefusals:
    """The half that matters. If either refusal failed to carry over, "make a
    dataflow instead" would be the documented bypass for a security control."""

    @pytest.mark.asyncio
    async def test_a_row_secured_source_cannot_feed_a_dataflow(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """A snapshot taken by one person would freeze THEIR slice as everyone's
        data -- and the output carries no rules of its own."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        db_session.add(RowSecurityRule(dataset_id=src.id, role_id=two_orgs["a"]["role"].id,
                                       filter_expr="k = 'v1'"))
        await db_session.commit()
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]

        r = await client.post(f"/api/v1/dataflows/{fid}/run",
                              json={"output_name": "Out"}, headers=auth_headers["a"])

        assert r.status_code == 403
        assert "security" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_a_column_secured_source_cannot_feed_a_dataflow(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        db_session.add(ColumnSecurityRule(dataset_id=src.id,
                                          role_id=two_orgs["a"]["role"].id,
                                          denied_columns=["n"]))
        await db_session.commit()
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]

        r = await client.post(f"/api/v1/dataflows/{fid}/run",
                              json={"output_name": "Out"}, headers=auth_headers["a"])

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_rules_added_after_creation_still_stop_a_run(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        """Every refusal re-runs on EVERY run, not just at create -- otherwise a
        dataflow made before the rules existed would launder newly-governed data
        on its next tick."""
        org = two_orgs["a"]["org"]
        src = await _source(db_session, org.id, _uploads)
        fid = (await _create(client, auth_headers["a"], src.id)).json()["id"]
        ok = await client.post(f"/api/v1/dataflows/{fid}/run",
                               json={"output_name": "Out"}, headers=auth_headers["a"])
        assert ok.status_code == 200

        db_session.add(RowSecurityRule(dataset_id=src.id, role_id=two_orgs["a"]["role"].id,
                                       filter_expr="k = 'v1'"))
        await db_session.commit()

        after = await client.post(f"/api/v1/dataflows/{fid}/run", json={},
                                  headers=auth_headers["a"])

        assert after.status_code == 403


class TestCrossOrg:
    @pytest.mark.asyncio
    async def test_cannot_build_a_dataflow_on_another_orgs_dataset(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        src = await _source(db_session, two_orgs["b"]["org"].id, _uploads)

        r = await _create(client, auth_headers["a"], src.id)

        assert r.status_code == 404


class TestTimestampSerialization:
    """last_run_at/created_at are DateTime(timezone=True) columns -- Postgres
    hands them back tz-aware, whose .isoformat() already carries a "+00:00"
    offset. SQLite (this suite's test DB) silently returns them naive, so a
    round trip through the real endpoints never exercises the aware case --
    this is why the bug shipped and only surfaced live, as "NaNd ago" in
    Dataflows.tsx, well after the test suite stayed green."""

    def test_a_timezone_aware_last_run_at_does_not_get_a_double_offset(self):
        flow = Dataflow(
            id=1, name="f", description=None, source_dataset_id=1,
            join_dataset_ids=[], steps=[], refresh_interval_minutes=None,
            created_by=1,
            created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            last_run_at=datetime(2026, 8, 1, 12, 5, 0, tzinfo=timezone.utc),
            last_run_status="ok", last_run_rows=10, last_run_error=None)

        out = _out(flow)

        # "...+00:00" + "Z" == "...+00:00Z", which `new Date()` cannot parse.
        assert "+00:00Z" not in (out["last_run_at"] or "")
        assert "+00:00Z" not in (out["created_at"] or "")
        assert out["last_run_at"] == "2026-08-01T12:05:00Z"
        assert out["created_at"] == "2026-08-01T12:00:00Z"
