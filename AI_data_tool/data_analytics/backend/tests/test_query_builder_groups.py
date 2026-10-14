"""Condition groups (query builder plan step 2, 2026-10-10): "Match all /
Match any" boxes inside each other, so  condition = Used AND (make = Kia OR
make = Hyundai)  no longer needs the SQL tab -- compiled by the same code as
every other condition, so nothing inside a group is checked less strictly."""
import sqlite3

import pytest

from app.services import connections
from app.services.query_builder import build_sql, referenced_tables

KNOWN = {"cars": {"make", "condition", "price"}, "dealers": {"make", "city"}}


def model(filters, joiner="and"):
    return {"table": "cars", "columns": [{"table": "cars", "column": "make"}],
            "filters": filters, "filters_joiner": joiner, "limit": 10}


def eq(col, v):
    return {"table": "cars", "column": col, "op": "eq", "value": v}


def where(sql):
    return sql.split(" WHERE ", 1)[1].split(" ORDER BY ")[0]


def test_an_or_group_inside_an_and():
    sql = build_sql(model([eq("condition", "Used"),
                           {"group": "or", "filters": [eq("make", "Kia"), eq("make", "Hyundai")]}]),
                    "postgresql", KNOWN)
    assert where(sql) == ('"cars"."condition" = \'Used\' AND '
                          '("cars"."make" = \'Kia\' OR "cars"."make" = \'Hyundai\')')


def test_groups_nest_and_a_one_item_group_needs_no_brackets():
    sql = build_sql(model([{"group": "and", "filters": [
        eq("make", "Kia"),
        {"group": "or", "filters": [eq("condition", "Used"), {"group": "and", "filters": [eq("price", 5)]}]}]}]),
        "postgresql", KNOWN)
    assert where(sql) == ('("cars"."make" = \'Kia\' AND '
                          '("cars"."condition" = \'Used\' OR "cars"."price" = 5))')


def test_an_empty_group_is_left_out():
    sql = build_sql(model([eq("make", "Kia"), {"group": "or", "filters": []}]), "postgresql", KNOWN)
    assert where(sql) == '"cars"."make" = \'Kia\''
    assert " WHERE " not in build_sql(model([{"group": "and", "filters": []}]), "postgresql", KNOWN)


def test_old_flat_models_compile_exactly_as_before():
    sql = build_sql(model([eq("make", "Kia"), eq("make", "Fiat")], joiner="or"), "postgresql", KNOWN)
    assert where(sql) == '"cars"."make" = \'Kia\' OR "cars"."make" = \'Fiat\''


@pytest.mark.parametrize("bad,msg", [
    ({"group": "xor", "filters": []}, "unknown group joiner"),
    ({"group": "or", "filters": [{"table": "cars", "column": "nope", "op": "eq", "value": 1}]}, "does not exist"),
    ({"group": "or", "filters": [{"table": "cars", "column": "make", "op": "drop", "value": 1}]}, "unknown filter op"),
])
def test_inside_a_group_everything_is_checked(bad, msg):
    with pytest.raises(ValueError, match=msg):
        build_sql(model([bad]), "postgresql", KNOWN)


def test_nesting_is_bounded():
    g = eq("make", "Kia")
    for _ in range(8):
        g = {"group": "and", "filters": [g]}
    with pytest.raises(ValueError, match="nest at most"):
        build_sql(model([g]), "postgresql", KNOWN)


def test_a_subquery_inside_a_group_is_introspected_and_compiled():
    sub = {"table": "dealers", "columns": [{"table": "dealers", "column": "make"}],
           "filters": [{"table": "dealers", "column": "city", "op": "eq", "value": "Cairo"}]}
    m = model([{"group": "or", "filters": [eq("condition", "New"),
                                           {"table": "cars", "column": "make", "op": "in", "subquery": sub}]}])
    assert "dealers" in referenced_tables(m)
    assert 'IN (SELECT "dealers"."make" FROM "dealers" WHERE "dealers"."city" = \'Cairo\')' in build_sql(m, "postgresql", KNOWN)


def test_against_a_real_database(tmp_path):
    path = tmp_path / "c.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE cars (make TEXT, condition TEXT, price REAL)")
    con.executemany("INSERT INTO cars VALUES (?, ?, ?)", [
        ("Kia", "Used", 1), ("Hyundai", "Used", 2), ("Fiat", "Used", 3), ("Kia", "New", 4)])
    con.commit()
    con.close()
    sql = build_sql(model([eq("condition", "Used"),
                           {"group": "or", "filters": [eq("make", "Kia"), eq("make", "Hyundai")]}]),
                    "sqlite", KNOWN)
    rows = connections.preview_table({"type": "sqlite", "filepath": str(path)}, None, sql)["rows"]
    assert sorted(r[0] for r in rows) == ["Hyundai", "Kia"]
