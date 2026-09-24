"""S3: in-org sharing identity. An AUTHENTICATED IN-ORG viewer who follows a
share link resolves RLS + author-expression tokens as THEMSELVES, not the
link's creator -- the creator-only identity (test_share_links.py) stays the
rule for anonymous callers and callers from a different org."""
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (
    Dataset, DatasetColumn, PageRoleVisibility, Report, ReportPage, ReportWidget,
    Role, RowSecurityRule, User,
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
    return ds, r, page, w


async def _restricted_user(db, org, ds, *, region: str, email: str, report=None) -> tuple[User, dict]:
    """`report` makes this user that report's `created_by` -- needed only when
    this user is about to mint the share link themselves (POST .../share-links
    requires 'edit', which an unowned report never gives a non-admin; see
    core/capability.py _resolve's "UNOWNED reports" rule). A user who only
    ever VIEWS someone else's link should not pass it."""
    role = Role(org_id=org.id, name=f"role-{email}", is_org_admin=False)
    db.add(role)
    await db.flush()
    db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr=f"`region` == '{region}'"))
    user = User(org_id=org.id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    if report is not None:
        report.created_by = user.id
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}
    return user, headers


@pytest.mark.asyncio
async def test_two_org_viewers_of_the_same_link_see_different_rows(client, auth_headers, db_session, two_orgs, salesfile):
    """The headline S3 case: one link, two authenticated in-org viewers, each
    sees their OWN row-security slice -- not each other's, and not the
    creator's (the creator here is the org admin, unrestricted)."""
    org = two_orgs["a"]["org"]
    ds, r, page, w = await _fixture(db_session, org, salesfile)
    _, us_headers = await _restricted_user(db_session, org, ds, region="US", email="us@example.com")
    _, eu_headers = await _restricted_user(db_session, org, ds, region="EU", email="eu@example.com")

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]

    us_resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}", headers=us_headers)
    eu_resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}", headers=eu_headers)

    assert {x["name"] for x in us_resp.json()["rows"]} == {"US"}
    assert {x["name"] for x in eu_resp.json()["rows"]} == {"EU"}


@pytest.mark.asyncio
async def test_in_org_viewer_overrides_creators_own_slice(client, db_session, two_orgs, salesfile):
    """The creator sees US only (their own RLS); an in-org viewer restricted
    to EU sees EU only through the SAME link -- proving the resolution really
    switched identity rather than just widening the creator's own result."""
    org = two_orgs["a"]["org"]
    ds, r, page, w = await _fixture(db_session, org, salesfile)
    creator, creator_headers = await _restricted_user(db_session, org, ds, region="US", email="creator@example.com", report=r)
    _, eu_headers = await _restricted_user(db_session, org, ds, region="EU", email="eu2@example.com")

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=creator_headers)).json()["token"]

    anon_resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}")
    eu_resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}", headers=eu_headers)

    assert {x["name"] for x in anon_resp.json()["rows"]} == {"US"}  # anonymous keeps creator semantics
    assert {x["name"] for x in eu_resp.json()["rows"]} == {"EU"}    # in-org viewer overrides it


@pytest.mark.asyncio
async def test_cross_org_authenticated_caller_keeps_creator_semantics(client, auth_headers, db_session, two_orgs, salesfile):
    """A caller authenticated into a DIFFERENT org gets the creator's slice,
    same as anonymous -- their own identity has no bearing on this org's data."""
    org_a = two_orgs["a"]["org"]
    ds, r, page, w = await _fixture(db_session, org_a, salesfile)
    token = (await client.post(f"/api/v1/reports/{r.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]

    resp = await client.post(f"/api/v1/shared/{token}/widget-data/{w.id}", headers=auth_headers["b"])
    assert resp.status_code == 200
    assert {x["name"]: x["value"] for x in resp.json()["rows"]} == {"US": 30.0, "EU": 40.0}  # org A admin: unrestricted


@pytest.mark.asyncio
async def test_bogus_bearer_on_shared_routes_degrades_to_anonymous_not_401(client):
    """GET /shared/{token} (the report-shape route) accepts the same optional
    bearer without ever 401ing -- a stale/garbage token on that route must
    fall back to anonymous rendering, not break the page. The path token
    itself is bogus too here, so the request still 404s -- but via the
    normal "link not found" branch, never a 401 from the bearer."""
    resp = await client.get("/api/v1/shared/definitely-bogus", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pinned_snapshot_role_restriction_survives_live_page_deletion(
    client, db_session, two_orgs, salesfile,
):
    """S3 snapshot edge case: a page restricted to a role at PIN time must
    stay restricted after the live page (and its cascade-deleted
    PageRoleVisibility rows) is gone -- the frozen snapshot copy is the
    source of truth for a pinned link, never a live lookup."""
    org = two_orgs["a"]["org"]
    ds, r, page, w = await _fixture(db_session, org, salesfile)

    # The creator holds a role that is NOT in the page's allowed set --
    # so the page is invisible to them from the moment it's restricted.
    creator_role = Role(org_id=org.id, name="creator-role", is_org_admin=False)
    other_role = Role(org_id=org.id, name="other-role", is_org_admin=False)
    db_session.add_all([creator_role, other_role])
    await db_session.flush()
    creator = User(org_id=org.id, role_id=creator_role.id, email="pinner@example.com",
                  password_hash=hash_password("pw"))
    db_session.add(creator)
    await db_session.flush()
    # POST .../share-links needs 'edit'; an unowned report caps a non-admin at
    # 'view' (core/capability.py _resolve's "UNOWNED reports" rule), and this
    # test's whole point is that THIS restricted user pins the link.
    r.created_by = creator.id
    db_session.add(PageRoleVisibility(page_id=page.id, role_id=other_role.id))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(creator.id, org.id)}"}

    token = (await client.post(f"/api/v1/reports/{r.id}/share-links",
                               json={"pinned": True}, headers=headers)).json()["token"]

    before = (await client.get(f"/api/v1/shared/{token}")).json()
    assert before["pages"] == []  # restricted from the start

    # Simulate the live page vanishing along with its PageRoleVisibility rows
    # (ON DELETE CASCADE) -- exactly the edge case the ledger tracked.
    from sqlalchemy import delete
    await db_session.execute(delete(PageRoleVisibility).where(PageRoleVisibility.page_id == page.id))
    await db_session.execute(delete(ReportWidget).where(ReportWidget.page_id == page.id))
    await db_session.execute(delete(ReportPage).where(ReportPage.id == page.id))
    await db_session.commit()

    after = (await client.get(f"/api/v1/shared/{token}")).json()
    assert after["pages"] == []  # still restricted -- read from the frozen snapshot, not a live (now-empty) lookup
