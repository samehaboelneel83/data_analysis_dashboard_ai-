from app.services.direct_query import get_engine


def test_get_engine_returns_same_engine_for_identical_config():
    cfg = {"type": "sqlite", "filepath": "/tmp/whatever.db"}

    e1 = get_engine(cfg)
    e2 = get_engine(cfg)

    assert e1 is e2


def test_get_engine_returns_different_engine_for_different_config():
    e1 = get_engine({"type": "sqlite", "filepath": "/tmp/a.db"})
    e2 = get_engine({"type": "sqlite", "filepath": "/tmp/b.db"})

    assert e1 is not e2


def test_get_engine_uses_pool_pre_ping():
    engine = get_engine({"type": "sqlite", "filepath": "/tmp/pre-ping-check.db"})

    assert engine.pool._pre_ping is True
