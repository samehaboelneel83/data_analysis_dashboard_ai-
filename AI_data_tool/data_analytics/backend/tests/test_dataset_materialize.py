"""Saving a prep pipeline's result as a dataset of its own.

A prep `join` step is a VIEW: it re-joins on every read and lives inside one
dataset's pipeline. `POST /datasets/{id}/materialize` runs it once and persists
the result, which is what turns "several datasets joined" into one listable
dataset that reports can be built on.

Two refusals carry the weight here and each has its own test:

  * a source with row- or column-security rules cannot be snapshotted, because
    every read applies the CALLER's RLS -- the file would contain one person's
    slice while the new dataset carries no rules at all; and
  * a source whose exports are disabled cannot be snapshotted, because writing
    its rows to a policy-free copy would make that control bypassable.
"""
import pandas as pd
import pytest

from app.core.config import settings as app_settings
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn,
                               Organization, Quota, RowSecurityRule)
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


def _join(right_id, how="left"):
    return {"kind": "join", "dataset_id": right_id, "how": how,
            "left_on": "cust", "right_on": "id"}


async def _materialize(client, headers, ds_id, steps, name="Joined"):
    return await client.post(f"/api/v1/datasets/{ds_id}/materialize",
                             json={"name": name, "description": "", "steps": steps},
                             headers=headers)


class TestItCreatesADataset:
    @pytest.mark.asyncio
    async def test_the_joined_result_becomes_a_listable_dataset(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["row_count"] == 3
        # `id` survives too: a left_on/right_on merge keeps both key columns,
        # unlike a merge on a shared name.
        assert {c["name"] for c in out["columns"]} == {"cust", "amount", "id", "segment"}

        listing = (await client.get("/api/v1/datasets", headers=auth_headers["a"])).json()
        assert out["id"] in {d["id"] for d in listing}

    @pytest.mark.asyncio
    async def test_the_new_dataset_has_no_pipeline_of_its_own(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """The join was consumed into the file. If the steps came along, the
        result would try to re-join on every read and double the work."""
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        new = (await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])).json()

        steps = (await client.get(f"/api/v1/datasets/{new['id']}/prep-steps",
                                  headers=auth_headers["a"])).json()
        assert steps == []

    @pytest.mark.asyncio
    async def test_it_records_the_recipe_verbatim(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        steps = [_join(right.id, "inner")]

        new = (await _materialize(client, auth_headers["a"], left.id, steps)).json()

        ds = await db_session.get(Dataset, new["id"])
        prov = (ds.column_meta or {})[DERIVED_FROM_KEY]
        assert prov["source_dataset_id"] == left.id
        assert prov["join_dataset_ids"] == [right.id]
        assert prov["steps"] == steps, "the recipe must be the steps that actually ran"
        assert prov["built_rows"] == 3
        assert prov["built_by_user_id"] and prov["built_at"]
        assert ds.last_refreshed_at is not None

    @pytest.mark.asyncio
    async def test_the_recipe_is_not_offered_as_a_column(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """`__derived_from__` lives in column_meta beside the real per-column
        entries; it must not surface as a phantom column."""
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        new = (await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])).json()

        assert not any(c["name"].startswith("__") for c in new["columns"])

    @pytest.mark.asyncio
    async def test_an_inner_join_drops_the_unmatched_rows(
            self, client, auth_headers, db_session, two_orgs, tmp_path):
        o = tmp_path / "o.csv"
        pd.DataFrame({"cust": ["a", "b", "zz"], "amount": [1.0, 2.0, 3.0]}).to_csv(o, index=False)
        c = tmp_path / "c.csv"
        pd.DataFrame({"id": ["a", "b"], "segment": ["SMB", "ENT"]}).to_csv(c, index=False)
        left, right = await _pair(db_session, two_orgs["a"]["org"], (str(o), str(c)))

        new = (await _materialize(client, auth_headers["a"], left.id,
                                  [_join(right.id, "inner")])).json()
        assert new["row_count"] == 2

    @pytest.mark.asyncio
    async def test_a_dataset_with_no_steps_is_a_plain_copy(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, _ = await _pair(db_session, two_orgs["a"]["org"], two_files)
        new = (await _materialize(client, auth_headers["a"], left.id, [])).json()
        assert new["row_count"] == 3
        assert {c["name"] for c in new["columns"]} == {"cust", "amount"}


class TestGovernedDataIsRefused:
    """The decision this feature turns on. Reads apply the CALLER's RLS, so a
    snapshot taken by a restricted user would freeze their slice as everyone's
    data -- silently, with no error and no rules on the copy."""

    @pytest.mark.asyncio
    async def test_refused_when_the_base_dataset_has_row_security(
            self, client, auth_headers, db_session, two_orgs, two_files):
        org = two_orgs["a"]["org"]
        left, right = await _pair(db_session, org, two_files)
        db_session.add(RowSecurityRule(role_id=two_orgs["a"]["role"].id,
                                       dataset_id=left.id, filter_expr="`cust` == 'a'"))
        await db_session.commit()

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert resp.status_code == 403, resp.text
        assert "security rules" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_refused_when_a_JOINED_dataset_has_column_security(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """The check spans join targets, not just the base -- otherwise the
        governed data would simply arrive through the join instead."""
        org = two_orgs["a"]["org"]
        left, right = await _pair(db_session, org, two_files)
        db_session.add(ColumnSecurityRule(role_id=two_orgs["a"]["role"].id,
                                          dataset_id=right.id, denied_columns=["segment"]))
        await db_session.commit()

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_nothing_is_written_when_it_is_refused(
            self, client, auth_headers, db_session, two_orgs, two_files, _isolated):
        org = two_orgs["a"]["org"]
        left, right = await _pair(db_session, org, two_files)
        db_session.add(RowSecurityRule(role_id=two_orgs["a"]["role"].id,
                                       dataset_id=left.id, filter_expr="`cust` == 'a'"))
        await db_session.commit()
        before = {str(p) for p in _isolated.rglob("*.csv")}

        await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert {str(p) for p in _isolated.rglob("*.csv")} == before


class TestExportPolicyIsHonoured:
    """Materializing writes source rows to a new file, so it is an export. If it
    were not checked, disabling export and then materializing would launder the
    data into a copy that carries no policy."""

    @pytest.mark.asyncio
    async def test_refused_when_exports_are_disabled_on_a_source(
            self, client, auth_headers, db_session, two_orgs, two_files):
        from app.routers.datasets import EXPORT_DISABLED_KEY
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        right.column_meta = {EXPORT_DISABLED_KEY: True}
        await db_session.commit()

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert resp.status_code == 403, resp.text
        assert "Exports are disabled" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_refused_when_csv_is_the_blocked_format(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """A CSV is literally what gets written."""
        from app.routers.datasets import EXPORT_DISABLED_KEY
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        left.column_meta = {EXPORT_DISABLED_KEY: {"formats": ["csv"]}}
        await db_session.commit()

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])
        assert resp.status_code == 403, resp.text

    @pytest.mark.asyncio
    async def test_a_surviving_policy_is_carried_onto_the_copy(
            self, client, auth_headers, db_session, two_orgs, two_files):
        """Blocking xlsx on the source must not evaporate on the copy."""
        from app.routers.datasets import EXPORT_DISABLED_KEY
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        right.column_meta = {EXPORT_DISABLED_KEY: {"formats": ["xlsx"]}}
        await db_session.commit()

        new = (await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])).json()

        ds = await db_session.get(Dataset, new["id"])
        assert (ds.column_meta or {}).get(EXPORT_DISABLED_KEY) == {"formats": ["xlsx"]}


