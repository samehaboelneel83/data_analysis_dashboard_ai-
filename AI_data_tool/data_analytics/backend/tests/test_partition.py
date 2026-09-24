"""First-class Partition data item (MASTER_PLAN Phase 3 item 4)."""
import numpy as np
import pandas as pd
import pytest

from app.services.model_widgets import shape_model_compare, shape_model_linear, shape_model_logistic
from app.services.prep import apply_prep_steps, validate_prep_steps

STEP = {"kind": "partition", "name": "_Partition_", "train_pct": 70, "seed": 7}


@pytest.fixture
def df():
    rng = np.random.default_rng(3)
    n = 1000
    units = rng.integers(1, 50, n).astype(float)
    cost = rng.normal(100, 20, n)
    return pd.DataFrame({
        "customer": [f"c{i % 250}" for i in range(n)],
        "units": units, "cost": cost,
        "revenue": 12 * units + 0.5 * cost + rng.normal(0, 5, n),
        "churned": np.where(rng.random(n) < 1 / (1 + np.exp(-(units - 25) / 5)), "yes", "no"),
        "region": rng.choice(["North", "South"], n),
    })


def test_validation_accepts_a_partition_and_its_column_downstream(df):
    validate_prep_steps([STEP, {"kind": "filter_rows", "expression": "`_Partition_` == 'Training'"}], set(df.columns))


@pytest.mark.parametrize("bad", [{"train_pct": 0}, {"train_pct": 100}, {"name": "units"}, {"key": "nope"}, {"seed": "x"}])
def test_validation_refuses_a_malformed_partition(df, bad):
    with pytest.raises(ValueError):
        validate_prep_steps([{**STEP, **bad}], set(df.columns))


def test_split_is_close_to_the_asked_share(df):
    out = apply_prep_steps(df, [STEP])
    share = (out["_Partition_"] == "Training").mean()
    assert 0.65 < share < 0.75
    assert set(out["_Partition_"]) == {"Training", "Validation"}


def test_a_row_keeps_its_side_whatever_other_rows_are_present(df):
    """Row-level security narrows the frame BEFORE prep runs; the split must
    not move a row because its neighbours were filtered away."""
    full = apply_prep_steps(df, [STEP])["_Partition_"]
    narrowed = apply_prep_steps(df[df["region"] == "North"], [STEP])["_Partition_"]
    assert (full.loc[narrowed.index] == narrowed).all()


def test_a_key_column_keeps_one_customer_on_one_side(df):
    out = apply_prep_steps(df, [{**STEP, "key": "customer"}])
    assert out.groupby("customer")["_Partition_"].nunique().max() == 1


def test_the_seed_changes_the_split(df):
    a = apply_prep_steps(df, [STEP])["_Partition_"]
    b = apply_prep_steps(df, [{**STEP, "seed": 8}])["_Partition_"]
    assert (a != b).any()


def test_linear_headlines_the_validation_score(df):
    frame = apply_prep_steps(df, [STEP])
    out = shape_model_linear(frame, {"measure": "revenue", "predictors": ["units", "cost"], "partition": "_Partition_"})
    assert out["status"] == "ok"
    assert out["fit"]["name"] == "R² on validation rows" and out["fit"]["value"] > 0.9
    p = out["population"]["partition"]
    assert p["train_rows"] + p["validation_rows"] == 1000
    assert "R² on training rows" in out["fit"]["secondary"]


def test_logistic_scores_on_validation_rows(df):
    frame = apply_prep_steps(df, [STEP])
    out = shape_model_logistic(frame, {"response": "churned", "predictors": ["units"], "event_value": "yes",
                                       "partition": "_Partition_"})
    assert out["status"] == "ok" and out["fit"]["name"] == "AUC on validation rows"
    cm = out["diagnostics"]["confusion"]
    assert cm["tp"] + cm["fp"] + cm["tn"] + cm["fn"] == out["population"]["partition"]["validation_rows"]


def test_a_missing_partition_column_is_refused_by_name(df):
    out = shape_model_linear(df, {"measure": "revenue", "predictors": ["units"], "partition": "_Partition_"})
    assert out["status"] == "refused" and "_Partition_" in out["reason"]


def test_compare_uses_the_shared_partition_as_its_split(df):
    frame = apply_prep_steps(df, [STEP])
    spec = lambda i, preds: {"id": i, "title": f"m{i}", "model": "linear", "response": "revenue",  # noqa: E731
                             "predictors": preds, "partition": "_Partition_"}
    out = shape_model_compare(frame, {"compare": [spec(1, ["units", "cost"]), spec(2, ["cost"])]})
    assert out["status"] == "ok" and out["winner"] == 1
    assert out["population"]["test_rows"] == int((frame["_Partition_"] == "Validation").sum())


def test_compare_refuses_models_holding_out_different_partitions(df):
    frame = apply_prep_steps(df, [STEP, {**STEP, "name": "other", "seed": 9}])
    out = shape_model_compare(frame, {"compare": [
        {"id": 1, "model": "linear", "response": "revenue", "predictors": ["units"], "partition": "_Partition_"},
        {"id": 2, "model": "linear", "response": "revenue", "predictors": ["cost"], "partition": "other"}]})
    assert out["status"] == "refused" and "different partitions" in out["reason"]


def test_prep_created_columns_are_listed_for_the_pickers():
    from app.services.prep import prep_added_columns
    cols = {"units": "numeric", "region": "categorical", "name": "categorical"}
    steps = [STEP, {"kind": "split", "column": "name", "delimiter": " ", "into": ["first", "last"]},
             {"kind": "rename", "column": "units", "to": "qty"}]
    assert prep_added_columns(steps, cols) == [("_Partition_", "categorical"), ("first", "categorical"),
                                               ("last", "categorical"), ("qty", "numeric")]
    assert prep_added_columns([{"kind": "bogus"}], cols) == []
