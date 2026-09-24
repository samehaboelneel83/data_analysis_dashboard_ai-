"""DirectQuery engine pool: dedup by connection identity + bounded LRU eviction."""
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
# The engine registry moved to services/engines.py (layer 1); direct_query
# re-exports the getters, but create_engine is called there, so that is
# where a patch has to land.
from app.services import engines as dq


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    dq._ENGINE_REGISTRY.clear()
    # Every create_engine call yields a fresh mock, so identity tells engines apart
    # and we can assert dispose() without touching a real database.
    monkeypatch.setattr(dq, "create_engine", lambda url, **kw: MagicMock())
    yield
    dq._ENGINE_REGISTRY.clear()


def test_same_connection_string_shares_one_engine_despite_cosmetic_config_differences():
    a = dq.get_engine({"type": "sqlite", "filepath": "/data/x.db", "label": "one"})
    b = dq.get_engine({"type": "sqlite", "filepath": "/data/x.db", "label": "two"})
    assert a is b                                   # one pool for one connection
    assert len(dq._ENGINE_REGISTRY) == 1


def test_distinct_connections_get_distinct_engines():
    a = dq.get_engine({"type": "sqlite", "filepath": "/data/a.db"})
    b = dq.get_engine({"type": "sqlite", "filepath": "/data/b.db"})
    assert a is not b
    assert len(dq._ENGINE_REGISTRY) == 2


def test_in_memory_sources_never_share_an_engine():
    # Each :memory: database is distinct; sharing would merge their data.
    a = dq.get_engine({"type": "sqlite", "filepath": ":memory:", "k": 1})
    b = dq.get_engine({"type": "sqlite", "filepath": ":memory:", "k": 2})
    assert a is not b


def test_engine_key_normalizes_connection_but_isolates_memory():
    k1 = dq._engine_key({"type": "sqlite", "filepath": "/x.db", "a": 1})
    k2 = dq._engine_key({"type": "sqlite", "filepath": "/x.db", "a": 2})
    assert k1 == k2 and k1.startswith("url:")        # cosmetic fields don't split the pool
    m1 = dq._engine_key({"type": "sqlite", "filepath": ":memory:", "a": 1})
    m2 = dq._engine_key({"type": "sqlite", "filepath": ":memory:", "a": 2})
    assert m1 != m2 and m1.startswith("cfg:")        # in-memory stays per-source


def test_lru_evicts_and_disposes_beyond_the_cap(monkeypatch):
    monkeypatch.setattr(settings, "directquery_engine_pool_maxsize", 2)
    e1 = dq.get_engine({"type": "sqlite", "filepath": "/1.db"})
    dq.get_engine({"type": "sqlite", "filepath": "/2.db"})
    dq.get_engine({"type": "sqlite", "filepath": "/3.db"})     # evicts the LRU (e1)
    assert len(dq._ENGINE_REGISTRY) == 2
    e1.dispose.assert_called_once()                            # evicted pool is closed


def test_recently_used_engine_is_not_the_one_evicted(monkeypatch):
    monkeypatch.setattr(settings, "directquery_engine_pool_maxsize", 2)
    a = dq.get_engine({"type": "sqlite", "filepath": "/a.db"})
    b = dq.get_engine({"type": "sqlite", "filepath": "/b.db"})
    dq.get_engine({"type": "sqlite", "filepath": "/a.db"})     # touch A -> now MRU
    dq.get_engine({"type": "sqlite", "filepath": "/c.db"})     # should evict B, not A
    a.dispose.assert_not_called()
    b.dispose.assert_called_once()
