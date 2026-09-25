"""Creating an aggregate: refuse what cannot be governed, run the first
refresh, and tell the UI what the grain must contain.
"""
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, hash_password
from app.models.models import (DataSource, Dataset, DatasetColumn, DatasetShare, Materialization,
                               Quota, Report, ReportCapability, Role, RowSecurityRule,
                               ScheduleFailure, User)
from app.services import dataset_refresh, quotas, upload_store


@pytest.fixture
async def source(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="Warehouse", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d",
                                "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    # created_by is the org admin used by auth_headers["a"] -- admins bypass
    # ownership (can_read_dataset), so every existing test that authenticates
    # as auth_headers["a"] is unaffected. A SECOND, non-admin user of org A
    # (the `colleague` fixture below) is exactly what this makes unreadable.
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders",
                  data_source_id=ds_src.id, created_by=two_orgs["a"]["user"].id)
    db_session.add(src)
    await db_session.flush()
    for c, t in (("tenant", "categorical"), ("region", "categorical"),
                 ("amount", "numeric"), ("units", "numeric")):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype=t))
    role = Role(org_id=org.id, name="Tenant", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=src.id, filter_expr="tenant == 'acme'"))
    await db_session.commit()
    return src


@pytest.fixture
async def colleague(db_session, two_orgs):
    """A second, NON-ADMIN member of org A: no share on `source`, not its
    creator, and on no report that reads it -- `can_read_dataset` must
    refuse them even though `source` is a perfectly real dataset of their
    own org."""
    org = two_orgs["a"]["org"]
    role = Role(org_id=org.id, name="Member", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="colleague@example.com",
               password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest.fixture
def fake_refresh(monkeypatch):
    """The customer's database is not reachable from a unit test. The refresh
    writes what a real one would: a CSV plus its parquet sidecar."""
    calls = []

    def _rewrite(cfg, filename, source_table, source_query):
        calls.append(source_query)
        df = pd.DataFrame([{"tenant": "acme", "region": "N", "amount_sum": 10.0, "row_count": 2}])
        df.to_csv(filename, index=False)
        from app.services.frame_cache import write_parquet_sidecar
        write_parquet_sidecar(filename)
        from app.services.ingest import detect_types
        return df, detect_types(df)

    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _rewrite)
    return calls


BODY = {"name": "orders by tenant/region", "grain": ["tenant", "region"],
        "measures": [{"column": "amount", "agg": "sum"}], "refresh_interval_minutes": 60}


@pytest.mark.asyncio
async def test_creates_runs_the_first_refresh_and_returns_the_dataset(
        client, auth_headers, source, fake_refresh, db_session, two_orgs):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["aggregate_of_dataset_id"] == source.id
    assert body["mode"] == "import"
    assert body["refresh_interval_minutes"] == 60
    assert body["row_count"] == 1
    assert fake_refresh and 'GROUP BY "tenant", "region"' in fake_refresh[0]
    assert {c["name"] for c in body["columns"]} == {"tenant", "region", "amount_sum", "row_count"}

    # The persistence contract, not just the response: what actually landed
    # in the row is what a refresh (and a widget reading it) will use.
    assert body["source_query"] is not None
    assert 'GROUP BY "tenant", "region"' in body["source_query"]
    assert 'COUNT(*) AS "row_count"' in body["source_query"]
    assert body["data_source_id"] == source.data_source_id
    assert body["aggregate_spec"]["measures"][0]["name"] == "amount_sum"

    row = await db_session.get(Dataset, body["id"])
    assert row.created_by == two_orgs["a"]["user"].id
    mat = (await db_session.execute(
        select(Materialization).where(Materialization.dataset_id == body["id"])
    )).scalar_one_or_none()
    assert mat is not None


@pytest.mark.asyncio
async def test_refuses_a_grain_that_does_not_cover_an_rls_column(client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                          json=dict(BODY, grain=["region"]), headers=auth_headers["a"])
    assert r.status_code == 400, r.text
    assert "tenant" in r.json()["detail"] and "Tenant" in r.json()["detail"]
    assert fake_refresh == []                      # nothing ran


@pytest.mark.asyncio
async def test_refuses_a_bad_spec_with_its_reason(client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                          json=dict(BODY, measures=[{"column": "amount", "agg": "avg"}]),
                          headers=auth_headers["a"])
    assert r.status_code == 400
    assert "avg" in r.json()["detail"]


