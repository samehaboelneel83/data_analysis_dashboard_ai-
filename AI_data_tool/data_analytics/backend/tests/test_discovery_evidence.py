"""A look at the rows before a card is offered (docs/discovery/PLAN.md §X-1)."""
import numpy as np
import pandas as pd

from app.services.discovery import engine, evidence, profile as store


def cards_of(df, meta=None):
    return engine.tier0(store.compute(df), meta or {})["cards"]


def looked(df, meta=None):
    kept, withheld = evidence.look(cards_of(df, meta), df, meta or {})
    return kept, withheld


def events(habit=True, seed=4):
    rng = np.random.default_rng(seed)
    when = pd.date_range("2024-01-01", "2025-06-30 23:00", freq="h")
    busy = (when.dayofweek == 3) & (when.hour == 9) if habit else np.zeros(len(when), dtype=bool)
    return pd.DataFrame({"when": when, "amount": np.where(busy, 80.0, 10.0) + rng.random(len(when)) * 0.2})


def grid(cards):
    return next((c for c in cards if (c["action"].get("config") or {}).get("dimension2_granularity") == "hour_of_day"), None)


def test_a_weekly_rhythm_is_kept_with_what_was_found():
    kept, _ = looked(events())
    g = grid(kept)
    assert g["evidence"]["kind"] == "rhythm" and g["evidence"]["figures"]["busiest_day"] == "Thu"
    assert g["evidence"]["figures"]["busiest_hour"] == 9 and "Busiest on Thu" in g["found"] and g["why"]["reason"] == "evidence"


def test_a_table_with_no_rhythm_gets_no_weekday_grid_and_is_told_why():
    kept, withheld = looked(events(habit=False))
    assert grid(kept) is None
    assert any("no rhythm" in w["reason"] for w in withheld)


def seasonal(season=True):
    rng = np.random.default_rng(2)
    days = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    level = np.where(days.month == 12, 3.0, 1.0) if season else np.ones(len(days))
    return pd.DataFrame({"when": days, "amount": 100.0 * level + rng.normal(0, 1, len(days))})


def test_a_month_that_runs_high_every_year_is_evidence_and_a_flat_year_is_just_a_chart():
    kept, _ = looked(seasonal())
    yearly = [c for c in kept if (c["action"].get("config") or {}).get("dimension2_granularity") in ("year", "month_of_year")]
    assert yearly and all(c["evidence"]["figures"]["highest_month"] == "Dec" for c in yearly)
    flat, _ = looked(seasonal(season=False))
    yearly = [c for c in flat if (c["action"].get("config") or {}).get("dimension2_granularity") in ("year", "month_of_year")]
    assert yearly and all(c["evidence"] is None for c in yearly)             # still offered: nothing claimed


PAIR_META = {"reached": {"number": "amount", "unit": "kg"}, "expected": {"number": "amount", "unit": "kg"}}


def pair(linked=True, seed=3):
    rng = np.random.default_rng(seed)
    n = 3000
    expected = rng.uniform(50, 150, n)
    reached = expected * 0.9 + rng.normal(0, 3, n) if linked else rng.uniform(50, 150, n)
    return pd.DataFrame({"when": pd.date_range("2024-01-01", periods=n, freq="h"), "kind": rng.choice(["a", "b", "c"], n),
                         "reached": reached, "expected": expected})


def test_two_numbers_that_move_together_are_set_against_each_other_and_two_that_do_not_are_withheld():
    kept, _ = looked(pair(), PAIR_META)
    mine = [c for c in kept if c["capability"] == "explain_variance" or (c["action"].get("config") or {}).get("bridge_from")]
    assert mine and all(c["evidence"]["figures"]["together"] > 0.9 for c in mine)
    assert all(-12 < c["evidence"]["figures"]["difference_pct"] < -8 for c in mine)
    kept, withheld = looked(pair(linked=False), PAIR_META)
    assert not [c for c in kept if c["capability"] == "explain_variance"]
    assert any("not a yardstick" in w["reason"] for w in withheld)


def groups(real=True, seed=7):
    rng = np.random.default_rng(seed)
    n = 8000
    arm = np.where(np.arange(n) % 2 == 0, "first", "second")
    done = rng.random(n) < np.where((arm == "second") & real, 0.20, 0.10)
    return pd.DataFrame({"arm": arm, "done": np.where(done, "yes", "no")})


