"""Suggestions that remember (docs/suggestions/PLAN.md, phase 4)."""
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Report, Role, User


async def _report(db_session, org_id):
    ds = Dataset(name="parcels", org_id=org_id, filename="x.csv")
    db_session.add(ds)
    await db_session.flush()
    report = Report(name="r", org_id=org_id, dataset_id=ds.id)
    db_session.add(report)
    await db_session.commit()
    return report


async def test_a_dismissal_is_kept_per_person_and_can_be_taken_back(client, db_session, two_orgs, auth_headers):
    report = await _report(db_session, two_orgs["a"]["org"].id)
    url = f"/api/v1/reports/{report.id}/suggestion-feedback"
    h = auth_headers["a"]
    assert (await client.get(url, headers=h)).json() == {"dismissed": [], "types": {}, "org_types": {}}
    got = (await client.post(url, headers=h, json={"signature": "histogram|fee", "widget_type": "histogram",
                                                   "action": "dismissed"})).json()
    assert got["dismissed"] == ["histogram|fee"] and got["types"] == {"histogram": {"added": 0, "dismissed": 1}}
    # Asked again from another device: still dismissed.
    assert (await client.get(url, headers=h)).json()["dismissed"] == ["histogram|fee"]
    back = (await client.post(url, headers=h, json={"signature": "histogram|fee", "widget_type": "histogram",
                                                    "action": "restored"})).json()
    assert back["dismissed"] == [] and back["types"] == {}


async def test_the_last_thing_done_with_a_chart_stands(client, db_session, two_orgs, auth_headers):
    report = await _report(db_session, two_orgs["a"]["org"].id)
    url = f"/api/v1/reports/{report.id}/suggestion-feedback"
    h = auth_headers["a"]
    await client.post(url, headers=h, json={"signature": "bar|fee|city", "widget_type": "bar", "action": "dismissed"})
    got = (await client.post(url, headers=h, json={"signature": "bar|fee|city", "widget_type": "bar",
                                                   "action": "added"})).json()
    assert got["dismissed"] == [] and got["types"] == {"bar": {"added": 1, "dismissed": 0}}


async def test_one_persons_dismissals_are_not_anothers_but_the_org_learns(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"]
    report = await _report(db_session, org.id)
    url = f"/api/v1/reports/{report.id}/suggestion-feedback"
    await client.post(url, headers=auth_headers["a"], json={"signature": "treemap|x", "widget_type": "treemap",
                                                            "action": "dismissed"})
    role = Role(org_id=org.id, name="colleague", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    other = User(org_id=org.id, role_id=role.id, email="colleague@example.invalid", password_hash=hash_password("pw"))
    db_session.add(other)
    await db_session.commit()
    h = {"Authorization": f"Bearer {create_access_token(other.id, org.id)}"}
    got = (await client.get(url, headers=h)).json()
    assert got["dismissed"] == [] and got["types"] == {}
    assert got["org_types"] == {"treemap": {"added": 0, "dismissed": 1}}


async def test_another_orgs_report_is_not_found(client, db_session, two_orgs, auth_headers):
    report = await _report(db_session, two_orgs["b"]["org"].id)
    resp = await client.get(f"/api/v1/reports/{report.id}/suggestion-feedback", headers=auth_headers["a"])
    assert resp.status_code == 404
