"""Compiling an aggregate: the SQL is pinned, and everything it refuses is named.

Nothing user-supplied reaches the SQL as text. Grain and measure columns are
validated against the source's real columns, aggregations against a fixed
allowlist, and identifiers are quoted with the same function DirectQuery
uses. `row_count` is reserved and always present so averages can be computed
as sum / row_count on the aggregate.
"""
import pytest

from app.services import aggregates
from app.services.aggregates import AggregateSpecError

COLS = {"region", "product", "order_date", "amount", "units", "tenant"}


class _DS:
    source_table = "orders"
    source_query = None


class TestNormalise:
    def test_fills_default_measure_names(self):
        spec = aggregates.normalise_spec(
            {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum"}]}, COLS)
        assert spec["measures"] == [{"column": "amount", "agg": "sum", "name": "amount_sum"}]

    def test_keeps_an_explicit_name(self):
        spec = aggregates.normalise_spec(
            {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "revenue"}]}, COLS)
        assert spec["measures"][0]["name"] == "revenue"

    def test_a_source_with_a_real_row_count_column_still_cannot_use_it_as_grain(self):
        """The reservation must be unconditional. The parametrised case above
        proves 'reserved beats unknown column'; this proves 'reserved beats a
        column the source really has', which is the fail-open core/rls.py's
        unconditional row_count strip depends on."""
        with pytest.raises(AggregateSpecError, match="reserved"):
            aggregates.normalise_spec(
                {"grain": ["row_count"], "measures": [{"column": "amount", "agg": "sum"}]},
                COLS | {"row_count"})

    @pytest.mark.parametrize("bad, message", [
        ({"grain": [], "measures": [{"column": "amount", "agg": "sum"}]}, "grain"),
        ({"grain": ["nope"], "measures": [{"column": "amount", "agg": "sum"}]}, "nope"),
        ({"grain": ["region"], "measures": []}, "measure"),
        ({"grain": ["region"], "measures": [{"column": "nope", "agg": "sum"}]}, "nope"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "avg"}]}, "avg"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "row_count"}]}, "row_count"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "region"}]}, "region"),
        ({"grain": ["row_count"], "measures": [{"column": "amount", "agg": "sum"}]}, "reserved"),
        ({"grain": ["region", "region"], "measures": [{"column": "amount", "agg": "sum"}]}, "twice"),
        ({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum", "name": "x"},
                                            {"column": "units", "agg": "sum", "name": "x"}]}, "twice"),
    ])
    def test_refuses_and_names_the_problem(self, bad, message):
        with pytest.raises(AggregateSpecError, match=message):
            aggregates.normalise_spec(bad, COLS)


class TestCompile:
    def test_the_sql_is_exactly_this(self):
        spec = aggregates.normalise_spec(
            {"grain": ["region", "order_date"],
             "measures": [{"column": "amount", "agg": "sum"}, {"column": "units", "agg": "max"},
                          {"column": "product", "agg": "count"}]}, COLS)
        sql = aggregates.compile_aggregate_sql(_DS(), spec)
        assert sql == (
            'SELECT "region", "order_date", '
            'SUM("amount") AS "amount_sum", MAX("units") AS "units_max", COUNT("product") AS "product_count", '
            'COUNT(*) AS "row_count" '
            'FROM (SELECT * FROM "orders") AS src '
            'GROUP BY "region", "order_date"')

    def test_a_source_query_is_wrapped_not_edited(self):
        class Q:
            source_table = None
            source_query = "SELECT * FROM orders WHERE deleted = false;"
        spec = aggregates.normalise_spec({"grain": ["region"], "measures": [{"column": "amount", "agg": "sum"}]}, COLS)
        sql = aggregates.compile_aggregate_sql(Q(), spec)
        assert 'FROM (SELECT * FROM orders WHERE deleted = false) AS src' in sql

    def test_identifiers_with_quotes_are_escaped(self):
        cols = COLS | {'we"ird'}
        spec = aggregates.normalise_spec({"grain": ['we"ird'], "measures": [{"column": "amount", "agg": "sum"}]}, cols)
        assert '"we""ird"' in aggregates.compile_aggregate_sql(_DS(), spec)


class _Rule:
    def __init__(self, role_id, expr):
        self.role_id, self.filter_expr = role_id, expr


class TestGrainCoversRules:
    def test_a_rule_column_missing_from_the_grain_is_named(self):
        bad = aggregates.rls_columns_outside_grain(
            [_Rule(5, "tenant == 'acme'"), _Rule(6, "region == 'EMEA' and product == 'x'")],
            grain=["region"], known_columns=COLS)
        assert bad == [(5, "tenant"), (6, "product")]

    def test_a_grain_that_covers_every_rule_passes(self):
        assert aggregates.rls_columns_outside_grain(
            [_Rule(5, "tenant == 'acme'")], grain=["tenant", "region"], known_columns=COLS) == []

    def test_an_untranslatable_rule_is_reported_not_ignored(self):
        bad = aggregates.rls_columns_outside_grain(
            [_Rule(5, "region.str.startswith('E')")], grain=["region"], known_columns=COLS)
        assert bad == [(5, "<untranslatable>")]


