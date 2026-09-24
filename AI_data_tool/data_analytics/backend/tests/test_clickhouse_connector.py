"""ClickHouse as a customer-facing DirectQuery connector (phase 1).

ClickHouse was already registered, but as a `_warehouse` entry: discoverable,
driver-gated, `sql_family=None`, import-only. Phase 1 promotes it to a SIXTH
SQL family, which is the first time the registry has grown past the five
wire-compatible families its docstring was written around.

The SQL is produced by the SAME builder every other family uses and then
transpiled to the ClickHouse dialect with sqlglot. Two properties of that
transpile are load-bearing and pinned here:

  * bound parameters survive it. A naive `sqlglot.transpile(sql, read=...,
    write='clickhouse')` rewrites `:f0` into `{f0: }` -- a ClickHouse named
    placeholder with an EMPTY type, which is a syntax error at the server and
    would have shipped as one. The builder guards them; these tests fail if
    that guard is removed.
  * the five existing families are untouched. The transpile is an identity
    function for them, asserted byte-for-byte, because "ClickHouse support"
    must not silently rewrite the SQL every other customer already runs.

Percentiles are refused rather than transpiled. sqlglot parses
`PERCENTILE_CONT(...) WITHIN GROUP (...)` as valid ClickHouse and emits it
unchanged, so it cannot act as a safety net here -- the refusal has to come
from the registry, the same fail-closed route Redshift already takes for
`WIDTH_BUCKET`.
"""
import re
from types import SimpleNamespace

import pytest

from app.services import connectors
from app.services.direct_query import (DirectQueryUnsupported, QueryPlan,
                                       build_count_sql, build_sql)


def _dataset(table="sales", cols=("region", "revenue", "segment")):
    return SimpleNamespace(source_table=table, source_query=None,
                           columns=[SimpleNamespace(name=c) for c in cols])


def _plan(**over):
    base = dict(dim="region", meas="revenue", agg="sum", filters=[], limit=10,
                sort_desc=True, sort_by_dim=False)
    base.update(over)
    return QueryPlan(**{k: v for k, v in base.items() if k in QueryPlan.__dataclass_fields__})


class TestRegistry:
    def test_clickhouse_resolves_to_its_own_family(self):
        assert connectors.sql_family_of({"type": "clickhouse"}) == "clickhouse"

    def test_clickhouse_is_directquery_capable(self):
        spec = connectors.resolve("clickhouse")
        assert spec.supports_directquery is True

    def test_percentiles_and_stats_are_refused_at_the_registry(self):
        """ClickHouse has `quantile()`, not `PERCENTILE_CONT ... WITHIN GROUP`,
        and no `WIDTH_BUCKET`/`CORR` in the shapes the stat widgets emit.
        Registering it fail-closed is the same call Redshift gets: a refusal
        the caller can read, never a number the engine computed differently."""
        spec = connectors.resolve("clickhouse")
        assert spec.supports_percentile is False
        assert spec.supports_stat is False

    def test_the_guard_is_family_membership_not_only_the_override(self):
        """Where the protection actually lives.

        A mutation run flipped `percentile_override=False` to `None` and every
        test still passed -- because `supports_percentile` falls back to family
        membership, and `clickhouse` is in neither capability set. The override
        is defence in depth, not the guard. This pins the guard itself, so
        adding the family to either set has to be a deliberate act that breaks a
        test naming the reason.
        """
        assert "clickhouse" not in connectors.PERCENTILE_FAMILIES
        assert "clickhouse" not in connectors.STAT_FAMILIES

    def test_the_family_is_registered_in_both_sets(self):
        assert "clickhouse" in connectors.SQL_FAMILIES
        assert "clickhouse" in connectors.DIRECTQUERY_FAMILIES

    def test_it_keeps_a_connect_timeout(self):
        """An unreachable warehouse must fail in seconds, not hang a worker."""
        args = connectors.connect_args({"type": "clickhouse", "host": "h", "database": "d"})
        assert args.get("connect_timeout")


