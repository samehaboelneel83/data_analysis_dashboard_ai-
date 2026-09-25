"""The query-model → SQL compiler: dialect quoting, derived GROUP BY, joins,
value encoding, and the validation-first identifier stance."""
import pytest

from app.services.query_builder import build_sql, referenced_tables

KNOWN = {"orders": {"id", "customer_id", "region", "amount"},
         "customers": {"id", "name", "segment"}}


def base_model(**over):
    return {"table": "orders",
            "columns": [{"column": "region"},
                        {"column": "amount", "aggregation": "sum", "alias": "total"}],
            **over}


def test_aggregation_derives_group_by_from_the_plain_columns():
    sql = build_sql(base_model(), "postgresql", KNOWN)
    assert 'SUM("orders"."amount") AS "total"' in sql
    assert 'GROUP BY "orders"."region"' in sql


def test_dialect_quoting_and_limits():
    my = build_sql(base_model(limit=50), "mysql", KNOWN)
    assert "`orders`.`region`" in my and my.endswith("LIMIT 50")
    ms = build_sql(base_model(limit=50), "sqlserver", KNOWN)
    assert ms.startswith("SELECT TOP 50 ") and "[orders].[region]" in ms and "LIMIT" not in ms
    ora = build_sql(base_model(limit=50), "oracle", KNOWN)
    assert ora.endswith("FETCH FIRST 50 ROWS ONLY")


def test_joins_compile_with_validated_endpoints():
    sql = build_sql(base_model(
        joins=[{"table": "customers", "left_column": "customer_id",
                "right_column": "id", "how": "inner"}],
        columns=[{"table": "customers", "column": "segment"},
                 {"column": "amount", "aggregation": "avg"}]), "postgresql", KNOWN)
    assert 'INNER JOIN "customers" ON "orders"."customer_id" = "customers"."id"' in sql
    assert 'AVG("orders"."amount") AS "avg_amount"' in sql


def test_filters_encode_values_and_double_quotes():
    sql = build_sql(base_model(filters=[
        {"column": "region", "op": "eq", "value": "O'Brien's"},
        {"column": "amount", "op": "gte", "value": 10},
        {"column": "region", "op": "in", "value": ["a", "b"]},
        {"column": "region", "op": "not_null"},
    ]), "postgresql", KNOWN)
    assert "= 'O''Brien''s'" in sql            # quote doubling, nothing else
    assert '"orders"."amount" >= 10' in sql
    assert "IN ('a', 'b')" in sql and "IS NOT NULL" in sql


def test_identifiers_are_membership_checked_never_escaped():
    # an attacker-shaped identifier is refused because it is not IN THE SCHEMA,
    # which is a stronger property than any escaping
    with pytest.raises(ValueError, match="does not exist on table"):
        build_sql(base_model(columns=[{"column": 'amount"; DROP TABLE x; --'}]), "postgresql", KNOWN)
    with pytest.raises(ValueError, match="does not exist on this connection"):
        build_sql(base_model(table="pg_shadow"), "postgresql", KNOWN)
    with pytest.raises(ValueError, match="plain identifier"):
        build_sql(base_model(columns=[{"column": "amount", "aggregation": "sum",
                                       "alias": "x; DROP"}]), "postgresql", KNOWN)


def test_sort_by_alias_must_be_selected():
    sql = build_sql(base_model(sort=[{"alias": "total", "dir": "desc"}]), "postgresql", KNOWN)
    assert 'ORDER BY "total" DESC' in sql
    with pytest.raises(ValueError, match="not in the select list"):
        build_sql(base_model(sort=[{"alias": "ghost"}]), "postgresql", KNOWN)


def test_limit_is_capped_and_sanitised():
    sql = build_sql(base_model(limit=10**9), "postgresql", KNOWN)
    assert sql.endswith("LIMIT 100000")
    sql = build_sql(base_model(limit="lots"), "postgresql", KNOWN)
    assert sql.endswith("LIMIT 10000")


def test_filters_joiner_or_ties_rows_together():
    sql = build_sql(base_model(filters=[
        {"column": "region", "op": "eq", "value": "US"},
        {"column": "amount", "op": "gte", "value": 100},
    ], filters_joiner="or"), "postgresql", KNOWN)
    where = sql.split("WHERE ")[1].split(" GROUP BY")[0]
    assert where == '"orders"."region" = \'US\' OR "orders"."amount" >= 100'


def test_filters_joiner_defaults_to_and():
    sql = build_sql(base_model(filters=[
        {"column": "region", "op": "eq", "value": "US"},
        {"column": "amount", "op": "gte", "value": 100},
    ]), "postgresql", KNOWN)
    where = sql.split("WHERE ")[1].split(" GROUP BY")[0]
    assert where == '"orders"."region" = \'US\' AND "orders"."amount" >= 100'


