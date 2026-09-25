"""An aggregate is governed by its source's rules, applied at read time.

Rules are never copied (materialize refused to copy them, and was right:
copies drift, and aggregation can delete the rule's column). Instead the
two resolvers follow `aggregate_of_dataset_id` and hand back the SOURCE's
rule for the caller's role. The rule references grain columns, which exist
on the aggregate with the same names, so it applies unchanged.

The value test is the whole point: a restricted user reading the aggregate
sees only their rows and their totals. Sabotage the redirect and they see
everyone's -- that is what the test must catch.
"""
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.rls import resolve_denied_columns
from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn, Role,
                               RowSecurityRule, User)

BAR = {"widget_type": "bar",
       "config": {"dimension": "region", "measure": "amount_sum", "aggregation": "sum"},
       "calculated_columns": [], "parameters": {}}


async def _restricted_user(db_session, org, dataset, expr, denied=None):
    """Same seeding as `_restricted` below, but hands back the User itself
    (role eagerly loaded) for tests that call a resolver directly rather than
    going through the HTTP layer."""
    role = Role(org_id=org.id, name=f"R-{expr[:8]}", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{role.id}@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=dataset.id, filter_expr=expr))
    if denied:
        db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=dataset.id, denied_columns=denied))
    await db_session.commit()
    # A plain refresh() only reloads columns and would lazy-load `.role` on
    # first access -- fatal on an AsyncSession outside a greenlet. Re-fetch
    # with the relationship already attached instead.
    return (await db_session.execute(
        select(User).options(selectinload(User.role)).where(User.id == user.id)
    )).scalar_one()


async def _restricted(db_session, org, dataset, expr, denied=None):
    user = await _restricted_user(db_session, org, dataset, expr, denied)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest.fixture(params=["pandas", "duckdb"])
def engine(request, monkeypatch):
    """Both engines, because production reads an aggregate through DuckDB
    (every refresh writes a sidecar) and the first version of these tests
    only ever exercised pandas."""
    from app.core.config import settings
    from app.services import duck_agg
    from app.services.frame_cache import clear_frame_cache
    from app.services.widget_data import clear_widget_data_cache
    clear_widget_data_cache(); clear_frame_cache()
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param == "duckdb")
    seen = {"ran": False, "reason": "not consulted"}
    real = duck_agg.try_aggregate

    def _spy(*a, **kw):
        frame, reason = real(*a, **kw)
        seen["ran"] = frame is not None
        seen["reason"] = reason
        return frame, reason
    monkeypatch.setattr(duck_agg, "try_aggregate", _spy)
    seen["name"] = request.param
    yield seen
    clear_widget_data_cache(); clear_frame_cache()


@pytest.fixture
async def source_and_aggregate(db_session, two_orgs, tmp_path, engine):
    """A DirectQuery source (rules live here) and an aggregate file over
    tenant x region -- the file is what a refresh would have written."""
    org = two_orgs["a"]["org"]
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders")
    db_session.add(src)
    await db_session.flush()
    for c in ("tenant", "region", "amount"):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype="categorical"))
    path = tmp_path / "agg.csv"
    pd.DataFrame([
        {"tenant": "acme", "region": "N", "amount_sum": 10.0, "row_count": 2},
        {"tenant": "acme", "region": "S", "amount_sum": 20.0, "row_count": 3},
        {"tenant": "globex", "region": "N", "amount_sum": 99.0, "row_count": 9},
    ]).to_csv(path, index=False)
    if engine["name"] == "duckdb":
        from app.services.frame_cache import write_parquet_sidecar
        assert write_parquet_sidecar(str(path)) is True
    agg = Dataset(name="orders by tenant/region", org_id=org.id, mode="import", filename=str(path),
                  aggregate_of_dataset_id=src.id,
                  aggregate_spec={"grain": ["tenant", "region"],
                                  "measures": [{"column": "amount", "agg": "sum", "name": "amount_sum"}]})
    db_session.add(agg)
    await db_session.flush()
    for c in ("tenant", "region", "amount_sum", "row_count"):
        db_session.add(DatasetColumn(dataset_id=agg.id, name=c, dtype="categorical"))
    await db_session.commit()
    return org, src, agg


