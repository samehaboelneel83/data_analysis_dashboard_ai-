"""Classifying a data item as Geography, the way SAS's data pane does.

Every map in this product asks the AUTHOR, per widget, which boundary set to
draw and hopes the column matches it. SAS asks once, on the data item:
`Country` is classified as Geography and every map built from it inherits that.

The gap this closes is repetition, not capability -- a dataset with a governorate
column and six maps on it currently means choosing the same boundary set six
times, and getting it wrong once means one map silently draws nothing.

Two rules the role has to obey:

  * **A geography is still a category.** Everything that groups, filters, sorts
    or counts by it must behave exactly as before -- the classification adds a
    default for maps, it does not create a new kind of column.

  * **The boundary set travels with it.** "This column is geography" is not
    useful on its own; "this column is geography, drawn with THESE shapes" is.
"""
import pytest

from app.models.models import Dataset, DatasetColumn


async def _dataset(db_session, org_id, tmp_path):
    import pandas as pd
    path = tmp_path / "geo.csv"
    pd.DataFrame([{"governorate": "Cairo", "sales": 5.0},
                  {"governorate": "Giza", "sales": 7.0}]).to_csv(path, index=False)
    ds = Dataset(name="Geo", filename=str(path), org_id=org_id, mode="import",
                 row_count=2, col_count=2)
    db_session.add(ds)
    await db_session.flush()
    for name, dtype in (("governorate", "categorical"), ("sales", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


@pytest.mark.asyncio
async def test_a_column_can_be_classified_as_geography(
        client, auth_headers, db_session, two_orgs, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"governorate": {"role": "geography"}}},
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    got = (await client.get(f"/api/v1/datasets/{ds.id}/column-meta",
                            headers=auth_headers["a"])).json()
    assert got["governorate"]["role"] == "geography"


@pytest.mark.asyncio
async def test_the_boundary_set_travels_with_the_column(
        client, auth_headers, db_session, two_orgs, tmp_path):
    """"This column is geography" is not useful on its own; "drawn with THESE
    shapes" is, and it is what saves choosing the same set on every map."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.put(
        f"/api/v1/datasets/{ds.id}/column-meta",
        json={"meta": {"governorate": {"role": "geography", "boundary_set_id": 7}}},
        headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    got = (await client.get(f"/api/v1/datasets/{ds.id}/column-meta",
                            headers=auth_headers["a"])).json()
    assert got["governorate"]["boundary_set_id"] == 7


@pytest.mark.asyncio
async def test_a_geography_still_groups_like_any_category(
        client, auth_headers, db_session, two_orgs, tmp_path):
    # The classification adds a default for maps. It must not create a new kind
    # of column that the shapers then have to know about.
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                     json={"meta": {"governorate": {"role": "geography"}}},
                     headers=auth_headers["a"])

    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "governorate", "measure": "sales",
                                           "aggregation": "sum"}},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"Cairo": 5.0, "Giza": 7.0}


@pytest.mark.asyncio
async def test_an_invented_classification_is_still_refused(
        client, auth_headers, db_session, two_orgs, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.put(f"/api/v1/datasets/{ds.id}/column-meta",
                         json={"meta": {"governorate": {"role": "nonsense"}}},
                         headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_a_negative_boundary_set_is_refused(
        client, auth_headers, db_session, two_orgs, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.put(
        f"/api/v1/datasets/{ds.id}/column-meta",
        json={"meta": {"governorate": {"role": "geography", "boundary_set_id": -1}}},
        headers=auth_headers["a"])
    assert r.status_code == 400