@pytest.mark.asyncio
async def test_only_a_directquery_dataset_can_be_aggregated(client, auth_headers, db_session, two_orgs, tmp_path):
    p = tmp_path / "i.csv"
    pd.DataFrame({"a": [1]}).to_csv(p, index=False)
    imp = Dataset(name="imported", org_id=two_orgs["a"]["org"].id, mode="import", filename=str(p))
    db_session.add(imp)
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{imp.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "DirectQuery" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_colleague_who_cannot_read_the_source_is_refused_by_both_routes(
        client, source, colleague):
    """`source` has an owner (see the fixture) and no report reads it, so a
    second, non-admin member of the SAME org gets 404 -- read, not just the
    data-model capability, gates both routes now."""
    pre = await client.get(f"/api/v1/datasets/{source.id}/aggregate-preflight", headers=colleague)
    assert pre.status_code == 404
    create = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=colleague)
    assert create.status_code == 404


@pytest.mark.asyncio
async def test_refuses_a_grain_that_produces_too_many_rows(
        client, auth_headers, source, fake_refresh, monkeypatch):
    import app.services.prep as prep
    monkeypatch.setattr(prep, "MATERIALIZE_MAX_ROWS", 0)
    before = set(upload_store.storage_root(source.org_id).glob("*"))

    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])

    assert r.status_code == 400, r.text
    assert "too fine" in r.json()["detail"] and "0" in r.json()["detail"]
    after = set(upload_store.storage_root(source.org_id).glob("*"))
    assert before == after                      # the CSV and its sidecar were unlinked


