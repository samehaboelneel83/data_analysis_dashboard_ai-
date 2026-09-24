"""The insights engine: each detector fires on data built to trigger it, stays
quiet on data built not to, and every sentence carries its own numbers."""
import numpy as np
import pandas as pd

from app.services.insights import generate_insights


def test_standout_and_laggard_fire_on_skewed_shares():
    df = pd.DataFrame({
        "region": ["A"] * 60 + ["B"] * 20 + ["C"] * 20,
        "rev": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    })
    r = generate_insights(df, {"region": "categorical", "rev": "numeric"})
    kinds = [f["kind"] for f in r["findings"]]
    assert "standout" in kinds
    top = next(f for f in r["findings"] if f["kind"] == "standout")
    assert "A carries 94%" in top["title"]
    assert top["columns"] == ["region", "rev"]


def test_trend_fires_on_a_spiking_last_month():
    dates = list(pd.date_range("2026-01-01", "2026-05-28", freq="3D").strftime("%Y-%m-%d"))
    vals = [10.0] * len(dates)
    for i, d in enumerate(dates):
        if d.startswith("2026-05"):
            vals[i] = 40.0
    df = pd.DataFrame({"d": dates, "v": vals})
    r = generate_insights(df, {"d": "datetime", "v": "numeric"})
    trend = next(f for f in r["findings"] if f["kind"] == "trend")
    assert "2026-05" in trend["title"] and "above" in trend["title"]


def test_correlation_fires_only_when_strong():
    rng = np.random.default_rng(7)
    x = rng.normal(size=200)
    df = pd.DataFrame({"x": x, "y": x * 2 + rng.normal(scale=0.1, size=200),
                       "noise": rng.normal(size=200)})
    tm = {"x": "numeric", "y": "numeric", "noise": "numeric"}
    r = generate_insights(df, tm)
    corr = [f for f in r["findings"] if f["kind"] == "correlation"]
    assert any("x moves with y" in f["title"] for f in corr)
    assert not any("noise" in f["title"] for f in corr)


def test_data_quality_flags_heavy_missingness():
    df = pd.DataFrame({"a": [1.0, None] * 25, "b": range(50)})
    r = generate_insights(df, {"a": "numeric", "b": "numeric"})
    dq = next(f for f in r["findings"] if f["kind"] == "data_quality")
    assert "a is 50% missing" in dq["title"]


def test_quiet_data_yields_a_quiet_narrative():
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"x": rng.normal(size=100), "y": rng.normal(size=100)})
    r = generate_insights(df, {"x": "numeric", "y": "numeric"})
    assert r["findings"] == [] or all(f["score"] < 0.6 for f in r["findings"])
    assert "rows" in r["narrative"]


def test_findings_rank_by_score_and_cap():
    df = pd.DataFrame({
        "region": ["A"] * 90 + ["B"] * 10,
        "rev": [50.0] * 90 + [1.0] * 10,
        "half_missing": [None, 1.0] * 50,
    })
    r = generate_insights(df, {"region": "categorical", "rev": "numeric", "half_missing": "numeric"})
    scores = [f["score"] for f in r["findings"]]
    assert scores == sorted(scores, reverse=True)
    assert len(r["findings"]) <= 12
    assert r["narrative"].startswith("Across 100 rows")


def test_role_overrides_reach_the_engine():
    """The ⇄ reclassification must change what the engine treats as a measure:
    a numeric column overridden to category stops producing trend/outlier
    findings and starts serving as a grouping.

    The column used to be called `year`. Since the semantic veto
    (services/semantic_guard.py) a column NAMED year never enters the measure
    pool at all, override or not -- so the override is exercised on a neutral
    name, and the veto is pinned separately below."""
    df = pd.DataFrame({
        "cohort": [2024.0] * 60 + [2025.0] * 40,
        "rev": [50.0] * 60 + [1.0] * 40,
    })
    tm = {"cohort": "numeric", "rev": "numeric"}

    without = generate_insights(df, tm)
    assert any("cohort" in f["title"] and f["kind"] != "standout" for f in without["findings"])

    with_override = generate_insights(df, tm, {"cohort": {"role": "category"}})
    # cohort is no longer a measure anywhere...
    assert not any(f["kind"] in ("correlation", "outlier_impact", "trend")
                   and "cohort" in f["columns"] for f in with_override["findings"])
    # ...and now groups rev as a category instead
    standout = next(f for f in with_override["findings"] if f["kind"] == "standout")
    assert standout["columns"] == ["cohort", "rev"]


