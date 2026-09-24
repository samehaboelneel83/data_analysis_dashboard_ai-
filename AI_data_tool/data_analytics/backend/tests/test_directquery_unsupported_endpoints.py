"""
DirectQuery datasets have no local file, so refresh (which re-fetches into that
file) can never work for them -- there's nothing to refresh, the dataset always
queries the live source directly. Before this fix `refresh` crashed with a
confusing "Refresh failed: ..." message (`Path(None)`). This test asserts a
clean, correctly-worded 400 instead.

Analysis and data-preview were also unsupported here previously, but both now
work for DirectQuery datasets (a capped/sampled live row fetch feeds the same
analysis/preview logic import-mode datasets use) -- see
test_analysis_directquery_router.py and test_data_preview_directquery_router.py
for their coverage.
"""
from app.models.models import DataSource, Dataset, DatasetColumn


async def _seed_directquery_dataset(db_session, org_id):
    src = DataSource(name="Live DB", type="sqlite", config={}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="DQ Dataset", org_id=org_id, mode="directquery",
                  data_source_id=src.id, source_table="sales")
    db_session.add(ds)
    await db_session.flush()
    db_session.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_refresh_on_directquery_dataset_returns_clean_400(client, db_session, two_orgs, auth_headers):
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh", headers=auth_headers["a"])

    assert resp.status_code == 400
    assert "directquery" in resp.json()["detail"].lower()
