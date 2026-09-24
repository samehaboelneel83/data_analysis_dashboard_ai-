"""Governed and filtered widgets on the DuckDB path.

The DuckDB shortcut was gated off by `not rls_filter_expr and not filter_expr
and not drop_columns`, so any governed widget -- exactly the ones an enterprise
runs -- fell to pandas and met the 2M-row cap. Meanwhile DirectQuery has
translated the same expressions into SQL for a year (`sql_expr`).

This wires that translator into the DuckDB plan. The contract is the one
`test_duck_agg.py` holds: DuckDB is IDENTICAL to pandas, or it does not run.

One deliberate hole, and the tests pin it: pandas keeps NaN rows under `!=`,
`not in` and `not`; SQL drops NULLs. The translator has no null handling, so
an expression with a negation is INELIGIBLE and stays on pandas rather than
being silently different. `==`, `in`, ordering and `and`/`or` yield the same
rows in both engines, nulls included, and pass through.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import duck_agg
from app.services.widget_data import (ImportRowCapExceeded, clear_widget_data_cache,
                                      get_widget_data)

BASE = {"dimension": "region", "measure": "sales", "aggregation": "sum"}


@pytest.fixture
def csv(tmp_path):
    """Nulls in the dimension AND in a text column, so null semantics are
    exercised rather than assumed. `secret` is the column security will deny."""
    rows = []
    regions = ["North", "South", None, "East"]
    for i in range(400):
        rows.append({"region": regions[i % 4], "sales": float(i % 50),
                     "tier": ["gold", None, "silver"][i % 3],
                     "secret": f"s{i}"})
    p = tmp_path / "gov.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return str(p)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


@pytest.fixture
def spy(monkeypatch):
    """Records whether DuckDB ran and, if not, why -- the test must know which
    engine produced the answer, or parity is a coin flip."""
    # Defaults say "never consulted": the gate can decline BEFORE DuckDB is
    # asked (an untranslatable expression), and that is a legitimate "did not
    # run", not a missing observation.
    seen = {"ran": False, "reason": "not consulted"}
    real = duck_agg.try_aggregate

    def _spy(*a, **kw):
        frame, reason = real(*a, **kw)
        seen["ran"] = frame is not None
        seen["reason"] = reason
        return frame, reason

    monkeypatch.setattr(duck_agg, "try_aggregate", _spy)
    return seen


def both(csv, monkeypatch, **kw):
    """The same render on both engines, values compared at rel=1e-9 the way
    test_duck_agg.py does -- two engines summing floats cannot agree bit-for-bit."""
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    clear_widget_data_cache()
    pandas_r = get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False, **kw)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    clear_widget_data_cache()
    duck_r = get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False, **kw)
    return pandas_r, duck_r


def assert_same(pandas_r, duck_r):
    # Shaped rows are {name, value}, whatever the columns were called.
    assert [r["name"] for r in pandas_r["rows"]] == [r["name"] for r in duck_r["rows"]]
    for a, b in zip(pandas_r["rows"], duck_r["rows"]):
        assert b["value"] == pytest.approx(a["value"], rel=1e-9)
    assert pandas_r["total"] == duck_r["total"]


class TestRowLevelSecurity:
    def test_rls_widget_runs_on_duckdb_and_matches_pandas(self, csv, monkeypatch, spy):
        p, d = both(csv, monkeypatch, rls_filter_expr="region == 'North'")
        assert spy["ran"], spy["reason"]
        assert_same(p, d)
        assert [r["name"] for r in d["rows"]] == ["North"]

    def test_rls_narrows_the_total_not_just_the_groups(self, csv, monkeypatch, spy):
        """`total` is source rows after every filter, the way pandas reports it."""
        _, d = both(csv, monkeypatch, rls_filter_expr="region == 'North'")
        assert spy["ran"]
        assert d["total"] == 100

    def test_a_governed_widget_over_the_cap_is_answered(self, csv, monkeypatch, spy):
        """The reason this exists. The cap bounds pandas frames; DuckDB never
        materialises one, so a governed dataset above it is now a query rather
        than a refusal -- and the answer contains only the caller's rows."""
        monkeypatch.setattr(settings, "import_row_cap", 100)
        r = get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False,
                            rls_filter_expr="region in ['North', 'South']")
        assert spy["ran"], spy["reason"]
        assert sorted(x["name"] for x in r["rows"]) == ["North", "South"]
        assert r["total"] == 200

    def test_the_same_widget_was_refused_before(self, csv, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 100)
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        with pytest.raises(ImportRowCapExceeded):
            get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False,
                            rls_filter_expr="region in ['North', 'South']")

    def test_an_untranslatable_rule_stays_on_pandas_and_fails_closed(self, csv, monkeypatch, spy):
        """pandas' apply_rls_filter returns ZERO rows for a broken rule. The
        DuckDB path must not turn that into 'no filter'."""
        p, d = both(csv, monkeypatch, rls_filter_expr="region.str.startswith('N')")
        assert not spy["ran"]
        assert d["rows"] == [] and p["rows"] == []


