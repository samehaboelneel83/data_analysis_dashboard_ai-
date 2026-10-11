"""Reloading a dataset that was imported as a stream (its file is parquet):
the reload is written to disk as it arrives and swapped in, never CSV text
under a parquet name, and what the callers count is the whole file."""
import pandas as pd
import pytest
import sqlalchemy as sa

from app.core.config import settings
from app.services import connections, data_checks, dataset_refresh as dr
from app.services import memory_guard as mg

N = 2600


@pytest.fixture
def source(tmp_path, monkeypatch):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'src.db'}")
    pd.DataFrame({"id": range(N), "grp": [f"g{i % 7}" for i in range(N)],
                  "amount": [i * 1.5 if i % 50 else None for i in range(N)]}).to_sql("t", engine, index=False)
    monkeypatch.setattr(connections, "CHUNK_ROWS", 500)
    monkeypatch.setattr(settings, "import_stream_rows", 1000, raising=False)
    monkeypatch.setattr(mg, "free_bytes", lambda: 10 ** 12)

    def fake(cfg, table, query, params=None, *, stream_dir=None, prepare=None):
        return connections._capped_read(query, engine, params, 0, stream_dir=stream_dir, prepare=prepare)
    monkeypatch.setattr(connections, "import_to_dataframe", fake)
    return engine


def live(tmp_path, suffix):
    folder = tmp_path / "data"
    folder.mkdir()
    path = folder / f"abc_import{suffix}"
    pd.DataFrame({"id": [1], "grp": ["old"], "amount": [1.0]}).to_parquet(path) if suffix == ".parquet" \
        else pd.DataFrame({"id": [1], "grp": ["old"], "amount": [1.0]}).to_csv(path, index=False)
    return path


def test_a_full_reload_of_a_streamed_dataset_is_streamed_and_counts_every_row(source, tmp_path):
    path = live(tmp_path, ".parquet")
    out = dr.refresh_dataset({}, str(path), None, "SELECT * FROM t ORDER BY id", "full", "id", None)
    df = out["df"]
    assert dr.rows_of(df) == N == out["rows_added"] and dr.missing_of(df, "amount") == 2.0
    assert out["cursor_value"] == str(N - 1) and out["mode"] == "full"
    back = pd.read_parquet(path)                      # a parquet file, with every row
    assert len(back) == N and back["id"].tolist() == list(range(N))
    # Nothing is left beside it.
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_deferred_write_leaves_the_live_file_until_the_caller_swaps_it_in(source, tmp_path):
    path = live(tmp_path, ".parquet")
    out = dr.refresh_dataset({}, str(path), None, "SELECT * FROM t", "full", None, None, write=False)
    assert len(pd.read_parquet(path)) == 1            # still the old data
    dr.write_dataset_files(out["df"], str(path))
    assert len(pd.read_parquet(path)) == N
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_blocked_or_broken_reload_keeps_the_old_file_and_leaves_nothing_behind(source, tmp_path):
    path = live(tmp_path, ".parquet")
    seen = {}

    def validate(df):
        seen["rows"] = dr.rows_of(df)
        raise data_checks.ChecksBlocked([])
    with pytest.raises(data_checks.ChecksBlocked):
        dr.rewrite_dataset_file({}, str(path), None, "SELECT * FROM t", validate=validate)
    assert seen["rows"] == N and len(pd.read_parquet(path)) == 1
    with pytest.raises(dr.SchemaBreak):
        dr.rewrite_dataset_file({}, str(path), None, "SELECT * FROM t", required_columns={"gone"})
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_what_an_abandoned_reload_left_is_cleared_by_the_next_one(source, tmp_path):
    path = live(tmp_path, ".parquet")
    dr.refresh_dataset({}, str(path), None, "SELECT * FROM t", "full", None, None, write=False)   # never written
    assert len(list(path.parent.iterdir())) == 2
    dr.rewrite_dataset_file({}, str(path), None, "SELECT * FROM t")
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_renamed_column_is_mapped_back_in_a_streamed_reload(source, tmp_path):
    path = live(tmp_path, ".parquet")
    out = dr.refresh_dataset({}, str(path), None, "SELECT id, grp AS team, amount FROM t", "full", None, None,
                             required_columns={"grp"}, column_map={"team": "grp"})
    assert list(pd.read_parquet(path).columns) == ["id", "grp", "amount"] and dr.rows_of(out["df"]) == N


def test_a_small_reload_of_a_parquet_dataset_is_still_parquet(source, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "import_stream_rows", 50_000, raising=False)
    path = live(tmp_path, ".parquet")
    out = dr.refresh_dataset({}, str(path), None, "SELECT * FROM t", "full", None, None)
    assert "rows" not in out["df"].attrs and len(pd.read_parquet(path)) == N
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_a_csv_dataset_reloads_as_it_always_did(source, tmp_path):
    path = live(tmp_path, ".csv")
    out = dr.refresh_dataset({}, str(path), None, "SELECT * FROM t", "full", None, None)
    assert len(out["df"]) == N and len(pd.read_csv(path)) == N


def test_adding_rows_to_a_file_too_large_for_memory_reloads_it_whole_and_says_so(source, tmp_path, monkeypatch):
    path = live(tmp_path, ".parquet")

    class Refuse:
        def __enter__(self):
            raise mg.TooLargeToLoad(10 ** 12, 10 ** 9)

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(mg, "reserved", lambda p: Refuse())
    out = dr.refresh_dataset({}, str(path), None, "SELECT * FROM t", "incremental", "id", "5")
    assert out["mode"] == "full" and "too large" in out["warning"] and len(pd.read_parquet(path)) == N


def test_checks_on_a_streamed_reload_use_the_whole_files_row_count(source):
    sample = pd.DataFrame({"id": [1, 2, 3], "amount": [1.0, 2.0, 3.0]})
    sample.attrs.update(rows=900, missing={"id": 0.0, "amount": 2.0})
    checks = [{"id": 1, "kind": "row_count", "params": {"min": 500}, "severity": "block"},
              {"id": 2, "kind": "row_drop", "params": {"max_drop_pct": 5}, "severity": "block"},
              {"id": 3, "kind": "not_null", "column": "amount", "severity": "warn"}]
    by = {r["id"]: r for r in data_checks.evaluate(sample, checks, previous_rows=1000)}
    assert by[1]["passed"] and by[1]["sampled"] == 3
    assert not by[2]["passed"] and "1,000 to 900" in by[2]["detail"]
    # Blanks the sample happened to miss are still counted.
    assert not by[3]["passed"] and by[3]["failing"] == 18 and "of 900 rows" in by[3]["detail"]
