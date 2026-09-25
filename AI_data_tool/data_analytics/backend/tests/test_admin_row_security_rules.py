import pandas as pd
from sqlalchemy import select
from app.models.models import Dataset, DatasetColumn, RowSecurityRule


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_directquery_dataset(db_session, org_id, columns=("region", "sales"), name="DQ Dataset"):
    ds = Dataset(name=name, org_id=org_id, mode="directquery", source_table="sales")
    db_session.add(ds)
    await db_session.flush()
    for col in columns:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype="string"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_create_rule_valid_expression(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == resp.json()["id"]))
    assert result.scalar_one() is not None


async def test_create_rule_invalid_expression_returns_400(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "not a valid expr((("},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.dataset_id == ds.id))
    assert result.scalar_one_or_none() is None


async def test_create_rule_with_dataset_from_another_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["b"]["org"].id, [{"region": "North", "sales": 100}],
    )

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_create_duplicate_rule_for_same_role_and_dataset_returns_400(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )
    db_session.add(RowSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'"))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'South'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_update_rule_cross_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["b"]["org"].id, [{"region": "North", "sales": 100}],
    )
    rule = RowSecurityRule(role_id=two_orgs["b"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    resp = await client.patch(
        f"/api/v1/admin/row-security-rules/{rule.id}", json={"filter_expr": "region == 'South'"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_create_rule_for_directquery_dataset_with_valid_expression(client, db_session, two_orgs, auth_headers):
    """A DirectQuery dataset has no file to sample -- validation must instead check
    the expression translates to SQL against the dataset's known DatasetColumn names."""
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == resp.json()["id"]))
    assert result.scalar_one() is not None


async def test_create_rule_for_directquery_dataset_rejects_untranslatable_expression(client, db_session, two_orgs, auth_headers):
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "SUM(sales) > 100"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.dataset_id == ds.id))
    assert result.scalar_one_or_none() is None


async def test_create_rule_for_directquery_dataset_rejects_unknown_column(client, db_session, two_orgs, auth_headers):
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "does_not_exist == 'x'"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_update_rule_for_directquery_dataset_with_valid_expression(client, db_session, two_orgs, auth_headers):
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id)
    rule = RowSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    resp = await client.patch(
        f"/api/v1/admin/row-security-rules/{rule.id}", json={"filter_expr": "region == 'South'"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    await db_session.refresh(rule)
    assert rule.filter_expr == "region == 'South'"


async def test_dataset_columns_expose_semantic_type(client, db_session, two_orgs, auth_headers):
    """S0b's codeless RLS builder pre-suggests email/user-ish columns from
    `semantic_type` -- it needs that field on the dataset GET response, which
    previously stopped at id/name/dtype/missing_pct/stats."""
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id, columns=("region", "sales"))
    email_col = next(c for c in (await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id, DatasetColumn.name == "region")
    )).scalars())
    email_col.semantic_type = "email"
    await db_session.commit()

    resp = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 200
    cols = {c["name"]: c["semantic_type"] for c in resp.json()["columns"]}
    assert cols["region"] == "email"
    assert cols["sales"] is None


async def test_delete_rule(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )
    rule = RowSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=ds.id, filter_expr="region == 'North'")
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    resp = await client.delete(f"/api/v1/admin/row-security-rules/{rule.id}", headers=auth_headers["a"])

    assert resp.status_code == 204
    result = await db_session.execute(select(RowSecurityRule).where(RowSecurityRule.id == rule.id))
    assert result.scalar_one_or_none() is None


async def test_an_rls_rule_cannot_call_a_defined_custom_function(client, db_session, two_orgs, auth_headers, tmp_path):
    """Proves the structural guarantee the design relies on: expansion
    (services/custom_functions.py) is wired only into apply_calculated_columns,
    never into apply_filter_expr/apply_rls_filter. So a filter expression
    calling a custom function fails exactly like calling any other
    undefined name -- a 400 at save time -- never a rule that silently means
    something different than what the admin who saved it, and who may no
    longer be able to edit the function, once wrote."""
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"revenue": 100, "cost": 40}], name="Sales",
    )
    ds.custom_functions = [{"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                            "expression": "(revenue - cost) / revenue"}]
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id,
              "filter_expr": "PROFIT_MARGIN(revenue, cost) > 0"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_a_rule_whose_dataset_is_in_another_org_is_not_this_orgs(client, db_session, two_orgs, auth_headers, tmp_path):
    """BUG-036. A seeder once bound org a's role to org b's dataset. Scoped by
    the role alone, org a's admin listed it (as a "Deleted dataset" -- the
    dataset is invisible to them), and could PATCH it, validating expressions
    against org b's data, or delete it. Both ends must be in the org."""
    from app.models.models import ColumnSecurityRule
    theirs = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["b"]["org"].id, [{"region": "North", "sales": 100}],
    )
    row = RowSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=theirs.id, filter_expr="region == 'North'")
    col = ColumnSecurityRule(role_id=two_orgs["a"]["role"].id, dataset_id=theirs.id, denied_columns=["sales"])
    db_session.add_all([row, col])
    await db_session.commit()

    h = auth_headers["a"]
    listed = (await client.get("/api/v1/admin/row-security-rules", headers=h)).json()
    assert row.id not in [r["id"] for r in listed]
    listed = (await client.get("/api/v1/admin/column-security-rules", headers=h)).json()
    assert col.id not in [r["id"] for r in listed]
    r = await client.patch(f"/api/v1/admin/row-security-rules/{row.id}",
                           json={"filter_expr": "secret_column > 0"}, headers=h)
    assert r.status_code == 404
    assert (await client.delete(f"/api/v1/admin/row-security-rules/{row.id}", headers=h)).status_code == 404
    assert (await client.delete(f"/api/v1/admin/column-security-rules/{col.id}", headers=h)).status_code == 404
