"""A large import from a database is written to disk as it arrives
(services/connections.Streamed): memory stays at about one chunk, and the
result is the same rows an in-memory import would have given."""
import pandas as pd
import pytest
import sqlalchemy as sa

from app.core.config import settings
from app.services import connections
from app.services import memory_guard as mg


@pytest.fixture
def source(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'src.db'}")
    n = 2600
    pd.DataFrame({"id": range(n), "grp": [f"g{i % 7}" for i in range(n)],
                  "amount": [i * 1.5 if i % 50 else None for i in range(n)],
                  # numbers for the first two thousand rows, then text: the type changes part-way
                  "code": [i if i < 2000 else f"x{i}" for i in range(n)]}).astype({"code": "object"}).to_sql(
        "t", engine, index=False)
    return engine


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch):
    monkeypatch.setattr(connections, "CHUNK_ROWS", 500)
    monkeypatch.setattr(settings, "import_stream_rows", 1000, raising=False)
    monkeypatch.setattr(mg, "free_bytes", lambda: 10 ** 12)


def test_past_the_threshold_the_rows_go_to_disk_and_none_is_lost(source, tmp_path):
    got = connections._capped_read("SELECT * FROM t ORDER BY id", source, None, 0, stream_dir=str(tmp_path))
    assert isinstance(got, connections.Streamed) and got.rows == 2600
    assert got.columns == ["id", "grp", "amount", "code"]
    back = pd.read_parquet(got.path)
    whole = pd.read_sql("SELECT * FROM t ORDER BY id", source)
    assert len(back) == 2600 and back["id"].tolist() == whole["id"].tolist()          # the order it arrived in
    assert back["amount"].isna().sum() == whole["amount"].isna().sum() == 52
    assert abs(back["amount"].sum() - whole["amount"].sum()) < 1e-6
    # How empty each column is was counted on every row.
    assert got.missing == {"id": 0.0, "grp": 0.0, "amount": 2.0, "code": 0.0}
    # Nothing is left behind but the file.
    assert sorted(p.name for p in tmp_path.iterdir() if p.name != "src.db") == ["import.parquet"]


def test_a_column_that_changes_its_type_part_way_keeps_every_value_as_text(source, tmp_path):
    got = connections._capped_read("SELECT * FROM t ORDER BY id", source, None, 0, stream_dir=str(tmp_path))
    back = pd.read_parquet(got.path)
    assert back["code"].isna().sum() == 0
    assert str(back["code"].iloc[5]) in ("5", "5.0") and back["code"].iloc[-1] == "x2599"


def test_below_the_threshold_an_import_is_a_frame_as_it_always_was(source, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "import_stream_rows", 5000, raising=False)
    got = connections._capped_read("SELECT * FROM t", source, None, 0, stream_dir=str(tmp_path))
    assert isinstance(got, pd.DataFrame) and len(got) == 2600
    # ...and without a folder to write in, or with streaming switched off, too.
    monkeypatch.setattr(settings, "import_stream_rows", 1000, raising=False)
    assert isinstance(connections._capped_read("SELECT * FROM t", source, None, 0), pd.DataFrame)
    monkeypatch.setattr(settings, "import_stream_rows", 0, raising=False)
    assert isinstance(connections._capped_read("SELECT * FROM t", source, None, 0, stream_dir=str(tmp_path)), pd.DataFrame)


def test_the_row_limit_still_stops_a_streamed_import(source, tmp_path):
    with pytest.raises(connections.ImportTooLarge, match="import limit"):
        connections._capped_read("SELECT * FROM t", source, None, 2000, stream_dir=str(tmp_path))


def test_each_chunk_is_prepared_before_it_is_written_and_memory_is_not_what_limits_it(source, tmp_path, monkeypatch):
    seen = []

    def prepare(chunk):
        seen.append(len(chunk))
        chunk["grp"] = chunk["grp"].str.upper()
        return chunk
    # Almost no memory "free": an in-memory import of this would be refused; a streamed one is not.
    monkeypatch.setattr(settings, "load_memory_share", 0.5, raising=False)
    monkeypatch.setattr(mg, "free_bytes", lambda: 400_000)
    got = connections._capped_read("SELECT * FROM t ORDER BY id", source, None, 0, stream_dir=str(tmp_path),
                                   prepare=prepare)
    assert isinstance(got, connections.Streamed) and sum(seen) == 2600 and max(seen) <= 500
    assert set(pd.read_parquet(got.path)["grp"].unique()) == {f"G{i}" for i in range(7)}


def test_the_sample_is_bounded_and_the_same_every_time(source, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "discovery_sample_rows", 300, raising=False)
    a = connections._capped_read("SELECT * FROM t ORDER BY id", source, None, 0, stream_dir=str(tmp_path / "a"))
    b = connections._capped_read("SELECT * FROM t ORDER BY id", source, None, 0, stream_dir=str(tmp_path / "b"))
    assert len(a.sample) == 300 and a.sample["id"].tolist() == b.sample["id"].tolist()
