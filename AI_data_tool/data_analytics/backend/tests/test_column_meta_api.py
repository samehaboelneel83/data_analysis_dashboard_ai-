"""Per-column metadata — SAS's "data item properties".

One JSON map on the dataset carries the overrides a report author needs per column:
a classification override (use a numeric code as a category), a default aggregation,
a visibility flag, and a friendly label. PUT takes the whole map, which is what makes
bulk edits across many columns a single request rather than N.

Detection stays the source of truth for `dtype`; this only ever overrides it, so a
re-upload that changes types does not silently strand an override.
"""
import pandas as pd

from app.models.models import Dataset, DatasetColumn


async def _dataset(db_session, org_id, tmp_path, name="ds"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame([{"region": "East", "sales": 100, "zip": 90210}]).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, row_count=1, col_count=3)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    for col, dtype in (("region", "categorical"), ("sales", "numeric"), ("zip", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype, missing_pct=0, stats={}))
    await db_session.commit()
    return ds


async def test_column_meta_starts_empty(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.get(f"/api/v1/datasets/{ds.id}/column-meta", headers=auth_headers["a"])

    assert r.status_code == 200
    assert r.json() == {}


async def test_put_and_get_roundtrips_the_whole_map(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    payload = {"meta": {
        "zip": {"role": "category"},
        "sales": {"aggregation": "avg", "label": "Revenue"},
    }}

    put = await client.put(f"/api/v1/datasets/{ds.id}/column-meta", json=payload, headers=auth_headers["a"])
    got = await client.get(f"/api/v1/datasets/{ds.id}/column-meta", headers=auth_headers["a"])

    assert put.status_code == 200
    assert got.json()["zip"]["role"] == "category"
    assert got.json()["sales"]["aggregation"] == "avg"
    assert got.json()["sales"]["label"] == "Revenue"


async def test_a_single_put_can_change_many_columns_at_once(db_session, two_orgs, auth_headers, client, tmp_path):
    """This is the bulk-edit path: one request, N columns."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta", json={"meta": {
        "region": {"hidden": True},
        "sales": {"hidden": True},
        "zip": {"hidden": True},
    }}, headers=auth_headers["a"])

    assert all(v["hidden"] for v in r.json().values())
    assert len(r.json()) == 3


async def test_put_replaces_rather_than_merges_so_a_property_can_be_cleared(
    db_session, two_orgs, auth_headers, client, tmp_path,
):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                     json={"meta": {"sales": {"aggregation": "avg"}}}, headers=auth_headers["a"])

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {}}, headers=auth_headers["a"])

    assert r.json() == {}


async def test_unknown_column_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"nope": {"hidden": True}}}, headers=auth_headers["a"])

    assert r.status_code == 400
    assert "nope" in r.json()["detail"]


async def test_a_calculated_column_may_carry_meta(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    ds.calculated_columns = [{"name": "margin", "expression": "sales * 2"}]
    await db_session.commit()

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"margin": {"aggregation": "avg"}}}, headers=auth_headers["a"])

    assert r.status_code == 200


async def test_an_unknown_role_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    """The example used to be "geography", which is now a REAL role: a category
    that also says what it is a category of, so a map inherits its boundary set.
    The invariant is unchanged -- a role the engine does not know is refused at
    write time rather than silently ignored at query time -- so only the example
    moved. `test_geography_classification.py` asserts the same refusal, and that
    geography itself is accepted."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"zip": {"role": "postcode"}}}, headers=auth_headers["a"])

    assert r.status_code == 400


async def test_an_unknown_aggregation_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    """A bad aggregation would be silently ignored at query time and render a
    plausible wrong number, so it is refused at write time."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"sales": {"aggregation": "bogus"}}}, headers=auth_headers["a"])

    assert r.status_code == 400


async def test_column_meta_is_returned_on_the_dataset(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                     json={"meta": {"zip": {"role": "category"}}}, headers=auth_headers["a"])

    body = (await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])).json()

    assert body["column_meta"]["zip"]["role"] == "category"


async def test_another_orgs_dataset_is_not_reachable(db_session, two_orgs, auth_headers, client, tmp_path):
    other = await _dataset(db_session, two_orgs["b"]["org"].id, tmp_path, name="other")

    r = await client.get(f"/api/v1/datasets/{other.id}/column-meta", headers=auth_headers["a"])

    assert r.status_code == 404
