"""SQL injection (owner request, 2026-10-10): values, names and hand-written SQL.

The query builder wrote a value as '...' with quotes doubled. On MySQL,
MariaDB and ClickHouse a backslash is an escape too, so the value
    \\' OR 1=1 #
compiled to  = '\\'' OR 1=1 #'  -- the string ' and then real SQL. Each case
here is checked the way the database reads it (sqlglot in that dialect), and
once against a real SQLite database.
"""
import sqlite3

import pytest
import sqlglot
from sqlglot import exp

from app.services import connections
from app.services.direct_query import _base_query_sql
from app.services.query_builder import build_sql
from app.services.sql_safety import (UnsafeQuery, encode_literal, ensure_read_only, like_pattern,
                                     quote_ident, sqlglot_dialect)

FAMILIES = ["postgresql", "mysql", "sqlserver", "oracle", "sqlite", "clickhouse"]
ATTACKS = [
    "\\' OR 1=1 #",
    "\\' OR 1=1 -- ",
    "' OR '1'='1",
    "x'; DROP TABLE cars; --",
    "\\\\'; DELETE FROM cars; --",
    "it's fine \\ really",
]
KNOWN = {"cars": {"make", "price", "item_url"}}


def _model(op, value):
    return {"table": "cars", "columns": [{"table": "cars", "column": "make"}],
            "filters": [{"table": "cars", "column": "make", "op": op, "value": value}], "limit": 10}


def _where_is_one_comparison(sql: str, family: str) -> exp.Expression:
    trees = [t for t in sqlglot.parse(sql, dialect=sqlglot_dialect(family))
             if t is not None and not isinstance(t, exp.Semicolon)]
    assert len(trees) == 1, f"{family}: more than one statement in {sql!r}"
    where = trees[0].find(exp.Where)
    assert where is not None
    assert where.find(exp.Or) is None, f"{family}: the value escaped its string: {sql!r}"
    return where


class TestValues:
    @pytest.mark.parametrize("family", FAMILIES)
    @pytest.mark.parametrize("attack", ATTACKS)
    def test_a_value_never_becomes_sql(self, family, attack):
        sql = build_sql(_model("eq", attack), family, KNOWN)
        where = _where_is_one_comparison(sql, family)
        assert len([l for l in where.find_all(exp.Literal) if l.is_string]) == 1

    @pytest.mark.parametrize("family", FAMILIES)
    @pytest.mark.parametrize("attack", ATTACKS)
    def test_contains_and_in_lists_too(self, family, attack):
        _where_is_one_comparison(build_sql(_model("contains", attack), family, KNOWN), family)
        _where_is_one_comparison(build_sql(_model("in", [attack, "Kia"]), family, KNOWN), family)

    def test_mysql_doubles_the_backslash_and_postgres_does_not(self):
        assert encode_literal("a\\'b", "mysql") == "'a\\\\''b'"
        assert encode_literal("a\\'b", "postgresql") == "'a\\''b'"
        # A family we do not know gets the strict encoding.
        assert encode_literal("a\\b", "snowflake") == "'a\\\\b'"

    def test_values_no_database_can_hold_are_refused(self):
        with pytest.raises(UnsafeQuery):
            encode_literal("a\x00b", "postgresql")
        with pytest.raises(UnsafeQuery):
            encode_literal(float("nan"), "postgresql")
        with pytest.raises(UnsafeQuery):
            encode_literal(float("inf"), "mysql")

    def test_contains_matches_percent_and_underscore_literally(self):
        # "50%" used to match "500": the % was a wildcard.
        assert like_pattern("50%_off", "postgresql") == "'%50!%!_off%' ESCAPE '!'"

    def test_a_quote_inside_a_name_is_doubled(self):
        assert quote_ident("postgresql", 'a"b') == '"a""b"'
        assert quote_ident("mysql", "a`b") == "`a``b`"
        assert quote_ident("sqlserver", "a]b") == "[a]]b]"


