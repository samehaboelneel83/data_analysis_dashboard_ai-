"""Task E1: embedded reports with host-signed JWTs -- "never trust the browser
with scope". Admin CRUD (mint/list/enable-disable), the token contract (HS256,
config secret, exp required <=24h, tampered/expired/oversized-TTL all reject),
cross-org/disabled 404, origin allowlist, filters/viewer_email carried ONLY by
the verified token (never the browser), the embed rate-limit bucket, and --
the load-bearing security property -- an embed NEVER exposes more than its
CREATOR's own row-level-security/column-security slice, exactly like a
ShareLink guest (routers/shared.py `_resolve_identity`)."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from jose import jwt
from sqlalchemy import select

from app.core.security import ALGORITHM, create_access_token, hash_password
from app.models.models import (
    ColumnSecurityRule, Dataset, DatasetColumn, EmbedConfig, PageRoleVisibility, Report, ReportPage, ReportWidget,
    Role, RowSecurityRule, User,
)
from app.services.secrets import decrypt_value


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({
        "region": ["US", "US", "EU"],
        "amount": [10.0, 20.0, 40.0],
        "owner": ["a@example.com", "b@example.com", "a@example.com"],
    }).to_csv(p, index=False)
    return str(p)


async def _fixture(db, org, path, default_filter_expr=None):
    ds = Dataset(name="S", filename=path, org_id=org.id, mode="import", default_filter_expr=default_filter_expr)
    db.add(ds)
    await db.flush()
    for c in ("region", "amount", "owner"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    r = Report(name="Embedded R", dataset_id=ds.id, org_id=org.id)
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


async def _restricted_user(db, org, ds, filter_expr=None, denied_columns=None, *, report=None):
    """A non-admin user, row/column-restricted on `ds`, plus bearer headers for
    them -- used to prove an embed can never exceed its CREATOR's own slice.

    `report` makes this user that report's `created_by`: every caller of this
    helper immediately mints an embed config AS this user, which needs 'edit'
    capability (routers/embed.py). An unowned report (created_by=None, as
    `_fixture` leaves it) resolves a non-admin to 'view' at best
    (core/capability.py `_resolve`'s "UNOWNED reports" rule) -- correct
    product behaviour, but it means a restricted user can never be the
    embed's creator unless something makes the report theirs first."""
    role = Role(org_id=org.id, name="restricted", is_org_admin=False)
    db.add(role)
    await db.flush()
    if filter_expr:
        db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr=filter_expr))
    if denied_columns:
        db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=denied_columns))
    user = User(org_id=org.id, role_id=role.id, email="restricted@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    if report is not None:
        report.created_by = user.id
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


def _host_token(secret: str, cfg_id: int, *, exp_delta=timedelta(hours=1), filters=None,
                viewer_email=None, viewer_org=None, no_exp=False):
    payload = {"cfg": cfg_id}
    if not no_exp:
        payload["exp"] = datetime.now(timezone.utc) + exp_delta
    if filters is not None:
        payload["filters"] = filters
    if viewer_email is not None:
        payload["viewer_email"] = viewer_email
    if viewer_org is not None:
        payload["viewer_org"] = viewer_org
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


async def _mint_config(client, headers, report_id, name="default", allowed_origins=None):
    resp = await client.post(f"/api/v1/reports/{report_id}/embed-configs",
                             json={"name": name, "allowed_origins": allowed_origins or []}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _session_token(client, secret, cfg_id, **kw):
    token = _host_token(secret, cfg_id, **kw)
    body = (await client.get(f"/api/v1/embed/report?token={token}")).json()
    return body["embed_session_token"]


@pytest.mark.asyncio
async def test_valid_token_renders_structure_and_widget_data(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    secret = cfg["secret"]
    token = _host_token(secret, cfg["id"])

    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Embedded R"
    assert body["pages"][0]["widgets"][0]["id"] == w.id
    session_token = body["embed_session_token"]
    assert session_token

    wd = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert wd.status_code == 200, wd.text
    assert {x["name"]: x["value"] for x in wd.json()["rows"]} == {"US": 30.0, "EU": 40.0}


@pytest.mark.asyncio
async def test_tampered_signature_404(client, auth_headers, db_session, two_orgs, salesfile):
    """Enumeration resistance: a bad signature 404s -- the SAME status a
    nonexistent config gets -- so a prober can't use 401-vs-404 to learn
    whether a guessed cfg id exists."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token("wrong-secret-entirely", cfg["id"])
    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_expired_401(client, auth_headers, db_session, two_orgs, salesfile):
    """Expiry alone stays 401 -- distinguishable from 404 only by someone who
    already holds a validly-signed token, so it leaks nothing to a prober."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token(cfg["secret"], cfg["id"], exp_delta=timedelta(minutes=-1))
    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_exp_404(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token(cfg["secret"], cfg["id"], no_exp=True)
    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_exp_more_than_24h_ahead_rejected(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token(cfg["secret"], cfg["id"], exp_delta=timedelta(hours=25))
    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 401

    # a token within the 24h ceiling still works
    ok_token = _host_token(cfg["secret"], cfg["id"], exp_delta=timedelta(hours=23))
    resp2 = await client.get(f"/api/v1/embed/report?token={ok_token}")
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_disabled_config_404(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token(cfg["secret"], cfg["id"])

    await client.patch(f"/api/v1/reports/{r.id}/embed-configs/{cfg['id']}",
                       json={"enabled": False}, headers=auth_headers["a"])
    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_config_404(client, auth_headers, db_session, two_orgs, salesfile):
    """A config whose report/org was deleted out from under it (or which never
    matched a live report in its own org) 404s -- never leaks which failed."""
    org_b = two_orgs["b"]["org"]
    _, r_a, w_a = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r_a.id)

    # Simulate a config pointing at a report belonging to a DIFFERENT org than
    # the config's own org_id (the invariant the endpoint's cross-check guards).
    row = await db_session.get(EmbedConfig, cfg["id"])
    row.org_id = org_b.id
    await db_session.commit()

    token = _host_token(cfg["secret"], cfg["id"])
    resp = await client.get(f"/api/v1/embed/report?token={token}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_filters_injected_value_pinned(client, auth_headers, db_session, two_orgs, salesfile):
    """Two different `filters` claims on the SAME widget produce different
    rows -- proof the token's filters are actually applied server-side."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    secret = cfg["secret"]

    session_us = await _session_token(client, secret, cfg["id"],
                                      filters=[{"column": "region", "op": "eq", "value": "US"}])
    wd_us = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                              headers={"Authorization": f"Bearer {session_us}"})
    assert {x["name"] for x in wd_us.json()["rows"]} == {"US"}

    session_eu = await _session_token(client, secret, cfg["id"],
                                      filters=[{"column": "region", "op": "eq", "value": "EU"}])
    wd_eu = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                              headers={"Authorization": f"Bearer {session_eu}"})
    assert {x["name"] for x in wd_eu.json()["rows"]} == {"EU"}


@pytest.mark.asyncio
async def test_viewer_email_expands_useremail(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    _, r, w = await _fixture(db_session, org, salesfile, default_filter_expr="`owner` == USEREMAIL()")
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"], viewer_email="a@example.com")
    wd = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert wd.status_code == 200, wd.text
    # owner==a@example.com rows are region US (10) and EU (40)
    assert {x["name"]: x["value"] for x in wd.json()["rows"]} == {"US": 10.0, "EU": 40.0}


@pytest.mark.asyncio
async def test_origin_mismatch_403(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id, allowed_origins=["https://good.example.com"])
    token = _host_token(cfg["secret"], cfg["id"])
    resp = await client.get(f"/api/v1/embed/report?token={token}",
                            headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403

    ok = await client.get(f"/api/v1/embed/report?token={token}",
                          headers={"Origin": "https://good.example.com"})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_browser_filter_params_ignored_value_pinned(client, auth_headers, db_session, two_orgs, salesfile):
    """The widget-data route never reads the request body/query string for
    scope -- a browser trying to widen its own view by adding filters gets
    exactly the token's rows, nothing else."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"],
                                         filters=[{"column": "region", "op": "eq", "value": "US"}])

    wd = await client.post(
        f"/api/v1/embed/widget-data/{w.id}?filters=[]",
        json={"config": {"filters": []}, "widget_type": "bar"},
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert wd.status_code == 200, wd.text
    assert {x["name"] for x in wd.json()["rows"]} == {"US"}


@pytest.mark.asyncio
async def test_secret_never_in_list_response(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    resp = await client.get(f"/api/v1/reports/{r.id}/embed-configs", headers=auth_headers["a"])
    assert resp.status_code == 200
    assert "secret" not in str(resp.json())
    assert cfg["secret"] not in str(resp.json())


@pytest.mark.asyncio
async def test_secret_encrypted_at_rest(db_session, auth_headers, client, two_orgs, salesfile):
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    row = await db_session.get(EmbedConfig, cfg["id"])
    assert row.secret_encrypted != cfg["secret"]
    assert row.secret_encrypted.startswith("enc:v2:")
    assert decrypt_value(row.secret_encrypted) == cfg["secret"]


@pytest.mark.asyncio
async def test_rate_limit_bucket_applied(client, auth_headers, db_session, two_orgs, salesfile, monkeypatch):
    from app.core import rate_limit as rl

    monkeypatch.setattr(rl, "is_test_mode", lambda: False)
    rl.reset_buckets()
    try:
        monkeypatch.setattr(rl.settings, "rate_limit_guest_requests_per_window", 1)
        monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
        monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1000)

        _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
        cfg = await _mint_config(client, auth_headers["a"], r.id)
        token = _host_token(cfg["secret"], cfg["id"])

        first = await client.get(f"/api/v1/embed/report?token={token}")
        assert first.status_code != 429
        second = await client.get(f"/api/v1/embed/report?token={token}")
        assert second.status_code == 429
        assert "Retry-After" in second.headers
    finally:
        rl.reset_buckets()


@pytest.mark.asyncio
async def test_embed_session_token_rejected_by_a_normal_authed_endpoint(
        client, auth_headers, db_session, two_orgs, salesfile):
    """The internal 15-min embed session token must never open anything besides
    the embed widget-data route -- it carries aud="embed", and
    decode_access_token never passes an audience, so python-jose refuses it."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"])

    resp = await client.get(f"/api/v1/reports/{r.id}", headers={"Authorization": f"Bearer {session_token}"})
    assert resp.status_code == 401


# ── The load-bearing security property: an embed never exceeds its creator's slice ──

@pytest.mark.asyncio
async def test_rls_dataset_embed_shows_only_creators_row_subset(client, db_session, two_orgs, salesfile):
    """A restricted creator's embed exposes exactly their RLS slice -- the
    anonymous host holder sees US rows only, because the CREATOR sees US rows
    only. Value-pinned: NOT all rows, exactly the subset."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    user, headers = await _restricted_user(db_session, org, ds, filter_expr="`region` == 'US'", report=r)
    cfg = await _mint_config(client, headers, r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"])

    wd = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert wd.status_code == 200, wd.text
    assert {x["name"]: x["value"] for x in wd.json()["rows"]} == {"US": 30.0}


@pytest.mark.asyncio
async def test_escalation_via_embed_token_is_dead(client, db_session, two_orgs, salesfile):
    """A row-restricted creator cannot use the host JWT's viewer_email/
    viewer_org to see more than their own RLS slice -- those only expand
    USEREMAIL()/ORGID() inside the dataset's OWN author expressions, they
    never substitute for the creator's role in RLS resolution."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    user, headers = await _restricted_user(db_session, org, ds, filter_expr="`region` == 'US'", report=r)
    cfg = await _mint_config(client, headers, r.id)
    # Claiming a different viewer identity does not widen the creator's own RLS slice.
    session_token = await _session_token(client, cfg["secret"], cfg["id"],
                                         viewer_email="somebody-else@example.com", viewer_org=999)

    wd = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert wd.status_code == 200, wd.text
    assert {x["name"]: x["value"] for x in wd.json()["rows"]} == {"US": 30.0}


@pytest.mark.asyncio
async def test_denied_columns_absent_from_embed(client, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    ds, r, _ = await _fixture(db_session, org, salesfile)
    user, headers = await _restricted_user(db_session, org, ds, denied_columns=["owner"], report=r)
    page = (await db_session.execute(
        select(ReportPage).where(ReportPage.report_id == r.id)
    )).scalars().one()
    table_widget = ReportWidget(page_id=page.id, widget_type="table",
                                config={"columns": ["region", "amount", "owner"]})
    db_session.add(table_widget)
    await db_session.commit()

    cfg = await _mint_config(client, headers, r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"])

    wd = await client.post(f"/api/v1/embed/widget-data/{table_widget.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert wd.status_code == 200, wd.text
    assert "owner" not in str(wd.json().get("columns", []))


@pytest.mark.asyncio
async def test_token_filters_compose_on_top_of_creator_rls(client, db_session, two_orgs, salesfile):
    """The token's own `filters` narrow the creator-scoped result further --
    they never widen it back out."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    user, headers = await _restricted_user(db_session, org, ds, filter_expr="`region` == 'US'", report=r)
    cfg = await _mint_config(client, headers, r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"],
                                         filters=[{"column": "amount", "op": "gt", "value": 15}])

    wd = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert wd.status_code == 200, wd.text
    # region==US AND amount>15 -> only the 20.0 row survives
    assert {x["name"]: x["value"] for x in wd.json()["rows"]} == {"US": 20.0}


@pytest.mark.asyncio
async def test_admin_creator_still_sees_everything(client, auth_headers, db_session, two_orgs, salesfile):
    """Regression: an unrestricted (admin) creator's embed is unaffected --
    this is what every other test in this file already exercises, pinned
    explicitly here against the creator-resolution change."""
    _, r, w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    cfg = await _mint_config(client, auth_headers["a"], r.id)
    session_token = await _session_token(client, cfg["secret"], cfg["id"])
    wd = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert {x["name"]: x["value"] for x in wd.json()["rows"]} == {"US": 30.0, "EU": 40.0}


@pytest.mark.asyncio
async def test_page_role_visibility_parity_with_guest_links(client, db_session, two_orgs, salesfile):
    """A page role-restricted away from the CREATOR's role is absent from the
    embed report structure -- and its widgets don't resolve via widget-data
    either -- exactly the parity a ShareLink guest gets from
    shared.py's `visible_pages_for_creator`. An unrestricted page stays
    present."""
    org = two_orgs["a"]["org"]
    ds, r, w = await _fixture(db_session, org, salesfile)
    user, headers = await _restricted_user(db_session, org, ds, report=r)  # unrestricted RLS, restricted page below

    other_role = Role(org_id=org.id, name="other", is_org_admin=False)
    db_session.add(other_role)
    await db_session.flush()
    restricted_page = ReportPage(report_id=r.id, name="Execs Only", position=1)
    db_session.add(restricted_page)
    await db_session.flush()
    db_session.add(PageRoleVisibility(page_id=restricted_page.id, role_id=other_role.id))
    hidden_widget = ReportWidget(page_id=restricted_page.id, widget_type="bar",
                                 config={"dimension": "region", "measure": "amount", "aggregation": "sum"})
    db_session.add(hidden_widget)
    await db_session.commit()

    cfg = await _mint_config(client, headers, r.id)
    token = _host_token(cfg["secret"], cfg["id"])
    body = (await client.get(f"/api/v1/embed/report?token={token}")).json()

    page_names = {p["name"] for p in body["pages"]}
    assert page_names == {"P1"}          # the unrestricted page is present
    assert "Execs Only" not in page_names  # the role-restricted page is absent
    assert "secret" not in str(body)

    session_token = body["embed_session_token"]
    resp = await client.post(f"/api/v1/embed/widget-data/{hidden_widget.id}",
                             headers={"Authorization": f"Bearer {session_token}"})
    assert resp.status_code == 404

    # the unrestricted page's own widget still resolves normally
    ok = await client.post(f"/api/v1/embed/widget-data/{w.id}",
                           headers={"Authorization": f"Bearer {session_token}"})
    assert ok.status_code == 200

@pytest.mark.asyncio
async def test_the_embed_payload_carries_the_pages_interaction_mode(
        client, auth_headers, db_session, two_orgs, salesfile):
    """The embed reaches `_shape_page` through `visible_pages_for_creator`,
    not by calling it directly -- so the share-link test next door does not
    cover this route. Both surfaces had the same defect (a viewer received no
    mode and every page fell back to manual) and both are fixed by one shaper;
    a future refactor that gives the embed its own shaper would silently
    reintroduce it here alone."""
    _, r, _w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    page = (await db_session.execute(
        select(ReportPage).where(ReportPage.report_id == r.id))).scalars().first()
    page.mobile_layout = {"interaction_mode": "linked"}
    await db_session.commit()

    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token(cfg["secret"], cfg["id"])

    body = (await client.get(f"/api/v1/embed/report?token={token}")).json()
    assert body["pages"][0]["interaction_mode"] == "linked"


@pytest.mark.asyncio
async def test_the_embed_payload_publishes_geography_classifications(
        client, auth_headers, db_session, two_orgs, salesfile):
    """Same derived subset as the share link, through the other route.

    Both payloads are assembled separately, so a classification reaching one
    says nothing about the other -- and an embed is exactly the surface where
    nobody is watching."""
    ds, r, _w = await _fixture(db_session, two_orgs["a"]["org"], salesfile)
    ds.column_meta = {"region": {"role": "geography", "boundary_set_id": 4},
                      "__prep_steps__": [{"op": "recipe"}]}
    await db_session.commit()

    cfg = await _mint_config(client, auth_headers["a"], r.id)
    token = _host_token(cfg["secret"], cfg["id"])
    body = (await client.get(f"/api/v1/embed/report?token={token}")).json()

    assert body["geography"] == {"region": 4}
    assert "column_meta" not in body