@pytest.mark.asyncio
async def test_refuses_when_storage_quota_is_exceeded(
        client, auth_headers, source, fake_refresh, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    quotas.invalidate_quota_cache()
    db_session.add(Quota(org_id=org.id, max_storage_mb=0))
    await db_session.commit()
    quotas.invalidate_quota_cache(org.id)
    before = set(upload_store.storage_root(org.id).glob("*"))
    try:
        r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
        # Same status code the QuotaExceeded handler in main.py would produce
        # for this limit (enforce_storage_quota raises it with status_code=413).
        assert r.status_code == 413, r.text
        after = set(upload_store.storage_root(org.id).glob("*"))
        assert before == after                  # nothing left on disk
    finally:
        quotas.invalidate_quota_cache()


@pytest.mark.asyncio
async def test_refuses_an_interval_below_the_minimum(client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                          json=dict(BODY, refresh_interval_minutes=1), headers=auth_headers["a"])
    assert r.status_code == 400, r.text
    assert "minimum" in r.json()["detail"].lower()
    assert fake_refresh == []                   # refused before the source was ever touched


@pytest.mark.asyncio
async def test_a_null_interval_means_unscheduled(client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                          json=dict(BODY, refresh_interval_minutes=None), headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    assert r.json()["refresh_interval_minutes"] is None


@pytest.mark.asyncio
async def test_the_export_policy_is_not_copied_onto_the_aggregate(
        client, auth_headers, db_session, source, fake_refresh):
    """The source already carries the policy when the aggregate is created --
    the only case in which the old code copied it -- and the aggregate row
    must still carry nothing: the policy is resolved, never copied."""
    src = await db_session.get(Dataset, source.id)
    src.column_meta = {**(src.column_meta or {}), "__exports_disabled__": True}
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    agg = await db_session.get(Dataset, r.json()["id"])
    assert "__exports_disabled__" not in (agg.column_meta or {})


@pytest.mark.asyncio
async def test_disabling_exports_on_the_source_later_bites_on_the_aggregate(
        client, auth_headers, db_session, source, fake_refresh):
    """A copy taken at creation would not notice this; a resolved policy does."""
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    src = await db_session.get(Dataset, source.id)
    src.column_meta = {**(src.column_meta or {}), "__exports_disabled__": True}
    await db_session.commit()
    r = await client.get(f"/api/v1/datasets/{agg_id}/export", headers=auth_headers["a"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_source_with_a_default_filter_cannot_be_aggregated(
        client, auth_headers, db_session, source, fake_refresh):
    src = await db_session.get(Dataset, source.id)
    src.default_filter_expr = "region == 'N'"
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "filter expression" in r.json()["detail"]
    assert fake_refresh == []


@pytest.mark.asyncio
async def test_materializing_an_aggregate_carries_the_sources_export_policy(
        client, auth_headers, db_session, two_orgs, fake_refresh):
    """The materialize guard's policy merge must resolve through the source too --
    an aggregate's own column_meta is always {}, so reading the merge policy off
    the aggregate itself would silently drop the source's real restriction."""
    from app.routers.datasets import EXPORT_DISABLED_KEY
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="Warehouse3", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d",
                                "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    src = Dataset(name="orders3", org_id=org.id, mode="directquery", source_table="orders",
                  data_source_id=ds_src.id, created_by=two_orgs["a"]["user"].id,
                  column_meta={EXPORT_DISABLED_KEY: {"formats": ["xlsx"]}})
    db_session.add(src)
    await db_session.flush()
    for c, t in (("tenant", "categorical"), ("region", "categorical"), ("amount", "numeric")):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype=t))
    await db_session.commit()

    r = await client.post(f"/api/v1/datasets/{src.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    agg_id = r.json()["id"]

    r = await client.post(f"/api/v1/datasets/{agg_id}/materialize",
                          json={"name": "copy", "description": "", "steps": []},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    new = await db_session.get(Dataset, r.json()["id"])
    assert (new.column_meta or {}).get(EXPORT_DISABLED_KEY) == {"formats": ["xlsx"]}


@pytest.mark.asyncio
async def test_materializing_an_aggregate_is_refused_when_the_source_blocks_csv(
        client, auth_headers, db_session, two_orgs, fake_refresh):
    """Direct coverage of the Task-3 guard change through the MATERIALIZE path:
    _refuse_if_ungovernable's csv check must resolve through the source too, or
    an aggregate whose source disables csv exports would launder its rows into
    a policy-free copy (a CSV is literally what materialize writes)."""
    from app.routers.datasets import EXPORT_DISABLED_KEY
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="Warehouse4", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d",
                                "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    src = Dataset(name="orders4", org_id=org.id, mode="directquery", source_table="orders",
                  data_source_id=ds_src.id, created_by=two_orgs["a"]["user"].id,
                  column_meta={EXPORT_DISABLED_KEY: {"formats": ["csv"]}})
    db_session.add(src)
    await db_session.flush()
    for c, t in (("tenant", "categorical"), ("region", "categorical"), ("amount", "numeric")):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype=t))
    await db_session.commit()

    r = await client.post(f"/api/v1/datasets/{src.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    agg_id = r.json()["id"]

    r = await client.post(f"/api/v1/datasets/{agg_id}/materialize",
                          json={"name": "copy", "description": "", "steps": []},
                          headers=auth_headers["a"])
    assert r.status_code == 403, r.text
    assert "Exports are disabled" in r.json()["detail"]


@pytest.mark.asyncio
async def test_widget_export_from_an_aggregate_is_refused_when_the_source_blocks_csv(
        client, auth_headers, db_session, two_orgs, fake_refresh):
    """The regression a reviewer caught: widget_data.py's own `_exports_disabled`
    call site read the aggregate's own (always-empty) column_meta directly, instead
    of resolving through the source -- a per-widget download bypassed the source's
    export policy entirely, both for the format list and for auto_private."""
    from app.routers.datasets import EXPORT_DISABLED_KEY
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="Warehouse5", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d",
                                "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    src = Dataset(name="orders5", org_id=org.id, mode="directquery", source_table="orders",
                  data_source_id=ds_src.id, created_by=two_orgs["a"]["user"].id,
                  column_meta={EXPORT_DISABLED_KEY: {"formats": ["csv"]}})
    db_session.add(src)
    await db_session.flush()
    for c, t in (("tenant", "categorical"), ("region", "categorical"), ("amount", "numeric")):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype=t))
    await db_session.commit()

    r = await client.post(f"/api/v1/datasets/{src.id}/aggregates", json=BODY, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    agg_id = r.json()["id"]

    body = {"widget_type": "bar",
           "config": {"dimension": "region", "measure": "amount_sum", "aggregation": "sum"}}
    r = await client.post(f"/api/v1/datasets/{agg_id}/widget-data/export?format=csv",
                          json=body, headers=auth_headers["a"])
    assert r.status_code == 403, r.text
    if "code" in r.json():
        assert r.json()["code"] == "export_disabled"


@pytest.mark.asyncio
async def test_set_export_policy_on_an_aggregate_is_refused(
        client, auth_headers, source, fake_refresh):
    """Export policy is inherited from the source, never a property of its own
    -- writing to the aggregate's own copy would be silently ignored."""
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.post(f"/api/v1/datasets/{agg_id}/export-policy",
                          json={"formats": ["csv"]}, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "inherited from the source" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_export_policy_on_an_aggregate_reports_the_sources_policy(
        client, auth_headers, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.post(f"/api/v1/datasets/{source.id}/export-policy",
                          json={"formats": ["xlsx"]}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/datasets/{agg_id}/export-policy", headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["export_policy"] == {"formats": ["xlsx"]}
    assert r.json()["inherited_from"] == source.id

    r = await client.get(f"/api/v1/datasets/{source.id}/export-policy", headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["inherited_from"] is None


@pytest.mark.asyncio
async def test_lists_the_aggregates_of_a_source(client, auth_headers, source, fake_refresh, db_session):
    created = (await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                                 json=BODY, headers=auth_headers["a"])).json()
    db_session.add(ScheduleFailure(kind="dataset", item_id=created["id"], attempts=2, last_error="boom"))
    await db_session.commit()

    r = await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["a"])

    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["dataset"]["name"] == BODY["name"]
    assert r.json()[0]["last_error"] == "boom"
    assert r.json()[0]["attempts"] == 2


@pytest.mark.asyncio
async def test_an_unscheduled_aggregate_reports_a_default_filter_gained_since_creation(
        client, auth_headers, db_session, source, fake_refresh):
    """The scheduler's tick only ever selects `refresh_interval_minutes IS NOT
    NULL`, so an unscheduled aggregate's guards never fire on their own -- the
    only way its Aggregates row would ever show this is if `list_aggregates`
    computes it itself, from the source as it is NOW."""
    from app.services.aggregates import DEFAULT_FILTER_STALENESS_MESSAGE
    created = (await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                                 json=dict(BODY, refresh_interval_minutes=None),
                                 headers=auth_headers["a"])).json()
    src = await db_session.get(Dataset, source.id)
    src.default_filter_expr = "region == 'N'"
    await db_session.commit()

    r = await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["a"])

    assert r.status_code == 200
    row = next(x for x in r.json() if x["dataset"]["id"] == created["id"])
    assert row["last_error"] == DEFAULT_FILTER_STALENESS_MESSAGE
    assert row["attempts"] == 0


@pytest.mark.asyncio
async def test_an_unscheduled_aggregate_reports_a_repointed_source_query(
        client, auth_headers, db_session, source, fake_refresh):
    from app.services.aggregates import QUERY_CHANGED_STALENESS_MESSAGE
    created = (await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                                 json=dict(BODY, refresh_interval_minutes=None),
                                 headers=auth_headers["a"])).json()
    src = await db_session.get(Dataset, source.id)
    src.source_table = "orders_v2"
    await db_session.commit()

    r = await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["a"])

    assert r.status_code == 200
    row = next(x for x in r.json() if x["dataset"]["id"] == created["id"])
    assert row["last_error"] == QUERY_CHANGED_STALENESS_MESSAGE