def test_a_column_named_year_is_never_a_measure():
    """The semantic veto: no trend, outlier or correlation finding about `year`,
    even with no override recorded."""
    df = pd.DataFrame({
        "year": [2024.0] * 60 + [2025.0] * 40,
        "rev": [50.0] * 60 + [1.0] * 40,
    })
    r = generate_insights(df, {"year": "numeric", "rev": "numeric"})
    assert not any(f["kind"] in ("correlation", "outlier_impact", "trend")
                   and "year" in f["columns"] for f in r["findings"])


def test_hidden_columns_leave_the_analysis_entirely():
    df = pd.DataFrame({
        "secretish": [None, 1.0] * 25,
        "rev": [float(i) for i in range(50)],
    })
    tm = {"secretish": "numeric", "rev": "numeric"}
    r = generate_insights(df, tm, {"secretish": {"hidden": True}})
    assert not any("secretish" in f["columns"] for f in r["findings"])


def test_reserved_meta_keys_and_junk_entries_are_ignored():
    df = pd.DataFrame({"rev": [float(i) for i in range(50)]})
    r = generate_insights(df, {"rev": "numeric"},
                          {"__prep_steps__": [{"kind": "trim"}], "rev": "not-a-dict"})
    assert "rows" in r["narrative"]          # no crash, engine ran


# ── Findings in the business's words ─────────────────────────────────────────
#
# A finding used to read "2 carries 62% of amount" -- correct, and written in the
# schema's vocabulary rather than the reader's, while the catalog knew perfectly
# well that the column is revenue and that 2 means "paid".

def test_a_described_column_is_named_in_words():
    df = pd.DataFrame({
        "st": ["A"] * 60 + ["B"] * 20 + ["C"] * 20,
        "amt": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    })
    r = generate_insights(df, {"st": "categorical", "amt": "numeric"},
                          labels={"amt": "revenue", "st": "order status"})
    titles = " ".join(f["title"] for f in r["findings"])
    assert "revenue" in titles
    assert "order status" in titles


def test_a_coded_value_is_spelled_out_in_the_sentence():
    df = pd.DataFrame({
        "st": [2] * 60 + [1] * 20 + [3] * 20,
        "amt": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    })
    r = generate_insights(df, {"st": "categorical", "amt": "numeric"},
                          value_labels={"st": {"1": "new", "2": "paid",
                                               "3": "cancelled"}})
    titles = " ".join(f["title"] for f in r["findings"])
    assert "paid" in titles


def test_without_labels_the_findings_are_exactly_what_they_were():
    """Every upload, and every dataset with no catalog behind it. The words
    change only where something is actually known."""
    df = pd.DataFrame({
        "region": ["A"] * 60 + ["B"] * 20 + ["C"] * 20,
        "rev": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    })
    roles = {"region": "categorical", "rev": "numeric"}
    assert generate_insights(df, roles) == generate_insights(
        df, roles, labels=None, value_labels=None)


def test_the_numbers_are_untouched_by_relabelling():
    """Only the words around them. Every figure a sentence states is still the
    figure this engine computed, which is what lets the UI show exactly what the
    words claim."""
    df = pd.DataFrame({
        "st": ["A"] * 60 + ["B"] * 20 + ["C"] * 20,
        "amt": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    })
    roles = {"st": "categorical", "amt": "numeric"}
    plain = generate_insights(df, roles)
    named = generate_insights(df, roles, labels={"amt": "revenue"})
    assert [f["score"] for f in plain["findings"]] == [f["score"] for f in named["findings"]]
    assert [f["kind"] for f in plain["findings"]] == [f["kind"] for f in named["findings"]]


# ── The widened role vocabulary ──────────────────────────────────────────────
#
# `_VALID_ROLES` (what the PUT accepted) and `_ROLE_TO_ANALYSIS_KIND` (what the
# engine reads) had drifted: `timestamp` and `identifier` were understood by
# every consumer and rejected by the only endpoint that could set them. An
# author could watch `student_id` charted as a measure with no way to say it was
# an identifier.

