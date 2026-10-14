"""The insights engine reads each column's stored classification
(docs/suggestions/PLAN.md): sizes are not findings, outcomes are measured as
rates, ordered categories are read in order."""
import numpy as np
import pandas as pd

from app.services.insights import generate_insights, suggest_widgets_from_findings


def parcels(n=6000, seed=1):
    rng = np.random.default_rng(seed)
    region = rng.choice(["Cairo", "Delta", "Canal", "Upper"], n, p=[0.55, 0.25, 0.12, 0.08])
    late_p = pd.Series(region).map({"Cairo": 0.15, "Delta": 0.16, "Canal": 0.14, "Upper": 0.35}).to_numpy()
    priority = rng.choice(["Low", "Medium", "High"], n)
    fee = rng.uniform(80, 120, n) + pd.Series(priority).map({"Low": 0, "Medium": 40, "High": 90}).to_numpy()
    return pd.DataFrame({
        "region": region,
        "fee": fee.round(2),
        "priority": priority,
        "is_late": rng.random(n) < late_p,
        "val2": rng.integers(1, 6, n).astype(float),            # a 1-5 score with nothing in its name
        "created": pd.date_range("2024-01-01", periods=n, freq="h"),
    })


TYPES = {"region": "categorical", "fee": "numeric", "priority": "categorical", "is_late": "categorical",
         "val2": "numeric", "created": "datetime"}
META = {"fee": {"number": "amount"}, "val2": {"number": "score", "direction": "higher_better"},
        "is_late": {"outcome": True}, "priority": {"level": "ordinal", "order": ["Low", "Medium", "High"]}}


def kinds(found):
    return [(f["kind"], tuple(f["columns"])) for f in found["findings"]]


def test_a_big_group_carrying_a_big_share_is_not_a_finding():
    found = generate_insights(parcels(), TYPES, META)
    titles = " | ".join(f["title"] for f in found["findings"])
    # Cairo has 55% of the rows and so 55% of the fees: that is its size.
    assert "Cairo carries" not in titles


def test_the_rate_of_an_outcome_per_group_is_found_against_each_groups_own_size():
    found = generate_insights(parcels(), TYPES, META)
    rate = next(f for f in found["findings"] if f["kind"] == "rate" and f["columns"] == ["region", "is_late"])
    # Upper has the fewest parcels and by far the highest share late.
    assert rate["figures"]["member"] == "Upper" and 30 < rate["figures"]["rate_pct"] < 40
    assert 15 < rate["figures"]["overall_pct"] < 20 and rate["significant"] is True
    assert "Upper has the highest share of is_late" in rate["title"]


def test_without_the_classification_no_rate_is_looked_for():
    assert not [f for f in generate_insights(parcels(), TYPES, {})["findings"] if f["kind"] == "rate"]


def test_a_measure_that_climbs_an_ordered_category_is_found_in_its_order():
    found = generate_insights(parcels(), TYPES, META)
    g = next(f for f in found["findings"] if f["kind"] == "gradient")
    assert g["columns"] == ["priority", "fee"] and g["figures"]["order"] == ["Low", "Medium", "High"]
    assert g["figures"]["direction"] == "up"
    # Unordered, the same column is just three categories.
    assert not [f for f in generate_insights(parcels(), TYPES, {})["findings"] if f["kind"] == "gradient"]


def test_a_number_is_treated_as_what_it_was_classified_as_whatever_its_name():
    df = parcels()
    # `val2` as a score is averaged: no finding totals it.
    scored = generate_insights(df, TYPES, META)
    assert not [f for f in scored["findings"] if "val2" in f["columns"] and "carries" in f["title"]]
    # Classified a code, it leaves the analysis altogether.
    coded = generate_insights(df, TYPES, {**META, "val2": {"number": "code"}})
    assert not [f for f in coded["findings"] if "val2" in f["columns"] and f["kind"] != "data_quality"]


def test_the_way_that_is_good_travels_with_the_finding():
    df = parcels()
    df["val2"] = np.where(df["region"] == "Upper", 2.0, 4.5)        # Upper rates low
    found = generate_insights(df, TYPES, META)
    low = next(f for f in found["findings"] if f["kind"] == "laggard" and "val2" in f["columns"])
    assert low["tone"] == "bad"                                     # the lowest of a higher-is-better score


