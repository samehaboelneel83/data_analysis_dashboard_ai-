"""Guest share links: mint/list/revoke, and the anonymous surface's security --
creator-frozen RLS, saved-config-only queries, and 404-on-everything-invalid."""
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import (
    Dataset, DatasetColumn, Report, ReportPage, ReportWidget,
    Role, RowSecurityRule, ShareLink, User,
)


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({"region": ["US", "US", "EU"], "amount": [10.0, 20.0, 40.0]}).to_csv(p, index=False)
    return str(p)


async def _fixture(db, org, path):
    ds = Dataset(name="S", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c in ("region", "amount"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    r = Report(name="Shared R", dataset_id=ds.id, org_id=org.id)
    db.add(r)
    await db.flush()
    page = ReportPage(report_id=r.id, name="P1", position=0)
    db.add(page)
    await db.flush()
    w = ReportWidget(page_id=page.id, widget_type="bar",
                     config={"dimension": "region", "measure": "amount", "aggregation": "sum"})
    db.add(w)
    await db.commit()
    return ds, r, w


@pytest.mark.asyncio
async def test_mint_view_and_query_round_trip(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    resp = await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 7},
                             headers=auth_headers["a"])
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]

    # anonymous: no Authorization header anywhere below
    resp = await client.get(f"/api/v1/shared/{token}")
    body = resp.json()
    assert body["name"] == "Shared R"
    assert body["pages"][0]["widgets"][0]["id"] == w.id

    resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")
    assert {x["name"]: x["value"] for x in resp.json()["rows"]} == {"US": 30.0, "EU": 40.0}


