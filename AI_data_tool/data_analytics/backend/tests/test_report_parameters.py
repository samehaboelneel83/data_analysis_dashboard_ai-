"""Report parameters: typed values referenced as @name in filters and expressions.

The type declarations are load-bearing: substitution encodes each value as a literal
of its declared type before anything is evaluated, which is what keeps a parameter
from being an injection path into the eval sandbox.
"""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn
from app.services.parameters import ParameterError, encode_literal, substitute


class TestEncoding:
    def test_numbers_become_float_literals(self):
        assert encode_literal("number", "5") == "5.0"
        assert encode_literal("number", 2.5) == "2.5"

    def test_a_non_number_is_rejected_not_passed_through(self):
        with pytest.raises(ParameterError):
            encode_literal("number", "5; import os")

    def test_text_is_quoted_by_repr_so_quotes_cannot_break_out(self):
        # The classic injection shape: a value carrying a quote and an or-clause. repr
        # keeps it ONE string literal, whatever quoting the value tries.
        lit = encode_literal("text", "US' or '1'=='1")
        assert lit == '"US\' or \'1\'==\'1"'
        assert eval(lit) == "US' or '1'=='1"   # still just a string

    def test_dates_validate_and_emit_iso(self):
        assert encode_literal("date", "2024-03-31") == "'2024-03-31'"
        with pytest.raises(ParameterError):
            encode_literal("date", "not a date")

    def test_substitute_rejects_unknown_names(self):
        from types import SimpleNamespace as NS
        with pytest.raises(ParameterError):
            substitute("x > @ghost", {}, [NS(name="n", param_type="number", default_value="1")])


