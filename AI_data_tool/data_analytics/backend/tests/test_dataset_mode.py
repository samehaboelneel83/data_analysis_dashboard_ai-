from app.models.models import Dataset


async def test_dataset_mode_defaults_to_import(db_session):
    ds = Dataset(name="d1")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    assert ds.mode == "import"


async def test_dataset_mode_can_be_set_to_directquery(db_session):
    ds = Dataset(name="d1", mode="directquery")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    assert ds.mode == "directquery"