@pytest.mark.asyncio
async def test_an_unscheduled_up_to_date_aggregate_reports_no_error(
        client, auth_headers, source, fake_refresh):
    created = (await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                                 json=dict(BODY, refresh_interval_minutes=None),
                                 headers=auth_headers["a"])).json()

    r = await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["a"])

    assert r.status_code == 200
    row = next(x for x in r.json() if x["dataset"]["id"] == created["id"])
    assert row["last_error"] is None


@pytest.mark.asyncio
async def test_a_real_schedule_failure_still_wins_over_the_computed_staleness(
        client, auth_headers, db_session, source, fake_refresh):
    """A real ScheduleFailure row (the scheduler actually tried and recorded
    something) must not be masked by the cheaper, freshly-computed check --
    it is checked first and, when present, decides `last_error` outright."""
    created = (await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                                 json=dict(BODY, refresh_interval_minutes=None),
                                 headers=auth_headers["a"])).json()
    src = await db_session.get(Dataset, source.id)
    src.default_filter_expr = "region == 'N'"          # would ALSO compute stale
    await db_session.commit()
    db_session.add(ScheduleFailure(kind="dataset", item_id=created["id"], attempts=3,
                                   last_error="a real recorded failure"))
    await db_session.commit()

    r = await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["a"])

    assert r.status_code == 200
    row = next(x for x in r.json() if x["dataset"]["id"] == created["id"])
    assert row["last_error"] == "a real recorded failure"
    assert row["attempts"] == 3