@pytest.mark.asyncio
async def test_a_restricted_user_sees_only_their_tenant_on_the_aggregate(
        client, db_session, two_orgs, source_and_aggregate, engine):
    org, src, agg = source_and_aggregate
    headers = await _restricted(db_session, org, src, "tenant == 'acme'")
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    assert r.status_code == 200, r.text
    if engine["name"] == "duckdb":
        # "tenant == 'acme'" is a plain equality against a real grain column,
        # and neither the dimension nor the measure is denied -- exactly the
        # shape duck_agg.plan() accepts, so production must answer this one
        # through DuckDB, not fall back to pandas.
        assert engine["ran"], engine["reason"]
    rows = {x["name"]: x["value"] for x in r.json()["rows"]}
    assert rows == {"N": 10.0, "S": 20.0}, rows        # globex's 99 never appears
    assert r.json()["total"] == 2


@pytest.mark.asyncio
async def test_an_admin_sees_everything(client, auth_headers, source_and_aggregate, engine):
    _, _, agg = source_and_aggregate
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=auth_headers["a"])
    assert r.status_code == 200
    if engine["name"] == "duckdb":
        # No RLS rule at all for an org-admin, no denied columns -- the plain
        # dimension+measure shape DuckDB was built for.
        assert engine["ran"], engine["reason"]
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"N": 109.0, "S": 20.0}


@pytest.mark.asyncio
async def test_a_denied_source_column_denies_the_measures_built_on_it(
        client, db_session, source_and_aggregate, engine):
    """A role that may not see `amount` may not see `amount_sum` either;
    `row_count` stays. `resolve_denied_columns` is checked directly so the
    behaviour is pinned at the source of truth, not just inferred from the
    HTTP response's shape -- {"name", "value"} rows would pass a weaker
    'amount_sum not in x' check for ANY response, denied or not."""
    org, src, agg = source_and_aggregate
    user = await _restricted_user(db_session, org, src, "tenant == 'acme'", denied=["amount"])
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    assert set(await resolve_denied_columns(db_session, user, agg.id)) == {"amount", "amount_sum"}

    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    # `amount_sum` is dropped from the frame before the widget ever sees it, so
    # the requested measure column doesn't exist; aggregation="sum" over an
    # absent measure falls back to counting rows per group (existing,
    # unrelated widget_data.py behaviour -- see the grouped-series branch) --
    # it never reveals the withheld sums, and the outcome is deterministic.
    assert r.status_code == 200, r.text
    if engine["name"] == "duckdb":
        # The widget's own measure IS the denied column: duck_agg.plan()
        # validates "amount_sum" against the VISIBLE columns only (denied ones
        # excluded), finds it missing and declines with "measure 'amount_sum'
        # is not a real column" -- the same refusal-by-absence the pandas path
        # reaches after dropping it. A correct decline, not a gap; asserted so
        # a future widening of the gate has to look at this line.
        assert not engine["ran"], (
            f"expected DuckDB to decline on a denied measure column, but it ran ({engine['reason']!r})")
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"N": 1, "S": 1}, r.json()

    count_widget = dict(BAR, config={"dimension": "region", "measure": "row_count", "aggregation": "sum"})
    r2 = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=count_widget, headers=headers)
    assert r2.status_code == 200, r2.text
    if engine["name"] == "duckdb":
        # row_count is not denied and not derived from the denied `amount` --
        # eligible again once the widget stops asking for the withheld sum.
        assert engine["ran"], engine["reason"]
    assert {x["name"]: x["value"] for x in r2.json()["rows"]} == {"N": 2, "S": 3}


@pytest.mark.asyncio
async def test_a_rule_the_grain_cannot_express_fails_closed(
        client, db_session, source_and_aggregate, engine):
    """A rule added to the source later, on a column the aggregate lacks:
    zero rows for that role, never everyone's rows."""
    org, src, agg = source_and_aggregate
    headers = await _restricted(db_session, org, src, "product == 'widget'")
    r = await client.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    assert r.status_code == 200, r.text
    if engine["name"] == "duckdb":
        # "product" isn't a column of the aggregate file at all (the grain is
        # tenant/region), so translate_filter_expr_null_safe raises on the
        # unknown column and the whole widget declines to pandas before
        # duck_agg is ever consulted -- the same "fails closed" answer, not
        # produced by DuckDB. Documented rather than asserted as a pushdown win.
        assert not engine["ran"], (
            f"expected DuckDB to decline (unknown grain column), but it ran ({engine['reason']!r})")
    assert r.json()["rows"] == []