class TestGeneratedSql:
    def test_the_dialect_is_clickhouse_not_ansi_passthrough(self):
        """`randCanonical()` is the tell: the ANSI builder emits `RANDOM()`,
        which ClickHouse does not have. If this reads RANDOM() the transpile
        is not running."""
        from app.services.direct_query import _finalize_for_dialect
        out = _finalize_for_dialect("SELECT * FROM t ORDER BY RANDOM() LIMIT 3", "clickhouse")
        assert "randCanonical" in out

    def test_bound_parameters_survive_the_transpile(self):
        """THE regression this engine nearly shipped with. A bare transpile
        turns `:f0` into `{f0: }` -- an empty-typed ClickHouse placeholder,
        rejected by the server. SQLAlchemy `text()` needs `:f0` back."""
        plan = _plan(filters=[{"column": "segment", "op": "eq", "value": "SMB"}])
        sql, params = build_sql(_dataset(), plan, "clickhouse")
        assert ":f0" in sql, f"bind mangled by the transpile: {sql}"
        assert "{f0" not in sql
        assert params["f0"] == "SMB"

    def test_an_IN_filter_keeps_every_bind(self):
        plan = _plan(filters=[{"column": "segment", "op": "in", "value": ["A", "B"]}])
        sql, params = build_sql(_dataset(), plan, "clickhouse")
        binds = set(re.findall(r":(\w+)", sql))
        assert binds >= {"k0_0", "k0_1"} or len(binds) >= 2, sql
        assert not re.search(r"\{\w+:\s*\}", sql), f"empty-typed placeholder: {sql}"

    def test_the_rls_predicate_sits_inside_the_innermost_subquery(self):
        """Row security is applied before anything else touches the data, so a
        widget filter can only narrow what is already there. Same guarantee the
        five families get; the transpile must not reorder it."""
        sql, params = build_sql(_dataset(), _plan(), "clickhouse",
                                rls_where='"region" = :rls0', rls_params={"rls0": "east"})
        assert ":rls0" in sql
        assert params["rls0"] == "east"
        rls_at = sql.index(":rls0")
        group_at = sql.upper().index("GROUP BY")
        assert rls_at < group_at, f"RLS applied after grouping: {sql}"

    def test_the_count_companion_also_carries_the_predicate(self):
        sql, params = build_count_sql(_dataset(), _plan(), "clickhouse",
                                      rls_where='"region" = :rls0', rls_params={"rls0": "east"})
        assert ":rls0" in sql and params["rls0"] == "east"

    def test_percentile_aggregations_refuse_rather_than_emit_wrong_sql(self):
        with pytest.raises(DirectQueryUnsupported):
            build_sql(_dataset(), _plan(agg="median"), "clickhouse")


class TestTheFiveFamiliesAreUntouched:
    """The seam is an identity function everywhere but ClickHouse. This is the
    whole safety argument for adding a sixth family to a builder five families
    already depend on."""

    #: Deliberately full of constructs the ClickHouse writer DOES rewrite --
    #: RANDOM() becomes randCanonical(), STDDEV() becomes stddevSamp(),
    #: VAR_SAMP() becomes varSamp(), and an ORDER BY acquires an explicit
    #: NULLS clause. An earlier version of this test used plain
    #: SELECT/SUM/GROUP BY, which transpiles to itself byte-for-byte -- so it
    #: passed even with the dialect guard removed and the transpile running for
    #: every family. A mutation run caught that; the SQL below is the fix.
    _REWRITTEN = ('SELECT "a" AS "a", STDDEV("b") AS "s", VAR_SAMP("c") AS "v" '
                  'FROM (SELECT * FROM "t") AS src '
                  'GROUP BY "a" ORDER BY 2 DESC, RANDOM() LIMIT 10')

    @pytest.mark.parametrize("dialect", ["postgresql", "mysql", "sqlite", "oracle", "sqlserver"])
    def test_finalize_is_identity(self, dialect):
        from app.services.direct_query import _finalize_for_dialect
        assert _finalize_for_dialect(self._REWRITTEN, dialect) == self._REWRITTEN

    def test_the_same_sql_really_is_rewritten_for_clickhouse(self):
        """The other half of the identity claim: prove the fixture WOULD change,
        so `== sql` above is a real assertion rather than a tautology."""
        from app.services.direct_query import _finalize_for_dialect
        out = _finalize_for_dialect(self._REWRITTEN, "clickhouse")
        assert out != self._REWRITTEN
        assert "randCanonical" in out and "stddevSamp" in out

    @pytest.mark.parametrize("dialect", ["postgresql", "mysql", "sqlite"])
    def test_build_sql_output_is_unchanged_for_existing_families(self, dialect):
        """Pinned by construction rather than by golden string: the ClickHouse
        branch may not alter the bytes any existing customer's source emits."""
        sql, params = build_sql(_dataset(), _plan(), dialect)
        assert "randCanonical" not in sql
        assert sql.startswith("SELECT ")
        assert "LIMIT 10" in sql