@pytest.fixture
def sales_ds(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({
        "region": ["US", "US", "CA", "CA"],
        "revenue": [100.0, 50.0, 30.0, 20.0],
    }).to_csv(p, index=False)
    return str(p)


async def _setup(client, headers, db, org_id, path):
    ds = Dataset(name="S", filename=path, org_id=org_id, mode="import")
    db.add(ds)
    await db.flush()
    db.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"))
    db.add(DatasetColumn(dataset_id=ds.id, name="revenue", dtype="numeric"))
    await db.commit()

    r = await client.post("/api/v1/reports", json={"name": "P", "dataset_id": ds.id}, headers=headers)
    report_id = r.json()["id"]
    await client.put(f"/api/v1/reports/{report_id}/parameters", json=[
        {"name": "min_revenue", "param_type": "number", "default_value": "40"},
        {"name": "chosen_region", "param_type": "text", "default_value": "US",
         "options": ["US", "CA"]},
    ], headers=headers)
    return ds, report_id


@pytest.mark.asyncio
async def test_a_parameter_drives_a_structured_filter(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)

    body = {"widget_type": "bar",
            "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum",
                       "filters": [{"column": "region", "op": "eq", "value": "@chosen_region"}]},
            "report_id": report_id, "parameters": {"chosen_region": "CA"}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert {row["name"] for row in r.json()["rows"]} == {"CA"}


@pytest.mark.asyncio
async def test_the_default_applies_when_the_viewer_sets_nothing(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)

    body = {"widget_type": "bar",
            "config": {"dimension": "region", "measure": "revenue",
                       "filters": [{"column": "region", "op": "eq", "value": "@chosen_region"}]},
            "report_id": report_id, "parameters": {}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert {row["name"] for row in r.json()["rows"]} == {"US"}


@pytest.mark.asyncio
async def test_a_parameter_reaches_a_calculated_expression_as_a_typed_literal(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)

    body = {"widget_type": "kpi",
            "config": {"measure": "above", "aggregation": "sum"},
            "calculated_columns": [{"name": "above", "expression": "IF(revenue > @min_revenue, revenue, 0)"}],
            "report_id": report_id, "parameters": {"min_revenue": "45"}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["value"] == 150.0    # 100 + 50; 30 and 20 fall below 45


@pytest.mark.asyncio
async def test_an_injection_shaped_text_value_stays_data(client, auth_headers, db_session, two_orgs, sales_ds):
    """The security case. A text parameter carrying quote-and-or must filter to zero
    rows -- it is a string nobody's region equals -- not evaluate."""
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)

    body = {"widget_type": "bar",
            "config": {"dimension": "region", "measure": "revenue",
                       "filters": [{"column": "region", "op": "eq", "value": "@chosen_region"}]},
            "report_id": report_id,
            "parameters": {"chosen_region": "US' or '1'=='1"}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["rows"] == []


@pytest.mark.asyncio
async def test_a_non_numeric_value_for_a_number_parameter_is_a_400(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)
    body = {"widget_type": "kpi",
            "config": {"measure": "above", "aggregation": "sum"},
            "calculated_columns": [{"name": "above", "expression": "IF(revenue > @min_revenue, revenue, 0)"}],
            "report_id": report_id, "parameters": {"min_revenue": "os.system"}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_an_unknown_parameter_in_a_filter_is_a_400_not_a_silent_mismatch(client, auth_headers, db_session, two_orgs, sales_ds):
    """The literal string "@ghost" matches no region, which would LOOK like a data bug.
    The config bug it actually is surfaces as a 400 naming the parameter."""
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)
    body = {"widget_type": "bar",
            "config": {"dimension": "region",
                       "filters": [{"column": "region", "op": "eq", "value": "@ghost"}]},
            "report_id": report_id, "parameters": {}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 400
    assert "ghost" in r.text


@pytest.mark.asyncio
async def test_another_orgs_report_cannot_be_used_for_definitions(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)
    # Org B creating its own dataset but pointing report_id at org A's report.
    p2 = sales_ds  # same file, different org's dataset row
    ds_b = Dataset(name="B", filename=p2, org_id=two_orgs["b"]["org"].id, mode="import")
    db_session.add(ds_b)
    await db_session.commit()

    body = {"widget_type": "bar", "config": {"dimension": "region"},
            "report_id": report_id, "parameters": {}}
    r = await client.post(f"/api/v1/datasets/{ds_b.id}/widget-data", json=body, headers=auth_headers["b"])
    assert r.status_code == 404


class TestDefinitionValidation:
    @pytest.mark.asyncio
    async def test_names_must_be_identifiers(self, client, auth_headers):
        r = await client.post("/api/v1/reports", json={"name": "V"}, headers=auth_headers["a"])
        rid = r.json()["id"]
        for bad in ("has space", "1starts_with_digit", "", "hy-phen"):
            resp = await client.put(f"/api/v1/reports/{rid}/parameters",
                                    json=[{"name": bad, "param_type": "number"}],
                                    headers=auth_headers["a"])
            assert resp.status_code == 400, bad

    @pytest.mark.asyncio
    async def test_duplicate_names_are_rejected(self, client, auth_headers):
        r = await client.post("/api/v1/reports", json={"name": "V2"}, headers=auth_headers["a"])
        rid = r.json()["id"]
        resp = await client.put(f"/api/v1/reports/{rid}/parameters",
                                json=[{"name": "p", "param_type": "number"},
                                      {"name": "p", "param_type": "text"}],
                                headers=auth_headers["a"])
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_a_parameter_drives_the_rank_count(client, auth_headers, db_session, two_orgs, sales_ds):
    """SAS can drive top-N from a parameter; rank.n accepts '@name' and the
    router substitutes the typed numeric value before the shaper sees it."""
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)

    body = {"widget_type": "bar",
            "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum",
                       "rank": {"mode": "top", "n": "@min_revenue"}},
            "report_id": report_id, "parameters": {"min_revenue": "1"}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    # top 1 by summed revenue: US (150) beats CA (50)
    assert [row["name"] for row in r.json()["rows"]] == ["US"]


@pytest.mark.asyncio
async def test_a_non_numeric_parameter_as_rank_count_is_a_400(client, auth_headers, db_session, two_orgs, sales_ds):
    ds, report_id = await _setup(client, auth_headers["a"], db_session, two_orgs["a"]["org"].id, sales_ds)

    body = {"widget_type": "bar",
            "config": {"dimension": "region", "measure": "revenue",
                       "rank": {"mode": "top", "n": "@chosen_region"}},
            "report_id": report_id, "parameters": {"chosen_region": "US"}}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert r.status_code == 400