def test_filters_joiner_rejects_unknown_value():
    with pytest.raises(ValueError, match="unknown filters joiner"):
        build_sql(base_model(filters=[{"column": "region", "op": "eq", "value": "US"}],
                              filters_joiner="xor"), "postgresql", KNOWN)


def test_referenced_tables_dedupes_in_order():
    m = base_model(joins=[{"table": "customers", "left_column": "customer_id", "right_column": "id"},
                          {"table": "customers", "left_column": "customer_id", "right_column": "id"}])
    assert referenced_tables(m) == ["orders", "customers"]


# ── Richer joins ─────────────────────────────────────────────────────────────

def test_full_outer_join_compiles():
    sql = build_sql(base_model(joins=[
        {"table": "customers", "left_column": "customer_id",
         "right_column": "id", "how": "full"}]), "postgresql", KNOWN)
    assert "FULL OUTER JOIN" in sql
    assert '"orders"."customer_id" = "customers"."id"' in sql


def test_cross_join_emits_no_on_clause():
    """CROSS JOIN takes no ON: emitting one is a syntax error, so the columns
    are not read at all rather than read and ignored."""
    sql = build_sql(base_model(joins=[
        {"table": "customers", "how": "cross"}]), "postgresql", KNOWN)
    assert "CROSS JOIN" in sql
    assert " ON " not in sql


def test_cross_join_needs_no_columns_in_the_model():
    # The model a diagram produces for a cross join genuinely has no endpoints;
    # requiring them would make the feature unusable from the canvas.
    build_sql(base_model(joins=[{"table": "customers", "how": "cross"}]),
              "postgresql", KNOWN)


def test_unknown_join_type_is_refused():
    with pytest.raises(ValueError, match="unknown join type"):
        build_sql(base_model(joins=[
            {"table": "customers", "left_column": "customer_id",
             "right_column": "id", "how": "sideways"}]), "postgresql", KNOWN)


# ── HAVING ───────────────────────────────────────────────────────────────────

def test_having_filters_the_aggregate():
    """WHERE runs before grouping, so 'regions whose total exceeds 1000'
    can only be said with HAVING."""
    sql = build_sql(base_model(having=[
        {"column": "amount", "aggregation": "sum", "op": "gt", "value": 1000}]),
        "postgresql", KNOWN)
    assert 'HAVING SUM("orders"."amount") > 1000' in sql
    # and it lands after GROUP BY, before ORDER BY / LIMIT
    assert sql.index("GROUP BY") < sql.index("HAVING")


def test_having_without_grouping_is_refused_not_silently_emitted():
    model = {"table": "orders", "columns": [{"column": "region"}],
             "having": [{"column": "amount", "aggregation": "sum",
                         "op": "gt", "value": 1}]}
    with pytest.raises(ValueError, match="HAVING needs"):
        build_sql(model, "postgresql", KNOWN)


def test_having_validates_its_column_like_any_other():
    with pytest.raises(ValueError, match="does not exist"):
        build_sql(base_model(having=[
            {"column": "nope", "aggregation": "sum", "op": "gt", "value": 1}]),
            "postgresql", KNOWN)


# ── Nested subqueries in WHERE ───────────────────────────────────────────────

SUB = {"table": "customers", "columns": [{"column": "id"}],
       "filters": [{"column": "segment", "op": "eq", "value": "enterprise"}]}


def test_in_subquery_nests_a_compiled_select():
    sql = build_sql(base_model(filters=[
        {"column": "customer_id", "op": "in", "subquery": SUB}]),
        "postgresql", KNOWN)
    assert '"orders"."customer_id" IN (SELECT' in sql
    assert '"customers"."segment" = \'enterprise\'' in sql


def test_exists_subquery_needs_no_left_column():
    sql = build_sql(base_model(filters=[{"op": "exists", "subquery": SUB}]),
                    "postgresql", KNOWN)
    assert sql.count("EXISTS (SELECT") == 1


def test_a_subquery_identifier_is_validated_as_strictly_as_an_outer_one():
    """THE property: nesting must not open a second, weaker path to SQL."""
    bad = {"table": "customers", "columns": [{"column": "id; DROP TABLE x"}]}
    with pytest.raises(ValueError, match="does not exist"):
        build_sql(base_model(filters=[
            {"column": "customer_id", "op": "in", "subquery": bad}]),
            "postgresql", KNOWN)


def test_an_in_subquery_must_select_exactly_one_column():
    two = {"table": "customers", "columns": [{"column": "id"}, {"column": "name"}]}
    with pytest.raises(ValueError, match="exactly one column"):
        build_sql(base_model(filters=[
            {"column": "customer_id", "op": "in", "subquery": two}]),
            "postgresql", KNOWN)


