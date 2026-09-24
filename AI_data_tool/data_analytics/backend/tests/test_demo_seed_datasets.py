"""Tests for persisting the demo frames as real Dataset rows.

The load-bearing test here is the one about a user's own dataset that happens to
share a demo name: an implementation that cleans up by matching on `name` passes
every other test in this file and silently deletes the user's data on re-seed.
"""
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models.models import Dataset, DatasetColumn
from app.services.analytics import detect_types, load_file
from app.services.demo_content import (
    DEMO_MARKER,
    DEMO_META_KEY,
    seed_demo_datasets,
)


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    """Point settings.upload_dir at a per-test temp dir, and remove it so the
    implementation has to create it rather than assume it exists."""
    from app.core.config import settings as app_settings

    target = tmp_path / "uploads"
    monkeypatch.setattr(app_settings, "upload_dir", str(target))
    assert not target.exists()
    return target


async def _org_datasets(db_session, org_id):
    result = await db_session.execute(
        select(Dataset).where(Dataset.org_id == org_id).order_by(Dataset.id)
    )
    return result.scalars().all()


async def test_seed_creates_a_dataset_per_frame_in_the_callers_org(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    created = await seed_demo_datasets(db_session, org_id)

    assert set(created) == {"sales", "metrics", "projects", "feedback", "routes"}
    rows = await _org_datasets(db_session, org_id)
    assert len(rows) == 5
    assert {ds.org_id for ds in rows} == {org_id}


async def test_demo_rows_are_tagged_with_the_marker_in_column_meta(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    created = await seed_demo_datasets(db_session, org_id)

    for key, ds in created.items():
        assert (ds.column_meta or {}).get(DEMO_META_KEY) == DEMO_MARKER, key


async def test_seeding_twice_leaves_one_copy_not_two(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await seed_demo_datasets(db_session, org_id)
    await seed_demo_datasets(db_session, org_id)

    rows = await _org_datasets(db_session, org_id)
    assert len(rows) == 5


async def test_reseeding_does_not_leave_orphaned_column_rows(db_session, two_orgs):
    """Superseded demo datasets must take their DatasetColumn rows with them."""
    org_id = two_orgs["a"]["org"].id

    await seed_demo_datasets(db_session, org_id)
    after_one = (await db_session.execute(select(func.count(DatasetColumn.id)))).scalar_one()
    await seed_demo_datasets(db_session, org_id)
    after_two = (await db_session.execute(select(func.count(DatasetColumn.id)))).scalar_one()

    assert after_one > 0
    assert after_two == after_one


async def test_a_users_own_dataset_with_a_demo_name_survives_a_reseed(db_session, two_orgs, upload_dir):
    """Cleanup must match the marker, never the name.

    This is the test that separates a correct implementation from a plausible
    one: an implementation that deletes by name passes every other test here.
    """
    org_id = two_orgs["a"]["org"].id
    seeded = await seed_demo_datasets(db_session, org_id)
    demo_name = seeded["sales"].name

    mine_path = upload_dir / "my_own_sales.csv"
    mine_path.write_text("a,b\n1,2\n", encoding="utf-8")
    mine = Dataset(
        name=demo_name,               # same name as the demo dataset
        org_id=org_id,
        filename=str(mine_path),
        column_meta={"revenue": {"label": "Revenue"}},  # meta, but no demo marker
    )
    db_session.add(mine)
    await db_session.commit()
    mine_id = mine.id

    await seed_demo_datasets(db_session, org_id)

    survivor = await db_session.get(Dataset, mine_id)
    assert survivor is not None, "a user's own dataset was deleted by the re-seed"
    assert survivor.column_meta == {"revenue": {"label": "Revenue"}}
    assert mine_path.exists(), "the re-seed deleted a user's data file"
    rows = await _org_datasets(db_session, org_id)
    assert len(rows) == 6  # 5 demo + the user's own


async def test_demo_seeded_in_one_org_is_invisible_from_another(db_session, two_orgs):
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id

    await seed_demo_datasets(db_session, org_a)

    assert await _org_datasets(db_session, org_b) == []


async def test_each_orgs_demo_gets_its_own_files(db_session, two_orgs):
    """Two orgs must not share a CSV on disk.

    Sharing looks harmless while the frames are identical, but it means one org
    deleting its demo dataset (which unlinks the file) silently empties the
    other's. Asserting only that the files still exist after a re-seed would pass
    either way, since the re-seed rewrites the shared path.
    """
    a_seeded = await seed_demo_datasets(db_session, two_orgs["a"]["org"].id)
    b_seeded = await seed_demo_datasets(db_session, two_orgs["b"]["org"].id)

    a_files = {ds.filename for ds in a_seeded.values()}
    b_files = {ds.filename for ds in b_seeded.values()}
    assert a_files.isdisjoint(b_files)


async def test_reseeding_one_org_leaves_another_orgs_demo_alone(db_session, two_orgs):
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id
    await seed_demo_datasets(db_session, org_a)
    b_seeded = await seed_demo_datasets(db_session, org_b)
    b_ids = {ds.id for ds in b_seeded.values()}

    await seed_demo_datasets(db_session, org_a)

    b_rows = await _org_datasets(db_session, org_b)
    assert {ds.id for ds in b_rows} == b_ids
    for ds in b_rows:
        assert Path(ds.filename).exists(), "another org's demo file was deleted"


async def test_written_csv_is_readable_by_the_loader_the_app_uses(db_session, two_orgs):
    created = await seed_demo_datasets(db_session, two_orgs["a"]["org"].id)

    for key, ds in created.items():
        df = load_file(ds.filename)  # not pd.read_csv — the app's own loader
        assert len(df) == ds.row_count, key
        assert len(df.columns) == ds.col_count, key
        assert ds.row_count > 0, key


async def test_counts_and_file_size_are_recorded_the_way_an_upload_records_them(db_session, two_orgs):
    created = await seed_demo_datasets(db_session, two_orgs["a"]["org"].id)

    for key, ds in created.items():
        path = Path(ds.filename)
        assert path.exists(), key
        assert ds.file_size == path.stat().st_size, key
        df = load_file(ds.filename)
        assert ds.row_count == len(df), key
        assert ds.col_count == len(df.columns), key


async def test_column_rows_use_the_upload_paths_own_type_detection(db_session, two_orgs):
    """dtypes must equal what detect_types says about the file as written, so the
    demo can't drift from the detection real uploads get."""
    org_id = two_orgs["a"]["org"].id
    created = await seed_demo_datasets(db_session, org_id)

    for key, ds in created.items():
        expected = detect_types(load_file(ds.filename))
        result = await db_session.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
        )
        actual = {c.name: c.dtype for c in result.scalars().all()}
        assert actual == expected, key


async def test_sales_dates_survive_the_csv_round_trip_as_a_datetime_column(db_session, two_orgs):
    """The time-series widgets need `date` to come back as datetime after the
    file round-trip, not as text."""
    created = await seed_demo_datasets(db_session, two_orgs["a"]["org"].id)
    sales = created["sales"]

    result = await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == sales.id)
    )
    dtypes = {c.name: c.dtype for c in result.scalars().all()}
    assert dtypes["date"] == "datetime"
    assert dtypes["revenue"] == "numeric"
    assert dtypes["region"] == "categorical"