class TestUncoveredMessage:
    """The one sentence shared by the create-time refusal (routers/datasets.py)
    and the refresh-time one (refresh_scheduler.py) -- both branches
    (translatable / `<untranslatable>`) and both framings (`when="create"` /
    `when="refresh"`)."""

    def test_names_the_role_and_column_on_create(self):
        msg = aggregates.uncovered_message([(5, "tenant")], {5: "Tenant"})
        assert "Tenant" in msg and "tenant" in msg
        assert not msg.startswith("Not refreshed")

    def test_the_refresh_framing_says_not_refreshed_and_still_names_it(self):
        msg = aggregates.uncovered_message([(5, "tenant")], {5: "Tenant"}, when="refresh")
        assert msg.startswith("Not refreshed:")
        assert "Tenant" in msg and "tenant" in msg

    def test_an_untranslatable_rule_names_the_role_not_the_placeholder_as_a_column(self):
        msg = aggregates.uncovered_message([(5, "<untranslatable>")], {5: "Tenant"})
        assert "cannot be checked" in msg
        assert "Tenant" in msg
        # The placeholder must never read as a column an operator could add.
        assert "'<untranslatable>'" not in msg

    def test_an_untranslatable_rule_on_refresh_still_leads_with_the_untranslatable_wording(self):
        msg = aggregates.uncovered_message([(5, "<untranslatable>")], {5: "Tenant"}, when="refresh")
        assert "cannot be checked" in msg
        assert "'<untranslatable>'" not in msg

    def test_an_unknown_role_id_falls_back_to_a_generic_label(self):
        msg = aggregates.uncovered_message([(999, "tenant")], {})
        assert "role 999" in msg


class TestDerivedMeasures:
    def test_measures_built_on_a_column_are_named(self):
        spec = {"grain": ["region"], "measures": [
            {"column": "amount", "agg": "sum", "name": "amount_sum"},
            {"column": "amount", "agg": "max", "name": "biggest"},
            {"column": "units", "agg": "sum", "name": "units_sum"}]}
        assert aggregates.derived_measure_names(spec, "amount") == ["amount_sum", "biggest"]
        assert aggregates.derived_measure_names(spec, "units") == ["units_sum"]
        assert aggregates.derived_measure_names(spec, "region") == []


class _Source:
    def __init__(self, source_table="orders", source_query=None, default_filter_expr=None):
        self.source_table = source_table
        self.source_query = source_query
        self.default_filter_expr = default_filter_expr


class _Agg:
    def __init__(self, aggregate_spec, source_query):
        self.aggregate_spec = aggregate_spec
        self.source_query = source_query


class TestAggregateStaleness:
    """The two cheap checks shared by `refresh_one` (acts on them) and
    `list_aggregates` (only reports them, for the unscheduled aggregates the
    tick's own query never selects) -- one helper so the wording cannot
    drift between the two call sites."""

    SPEC = aggregates.normalise_spec(
        {"grain": ["region"], "measures": [{"column": "amount", "agg": "sum"}]}, COLS)

    def test_an_up_to_date_source_reports_nothing(self):
        source = _Source()
        sql = aggregates.compile_aggregate_sql(source, self.SPEC)
        agg = _Agg(self.SPEC, sql)
        assert aggregates.aggregate_staleness(source, agg) is None

    def test_a_default_filter_on_the_source_is_reported(self):
        source = _Source(default_filter_expr="region == 'N'")
        sql = aggregates.compile_aggregate_sql(source, self.SPEC)
        agg = _Agg(self.SPEC, sql)
        msg = aggregates.aggregate_staleness(source, agg)
        assert msg is not None
        assert msg.startswith("Not refreshed:")
        assert "filter expression" in msg

    def test_a_repointed_source_table_is_reported_as_a_query_change(self):
        source = _Source()
        sql = aggregates.compile_aggregate_sql(source, self.SPEC)
        agg = _Agg(self.SPEC, sql)
        source.source_table = "orders_v2"          # re-pointed since the aggregate was built
        msg = aggregates.aggregate_staleness(source, agg)
        assert msg is not None and "query changed" in msg

    def test_the_filter_check_wins_over_a_query_change(self):
        source = _Source(default_filter_expr="region == 'N'")
        agg = _Agg(self.SPEC, "stale sql, does not matter")
        msg = aggregates.aggregate_staleness(source, agg)
        assert "filter expression" in msg

    def test_no_source_reports_nothing(self):
        agg = _Agg(self.SPEC, "anything")
        assert aggregates.aggregate_staleness(None, agg) is None
