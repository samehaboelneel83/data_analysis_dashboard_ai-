"""A dataset's health, read off its stored profile (docs/discovery/PLAN.md §N-5)."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.services.discovery import health, profile as store

NOW = datetime(2025, 7, 2, tzinfo=timezone.utc)


def table(last="2025-06-30", per_day=20, seed=1, thin_last_month=False):
    rng = np.random.default_rng(seed)
    out = []
    for d in pd.date_range("2024-01-01", last, freq="D"):
        n = per_day if not (thin_last_month and d.strftime("%Y-%m") == "2025-06") else 3
        for _ in range(n):
            out.append((d, rng.choice(["a", "b", "c"]), float(rng.normal(100, 5)), "same"))
    return pd.DataFrame(out, columns=["when", "kind", "amount", "fixed"])


def by_id(result):
    return {c["id"]: c for c in result["checks"]}


def test_a_sound_table_passes_and_says_what_was_checked():
    df = table().drop(columns=["fixed"])
    got = health.checks(store.compute(df), "when", NOW)
    c = by_id(got)
    assert got["summary"]["status"] == "pass" and got["summary"]["fail"] == 0 and got["summary"]["warn"] == 0
    assert c["freshness"]["status"] == "pass" and c["volume"]["status"] == "pass" and c["missing"]["status"] == "pass"
    assert c["schema"]["figures"]["checked"] is False and got["summary"]["not_checked"] == 1     # nothing to compare with yet
    assert len(c["volume"]["figures"]["series"]) == 18


def test_data_that_stopped_arriving_is_late_by_its_own_rhythm():
    c = by_id(health.checks(store.compute(table(last="2025-05-10")), "when", NOW))
    # Worth a look, never a failure: nothing knows the data was meant to keep arriving.
    assert c["freshness"]["status"] == "warn" and "2025-05-10" in c["freshness"]["sentence"]
    # A yearly table is not late after two months.
    yearly = pd.DataFrame({"when": pd.to_datetime([f"{y}-05-01" for y in range(2010, 2026)]), "v": range(16)})
    assert by_id(health.checks(store.compute(yearly), "when", NOW))["freshness"]["status"] == "pass"


def test_a_month_far_below_its_history_fails_and_an_unfinished_month_is_not_judged():
    c = by_id(health.checks(store.compute(table(thin_last_month=True)), "when", NOW))
    assert c["volume"]["status"] == "fail" and c["volume"]["figures"]["month"] == "2025-06"
    assert "fewer" in c["volume"]["sentence"]
    part = by_id(health.checks(store.compute(table(last="2025-06-04")), "when", datetime(2025, 6, 5, tzinfo=timezone.utc)))
    assert part["volume"]["status"] == "pass" and part["volume"]["figures"]["month"] == "2025-05"


def test_empty_gappy_mistyped_constant_and_copied_are_each_named():
    df = table()
    df["none"] = None
    df["gaps"] = np.where(np.arange(len(df)) % 10 == 0, None, "x")
    df["mixed"] = [str(i) for i in range(len(df))]
    df.loc[df.index[:50], "mixed"] = "n/a"
    df = pd.concat([df, df.iloc[:600]], ignore_index=True)
    got = health.checks(store.compute(df), "when", NOW)
    c = by_id(got)
    assert c["missing"]["status"] == "fail" and "none" in c["missing"]["figures"]["empty"] and "gaps" in c["missing"]["figures"]["some_missing"]
    assert c["mistyped"]["status"] == "warn" and c["mistyped"]["columns"] == ["mixed"]
    assert c["constant"]["status"] == "warn" and "fixed" in c["constant"]["columns"]
    assert c["duplicates"]["status"] == "fail" and c["duplicates"]["figures"]["duplicates"] >= 600
    assert got["summary"]["status"] == "fail" and got["checks"][0]["status"] == "fail"      # worst first


def test_columns_that_went_or_changed_kind_since_last_time_are_said():
    before = store.compute(table())
    df = table().drop(columns=["kind"])
    df["amount"] = df["amount"].round().astype(str) + " units"
    df["added"] = 1.5
    now = store.compute(df)
    now["previous"] = {"measured_at": "2025-06-01T00:00:00+00:00", "rows": 1,
                       "columns": {n: st.get("kind") for n, st in before["columns"].items()}}
    s = by_id(health.checks(now, "when", NOW))["schema"]
    assert s["status"] == "warn" and s["figures"]["removed"] == ["kind"] and s["figures"]["retyped"] == ["amount"]
    assert s["figures"]["added"] == ["added"] and "2025-06-01" in s["sentence"]
    # Only new columns: said, and not a problem.
    now["previous"]["columns"] = {n: st.get("kind") for n, st in now["columns"].items() if n != "added"}
    s = by_id(health.checks(now, "when", NOW))["schema"]
    assert s["status"] == "pass" and s["figures"]["added"] == ["added"]


def test_a_reader_under_a_row_rule_gets_no_month_by_month_volume_and_no_dates():
    prof = store.for_reader(store.compute(table()), None, row_rule=True)
    c = by_id(health.checks(prof, "when", NOW))
    assert c["volume"]["figures"]["checked"] is False and c["volume"]["figures"]["series"] == []
    assert c["freshness"]["figures"]["checked"] is False
    hidden = store.for_reader({**store.compute(table()), "previous": {"measured_at": "x", "columns": {"kind": "text", "secret": "text"}}},
                              {"secret"}, False)
    assert "secret" not in hidden["previous"]["columns"]


async def test_the_columns_of_the_previous_data_are_kept_when_the_data_changes():
    """`remember` keeps what the columns were the last time the DATA differed;
    re-measuring the same data carries that yardstick forward."""
    from types import SimpleNamespace

    class Db:
        def __init__(self): self.row = None
        async def get(self, _model, _id): return self.row
        def add(self, row): self.row = row
        async def commit(self): pass
        async def rollback(self): pass

    db, ds = Db(), SimpleNamespace(id=1, filename=None, mode="import", row_count=100)
    first = store.compute(table())
    await store.remember(db, ds, first)
    assert "previous" not in db.row.body                              # measured once: nothing to compare with
    ds.row_count = 200                                               # the data changed
    second = store.compute(table().drop(columns=["kind"]))
    await store.remember(db, ds, second)
    assert db.row.body["previous"]["columns"]["kind"] == "text" and db.row.body["previous"]["rows"] == first["table"]["rows"]
    await store.remember(db, ds, store.compute(table().drop(columns=["kind"])))     # same data, measured again
    assert db.row.body["previous"]["columns"]["kind"] == "text"
    s = by_id(health.checks(store.for_reader(db.row.body), "when", NOW))["schema"]
    assert s["status"] == "warn" and s["figures"]["removed"] == ["kind"]