class TestItRefusesBadInput:
    @pytest.mark.asyncio
    async def test_a_cross_org_join_target_is_refused(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, _ = await _pair(db_session, two_orgs["a"]["org"], two_files)
        _, foreign = await _pair(db_session, two_orgs["b"]["org"], two_files)

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(foreign.id)])

        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_bad_join_key_is_refused_hard_not_silently_skipped(
            self, client, auth_headers, db_session, two_orgs, two_files, _isolated):
        """Reads degrade soft on a broken step; a write must not -- a silently
        un-joined snapshot is indistinguishable from a correct one."""
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        bad = {**_join(right.id), "right_on": "nope"}

        resp = await _materialize(client, auth_headers["a"], left.id, [bad])

        assert resp.status_code == 400, resp.text
        assert list(_isolated.rglob("*joined*")) == []

    @pytest.mark.asyncio
    async def test_an_empty_name_is_refused(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)], name="   ")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_a_directquery_dataset_cannot_be_materialized(
            self, client, auth_headers, db_session, two_orgs, two_files):
        left, _ = await _pair(db_session, two_orgs["a"]["org"], two_files)
        left.mode = "directquery"
        await db_session.commit()

        resp = await _materialize(client, auth_headers["a"], left.id, [])
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_the_row_cap_refuses_a_runaway_join(
            self, client, auth_headers, db_session, two_orgs, two_files, monkeypatch):
        """A many-to-many join multiplies rows; the cap is what stops a snapshot
        nobody asked for from filling the disk."""
        import app.services.prep as prep_mod
        monkeypatch.setattr(prep_mod, "MATERIALIZE_MAX_ROWS", 2)
        left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert resp.status_code == 400, resp.text
        assert "over the" in resp.json()["detail"]


class TestQuota:
    @pytest.mark.asyncio
    async def test_over_quota_returns_413_and_leaves_no_file(
            self, client, auth_headers, db_session, two_orgs, two_files, _isolated):
        """`QuotaExceeded` is a plain Exception, not an HTTPException -- catching
        only the latter would 500 AND strand the bytes already written."""
        org = two_orgs["a"]["org"]
        left, right = await _pair(db_session, org, two_files)
        if (await db_session.get(Organization, org.id)) is None:      # defensive
            db_session.add(Organization(id=org.id, name="o"))
        db_session.add(Quota(org_id=org.id, max_storage_mb=0))
        await db_session.commit()
        quotas.invalidate_quota_cache(org.id)
        before = {str(p) for p in _isolated.rglob("*.csv")}

        resp = await _materialize(client, auth_headers["a"], left.id, [_join(right.id)])

        assert resp.status_code == 413, resp.text
        assert {str(p) for p in _isolated.rglob("*.csv")} == before, "orphaned bytes"