def test_two_groups_are_offered_only_when_they_differ():
    meta = {"done": {"outcome": True}}
    kept, _ = looked(groups(), meta)
    card = next(c for c in kept if c["capability"] == "compare_two_groups")
    assert card["evidence"]["band"] == "strong" and "higher" in card["found"]
    kept, withheld = looked(groups(real=False), meta)
    assert not [c for c in kept if c["capability"] == "compare_two_groups"]
    assert any("do not clearly differ" in w["reason"] for w in withheld)


def test_scenarios_on_two_totals_that_only_share_volume_are_withheld():
    """Both numbers are bigger in busier months and unrelated row by row: the
    period fit is near perfect and means nothing."""
    rng = np.random.default_rng(1)
    rows = []
    for m in pd.date_range("2023-01-01", periods=24, freq="MS"):
        for _ in range(int(rng.integers(200, 900))):
            rows.append((m, rng.normal(50, 5), rng.normal(20, 4)))
    df = pd.DataFrame(rows, columns=["when", "fee", "weight"])
    meta = {"fee": {"number": "amount"}, "weight": {"number": "amount"}}
    assert any(c["capability"] == "compare_scenarios" for c in cards_of(df, meta))     # offered by shape
    kept, withheld = looked(df, meta)
    assert not [c for c in kept if c["capability"] == "compare_scenarios"]
    assert any("busier periods hold more of everything" in w["reason"] or "no clear link" in w["reason"] for w in withheld)


def test_the_stage_is_the_column_that_separates_open_rows_whatever_the_shape_suggested():
    rng = np.random.default_rng(4)
    n = 2000
    began = pd.Timestamp("2025-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 180, n)), unit="D")
    still = np.arange(n) >= int(n * 0.9)
    df = pd.DataFrame({"began": began, "due": began + pd.Timedelta(days=5), "done_on": began + pd.Timedelta(days=4),
                       # `zone` comes first and has no link to being open; `state` is the real stage.
                       "zone": rng.choice(["north", "south", "east", "west"], n),
                       "state": np.where(still, "moving", np.where(rng.random(n) < 0.1, "back", "done"))})
    df.loc[still, "done_on"] = pd.NaT
    kept, _ = looked(df)
    card = next(c for c in kept if c["capability"] == "stage_board")
    assert card["action"]["params"]["stage_col"] == "state" and "state" in card["title"] and card["evidence"]["band"] == "strong"
    # With no column that separates them, there is no board.
    kept, withheld = looked(df.drop(columns=["state"]))
    assert not [c for c in kept if c["capability"] == "stage_board"]
    assert any("no stages to show" in w["reason"] for w in withheld)


def test_a_check_that_breaks_never_loses_its_card(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("no")
    monkeypatch.setattr(evidence, "_weekly_rhythm", boom)
    kept, withheld = looked(events())
    assert grid(kept) is not None and grid(kept)["evidence"] is None and not withheld


def test_a_rhythm_of_hours_alone_does_not_dress_up_the_weekdays():
    when = pd.date_range("2024-01-01", "2025-06-30 23:00", freq="h")
    df = pd.DataFrame({"when": when, "amount": np.where((when.hour >= 9) & (when.hour < 17), 10.0, 0.0)})
    g = grid(looked(df)[0])
    assert "between 09:00 and 17:00" in g["found"] and "about the same" in g["found"] and "Busiest on" not in g["found"]


def test_what_was_found_is_handed_to_the_dashboard_designer_once_per_finding():
    """Only cards with evidence, as the widget that draws them; the three
    yearly cards share one season and are one idea."""
    df = seasonal()
    got = engine.candidates(df, None, {}, lambda wt, cfg: "time")
    assert got and all(c["source"] == "discovery" and c["section"] == "time" and c["why"] for c in got)
    yearly = [c for c in got if (c["config"].get("dimension2_granularity") in ("year", "month_of_year"))]
    assert len(yearly) == 1 and "Dec" in yearly[0]["why"]
    assert all(c["widget_type"] and isinstance(c["config"], dict) for c in got)
    assert engine.candidates(seasonal(season=False), None, {}) == [] or all(
        "dimension2_granularity" not in c["config"] for c in engine.candidates(seasonal(season=False), None, {}))
