"""Guided setup 0c: one journey per person and connection, read as the caller."""
from app.core.security import create_access_token, hash_password
from app.models.models import DataSource, Dataset, Report, Role, User


async def _source(db_session, org_id, name="cars", created_by=None):
    src = DataSource(name=name, type="postgresql", config={}, org_id=org_id, created_by=created_by)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def _member(db_session, org_id, email):
    role = Role(org_id=org_id, name=f"Member {email}", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_first_visit_starts_at_understand(client, db_session, two_orgs, auth_headers):
    src = await _source(db_session, two_orgs["a"]["org"].id)
    resp = await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["step"] == "understand" and body["position"] == 1 and body["total"] == 4
    assert body["source"]["name"] == "cars"
    # A second visit returns the same journey, not a new one.
    again = await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
    assert again.json()["id"] == body["id"]


async def test_progress_and_brief_round_trip(client, db_session, two_orgs, auth_headers):
    src = await _source(db_session, two_orgs["a"]["org"].id)
    await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
    resp = await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"], json={
        "step": "data",
        "brief": {"work": "  I sell used cars  ", "focus": "", "questions": "What sells fastest?"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["position"] == 2
    # Blank answers are dropped and the rest trimmed.
    assert body["brief"] == {"work": "I sell used cars", "questions": "What sells fastest?"}


async def test_unknown_step_is_refused(client, db_session, two_orgs, auth_headers):
    src = await _source(db_session, two_orgs["a"]["org"].id)
    await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
    resp = await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"], json={"step": "launch"})
    assert resp.status_code == 422


async def test_journeys_are_per_person(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"].id
    src = await _source(db_session, org)  # unowned: visible to every member
    member = await _member(db_session, org, "lawyer@example.com")
    await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
    await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"], json={"step": "check"})
    mine = await client.get(f"/api/v1/setup/{src.id}", headers=_h(member))
    assert mine.json()["step"] == "understand"


async def test_a_hidden_connection_is_404(client, db_session, two_orgs):
    org = two_orgs["a"]["org"].id
    owner = await _member(db_session, org, "owner@example.com")
    other = await _member(db_session, org, "other@example.com")
    src = await _source(db_session, org, created_by=owner.id)
    assert (await client.get(f"/api/v1/setup/{src.id}", headers=_h(other))).status_code == 404
    assert (await client.get(f"/api/v1/setup/{src.id}", headers=_h(owner))).status_code == 200


async def test_another_orgs_connection_is_404(client, db_session, two_orgs, auth_headers):
    src = await _source(db_session, two_orgs["b"]["org"].id)
    assert (await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])).status_code == 404


async def test_datasets_and_dashboard_must_be_the_callers_to_record(
        client, db_session, two_orgs, auth_headers):
    a, b = two_orgs["a"]["org"].id, two_orgs["b"]["org"].id
    src = await _source(db_session, a)
    ours = Dataset(name="cars listings", org_id=a, data_source_id=src.id)
    theirs = Dataset(name="theirs", org_id=b)
    their_report = Report(name="theirs", org_id=b)
    db_session.add_all([ours, theirs, their_report])
    await db_session.commit()
    await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])

    ok = await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"],
                            json={"dataset_ids": [ours.id, ours.id]})
    assert ok.status_code == 200 and ok.json()["dataset_ids"] == [ours.id]
    assert (await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"],
                               json={"dataset_ids": [theirs.id]})).status_code == 404
    assert (await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"],
                               json={"report_id": their_report.id})).status_code == 404


async def test_home_lists_only_unfinished_journeys(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"].id
    cars = await _source(db_session, org, "cars")
    shop = await _source(db_session, org, "shop")
    for src in (cars, shop):
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
    await client.patch(f"/api/v1/setup/{shop.id}", headers=auth_headers["a"], json={"step": "done"})
    resp = await client.get("/api/v1/setup/journeys", headers=auth_headers["a"])
    assert [j["source"]["name"] for j in resp.json()] == ["cars"]