def test_the_engine_reads_every_role_the_api_accepts():
    """The pin that keeps the writer and the reader from drifting again. Roles
    absent from the map fall through to DETECTION on purpose (geography: a
    country detects as categorical and a latitude as numeric, and both are
    right) — so the assertion is about the widened vocabulary being understood,
    not about every role having an entry."""
    from app.routers.datasets import _VALID_ROLES
    from app.services.insights import _ROLE_TO_ANALYSIS_KIND

    must_be_read = {"measure", "category", "temporal", "freetext", "identifier"}
    assert must_be_read <= set(_VALID_ROLES)
    assert must_be_read <= set(_ROLE_TO_ANALYSIS_KIND)


def test_free_text_stops_being_charted_as_a_category():
    """The defect this role exists for: `detect_types` emits only
    numeric/categorical/datetime, so a 3,000-distinct-value comments field
    arrives labelled `categorical` and gets proposed as a bar chart with 3,000
    bars. `text` matches no consumer's equality check, so it drops out of the
    dimension pickers — and `text_topics` is the one analysis that goes looking
    for it."""
    from app.services.insights import effective_roles

    roles = effective_roles({"notes": "categorical", "amount": "numeric"},
                            {"notes": {"role": "freetext"}})
    assert roles["notes"] == "text"
    assert roles["amount"] == "numeric"


def test_a_column_marked_temporal_is_read_as_a_date():
    from app.services.insights import effective_roles

    roles = effective_roles({"period": "categorical"}, {"period": {"role": "temporal"}})
    assert roles["period"] == "datetime"


def test_aliases_canonicalise_so_storage_holds_one_spelling_per_concept():
    from app.routers.datasets import _canonical_role

    assert _canonical_role("dimension") == "category"
    assert _canonical_role("categorical") == "category"
    assert _canonical_role("timestamp") == "temporal"
    assert _canonical_role("datetime") == "temporal"
    assert _canonical_role("geo") == "geography"
    assert _canonical_role("text") == "freetext"
    assert _canonical_role("  MEASURE ") == "measure"
    # An unknown value passes through unchanged so validation still refuses it —
    # canonicalising must never turn a typo into a silent acceptance.
    assert _canonical_role("nonsense") == "nonsense"
    assert _canonical_role(None) is None


def test_geography_still_falls_through_to_detection():
    """Absent from the map on purpose. Mapping it to one analysis kind would
    reclassify either country names or latitudes, whichever the choice went
    against."""
    from app.services.insights import effective_roles

    assert effective_roles({"country": "categorical"},
                           {"country": {"role": "geography"}})["country"] == "categorical"
    assert effective_roles({"lat": "numeric"},
                           {"lat": {"role": "geography"}})["lat"] == "numeric"


# ── Eligibility: withheld from suggestion, not hidden ────────────────────────

def test_an_ineligible_column_is_never_volunteered():
    from app.services.insights import suggest_widgets_from_findings

    findings = [
        {"kind": "standout", "score": 0.9, "title": "A carries most of amount",
         "columns": ["region", "amount"]},
        {"kind": "standout", "score": 0.8, "title": "B carries most of cost",
         "columns": ["region", "internal_cost"]},
    ]
    roles = {"region": "categorical", "amount": "numeric", "internal_cost": "numeric"}

    everything = suggest_widgets_from_findings(findings, roles)
    assert len(everything) == 2

    withheld = suggest_widgets_from_findings(findings, roles,
                                             ineligible={"internal_cost"})
    titles = " ".join(s["title"] for s in withheld)
    assert "internal_cost" not in titles
    assert len(withheld) == 1


def test_eligibility_withholds_the_offer_and_nothing_else():
    """Distinct from `hidden`, and the distinction is the whole point: hidden
    removes a column from the analysis entirely, while this leaves the finding
    computed, true, and readable by anyone who goes looking."""
    import pandas as pd
    from app.services.insights import effective_roles, generate_insights

    df = pd.DataFrame({
        "region": ["A"] * 60 + ["B"] * 20 + ["C"] * 20,
        "internal_cost": [10.0] * 60 + [1.0] * 20 + [1.0] * 20,
    })
    meta = {"internal_cost": {"eligible_for_suggestion": False}}
    roles = effective_roles({"region": "categorical", "internal_cost": "numeric"}, meta)
    # Still analysed: eligibility is not a role override and not a hide.
    assert roles["internal_cost"] == "numeric"
    assert generate_insights(df, {"region": "categorical",
                                  "internal_cost": "numeric"}, meta)["findings"]
