"""Re-running the recipe behind a materialized dataset.

A saved join is a SNAPSHOT: it does not follow its sources, which is what makes
it safe to build a report on. `POST /datasets/{id}/rebuild` is the deliberate
way to catch it up, and the two properties that matter are:

  * it replays the recipe captured at save time, NOT the source's current
    pipeline -- otherwise editing a source's steps would silently change a
    dataset somebody else's report depends on; and
  * it fails HARD where a read fails soft. `_apply_one` treats a missing join
    frame as a no-op, which costs one widget on a read and would silently drop
    every joined column from a persisted dataset here.
"""
import pandas as pd
import pytest

from app.core.config import settings as app_settings
from app.models.models import Dataset, DatasetColumn, RowSecurityRule
from app.services import quotas
from app.services.prep import DERIVED_FROM_KEY


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    quotas.invalidate_quota_cache()
    yield tmp_path
    quotas.invalidate_quota_cache()


@pytest.fixture
def two_files(tmp_path):
    o = tmp_path / "orders.csv"
    pd.DataFrame({"cust": ["a", "b", "c"], "amount": [10.0, 20.0, 30.0]}).to_csv(o, index=False)
    c = tmp_path / "customers.csv"
    pd.DataFrame({"id": ["a", "b", "c"], "segment": ["SMB", "ENT", "GOV"]}).to_csv(c, index=False)
    return str(o), str(c)


async def _pair(db, org, two_files):
    opath, cpath = two_files
    left = Dataset(name="Orders", filename=opath, org_id=org.id, mode="import")
    right = Dataset(name="Customers", filename=cpath, org_id=org.id, mode="import")
    db.add_all([left, right])
    await db.flush()
    for ds, cols in ((left, ["cust", "amount"]), (right, ["id", "segment"])):
        for c in cols:
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db.commit()
    return left, right


def _join(right_id):
    return {"kind": "join", "dataset_id": right_id, "how": "left",
            "left_on": "cust", "right_on": "id"}


async def _build(client, headers, db, org, two_files):
    """A materialized dataset plus its two sources."""
    left, right = await _pair(db, org, two_files)
    resp = await client.post(f"/api/v1/datasets/{left.id}/materialize",
                             json={"name": "Joined", "steps": [_join(right.id)]},
                             headers=headers)
    assert resp.status_code == 200, resp.text
    return left, right, resp.json()


async def _rebuild(client, headers, ds_id):
    return await client.post(f"/api/v1/datasets/{ds_id}/rebuild", headers=headers)