class TestRealDatabase:
    """The same attacks against a real SQLite file: no extra rows, no damage."""

    @pytest.fixture
    def db(self, tmp_path):
        path = tmp_path / "cars.db"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE cars (make TEXT, price REAL, item_url TEXT)")
        con.executemany("INSERT INTO cars VALUES (?, ?, ?)",
                        [("Kia", 1, "u1"), ("Fiat", 2, "u2"), ("50% off", 3, "u3")])
        con.commit()
        con.close()
        return {"type": "sqlite", "filepath": str(path)}

    @pytest.mark.parametrize("attack", ATTACKS)
    def test_an_attack_matches_nothing_and_changes_nothing(self, db, attack):
        sql = build_sql(_model("eq", attack), "sqlite", KNOWN)
        assert connections.preview_table(db, None, sql)["rows"] == []
        assert len(connections.preview_table(db, "cars", None)["rows"]) == 3

    def test_contains_finds_the_literal_text(self, db):
        rows = connections.preview_table(db, None, build_sql(_model("contains", "0%"), "sqlite", KNOWN))["rows"]
        assert rows == [["50% off"]]

    @pytest.mark.parametrize("sql", ["DELETE FROM cars", "SELECT 1; DROP TABLE cars",
                                     "DROP TABLE cars", "UPDATE cars SET price = 0"])
    def test_hand_written_sql_that_writes_never_runs(self, db, sql):
        with pytest.raises(UnsafeQuery):
            connections.preview_table(db, None, sql)
        with pytest.raises(UnsafeQuery):
            connections.import_to_dataframe(db, None, sql)
        assert len(connections.preview_table(db, "cars", None)["rows"]) == 3


class TestHandWrittenSql:
    @pytest.mark.parametrize("sql", [
        "SELECT make FROM cars",
        "SELECT make FROM cars;",
        "with x as (select * from cars) select make from x",
        "SELECT make FROM cars UNION SELECT make FROM cars",
        "(SELECT make FROM cars)",
        "SELECT ';' AS semi, make FROM cars -- a ; in a comment",
        "SELECT REPLACE(make, 'a', 'b') FROM cars WHERE updated_at > :cursor_val",
    ])
    def test_reads_are_allowed(self, sql):
        assert ensure_read_only(sql, "postgresql")

    @pytest.mark.parametrize("sql,family", [
        ("DELETE FROM cars", "postgresql"),
        ("SELECT 1; DROP TABLE cars", "postgresql"),
        ("SELECT 'a\\'; DROP TABLE cars; --'", "postgresql"),
        ("SELECT * INTO copy FROM cars", "postgresql"),
        ("WITH d AS (DELETE FROM cars RETURNING *) SELECT * FROM d", "postgresql"),
        ("EXEC xp_cmdshell 'dir'", "sqlserver"),
        ("SELECT TOP 5 * FROM cars; DROP TABLE cars", "sqlserver"),
        ("TRUNCATE TABLE cars", "mysql"),
        ("SELECT * FROM cars INTO OUTFILE '/tmp/x'", "mysql"),
        ("", "postgresql"),
    ])
    def test_anything_else_is_refused_with_a_reason(self, sql, family):
        with pytest.raises(UnsafeQuery) as e:
            ensure_read_only(sql, family)
        assert str(e.value)

    def test_a_saved_live_query_with_two_statements_is_not_run(self):
        class Ds:
            source_query = "SELECT * FROM cars; DROP TABLE cars"
            source_table = None
        with pytest.raises(UnsafeQuery):
            _base_query_sql(Ds())


class TestDriverText:
    """psycopg2/pymysql read % as a placeholder: every LIKE '%x%' in hand-written
    SQL failed on PostgreSQL ("immutabledict is not a sequence"), and the
    incremental refresh's :cursor_val could not be bound at all."""

    def _engine(self, style):
        class Dialect:
            paramstyle = style

        class Engine:
            dialect = Dialect()
        return Engine()

    def test_percent_is_doubled_only_for_percent_style_drivers(self):
        sql = "SELECT * FROM t WHERE a LIKE '%x%'"
        assert connections._driver_sql(sql, self._engine("pyformat")) == "SELECT * FROM t WHERE a LIKE '%%x%%'"
        assert connections._driver_sql(sql, self._engine("format")) == "SELECT * FROM t WHERE a LIKE '%%x%%'"
        assert connections._driver_sql(sql, self._engine("qmark")) == sql

    def test_incremental_parameters_are_bound(self, tmp_path):
        from app.services.dataset_refresh import build_incremental_query
        path = tmp_path / "w.db"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE t (id INTEGER, note TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?)", [(1, "50% off"), (2, "a"), (3, "b")])
        con.commit()
        con.close()
        cfg = {"type": "sqlite", "filepath": str(path)}
        q = build_incremental_query(None, "SELECT id, note FROM t WHERE note LIKE '%'", "id", 1, {"id", "note"})
        df = connections.import_to_dataframe(cfg, None, q, params={"cursor_val": 1})
        assert sorted(df["id"]) == [2, 3]
