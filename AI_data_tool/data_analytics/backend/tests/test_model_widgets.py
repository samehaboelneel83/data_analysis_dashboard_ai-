"""Model widgets (MASTER_PLAN Phase 3): statistics/ML as living canvas objects.

Each shaper must (a) say what it still needs instead of failing, (b) state its
population, (c) refuse with a reason rather than render nonsense, and the
comparison must score every candidate on the SAME held-out rows."""
import numpy as np
import pandas as pd
import pytest

from app.services.model_widgets import (
    MODEL_SHAPERS, shape_model_cluster, shape_model_compare, shape_model_linear,
    shape_model_logistic, shape_model_tree,
)
from app.services.widget_data import SHAPERS


@pytest.fixture
def df():
    rng = np.random.default_rng(7)
    n = 400
    units = rng.integers(1, 50, n).astype(float)
    cost = rng.normal(100, 20, n)
    noise = rng.normal(0, 5, n)
    revenue = 12 * units + 0.5 * cost + noise
    churn_p = 1 / (1 + np.exp(-(units - 25) / 5))
    churned = np.where(rng.random(n) < churn_p, "yes", "no")
    region = rng.choice(["North", "South", "East"], n)
    frame = pd.DataFrame({"units": units, "cost": cost, "revenue": revenue,
                          "churned": churned, "region": region})
    frame.loc[:9, "cost"] = np.nan  # ten incomplete rows the population must name
    return frame


def test_registered_in_the_widget_dispatch_table():
    for t in MODEL_SHAPERS:
        assert SHAPERS[t] is MODEL_SHAPERS[t]


def test_linear_names_what_it_still_needs():
    out = shape_model_linear(pd.DataFrame({"a": [1, 2]}), {})
    assert out["status"] == "incomplete"
    assert "Response" in " ".join(out["needs"]) or out["needs"]


def test_linear_fits_and_discloses_population(df):
    out = shape_model_linear(df, {"measure": "revenue", "measures": ["units", "cost"]})
    assert out["status"] == "ok" and out["model"] == "linear"
    assert out["fit"]["value"] > 0.9
    pop = out["population"]
    assert pop["rows_total"] == 400 and pop["rows_used"] == 390 and pop["rows_dropped"] == 10
    assert out["diagnostics"]["residuals"] and out["diagnostics"]["actual_predicted"]


def test_logistic_reports_auc_and_a_confusion_matrix(df):
    out = shape_model_logistic(df, {"response": "churned", "measures": ["units"], "event_value": "yes"})
    assert out["status"] == "ok"
    assert out["event"] == "yes"
    assert out["fit"]["name"] == "AUC" and out["fit"]["value"] > 0.7
    cm = out["diagnostics"]["confusion"]
    assert cm["tp"] + cm["fp"] + cm["tn"] + cm["fn"] == out["population"]["rows_used"]


def test_logistic_refuses_a_non_binary_response_with_a_reason(df):
    out = shape_model_logistic(df, {"response": "region", "measures": ["units"]})
    assert out["status"] == "refused" and out["reason"]


def test_tree_defaults_to_every_other_column(df):
    out = shape_model_tree(df, {"response": "churned", "max_depth": 3})
    assert out["status"] == "ok" and out["model"] == "tree"
    assert out["predictors"]
    assert out["rows"]  # importance bars


def test_cluster_needs_two_variables(df):
    assert shape_model_cluster(df, {"measures": ["units"]})["status"] in {"incomplete", "refused"}
    out = shape_model_cluster(df, {"measures": ["units", "revenue"]})
    assert out["status"] == "ok"


def _spec(i, model, response, preds, **kw):
    return {"id": i, "title": f"m{i}", "model": model, "response": response, "predictors": preds, **kw}


def test_compare_refuses_fewer_than_two_models(df):
    out = shape_model_compare(df, {"compare": [_spec(1, "linear", "revenue", ["units"])]})
    assert out["status"] == "refused" and "two" in out["reason"]


def test_compare_refuses_models_of_different_responses(df):
    out = shape_model_compare(df, {"compare": [_spec(1, "linear", "revenue", ["units"]),
                                               _spec(2, "logistic", "churned", ["units"])]})
    assert out["status"] == "refused" and "different" in out["reason"]


def test_compare_names_a_winner_on_one_shared_split(df):
    out = shape_model_compare(df, {"compare": [_spec(1, "linear", "revenue", ["units", "cost"]),
                                               _spec(2, "linear", "revenue", ["cost"])]})
    assert out["status"] == "ok"
    assert out["winner"] == 1 and out["winner_beats_baseline"] is True
    pop = out["population"]
    assert pop["train_rows"] + pop["test_rows"] == pop["rows_used"]
    # Deterministic: the same split every render.
    again = shape_model_compare(df, {"compare": [_spec(1, "linear", "revenue", ["units", "cost"]),
                                                 _spec(2, "linear", "revenue", ["cost"])]})
    assert [m["score"] for m in again["models"]] == [m["score"] for m in out["models"]]