@pytest.mark.asyncio
async def test_link_carries_the_creators_rls_not_more(client, db_session, two_orgs, salesfile):
    """A restricted user's link exposes exactly their slice: the anonymous
    holder sees US rows only, because the CREATOR sees US rows only."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    role = Role(org_id=org.id, name="us-only", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="`region` == 'US'"))
    user = User(org_id=org.id, role_id=role.id, email="us@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    # POST .../share-links needs 'edit' capability (routers/reports.py); an
    # unowned report (created_by=None, as `_fixture` leaves it) caps a
    # non-admin at 'view' (core/capability.py _resolve's "UNOWNED reports"
    # rule) -- correct product behaviour, but this test's whole point is that
    # THIS restricted user is the link's creator, so they must actually own it.
    r.created_by = user.id
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=headers)).json()["token"]
    resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")
    assert {x["name"] for x in resp.json()["rows"]} == {"US"}


@pytest.mark.asyncio
async def test_expired_revoked_and_bogus_tokens_all_404_identically(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]

    assert (await client.get("/api/v1/shared/definitely-not-a-token")).status_code == 404

    # revoke, then the working token dies
    links = (await client.get(f"/api/v1/reports/{r.id}/share-links", headers=auth_headers["a"])).json()
    await client.delete(f"/api/v1/reports/{r.id}/share-links/{links[0]['id']}", headers=auth_headers["a"])
    assert (await client.get(f"/api/v1/shared/{token}")).status_code == 404
    assert (await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")).status_code == 404

    # expiry: force the clock past it on a fresh link
    token2 = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 1},
                                headers=auth_headers["a"])).json()["token"]
    from app.routers.shared import hash_token
    link = (await db_session.execute(
        __import__("sqlalchemy").select(ShareLink).where(ShareLink.token_hash == hash_token(token2))
    )).scalars().one()
    link.expires_at = datetime.utcnow() - timedelta(minutes=1)
    await db_session.commit()
    assert (await client.get(f"/api/v1/shared/{token2}")).status_code == 404


@pytest.mark.asyncio
async def test_share_token_opens_nothing_but_the_two_shared_routes(client, auth_headers, db_session, two_orgs, salesfile):
    ds, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    fake = {"Authorization": f"Bearer {token}"}
    # the token is not a JWT: everything JWT-guarded rejects it
    assert (await client.get(f"/api/v1/reports/{r.id}", headers=fake)).status_code == 401
    assert (await client.get("/api/v1/datasets", headers=fake)).status_code == 401
    assert (await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                              json={"widget_type": "bar", "config": {}}, headers=fake)).status_code == 401


@pytest.mark.asyncio
async def test_only_saved_widgets_resolve_never_foreign_ones(client, auth_headers, db_session, two_orgs, salesfile):
    org_a = two_orgs["a"]["org"]
    _, r, _ = await _fixture(db_session, org_a, salesfile)
    _, r2, w2 = await _fixture(db_session, two_orgs["b"]["org"], salesfile)
    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    # a widget from ANOTHER org's report does not resolve through this link
    assert (await client.post(f"/api/v1/shared/{token}/widget-data/{w2.id}")).status_code == 404


@pytest.mark.asyncio
async def test_pinned_link_unchanged_after_report_edit(client, auth_headers, db_session, two_orgs, salesfile):
    """A pinned link freezes pages/widgets at mint time: editing the report
    afterwards (renaming a page, adding a widget) never reaches that guest."""
    from app.models.models import ReportPage, ReportWidget

    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    resp = await client.post(f"/api/v1/reports/{r.id}/share-links",
                             json={"expires_days": 7, "pinned": True}, headers=auth_headers["a"])
    assert resp.status_code == 201, resp.text
    assert resp.json()["pinned"] is True
    token = resp.json()["token"]

    before = (await client.get(f"/api/v1/shared/{token}")).json()
    assert before["pinned"] is True
    assert before["pages"][0]["name"] == "P1"
    assert len(before["pages"][0]["widgets"]) == 1

    # edit the live report: rename the page, add a widget
    page_id = before["pages"][0]["id"]
    page = await db_session.get(ReportPage, page_id)
    page.name = "Renamed"
    db_session.add(ReportWidget(page_id=page_id, widget_type="bar",
                               config={"dimension": "region", "measure": "amount", "aggregation": "sum"}))
    await db_session.commit()

    after = (await client.get(f"/api/v1/shared/{token}")).json()
    assert after["pages"][0]["name"] == "P1"  # not "Renamed"
    assert len(after["pages"][0]["widgets"]) == 1  # the new widget is invisible


@pytest.mark.asyncio
async def test_unpinned_link_follows_report_edits(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    resp = await client.post(f"/api/v1/reports/{r.id}/share-links",
                             json={"expires_days": 7}, headers=auth_headers["a"])
    assert resp.json()["pinned"] is False
    token = resp.json()["token"]

    from app.models.models import ReportPage
    page = await db_session.get(ReportPage, (await client.get(f"/api/v1/shared/{token}")).json()["pages"][0]["id"])
    page.name = "Renamed"
    await db_session.commit()

    after = (await client.get(f"/api/v1/shared/{token}")).json()
    assert after["pages"][0]["name"] == "Renamed"
    assert after["pinned"] is False


@pytest.mark.asyncio
async def test_pin_stores_via_the_real_page_serializer(client, auth_headers, db_session, two_orgs, salesfile):
    """The stored snapshot round-trips through the guest view render with the
    same widget config/layout the report GET would have shown."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    token = (await client.post(f"/api/v1/reports/{r.id}/share-links",
                               json={"pinned": True}, headers=auth_headers["a"])).json()["token"]
    body = (await client.get(f"/api/v1/shared/{token}")).json()
    widget = body["pages"][0]["widgets"][0]
    assert widget["config"] == {"dimension": "region", "measure": "amount", "aggregation": "sum"}

    resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")
    assert {x["name"]: x["value"] for x in resp.json()["rows"]} == {"US": 30.0, "EU": 40.0}


