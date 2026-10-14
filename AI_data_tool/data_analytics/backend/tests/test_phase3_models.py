"""Feature importance on the automated-prediction winner, and key influencers
as a page widget (docs/discovery/PLAN.md, phase 3 #15-#16)."""
import numpy as np
import pandas as pd

from app.services.analysis.automated_prediction import automated_prediction
from app.services.model_widgets import MODEL_SHAPERS
from app.services.widget_roles import REQUIRED_ROLES


def frame(n=900, seed=5):
    rng = np.random.default_rng(seed)
    strong = rng.normal(0, 1, n)
    weak = rng.normal(0, 1, n)
    noise = rng.normal(0, 1, n)
    kind = rng.choice(["a", "b", "c"], n)
    y = 5 * strong + 0.6 * weak + np.where(kind == "c", 4.0, 0.0) + rng.normal(0, 0.5, n)
    return pd.DataFrame({"strong": strong, "weak": weak, "noise": noise, "kind": kind, "y": y})


def test_importance_ranks_what_the_winner_leans_on():
    got = automated_prediction(frame(), "y")
    imp = {r["column"]: r for r in got["importance"]}
    assert got["importance_of"] == got["champion"]["model"]
    assert [r["column"] for r in got["importance"]][0] == "strong"
    assert imp["strong"]["matters"] and imp["kind"]["matters"]
    assert not imp["noise"]["matters"]                       # shuffling it changes nothing
    # A text column is one answer, not one per value.
    assert set(imp) == {"strong", "weak", "noise", "kind"}
    assert "not what causes" in got["importance_note"]


def test_no_importance_when_nothing_beats_guessing():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400), "y": rng.normal(size=400)})
    got = automated_prediction(df, "y")
    assert got["beats_baseline"] is False and got["importance"] == [] and got["importance_of"] is None


def test_importance_is_the_same_twice():
    assert automated_prediction(frame(), "y")["importance"] == automated_prediction(frame(), "y")["importance"]


def outcomes(n=1200, seed=2):
    rng = np.random.default_rng(seed)
    kind = rng.choice(["a", "b", "c"], n)
    place = rng.choice(["x", "y"], n)
    p = np.where(kind == "c", 0.6, 0.1)
    return pd.DataFrame({"kind": kind, "place": place, "size": rng.normal(50, 10, n),
                         "state": np.where(rng.random(n) < p, "closed", "open")})


def test_influencers_widget_names_the_group_that_goes_with_the_outcome():
    assert REQUIRED_ROLES["model_influencers"] == ("response",)
    out = MODEL_SHAPERS["model_influencers"](outcomes(), {"response": "state", "event_value": "closed"})
    assert out["status"] == "ok" and out["model"] == "influencers" and out["event"] == "closed"
    top = out["influencers"][0]
    assert (top["factor"], top["group"]) == ("kind", "c") and top["lift"] > 2
    assert out["value_format"] == "percent" and 0.2 < out["baseline"] < 0.35
    assert "not proof" in out["result"]["caveats"][0]


def test_influencers_widget_refits_on_the_page_filters_and_says_so():
    out = MODEL_SHAPERS["model_influencers"](
        outcomes(), {"response": "state", "event_value": "closed",
                     "filters": [{"column": "place", "op": "eq", "value": "x"}]})
    assert out["status"] == "ok" and out["population"]["rows_before_filters"] == 1200
    assert all(i["factor"] != "place" for i in out["influencers"])       # one value left: not a factor


def test_influencers_widget_without_a_response_is_not_set_up():
    out = MODEL_SHAPERS["model_influencers"](outcomes(), {})
    assert out["status"] != "ok"


def test_influencers_widget_on_a_number_compares_averages():
    out = MODEL_SHAPERS["model_influencers"](frame(), {"response": "y", "predictors": ["kind", "noise"]})
    assert out["measure"] == "mean" and out["value_format"] is None
    assert (out["influencers"][0]["factor"], out["influencers"][0]["group"]) == ("kind", "c")
