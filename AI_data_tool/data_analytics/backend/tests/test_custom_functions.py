"""Custom calculated-column functions: validation and expansion.

See docs/superpowers/specs/2026-09-08-custom-calc-functions-design.md.
"""
import pytest

from app.services.custom_functions import CustomFunctionError, validate_custom_function_def


def _validate(name="PROFIT_MARGIN", params=None, expression="(revenue - cost) / revenue",
              column_names=None, calc_names=None, measure_names=None, other_functions=None):
    validate_custom_function_def(
        name, params if params is not None else ["revenue", "cost"], expression,
        column_names or set(), calc_names or set(), measure_names or set(),
        other_functions or {})


class TestValidDefinitionsPass:
    def test_a_well_formed_definition_is_accepted(self):
        _validate()  # must not raise


class TestNameCollisions:
    def test_rejects_a_name_colliding_with_a_builtin(self):
        with pytest.raises(CustomFunctionError, match="built-in"):
            _validate(name="SUM")

    def test_rejects_a_name_colliding_with_a_builtin_case_insensitively(self):
        with pytest.raises(CustomFunctionError, match="built-in"):
            _validate(name="sum")

    def test_rejects_a_name_colliding_with_a_dataset_column(self):
        with pytest.raises(CustomFunctionError, match="column or measure"):
            _validate(column_names={"PROFIT_MARGIN"})

    def test_rejects_a_name_colliding_with_a_calculated_column(self):
        with pytest.raises(CustomFunctionError, match="column or measure"):
            _validate(calc_names={"PROFIT_MARGIN"})

    def test_rejects_a_name_colliding_with_a_measure(self):
        with pytest.raises(CustomFunctionError, match="column or measure"):
            _validate(measure_names={"PROFIT_MARGIN"})

    def test_rejects_a_name_colliding_with_another_custom_function(self):
        with pytest.raises(CustomFunctionError, match="custom function"):
            _validate(other_functions={"PROFIT_MARGIN": {"params": [], "expression": "1"}})

    def test_rejects_a_name_that_is_not_a_valid_identifier(self):
        # Otherwise it saves successfully and is simply uncallable -- any expression
        # trying to call it fails to parse or never matches, and (same failure mode
        # as Fix 2) gets silently swallowed rather than erroring at save time.
        with pytest.raises(CustomFunctionError, match="not a valid function name"):
            _validate(name="my func")

    def test_rejects_a_name_that_is_a_python_keyword(self):
        with pytest.raises(CustomFunctionError, match="reserved"):
            _validate(name="class")


class TestParameterRules:
    def test_rejects_duplicate_parameter_names(self):
        with pytest.raises(CustomFunctionError, match="more than once"):
            _validate(params=["revenue", "revenue"], expression="revenue")

    def test_rejects_a_parameter_starting_with_underscore(self):
        with pytest.raises(CustomFunctionError, match="cannot start with"):
            _validate(params=["_revenue"], expression="_revenue")

    def test_rejects_a_parameter_colliding_with_a_builtin(self):
        with pytest.raises(CustomFunctionError, match="built-in"):
            _validate(params=["SUM"], expression="SUM")

    def test_rejects_a_parameter_that_is_not_a_valid_identifier(self):
        with pytest.raises(CustomFunctionError, match="not a valid parameter"):
            _validate(params=["not valid!"], expression="1")


class TestBodySafety:
    def test_rejects_an_unsafe_body_via_the_existing_ast_whitelist(self):
        # Attribute access is never in _ALLOWED_AST_NODES.
        with pytest.raises(CustomFunctionError):
            _validate(expression="revenue.sum()")

    def test_rejects_a_body_referencing_a_real_dataset_column_by_name(self):
        # 'tax' is neither a declared parameter nor a builtin -- rejected so
        # the function stays reusable and never silently hardcodes a column.
        with pytest.raises(CustomFunctionError, match="'tax'"):
            _validate(params=["revenue"], expression="revenue - tax")

    def test_rejects_a_body_calling_another_custom_function(self):
        with pytest.raises(CustomFunctionError, match="'OTHER_FN'"):
            _validate(params=["revenue"], expression="OTHER_FN(revenue)")

    def test_allows_a_body_that_only_uses_parameters_and_builtins(self):
        _validate(params=["revenue", "cost"], expression="round((revenue - cost) / revenue, 2)")


from app.services.custom_functions import expand_custom_functions

