"""Prep pipeline end to end: the API contract, the load-order guarantees, and the
reserved-key survival that keeps governance settings alive through bulk edits."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn
from app.services.prep import PREP_STEPS_KEY
from app.services.widget_data import get_widget_data


@pytest.fixture
def messy_ds(tmp_path):
    p = tmp_path / "messy.csv"
    pd.DataFrame({
        "region": ["  US ", "US", "ca", "MX"],
        "amount": [10.0, 10.0, 5.0, 50.0],
    }).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path):
    ds = Dataset(name="Messy", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("amount", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


@pytest.mark.asyncio
async def test_put_validates_and_get_round_trips(client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    steps = [{"kind": "trim"}, {"kind": "case", "column": "region", "to": "upper"}]
    r = await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=steps, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/datasets/{ds.id}/prep-steps", headers=auth_headers["a"])
    assert r.json() == steps


@pytest.mark.asyncio
async def test_put_refuses_a_malformed_step(client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    r = await client.put(f"/api/v1/datasets/{ds.id}/prep-steps",
                         json=[{"kind": "case", "column": "region", "to": "shouting"}],
                         headers=auth_headers["a"])
    assert r.status_code == 400
    assert "to must be one of" in r.json()["detail"]


@pytest.mark.asyncio
async def test_widget_data_sees_the_cleansed_frame(client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    steps = [{"kind": "trim"}, {"kind": "case", "column": "region", "to": "upper"},
             {"kind": "filter_rows", "expression": "`amount` > 7"}]
    await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=steps, headers=auth_headers["a"])
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "region", "measure": "amount", "aggregation": "sum"}},
                          headers=auth_headers["a"])
    # "  US " and "US" merge into one 20.0 bar; ca (5.0) is filtered away.
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"US": 20.0, "MX": 50.0}


@pytest.mark.asyncio
async def test_prep_preview_shows_before_and_after(client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    r = await client.post(f"/api/v1/datasets/{ds.id}/prep-preview",
                          json=[{"kind": "drop_duplicates"}, {"kind": "trim"},
                                {"kind": "drop_duplicates", "subset": ["region"]}],
                          headers=auth_headers["a"])
    body = r.json()
    assert body["before"]["rows"] == 4
    assert body["after"]["rows"] == 3          # "  US " == "US" only after trim
    assert body["sample"]["columns"] == ["region", "amount"]


@pytest.mark.asyncio
async def test_prep_runs_after_rls_so_aggregates_only_see_visible_rows(db_session, messy_ds):
    # Pure load-path check: an aggregate over an RLS-filtered frame must not
    # include hidden rows in its sums.
    steps = [{"kind": "aggregate", "group_by": ["region"],
              "aggregations": [{"column": "amount", "agg": "sum", "as": "amount"}]}]
    result = get_widget_data(messy_ds, {"dimension": "region", "measure": "amount", "aggregation": "sum"},
                             "bar", rls_filter_expr="`region` != 'MX'",
                             prep_steps=steps, use_cache=False)
    names = {x["name"] for x in result["rows"]}
    assert "MX" not in names


@pytest.mark.asyncio
async def test_prep_preview_endpoint_applies_rls_to_the_base_frame(
    client, db_session, two_orgs, messy_ds):
    """S1: /prep-preview must feed the restricted user's RLS-filtered frame into
    the candidate steps, not preview over the full table. Value-pin: 'before.rows'
    (computed pre-aggregation, straight off the base frame) must already exclude
    the hidden MX row."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import Dataset, DatasetColumn, Role, RowSecurityRule, User

    org = two_orgs["a"]["org"]
    ds = Dataset(name="Messy2", filename=messy_ds, org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("region", "categorical"), ("amount", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))

    role = Role(org_id=org.id, name="No MX", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region != 'MX'"))
    user = User(org_id=org.id, role_id=role.id, email="prep-rls@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    r = await client.post(f"/api/v1/datasets/{ds.id}/prep-preview",
                          json=[{"kind": "trim"}], headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before"]["rows"] == 3, "the RLS-hidden MX row leaked into the base frame the preview computed on"
    sample_regions = {row[0].strip() for row in body["sample"]["rows"]}
    assert "MX" not in sample_regions


@pytest.mark.asyncio
async def test_prep_preview_returns_per_step_counts(client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    r = await client.post(f"/api/v1/datasets/{ds.id}/prep-preview",
                          json=[{"kind": "trim"}, {"kind": "dedupe", "subset": ["region"]}],
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    steps = body["steps"]
    assert len(steps) == 2
    assert steps[0]["rows_in"] == 4 and steps[0]["rows_out"] == 4       # trim: no row change
    assert steps[1]["rows_in"] == 4 and steps[1]["rows_out"] == 3       # dedupe drops "  US "/"US"
    assert body["after"]["rows"] == 3


@pytest.mark.asyncio
async def test_prep_preview_per_step_counts_are_rls_filtered(client, db_session, two_orgs, messy_ds):
    """Per-step breakdown must be computed on the RLS-filtered base frame, not
    the full table -- value-pinned with a restricted user like the whole-pipeline
    RLS test above."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import Dataset, DatasetColumn, Role, RowSecurityRule, User

    org = two_orgs["a"]["org"]
    ds = Dataset(name="Messy3", filename=messy_ds, org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("region", "categorical"), ("amount", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))

    role = Role(org_id=org.id, name="No MX2", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region != 'MX'"))
    user = User(org_id=org.id, role_id=role.id, email="prep-rls-steps@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    r = await client.post(f"/api/v1/datasets/{ds.id}/prep-preview",
                          json=[{"kind": "trim"}], headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # messy_ds has 4 rows including one MX row; RLS hides it, so the first
    # step's rows_in must reflect 3, not 4.
    assert body["steps"][0]["rows_in"] == 3
    assert body["steps"][0]["rows_out"] == 3


@pytest.mark.asyncio
async def test_disabled_step_round_trips_and_is_skipped_in_apply_and_preview(
    client, auth_headers, db_session, two_orgs, messy_ds):
    """A disabled step is a persisted pause, not a delete: it must survive
    save -> GET, be skipped when the pipeline actually runs, and the preview's
    per-step entry must mark it 'skipped' with rows_in == rows_out."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    steps = [{"kind": "trim", "disabled": True},
             {"kind": "case", "column": "region", "to": "upper"}]
    r = await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=steps, headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/datasets/{ds.id}/prep-steps", headers=auth_headers["a"])
    assert r.json() == steps  # round-trips with the disabled flag intact

    r = await client.post(f"/api/v1/datasets/{ds.id}/prep-preview", json=steps, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    trim_entry = body["steps"][0]
    assert trim_entry["skipped"] is True
    assert trim_entry["rows_in"] == trim_entry["rows_out"]
    # "  US " never got trimmed (case is a no-op on already-upper text with
    # spaces) -- proving the disabled trim step genuinely did not run.
    sample_regions = [row[0] for row in body["sample"]["rows"]]
    assert "  US " in sample_regions


@pytest.mark.asyncio
async def test_old_saved_pipelines_still_apply_after_new_kinds_added(client, auth_headers, db_session, two_orgs, messy_ds):
    """Backward compatibility: step JSON saved before sort/dedupe existed has no
    knowledge of them and must still validate and apply unchanged."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    old_steps = [{"kind": "trim"}, {"kind": "case", "column": "region", "to": "upper"},
                {"kind": "drop_duplicates", "subset": ["region"]}]
    r = await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=old_steps, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/datasets/{ds.id}/prep-steps", headers=auth_headers["a"])
    assert r.json() == old_steps
    r = await client.post(f"/api/v1/datasets/{ds.id}/prep-preview", json=old_steps, headers=auth_headers["a"])
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_cache_distinguishes_different_pipelines(messy_ds):
    base = {"dimension": "region", "measure": "amount", "aggregation": "sum"}
    with_prep = get_widget_data(messy_ds, base, "bar",
                                prep_steps=[{"kind": "filter_rows", "expression": "`amount` > 7"}])
    without = get_widget_data(messy_ds, base, "bar")
    # If the pipeline were missing from the cache key these would be identical.
    assert len(without["rows"]) > len(with_prep["rows"]) or \
        {x["name"] for x in without["rows"]} != {x["name"] for x in with_prep["rows"]}


@pytest.mark.asyncio
async def test_directquery_datasets_refuse_prep_steps(client, auth_headers, db_session, two_orgs):
    ds = Dataset(name="DQ", org_id=two_orgs["a"]["org"].id, mode="directquery")
    db_session.add(ds)
    await db_session.commit()
    r = await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=[{"kind": "trim"}],
                         headers=auth_headers["a"])
    assert r.status_code == 400
    assert "DirectQuery" in r.json()["detail"]


@pytest.mark.asyncio
async def test_column_meta_bulk_edit_preserves_reserved_keys(client, auth_headers, db_session, two_orgs, messy_ds):
    """The latent wipe this feature would have made live: PUT /column-meta
    replaces the map wholesale, and the prep pipeline + export policy live in
    that map under reserved keys. A bulk column edit must not destroy them."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=[{"kind": "trim"}], headers=auth_headers["a"])
    await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true", headers=auth_headers["a"])

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"region": {"role": "category"}}}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    await db_session.refresh(ds)
    assert ds.column_meta.get(PREP_STEPS_KEY) == [{"kind": "trim"}]
    assert ds.column_meta.get("__exports_disabled__") is True
    # and the route refuses to write reserved keys directly
    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"__prep_steps__": {"role": "category"}}}, headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_export_carries_the_cleansed_frame(client, auth_headers, db_session, two_orgs, messy_ds):
    import io
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    await client.put(f"/api/v1/datasets/{ds.id}/prep-steps",
                     json=[{"kind": "trim"}, {"kind": "drop_duplicates", "subset": ["region", "amount"]}],
                     headers=auth_headers["a"])
    r = await client.get(f"/api/v1/datasets/{ds.id}/export", headers=auth_headers["a"])
    exported = pd.read_csv(io.BytesIO(r.content))
    assert len(exported) == 3  # the trimmed duplicate is gone from the file too


