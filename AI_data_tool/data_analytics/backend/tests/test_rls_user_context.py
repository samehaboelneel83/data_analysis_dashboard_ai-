"""Dynamic user context in RLS: USEREMAIL()/USER()/USERID() (enterprise profiling).

One role-level rule like `owner == USEREMAIL()` scopes every user in that role to their
own rows, instead of needing a separate role and rule per user.
"""
import pandas as pd
import pytest

from app.core.rls import apply_user_context
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


# ── unit: safe substitution ───────────────────────────────────────────────────

def test_useremail_and_user_resolve_to_a_quoted_literal():
    assert apply_user_context("owner == USEREMAIL()", email="a@x.com", user_id=7) == "owner == 'a@x.com'"
    assert apply_user_context("owner == USER()", email="a@x.com", user_id=7) == "owner == 'a@x.com'"


def test_userid_resolves_to_an_int_literal():
    assert apply_user_context("owner_id == USERID()", email="a@x.com", user_id=7) == "owner_id == 7"


def test_an_email_with_a_quote_stays_one_literal():
    # The injection shape: a value carrying a quote must not break out of its literal.
    out = apply_user_context("owner == USEREMAIL()", email="o'brien@x.com", user_id=1)
    assert eval(out.split("==")[1]) == "o'brien@x.com"   # still just the string


def test_none_and_tokenless_expressions_pass_through():
    assert apply_user_context(None, email="a@x.com", user_id=1) is None
    assert apply_user_context("region == 'North'", email="a@x.com", user_id=1) == "region == 'North'"


# ── end-to-end: one rule, per-user rows ───────────────────────────────────────

async def _dataset(db, tmp_path, org_id, rows):
    p = tmp_path / "owned.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    ds = Dataset(name="Owned", org_id=org_id, filename=str(p))
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _user(db, org_id, role_id, email):
    u = User(org_id=org_id, role_id=role_id, email=email, password_hash=hash_password("pw"))
    db.add(u)
    await db.flush()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_one_rule_scopes_each_user_to_their_own_rows(client, db_session, two_orgs, tmp_path):
    org_id = two_orgs["a"]["org"].id
    ds = await _dataset(db_session, tmp_path, org_id, [
        {"owner": "alice@x.com", "sales": 100},
        {"owner": "bob@x.com", "sales": 200},
        {"owner": "alice@x.com", "sales": 50},
    ])
    role = Role(org_id=org_id, name="Owners", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="owner == USEREMAIL()"))
    alice = await _user(db_session, org_id, role.id, "alice@x.com")
    bob = await _user(db_session, org_id, role.id, "bob@x.com")
    await db_session.commit()

    q = {"config": {"dimension": "owner", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"}
    ra = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=q, headers=_headers(alice))
    rb = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=q, headers=_headers(bob))

    assert ra.status_code == 200 and rb.status_code == 200
    # Same role, same rule — but each user sees only their own rows.
    assert {r["name"] for r in ra.json()["rows"]} == {"alice@x.com"}
    assert sum(r["value"] for r in ra.json()["rows"]) == 150
    assert {r["name"] for r in rb.json()["rows"]} == {"bob@x.com"}
    assert sum(r["value"] for r in rb.json()["rows"]) == 200


@pytest.mark.asyncio
async def test_rls_rule_orgname_with_whitespace_still_scopes_rows(client, db_session, two_orgs, tmp_path):
    """resolve_rls_expr only bothers fetching org_name when its own preload
    check detects ORGNAME() in the rule text. That check must tolerate the
    same `ORGNAME ( )` whitespace the substitution regex tolerates, or
    org_name stays None, the token is left unexpanded, and the rule fails
    closed (zero rows) instead of scoping to this org."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, tmp_path, org.id, [
        {"org_name": org.name, "sales": 100},
        {"org_name": "Someone Else Inc", "sales": 200},
    ])
    role = Role(org_id=org.id, name="OrgScoped", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="org_name == ORGNAME ( )"))
    user = await _user(db_session, org.id, role.id, "orgname-ws@x.com")
    await db_session.commit()

    q = {"config": {"dimension": "org_name", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"}
    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=q, headers=_headers(user))

    assert resp.status_code == 200
    assert [r["value"] for r in resp.json()["rows"]] == [100]


@pytest.mark.asyncio
async def test_admin_can_create_a_rule_that_uses_user_tokens(client, db_session, two_orgs, auth_headers, tmp_path):
    org_id = two_orgs["a"]["org"].id
    ds = await _dataset(db_session, tmp_path, org_id, [{"owner": "a@x.com", "sales": 1}])
    r = await client.post("/api/v1/admin/row-security-rules",
                          json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id,
                                "filter_expr": "owner == USEREMAIL()"},
                          headers=auth_headers["a"])
    # The validator resolves the token against a placeholder identity, so a rule that
    # references a real column validates rather than erroring on an "unknown function".
    assert r.status_code in (200, 201), r.text