@pytest.mark.asyncio
async def test_guest_view_never_shows_non_normal_pages_live(client, auth_headers, db_session, two_orgs, salesfile):
    """Hidden/popup/tooltip/drillthrough pages are absent from the guest
    payload's CONTENT, not merely unlinked -- the server never serializes
    them for an anonymous viewer, live path."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    hidden = ReportPage(report_id=r.id, name="Notes", position=1, page_type="hidden")
    popup = ReportPage(report_id=r.id, name="Popup", position=2, page_type="popup")
    tooltip = ReportPage(report_id=r.id, name="Tip", position=3, page_type="tooltip")
    drillthrough = ReportPage(report_id=r.id, name="Drill", position=4, page_type="drillthrough")
    db_session.add_all([hidden, popup, tooltip, drillthrough])
    await db_session.flush()
    hidden_widget = ReportWidget(page_id=hidden.id, widget_type="text", config={"secret": "do not ship"})
    db_session.add(hidden_widget)
    await db_session.commit()

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    body = (await client.get(f"/api/v1/shared/{token}")).json()
    page_names = {p["name"] for p in body["pages"]}
    assert page_names == {"P1"}
    assert "secret" not in str(body)  # the hidden page's widget config never serialised

    # nor is the hidden widget resolvable directly by id
    resp = await client.post(f"/api/v1/shared/{token}/widget-data/{hidden_widget.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pinned_snapshot_also_filters_non_normal_pages(client, auth_headers, db_session, two_orgs, salesfile):
    """Interaction of pinning + page filtering: a snapshot taken while the
    report had a hidden page must ALSO filter it out at serve time."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    hidden = ReportPage(report_id=r.id, name="Notes", position=1, page_type="hidden")
    db_session.add(hidden)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=hidden.id, widget_type="text", config={"secret": "do not ship"}))
    await db_session.commit()

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={"pinned": True},
                               headers=auth_headers["a"])).json()["token"]
    body = (await client.get(f"/api/v1/shared/{token}")).json()
    assert {p["name"] for p in body["pages"]} == {"P1"}
    assert "secret" not in str(body)


@pytest.mark.asyncio
async def test_non_creator_non_admin_cannot_revoke(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    _, r, _ = await _fixture(db_session, org, salesfile)
    resp = await client.post(f"/api/v1/reports/{r.id}/share-links", json={}, headers=auth_headers["a"])
    link_id = resp.json()["id"]

    role = Role(org_id=org.id, name="bystander", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    u2 = User(org_id=org.id, role_id=role.id, email="by@example.com",
              password_hash=hash_password("pw"))
    db_session.add(u2)
    await db_session.commit()
    h2 = {"Authorization": f"Bearer {create_access_token(u2.id, org.id)}"}
    assert (await client.delete(f"/api/v1/reports/{r.id}/share-links/{link_id}",
                                headers=h2)).status_code == 403

@pytest.mark.asyncio
async def test_the_payload_carries_the_pages_authored_interaction_mode(
        client, auth_headers, db_session, two_orgs, salesfile):
    """A page set to an automatic action mode keeps that mode through the link.

    The mode lives inside `mobile_layout`, which the public payload does not
    publish -- so a viewer received no mode at all and the page fell back to
    manual. Every widget then obeyed its own per-widget setting, which is the
    exact opposite of what an automatic mode means: the author's page-level
    choice worked in the builder and died the moment the link was shared."""
    ds, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    page = (await db_session.execute(
        select(ReportPage).where(ReportPage.report_id == r.id))).scalars().first()
    page.mobile_layout = {"interaction_mode": "twoway", "hidden": []}
    await db_session.commit()

    resp = await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 7},
                             headers=auth_headers["a"])
    token = resp.json()["token"]

    body = (await client.get(f"/api/v1/shared/{token}")).json()
    assert body["pages"][0]["interaction_mode"] == "twoway"


@pytest.mark.asyncio
async def test_a_page_with_no_mode_publishes_manual_not_nothing(
        client, auth_headers, db_session, two_orgs, salesfile):
    """The field is always present, so the viewer never has to guess.

    An absent key and the string "manual" mean the same thing to a careful
    reader and different things to code that treats undefined as "unknown"."""
    _, r, _w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    resp = await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 7},
                             headers=auth_headers["a"])
    token = resp.json()["token"]

    body = (await client.get(f"/api/v1/shared/{token}")).json()
    assert body["pages"][0]["interaction_mode"] == "manual"