@pytest.mark.asyncio
async def test_admin_refuses_a_row_rule_saved_directly_on_the_aggregate(
        client, db_session, auth_headers, source_and_aggregate):
    """A rule saved on the aggregate would sit there, inert: both resolvers
    redirect past the aggregate to its source before ever looking a rule up
    (core/rls.py). Refuse at creation, naming the dataset it belongs on."""
    org, src, agg = source_and_aggregate
    role = Role(org_id=org.id, name="Some-Role", is_org_admin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    r = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": role.id, "dataset_id": agg.id, "filter_expr": "tenant == 'acme'"},
        headers=auth_headers["a"],
    )
    assert r.status_code == 400, r.text
    assert str(src.id) in r.json()["detail"]


@pytest.mark.asyncio
async def test_admin_refuses_a_column_rule_saved_directly_on_the_aggregate(
        client, db_session, auth_headers, source_and_aggregate):
    org, src, agg = source_and_aggregate
    role = Role(org_id=org.id, name="Some-Role-2", is_org_admin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    r = await client.post(
        "/api/v1/admin/column-security-rules",
        json={"role_id": role.id, "dataset_id": agg.id, "denied_columns": ["amount_sum"]},
        headers=auth_headers["a"],
    )
    assert r.status_code == 400, r.text
    assert str(src.id) in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_governed_source_makes_the_aggregate_governed_too(
        client, db_session, auth_headers, source_and_aggregate):
    """`_dataset_has_security` backs auto_private and the materialize refusal.
    Both must see through the aggregate to its source -- otherwise a governed
    aggregate reads as unprotected, materialize snapshots it rule-free, and
    auto_private never triggers on it."""
    from app.routers.datasets import _dataset_has_security

    org, src, agg = source_and_aggregate
    role = Role(org_id=org.id, name="Governed-Role", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=src.id, filter_expr="tenant == 'acme'"))
    await db_session.commit()

    assert await _dataset_has_security(db_session, agg.id) is True

    r = await client.post(
        f"/api/v1/datasets/{agg.id}/materialize",
        json={"name": "Snapshot", "description": "", "steps": []},
        headers=auth_headers["a"],
    )
    assert r.status_code == 403, r.text
    assert "security rules" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_broken_aggregate_spec_fails_closed_never_200(db_session, source_and_aggregate, engine):
    """A null/malformed `aggregate_spec` must refuse the read outright, never
    silently skip the measure-expansion (fail OPEN) and serve `amount_sum`
    unfiltered to a role that has `amount` denied on the source.

    Uses a raw client with `raise_app_exceptions=False` (the shared `client`
    fixture lets httpx re-raise an unhandled exception instead of turning it
    into a response) so the real production behaviour -- Starlette's default
    500 -- is what gets asserted on, not a Python exception escaping the test.
    """
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.main import app

    org, src, agg = source_and_aggregate
    agg.aggregate_spec = None
    await db_session.commit()
    headers = await _restricted(db_session, org, src, "tenant == 'acme'")

    async def _override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(f"/api/v1/datasets/{agg.id}/widget-data", json=BAR, headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 500, r.text
    # `resolve_denied_columns` raises on the broken spec before the widget
    # path ever reaches `duck_agg` (its RuntimeError fires ahead of the
    # DuckDB gate on both engines) -- so DuckDB is never even consulted here.
    assert not engine["ran"]


@pytest.mark.asyncio
async def test_resolve_denied_columns_raises_on_a_broken_aggregate_spec(
        db_session, source_and_aggregate):
    org, src, agg = source_and_aggregate
    agg.aggregate_spec = None
    await db_session.commit()
    user = await _restricted_user(db_session, org, src, "tenant == 'acme'")

    with pytest.raises(RuntimeError):
        await resolve_denied_columns(db_session, user, agg.id)


@pytest.mark.asyncio
async def test_admin_refuses_auto_generated_rules_on_the_aggregate(
        client, db_session, auth_headers, source_and_aggregate):
    """auto-generate is a THIRD row-rule creation path (besides the plain
    create endpoint) -- it must refuse the aggregate too, or a proposal built
    from a grain column (`tenant` matches the org-ish heuristic) writes an
    inert RowSecurityRule straight onto the aggregate."""
    from app.models.models import RowSecurityRule

    org, src, agg = source_and_aggregate
    role = Role(org_id=org.id, name="Auto-Gen-Role", is_org_admin=False)
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    r = await client.post(
        "/api/v1/admin/rls-rules/auto-generate",
        json={"dataset_id": agg.id, "role_id": role.id, "apply": True},
        headers=auth_headers["a"],
    )
    assert r.status_code == 400, r.text
    assert str(src.id) in r.json()["detail"]

    rows = (await db_session.execute(
        select(RowSecurityRule).where(RowSecurityRule.dataset_id == agg.id)
    )).scalars().all()
    assert rows == []
