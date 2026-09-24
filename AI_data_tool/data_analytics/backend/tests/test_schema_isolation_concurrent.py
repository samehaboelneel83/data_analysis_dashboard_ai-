"""Two sources on one database, different schemas, under concurrency.

The pooled-engine registry hands out one engine per connection identity. Two
sources that differ only by schema build a byte-identical URL, and until
2026-09-12 shared one engine -- whichever connected first set the search path
for both. `test_source_schema.py` pins the key; this pins what the key is FOR:
under a thread storm alternating the two sources, every engine handed to A is
the same one, every engine handed to B is the same one, and the two sets never
touch. The live search_path itself was proved against a real Postgres (12
groups with the schema, UndefinedTable without); the suite runs on SQLite, so
what it can hold is the identity contract the search_path rides on.
"""
import threading

from app.services import engines


def cfg(schema: str) -> dict:
    return {"type": "postgresql", "host": "db.example", "port": 5432,
            "database": "warehouse", "username": "r", "password": "p",
            "schema": schema}


def test_alternating_sources_never_share_an_engine():
    a, b = cfg("sales"), cfg("finance")
    seen = {"sales": set(), "finance": set()}
    lock = threading.Lock()

    def worker(n: int) -> None:
        for i in range(60):
            c = a if (i + n) % 2 == 0 else b
            e = engines.get_engine(c)
            with lock:
                seen[c["schema"]].add(id(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # One engine per source across 480 interleaved calls, and never the same one.
    assert len(seen["sales"]) == 1, seen
    assert len(seen["finance"]) == 1, seen
    assert seen["sales"].isdisjoint(seen["finance"])


def test_the_same_source_twice_is_one_engine():
    """The sharing the registry exists for must survive the schema key."""
    assert engines.get_engine(cfg("sales")) is engines.get_engine(cfg("sales"))