@pytest.mark.asyncio
async def test_preflight_names_the_columns_the_grain_must_contain(client, auth_headers, source):
    r = await client.get(f"/api/v1/datasets/{source.id}/aggregate-preflight", headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["rls_columns"] == ["tenant"]
    assert set(r.json()["measure_candidates"]) == {"amount", "units"}
    assert "tenant" in r.json()["grain_candidates"]


@pytest.mark.asyncio
async def test_another_org_cannot_see_or_create(client, auth_headers, source):
    assert (await client.get(f"/api/v1/datasets/{source.id}/aggregates", headers=auth_headers["b"])).status_code == 404
    assert (await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["b"])).status_code == 404
    assert (await client.get(f"/api/v1/datasets/{source.id}/aggregate-preflight", headers=auth_headers["b"])).status_code == 404


@pytest.mark.asyncio
async def test_deleting_the_source_deletes_its_aggregates_files_too(
        client, auth_headers, source, fake_refresh, db_session):
    """The DB's ON DELETE CASCADE on aggregate_of_dataset_id removes the
    aggregate ROW with no application code running -- its CSV and parquet
    sidecar would otherwise be orphaned on disk forever."""
    created = (await client.post(f"/api/v1/datasets/{source.id}/aggregates",
                                 json=BODY, headers=auth_headers["a"])).json()
    row = await db_session.get(Dataset, created["id"])
    filename = row.filename
    assert Path(filename).exists()
    assert Path(filename + ".parquet").exists()

    r = await client.delete(f"/api/v1/datasets/{source.id}", headers=auth_headers["a"])
    assert r.status_code == 204, r.text

    db_session.expire_all()
    assert (await db_session.get(Dataset, created["id"])) is None
    assert not Path(filename).exists()
    assert not Path(filename + ".parquet").exists()


@pytest.mark.asyncio
async def test_deleting_the_source_removes_its_and_its_aggregates_failure_rows(
        client, auth_headers, db_session, source, fake_refresh):
    from app.services.refresh_scheduler import record_failure
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    await record_failure(db_session, "dataset", agg_id, "grain no longer covers tenant")
    await record_failure(db_session, "dataset", source.id, "source unreachable")

    r = await client.delete(f"/api/v1/datasets/{source.id}", headers=auth_headers["a"])
    assert r.status_code == 204
    left = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id.in_([source.id, agg_id])))).scalars().all()
    assert left == []


