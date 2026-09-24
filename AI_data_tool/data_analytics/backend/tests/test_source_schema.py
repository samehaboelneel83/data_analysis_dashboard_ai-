"""The Schema field on a connection, which until now did nothing.

`connectors._hostport_fields(..., schema=True)` puts a "Schema (optional)" box
on every PostgreSQL-family connection form. Nothing in the application ever
read it: grep for a consumer across `app/services` and `app/routers` returns
none. So a customer whose tables live in `sales` rather than `public` fills the
box in, and every query still resolves against the default search path and
fails with "relation does not exist" -- pointing at a table that is right there.

DirectQuery cannot work around it either: `direct_query._quote` wraps a
source_table in ONE pair of quotes, so typing `sales.orders` addresses a single
relation whose NAME contains a dot.

Found while benchmarking DirectQuery against a table in its own schema.

Three properties, and the third is the one that bites late:

  * A configured schema reaches the connection, as a search_path.
  * A schema that is not a plain identifier is REFUSED rather than
    interpolated -- the value lands in a libpq options string, and a comma or a
    space there silently changes what the connection resolves.
  * Two sources that differ ONLY by schema must not share a pooled engine. The
    registry is keyed on the built URL, which is identical for both, so without
    this the first one to connect decides the search path for the other -- a
    cross-source data leak that looks like a caching bug.
"""
import pytest

from app.services import connectors, engines


def pg(**over) -> dict:
    cfg = {"type": "postgresql", "host": "db.example", "port": 5432,
           "database": "warehouse", "username": "reader", "password": "pw"}
    cfg.update(over)
    return cfg


def test_a_configured_schema_reaches_the_connection():
    args = connectors.connect_args(pg(schema="sales"))
    assert "options" in args, "the Schema field still does nothing"
    assert "search_path" in args["options"]
    assert "sales" in args["options"]


def test_public_stays_reachable_alongside_it():
    """A schema is where the customer's tables are, not a jail.

    Dropping `public` would break anything qualified against it -- extensions
    land there by default."""
    args = connectors.connect_args(pg(schema="sales"))
    assert "public" in args["options"]


def test_no_schema_means_no_change():
    args = connectors.connect_args(pg())
    assert "options" not in args
    # The connect timeout that was already there is untouched.
    assert args.get("connect_timeout") == 8


def test_a_blank_schema_is_the_same_as_none():
    for blank in ("", "   ", None):
        assert "options" not in connectors.connect_args(pg(schema=blank))


@pytest.mark.parametrize("bad", [
    "sales,public",          # a comma adds a second entry to the search path
    "sales public",          # a space ends the option value
    'sa"les',                # quoting
    "sales;drop",
    "-csomething",           # another libpq option entirely
])
def test_a_schema_that_is_not_an_identifier_is_refused(bad):
    """Refused, not sanitised and not ignored.

    The value is interpolated into a libpq options string. Silently dropping it
    would put the customer back where they started -- a box that does nothing --
    and silently repairing it would connect them to a schema they did not name.
    """
    with pytest.raises(ValueError) as e:
        connectors.connect_args(pg(schema=bad))
    assert "schema" in str(e.value).lower()


def test_a_normal_identifier_is_accepted():
    for ok in ("sales", "Sales_2026", "_staging", "s3"):
        assert "options" in connectors.connect_args(pg(schema=ok))


def test_two_sources_differing_only_by_schema_get_different_engines():
    """The pooled-engine registry is keyed on the built URL, and these two
    build the SAME url -- so without the schema in the key they would share one
    engine, and whichever connected first would set the search path for both."""
    a = engines._engine_key(pg(schema="sales"))
    b = engines._engine_key(pg(schema="finance"))
    assert a != b


def test_no_schema_still_shares_an_engine_with_no_schema():
    """The sharing that already exists must survive: two identical configs are
    one connection identity, which is the whole point of the registry."""
    assert engines._engine_key(pg()) == engines._engine_key(pg())


def test_mysql_is_untouched():
    """MySQL has no schema separate from the database, and `options` is a libpq
    thing -- passing it to pymysql would be a TypeError on connect."""
    cfg = {"type": "mysql", "host": "db.example", "port": 3306,
           "database": "warehouse", "username": "r", "password": "p",
           "schema": "sales"}
    assert "options" not in connectors.connect_args(cfg)
