"""Who comes back (docs/discovery/PLAN.md §D-19, phase 5)."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.cohort_retention import CohortRetentionError, cohort_retention


def visits(members=120, months=8, stay=0.6, seed=0):
    """Each member joins in one of the first three months and is seen in each
    later month with probability `stay`."""
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(members):
        first = int(rng.integers(0, 3))
        rows.append((f"m{m:03d}", pd.Timestamp("2025-01-10") + pd.DateOffset(months=first)))
        for k in range(first + 1, months):
            if rng.random() < stay:
                rows.append((f"m{m:03d}", pd.Timestamp("2025-01-10") + pd.DateOffset(months=k)))
                if rng.random() < 0.3:                      # twice in a month is still once
                    rows.append((f"m{m:03d}", pd.Timestamp("2025-01-20") + pd.DateOffset(months=k)))
    return pd.DataFrame(rows, columns=["member", "seen"])


def test_the_table_is_exact_on_a_case_small_enough_to_count_by_hand():
    df = pd.DataFrame({"who": ["a", "a", "a", "b", "b", "c", "d", "d"],
                       "at": pd.to_datetime(["2025-01-05", "2025-02-05", "2025-03-05", "2025-01-09", "2025-03-01",
                                             "2025-01-20", "2025-02-02", "2025-03-30"])})
    import app.services.analysis.cohort_retention as mod
    old, mod.MIN_ENTITIES = mod.MIN_ENTITIES, 2
    try:
        got = cohort_retention(df, "who", "at").to_dict()
    finally:
        mod.MIN_ENTITIES = old
    rows = {r["cohort"]: r for r in got["rows"]}
    # January: a, b, c. February: a only. March: a and b.
    assert (rows["2025-01"]["size"], rows["2025-01"]["p1"], rows["2025-01"]["p2"]) == (3, 33.3, 66.7)
    # February: d, seen again in March; there is no April, so +2 is empty -- not zero.
    assert (rows["2025-02"]["size"], rows["2025-02"]["p1"], rows["2025-02"]["p2"]) == (1, 100.0, None)
    curve = {c["period"]: c for c in got["meta"]["curve"]}
    assert curve[1]["retention"] == 50.0 and curve[1]["entities"] == 4          # 2 of the 4 who had a next month
    assert curve[2]["retention"] == 66.7 and curve[2]["entities"] == 3
    assert got["meta"]["once_only"] == 1 and got["meta"]["entities"] == 4


def test_retention_is_about_what_was_put_in_and_a_second_row_in_a_month_changes_nothing():
    got = cohort_retention(visits(stay=0.6), "member", "seen").to_dict()
    assert 50 <= got["meta"]["first_back"] <= 70
    again = cohort_retention(pd.concat([visits(stay=0.6)] * 2), "member", "seen").to_dict()
    assert again["rows"] == got["rows"]


def test_what_cannot_be_followed_is_refused_in_plain_words():
    df = visits()
    with pytest.raises(CohortRetentionError, match="not in this dataset"):
        cohort_retention(df, "nobody", "seen")
    with pytest.raises(CohortRetentionError, match="at least"):
        cohort_retention(df[df["member"].isin(["m001", "m002"])], "member", "seen")
    once = df.drop_duplicates("member")
    with pytest.raises(CohortRetentionError, match="one row only"):
        cohort_retention(once, "member", "seen")
    with pytest.raises(CohortRetentionError, match="no dates"):
        cohort_retention(df.assign(seen="soon"), "member", "seen")


def test_the_footnotes_carry_keys_and_say_what_an_empty_cell_is():
    got = cohort_retention(visits(), "member", "seen").to_dict()
    assert len(got["warnings"]) == len(got["meta"]["warnings_i18n"]) and all(got["meta"]["warnings_i18n"])
    assert any("empty, not zero" in w for w in got["warnings"])
    assert got["meta"]["headline_i18n"]["key"] == "co.headline"


def test_the_engine_offers_it_only_for_an_identifier_that_repeats():
    from app.services.discovery import engine
    from app.services.discovery import profile as store
    df = visits().assign(amount=1.0)
    cards = engine.tier0(store.compute(df, {"member": "categorical", "seen": "datetime", "amount": "numeric"}), None)["cards"]
    card = next(c for c in cards if c["capability"] == "cohort_retention")
    assert card["action"]["params"] == {"entity": "member", "date_column": "seen", "granularity": "month"}
    once = df.drop_duplicates("member")
    cards = engine.tier0(store.compute(once, {"member": "categorical", "seen": "datetime", "amount": "numeric"}), None)["cards"]
    assert not [c for c in cards if c["capability"] == "cohort_retention"]