@pytest.mark.asyncio
async def test_deleting_the_data_source_leaves_its_datasets_in_place(
        client, auth_headers, db_session, source, fake_refresh):
    """Dataset.data_source_id is ON DELETE SET NULL by design: an imported
    dataset is a standalone file a user built reports on, and a DirectQuery
    dataset (or its aggregate) may still be read by dashboards. Deleting the
    connection must not silently remove what was built on it -- only
    deleting the DATASET itself (test_deleting_the_source_... above) sweeps
    its files and failure rows."""
    from app.services.frame_cache import sidecar_path
    source_id, data_source_id = source.id, source.data_source_id
    r = await client.post(f"/api/v1/datasets/{source_id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    filename = r.json()["filename"]
    assert Path(filename).exists()
    assert Path(sidecar_path(filename)).exists()

    r = await client.delete(f"/api/v1/data-sources/{data_source_id}", headers=auth_headers["a"])
    assert r.status_code == 204

    db_session.expire_all()
    src_row = await db_session.get(Dataset, source_id)
    agg_row = await db_session.get(Dataset, agg_id)
    assert src_row is not None
    assert src_row.data_source_id is None
    assert agg_row is not None
    assert Path(filename).exists()
    assert Path(sidecar_path(filename)).exists()


@pytest.mark.asyncio
async def test_editing_an_aggregate_recompiles_rewrites_and_clears_the_failure(
        client, auth_headers, db_session, source, fake_refresh, two_orgs):
    from app.services.refresh_scheduler import record_failure
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    old_file = r.json()["filename"]
    await record_failure(db_session, "dataset", agg_id, "the source's query changed")

    # The source can be re-pointed at a different connection between the
    # first build and this edit; the aggregate's OWN data_source_id -- what
    # the scheduler refreshes through -- must be resynced to match, or a
    # later scheduled refresh reads the OLD connection with SQL compiled
    # against the NEW one.
    other = DataSource(name="Warehouse2", type="postgresql", org_id=two_orgs["a"]["org"].id,
                       config={"host": "h2", "port": 5432, "database": "d2",
                               "username": "u", "password": "p"})
    db_session.add(other)
    await db_session.flush()
    src = await db_session.get(Dataset, source.id)
    src.data_source_id = other.id
    await db_session.commit()

    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}",
                         json={"measures": [{"column": "amount", "agg": "sum"}, {"column": "units", "agg": "max"}]},
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data_source_id"] == other.id                                # resynced to the CURRENT connection
    assert body["aggregate_spec"]["grain"] == ["tenant", "region"]          # kept
    assert [m["name"] for m in body["aggregate_spec"]["measures"]] == ["amount_sum", "units_max"]
    assert body["refresh_interval_minutes"] == 60                             # kept
    assert len(fake_refresh) == 2 and '"units"' in fake_refresh[-1]           # recompiled and rewritten
    assert body["filename"] != old_file                                       # a new file was allocated
    assert not Path(old_file).exists()                                        # and the old one is gone
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg_id))).scalar_one_or_none()
    assert failure is None
    agg = (await db_session.execute(select(Dataset).options(selectinload(Dataset.columns))
                                    .where(Dataset.id == agg_id))).scalar_one()
    # fake_refresh writes a fixed frame whatever the SQL asked for; the columns
    # are replaced from THAT frame, so this is what the row must now carry.
    assert {c.name for c in agg.columns} == {"tenant", "region", "amount_sum", "row_count"}


@pytest.mark.asyncio
async def test_an_empty_edit_is_a_rebuild(client, auth_headers, db_session, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=auth_headers["a"])
    assert r.status_code == 200
    assert len(fake_refresh) == 2 and fake_refresh[0] == fake_refresh[1]


@pytest.mark.asyncio
async def test_an_edit_re_runs_the_grain_check(client, auth_headers, db_session, source, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}",
                         json={"grain": ["region"]}, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "tenant" in r.json()["detail"] and "Tenant" in r.json()["detail"]
    assert len(fake_refresh) == 1


