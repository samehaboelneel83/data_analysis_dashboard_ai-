"""The process-local DataFrame memo: correctness properties that make it safe
to sit under every load_file caller — mutation isolation above all."""
import threading

import pandas as pd
import pytest

from app.core.config import settings
from app.services.analytics import detect_types, load_file
from app.services.frame_cache import clear_frame_cache, get_frame


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_frame_cache()
    yield
    clear_frame_cache()


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def test_hit_returns_an_equal_frame(tmp_path):
    p = _write(tmp_path / "a.csv", [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}])
    first = get_frame(p)
    second = get_frame(p)
    pd.testing.assert_frame_equal(first, second)


def test_mutation_isolation(tmp_path):
    """A caller mutating its returned frame — new column or in-place cell
    write, the way detect_types does — must never contaminate later reads."""
    p = _write(tmp_path / "b.csv", [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}])
    df = get_frame(p)
    df["x"] = 999
    df.iloc[0, df.columns.get_loc("y")] = "MUTATED"
    df["new_col"] = "junk"

    fresh = get_frame(p)
    assert list(fresh.columns) == ["x", "y"]
    assert fresh["x"].tolist() == [1, 2]
    assert fresh["y"].tolist() == ["a", "b"]


def test_rewrite_invalidates(tmp_path):
    p = _write(tmp_path / "c.csv", [{"x": 1}])
    assert get_frame(p)["x"].tolist() == [1]
    _write(tmp_path / "c.csv", [{"x": 7}, {"x": 8}])
    assert get_frame(p)["x"].tolist() == [7, 8]


def test_eviction_respects_frame_count_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frame_cache_max_frames", 2)
    paths = [_write(tmp_path / f"e{i}.csv", [{"x": i}]) for i in range(4)]
    for p in paths:
        get_frame(p)
    from app.services import frame_cache
    assert len(frame_cache._CACHE) <= 2
    # and total-bytes bookkeeping stayed consistent with what's stored
    assert frame_cache._TOTAL_BYTES == sum(s for _, s in frame_cache._CACHE.values())


def test_oversized_frame_is_served_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frame_cache_max_total_bytes", 10)  # everything is oversized
    p = _write(tmp_path / "big.csv", [{"x": 1, "y": "hello"}])
    df = get_frame(p)
    assert df["x"].tolist() == [1]
    from app.services import frame_cache
    assert len(frame_cache._CACHE) == 0


def test_kill_switch_bypasses_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frame_cache_enabled", False)
    p = _write(tmp_path / "k.csv", [{"x": 1}])
    get_frame(p)
    from app.services import frame_cache
    assert len(frame_cache._CACHE) == 0


def test_detect_types_twice_yields_identical_maps(tmp_path):
    """The real-world in-place mutator: detect_types converts date-like string
    columns on the frame it's given. Through the memo, a second load+detect
    must see pristine strings and produce the same result."""
    p = _write(tmp_path / "d.csv", [
        {"d": "2024-01-01", "v": 1.5}, {"d": "2024-02-01", "v": 2.5},
        {"d": "2024-03-01", "v": 3.5}, {"d": "2024-04-01", "v": 4.5},
        {"d": "2024-05-01", "v": 5.5},
    ])
    first = detect_types(load_file(p))
    second = detect_types(load_file(p))
    assert first == second == {"d": "datetime", "v": "numeric"}


def test_concurrent_reads_are_safe_and_equal(tmp_path):
    p = _write(tmp_path / "t.csv", [{"x": i, "y": f"row{i}"} for i in range(200)])
    frames: list[pd.DataFrame] = []
    errors: list[Exception] = []

    def read():
        try:
            frames.append(get_frame(p))
        except Exception as e:  # noqa: BLE001 — surfaced via the assert below
            errors.append(e)

    threads = [threading.Thread(target=read) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(frames) == 8
    for f in frames[1:]:
        pd.testing.assert_frame_equal(frames[0], f)


def test_cold_stampede_parses_once(tmp_path, monkeypatch):
    """28 threads hitting the same cold key elect one parser; the rest wait
    and read the stored frame. Duplicate parses of the same file version are
    the frame cache's whole reason to exist."""
    from app.services import frame_cache

    p = _write(tmp_path / "s.csv", [{"x": i} for i in range(500)])
    calls = {"n": 0}
    real_parse = frame_cache._parse

    def counting_parse(path):
        calls["n"] += 1
        return real_parse(path)

    monkeypatch.setattr(frame_cache, "_parse", counting_parse)
    frames, errors = [], []

    def read():
        try:
            frames.append(get_frame(p))
        except Exception as e:  # noqa: BLE001 -- surfaced via the assert below
            errors.append(e)

    threads = [threading.Thread(target=read) for _ in range(28)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(frames) == 28
    assert calls["n"] == 1
    for f in frames[1:]:
        pd.testing.assert_frame_equal(frames[0], f)