def test_new_findings_become_charts_that_show_them():
    df = parcels()
    found = generate_insights(df, TYPES, META)
    roles = {"region": "categorical", "fee": "numeric", "priority": "categorical", "is_late": "categorical",
             "val2": "numeric", "created": "datetime"}
    sugg = suggest_widgets_from_findings(found["findings"], roles, column_meta=META)
    rate = next(x for x in sugg if x["kind"] == "rate")
    assert rate["config"] == {"dimension": "region", "dimension2": "is_late", "measure": "region",
                              "aggregation": "count", "bar_mode": "stacked100"}
    grad = next(x for x in sugg if x["kind"] == "gradient")
    assert grad["config"]["sort_by"] == "order" and grad["config"]["category_order"] == ["Low", "Medium", "High"]


def test_an_ordinal_axis_is_drawn_in_its_order():
    from app.services.widget_data import get_widget_data_from_df
    got = get_widget_data_from_df(parcels(), {"dimension": "priority", "measure": "fee", "aggregation": "avg",
                                              "sort_by": "order", "category_order": ["Low", "Medium", "High"]}, "bar")
    assert [r["name"] for r in got["rows"]] == ["Low", "Medium", "High"]


def test_a_monthly_total_that_only_follows_volume_says_so():
    """More rows in the last month, the same fee per row: the total rose with
    the volume. Still news -- the month was busy -- but the finding says it is
    volume, and ranks below one where the fee itself moved."""
    rng = np.random.default_rng(4)
    days = pd.date_range("2024-01-01", "2024-08-31", freq="D")
    rows = []
    for d in days:
        n = 40 if d.month < 8 else 80                       # August is twice as busy
        rows += [(d, 100.0 + rng.normal(0, 3)) for _ in range(n)]
    busy = pd.DataFrame(rows, columns=["day", "fee"])
    types = {"day": "datetime", "fee": "numeric"}
    found = generate_insights(busy, types, {"fee": {"number": "amount"}})
    trend = next(f for f in found["findings"] if f["kind"] == "trend")
    assert trend["figures"]["follows_volume"] and "number of rows moved the same way" in trend["detail"]
    # The same volume all year and the FEE up in the last month: a change per row.
    steady = pd.DataFrame([(d, 100.0 + rng.normal(0, 3)) for d in days for _ in range(40)], columns=["day", "fee"])
    steady.loc[steady["day"].dt.month == 8, "fee"] *= 1.6
    found = generate_insights(steady, types, {"fee": {"number": "amount"}})
    dear = next(f for f in found["findings"] if f["kind"] == "trend")
    assert not dear["figures"]["follows_volume"] and "number of rows" not in dear["detail"]
    assert dear["score"] > trend["score"] * 0.5


def test_a_description_is_not_used_as_a_name_in_a_sentence():
    found = generate_insights(parcels(), TYPES, META, labels={
        "is_late": "Whether the parcel reached the customer after the promised date.",
        "region": "Region"})
    rate = next(f for f in found["findings"] if f["kind"] == "rate")
    assert "share of is_late" in rate["title"] and "Whether the parcel" not in rate["title"]


def test_one_kind_of_finding_cannot_fill_the_list():
    rng = np.random.default_rng(6)
    n = 3000
    df = pd.DataFrame({f"m{i}": np.where(rng.random(n) < 0.02, 5000.0, rng.uniform(1, 9, n)) for i in range(6)})
    df["g"] = rng.choice(["a", "b"], n)
    types = {**{f"m{i}": "numeric" for i in range(6)}, "g": "categorical"}
    found = generate_insights(df, types, {})
    assert sum(1 for f in found["findings"] if f["kind"] == "outlier_impact") <= 2


def test_an_outcome_is_not_offered_as_the_breakdown_of_a_total():
    from app.services.insights import baseline_suggestions
    roles = {"region": "categorical", "fee": "numeric", "priority": "categorical", "is_late": "categorical",
             "val2": "numeric", "created": "datetime"}
    got = baseline_suggestions(parcels(), roles, META)
    assert got and not [b for b in got if b["config"].get("dimension") == "is_late"]


