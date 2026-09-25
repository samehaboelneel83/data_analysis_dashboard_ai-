"""sqlglot is the agent's one new dependency — and its only parser.

The spec (F4) forbids string concatenation and post-filtering for row
policies; sqlglot's AST is the mechanism. If this import breaks, every
ladder rung V1-V5 breaks with it, so it gets its own loud test.
"""


def test_sqlglot_is_importable_and_parses():
    import sqlglot

    tree = sqlglot.parse_one("SELECT a FROM t WHERE b = 1", dialect="postgres")
    assert tree is not None
    assert "SELECT" in tree.sql(dialect="postgres").upper()


def test_sqlglot_round_trips_a_join():
    import sqlglot

    sql = "SELECT o.id FROM orders AS o JOIN customers AS c ON o.customer_id = c.id"
    rendered = sqlglot.parse_one(sql, dialect="postgres").sql(dialect="postgres")
    assert "JOIN" in rendered.upper()
