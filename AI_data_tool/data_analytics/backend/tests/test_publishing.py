"""Publishing and sharing (docs/publishing/PLAN.md): who may open a dashboard,
what they may do with it, and what happens to that when it is changed.

Every refusal here is the SERVER's: no test relies on a button being hidden.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.models import (AuditLogEntry, Dataset, DatasetColumn, OrgReviewSettings, OrgUnit, Report,
                               ReportSchedule, ReportUserGrant, Role, RowSecurityRule, User, UserOrgUnit)
from sqlalchemy import select

API = "/api/v1"


async def member(db, org_id, name, role=None):
    if role is None:
        role = Role(org_id=org_id, name=name, is_org_admin=False)
        db.add(role)
        await db.flush()
    user = User(org_id=org_id, role_id=role.id, email=f"{name}-{role.id}@ex.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    return role, user


def hdr(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def dashboard(client, author, name="Board", widget=None):
    rid = (await client.post(f"{API}/reports", json={"name": name}, headers=hdr(author))).json()["id"]
    page = (await client.get(f"{API}/reports/{rid}", headers=hdr(author))).json()["pages"][0]
    w = await client.post(f"{API}/reports/{rid}/pages/{page['id']}/widgets", headers=hdr(author),
                          json=widget or {"widget_type": "text", "title": "T", "config": {}, "layout": {"x": 0, "y": 0, "w": 4, "h": 3}})
    assert w.status_code == 201, w.text
    return rid, page["id"], w.json()["id"]


async def publish(client, author, rid, on=True):
    r = await client.post(f"{API}/reports/{rid}/publish", json={"published": on}, headers=hdr(author))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def people(db_session, two_orgs):
    org = two_orgs["a"]["org"]
    _, author = await member(db_session, org.id, "analyst")
    _, reader = await member(db_session, org.id, "reader")
    _, stranger = await member(db_session, org.id, "stranger")
    admin = two_orgs["a"]["user"]
    await db_session.commit()
    return {"org": org, "author": author, "reader": reader, "stranger": stranger, "admin": admin,
            "other_org": two_orgs["b"]["user"]}


# 1, 2, 7, 8 ─ publishing, direct URLs, changed ids, drafts ──────────────────

async def test_a_published_dashboard_opens_for_a_reader_and_a_draft_does_not_exist_for_them(client, people):
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    # A draft: not in the catalogue, and its id answers "not found" on every route -- never "forbidden".
    assert (await client.get(f"{API}/portal/catalog", headers=hdr(r))).json()["total"] == 0
    for path in (f"/reports/{rid}", f"/reports/{rid}/publication", f"/reports/{rid}/access", f"/reports/{rid}/pdf"):
        assert (await client.get(API + path, headers=hdr(r))).status_code == 404, path
    for method, path, body in (("post", f"/reports/{rid}/archive", None), ("post", f"/reports/{rid}/owner", {"email": r.email}),
                               ("patch", f"/reports/{rid}/publication", {"category": "x"}),
                               ("put", f"/portal/favorites/{rid}", None)):
        assert (await getattr(client, method)(API + path, json=body, headers=hdr(r))).status_code == 404, path
    await publish(client, a, rid)
    opened = await client.get(f"{API}/reports/{rid}", headers=hdr(r))
    assert opened.status_code == 200 and opened.json()["my_capability"] == "view"
    cat = (await client.get(f"{API}/portal/catalog", headers=hdr(r))).json()
    assert [i["id"] for i in cat["items"]] == [rid] and cat["items"][0]["via"] == "published"
    # Someone from another organisation: nothing, whatever the id.
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(people["other_org"]))).status_code == 404
    assert (await client.get(f"{API}/reports/{rid}/access", headers=hdr(people["other_org"]))).status_code == 404


async def test_a_reader_cannot_do_what_only_its_owner_may_whatever_they_send(client, people):
    a, r = people["author"], people["reader"]
    rid, pid, wid = await dashboard(client, a)
    await publish(client, a, rid)
    for method, path, body in (
            ("patch", f"/reports/{rid}/publication", {"viewers_may_export": True}),
            ("post", f"/reports/{rid}/archive", None), ("post", f"/reports/{rid}/restore", None),
            ("post", f"/reports/{rid}/owner", {"email": r.email}),
            ("post", f"/reports/{rid}/grants", {"email": people["stranger"].email, "level": "view"}),
            ("post", f"/reports/{rid}/publish", {"published": False}),
            ("post", f"/reports/{rid}/releases/1/rollback", None),
            ("patch", f"/reports/{rid}/pages/{pid}/widgets/{wid}", {"title": "mine now"})):
        got = await getattr(client, method)(API + path, json=body, headers=hdr(r))
        assert got.status_code == 403, (path, got.status_code, got.text[:120])
    access = (await client.get(f"{API}/reports/{rid}/access", headers=hdr(r))).json()
    assert access["view"] and not access["edit"] and not access["share"] and not access["publish"] and not access["administer"]


# 5, 6 ─ sharing: people, roles, teams; revoked; expired ─────────────────────

async def test_sharing_with_a_person_a_role_and_a_team_and_taking_it_back(client, db_session, people):
    a, org = people["author"], people["org"]
    role, by_role = await member(db_session, org.id, "finance")
    _, by_team = await member(db_session, org.id, "north")
    _, in_child = await member(db_session, org.id, "north-east")
    unit = OrgUnit(org_id=org.id, name="North", match_value="North")
    db_session.add(unit)
    await db_session.flush()
    child = OrgUnit(org_id=org.id, name="North East", match_value="North East", parent_id=unit.id)
    db_session.add(child)
    await db_session.flush()
    db_session.add_all([UserOrgUnit(user_id=by_team.id, org_unit_id=unit.id),
                        UserOrgUnit(user_id=in_child.id, org_unit_id=child.id)])
    await db_session.commit()
    rid, _, _ = await dashboard(client, a)                       # a DRAFT: only a share opens it

    async def opens(u):
        return (await client.get(f"{API}/reports/{rid}", headers=hdr(u))).status_code == 200

    assert not any([await opens(u) for u in (people["reader"], by_role, by_team, in_child)])
    made = {}
    for key, body in (("person", {"email": people["reader"].email, "level": "view", "message": "For Monday"}),
                      ("role", {"role_id": role.id, "level": "view"}), ("team", {"org_unit_id": unit.id, "level": "edit"})):
        got = await client.post(f"{API}/reports/{rid}/grants", json=body, headers=hdr(a))
        assert got.status_code == 201, got.text
        made[key] = got.json()
    assert [made[k]["kind"] for k in ("person", "role", "team")] == ["user", "role", "team"]
    assert all([await opens(u) for u in (people["reader"], by_role, by_team, in_child)])     # a team reaches the teams under it
    assert not await opens(people["stranger"])
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(in_child))).json()["my_capability"] == "edit"
    # The person was told, with the note.
    notes = (await client.get(f"{API}/notifications", headers=hdr(people["reader"]))).json()
    assert any("For Monday" in n["text"] and n["link"] == f"/reports/{rid}" for n in notes["notifications"])
    # The catalogue files each under how it reached them.
    via = lambda u: client.get(f"{API}/portal/catalog", headers=hdr(u))
    assert (await via(by_team)).json()["items"][0]["via"] == "team" and (await via(by_role)).json()["items"][0]["via"] == "role"
    assert (await client.get(f"{API}/portal/catalog?section=team", headers=hdr(by_team))).json()["total"] == 1
    # Taken back: each stops at once.
    for key, u in (("person", people["reader"]), ("role", by_role), ("team", in_child)):
        assert (await client.delete(f"{API}/reports/{rid}/grants/{made[key]['id']}", headers=hdr(a))).status_code == 204
        assert not await opens(u)
    # A share must name exactly one of the three, and only in this organisation.
    bad = await client.post(f"{API}/reports/{rid}/grants", json={"email": people["reader"].email, "role_id": role.id}, headers=hdr(a))
    assert bad.status_code == 400
    assert (await client.post(f"{API}/reports/{rid}/grants", json={"email": people["other_org"].email}, headers=hdr(a))).status_code == 404


async def test_an_expired_share_gives_nothing(client, db_session, people):
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    g = (await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "view", "expires_at": soon}, headers=hdr(a))).json()
    assert g["expires_at"] and not g["expired"]
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 200
    # The clock passes it (set in the past as the database would hold it).
    row = await db_session.get(ReportUserGrant, g["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 404
    assert (await client.get(f"{API}/portal/catalog", headers=hdr(r))).json()["total"] == 0
    listed = (await client.get(f"{API}/reports/{rid}/grants", headers=hdr(a))).json()
    assert listed[0]["expired"] is True                       # kept, and shown as lapsed, to its owner
    # A share cannot be made already expired.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert (await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "expires_at": past}, headers=hdr(a))).status_code == 400


async def test_sharing_on_never_gives_more_than_was_held(client, people):
    a, r, s = people["author"], people["reader"], people["stranger"]
    rid, _, _ = await dashboard(client, a)
    await client.post(f"{API}/reports/{rid}/grants", headers=hdr(a),
                      json={"email": r.email, "level": "view", "can_share": True, "can_export": False})
    assert (await client.get(f"{API}/reports/{rid}/access", headers=hdr(r))).json()["share"] is True
    # Not above view, not to a role, not with the right to share on again.
    for body in ({"email": s.email, "level": "edit"}, {"email": s.email, "level": "view", "can_share": True},
                 {"role_id": s.role_id, "level": "view"}):
        assert (await client.post(f"{API}/reports/{rid}/grants", json=body, headers=hdr(r))).status_code == 403, body
    ok = await client.post(f"{API}/reports/{rid}/grants", json={"email": s.email, "level": "view", "can_export": True}, headers=hdr(r))
    assert ok.status_code == 201 and ok.json()["can_export"] is False          # downloads were not theirs to give
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(s))).status_code == 200
    # They cannot see or change the list of shares.
    assert (await client.get(f"{API}/reports/{rid}/grants", headers=hdr(r))).status_code == 403


# 4 ─ viewing is not downloading ─────────────────────────────────────────────

async def test_downloads_can_be_refused_while_viewing_stays_allowed(client, db_session, people):
    a, r, s = people["author"], people["reader"], people["stranger"]
    rid, _, _ = await dashboard(client, a)
    await publish(client, a, rid)
    assert (await client.get(f"{API}/reports/{rid}/xlsx", headers=hdr(r))).status_code == 200      # as it always was
    # Switched off for one person: they still open it, and cannot take it away in any form.
    await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "view", "can_export": False}, headers=hdr(a))
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 200
    for path in ("xlsx", "pdf", "package"):
        got = await client.get(f"{API}/reports/{rid}/{path}", headers=hdr(r))
        assert got.status_code == 403 and "download" in got.json()["detail"].lower(), path
    access = (await client.get(f"{API}/reports/{rid}/access", headers=hdr(r))).json()
    assert access["view"] and not access["export"] and access["export_refusal"]
    assert (await client.get(f"{API}/reports/{rid}/xlsx", headers=hdr(s))).status_code == 200      # others are untouched
    # Switched off for every viewer: the owner and editors still may.
    await client.patch(f"{API}/reports/{rid}/publication", json={"viewers_may_export": False}, headers=hdr(a))
    assert (await client.get(f"{API}/reports/{rid}/xlsx", headers=hdr(s))).status_code == 403
    assert (await client.get(f"{API}/reports/{rid}/xlsx", headers=hdr(a))).status_code == 200
    assert (await client.get(f"{API}/portal/catalog", headers=hdr(s))).json()["items"][0]["can_export"] is False
    # The refusals are in the audit log, with who and why -- and no data.
    seen = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.action == "report.export_denied"))).scalars().all()
    assert {e.user_email for e in seen} >= {r.email, s.email} and all(e.entity_id == rid for e in seen)


async def test_the_print_view_is_a_download_and_is_refused_with_downloads(client, db_session, people):
    """F-02: Print / Save as PDF and PowerPoint are built from the print view,
    so the print view is gated like every other download."""
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    await publish(client, a, rid)
    assert (await client.get(f"{API}/reports/{rid}", params={"view": "print"}, headers=hdr(r))).status_code == 200
    await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "view", "can_export": False}, headers=hdr(a))
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 200          # viewing stays
    got = await client.get(f"{API}/reports/{rid}", params={"view": "print"}, headers=hdr(r))
    assert got.status_code == 403 and "download" in got.json()["detail"].lower()
    assert (await client.get(f"{API}/reports/{rid}", params={"view": "print"}, headers=hdr(a))).status_code == 200
    # Every viewer switched off; the author (an editor) still prints.
    await client.patch(f"{API}/reports/{rid}/publication", json={"viewers_may_export": False}, headers=hdr(a))
    assert (await client.get(f"{API}/reports/{rid}", params={"view": "print"}, headers=hdr(people["stranger"]))).status_code == 403
    assert (await client.get(f"{API}/reports/{rid}", params={"view": "print"}, headers=hdr(a))).status_code == 200
    actions = [e.action for e in (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.entity_id == rid))).scalars().all()]
    assert "report.export_denied" in actions and "report.export" in actions


async def test_guest_links_and_embeds_offer_no_download_route(client, people):
    """F-02 regression guard: the public surfaces have no export routes at all."""
    for path in ("/shared/tok/pdf", "/shared/tok/xlsx", "/shared/tok/export", "/embed/report/pdf", "/embed/export"):
        got = await client.get(API + path)
        assert got.status_code in (404, 405), path


# 9 ─ lifecycle: release, rollback, archive, restore, owner ──────────────────

async def test_readers_see_the_release_until_the_next_and_can_be_taken_back_to_an_earlier_one(client, people):
    a, r = people["author"], people["reader"]
    rid, pid, wid = await dashboard(client, a)
    first = (await publish(client, a, rid))["release"]

    async def title_seen(u):
        return (await client.get(f"{API}/reports/{rid}", headers=hdr(u))).json()["pages"][0]["widgets"][0]["title"]

    await client.patch(f"{API}/reports/{rid}/pages/{pid}/widgets/{wid}", json={"title": "Second"}, headers=hdr(a))
    assert await title_seen(r) == "T" and await title_seen(a) == "Second"       # the edit has not reached readers
    pub = (await client.get(f"{API}/reports/{rid}/publication", headers=hdr(a))).json()
    assert pub["state"] == "published" and pub["unreleased_changes"] is True and pub["published_by"] == a.email
    assert (await client.post(f"{API}/reports/{rid}/release", json={"note": "v2"}, headers=hdr(a))).status_code == 201
    assert await title_seen(r) == "Second"
    back = await client.post(f"{API}/reports/{rid}/releases/{first['id']}/rollback", headers=hdr(a))
    assert back.status_code == 201 and back.json()["release"]["reason"] == "rollback"
    assert await title_seen(r) == "T" and await title_seen(a) == "Second"       # readers go back; the draft is untouched
    history = (await client.get(f"{API}/reports/{rid}/releases", headers=hdr(a))).json()
    assert [h["reason"] for h in history][:3] == ["rollback", "release", "publish"]   # nothing rewritten
    assert (await client.post(f"{API}/reports/{rid}/releases/999999/rollback", headers=hdr(a))).status_code == 404


async def test_archiving_closes_everything_and_restoring_brings_it_back(client, db_session, people, monkeypatch):
    a, r, admin = people["author"], people["reader"], people["admin"]
    rid, _, _ = await dashboard(client, a)
    await publish(client, a, rid)
    await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "edit"}, headers=hdr(a))
    link = (await client.post(f"{API}/reports/{rid}/share-links", json={}, headers=hdr(a))).json()
    token = link.get("token") or link["url"].rsplit("/", 1)[-1]
    assert (await client.get(f"{API}/shared/{token}")).status_code == 200
    assert (await client.post(f"{API}/reports/{rid}/archive", headers=hdr(a))).json()["state"] == "archived"
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 404       # even with an edit share
    assert (await client.get(f"{API}/shared/{token}")).status_code == 404
    assert (await client.get(f"{API}/portal/catalog", headers=hdr(r))).json()["total"] == 0
    for u in (a, admin):                                                                      # owner and administrator keep it
        assert (await client.get(f"{API}/reports/{rid}", headers=hdr(u))).status_code == 200
    assert (await client.get(f"{API}/portal/catalog?section=archived", headers=hdr(a))).json()["total"] == 1
    assert (await client.post(f"{API}/reports/{rid}/publish", json={"published": True}, headers=hdr(a))).status_code in (200, 409)
    # F-04: it comes back as a DRAFT -- readers do not get it again until it is published again.
    assert (await client.post(f"{API}/reports/{rid}/restore", headers=hdr(a))).json()["state"] == "draft"
    assert (await client.get(f"{API}/reports/{rid}/publication", headers=hdr(a))).json()["state"] == "draft"
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(people["stranger"]))).status_code == 404  # reached it only by publication
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 200       # shares and links came back as they were
    assert (await client.get(f"{API}/shared/{token}")).status_code == 200
    restored = (await db_session.execute(select(AuditLogEntry).where(
        AuditLogEntry.action == "report.restore", AuditLogEntry.entity_id == rid))).scalars().all()
    assert restored and "draft" in (restored[-1].detail or "")
    await publish(client, a, rid)
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(people["stranger"]))).status_code == 200
    # Unpublishing leaves the named share and takes the rest of the organisation out.
    await publish(client, a, rid, on=False)
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(r))).status_code == 200
    assert (await client.get(f"{API}/reports/{rid}", headers=hdr(people["stranger"]))).status_code == 404


async def test_a_guest_link_stops_with_its_makers_access_and_with_the_policy(client, db_session, people, monkeypatch):
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    g = (await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "edit"}, headers=hdr(a))).json()
    link = (await client.post(f"{API}/reports/{rid}/share-links", json={}, headers=hdr(r))).json()
    token = link.get("token") or link["url"].rsplit("/", 1)[-1]
    assert (await client.get(f"{API}/shared/{token}")).status_code == 200
    await client.delete(f"{API}/reports/{rid}/grants/{g['id']}", headers=hdr(a))               # the maker loses access
    assert (await client.get(f"{API}/shared/{token}")).status_code == 404
    # The platform's policy: off by default, and off closes links that exist.
    assert type(settings).model_fields["guest_links_enabled"].default is False
    link2 = (await client.post(f"{API}/reports/{rid}/share-links", json={}, headers=hdr(a))).json()
    token2 = link2.get("token") or link2["url"].rsplit("/", 1)[-1]
    monkeypatch.setattr(settings, "guest_links_enabled", False)
    assert (await client.get(f"{API}/shared/{token2}")).status_code == 404
    refused = await client.post(f"{API}/reports/{rid}/share-links", json={}, headers=hdr(a))
    assert refused.status_code == 403 and "switched off" in refused.json()["detail"]


async def test_handing_a_dashboard_to_another_owner(client, db_session, people):
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    assert (await client.post(f"{API}/reports/{rid}/owner", json={"email": "nobody@ex.com"}, headers=hdr(a))).status_code == 404
    assert (await client.post(f"{API}/reports/{rid}/owner", json={"email": people["other_org"].email}, headers=hdr(a))).status_code == 404
    assert (await client.post(f"{API}/reports/{rid}/owner", json={"email": r.email}, headers=hdr(a))).json() == {"owner": r.email}
    new = (await client.get(f"{API}/reports/{rid}/access", headers=hdr(r))).json()
    old = (await client.get(f"{API}/reports/{rid}/access", headers=hdr(a))).json()
    assert new["is_owner"] and new["publish"] and old["edit"] and not old["publish"]           # kept in, no longer in charge
    assert (await client.post(f"{API}/reports/{rid}/owner", json={"email": a.email}, headers=hdr(a))).status_code == 403
    actions = (await db_session.execute(select(AuditLogEntry.action).where(AuditLogEntry.entity_id == rid))).scalars().all()
    assert "report.owner" in actions


async def test_where_approval_is_asked_for_nothing_goes_out_without_it(client, db_session, people):
    a, admin, org = people["author"], people["admin"], people["org"]
    db_session.add(OrgReviewSettings(org_id=org.id, require_approval=True))
    await db_session.commit()
    rid, pid, wid = await dashboard(client, a)
    refused = await client.post(f"{API}/reports/{rid}/publish", json={"published": True}, headers=hdr(a))
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "approval_needed"
    assert (await client.post(f"{API}/reports/{rid}/review/decision", json={"approve": True}, headers=hdr(a))).status_code == 403
    assert (await client.post(f"{API}/reports/{rid}/review/request", json={"note": "ready"}, headers=hdr(a))).json()["state"] == "requested"
    # Changed after asking: the approval would be of something else.
    await client.patch(f"{API}/reports/{rid}/pages/{pid}/widgets/{wid}", json={"title": "Changed"}, headers=hdr(a))
    assert (await client.post(f"{API}/reports/{rid}/review/decision", json={"approve": True}, headers=hdr(admin))).status_code == 409
    await client.post(f"{API}/reports/{rid}/review/request", headers=hdr(a))
    assert (await client.post(f"{API}/reports/{rid}/review/decision", json={"approve": True, "note": "ok"}, headers=hdr(admin))).json()["state"] == "approved"
    await publish(client, a, rid)
    # An edit after it is out needs approval again before readers get it.
    await client.patch(f"{API}/reports/{rid}/pages/{pid}/widgets/{wid}", json={"title": "Later"}, headers=hdr(a))
    assert (await client.post(f"{API}/reports/{rid}/release", headers=hdr(a))).status_code == 409
    # An administrator publishing is their own approval.
    rid2, _, _ = await dashboard(client, admin, "Admin's")
    await publish(client, admin, rid2)


# 3, 10 ─ another team's rows; cached answers ─────────────────────────────────

@pytest.fixture
async def two_teams(client, db_session, people, tmp_path):
    org, a = people["org"], people["author"]
    north_role, north = await member(db_session, org.id, "north-reader")
    south_role, south = await member(db_session, org.id, "south-reader")
    path = tmp_path / "rows.csv"
    path.write_text("area,amount\n" + "".join(f"North,{i}\n" for i in range(1, 11)) + "".join(f"South,{100 * i}\n" for i in range(1, 11)),
                    encoding="utf-8")
    ds = Dataset(name="Rows", filename=str(path), org_id=org.id, mode="import", row_count=20, col_count=2, created_by=a.id)
    db_session.add(ds)
    await db_session.flush()
    db_session.add_all([DatasetColumn(dataset_id=ds.id, name="area", dtype="categorical"),
                        DatasetColumn(dataset_id=ds.id, name="amount", dtype="numeric"),
                        RowSecurityRule(role_id=north_role.id, dataset_id=ds.id, filter_expr="area == 'North'"),
                        RowSecurityRule(role_id=south_role.id, dataset_id=ds.id, filter_expr="area == 'South'")])
    await db_session.commit()
    cfg = {"dimension": "area", "measure": "amount", "aggregation": "sum"}
    rid = (await client.post(f"{API}/reports", json={"name": "By area", "dataset_id": ds.id}, headers=hdr(a))).json()["id"]
    page = (await client.get(f"{API}/reports/{rid}", headers=hdr(a))).json()["pages"][0]
    await client.post(f"{API}/reports/{rid}/pages/{page['id']}/widgets", headers=hdr(a),
                      json={"widget_type": "bar", "title": "Amount", "config": cfg, "layout": {"x": 0, "y": 0, "w": 6, "h": 4}})
    await publish(client, a, rid)
    return {"ds": ds, "rid": rid, "cfg": cfg, "north": north, "south": south}


async def rows_for(client, world, user, **more):
    got = await client.post(f"{API}/datasets/{world['ds'].id}/widget-data", headers=hdr(user),
                            json={"widget_type": "bar", "config": {**world["cfg"], **more}, "report_id": world["rid"],
                                  "calculated_columns": [], "parameters": {}})
    assert got.status_code == 200, got.text
    return {r["name"]: r["value"] for r in got.json()["rows"]}


async def test_a_reader_sees_only_their_own_rows_and_a_cached_answer_never_crosses_over(client, people, two_teams):
    w = two_teams
    # The same chart, the same request, asked in turn and again: each time only their own rows.
    for _ in range(3):
        assert await rows_for(client, w, w["north"]) == {"North": 55}
        assert await rows_for(client, w, w["south"]) == {"South": 5500}
        assert await rows_for(client, w, people["author"]) == {"North": 55, "South": 5500}
    # A filter a reader adds themselves cannot reach the other team's rows.
    assert await rows_for(client, w, w["north"], filters=[{"column": "area", "op": "eq", "value": "South"}]) == {}
    # What they download is what they see.
    got = await client.post(f"{API}/datasets/{w['ds'].id}/widget-data/export?format=csv", headers=hdr(w["north"]),
                            json={"widget_type": "bar", "config": w["cfg"], "report_id": w["rid"], "calculated_columns": [], "parameters": {}})
    assert got.status_code == 200 and "North" in got.text and "South" not in got.text and "5500" not in got.text


async def test_a_download_of_one_chart_is_refused_with_the_dashboards_downloads(client, people, two_teams):
    w = two_teams
    await client.patch(f"{API}/reports/{w['rid']}/publication", json={"viewers_may_export": False}, headers=hdr(people["author"]))
    body = {"widget_type": "bar", "config": w["cfg"], "report_id": w["rid"], "calculated_columns": [], "parameters": {}}
    assert (await client.post(f"{API}/datasets/{w['ds'].id}/widget-data/export?format=csv", json=body, headers=hdr(w["north"]))).status_code == 403
    assert await rows_for(client, w, w["north"]) == {"North": 55}                # still viewable


async def test_a_chart_download_without_its_dashboard_cannot_slip_past_the_dashboards_downloads(client, people, two_teams):
    """F-02: the widget menu used to send no report_id, so the dashboard's
    "no downloads" was never consulted. A dataset the reader reaches only
    through a dashboard is downloadable only through that dashboard."""
    w = two_teams
    await client.patch(f"{API}/reports/{w['rid']}/publication", json={"viewers_may_export": False}, headers=hdr(people["author"]))
    body = {"widget_type": "bar", "config": w["cfg"], "calculated_columns": [], "parameters": {}}
    url = f"{API}/datasets/{w['ds'].id}/widget-data/export?format=csv"
    refused = await client.post(url, json=body, headers=hdr(w["north"]))
    assert refused.status_code == 403 and "dashboard" in refused.json()["detail"].lower()
    # Naming a dashboard that does not draw on this dataset does not help either.
    other, _, _ = await dashboard(client, people["author"], "Other")
    await publish(client, people["author"], other)
    assert (await client.post(url, json={**body, "report_id": other}, headers=hdr(w["north"]))).status_code == 403
    # The owner of the data still may, with or without the dashboard.
    assert (await client.post(url, json=body, headers=hdr(people["author"]))).status_code == 200
    # Downloads on again: through the dashboard it works, without it still not (the data is not theirs).
    await client.patch(f"{API}/reports/{w['rid']}/publication", json={"viewers_may_export": True}, headers=hdr(people["author"]))
    assert (await client.post(url, json={**body, "report_id": w["rid"]}, headers=hdr(w["north"]))).status_code == 200
    assert (await client.post(url, json=body, headers=hdr(w["north"]))).status_code == 403


# 11 ─ scheduled delivery ────────────────────────────────────────────────────

async def test_a_scheduled_delivery_is_decided_again_at_every_run(client, db_session, people, monkeypatch):
    from app.services import delivery
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    g = (await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "view"}, headers=hdr(a))).json()
    sent = []
    monkeypatch.setattr(delivery, "send_email", lambda *args, **kw: sent.append(args) or None)
    schedule = ReportSchedule(org_id=people["org"].id, report_id=rid, creator_user_id=r.id, interval_minutes=60,
                              recipients=["someone@ex.com"])
    db_session.add(schedule)
    await db_session.commit()

    async def run():
        await delivery.run_schedule(db_session, schedule)
        await db_session.refresh(schedule)
        return schedule.last_status or ""

    # Downloads switched off for this person since the schedule was made: nothing is sent.
    await client.patch(f"{API}/reports/{rid}/grants/{g['id']}", json={"can_export": False}, headers=hdr(a))
    assert "not sent" in await run() and "download" in schedule.last_status and not sent
    # Their access taken back: nothing is sent.
    await client.delete(f"{API}/reports/{rid}/grants/{g['id']}", headers=hdr(a))
    assert "can no longer open" in await run() and not sent
    # Archived: nothing is sent, whoever set it up.
    schedule.creator_user_id = a.id
    await db_session.commit()
    await client.post(f"{API}/reports/{rid}/archive", headers=hdr(a))
    assert "archived" in await run() and not sent


# 12 ─ the catalogue: favourites, search, size ────────────────────────────────

async def test_the_catalogue_shows_only_what_a_person_may_open_and_finds_it(client, db_session, people):
    a, r = people["author"], people["reader"]
    made = {}
    for name, category, tags in (("Sales by region", "Sales", ["weekly", "north"]), ("Stock levels", "Supply", ["daily"]),
                                 ("Private notes", "Sales", ["draft"])):
        rid, _, _ = await dashboard(client, a, name)
        await client.patch(f"{API}/reports/{rid}/publication", json={"category": category, "tags": tags + [tags[0].upper(), "  "]}, headers=hdr(a))
        made[name] = rid
    for name in ("Sales by region", "Stock levels"):
        await publish(client, a, made[name])

    async def cat(u, **q):
        return (await client.get(f"{API}/portal/catalog", params=q, headers=hdr(u))).json()

    assert {i["name"] for i in (await cat(r))["items"]} == {"Sales by region", "Stock levels"}       # the draft is not there
    assert [i["name"] for i in (await cat(r, q="region sales"))["items"]] == ["Sales by region"]
    assert [i["name"] for i in (await cat(r, category="supply"))["items"]] == ["Stock levels"]
    assert [i["name"] for i in (await cat(r, tag="weekly"))["items"]] == ["Sales by region"]
    assert (await cat(r, owner=a.email))["total"] == 2 and (await cat(r, q="private"))["total"] == 0
    assert (await cat(r, tag="weekly"))["items"][0]["tags"] == ["weekly", "north"]                   # tidied: no repeat, no blank
    facets = (await client.get(f"{API}/portal/facets", headers=hdr(r))).json()
    assert {c["value"] for c in facets["categories"]} == {"Sales", "Supply"}
    assert "draft" not in {t["value"] for t in facets["tags"]}                                      # nothing of what they cannot open
    # Favourites and recently viewed are their own.
    assert (await client.put(f"{API}/portal/favorites/{made['Stock levels']}", headers=hdr(r))).status_code == 204
    assert (await client.put(f"{API}/portal/favorites/{made['Private notes']}", headers=hdr(r))).status_code == 404
    assert [i["name"] for i in (await cat(r, section="favorites"))["items"]] == ["Stock levels"]
    assert (await cat(a, section="favorites"))["total"] == 0 and (await cat(a, section="mine"))["total"] == 3
    await client.delete(f"{API}/portal/favorites/{made['Stock levels']}", headers=hdr(r))
    assert (await cat(r, section="favorites"))["total"] == 0
    page = await cat(r, limit=1, offset=1)
    assert page["total"] == 2 and len(page["items"]) == 1 and page["counts"]["all"] == 2
    assert (await client.get(f"{API}/portal/catalog?section=nope", headers=hdr(r))).status_code == 400


async def test_a_large_catalogue_is_answered_in_a_fixed_number_of_queries(client, db_session, people):
    from sqlalchemy import event
    a, r, org = people["author"], people["reader"], people["org"]
    db_session.add_all([Report(name=f"Board {i}", org_id=org.id, created_by=a.id, published=True,
                               category=f"C{i % 7}", tags=[f"t{i % 13}"]) for i in range(600)])
    await db_session.commit()
    counted = []
    engine = db_session.bind.sync_engine if hasattr(db_session.bind, "sync_engine") else db_session.get_bind()
    listen = lambda *args: counted.append(1)
    event.listen(engine, "before_cursor_execute", listen)
    try:
        got = (await client.get(f"{API}/portal/catalog?limit=24", headers=hdr(r))).json()
    finally:
        event.remove(engine, "before_cursor_execute", listen)
    assert got["total"] == 600 and len(got["items"]) == 24
    assert len(counted) <= 20, f"{len(counted)} queries for a 600-dashboard catalogue"
    assert "pages" not in got["items"][0]                       # light rows: no pages, no widgets


# 13 ─ what is recorded ───────────────────────────────────────────────────────

async def test_every_change_of_access_or_state_is_recorded_with_who_and_what(client, db_session, people):
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    await publish(client, a, rid)
    g = (await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "view"}, headers=hdr(a))).json()
    await client.patch(f"{API}/reports/{rid}/grants/{g['id']}", json={"level": "edit", "can_export": False}, headers=hdr(a))
    await client.delete(f"{API}/reports/{rid}/grants/{g['id']}", headers=hdr(a))
    await client.patch(f"{API}/reports/{rid}/publication", json={"category": "Ops"}, headers=hdr(a))
    await client.post(f"{API}/reports/{rid}/archive", headers=hdr(a))
    await client.post(f"{API}/reports/{rid}/restore", headers=hdr(a))
    await publish(client, a, rid, on=False)
    rows = (await db_session.execute(select(AuditLogEntry).where(AuditLogEntry.entity == "report", AuditLogEntry.entity_id == rid))).scalars().all()
    assert {x.action for x in rows} >= {"report.publish", "report.share", "report.share_change", "report.unshare",
                                         "report.publication", "report.archive", "report.restore", "report.unpublish"}
    assert all(x.user_email == a.email and x.created_at for x in rows)


async def test_the_screen_is_told_the_same_answer_the_action_would_get(client, people, monkeypatch):
    """/authz/decisions is what a button is greyed from. It must not promise a
    download or a guest link the server would then refuse."""
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    await publish(client, a, rid)

    async def decide(user, action):
        got = await client.post(f"{API}/authz/decisions", headers=hdr(user),
                                json={"checks": [{"resource": "report", "id": rid, "action": action}]})
        assert got.status_code == 200, got.text
        return got.json()["decisions"][0]

    assert (await decide(r, "download"))["allowed"] is True
    await client.patch(f"{API}/reports/{rid}/publication", json={"viewers_may_export": False}, headers=hdr(a))
    refused = await decide(r, "download")
    assert refused["allowed"] is False and "switched downloads off" in refused["reason"]
    assert (await client.get(f"{API}/reports/{rid}/pdf", headers=hdr(r))).status_code == 403
    assert (await decide(a, "download"))["allowed"] is True                      # the owner still may

    assert (await decide(a, "share_link"))["allowed"] is True
    monkeypatch.setattr(settings, "guest_links_enabled", False)
    off = await decide(a, "share_link")
    assert off["allowed"] is False and "switched off" in off["reason"]
    monkeypatch.setattr(settings, "guest_links_enabled", True)
    await client.post(f"{API}/reports/{rid}/archive", headers=hdr(a))
    assert (await decide(a, "share_link"))["allowed"] is False


async def test_a_cross_site_request_cannot_change_sharing_or_state(client, people):
    """The browser sends the session cookie by itself; a write that comes with
    the cookie alone (what a form on another site can cause) is not signed in."""
    from app.core.security import SESSION_COOKIE
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    cookie = {"Cookie": f"{SESSION_COOKIE}={create_access_token(a.id, a.org_id)}"}
    for method, path, body in (("post", f"/reports/{rid}/grants", {"email": r.email, "level": "edit"}),
                               ("post", f"/reports/{rid}/archive", None),
                               ("post", f"/reports/{rid}/owner", {"email": r.email}),
                               ("patch", f"/reports/{rid}/publication", {"viewers_may_export": False}),
                               ("put", f"/portal/favorites/{rid}", None)):
        refused = await getattr(client, method)(API + path, json=body, headers=cookie)
        assert refused.status_code == 401, (path, refused.status_code)
    assert (await client.get(f"{API}/reports/{rid}/grants", headers=hdr(a))).json() == []
    assert (await client.get(f"{API}/reports/{rid}/publication", headers=hdr(a))).json()["state"] == "draft"
    # The same write with the header the application's own pages send goes through.
    ok = await client.post(f"{API}/reports/{rid}/grants", json={"email": r.email, "level": "view"},
                           headers={**cookie, "X-Requested-With": "XMLHttpRequest"})
    assert ok.status_code == 201, ok.text


async def test_text_people_type_is_stored_as_text_and_bounded(client, people):
    """A category, a tag or a message is shown as text by the screens; here:
    it is kept as typed (never interpreted), trimmed and bounded."""
    a, r = people["author"], people["reader"]
    rid, _, _ = await dashboard(client, a)
    markup = '<img src=x onerror=alert(1)>'
    got = (await client.patch(f"{API}/reports/{rid}/publication", headers=hdr(a),
                              json={"category": markup, "tags": [markup, "  a   b ", "A B", ""] + [f"t{i}" for i in range(40)]})).json()
    assert got["category"] == markup and got["tags"][0] == markup and got["tags"][1] == "a b"
    assert "A B" not in got["tags"] and len(got["tags"]) <= 20
    too_long = await client.post(f"{API}/reports/{rid}/grants", headers=hdr(a),
                                 json={"email": r.email, "level": "view", "message": "x" * 301})
    assert too_long.status_code == 400                                         # refused, nothing stored
    assert (await client.get(f"{API}/portal/catalog", headers=hdr(a), params={"q": "' OR 1=1 --"})).json()["total"] == 0