# ── In-place cell editing over the wire ──────────────────────────────────────
#
# The grid saves a correction as an `edit_cells` step. Every part of that is
# tested somewhere -- the merge rules in the frontend, validation and apply in
# test_prep_steps.py -- and none of those touch the ROUTE in between, which is
# exactly where a feature dies with a green suite.

@pytest.mark.asyncio
async def test_a_cell_correction_round_trips_through_the_api(
        client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    steps = [{"kind": "edit_cells", "key_column": "region", "column": "amount",
              "edits": [{"key": "ca", "value": 99}]}]
    r = await client.put(f"/api/v1/datasets/{ds.id}/prep-steps", json=steps,
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/datasets/{ds.id}/prep-steps", headers=auth_headers["a"])
    assert r.json() == steps


@pytest.mark.asyncio
async def test_the_data_grid_shows_the_corrected_value(
        client, auth_headers, db_session, two_orgs, messy_ds):
    """The whole point of the feature: type in the grid, see the new value in
    the grid. The Data tab reads through the prep pipeline, so the correction
    has to be there on the next load."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    await client.put(
        f"/api/v1/datasets/{ds.id}/prep-steps",
        json=[{"kind": "edit_cells", "key_column": "region", "column": "amount",
               "edits": [{"key": "ca", "value": 99}]}],
        headers=auth_headers["a"])

    r = await client.post(f"/api/v1/datasets/{ds.id}/data-preview",
                          json={"filters": [], "calculated_columns": [],
                                "limit": 50, "offset": 0},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    at = body["columns"].index("amount")
    region = body["columns"].index("region")
    corrected = [row[at] for row in body["rows"] if row[region] == "ca"]
    assert corrected == [99]


@pytest.mark.asyncio
async def test_a_correction_reaches_every_widget_on_the_dataset(
        client, auth_headers, db_session, two_orgs, messy_ds):
    # A correction only the Data tab honours would be a second, private copy
    # of the data -- the opposite of what a prep step is for.
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    await client.put(
        f"/api/v1/datasets/{ds.id}/prep-steps",
        json=[{"kind": "edit_cells", "key_column": "region", "column": "amount",
               "edits": [{"key": "MX", "value": 0}]}],
        headers=auth_headers["a"])

    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "region", "measure": "amount",
                                           "aggregation": "sum"}},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert {x["name"]: x["value"] for x in r.json()["rows"]}["MX"] == 0

@pytest.mark.asyncio
async def test_the_api_refuses_a_correction_to_the_key_column(
        client, auth_headers, db_session, two_orgs, messy_ds):
    ds = await _dataset(db_session, two_orgs["a"]["org"], messy_ds)
    r = await client.put(
        f"/api/v1/datasets/{ds.id}/prep-steps",
        json=[{"kind": "edit_cells", "key_column": "region", "column": "region",
               "edits": [{"key": "ca", "value": "CA"}]}],
        headers=auth_headers["a"])
    assert r.status_code == 400