class TestItRefreshesFromTheSources:
    @pytest.mark.asyncio
    async def test_it_picks_up_changed_source_rows(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, right, new = await _build(client, auth_headers["a"],
                                        db_session, two_orgs["a"]["org"], two_files)
        assert new["row_count"] == 3

        pd.DataFrame({"cust": ["a", "b", "c", "d"],
                      "amount": [1.0, 2.0, 3.0, 4.0]}).to_csv(left.filename, index=False)

        resp = await _rebuild(client, auth_headers["a"], new["id"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["row_count"] == 4

    @pytest.mark.asyncio
    async def test_the_old_file_and_its_sidecar_are_removed(
            self, client, auth_headers, db_session, two_orgs, two_files):
        from pathlib import Path
        _, _, new = await _build(client, auth_headers["a"],
                                 db_session, two_orgs["a"]["org"], two_files)
        old = Path(new["filename"])
        assert old.exists()

        after = (await _rebuild(client, auth_headers["a"], new["id"])).json()

        assert Path(after["filename"]) != old
        assert not old.exists(), "the superseded file was left behind"
        assert not Path(str(old) + ".parquet").exists()

    @pytest.mark.asyncio
    async def test_it_replays_the_snapshot_not_the_sources_current_pipeline(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """The core guarantee. Somebody editing the source's pipeline must not
        change what a already-built dataset contains on its next rebuild."""
        left, right, new = await _build(client, auth_headers["a"],
                                        db_session, two_orgs["a"]["org"], two_files)

        # The source now filters itself down to one row...
        r = await client.put(f"/api/v1/datasets/{left.id}/prep-steps",
                             json=[{"kind": "filter_rows", "expression": "`cust` == 'a'"}],
                             headers=auth_headers["a"])
        assert r.status_code == 200, r.text

        resp = await _rebuild(client, auth_headers["a"], new["id"])

        # ...but the snapshot's own recipe still says "join, no filter".
        assert resp.status_code == 200, resp.text
        assert resp.json()["row_count"] == 3
        ds = await db_session.get(Dataset, new["id"])
        assert (ds.column_meta or {})[DERIVED_FROM_KEY]["steps"][0]["kind"] == "join"

    @pytest.mark.asyncio
    async def test_it_records_who_rebuilt_it_and_when(
            self, client, auth_headers, db_session, two_orgs, two_files):
        _, _, new = await _build(client, auth_headers["a"],
                                 db_session, two_orgs["a"]["org"], two_files)
        before = (await db_session.get(Dataset, new["id"])).last_refreshed_at

        await _rebuild(client, auth_headers["a"], new["id"])

        db_session.expire_all()
        ds = await db_session.get(Dataset, new["id"])
        assert ds.last_refreshed_at >= before


class TestItFailsHardNotSoft:
    @pytest.mark.asyncio
    async def test_a_deleted_source_is_a_409_and_the_data_is_left_alone(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """Reads degrade to a no-op on a missing frame. Here that would silently
        drop every joined column, so refuse and keep the last good snapshot."""
        from pathlib import Path
        left, _, new = await _build(client, auth_headers["a"],
                                    db_session, two_orgs["a"]["org"], two_files)
        rows_before = new["row_count"]

        r = await client.delete(f"/api/v1/datasets/{left.id}", headers=auth_headers["a"])
        assert r.status_code == 204

        resp = await _rebuild(client, auth_headers["a"], new["id"])

        assert resp.status_code == 409, resp.text
        assert "no longer exists" in resp.json()["detail"]
        ds = await db_session.get(Dataset, new["id"])
        assert ds.row_count == rows_before
        assert Path(ds.filename).exists(), "the old snapshot must survive a failed rebuild"

    @pytest.mark.asyncio
    async def test_a_vanished_join_key_is_a_409_naming_the_problem(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, right, new = await _build(client, auth_headers["a"],
                                        db_session, two_orgs["a"]["org"], two_files)

        # The joined dataset is re-uploaded without its key column.
        for c in (await db_session.execute(
            __import__("sqlalchemy").select(DatasetColumn)
            .where(DatasetColumn.dataset_id == right.id))).scalars().all():
            if c.name == "id":
                await db_session.delete(c)
        await db_session.commit()

        resp = await _rebuild(client, auth_headers["a"], new["id"])

        assert resp.status_code == 409, resp.text
        assert "no longer fits" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_security_added_after_the_build_blocks_the_rebuild(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """Refusals are re-evaluated, so a rebuild cannot launder data that has
        become governed since the snapshot was taken."""
        left, _, new = await _build(client, auth_headers["a"],
                                    db_session, two_orgs["a"]["org"], two_files)
        db_session.add(RowSecurityRule(role_id=two_orgs["a"]["role"].id,
                                       dataset_id=left.id, filter_expr="`cust` == 'a'"))
        await db_session.commit()

        resp = await _rebuild(client, auth_headers["a"], new["id"])

        assert resp.status_code == 403, resp.text
        assert "security rules" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_plain_uploaded_dataset_has_nothing_to_rebuild(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, _ = await _pair(db_session, two_orgs["a"]["org"], two_files)

        resp = await _rebuild(client, auth_headers["a"], left.id)

        assert resp.status_code == 400
        assert "not built from other datasets" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_another_orgs_dataset_cannot_be_rebuilt(
            self, client, auth_headers, db_session, two_orgs, two_files):
        _, _, new = await _build(client, auth_headers["a"],
                                 db_session, two_orgs["a"]["org"], two_files)

        resp = await _rebuild(client, auth_headers["b"], new["id"])

        assert resp.status_code == 404
