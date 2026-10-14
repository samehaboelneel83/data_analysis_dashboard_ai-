""""Allow AI" per dataset: the switch an uploaded file did not have
(docs/discovery/PLAN.md, phase 0; services/ai_policy.py)."""
from app.models.models import DataSource, Dataset


async def _dataset(db_session, two_orgs, **kw):
    ds = Dataset(name="upload", filename="u.csv", org_id=two_orgs["a"]["org"].id, **kw)
    db_session.add(ds)
    await db_session.commit()
    return ds


async def test_an_uploaded_dataset_follows_the_default_until_someone_sets_it(client, auth_headers, two_orgs, db_session):
    ds = await _dataset(db_session, two_orgs)
    got = (await client.get(f"/api/v1/datasets/{ds.id}/allow-ai", headers=auth_headers["a"])).json()
    assert got == {"own": None, "effective": True, "decided_by": "default", "connection": None}
    off = await client.put(f"/api/v1/datasets/{ds.id}/allow-ai", json={"allow": False}, headers=auth_headers["a"])
    assert off.status_code == 200 and off.json()["effective"] is False and off.json()["decided_by"] == "dataset"
    back = await client.put(f"/api/v1/datasets/{ds.id}/allow-ai", json={"allow": None}, headers=auth_headers["a"])
    assert back.json()["own"] is None and back.json()["effective"] is True


async def test_a_dataset_cannot_switch_on_what_its_connection_switched_off(client, auth_headers, two_orgs, db_session):
    src = DataSource(name="Warehouse", type="postgresql", org_id=two_orgs["a"]["org"].id, allow_llm_sampling=False)
    db_session.add(src)
    await db_session.flush()
    ds = await _dataset(db_session, two_orgs, data_source_id=src.id)
    on = await client.put(f"/api/v1/datasets/{ds.id}/allow-ai", json={"allow": True}, headers=auth_headers["a"])
    assert on.json()["effective"] is False and on.json()["decided_by"] == "connection"
    assert on.json()["connection"] == "Warehouse"


async def test_another_organisation_cannot_read_or_change_it(client, auth_headers, two_orgs, db_session):
    ds = await _dataset(db_session, two_orgs)
    assert (await client.get(f"/api/v1/datasets/{ds.id}/allow-ai", headers=auth_headers["b"])).status_code == 404
    assert (await client.put(f"/api/v1/datasets/{ds.id}/allow-ai", json={"allow": False},
                             headers=auth_headers["b"])).status_code == 404


async def test_only_true_false_or_null_is_accepted(client, auth_headers, two_orgs, db_session):
    ds = await _dataset(db_session, two_orgs)
    bad = await client.put(f"/api/v1/datasets/{ds.id}/allow-ai", json={"allow": "yes"}, headers=auth_headers["a"])
    assert bad.status_code == 400