class TestNullSemantics:
    """Where SQL and pandas disagree, DuckDB must decline, not differ."""

    @pytest.mark.parametrize("expr", [
        "region != 'North'",
        "region not in ['North']",
        "not (region == 'North')",
        "tier != 'gold' and region == 'North'",
    ])
    def test_a_negation_is_ineligible(self, csv, monkeypatch, spy, expr):
        p, d = both(csv, monkeypatch, rls_filter_expr=expr)
        assert not spy["ran"], "DuckDB ran a negation, whose NULL rows differ from pandas"
        # The gate declines before DuckDB is consulted, so the spy holds no
        # reason -- the refusal itself is the unit, and it must name why.
        from app.services.sql_expr import (ExpressionTranslationError,
                                           translate_filter_expr_null_safe)
        with pytest.raises(ExpressionTranslationError, match="negation"):
            translate_filter_expr_null_safe(expr, {"region", "sales", "tier", "secret"})
        assert_same(p, d)   # same engine, so trivially -- pinned so a future 'fix' shows here

    @pytest.mark.parametrize("expr", [
        "region == 'North'",
        "region in ['North', 'East']",
        "sales > 10 and region == 'South'",
        "sales >= 40 or region == 'East'",
        "tier == 'gold'",
    ])
    def test_positive_forms_match_with_nulls_present(self, csv, monkeypatch, spy, expr):
        p, d = both(csv, monkeypatch, rls_filter_expr=expr)
        assert spy["ran"], spy["reason"]
        assert_same(p, d)


class TestReportFilterExpression:
    def test_filter_expr_runs_on_duckdb_and_matches(self, csv, monkeypatch, spy):
        p, d = both(csv, monkeypatch, filter_expr="sales > 20")
        assert spy["ran"], spy["reason"]
        assert_same(p, d)

    def test_rls_and_filter_expr_together(self, csv, monkeypatch, spy):
        p, d = both(csv, monkeypatch, rls_filter_expr="region == 'North'",
                    filter_expr="sales > 20")
        assert spy["ran"], spy["reason"]
        assert_same(p, d)
        assert d["total"] == sum(1 for i in range(400) if i % 4 == 0 and (i % 50) > 20)


class TestColumnSecurity:
    def test_a_denied_unrelated_column_does_not_block_duckdb(self, csv, monkeypatch, spy):
        p, d = both(csv, monkeypatch, drop_columns=["secret"])
        assert spy["ran"], spy["reason"]
        assert_same(p, d)

    def test_a_denied_dimension_is_ineligible(self, csv, monkeypatch, spy):
        """The pandas path drops the column and then refuses in its own way;
        DuckDB must not answer from a column the reader cannot see."""
        get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False,
                        drop_columns=["region"])
        assert not spy["ran"]

    def test_a_report_filter_on_a_denied_column_is_ineligible(self, csv, monkeypatch, spy):
        get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False,
                        drop_columns=["secret"], filter_expr="secret == 's1'")
        assert not spy["ran"]

    def test_an_rls_rule_on_a_hidden_column_is_evaluated_before_the_column_is_hidden(self, csv, monkeypatch):
        """The rule is the admin's predicate: it removes rows, and the reader
        never receives the column it reads. Hiding `tier` from this role must
        not turn a row rule ON `tier` into an empty widget -- DirectQuery and
        every analysis surface already evaluate it; the widget path was the
        one place that dropped the column first and so failed to zero rows.

        The gold rows are i % 3 == 0 -> 134 of 400; regions cycle i % 4, and
        the null region is not a group."""
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        r = get_widget_data(csv, dict(BASE), widget_type="bar", use_cache=False,
                            drop_columns=["tier"], rls_filter_expr="tier == 'gold'")
        assert r["total"] == 134
        assert sorted(x["name"] for x in r["rows"]) == ["East", "North", "South"]

    def test_the_hidden_column_still_never_reaches_the_reader(self, csv, monkeypatch):
        """Evaluating the rule on the hidden column must not resurrect it."""
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        r = get_widget_data(csv, {"columns": ["region", "tier", "sales"]}, widget_type="table",
                            use_cache=False, drop_columns=["tier"], rls_filter_expr="tier == 'gold'")
        assert "tier" not in r.get("columns", [])
        assert "gold" not in str(r)
        assert r["total"] == 134

    def test_an_rls_rule_on_a_hidden_column_runs_on_duckdb_and_matches_pandas(self, csv, monkeypatch, spy):
        """Parity, now in the permissive direction for both engines: the row
        rule is translated against every file column, the report filter and
        the plan against the visible ones only."""
        p, d = both(csv, monkeypatch, drop_columns=["tier"], rls_filter_expr="tier == 'gold'")
        assert spy["ran"], spy["reason"]
        assert_same(p, d)
        assert d["total"] == 134
