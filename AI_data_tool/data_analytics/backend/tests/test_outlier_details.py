"""Outlier details behind the ⚠ badge: fences, the rows, and the impact."""
import pandas as pd
import pytest

from app.models.models import ColumnSecurityRule, Dataset, DatasetColumn, Role, User
from app.core.security import create_access_token, hash_password


@pytest.fixture
def spiky(tmp_path):
    p = tmp_path / "spiky.csv"
    # 20 quiet values and one 1000.0 spike: exactly one IQR outlier.
    pd.DataFrame({"who": [f"r{i}" for i in range(21)],
                  "amount": [10.0] * 10 + [12.0] * 10 + [1000.0]}).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path):
    ds = Dataset(name="Spiky", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("who", "categorical"), ("amount", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


@pytest.mark.asyncio
async def test_details_carry_stats_rows_and_impact(client, auth_headers, db_session, two_orgs, spiky):
    ds = await _dataset(db_session, two_orgs["a"]["org"], spiky)
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=amount",
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outliers"]["count"] == 1
    assert body["outliers"]["total_rows"] == 21
    assert body["outliers"]["rows"][0][0] == "r20"
    assert body["stats"]["median"] == pytest.approx(12.0)  # 11th of 21 sorted values
    # the spike carries ~82% of the total; removing it drops the mean to ~11
    assert body["impact"]["share_of_sum"] == pytest.approx(1000.0 / 1220.0)
    assert body["impact"]["mean_with"] == pytest.approx(1220.0 / 21)
    assert body["impact"]["mean_without"] == pytest.approx(11.0)


@pytest.mark.asyncio
async def test_denied_column_fails_closed(client, db_session, two_orgs, spiky):
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, spiky)
    role = Role(org_id=org.id, name="no-amount", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["amount"]))
    user = User(org_id=org.id, role_id=role.id, email="noamt@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=amount", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unknown_column_is_404_not_500(client, auth_headers, db_session, two_orgs, spiky):
    ds = await _dataset(db_session, two_orgs["a"]["org"], spiky)
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=nope",
                          headers=auth_headers["a"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detector_defaults_to_iqr_and_is_reported(client, auth_headers, db_session, two_orgs, spiky):
    """A3: byte-identical to before this task when `detector` is omitted, plus the
    new additive `detector` field."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], spiky)
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=amount",
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["detector"] == "iqr"


@pytest.mark.asyncio
async def test_iforest_detector_flags_the_spike(client, auth_headers, db_session, two_orgs, spiky):
    ds = await _dataset(db_session, two_orgs["a"]["org"], spiky)
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=amount&detector=iforest",
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detector"] == "iforest"
    assert body["outliers"]["count"] >= 1
    assert body["outliers"]["rows"][0][0] == "r20"
    # fences are still the IQR ones regardless of detector
    assert body["stats"]["fence_high"] == pytest.approx(12.0 + 1.5 * 2.0)


@pytest.mark.asyncio
async def test_ecod_detector_runs(client, auth_headers, db_session, two_orgs, spiky):
    ds = await _dataset(db_session, two_orgs["a"]["org"], spiky)
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=amount&detector=ecod",
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["detector"] == "ecod"


@pytest.mark.asyncio
async def test_unknown_detector_is_400(client, auth_headers, db_session, two_orgs, spiky):
    ds = await _dataset(db_session, two_orgs["a"]["org"], spiky)
    r = await client.post(f"/api/v1/datasets/{ds.id}/outlier-details?column=amount&detector=bogus",
                          headers=auth_headers["a"])
    assert r.status_code == 400
