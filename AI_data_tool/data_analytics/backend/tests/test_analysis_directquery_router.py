import sqlite3

import pytest

from app.models.models import DataSource, Dataset, DatasetColumn
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


async def _seed_data_source(db_session, org_id, name="Live DB", type_="sqlite", config=None):
    src = DataSource(name=name, type=type_, config=config or {}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()
    return src


def _seed_sqlite_sales_db(tmp_path, rows=(("east", 100), ("east", 50), ("west", 30))):
    db_path = tmp_path / "sales.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany("INSERT INTO sales (region, revenue) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()
    return str(db_path)


async def _seed_directquery_dataset(db_session, org_id, data_source_id, source_table="sales",
                                     columns=("region", "revenue")):
    ds = Dataset(
        name="DQ Dataset", org_id=org_id, mode="directquery",
        data_source_id=data_source_id, source_table=source_table,
    )
    db_session.add(ds)
    await db_session.flush()
    for col in columns:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype="string"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_analysis_directquery_returns_sample_based_stats(client, db_session, two_orgs, auth_headers, tmp_path):
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={"analysis_type": "full"}, headers=auth_headers["a"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["overview"]["rows"] == 3
    assert body["sampled"] is False
    assert body["total_rows"] == 3


# ── The frame an ANALYSIS gets, as opposed to a preview ──────────────────────
#
# Every DirectQuery branch in routers/analysis.py fetched through
# `run_direct_query(widget_type="table")`, whose job is to fill a preview grid.
# It returned 50 rows. The analyses were not refused on DirectQuery -- they were
# quietly answered from 50 rows and presented as describing the dataset, which
# is a different answer rather than a rougher one, with nothing on screen saying
# so. These pin the replacement.

@pytest.mark.asyncio
async def test_the_analysis_frame_is_the_whole_table_not_a_preview(
        db_session, two_orgs, tmp_path):
    from app.services.analysis_frame import load_directquery_frame

    org = two_orgs["a"]["org"]
    rows = [("east", i) for i in range(400)]
    path = _seed_sqlite_sales_db(tmp_path, rows=tuple(rows))
    src = await _seed_data_source(db_session, org.id, config={"filepath": str(path)})
    ds = await _seed_directquery_dataset(db_session, org.id, src.id)

    live = await load_directquery_frame(db_session, ds)
    assert live.rows_analysed == 400, "a preview-sized frame is the defect this fixes"
    assert live.total_rows == 400
    assert live.sampled is False
    assert live.exact is True


@pytest.mark.asyncio
async def test_over_the_cap_it_samples_and_says_so(db_session, two_orgs, tmp_path):
    """A figure drawn from part of the data must never be presented as though it
    came from all of it. `insights.py` promises every number is computed rather
    than guessed; that only stays true if a sampled number says it is one."""
    from app.services.analysis_frame import load_directquery_frame

    org = two_orgs["a"]["org"]
    rows = [("east", i) for i in range(300)]
    path = _seed_sqlite_sales_db(tmp_path, rows=tuple(rows))
    src = await _seed_data_source(db_session, org.id, config={"filepath": str(path)})
    ds = await _seed_directquery_dataset(db_session, org.id, src.id)

    live = await load_directquery_frame(db_session, ds, row_cap=100)
    assert live.sampled is True
    assert live.exact is False
    assert live.rows_analysed == 100
    assert live.total_rows == 300
    assert "sample" in live.describe().lower()
    assert "300" in live.describe()


@pytest.mark.asyncio
async def test_it_says_how_much_it_measured_in_words_a_person_can_read(
        db_session, two_orgs, tmp_path):
    from app.services.analysis_frame import load_directquery_frame

    org = two_orgs["a"]["org"]
    path = _seed_sqlite_sales_db(tmp_path, rows=(("east", 1), ("west", 2)))
    src = await _seed_data_source(db_session, org.id, config={"filepath": str(path)})
    ds = await _seed_directquery_dataset(db_session, org.id, src.id)

    live = await load_directquery_frame(db_session, ds)
    assert live.describe() == "Measured live over all 2 rows."


@pytest.mark.asyncio
async def test_a_denied_column_never_reaches_the_frame(db_session, two_orgs, tmp_path):
    """Column security is not weakened by reading live. The fetch is SELECT * by
    design -- shapers ignore what they do not need -- so the drop happens on
    arrival, exactly as the import path drops it from its own frame."""
    from app.services.analysis_frame import load_directquery_frame

    org = two_orgs["a"]["org"]
    path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org.id, config={"filepath": str(path)})
    ds = await _seed_directquery_dataset(db_session, org.id, src.id)

    live = await load_directquery_frame(db_session, ds, denied={"amount"})
    assert "amount" not in live.frame.columns
    assert "region" in live.frame.columns


@pytest.mark.asyncio
async def test_a_dataset_with_no_connection_refuses_with_a_readable_reason(
        db_session, two_orgs):
    from app.services.analysis_frame import FrameUnavailable, load_directquery_frame

    ds = Dataset(name="orphan", org_id=two_orgs["a"]["org"].id, mode="directquery")
    db_session.add(ds)
    await db_session.flush()

    with pytest.raises(FrameUnavailable) as excinfo:
        await load_directquery_frame(db_session, ds)
    assert "no connection" in str(excinfo.value).lower()


def test_an_imported_frame_is_never_reported_as_sampled():
    import pandas as pd

    from app.services.analysis_frame import imported_frame

    got = imported_frame(pd.DataFrame({"a": [1, 2, 3]}))
    assert got.origin == "import"
    assert got.sampled is False
    assert got.describe() == "Measured over all 3 rows."