@pytest.mark.asyncio
async def test_editing_an_aggregate_serves_the_new_frame_with_no_cache_clear(
        client, auth_headers, db_session, source, monkeypatch):
    """update_aggregate used to flush the whole shared cache
    (`clear_widget_data_cache` empties the Valkey `wdc:` namespace for every
    org) on every edit. Both caches key on path + mtime + size and a rebuild
    always allocates a NEW file path, so a stale hit is impossible -- nothing
    ever needs clearing, and clearing costs every OTHER org's warm cache.
    Pin the guarantee directly: no clear function runs, and a query issued
    after the edit reads the NEW frame's values, not the first refresh's."""
    calls = []

    def _rewrite(cfg, filename, source_table, source_query):
        df = pd.DataFrame([{"tenant": "acme", "region": "N",
                            "amount_sum": 10.0 if not calls else 99.0, "row_count": 2}])
        calls.append(df)
        df.to_csv(filename, index=False)
        from app.services.frame_cache import write_parquet_sidecar
        write_parquet_sidecar(filename)
        from app.services.ingest import detect_types
        return df, detect_types(df)
    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _rewrite)

    from app.services import frame_cache as frame_cache_module
    from app.services import widget_data as widget_data_module
    cache_clears = []
    monkeypatch.setattr(frame_cache_module, "clear_frame_cache",
                        lambda: cache_clears.append("frame"))
    monkeypatch.setattr(widget_data_module, "clear_widget_data_cache",
                        lambda: cache_clears.append("widget"))

    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]

    bar = {"widget_type": "bar",
          "config": {"dimension": "region", "measure": "amount_sum", "aggregation": "sum"},
          "calculated_columns": [], "parameters": {}}
    # Read BEFORE the edit, to WARM both the widget-data memo and the frame
    # cache with the OLD file's value -- proving "no clear needed" requires a
    # populated cache to not-clear. A cold read after the PUT would return the
    # new frame trivially, whether or not a stale, warm entry could ever have
    # been served.
    r = await client.post(f"/api/v1/datasets/{agg_id}/widget-data", json=bar, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    rows = {x["name"]: x["value"] for x in r.json()["rows"]}
    assert rows == {"N": 10.0}, rows        # warm with the OLD frame's value

    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/datasets/{agg_id}/widget-data", json=bar, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    rows = {x["name"]: x["value"] for x in r.json()["rows"]}
    assert rows == {"N": 99.0}, rows        # the NEW frame from the second refresh call, not the warm entry

    assert cache_clears == []


@pytest.mark.asyncio
async def test_an_edit_needs_the_data_capability_and_the_right_source(
        client, auth_headers, db_session, source, colleague, fake_refresh):
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=colleague)
    assert r.status_code == 404          # require_dataset_read refuses deterministically -- not 403
    r = await client.put(f"/api/v1/datasets/{source.id + 1000}/aggregates/{agg_id}", json={}, headers=auth_headers["a"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_an_edit_needs_write_on_the_aggregate_itself_not_only_data_on_the_source(
        client, auth_headers, db_session, source, fake_refresh, two_orgs):
    """Editing an aggregate used to gate on the SOURCE's data capability only
    -- a role restricted below `data` on a report built over the AGGREGATE
    could still rewrite the aggregate's grain and measures out from under
    that report, because nothing ever asked about the aggregate itself.

    Grants the member DatasetShare-read on the source (so `require_dataset_read`
    passes) and leaves the source's own data capability unrestricted (no report
    uses it, so `max_dataset_capability` defaults open) -- isolating the new
    check to the one thing it is meant to gate: write access to the AGGREGATE,
    via a report built on it that holds this role below `data`."""
    org = two_orgs["a"]["org"]
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]

    role = Role(org_id=org.id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    member = User(org_id=org.id, role_id=role.id, email="restricted@example.com",
                 password_hash=hash_password("pw"))
    db_session.add(member)
    await db_session.flush()
    db_session.add(DatasetShare(dataset_id=source.id, user_id=member.id))
    report = Report(name="R", org_id=org.id, dataset_id=agg_id)
    db_session.add(report)
    await db_session.flush()
    db_session.add(ReportCapability(report_id=report.id, role_id=role.id, level="view"))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(member.id, member.org_id)}"}

    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=headers)

    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_editing_an_aggregate_drops_a_stale_export_disabled_key(
        client, auth_headers, db_session, source, fake_refresh):
    """The aggregate's own column_meta is meant to always be {} -- export
    policy is resolved through the SOURCE, never stored here (see
    test_the_export_policy_is_not_copied_onto_the_aggregate above) -- but an
    older build, or a direct row edit, could still leave the key behind. An
    edit must not perpetuate a stale copy of a key that is never meant to be
    read off the aggregate."""
    from app.routers.datasets import EXPORT_DISABLED_KEY
    r = await client.post(f"/api/v1/datasets/{source.id}/aggregates", json=BODY, headers=auth_headers["a"])
    agg_id = r.json()["id"]
    agg = await db_session.get(Dataset, agg_id)
    agg.column_meta = {EXPORT_DISABLED_KEY: True}
    await db_session.commit()

    r = await client.put(f"/api/v1/datasets/{source.id}/aggregates/{agg_id}", json={}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    db_session.expire_all()
    agg = await db_session.get(Dataset, agg_id)
    assert EXPORT_DISABLED_KEY not in (agg.column_meta or {})


@pytest.mark.asyncio
async def test_policy_dataset_fails_closed_when_the_source_row_is_gone(db_session, source, monkeypatch):
    """The FK cascade (`aggregate_of_dataset_id`, ondelete=CASCADE) makes an
    aggregate outliving its source unreachable through the app today -- but
    `_policy_dataset` must still fail CLOSED if it ever happens, not silently
    fall back to resolving the policy from `ds` itself (an aggregate's own
    column_meta is always {}, i.e. unrestricted) as though nothing were wrong.
    A security resolver defaults closed, not open."""
    from app.core import rls as rls_module
    from app.routers.datasets import _policy_dataset

    async def _fake_source(db, dataset_id):
        return 999999, None          # a source id that does not exist
    monkeypatch.setattr(rls_module, "_aggregate_source", _fake_source)

    with pytest.raises(HTTPException) as exc:
        await _policy_dataset(db_session, source)
    assert exc.value.status_code == 404