PROFIT_MARGIN = {"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                  "expression": "(revenue - cost) / revenue"}


class TestExpansion:
    def test_returns_the_expression_unchanged_when_there_are_no_custom_functions(self):
        assert expand_custom_functions("revenue * 2", []) == "revenue * 2"

    def test_expands_a_call_into_its_body_with_arguments_substituted(self):
        out = expand_custom_functions("PROFIT_MARGIN(rev, cst)", [PROFIT_MARGIN])
        assert out == "(rev - cst) / rev"

    def test_leaves_an_expression_with_no_matching_call_unchanged(self):
        out = expand_custom_functions("revenue * 2", [PROFIT_MARGIN])
        assert out == "revenue * 2"

    def test_swapped_arguments_produce_a_correspondingly_different_expansion(self):
        forward = expand_custom_functions("PROFIT_MARGIN(rev, cst)", [PROFIT_MARGIN])
        swapped = expand_custom_functions("PROFIT_MARGIN(cst, rev)", [PROFIT_MARGIN])
        assert forward == "(rev - cst) / rev"
        assert swapped == "(cst - rev) / cst"

    def test_hygienic_when_an_argument_subtree_contains_a_parameter_name(self):
        # 'cost' must NOT be re-substituted inside the already-injected
        # 'revenue + cost' subtree standing in for the 'revenue' parameter.
        out = expand_custom_functions("PROFIT_MARGIN(revenue + cost, cost)", [PROFIT_MARGIN])
        assert out == "(revenue + cost - cost) / (revenue + cost)"

    def test_rejects_too_few_arguments(self):
        with pytest.raises(CustomFunctionError, match="2 argument"):
            expand_custom_functions("PROFIT_MARGIN(rev)", [PROFIT_MARGIN])

    def test_rejects_too_many_arguments(self):
        with pytest.raises(CustomFunctionError, match="2 argument"):
            expand_custom_functions("PROFIT_MARGIN(rev, cst, extra)", [PROFIT_MARGIN])

    def test_rejects_keyword_arguments(self):
        with pytest.raises(CustomFunctionError, match="keyword"):
            expand_custom_functions("PROFIT_MARGIN(revenue=rev, cost=cst)", [PROFIT_MARGIN])

    def test_expands_nested_calls_to_two_different_custom_functions(self):
        discount = {"name": "DISCOUNT", "params": ["x"], "expression": "x * 0.9"}
        out = expand_custom_functions("PROFIT_MARGIN(rev, DISCOUNT(cst))", [PROFIT_MARGIN, discount])
        assert out == "(rev - cst * 0.9) / rev"

    def test_rejects_runaway_expansion_from_nested_repeated_parameter_use(self):
        # A's body uses its one parameter 3 times, so each nesting level roughly
        # triples the node count of everything beneath it -- exponential growth
        # with nesting depth. Deep-enough nesting must be rejected rather than
        # stalling/OOMing a worker thread.
        triple = {"name": "TRIPLE", "params": ["x"], "expression": "x + x + x"}
        expr = "x"
        for _ in range(10):
            expr = f"TRIPLE({expr})"
        with pytest.raises(CustomFunctionError, match="too complex"):
            expand_custom_functions(expr, [triple])

    def test_a_normal_expression_is_unaffected_by_the_complexity_limit(self):
        out = expand_custom_functions("PROFIT_MARGIN(rev, DISCOUNT(cst))",
                                       [PROFIT_MARGIN, {"name": "DISCOUNT", "params": ["x"], "expression": "x * 0.9"}])
        assert out == "(rev - cst * 0.9) / rev"

    def test_backtick_quoted_column_name_with_no_function_call_passes_through_unchanged(self):
        # Backtick-quoted names (auto-generated by ExpressionBuilder for any column
        # name containing a space) are not valid Python syntax, so ast.parse raises
        # SyntaxError. A column expression that calls no custom function must still
        # round-trip completely unchanged rather than raising -- it is evaluated
        # normally afterward by _eval_expr, which handles backticks on its own.
        out = expand_custom_functions("`net revenue` * 2", [PROFIT_MARGIN])
        assert out == "`net revenue` * 2"


import pandas as pd

from app.services.widget_data import apply_calculated_columns


class TestAppliedThroughCalculatedColumns:
    def test_a_calculated_column_can_call_a_custom_function(self):
        df = pd.DataFrame({"revenue": [100.0, 200.0], "cost": [40.0, 50.0]})
        out = apply_calculated_columns(
            df, [{"name": "margin", "expression": "PROFIT_MARGIN(revenue, cost)"}],
            custom_functions=[PROFIT_MARGIN])
        assert list(out["margin"]) == [0.6, 0.75]

    def test_an_unrecognized_call_with_no_custom_functions_given_drops_the_column_silently(self):
        # Matches apply_calculated_columns' existing swallow-on-error contract
        # (widget_data.py:2753-2754) for any other broken expression.
        df = pd.DataFrame({"revenue": [100.0], "cost": [40.0]})
        out = apply_calculated_columns(
            df, [{"name": "margin", "expression": "PROFIT_MARGIN(revenue, cost)"}])
        assert "margin" not in out.columns

    def test_backtick_quoted_column_still_computes_when_custom_functions_are_defined(self):
        # Regression: expand_custom_functions used to raise SyntaxError on any
        # backtick-quoted column name, and apply_calculated_columns swallows all
        # per-column exceptions -- so the moment ANY custom function existed on a
        # dataset, every calculated column referencing a space-containing column
        # name would silently stop producing a value.
        df = pd.DataFrame({"net revenue": [100.0, 200.0]})
        out = apply_calculated_columns(
            df, [{"name": "doubled", "expression": "`net revenue` * 2"}],
            custom_functions=[PROFIT_MARGIN])
        assert list(out["doubled"]) == [200.0, 400.0]


from app.models.models import Dataset, DatasetColumn


@pytest.fixture(autouse=True)
def _uploads(tmp_path, monkeypatch):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    return tmp_path


async def _numeric_dataset(db, org_id, tmp_path, name="Sales"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"revenue": [100.0, 200.0], "cost": [40.0, 50.0]}).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, mode="import",
                 row_count=2, col_count=2, custom_functions=[])
    db.add(ds)
    await db.flush()
    for c in ("revenue", "cost"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    await db.commit()
    return ds


class TestCustomFunctionsApi:
    @pytest.mark.asyncio
    async def test_create_then_list_it_back(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                             json={"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                                   "expression": "(revenue - cost) / revenue"},
                             headers=auth_headers["a"])
        assert r.status_code == 200, r.text

        got = await client.get(f"/api/v1/datasets/{ds.id}/custom-functions", headers=auth_headers["a"])
        assert got.status_code == 200
        assert got.json() == [{"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                                "expression": "(revenue - cost) / revenue"}]

    @pytest.mark.asyncio
    async def test_an_invalid_definition_is_rejected_with_400(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                             json={"name": "SUM", "params": [], "expression": "1"},
                             headers=auth_headers["a"])
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_removes_it(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                         json={"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                               "expression": "(revenue - cost) / revenue"},
                         headers=auth_headers["a"])
        r = await client.delete(f"/api/v1/datasets/{ds.id}/custom-functions/PROFIT_MARGIN",
                                headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_preview_evaluates_against_sample_values(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.post(f"/api/v1/datasets/{ds.id}/custom-functions/preview",
                              json={"params": ["revenue", "cost"], "expression": "(revenue - cost) / revenue",
                                    "sample_values": {"revenue": 100, "cost": 40}},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json() == {"ok": True, "result": 0.6}

    @pytest.mark.asyncio
    async def test_preview_of_an_unsafe_expression_reports_the_error_not_a_500(self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        r = await client.post(f"/api/v1/datasets/{ds.id}/custom-functions/preview",
                              json={"params": ["revenue"], "expression": "revenue.sum()",
                                    "sample_values": {"revenue": 100}},
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json()["ok"] is False


async def _regioned_numeric_dataset(db, org_id, tmp_path, name="Sales2"):
    """Like _numeric_dataset, but with a categorical column so a calculated
    column referencing PROFIT_MARGIN can be inspected per-group through the
    real bar-chart shaper (widget_data.shape_bar groups by a categorical
    dimension and aggregates the measure within each group)."""
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({
        "region": ["East", "West"],
        "revenue": [100.0, 200.0],
        "cost": [40.0, 50.0],
    }).to_csv(path, index=False)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, mode="import",
                 row_count=2, col_count=3, custom_functions=[])
    db.add(ds)
    await db.flush()
    for c, dtype in (("region", "categorical"), ("revenue", "numeric"), ("cost", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=dtype))
    await db.commit()
    return ds


class TestCustomFunctionsThroughWidgetData:
    """The spec's required end-to-end test: a saved function computes the correct
    value through the real GET .../widget-data path when used inside a calculated
    column, and editing the function busts the widget-data result cache (custom_functions
    was threaded into get_widget_data's cache key -- see widget_data.py's
    '__custom_fns__' cache-key entry)."""

    @pytest.mark.asyncio
    async def test_saved_function_computes_through_widget_data_and_edits_bust_the_cache(
            self, client, db_session, two_orgs, auth_headers, _uploads):
        ds = await _regioned_numeric_dataset(db_session, two_orgs["a"]["org"].id, _uploads)
        await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                         json={"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                               "expression": "(revenue - cost) / revenue"},
                         headers=auth_headers["a"])

        req = {
            "config": {"dimension": "region", "measure": "margin", "aggregation": "sum"},
            "widget_type": "bar",
            "calculated_columns": [{"name": "margin", "expression": "PROFIT_MARGIN(revenue, cost)"}],
        }
        r1 = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=req, headers=auth_headers["a"])
        assert r1.status_code == 200, r1.text
        by_name1 = {row["name"]: row["value"] for row in r1.json()["rows"]}
        assert round(by_name1["East"], 2) == 0.6      # (100 - 40) / 100
        assert round(by_name1["West"], 2) == 0.75     # (200 - 50) / 200

        # Edit the function's definition -- a different formula -- and request the
        # SAME widget-data config again. The new value must come back, not a stale
        # cached one from before the edit.
        await client.put(f"/api/v1/datasets/{ds.id}/custom-functions",
                         json={"name": "PROFIT_MARGIN", "params": ["revenue", "cost"],
                               "expression": "(revenue - cost) / cost"},
                         headers=auth_headers["a"])

        r2 = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=req, headers=auth_headers["a"])
        assert r2.status_code == 200, r2.text
        by_name2 = {row["name"]: row["value"] for row in r2.json()["rows"]}
        assert round(by_name2["East"], 2) == 1.5      # (100 - 40) / 40
        assert round(by_name2["West"], 2) == 3.0      # (200 - 50) / 50
