"""Self-referencing hierarchies in the query builder.

Any table shaped (id, parent_id) -- an org chart, a category tree, a bill of
materials -- is walked with a generated recursive CTE that adds the three
columns the table cannot answer alone: `__level`, `__path`, `__root_id`.

Generated INLINE rather than installed as a stored `get_hierarchy()` function,
because a read-only analytics connection cannot CREATE FUNCTION and PL/pgSQL
covers one of the five dialects this builder supports. These tests pin that the
generated SQL is correct, portable, and actually RUNS -- the last part matters
most: a CTE that compiles but returns the wrong tree is the failure a
string-shape assertion would miss.
"""
import sqlite3

import pytest

from app.services.query_builder import (MAX_HIERARCHY_DEPTH, build_sql,
                                        referenced_tables)

KNOWN = {"employees": {"id", "name", "manager_id", "dept"},
         "salaries": {"employee_id", "amount"}}

HIER = {"table": "employees", "id_column": "id", "parent_column": "manager_id"}


def model(**over):
    m = {"table": "hierarchy", "hierarchy": HIER,
         "columns": [{"table": "hierarchy", "column": "name"},
                     {"table": "hierarchy", "column": "__level"}]}
    m.update(over)
    return m


def _run(sql: str):
    """Execute against a real SQLite tree: Amira → Bassem → {Carine, Dina},
    Amira → Emad."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE employees (id INT, name TEXT, manager_id INT, dept TEXT)")
    con.executemany("INSERT INTO employees VALUES (?,?,?,?)", [
        (1, "Amira", None, "Exec"), (2, "Bassem", 1, "Eng"),
        (3, "Carine", 2, "Eng"), (4, "Dina", 2, "Eng"), (5, "Emad", 1, "Sales")])
    con.execute("CREATE TABLE salaries (employee_id INT, amount INT)")
    con.executemany("INSERT INTO salaries VALUES (?,?)",
                    [(1, 100), (2, 80), (3, 60), (4, 60), (5, 70)])
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


class TestTheWalkIsCorrect:
    def test_level_path_and_root_are_produced_and_run(self):
        sql = build_sql(model(
            columns=[{"table": "hierarchy", "column": "name"},
                     {"table": "hierarchy", "column": "__level"},
                     {"table": "hierarchy", "column": "__path"},
                     {"table": "hierarchy", "column": "__root_id"}],
            sort=[{"table": "hierarchy", "column": "__path", "dir": "asc"}],
        ), "sqlite", KNOWN)
        rows = _run(sql)
        assert rows == [
            ("Amira", 1, "1", "1"),
            ("Bassem", 2, "1/2", "1"),
            ("Carine", 3, "1/2/3", "1"),
            ("Dina", 3, "1/2/4", "1"),
            ("Emad", 2, "1/5", "1"),
        ]

    def test_ordering_by_path_is_depth_first(self):
        """The reason `path` exists: ORDER BY path renders a tree in reading
        order, which no ORDER BY on id or name can do."""
        sql = build_sql(model(
            columns=[{"table": "hierarchy", "column": "name"}],
            sort=[{"table": "hierarchy", "column": "__path", "dir": "asc"}],
        ), "sqlite", KNOWN)
        assert [r[0] for r in _run(sql)] == ["Amira", "Bassem", "Carine", "Dina", "Emad"]

    def test_a_subtree_can_be_rooted_at_one_node(self):
        sql = build_sql(model(
            hierarchy={**HIER, "root_value": 2},
            columns=[{"table": "hierarchy", "column": "name"}],
            sort=[{"table": "hierarchy", "column": "__path", "dir": "asc"}],
        ), "sqlite", KNOWN)
        # Bassem and his reports only -- not Amira above him, not Emad beside.
        assert [r[0] for r in _run(sql)] == ["Bassem", "Carine", "Dina"]

    def test_the_base_tables_own_columns_survive_the_walk(self):
        sql = build_sql(model(
            columns=[{"table": "hierarchy", "column": "name"},
                     {"table": "hierarchy", "column": "dept"}],
            sort=[{"table": "hierarchy", "column": "__path", "dir": "asc"}],
        ), "sqlite", KNOWN)
        assert _run(sql)[0] == ("Amira", "Exec")

    def test_a_hierarchy_can_be_filtered_grouped_and_joined_like_any_table(self):
        """The CTE is a SOURCE, not a new kind of query: the rest of the
        compiler needs no special case, and this is what proves it."""
        sql = build_sql(model(
            columns=[{"table": "hierarchy", "column": "dept"},
                     {"table": "salaries", "column": "amount",
                      "aggregation": "sum", "alias": "total"}],
            joins=[{"left_table": "hierarchy", "left_column": "id",
                    "table": "salaries", "right_column": "employee_id",
                    "how": "inner"}],
            filters=[{"table": "hierarchy", "column": "__level", "op": "gte", "value": 2}],
        ), "sqlite", KNOWN)
        rows = dict(_run(sql))
        # Level >= 2 excludes Amira (100); Eng = 80+60+60, Sales = 70.
        assert rows == {"Eng": 200, "Sales": 70}


class TestGeneratedSqlIsPortable:
    @pytest.mark.parametrize("dialect,expected", [
        ("postgresql", "WITH RECURSIVE"),
        ("mysql", "WITH RECURSIVE"),
        ("sqlite", "WITH RECURSIVE"),
        # T-SQL's CTE is recursive without the keyword; using it is a syntax error.
        ("sqlserver", "WITH "),
    ])
    def test_the_recursive_keyword_matches_the_dialect(self, dialect, expected):
        sql = build_sql(model(), dialect, KNOWN)
        assert sql.startswith(expected)
        if dialect == "sqlserver":
            assert not sql.startswith("WITH RECURSIVE")

    def test_path_concatenation_uses_each_dialects_operator(self):
        assert "CONCAT(" in build_sql(model(), "mysql", KNOWN)
        assert " + '/' + " in build_sql(model(), "sqlserver", KNOWN)
        assert " || '/' || " in build_sql(model(), "postgresql", KNOWN)

    def test_every_generated_identifier_is_quoted(self):
        """An unquoted `h.__path` parses in SQLite and breaks elsewhere -- the
        whole reason this is generated rather than hand-written per dialect."""
        sql = build_sql(model(), "postgresql", KNOWN)
        assert "h.__path" not in sql and 'h."__path"' in sql

    def test_recursion_is_depth_bounded(self):
        """A cycle in the data (A parents B parents A) makes an unbounded CTE
        run forever. The stored-function version has no such guard; this one
        turns a hung connection into a truncated result."""
        sql = build_sql(model(), "postgresql", KNOWN)
        assert f"< {MAX_HIERARCHY_DEPTH}" in sql

    def test_a_cycle_terminates_instead_of_hanging(self):
        sql = build_sql(model(
            columns=[{"table": "hierarchy", "column": "name"}]), "sqlite", KNOWN)
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE employees (id INT, name TEXT, manager_id INT, dept TEXT)")
        # A real root, plus a two-node cycle that must not spin.
        con.executemany("INSERT INTO employees VALUES (?,?,?,?)", [
            (1, "Root", None, "X"), (2, "A", 3, "X"), (3, "B", 2, "X")])
        rows = con.execute(sql).fetchall()
        con.close()
        # The cycle is unreachable from a root, so only Root appears -- and
        # crucially the query RETURNED.
        assert rows == [("Root",)]


class TestValidation:
    def test_the_source_table_is_membership_checked(self):
        with pytest.raises(ValueError, match="does not exist on this connection"):
            build_sql(model(hierarchy={**HIER, "table": "pg_shadow"}), "postgresql", KNOWN)

    def test_the_key_columns_are_membership_checked(self):
        with pytest.raises(ValueError, match="does not exist on table"):
            build_sql(model(hierarchy={**HIER, "parent_column": "boss; DROP TABLE x"}),
                      "postgresql", KNOWN)

    def test_id_and_parent_must_differ(self):
        with pytest.raises(ValueError, match="must be different"):
            build_sql(model(hierarchy={**HIER, "parent_column": "id"}), "postgresql", KNOWN)

    def test_missing_key_columns_are_refused(self):
        with pytest.raises(ValueError, match="hierarchy needs id_column"):
            build_sql(model(hierarchy={"table": "employees", "parent_column": "manager_id"}),
                      "postgresql", KNOWN)

    def test_a_generated_name_that_collides_is_refused_not_shadowed(self):
        """If the base table already has `__level`, the CTE would emit two
        columns of that name and every outer reference becomes ambiguous."""
        known = {"employees": KNOWN["employees"] | {"__level"}}
        with pytest.raises(ValueError, match="already has a column named"):
            build_sql(model(), "postgresql", known)

    def test_the_generated_columns_are_validated_like_real_ones(self):
        with pytest.raises(ValueError, match="does not exist on table"):
            build_sql(model(columns=[{"table": "hierarchy", "column": "__depth"}]),
                      "postgresql", KNOWN)

    def test_a_hierarchy_inside_a_subquery_is_refused(self):
        """Legal in some dialects, not others; refusing beats emitting SQL that
        works on one customer's database and not the next."""
        sub = {"table": "hierarchy", "hierarchy": HIER,
               "columns": [{"table": "hierarchy", "column": "id"}]}
        with pytest.raises(ValueError, match="cannot be used inside a subquery"):
            build_sql({"table": "employees",
                       "columns": [{"column": "name"}],
                       "filters": [{"column": "id", "op": "in", "subquery": sub}]},
                      "postgresql", KNOWN)

    def test_referenced_tables_reports_the_source_not_the_cte(self):
        """The router introspects this list: the SOURCE must be in it, and the
        CTE name must not (it is not a table in the schema)."""
        tables = referenced_tables(model())
        assert "employees" in tables
        assert "hierarchy" not in tables
