from app.models.models import DataSource


async def test_data_source_cache_ttl_defaults_to_60(db_session):
    src = DataSource(name="s1", type="postgresql", config={})
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)

    assert src.cache_ttl_seconds == 60


async def test_data_source_cache_ttl_can_be_set_to_zero_for_true_realtime(db_session):
    src = DataSource(name="s1", type="postgresql", config={}, cache_ttl_seconds=0)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)

    assert src.cache_ttl_seconds == 0