def test_a_count_of_an_identifier_names_the_thing_counted():
    from app.services.insights import counted_as
    assert counted_as("shipment_id") == "Shipment count"
    assert counted_as("Order No") == "Order count"
    assert counted_as("id") == "Number of id"                # nothing left to name
    assert counted_as("رقم_الشحنة") == "عدد الشحنة"              # the same word, where Arabic puts it
    assert counted_as("الشحنات") == "Number of الشحنات"           # no identifier word: left as written


def test_a_thin_last_month_is_the_tail_of_the_data_not_a_trend():
    rng = np.random.default_rng(9)
    days = pd.date_range("2024-01-01", "2024-07-31", freq="D")
    rows = [(d, 50.0 + rng.normal(0, 2)) for d in days for _ in range(30)]
    rows += [(pd.Timestamp("2024-08-01") + pd.Timedelta(days=i), 50.0) for i in range(31)]   # 31 rows against ~900
    df = pd.DataFrame(rows, columns=["day", "qty"])
    found = generate_insights(df, {"day": "datetime", "qty": "numeric"}, {"qty": {"number": "amount"}})
    assert not [f for f in found["findings"] if f["kind"] == "trend"]


def test_a_total_of_gains_and_losses_is_not_shared_out():
    rng = np.random.default_rng(2)
    profit = np.concatenate([rng.normal(10, 5, 950), rng.normal(-900, 50, 50)])
    df = pd.DataFrame({"profit": profit, "g": rng.choice(["a", "b"], 1000)})
    found = generate_insights(df, {"profit": "numeric", "g": "categorical"}, {"profit": {"number": "amount"}})
    titles = [f["title"] for f in found["findings"] if f["kind"] == "outlier_impact"]
    assert titles and all("carry" not in t and "move the average" in t for t in titles)


def test_the_only_group_with_a_measure_is_said_as_that_and_ranked_low():
    rng = np.random.default_rng(3)
    n = 1200
    kind = rng.choice(["data", "voice", "sms"], n)
    volume = np.where(kind == "data", rng.uniform(1, 100, n), 0.0)
    df = pd.DataFrame({"kind": kind, "volume": volume})
    found = generate_insights(df, {"kind": "categorical", "volume": "numeric"}, {"volume": {"number": "amount"}})
    top = next(f for f in found["findings"] if f["kind"] == "standout")
    assert top["title"] == "Almost all volume is in data" and top["score"] <= 0.3


def test_a_group_that_is_only_a_number_is_named_with_its_column():
    rng = np.random.default_rng(5)
    n = 900
    fee = rng.choice([8800, 12000, 15800], n)
    score = rng.normal(60, 5, n) + (fee == 15800) * 12
    df = pd.DataFrame({"fee": fee.astype(str), "score": score})
    found = generate_insights(df, {"fee": "categorical", "score": "numeric"}, {"score": {"number": "score"}})
    top = next(f for f in found["findings"] if f["kind"] == "standout")
    assert top["title"].startswith("fee 15800 has the highest average")


def test_a_total_made_by_a_few_extreme_rows_has_no_monthly_trend():
    rng = np.random.default_rng(12)
    days = pd.date_range("2024-01-01", "2024-08-31", freq="D")
    df = pd.DataFrame([(d, rng.uniform(60, 140)) for d in days for _ in range(10)], columns=["day", "area"])
    wild = df.sample(40, random_state=1).index
    wild = [i for i in wild if df.loc[i, "day"].month != 8]          # none of them in the last month
    df.loc[wild, "area"] = 90000.0
    found = generate_insights(df, {"day": "datetime", "area": "numeric"}, {"area": {"number": "amount"}})
    assert not [f for f in found["findings"] if f["kind"] == "trend"]


def test_a_two_sided_mix_is_described_by_the_side_that_happens_to_some_rows():
    from app.services.readback import takeaway
    cfg = {"dimension": "region", "dimension2": "is_late", "measure": "region", "aggregation": "count",
           "bar_mode": "stacked100"}
    drawn = {"type": "crosstab", "columns": ["region", "False", "True", "__total__"],
             "rows": [["Canal", 860, 140, 1000], ["Upper Egypt", 760, 240, 1000], ["Delta", 820, 180, 1000]]}
    said = str(takeaway("bar", cfg, drawn))
    assert "True is 24% of Upper Egypt but 14% of Canal" in said, said