@pytest.mark.asyncio
async def test_an_unknown_mode_is_published_as_manual(
        client, auth_headers, db_session, two_orgs, salesfile):
    """`mobile_layout` is author-written JSON, so it can hold anything.

    An unrecognised mode reaching the frontend union would become a filter
    rule nothing implements -- silently no interactions at all, rather than
    an error anyone can see."""
    ds, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    page = (await db_session.execute(
        select(ReportPage).where(ReportPage.report_id == r.id))).scalars().first()
    page.mobile_layout = {"interaction_mode": "sideways"}
    await db_session.commit()

    resp = await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 7},
                             headers=auth_headers["a"])
    token = resp.json()["token"]

    body = (await client.get(f"/api/v1/shared/{token}")).json()
    assert body["pages"][0]["interaction_mode"] == "manual"


@pytest.mark.asyncio
async def test_the_payload_publishes_geography_classifications_only(
        client, auth_headers, db_session, two_orgs, salesfile):
    """A column classified as geography draws its own boundaries for a reader.

    The classification lives in the dataset's `column_meta`, which a viewer
    never sees -- so without publishing it a shared link drew a world map for a
    column the author had told the product was governorates. Publishing the
    WHOLE blob is not the fix: `column_meta` also carries `__prep_steps__` and
    `__derived_from__`, the recipe. Only the derived mapping crosses."""
    ds, r, _w = await _fixture(db_session, two_orgs["a"]["org"].id and two_orgs["a"]["org"], salesfile)
    ds.column_meta = {
        "region": {"role": "geography", "boundary_set_id": 9},
        "amount": {"role": "measure"},
        "__prep_steps__": [{"op": "secret_recipe"}],
    }
    await db_session.commit()

    resp = await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 7},
                             headers=auth_headers["a"])
    token = resp.json()["token"]
    body = (await client.get(f"/api/v1/shared/{token}")).json()

    assert body["geography"] == {"region": 9}
    # The recipe stays behind.
    assert "__prep_steps__" not in str(body.get("geography"))
    assert "column_meta" not in body


@pytest.mark.asyncio
async def test_the_acceptance_criteria_hold_on_the_share_link_too(client, auth_headers, db_session, two_orgs, tmp_path):
    """MASTER_PLAN Part IV criterion 11 -- criteria 3 and 4 on the anonymous
    surface: the population travels with the result, and a summed year saved
    into a report is refused to a guest with the same reason as in the builder."""
    p = tmp_path / "y.csv"
    pd.DataFrame({"region": ["US", "US", "EU"], "year": [2024, 2025, 2025], "amount": [1.0, 2.0, 3.0]}).to_csv(p, index=False)
    org = two_orgs["a"]["org"]
    ds = Dataset(name="Y", filename=str(p), org_id=org.id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    r = Report(name="R", dataset_id=ds.id, org_id=org.id)
    db_session.add(r)
    await db_session.flush()
    page = ReportPage(report_id=r.id, name="P1", position=0)
    db_session.add(page)
    await db_session.flush()
    good = ReportWidget(page_id=page.id, widget_type="bar",
                        config={"dimension": "region", "measure": "amount", "aggregation": "sum"})
    bad = ReportWidget(page_id=page.id, widget_type="bar",
                       config={"dimension": "region", "measure": "year", "aggregation": "sum"})
    db_session.add_all([good, bad])
    await db_session.commit()

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={"expires_days": 7},
                               headers=auth_headers["a"])).json()["token"]
    ok = await client.post(f"/api/v1/shared/{token}/widget-data/{good.id}")
    assert ok.status_code == 200 and ok.json()["rows_scanned"] == 3
    assert "truncation" in ok.json()
    refused = await client.post(f"/api/v1/shared/{token}/widget-data/{bad.id}")
    assert refused.status_code == 422
    assert refused.json()["code"] == "semantic_veto" and "adds up years" in refused.json()["detail"]
