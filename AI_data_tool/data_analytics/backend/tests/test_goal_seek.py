"""Goal seeking on a linear fit over the secured frame."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn


@pytest.fixture
def linearish(tmp_path):
    p = tmp_path / "l.csv"
    # y = 2x + 1 exactly: the solve is checkable by hand
    pd.DataFrame({"spend": [1.0, 2.0, 3.0, 4.0], "sales": [3.0, 5.0, 7.0, 9.0]}).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path):
    ds = Dataset(name="L", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c in ("spend", "sales"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    await db.commit()
    return ds


@pytest.mark.asyncio
async def test_solves_the_required_factor_value(client, auth_headers, db_session, two_orgs, linearish):
    ds = await _dataset(db_session, two_orgs["a"]["org"], linearish)
    r = await client.post(
        f"/api/v1/datasets/{ds.id}/goal-seek?x_column=spend&y_column=sales&target_y=15",
        headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["required_x"] == pytest.approx(7.0)     # 15 = 2x + 1
    assert body["r2"] == pytest.approx(1.0)
    assert body["within_observed_range"] is False       # 7 > max observed 4: extrapolation, flagged


@pytest.mark.asyncio
async def test_target_inside_the_data_is_marked_in_range(client, auth_headers, db_session, two_orgs, linearish):
    ds = await _dataset(db_session, two_orgs["a"]["org"], linearish)
    r = await client.post(
        f"/api/v1/datasets/{ds.id}/goal-seek?x_column=spend&y_column=sales&target_y=6",
        headers=auth_headers["a"])
    body = r.json()
    assert body["required_x"] == pytest.approx(2.5)
    assert body["within_observed_range"] is True


@pytest.mark.asyncio
async def test_flat_relationship_is_refused_not_divided_by_zero(client, auth_headers, db_session, two_orgs, tmp_path):
    p = tmp_path / "flat.csv"
    pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [5.0, 5.0, 5.0]}).to_csv(p, index=False)
    ds = await _dataset(db_session, two_orgs["a"]["org"], str(p))
    r = await client.post(
        f"/api/v1/datasets/{ds.id}/goal-seek?x_column=x&y_column=y&target_y=9",
        headers=auth_headers["a"])
    assert r.status_code == 400
    assert "flat" in r.json()["detail"]


@pytest.mark.asyncio
async def test_bounds_feasible_and_infeasible(client, auth_headers, db_session, two_orgs, linearish):
    """y = 2x + 1 exactly: target 15 needs x = 7. Bounds [0, 10] -> feasible;
    bounds [0, 5] -> infeasible, with the best achievable y at the bound."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], linearish)

    ok = await client.post(
        f"/api/v1/datasets/{ds.id}/goal-seek?x_column=spend&y_column=sales&target_y=15&x_min=0&x_max=10",
        headers=auth_headers["a"])
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["within_bounds"] is True
    assert abs(body["required_x"] - 7) < 1e-6

    capped = await client.post(
        f"/api/v1/datasets/{ds.id}/goal-seek?x_column=spend&y_column=sales&target_y=15&x_min=0&x_max=5",
        headers=auth_headers["a"])
    body = capped.json()
    assert body["within_bounds"] is False
    assert body["bound_x"] == 5
    assert abs(body["achievable_y"] - 11) < 1e-6  # 2*5 + 1


@pytest.mark.asyncio
async def test_inverted_bounds_rejected(client, auth_headers, db_session, two_orgs, linearish):
    ds = await _dataset(db_session, two_orgs["a"]["org"], linearish)
    r = await client.post(
        f"/api/v1/datasets/{ds.id}/goal-seek?x_column=spend&y_column=sales&target_y=15&x_min=30&x_max=10",
        headers=auth_headers["a"])
    assert r.status_code == 400
