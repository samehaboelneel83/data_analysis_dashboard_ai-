"""The same work asked for by several people at once is done once
(services/single_flight.py), and concurrent loads are weighed together
(services/memory_guard.reserved)."""
import threading
import time

import pandas as pd
import pytest

from app.core.config import settings
from app.services import memory_guard as mg
from app.services import single_flight as sf


def _together(n, fn):
    out, errors = [None] * n, []
    start = threading.Barrier(n)

    def go(i):
        start.wait()
        try:
            out[i] = fn(i)
        except Exception as e:                              # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    return out, errors


def test_identical_requests_arriving_together_are_computed_once_and_each_gets_its_own_copy():
    ran = []

    def work():
        ran.append(1)
        time.sleep(0.3)
        return {"rows": [1, 2, 3]}
    out, errors = _together(8, lambda i: sf.run("same", work))
    assert not errors and len(ran) == 1
    assert all(o == {"rows": [1, 2, 3]} for o in out)
    out[0]["rows"].append(4)                               # one reader's copy is not another's
    assert out[1] == {"rows": [1, 2, 3]}


def test_different_requests_are_not_shared_and_nothing_is_kept_afterwards():
    ran = []
    out, _ = _together(4, lambda i: sf.run(f"k{i}", lambda: ran.append(i) or i))
    assert sorted(out) == [0, 1, 2, 3] and len(ran) == 4
    assert sf.run("same-again", lambda: 1) == 1 and sf.run("same-again", lambda: 2) == 2   # not a cache


def test_when_the_first_fails_the_others_compute_for_themselves():
    calls = []

    def work():
        calls.append(1)
        time.sleep(0.2)
        if len(calls) == 1:
            raise ValueError("the first one failed")
        return "ok"
    out, errors = _together(3, lambda i: sf.run("flaky", work))
    assert len(errors) == 1 and sorted(o for o in out if o) == ["ok", "ok"]


def test_no_key_means_never_shared():
    ran = []
    _together(3, lambda i: sf.run(None, lambda: ran.append(1) or time.sleep(0.1)))
    assert len(ran) == 3 and sf.key_of(object()) is not None and sf.key_of({"a": 1}) == sf.key_of({"a": 1})


def test_a_chart_asked_for_by_many_at_once_is_drawn_once(tmp_path, monkeypatch):
    from app.services import widget_data as wd
    path = tmp_path / "d.csv"
    pd.DataFrame({"g": ["a", "b"] * 50, "v": range(100)}).to_csv(path, index=False)
    ran = []
    real = wd._get_widget_data

    def slow(*a, **k):
        ran.append(1)
        time.sleep(0.3)
        return real(*a, **k)
    monkeypatch.setattr(wd, "_get_widget_data", slow)
    config = {"dimension": "g", "measure": "v", "aggregation": "sum"}
    out, errors = _together(6, lambda i: wd.get_widget_data(str(path), config, "bar", use_cache=False))
    assert not errors and len(ran) == 1
    assert all(o["rows"] == out[0]["rows"] for o in out)


def test_loads_in_progress_are_weighed_together(tmp_path, monkeypatch):
    path = tmp_path / "rows.parquet"
    pd.DataFrame({"a": range(5000), "b": ["text"] * 5000}).to_parquet(path)
    needed, _ = mg.estimate(str(path))
    monkeypatch.setattr(settings, "load_memory_share", 1.0, raising=False)
    monkeypatch.setattr(mg, "free_bytes", lambda: int(needed * 2.5))        # room for two, not three
    with mg.reserved(str(path)):
        with mg.reserved(str(path)):
            with pytest.raises(mg.TooLargeToLoad):
                with mg.reserved(str(path)):
                    pass
        with mg.reserved(str(path)):                       # one finished: there is room again
            pass
    assert mg._RESERVED == 0


def test_across_processes_a_second_asker_waits_for_the_first_then_finds_its_answer(monkeypatch):
    """Two server processes share no memory, only the shared store: the second
    waits while the first holds the key, then runs -- by which time the first
    has put its answer in the shared result cache."""
    import threading
    import time

    import fakeredis

    from app.services import single_flight as sf
    store = fakeredis.FakeRedis()
    monkeypatch.setattr(sf, "_shared", lambda: store)
    cache, order, started = {}, [], threading.Event()

    def work(who):
        def fn():
            if "answer" in cache:                      # the shared result cache
                order.append(f"{who} read")
                return cache["answer"]
            order.append(f"{who} computes")
            started.set()
            time.sleep(0.3)
            cache["answer"] = 42
            return 42
        return fn

    before = sf.waited_across
    first = threading.Thread(target=lambda: sf._across("k", work("first")))
    first.start()
    started.wait(2)
    assert sf._across("k", work("second")) == 42      # "another process": straight to the shared store
    first.join()
    assert order == ["first computes", "second read"] and sf.waited_across == before + 1
    assert not store.exists("sf:k")                    # the key is given back


def test_a_shared_store_that_fails_never_stops_an_answer(monkeypatch):
    from app.services import single_flight as sf

    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")
    monkeypatch.setattr(sf, "_shared", lambda: Broken())
    assert sf.run("k2", lambda: 7) == 7
