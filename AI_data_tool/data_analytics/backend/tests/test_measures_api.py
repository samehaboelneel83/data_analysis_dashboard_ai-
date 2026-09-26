"""Measures CRUD + preview API, and the DirectQuery rejection.

Uses the router-test fixtures from conftest: `client`, `db_session`, `two_orgs`
(a dict keyed "a"/"b"), and `auth_headers` (bearer headers per org). asyncio_mode
is auto, so no decorators are needed.
"""
import pandas as pd

from app.models.models import Dataset, DatasetColumn


async def _make_dataset(db_session, org_id, tmp_path, mode="import", name="ds"):
    """Create a dataset the way upload does — including DatasetColumn rows, which the
    measure-name collision check queries."""
    path = tmp_path / f"{name}.csv"
    pd.DataFrame([
        {"region": "East", "sales": 100, "profit": 10},
        {"region": "West", "sales": 300, "profit": 60},
    ]).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, mode=mode,
                 row_count=2, col_count=3)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    for col, dtype in (("region", "categorical"), ("sales", "numeric"), ("profit", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype, missing_pct=0, stats={}))
    await db_session.commit()
    return ds


async def test_measures_default_to_an_empty_list(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.get(f"/api/v1/datasets/{ds.id}/measures", headers=auth_headers["a"])

    assert r.status_code == 200
    assert r.json() == []


async def test_save_then_list_roundtrips_a_measure(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    payload = {"name": "Sales Pct", "expression": "SUM(sales) / TOTAL(SUM(sales)) * 100"}

    saved = await client.post(f"/api/v1/datasets/{ds.id}/measures", json=payload, headers=auth_headers["a"])
    listed = await client.get(f"/api/v1/datasets/{ds.id}/measures", headers=auth_headers["a"])

    assert saved.status_code == 200
    assert [m["name"] for m in listed.json()] == ["Sales Pct"]


async def test_saving_the_same_name_replaces_rather_than_duplicates(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.post(f"/api/v1/datasets/{ds.id}/measures",
                      json={"name": "M", "expression": "SUM(sales)"}, headers=auth_headers["a"])

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures",
                          json={"name": "M", "expression": "SUM(profit)"}, headers=auth_headers["a"])

    assert len(r.json()) == 1
    assert r.json()[0]["expression"] == "SUM(profit)"


async def test_delete_removes_a_measure(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.post(f"/api/v1/datasets/{ds.id}/measures",
                      json={"name": "M", "expression": "SUM(sales)"}, headers=auth_headers["a"])

    r = await client.delete(f"/api/v1/datasets/{ds.id}/measures/M", headers=auth_headers["a"])

    assert r.status_code == 200
    assert r.json() == []


async def test_measure_name_colliding_with_a_real_column_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    """A collision would make the measure unreachable — shape_series resolves real
    columns first — so it is rejected at save time rather than silently ignored."""
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures",
                          json={"name": "sales", "expression": "SUM(sales)"}, headers=auth_headers["a"])

    assert r.status_code == 400
    assert "column" in r.json()["detail"].lower()


async def test_measure_name_colliding_with_a_custom_function_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    """The name-collision rule must run both directions: validate_custom_function_def
    already rejects a new custom function colliding with an existing measure, so a new
    measure colliding with an existing custom function must be rejected too -- otherwise
    the same naming ambiguity the rule exists to prevent can be recreated the other way."""
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    ds.custom_functions = [{"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                            "expression": "(revenue - cost) / revenue"}]
    await db_session.commit()

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures",
                          json={"name": "PROFIT_MARGIN", "expression": "SUM(sales)"}, headers=auth_headers["a"])

    assert r.status_code == 400
    assert "custom function" in r.json()["detail"].lower()


async def test_unsafe_measure_expression_is_rejected_at_save_time(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures",
                          json={"name": "Bad", "expression": "SUM(sales.values)"}, headers=auth_headers["a"])

    assert r.status_code == 400


async def test_measure_referencing_another_measure_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    """Measure-on-measure needs dependency ordering and cycle detection; until that
    exists the reference is rejected rather than evaluating to a NameError at render."""
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.post(f"/api/v1/datasets/{ds.id}/measures",
                      json={"name": "Base", "expression": "SUM(sales)"}, headers=auth_headers["a"])

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures",
                          json={"name": "Derived", "expression": "Base * 2"}, headers=auth_headers["a"])

    assert r.status_code == 400
    assert "measure" in r.json()["detail"].lower()


async def test_preview_returns_one_value_per_group(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.post(
        f"/api/v1/datasets/{ds.id}/measures/preview",
        json={"expression": "SUM(sales) / TOTAL(SUM(sales)) * 100", "group_by": "region"},
        headers=auth_headers["a"],
    )

    body = r.json()
    assert body["ok"] is True
    by_group = {s["group"]: s["value"] for s in body["sample"]}
    assert round(by_group["East"], 2) == 25.0     # 100 / 400
    assert round(by_group["West"], 2) == 75.0     # 300 / 400


async def test_preview_reports_a_bad_expression_without_raising(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(nope)"}, headers=auth_headers["a"])

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "nope" in r.json()["error"]


async def test_another_orgs_dataset_is_not_reachable(db_session, two_orgs, auth_headers, client, tmp_path):
    other = await _make_dataset(db_session, two_orgs["b"]["org"].id, tmp_path, name="other")

    r = await client.get(f"/api/v1/datasets/{other.id}/measures", headers=auth_headers["a"])

    assert r.status_code == 404


async def test_directquery_no_longer_refuses_a_measure_role(db_session, two_orgs, auth_headers, client, tmp_path):
    """E04: measures run on DirectQuery now (services/measure_sql.py). The
    route used to refuse any config naming one; it must not any more. The
    numbers are pinned in test_numeric_goldens.py and
    test_direct_query_measures.py."""
    ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path, mode="directquery", name="dq")
    ds.measures = [{"name": "M", "expression": "SUM(sales)"}]
    await db_session.commit()

    r = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "M"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert "Measures are not yet supported" not in r.text


class TestMetricVersions:
    """E05: editing a measure's formula changed every chart, export and AI
    answer built on it, with no record of what it had been."""

    async def _save(self, client, headers, ds, expression, agg=None):
        body = {"name": "Margin", "expression": expression, **({"default_aggregation": agg} if agg else {})}
        r = await client.post(f"/api/v1/datasets/{ds.id}/measures", json=body, headers=headers)
        assert r.status_code == 200, r.text
        return next(m for m in r.json() if m["name"] == "Margin")

    async def test_a_changed_formula_is_a_new_version_and_the_old_one_is_kept(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        h = auth_headers["a"]
        v1 = await self._save(client, h, ds, "SUM(profit) / SUM(sales)")
        assert v1["version"] == 1 and v1["history"] == [] and v1["saved_by"]
        same = await self._save(client, h, ds, "SUM(profit) / SUM(sales)")
        assert same["version"] == 1                          # nothing changed, no version
        v2 = await self._save(client, h, ds, "SUM(profit) / SUM(sales) * 100")
        assert v2["version"] == 2
        assert [x["expression"] for x in v2["history"]] == ["SUM(profit) / SUM(sales)"]

        hist = (await client.get(f"/api/v1/datasets/{ds.id}/measures/Margin/history", headers=h)).json()
        assert hist["current"]["version"] == 2
        assert [x["version"] for x in hist["history"]] == [1]

    async def test_restore_brings_a_formula_back_as_a_new_version(
            self, db_session, two_orgs, auth_headers, client, tmp_path):
        ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        h = auth_headers["a"]
        await self._save(client, h, ds, "SUM(profit) / SUM(sales)")
        await self._save(client, h, ds, "SUM(profit) / SUM(sales) * 100")
        r = await client.post(f"/api/v1/datasets/{ds.id}/measures/Margin/restore", json={"version": 1}, headers=h)
        assert r.status_code == 200, r.text
        m = next(x for x in r.json() if x["name"] == "Margin")
        assert m["version"] == 3 and m["expression"] == "SUM(profit) / SUM(sales)"
        assert [x["version"] for x in m["history"]] == [1, 2]      # history is only appended
        missing = await client.post(f"/api/v1/datasets/{ds.id}/measures/Margin/restore", json={"version": 9}, headers=h)
        assert missing.status_code == 404

    async def test_a_rename_keeps_the_history(self, db_session, two_orgs, auth_headers, client, tmp_path):
        ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        h = auth_headers["a"]
        await self._save(client, h, ds, "SUM(profit) / SUM(sales)")
        await self._save(client, h, ds, "SUM(profit) / SUM(sales) * 100")
        r = await client.post(f"/api/v1/datasets/{ds.id}/measures/Margin/rename", json={"new_name": "Margin %"}, headers=h)
        assert r.status_code == 200, r.text
        hist = (await client.get(f"/api/v1/datasets/{ds.id}/measures/Margin %25/history", headers=h)).json()
        assert hist["current"]["version"] == 2 and len(hist["history"]) == 1

    async def test_another_org_sees_no_history(self, db_session, two_orgs, auth_headers, client, tmp_path):
        ds = await _make_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        await self._save(client, auth_headers["a"], ds, "SUM(profit)")
        r = await client.get(f"/api/v1/datasets/{ds.id}/measures/Margin/history", headers=auth_headers["b"])
        assert r.status_code == 404
