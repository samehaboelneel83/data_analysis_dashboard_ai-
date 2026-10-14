from types import SimpleNamespace

import pytest

from app.services.direct_query import (
    DirectQueryUnsupported,
    build_row_fetch_sql,
    plan_row_fetch,
)


def _dataset(source_table="sales"):
    return SimpleNamespace(source_table=source_table, source_query=None, columns=[])


def test_plan_row_fetch_accepts_known_row_capped_widget_types():
    plan = plan_row_fetch({}, "bubble")
    assert plan.filters == []


@pytest.mark.parametrize("widget_type", [
    "numeric_series", "bubble", "bubble_change", "parallel_coordinates", "schedule", "vector_plot",
])
def test_plan_row_fetch_accepts_all_row_capped_widget_types(widget_type):
    plan_row_fetch({}, widget_type)


def test_plan_row_fetch_rejects_non_row_capped_widget_type():
    with pytest.raises(DirectQueryUnsupported):
        plan_row_fetch({}, "bar")


def test_plan_row_fetch_rejects_unsupported_filter_operator():
    with pytest.raises(DirectQueryUnsupported):
        plan_row_fetch({"filters": [{"column": "region", "op": "regex", "value": "e"}]}, "bubble")


def test_build_row_fetch_sql_unsampled_has_no_order_by():
    plan = plan_row_fetch({}, "bubble")
    sql, params = build_row_fetch_sql(_dataset(), plan, "postgresql", cap=1000, sampled=False)

    assert sql == 'SELECT * FROM (SELECT * FROM "sales") AS src LIMIT 1000'
    assert params == {}


def test_build_row_fetch_sql_sampled_orders_by_random_postgres():
    plan = plan_row_fetch({}, "bubble")
    sql, _ = build_row_fetch_sql(_dataset(), plan, "postgresql", cap=100, sampled=True)

    assert sql == 'SELECT * FROM (SELECT * FROM "sales") AS src ORDER BY RANDOM() LIMIT 100'


def test_build_row_fetch_sql_sampled_orders_by_rand_mysql():
    plan = plan_row_fetch({}, "bubble")
    sql, _ = build_row_fetch_sql(_dataset(), plan, "mysql", cap=100, sampled=True)

    assert "ORDER BY RAND()" in sql


def test_build_row_fetch_sql_includes_filters():
    plan = plan_row_fetch({"filters": [{"column": "region", "op": "eq", "value": "east"}]}, "bubble")
    sql, params = build_row_fetch_sql(_dataset(), plan, "postgresql", cap=1000, sampled=False)

    assert 'WHERE "region" = :f0' in sql
    assert params == {"f0": "east"}


class TestDataLimitOverride:
    """Per-object override of the system row cap (gap row: SAS's Override system data
    limit). Clamped both ways: the cap protects the SOURCE database, so an unbounded
    override would defeat its purpose."""

    def test_override_raises_the_cap(self):
        from app.services.direct_query import DEFAULT_ROW_CAP
        captured = {}
        import app.services.direct_query as dq
        original = dq._run_row_capped
        def spy(source_cfg, dataset, config, widget_type, rls, cap, **_kw):
            captured["cap"] = cap
            return {"rows": [], "total": 0}
        dq._run_row_capped = spy
        try:
            dq.run_direct_query({"type": "sqlite", "filepath": ":memory:"},
                                _spy_dataset(), {"data_limit": 25_000}, widget_type="table",
                                cache_ttl_seconds=0)
        finally:
            dq._run_row_capped = original
        assert captured["cap"] == 25_000
        assert captured["cap"] != DEFAULT_ROW_CAP

    def test_override_is_clamped_to_ten_times_the_default(self):
        import app.services.direct_query as dq
        captured = {}
        original = dq._run_row_capped
        dq._run_row_capped = lambda *a, **_kw: captured.__setitem__("cap", a[5]) or {"rows": [], "total": 0}
        try:
            dq.run_direct_query({"type": "sqlite", "filepath": ":memory:"},
                                _spy_dataset(), {"data_limit": 10_000_000}, widget_type="table",
                                cache_ttl_seconds=0)
        finally:
            dq._run_row_capped = original
        assert captured["cap"] == dq.DEFAULT_ROW_CAP * 10

    def test_a_garbage_override_falls_back_to_the_default(self):
        import app.services.direct_query as dq
        captured = {}
        original = dq._run_row_capped
        dq._run_row_capped = lambda *a, **_kw: captured.__setitem__("cap", a[5]) or {"rows": [], "total": 0}
        try:
            dq.run_direct_query({"type": "sqlite", "filepath": ":memory:"},
                                _spy_dataset(), {"data_limit": "lots"}, widget_type="table",
                                cache_ttl_seconds=0)
        finally:
            dq._run_row_capped = original
        assert captured["cap"] == dq.DEFAULT_ROW_CAP


def _spy_dataset():
    from types import SimpleNamespace
    return SimpleNamespace(source_table="t", source_query=None,
                           columns=[SimpleNamespace(name="a")])


class TestAGroupedTableReadsTheAnalysisCap:
    """Live QA 2026-10-03: a table of average price per order status, on a live
    source bigger than the 10,000-row drawing cap, gave two identical widgets
    different averages -- each a random sample. Its rows are aggregates, so it
    reads the analysis cap like a bubble chart does; a raw table keeps the
    drawing cap."""

    def _cap_for(self, config, widget_type):
        import app.services.direct_query as dq
        captured = {}
        original = dq._run_row_capped
        dq._run_row_capped = lambda *a, **_kw: captured.__setitem__("cap", a[5]) or {"rows": [], "total": 0}
        try:
            dq.run_direct_query({"type": "sqlite", "filepath": ":memory:"},
                                _spy_dataset(), config, widget_type=widget_type,
                                cache_ttl_seconds=0)
        finally:
            dq._run_row_capped = original
        return captured["cap"]

    @pytest.mark.parametrize("widget_type", ["table", "list"])
    def test_grouped_rows_are_not_sampled_at_the_drawing_cap(self, widget_type):
        from app.core.config import settings
        cap = self._cap_for({"dimension": "region", "measure": "amount",
                             "aggregation": "avg"}, widget_type)
        assert cap == int(getattr(settings, "analysis_row_cap", 250_000) or 250_000)

    def test_a_raw_table_keeps_the_drawing_cap(self):
        import app.services.direct_query as dq
        assert self._cap_for({}, "table") == dq.DEFAULT_ROW_CAP
