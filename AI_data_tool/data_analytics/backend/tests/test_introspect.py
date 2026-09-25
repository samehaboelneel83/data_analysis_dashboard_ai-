"""Stage 1 — reading a database's own catalog.

ARCHITECTURE.md stage 1.4: use SQLAlchemy's Inspector, which "normalizes
introspection across 10+ dialects — the biggest single saving here".

The point of this stage is that it needs NOTHING but a connection. No dataset,
no prior import, no human having decided which tables matter. A description
assembled only from datasets describes the part of the database someone already
knew about, which is exactly backwards for a person connecting a new source.

Tested against a real SQLite database rather than mocks, because the whole
value of the module is what a live Inspector actually returns — declared
foreign keys, primary keys, nullability, comments — and a mock would only
assert what I already believed.
"""
import pytest
from sqlalchemy import create_engine, text

from app.services.metadata import introspect


@pytest.fixture
def db(tmp_path):
    """A small schema with the features introspection has to survive."""
    path = tmp_path / "shop.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                city TEXT
            )"""))
        conn.execute(text("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                total NUMERIC(10, 2),
                placed_at TIMESTAMP
            )"""))
        conn.execute(text("""
            CREATE TABLE "odd name" (
                "select" TEXT,
                value INTEGER
            )"""))
        conn.execute(text("CREATE VIEW active_customers AS SELECT * FROM customers"))
        conn.execute(text("INSERT INTO customers (id, email) VALUES (1, 'a@x.com')"))
    yield engine
    engine.dispose()


class TestListObjects:
    def test_finds_tables_and_views(self, db):
        objects = introspect.list_objects(db)
        by_name = {o["name"]: o for o in objects}
        assert by_name["customers"]["kind"] == "table"
        assert by_name["active_customers"]["kind"] == "view"

    def test_finds_every_table_without_being_told_which(self, db):
        """No dataset, no import, no configuration — just the connection."""
        names = {o["name"] for o in introspect.list_objects(db)}
        assert {"customers", "orders", "odd name"} <= names

    def test_skips_system_objects(self, db):
        names = {o["name"] for o in introspect.list_objects(db)}
        assert not any(n.startswith("sqlite_") for n in names)


class TestDescribeObject:
    def test_returns_columns_in_order(self, db):
        got = introspect.describe_object(db, "customers")
        assert [c["name"] for c in got["columns"]] == ["id", "email", "city"]
        assert [c["position"] for c in got["columns"]] == [0, 1, 2]

    def test_reports_native_and_normalized_types(self, db):
        """The native type is what the database said; the normalized one is what
        this platform reasons about. NUMERIC(10,2) is money — collapsing it to
        'float' loses exactly the information that says so."""
        got = introspect.describe_object(db, "orders")
        total = next(c for c in got["columns"] if c["name"] == "total")
        assert "NUMERIC" in (total["native_type"] or "").upper()
        assert total["dtype"] == "numeric"

    def test_maps_a_timestamp(self, db):
        got = introspect.describe_object(db, "orders")
        placed = next(c for c in got["columns"] if c["name"] == "placed_at")
        assert placed["dtype"] == "datetime"

    def test_reports_nullability(self, db):
        got = introspect.describe_object(db, "customers")
        by_name = {c["name"]: c for c in got["columns"]}
        assert by_name["email"]["nullable"] is False
        assert by_name["city"]["nullable"] is True

    def test_reports_the_primary_key(self, db):
        got = introspect.describe_object(db, "customers")
        by_name = {c["name"]: c for c in got["columns"]}
        assert by_name["id"]["is_primary_key"] is True
        assert by_name["email"]["is_primary_key"] is False

    def test_reports_declared_foreign_keys(self, db):
        """A declared FK is a FACT, not an inference. Seeding these means the
        join graph starts from what the database already guarantees, and value
        overlap is only asked to find the ones nobody declared."""
        got = introspect.describe_object(db, "orders")
        assert got["foreign_keys"] == [{
            "from_column": "customer_id",
            "to_table": "customers",
            "to_column": "id",
        }]

    def test_a_table_without_foreign_keys_reports_none(self, db):
        assert introspect.describe_object(db, "customers")["foreign_keys"] == []

    def test_survives_reserved_words_and_spaces(self, db):
        """Real catalogs contain both, and a name that cannot be read is a table
        that silently vanishes from the description."""
        got = introspect.describe_object(db, "odd name")
        assert {c["name"] for c in got["columns"]} == {"select", "value"}

    def test_a_missing_table_raises_rather_than_returning_empty(self, db):
        """An empty result would be indistinguishable from a table with no
        columns, and would quietly enter the catalog as one."""
        with pytest.raises(Exception):
            introspect.describe_object(db, "no_such_table")


class TestIntrospectAll:
    def test_returns_every_object_with_its_columns(self, db):
        got = introspect.introspect_source(db)
        by_name = {o["name"]: o for o in got}
        assert len(by_name["customers"]["columns"]) == 3
        assert len(by_name["orders"]["columns"]) == 4

    def test_carries_foreign_keys_through(self, db):
        got = introspect.introspect_source(db)
        orders = next(o for o in got if o["name"] == "orders")
        assert orders["foreign_keys"][0]["to_table"] == "customers"

    def test_one_unreadable_object_does_not_lose_the_rest(self, db, monkeypatch):
        """A permission-denied view is normal in a real database. Losing the
        other nineteen tables over it is not."""
        original = introspect.describe_object

        def selective(engine, name, schema=None):
            if name == "orders":
                raise RuntimeError("permission denied")
            return original(engine, name, schema)

        monkeypatch.setattr(introspect, "describe_object", selective)
        got = introspect.introspect_source(db)
        names = {o["name"] for o in got}
        assert "customers" in names
        assert "orders" not in names

    def test_row_counts_come_from_engine_statistics_or_not_at_all(self, db):
        """SQLite keeps no reltuples-equivalent, so every object reports an
        unknown count — and that is the correct answer, not a gap.

        Introspection must never scan. Measured on a real 82-object Postgres
        source, counting the VIEWS took nearly two minutes each, because a
        count on a view executes the view over its underlying tables.
        """
        got = introspect.introspect_source(db, with_counts=True)
        assert all(o["row_count_estimate"] is None for o in got)

    def test_an_exact_count_is_available_but_never_used_here(self, db):
        """Kept for a caller that has decided the scan is worth it. That caller
        is not introspection."""
        assert introspect.count_rows(db, "customers", None) == 1

    def test_counting_is_optional(self, db):
        got = introspect.introspect_source(db, with_counts=False)
        assert all(o["row_count_estimate"] is None for o in got)


class TestTypeNormalization:
    @pytest.mark.parametrize("native,expected", [
        ("INTEGER", "integer"),
        ("BIGINT", "integer"),
        ("NUMERIC(10, 2)", "numeric"),
        ("DOUBLE PRECISION", "numeric"),
        ("VARCHAR(255)", "text"),
        ("TEXT", "text"),
        ("BOOLEAN", "boolean"),
        ("TIMESTAMP", "datetime"),
        ("DATE", "datetime"),
        ("JSONB", "json"),
        ("UUID", "text"),
    ])
    def test_common_types(self, native, expected):
        assert introspect.normalize_type(native) == expected

    def test_an_unknown_type_is_kept_rather_than_guessed(self):
        """Inventing a type for something unrecognised is worse than admitting
        it is unknown — a wrong dtype silently changes how a column is treated
        everywhere downstream."""
        assert introspect.normalize_type("GEOGRAPHY(POINT,4326)") == "unknown"

    def test_none_is_unknown(self):
        assert introspect.normalize_type(None) == "unknown"