def test_subquery_nesting_is_depth_bounded():
    """A client-supplied model is compiled recursively, so an unbounded nest is
    a stack-overflow request rather than a query."""
    deep = SUB
    for _ in range(6):
        deep = {"table": "customers", "columns": [{"column": "id"}],
                "filters": [{"column": "id", "op": "in", "subquery": deep}]}
    with pytest.raises(ValueError, match="nest at most"):
        build_sql(base_model(filters=[
            {"column": "customer_id", "op": "in", "subquery": deep}]),
            "postgresql", KNOWN)


def test_a_missing_subquery_is_refused():
    # `not_in` has no value-list form, so a missing subquery is unambiguous.
    with pytest.raises(ValueError, match="needs a subquery"):
        build_sql(base_model(filters=[{"column": "customer_id", "op": "not_in"}]),
                  "postgresql", KNOWN)


def test_in_with_a_value_list_still_means_a_value_list():
    """`in` is overloaded: a list keeps its original meaning, a subquery nests.
    Overloading it silently broke the list form once -- this pins both."""
    sql = build_sql(base_model(filters=[
        {"column": "region", "op": "in", "value": ["North", "South"]}]),
        "postgresql", KNOWN)
    assert "IN ('North', 'South')" in sql
    assert "SELECT" == sql[:6]          # only the outer select


def test_referenced_tables_walks_into_subqueries():
    """The router introspects exactly this list; a subquery table missing from
    it would fail validation as 'does not exist' even though it does."""
    model = {"table": "orders",
             "filters": [{"column": "customer_id", "op": "in", "subquery": SUB}]}
    assert set(referenced_tables(model)) == {"orders", "customers"}


def test_a_subquery_carries_no_limit_of_its_own():
    """A LIMIT inside `IN (...)` truncates the SET BEING MATCHED AGAINST, which
    turns "customers in the enterprise segment" into "the first N of them" -- a
    wrong answer that looks like a right one. Oracle and SQL Server also reject
    a bare inner LIMIT/TOP outright."""
    sql = build_sql(base_model(filters=[
        {"column": "customer_id", "op": "in", "subquery": SUB}]),
        "postgresql", KNOWN)
    inner = sql[sql.index("IN (") + 4: sql.rindex(")")]
    assert "LIMIT" not in inner
    assert sql.rstrip().endswith("LIMIT 10000")      # the OUTER limit survives


def test_sqlserver_top_is_not_emitted_inside_a_subquery():
    sql = build_sql(base_model(filters=[
        {"column": "customer_id", "op": "in", "subquery": SUB}]),
        "sqlserver", KNOWN)
    assert sql.count("TOP ") == 1                    # outer only


# ── Malformed models must refuse with an author-readable message ─────────────
# Found by exercising the compiler with incomplete models: each of these used
# to raise a bare KeyError, which the router turned into a 400 whose entire
# body was `'column'` -- not a crash, but useless to whoever has to fix it.

@pytest.mark.parametrize("model,missing", [
    ({"table": "orders", "columns": [{}]}, "selected column"),
    ({"table": "orders", "columns": [{"column": "region"}],
      "joins": [{"table": "customers", "how": "inner"}]}, "join"),
    ({"table": "orders", "columns": [{"column": "region"}],
      "filters": [{"op": "eq", "value": 1}]}, "filter"),
    ({"table": "orders",
      "columns": [{"column": "region"},
                  {"column": "amount", "aggregation": "sum", "alias": "t"}],
      "having": [{"aggregation": "sum", "op": "gt", "value": 1}]}, "having"),
])
def test_a_missing_required_field_says_which_one(model, missing):
    with pytest.raises(ValueError, match="is missing its"):
        build_sql(model, "postgresql", KNOWN)
    try:
        build_sql(model, "postgresql", KNOWN)
    except ValueError as e:
        assert missing in str(e), f"message does not name the offender: {e}"


def test_joining_a_table_to_itself_is_refused_with_an_explanation():
    """It used to COMPILE and then fail at the database with "ambiguous column
    name" -- the author was told at the wrong moment by the wrong component.
    Self-joins need per-side aliases, which this compiler has no vocabulary
    for, so the honest answer is to say so and point at the hierarchy walk."""
    with pytest.raises(ValueError, match="already in this query"):
        build_sql(base_model(joins=[
            {"table": "orders", "left_column": "customer_id",
             "right_column": "id", "how": "inner"}]), "postgresql", KNOWN)


def test_the_same_table_joined_twice_is_refused():
    with pytest.raises(ValueError, match="already in this query"):
        build_sql(base_model(joins=[
            {"table": "customers", "left_column": "customer_id",
             "right_column": "id", "how": "inner"},
            {"table": "customers", "left_column": "customer_id",
             "right_column": "id", "how": "left"}]), "postgresql", KNOWN)
