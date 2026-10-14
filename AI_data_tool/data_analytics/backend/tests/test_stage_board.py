"""Where things stand: rows by stage, age, on time and overdue (docs/discovery/PLAN.md §N, stage boards)."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.stage_board import StageBoardError, stage_board
from app.services.discovery import engine, profile as store


def rows(n=2000, seed=4):
    """Rows begin over six months; due 5 days later; most finish in ~4 days,
    one in ten late; the newest 6% are still going (two stages of them)."""
    rng = np.random.default_rng(seed)
    began = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 180, n)), unit="D")
    due = began + pd.Timedelta(days=5)
    took = np.where(rng.random(n) < 0.1, 9, 4)
    done = began + pd.to_timedelta(took, unit="D")
    still = np.arange(n) >= int(n * 0.94)
    state = np.where(still, np.where(np.arange(n) % 2 == 0, "moving", "waiting"), np.where(took > 5, "done late", "done"))
    df = pd.DataFrame({"began": began, "due": due, "done_on": done, "state": state,
                       "kind": rng.choice(["a", "b", "c", "d"], n), "amount": rng.normal(50, 5, n)})
    df.loc[still, "done_on"] = pd.NaT
    return df


def test_rows_by_stage_with_what_is_open_overdue_and_on_time():
    got = stage_board(rows(), "state", "began", "done_on", "due").to_dict()
    m, by = got["meta"], {r["stage"]: r for r in got["rows"]}
    assert m["rows"] == 2000 and m["open"] == 120 and m["finished"] == 1880
    assert 88 < m["on_time_pct"] < 92                                   # one in ten was late
    assert by["done"]["on_time_pct"] == 100.0 and by["done late"]["on_time_pct"] == 0.0
    assert by["moving"]["open"] == 60 and "median_age_days" in by["moving"] and by["done"]["open"] == 0
    assert 0 < m["overdue"] <= 120 and by["moving"]["overdue"] + by["waiting"]["overdue"] == m["overdue"]
    # No stored order: the stages holding open rows come first.
    assert {got["rows"][0]["stage"], got["rows"][1]["stage"]} == {"moving", "waiting"} and m["order_source"] == "open_rows"


def test_now_is_the_newest_date_in_the_data_so_an_old_file_is_not_all_overdue():
    got = stage_board(rows(), "state", "began", "done_on", "due").to_dict()
    assert got["meta"]["as_of"] <= "2025-07-10" and "not today" in got["warnings"][0]
    assert got["meta"]["overdue"] < got["meta"]["open"]                 # the newest open rows are not yet due


def test_a_stored_order_is_the_order_of_the_board():
    meta = {"state": {"level": "ordinal", "order": ["waiting", "moving", "done", "done late"]}}
    got = stage_board(rows(), "state", "began", "done_on", "due", column_meta=meta).to_dict()
    assert [r["stage"] for r in got["rows"]] == ["waiting", "moving", "done", "done late"]
    assert got["meta"]["order_source"] == "stored"


def test_without_a_finish_date_every_row_is_going_and_it_says_so():
    got = stage_board(rows(), "state", "began").to_dict()
    assert got["meta"]["open"] is None and "overdue" not in got["rows"][0]
    assert any("every row counts as still going" in w for w in got["warnings"])


def test_what_is_not_a_board_is_refused_in_plain_words():
    df = rows()
    with pytest.raises(StageBoardError, match="one value"):
        stage_board(df.assign(state="x"), "state", "began")
    with pytest.raises(StageBoardError, match="20 or fewer"):
        stage_board(df.assign(state=[str(i % 40) for i in range(len(df))]), "state", "began")
    with pytest.raises(StageBoardError, match="not in this dataset"):
        stage_board(df, "state", "began", "nope")


def test_the_columns_are_found_from_the_tables_shape_and_the_card_runs():
    df = rows()
    prof = store.compute(df)
    kinds = engine.column_kinds(prof, {})
    found = engine.stage_columns(prof, kinds, {})
    assert found["start_date"] == "began" and found["done_date"] == "done_on" and found["due_date"] == "due"
    assert found["stage_col"] in ("state", "kind")
    # A stored order (or outcome) says which category is the stage.
    assert engine.stage_columns(prof, kinds, {"state": {"order": ["waiting", "moving", "done", "done late"]}})["stage_col"] == "state"
    card = next(c for c in engine.tier0(prof, {"state": {"outcome": True}})["cards"] if c["capability"] == "stage_board")
    from app.services.analysis import registry
    out = registry.run_analysis("stage_board", df, card["action"]["params"], column_meta={})
    assert (out.to_dict() if hasattr(out, "to_dict") else out)["meta"]["open"] == 120


def test_no_board_is_offered_when_nothing_says_which_rows_are_still_going():
    df = rows().drop(columns=["done_on"])
    prof = store.compute(df)
    assert engine.stage_columns(prof, engine.column_kinds(prof, {}), {}) is None


def test_a_due_date_is_due_by_the_end_of_that_day():
    df = pd.DataFrame({"began": pd.to_datetime(["2025-01-01 09:00"] * 40), "due": pd.to_datetime(["2025-01-03"] * 40),
                       "done_on": pd.to_datetime(["2025-01-03 15:00"] * 20 + ["2025-01-04 08:00"] * 20),
                       "state": ["x"] * 20 + ["y"] * 20})
    by = {r["stage"]: r for r in stage_board(df, "state", "began", "done_on", "due").to_dict()["rows"]}
    assert by["x"]["on_time_pct"] == 100.0 and by["y"]["on_time_pct"] == 0.0
