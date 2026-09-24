import pandas as pd
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, DatasetColumn, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.flush()
    for col_name in rows[0].keys():
        dtype = "numeric" if isinstance(rows[0][col_name], (int, float)) else "string"
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col_name, dtype=dtype))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, email="restricted@example.com"):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(role)
    return role, user


def _headers_for(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_proposals_cover_email_and_org_columns(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"owner_email": "a@example.com", "org_id": 1, "team_name": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/rls-rules/auto-generate", json={"dataset_id": ds.id}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    proposals = {p["column"]: p for p in resp.json()["proposals"]}
    assert proposals["owner_email"]["expression"] == "`owner_email` == USEREMAIL()"
    assert proposals["owner_email"]["kind"] == "user_email"
    assert proposals["org_id"]["expression"] == "`org_id` == ORGID()"
    assert proposals["org_id"]["kind"] == "org_id"
    assert "sales" not in proposals
    # "team_name" doesn't match user/email/owner nor org/tenant/company -- no proposal.
    assert "team_name" not in proposals


async def test_semantic_type_email_proposes_useremail(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"contact": "a@example.com", "sales": 1}],
    )
    col = (await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id, DatasetColumn.name == "contact")
    )).scalar_one()
    col.semantic_type = "email"
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/rls-rules/auto-generate", json={"dataset_id": ds.id}, headers=auth_headers["a"],
    )

    proposals = {p["column"]: p for p in resp.json()["proposals"]}
    assert proposals["contact"]["expression"] == "`contact` == USEREMAIL()"


async def test_org_text_column_proposes_orgname(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"company_name": "Acme", "sales": 1}],
    )

    resp = await client.post(
        "/api/v1/admin/rls-rules/auto-generate", json={"dataset_id": ds.id}, headers=auth_headers["a"],
    )

    proposals = {p["column"]: p for p in resp.json()["proposals"]}
    assert proposals["company_name"]["expression"] == "`company_name` == ORGNAME()"
    assert proposals["company_name"]["kind"] == "org_name"


async def test_apply_creates_auto_generated_rule(client, db_session, two_orgs, auth_headers, tmp_path):
    role, _user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id)
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"owner_email": "a@example.com", "sales": 1}],
    )

    resp = await client.post(
        "/api/v1/admin/rls-rules/auto-generate",
        json={"dataset_id": ds.id, "role_id": role.id, "apply": True},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"]["auto_generated"] is True
    assert body["created"]["filter_expr"] == "`owner_email` == USEREMAIL()"
    row = (await db_session.execute(
        select(RowSecurityRule).where(RowSecurityRule.role_id == role.id, RowSecurityRule.dataset_id == ds.id)
    )).scalar_one()
    assert row.auto_generated is True


async def test_apply_is_idempotent_never_duplicates(client, db_session, two_orgs, auth_headers, tmp_path):
    role, _user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id)
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"owner_email": "a@example.com", "sales": 1}],
    )

    for _ in range(2):
        resp = await client.post(
            "/api/v1/admin/rls-rules/auto-generate",
            json={"dataset_id": ds.id, "role_id": role.id, "apply": True},
            headers=auth_headers["a"],
        )
        assert resp.status_code == 200

    rows = (await db_session.execute(
        select(RowSecurityRule).where(RowSecurityRule.role_id == role.id, RowSecurityRule.dataset_id == ds.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].filter_expr == "`owner_email` == USEREMAIL()"


async def test_edit_clears_auto_generated_flag_and_blocks_reapply(client, db_session, two_orgs, auth_headers, tmp_path):
    role, _user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id)
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"owner_email": "a@example.com", "sales": 1}],
    )
    rule = RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                            filter_expr="`owner_email` == USEREMAIL()", auto_generated=True)
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    edit_resp = await client.patch(
        f"/api/v1/admin/row-security-rules/{rule.id}",
        json={"filter_expr": "`owner_email` == USEREMAIL() and sales > 0"},
        headers=auth_headers["a"],
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["auto_generated"] is False

    reapply = await client.post(
        "/api/v1/admin/rls-rules/auto-generate",
        json={"dataset_id": ds.id, "role_id": role.id, "apply": True},
        headers=auth_headers["a"],
    )
    assert reapply.status_code == 200
    assert reapply.json()["created"] is None
    await db_session.refresh(rule)
    assert rule.filter_expr == "`owner_email` == USEREMAIL() and sales > 0"
    assert rule.auto_generated is False


async def test_generated_rule_actually_filters_base_frame(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"owner_email": "alice@example.com", "sales": 100},
         {"owner_email": "bob@example.com", "sales": 200}],
    )
    role, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, email="alice@example.com")

    apply_resp = await client.post(
        "/api/v1/admin/rls-rules/auto-generate",
        json={"dataset_id": ds.id, "role_id": role.id, "apply": True},
        headers=auth_headers["a"],
    )
    assert apply_resp.status_code == 200

    resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=_headers_for(user))

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    emails = {row[0] for row in body["rows"]}
    assert emails == {"alice@example.com"}


async def test_auto_generate_dataset_from_another_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["b"]["org"].id, [{"owner_email": "a@example.com", "sales": 1}],
    )

    resp = await client.post(
        "/api/v1/admin/rls-rules/auto-generate", json={"dataset_id": ds.id}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404
