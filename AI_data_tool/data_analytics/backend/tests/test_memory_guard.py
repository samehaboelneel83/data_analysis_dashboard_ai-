"""A dataset that does not fit in memory is refused with a sentence, before a
row is read (services/memory_guard.py)."""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import memory_guard as mg


@pytest.fixture
def parquet(tmp_path):
    path = tmp_path / "rows.parquet"
    pd.DataFrame({"a": range(5000), "b": ["some text"] * 5000}).to_parquet(path)
    return str(path)


def test_the_size_comes_from_the_footer_and_counts_the_copies(parquet):
    needed, rows = mg.estimate(parquet)
    assert rows == 5000 and needed > 0
    one = pd.read_parquet(parquet).memory_usage(deep=True).sum()
    # Within the same order as what a load really takes, and never an underestimate of one copy by much.
    assert needed > one * 0.3


def test_a_csv_is_sized_from_its_bytes(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text("a,b\n" + "1,x\n" * 1000)
    needed, rows = mg.estimate(str(path))
    assert rows is None and needed == int(path.stat().st_size * mg.CSV_FACTOR) * mg.COPIES


def test_it_refuses_when_the_load_would_not_fit_and_says_what_still_works(parquet, monkeypatch):
    monkeypatch.setattr(settings, "load_memory_share", 0.5, raising=False)
    needed, _ = mg.estimate(parquet)
    monkeypatch.setattr(mg, "free_bytes", lambda: needed)          # half of it is allowed: not enough
    with pytest.raises(mg.TooLargeToLoad) as e:
        mg.check(parquet)
    said = str(e.value)
    assert "5,000 rows" in said and "still work" in said and "live connection" in said
    monkeypatch.setattr(mg, "free_bytes", lambda: needed * 4)
    mg.check(parquet)                                              # fits: nothing happens


def test_zero_switches_it_off_and_an_unknown_machine_is_let_through(parquet, monkeypatch):
    monkeypatch.setattr(mg, "free_bytes", lambda: 1)
    monkeypatch.setattr(settings, "load_memory_share", 0.0, raising=False)
    mg.check(parquet)
    monkeypatch.setattr(settings, "load_memory_share", 0.6, raising=False)
    monkeypatch.setattr(mg, "free_bytes", lambda: None)
    mg.check(parquet)


def test_a_file_that_cannot_be_measured_is_left_to_the_load(tmp_path, monkeypatch):
    monkeypatch.setattr(mg, "free_bytes", lambda: 1)
    mg.check(str(tmp_path / "missing.parquet"))


def test_free_memory_is_read_on_this_machine():
    free = mg.free_bytes()
    assert free is None or free > 0


class TestAnImportFromADatabase:
    """Rows arriving from a source are checked against memory as they come."""

    def _engine(self, tmp_path, rows=2500):
        import sqlalchemy as sa
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'src.db'}")
        pd.DataFrame({"a": range(rows), "b": ["text " * 4] * rows}).to_sql("t", engine, index=False)
        return engine

    def test_it_stops_while_it_is_still_cheap_and_says_how_to_go_on(self, tmp_path, monkeypatch):
        from app.services import connections
        monkeypatch.setattr(settings, "load_memory_share", 0.5, raising=False)
        monkeypatch.setattr(mg, "free_bytes", lambda: 10_000)                 # almost nothing free
        with pytest.raises(connections.ImportTooLarge) as e:
            connections._capped_read("SELECT * FROM t", self._engine(tmp_path), None, 0)
        said = str(e.value)
        assert "memory" in said and "connect it live" in said and "rows" in said

    def test_what_fits_is_read_whole_and_the_row_limit_still_holds(self, tmp_path, monkeypatch):
        from app.services import connections
        monkeypatch.setattr(settings, "load_memory_share", 0.5, raising=False)
        monkeypatch.setattr(mg, "free_bytes", lambda: 10 ** 12)
        engine = self._engine(tmp_path)
        assert len(connections._capped_read("SELECT * FROM t", engine, None, 0)) == 2500
        with pytest.raises(connections.ImportTooLarge, match="import limit"):
            connections._capped_read("SELECT * FROM t", engine, None, 100)

    def test_switched_off_it_reads_as_before(self, tmp_path, monkeypatch):
        from app.services import connections
        monkeypatch.setattr(settings, "load_memory_share", 0.0, raising=False)
        monkeypatch.setattr(mg, "free_bytes", lambda: 1)
        assert len(connections._capped_read("SELECT * FROM t", self._engine(tmp_path), None, 0)) == 2500


def test_what_another_server_process_has_promised_counts_too(tmp_path, monkeypatch):
    """Two workers on one machine each saw the same free memory and each let a
    large load through alone. The promise is now written where both read it."""
    import json
    import os

    from app.services import memory_guard as mg
    ledger = tmp_path / "ledger.json"
    monkeypatch.setattr(mg, "_ledger_path", lambda: str(ledger))
    monkeypatch.setattr(mg, "free_bytes", lambda: 1000)
    monkeypatch.setattr(mg, "share", lambda: 1.0)
    monkeypatch.setattr(mg, "estimate", lambda p, columns=None: (600, 10))
    other = os.getppid()                                   # a live process that is not this one
    ledger.write_text(json.dumps({str(other): 600}))
    with pytest.raises(mg.TooLargeToLoad):
        with mg.reserved("x"):
            pass
    # A process that died without giving its bytes back is forgotten.
    ledger.write_text(json.dumps({"999999999": 600}))
    with mg.reserved("x"):
        assert json.loads(ledger.read_text()) == {str(os.getpid()): 600}
    assert json.loads(ledger.read_text()) == {}
