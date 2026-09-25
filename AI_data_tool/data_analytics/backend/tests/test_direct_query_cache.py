import time
from types import SimpleNamespace

from app.services.direct_query import _directquery_cache_key


def _dataset(data_source_id=1, source_table="sales", source_query=None):
    return SimpleNamespace(data_source_id=data_source_id, source_table=source_table, source_query=source_query)


def test_cache_key_is_stable_for_identical_inputs():
    k1 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "bar", None, 60)
    k2 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "bar", None, 60)
    assert k1 == k2


def test_cache_key_differs_by_rls_filter_expr():
    """Load-bearing for RLS isolation, mirroring widget_data._widget_data_cache_key's
    own guarantee: two roles with different RLS expressions must never share a cache
    entry, and a fail-closed empty/error result for one role must never be served to
    a different role whose expression is valid."""
    k1 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "bar", "region == 'east'", 60)
    k2 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "bar", "region == 'west'", 60)
    k3 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "bar", None, 60)
    assert len({k1, k2, k3}) == 3


def test_cache_key_differs_by_data_source_id():
    """A file-based (import) and DirectQuery entry must never collide, and neither
    should two DirectQuery datasets pointed at different sources."""
    k1 = _directquery_cache_key({}, _dataset(data_source_id=1), {}, "bar", None, 60)
    k2 = _directquery_cache_key({}, _dataset(data_source_id=2), {}, "bar", None, 60)
    assert k1 != k2


def test_cache_key_differs_by_source_table_or_query():
    k1 = _directquery_cache_key({}, _dataset(source_table="sales"), {}, "bar", None, 60)
    k2 = _directquery_cache_key({}, _dataset(source_table="orders"), {}, "bar", None, 60)
    k3 = _directquery_cache_key({}, _dataset(source_table=None, source_query="SELECT * FROM sales"), {}, "bar", None, 60)
    assert len({k1, k2, k3}) == 3


def test_cache_key_differs_by_config_or_widget_type():
    k1 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "bar", None, 60)
    k2 = _directquery_cache_key({}, _dataset(), {"dimension": "product"}, "bar", None, 60)
    k3 = _directquery_cache_key({}, _dataset(), {"dimension": "region"}, "line", None, 60)
    assert len({k1, k2, k3}) == 3


def test_cache_key_differs_by_row_cap():
    """row_cap affects the actual query (LIMIT n) and therefore the result --
    two calls with different caps must never share a cache entry."""
    k1 = _directquery_cache_key({}, _dataset(), {}, "numeric_series", None, 60, row_cap=100)
    k2 = _directquery_cache_key({}, _dataset(), {}, "numeric_series", None, 60, row_cap=5)
    assert k1 != k2


def test_cache_key_changes_across_ttl_buckets():
    now = 16_666 * 60.0  # bucket-aligned, so +30 stays in-bucket and +61 rolls over
    k_bucket_a = _directquery_cache_key({}, _dataset(), {}, "bar", None, 60, now=now)
    k_bucket_a_again = _directquery_cache_key({}, _dataset(), {}, "bar", None, 60, now=now + 30)
    k_bucket_b = _directquery_cache_key({}, _dataset(), {}, "bar", None, 60, now=now + 61)
    assert k_bucket_a == k_bucket_a_again  # same 60s bucket
    assert k_bucket_a != k_bucket_b        # rolled into the next bucket


def test_key_differs_by_denied_columns():
    # Two roles with different column rules must never share a cached result.
    k1 = _directquery_cache_key({}, _dataset(), {}, "table", None, 60)
    k2 = _directquery_cache_key({}, _dataset(), {}, "table", None, 60, drop_columns=["salary"])
    k3 = _directquery_cache_key({}, _dataset(), {}, "table", None, 60, drop_columns=["salary"])
    assert k1 != k2
    assert k2 == k3
