"""Fit several models, name the one that wins — and say whether it earned it.

SAS's "automated prediction" runs a handful of candidates and picks a champion.
Every piece was already here — a decision tree, a linear model, a logistic one —
and nothing had ever put them in the same room and compared them.

Four things decide whether this is an answer or a number generator:

  * **One split, shared by every candidate.** A tree scored on one random
    quarter against a forest scored on a different quarter compares the
    quarters. This is the property the whole comparison rests on and the
    easiest to get silently wrong.

  * **A dumb baseline always runs.** "Always guess the majority class" is the
    score a real model has to beat to have earned its place. Reporting 82%
    accuracy without mentioning that guessing scores 79% is the most common way
    a prediction result misleads.

  * **The margin is the headline.** A champion beating the baseline by half a
    point is a champion of nothing, and this says so in words rather than
    leaving the reader to subtract two numbers.

  * **This call persists nothing, and says so.** It refits and discards, so
    it answers "what could predict this, and how well". Scoring new rows is
    a different job with different security, and lives in `model_store.py`
    and `routers/prediction_models.py` — which keep the champion, record the
    columns it was trained on, and refuse a caller who has since been denied
    one of them.

sklearn is imported lazily, inside the function, like every other sklearn
analysis here.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .decision_tree import (MAX_TARGET_CLASSES, RANDOM_STATE, _encode,
                            _usable_predictors)

#: A quarter held back, same as the tree.
TEST_SIZE = 0.25
#: Enough that a held-out quarter is a real test.
MIN_ROWS = 60
#: Same ceiling as the tree: past this a "classification" is an identifier.
MAX_CLASSES = MAX_TARGET_CLASSES
FRAME_SAMPLE_THRESHOLD = 50_000

#: Below this margin over "always guess", the champion has not earned its name.
#: Deliberately not zero: a model that wins by a rounding error has won nothing,
#: and reporting it as a success is how a dashboard ends up trusted for a
#: decision it cannot support.
MEANINGFUL_LIFT = 0.02


class AutomatedPredictionError(ValueError):
    """Nothing here can be predicted from anything else, with the reason."""


def automated_prediction(df: pd.DataFrame, target: str,
                         predictors: list[str] | None = None,
                         partition: str | None = None) -> dict:
    """Fit several candidate models on one split and report which wins.

    `partition` names a Training/Validation column (the prep `partition` step,
    or any train/test or 1/0 column): the split is then THAT one instead of a
    random 25% -- the same rows a saved model or a canvas model widget trains
    and validates on, so the three agree on what "held out" means."""
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    if target not in df.columns:
        raise AutomatedPredictionError(f"Column '{target}' not found")

    if partition and partition not in df.columns:
        raise AutomatedPredictionError(f"Partition column '{partition}' not found")
    if partition and partition == target:
        raise AutomatedPredictionError("The partition column cannot also be the outcome")
    used, skipped = _usable_predictors(df, target, [p for p in (predictors or []) if p != partition] or
                                       ([c for c in df.columns if c not in (target, partition)] if partition else None))
    used = [c for c in used if c != partition]
    if not used:
        raise AutomatedPredictionError(
            "No column can be used as a predictor here. Numeric columns and "
            "categorical ones with a manageable number of values can be, "
            "identifiers and dates cannot.")

    frame = df[[target, *used, *([partition] if partition else [])]].dropna(subset=[target])
    sampled = len(frame) > FRAME_SAMPLE_THRESHOLD
    if sampled:
        frame = frame.sample(FRAME_SAMPLE_THRESHOLD, random_state=RANDOM_STATE)
    if len(frame) < MIN_ROWS:
        raise AutomatedPredictionError(
            f"Only {len(frame)} usable rows; at least {MIN_ROWS} are needed to "
            f"compare models on data none of them was fitted to.")

    y = frame[target]
    classification = not (pd.api.types.is_numeric_dtype(y)
                          and y.nunique() > MAX_CLASSES)
    if classification:
        y = y.astype(str)
        classes = sorted(y.unique())
        if len(classes) < 2:
            raise AutomatedPredictionError(
                f"'{target}' has only one value, so there is nothing to predict.")
        if len(classes) > MAX_CLASSES:
            raise AutomatedPredictionError(
                f"'{target}' has {len(classes):,} distinct values -- that is an "
                f"identifier, not an outcome.")

    X, _labels = _encode(frame, used)
    if partition:
        # The named split, not a random one (see the docstring).
        labels = frame[partition].astype(str).str.strip().str.lower()
        present = frame[partition].notna().to_numpy()
        is_train = present & (labels.str.startswith("train") | (labels == "1")).to_numpy()
        is_test = present & ~is_train
        if is_train.sum() < 10 or is_test.sum() < 5:
            raise AutomatedPredictionError(
                f"Partition '{partition}' leaves {int(is_train.sum())} training and "
                f"{int(is_test.sum())} validation rows; need at least 10 and 5.")
        X_train, X_test = X[is_train], X[is_test]
        y_train, y_test = y[is_train], y[is_test]
    else:
        stratify = y if classification and y.value_counts().min() >= 2 else None
        # ONE split, made once, used by every candidate below. Re-splitting per
        # model would compare the splits.
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=stratify)

    leaf = max(2, len(X_train) // 100)
    if classification:
        candidates: list[tuple[str, Any, bool]] = [
            ("always the most common", DummyClassifier(strategy="most_frequent"), True),
            ("decision tree", DecisionTreeClassifier(
                max_depth=4, random_state=RANDOM_STATE, min_samples_leaf=leaf), False),
            ("random forest", RandomForestClassifier(
                n_estimators=100, max_depth=8, random_state=RANDOM_STATE,
                min_samples_leaf=leaf, n_jobs=1), False),
            ("logistic regression", LogisticRegression(
                max_iter=1000, random_state=RANDOM_STATE), False),
        ]
        score_name = "accuracy"
    else:
        candidates = [
            ("always the average", DummyRegressor(strategy="mean"), True),
            ("decision tree", DecisionTreeRegressor(
                max_depth=4, random_state=RANDOM_STATE, min_samples_leaf=leaf), False),
            ("random forest", RandomForestRegressor(
                n_estimators=100, max_depth=8, random_state=RANDOM_STATE,
                min_samples_leaf=leaf, n_jobs=1), False),
            ("linear regression", LinearRegression(), False),
        ]
        score_name = "r2"

    results: list[dict] = []
    for name, model, is_baseline in candidates:
        try:
            model.fit(X_train, y_train)
            score = round(float(model.score(X_test, y_test)), 4)
            train = round(float(model.score(X_train, y_train)), 4)
        except Exception:
            # A candidate that cannot fit this data is not a failure of the
            # comparison -- it is one fewer option, and the others still answer
            # the question. Recorded so its absence is not mysterious.
            results.append({"model": name, "score": None, "train_score": None,
                            "n_test": int(len(X_test)), "is_baseline": is_baseline,
                            "error": "could not be fitted to this data"})
            continue
        results.append({"model": name, "score": score, "train_score": train,
                        "n_test": int(len(X_test)), "is_baseline": is_baseline,
                        "error": None})

    scored = [r for r in results if r["score"] is not None]
    if not scored:
        raise AutomatedPredictionError(
            "No candidate model could be fitted to this data.")

    champion = max(scored, key=lambda r: r["score"])
    baseline = next((r for r in scored if r["is_baseline"]), None)
    baseline_score = baseline["score"] if baseline else None
    lift = (round(champion["score"] - baseline_score, 4)
            if baseline_score is not None else None)
    beats = lift is not None and lift >= MEANINGFUL_LIFT

    caveats = [
        ("Every candidate was fitted on the same rows and scored on the same "
         f"{len(X_test):,} rows held back from all of them.")
        + (f" The split is the partition column '{partition}' ({len(X_train):,} training, "
           f"{len(X_test):,} validation) -- the same one saved models use." if partition else ""),
        "These models describe what predicts the outcome in THIS data. That is "
        "association, not causation.",
        # What this call does and does not leave behind. It used to say no
        # model store existed; one does now, so saying otherwise would send
        # a reader away from the thing they are looking for.
        "This comparison does not keep the winner -- it refits from scratch "
        "each time. To score new rows, save a model from this dataset and "
        "apply that instead.",
    ]
    if not beats:
        caveats.append(
            f"The best model scores {champion['score']} and simply guessing "
            f"scores {baseline_score}. Nothing here predicts "
            f"'{target}' meaningfully better than no model at all.")
    if champion["train_score"] is not None and \
            champion["train_score"] - champion["score"] > 0.15:
        caveats.append(
            f"The winner scores {champion['train_score']} on the rows it was "
            f"fitted to and {champion['score']} on rows it never saw -- it has "
            f"memorised detail that does not generalise.")
    if sampled:
        caveats.append(f"Fitted on a random sample of {FRAME_SAMPLE_THRESHOLD:,} rows.")

    return {
        "kind": "automated_prediction",
        "task": "classification" if classification else "regression",
        "target": target,
        "score_name": score_name,
        "candidates": sorted(
            results, key=lambda r: (r["score"] is None, -(r["score"] or 0))),
        "champion": champion,
        "baseline_score": baseline_score,
        "lift_over_baseline": lift,
        "beats_baseline": beats,
        "predictors_used": used,
        "predictors_skipped": skipped,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "split": ({"kind": "partition", "column": partition} if partition
                  else {"kind": "random", "test_share": TEST_SIZE}),
        "caveats": caveats,
    }