def test_compare_classification_uses_auc_and_a_tree_without_listed_predictors(df):
    out = shape_model_compare(df, {"compare": [_spec(1, "logistic", "churned", ["units"], event_value="yes"),
                                               _spec(2, "tree", "churned", [])]})
    assert out["status"] == "ok" and out["metric"].startswith("AUC")
    assert all(m["score"] is not None for m in out["models"])
    assert out["baseline"]["score"] == 0.5
    # the ROC overlay: one curve per model, from (0,0) to (1,1), on the same rows
    for m in out["models"]:
        assert m["roc"][0] == [0.0, 0.0] and m["roc"][-1] == [1.0, 1.0]


def test_a_regression_comparison_has_no_roc(df):
    out = shape_model_compare(df, {"compare": [_spec(1, "linear", "revenue", ["units"]),
                                               _spec(2, "linear", "revenue", ["cost"])]})
    assert all("roc" not in m for m in out["models"])


def test_compare_names_predictors_it_had_to_leave_out(df):
    df = df.assign(customer=[f"c{i}" for i in range(len(df))])
    out = shape_model_compare(df, {"compare": [_spec(1, "linear", "revenue", ["units", "customer"]),
                                               _spec(2, "linear", "revenue", ["cost"])]})
    m1 = next(m for m in out["models"] if m["id"] == 1)
    assert "customer" in m1.get("note", "")
    assert m1["predictors"] == ["units"]


def test_compare_refits_text_predictors_one_hot(df):
    out = shape_model_compare(df, {"compare": [_spec(1, "logistic", "churned", ["units", "region"], event_value="yes"),
                                               _spec(2, "logistic", "churned", ["region"], event_value="yes")]})
    assert out["status"] == "ok" and out["winner"] == 1
    assert not any(m.get("note") for m in out["models"])


def test_linear_takes_a_text_predictor_against_a_named_reference(df):
    out = shape_model_linear(df, {"measure": "revenue", "measures": ["units", "region"]})
    assert out["status"] == "ok"
    terms = [c["term"] for c in out["result"]["detail"]["coefficients"]]
    ref = out["encodings"]["region"]["reference"]
    assert f"region={ref}" not in terms
    assert sum(t.startswith("region=") for t in terms) == 2
    # region has no missing values, so only cost's ten gaps drop rows -- and
    # cost is not in this model, so nothing is dropped.
    assert out["population"]["rows_used"] == 400


def test_logistic_churn_by_tenure_and_region(df):
    """The Phase 3 acceptance sentence: churn ~ tenure + region + spend."""
    out = shape_model_logistic(df, {"response": "churned", "measures": ["units", "region", "cost"],
                                    "event_value": "yes"})
    assert out["status"] == "ok"
    terms = {c["term"] for c in out["result"]["detail"]["coefficients"]}
    assert "units" in terms and any(t.startswith("region=") for t in terms)
    assert out["population"]["dropped_by"] == {"cost": 10}


def test_a_text_predictor_with_too_many_values_is_refused_by_name(df):
    df = df.assign(customer=[f"c{i}" for i in range(len(df))])
    out = shape_model_linear(df, {"measure": "revenue", "measures": ["customer"]})
    assert out["status"] == "refused" and "customer" in out["reason"]


def test_compare_tells_apart_models_with_the_same_title(df):
    out = shape_model_compare(df, {"compare": [
        {**_spec(1, "linear", "revenue", ["units", "cost"]), "title": "Linear Regression"},
        {**_spec(2, "linear", "revenue", ["cost"]), "title": "Linear Regression"}]})
    assert [m["title"] for m in out["models"]] == ["Linear Regression (units + cost)", "Linear Regression (cost)"]


def test_tree_warns_when_one_column_is_the_answer_in_disguise(df):
    df = df.assign(region_code=df["region"].map({"North": "N", "South": "S", "East": "E"}))
    out = shape_model_tree(df, {"response": "region", "predictors": ["region_code", "units"]})
    assert out["status"] == "ok"
    assert any("region_code" in w for w in out["warnings"])


def test_a_model_widget_refits_under_the_page_filters(df):
    fit = MODEL_SHAPERS["model_linear"]
    out = fit(df, {"measure": "revenue", "predictors": ["units"],
                   "filters": [{"column": "region", "op": "eq", "value": "North"}]})
    assert out["status"] == "ok"
    north = int((df["region"] == "North").sum())
    assert out["population"]["rows_total"] == north
    assert out["population"]["rows_before_filters"] == 400
