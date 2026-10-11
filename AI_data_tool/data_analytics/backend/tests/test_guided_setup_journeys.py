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


# ── flows: several analyses (steps 2-4) on one connection (PLAN_V2, part 1) ──

async def _past_understand(client, src, headers):
    await client.get(f"/api/v1/setup/{src.id}", headers=headers)
    return (await client.patch(f"/api/v1/setup/{src.id}", headers=headers, json={"step": "data"})).json()


async def test_a_second_analysis_never_replaces_the_first(client, db_session, two_orgs, auth_headers):
    h = auth_headers["a"]
    src = await _source(db_session, two_orgs["a"]["org"].id)
    first = await _past_understand(client, src, h)
    ds = Dataset(name="parcels", org_id=two_orgs["a"]["org"].id, data_source_id=src.id)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    await client.patch(f"/api/v1/setup/{src.id}", headers=h, json={
        "brief": {"work": "ops manager", "focus": "Express only"}, "dataset_ids": [ds.id],
        "created_ids": [ds.id], "step": "check"})

    second = (await client.post(f"/api/v1/setup/{src.id}/flows", headers=h)).json()
    assert second["flow_id"] != first["flow_id"] and second["step"] == "data"
    # Who the person is was asked once; what they want this time was not.
    assert second["brief"] == {"work": "ops manager"} and second["dataset_ids"] == []
    assert [f["step"] for f in second["flows"]] == ["check", "data"]

    await client.patch(f"/api/v1/setup/{src.id}", headers=h, params={"flow": second["flow_id"]},
                       json={"brief": {"focus": "returns"}})
    one = (await client.get(f"/api/v1/setup/{src.id}", headers=h, params={"flow": first["flow_id"]})).json()
    assert one["brief"]["focus"] == "Express only" and one["dataset_ids"] == [ds.id] and one["step"] == "check"
    two = (await client.get(f"/api/v1/setup/{src.id}", headers=h, params={"flow": second["flow_id"]})).json()
    assert two["brief"] == {"focus": "returns"} and two["step"] == "data"


async def test_pressing_new_twice_makes_one_empty_analysis(client, db_session, two_orgs, auth_headers):
    h = auth_headers["a"]
    src = await _source(db_session, two_orgs["a"]["org"].id)
    await _past_understand(client, src, h)
    a = (await client.post(f"/api/v1/setup/{src.id}/flows", headers=h)).json()
    b = (await client.post(f"/api/v1/setup/{src.id}/flows", headers=h)).json()
    assert a["flow_id"] == b["flow_id"] and len(b["flows"]) == 1      # the first was still empty


async def test_a_journey_from_before_flows_keeps_its_progress(client, db_session, two_orgs, auth_headers, org_admin=None):
    from app.models.models import SetupJourney
    org, user = two_orgs["a"]["org"], two_orgs["a"]["user"]
    src = await _source(db_session, org.id)
    db_session.add(SetupJourney(org_id=org.id, user_id=user.id, data_source_id=src.id, step="check",
                                brief={"work": "dealer"}, proposals={"items": [{"id": "p1"}]}))
    await db_session.commit()
    body = (await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])).json()
    assert body["step"] == "check" and body["brief"] == {"work": "dealer"} and len(body["flows"]) == 1
    step = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
    assert [p["id"] for p in step["proposals"]["items"]] == ["p1"]


async def test_home_offers_each_unfinished_analysis_and_can_rename_or_remove_one(
        client, db_session, two_orgs, auth_headers):
    h = auth_headers["a"]
    src = await _source(db_session, two_orgs["a"]["org"].id)
    first = await _past_understand(client, src, h)
    await client.patch(f"/api/v1/setup/{src.id}", headers=h, json={"brief": {"focus": "Express only"}})
    second = (await client.post(f"/api/v1/setup/{src.id}/flows", headers=h)).json()
    await client.patch(f"/api/v1/setup/{src.id}/flows/{second['flow_id']}", headers=h, json={"name": "Returns"})
    mine = (await client.get("/api/v1/setup/journeys", headers=h)).json()
    assert {(m["flow_id"], m["flow_name"]) for m in mine} == {(first["flow_id"], "Express only"),
                                                               (second["flow_id"], "Returns")}
    # A finished analysis is no longer offered to continue.
    await client.patch(f"/api/v1/setup/{src.id}", headers=h, params={"flow": first["flow_id"]}, json={"step": "done"})
    mine = (await client.get("/api/v1/setup/journeys", headers=h)).json()
    assert [m["flow_id"] for m in mine] == [second["flow_id"]]
    left = (await client.patch(f"/api/v1/setup/{src.id}/flows/{second['flow_id']}", headers=h,
                               json={"archived": True})).json()
    assert [f["id"] for f in left["flows"]] == [first["flow_id"]]


async def test_another_persons_analysis_cannot_be_opened(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"]
    src = await _source(db_session, org.id)
    mine = await _past_understand(client, src, auth_headers["a"])
    other = await _member(db_session, org.id, "flows-other@example.invalid")
    resp = await client.get(f"/api/v1/setup/{src.id}", headers=_h(other), params={"flow": mine["flow_id"]})
    assert resp.status_code == 404
