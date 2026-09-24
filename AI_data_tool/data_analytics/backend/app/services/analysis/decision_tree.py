"""A decision tree: the rules that separate one outcome from another.

SAS Visual Statistics' headline object, and the one analysis in this catalogue
that answers "why" with something a person can read out loud: *if margin is
below 12% and the channel is Wholesale, three quarters of these churn*.
Correlations and effect sizes describe a relationship; a tree gives you the
branch.

scikit-learn is imported LAZILY, inside the function, for the same reason
`segment.py` and `anomaly.py` do it -- a heavy BLAS/model-selection import must
never land on the app-import path, and a third sklearn analysis must not be the
one that undoes that.

Three decisions carry most of the honesty:

  * **Scored on rows it never saw.** A tree deep enough reproduces its training
    data exactly, so training accuracy measures nothing. The headline score is
    held out; the training score comes back beside it precisely so the gap is
    visible, and a wide gap adds a caveat saying what it means.

  * **Shallow by default, and capped.** A depth-20 tree is not an explanation;
    it is the data written out longhand. Four levels is what a person reads, and
    the cap means an author cannot accidentally ask for the longhand version.

  * **Columns it cannot use are named.** A reader who is not told a column was
    skipped will assume it was considered and found unimportant -- the opposite
    of the truth.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

RANDOM_STATE = 42

#: Separator between a one-hot column's source and its value. A unit separator
#: rather than an underscore because `region_North` is ambiguous when a real
#: column is called `region_north`, and written as an escape because pasting a
#: control character into source is how a NUL byte got in here once.
SEP = "\x1f"

#: Four levels is about what a person can hold while reading a branch aloud.
DEFAULT_MAX_DEPTH = 4
#: Asked for more, they get this. See the module docstring: past here a tree
#: stops being an explanation.
HARD_MAX_DEPTH = 8

#: A categorical predictor with more distinct values than this is an
#: identifier, a free-text field or a date -- one-hot encoding it would add
#: hundreds of columns that each split one row off.
MAX_PREDICTOR_CARDINALITY = 20
#: A "classification" over more labels than this is not a tree anybody reads.
MAX_TARGET_CLASSES = 20
#: Enough rows that a held-out quarter is a real test rather than a rounding
#: error. Below this the honest answer is "not enough data".
MIN_ROWS = 40
#: Same cap the sibling analyses use: fitting over an unbounded import frame
#: turns one request into a very long one.
FRAME_SAMPLE_THRESHOLD = 50_000

#: Beyond this gap between training and held-out score, the tree has memorised
#: rather than learned, and the reader is told so.
MEMORISED_GAP = 0.15


class DecisionTreeError(ValueError):
    """Not something a readable tree can be fitted to, with the reason."""


def _usable_predictors(df: pd.DataFrame, target: str,
                       requested: list[str] | None) -> tuple[list[str], list[dict]]:
    """Which columns can be split on, and why the others cannot.

    Named rather than silently dropped: a reader who is not told a column was
    skipped will read its absence from the importance list as "considered and
    unimportant".
    """
    candidates = [c for c in (requested or df.columns) if c != target]
    used: list[str] = []
    skipped: list[dict] = []
    for column in candidates:
        if column not in df.columns:
            skipped.append({"column": column, "reason": "not in this dataset"})
            continue
        series = df[column]
        if pd.api.types.is_numeric_dtype(series):
            if series.notna().sum() == 0:
                skipped.append({"column": column, "reason": "no values"})
            else:
                used.append(column)
            continue
        if pd.api.types.is_datetime64_any_dtype(series):
            skipped.append({"column": column,
                            "reason": "a date -- split on a derived part of it "
                                      "(month, year) instead"})
            continue
        distinct = series.nunique(dropna=True)
        if distinct < 2:
            skipped.append({"column": column, "reason": "only one value"})
        elif distinct > MAX_PREDICTOR_CARDINALITY:
            skipped.append({
                "column": column,
                "reason": f"{distinct:,} distinct values -- too many to split "
                          f"on, and usually an identifier rather than a predictor"})
        else:
            used.append(column)
    return used, skipped


def _encode(df: pd.DataFrame, predictors: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """Numeric matrix for sklearn, plus how to say each column out loud again.

    Categorical predictors are one-hot encoded, which makes a split read
    `region_North <= 0.5` -- true, and unreadable. The mapping back is what lets
    the tree say "region is not North".
    """
    frame = df[predictors]
    encoded = pd.get_dummies(frame, columns=[
        c for c in predictors if not pd.api.types.is_numeric_dtype(frame[c])
    ], prefix_sep=SEP)
    labels: dict[str, str] = {}
    for column in encoded.columns:
        if SEP in str(column):
            source, value = str(column).split(SEP, 1)
            labels[str(column)] = f"{source} is {value}"
        else:
            labels[str(column)] = str(column)
    return encoded.astype(float), labels


def _node(tree, index: int, feature_names: list[str], labels: dict[str, str],
          classes: list[str] | None) -> dict:
    """One node of the fitted tree, as something renderable.

    The `label` is the sentence the split makes. For a one-hot column the
    arithmetic (`<= 0.5`) is an encoding artefact, so it is rendered as
    membership instead -- `region is not North` rather than a threshold on a
    number nobody put in their data.
    """
    left = int(tree.children_left[index])
    right = int(tree.children_right[index])
    samples = int(tree.n_node_samples[index])

    if classes is not None:
        counts = tree.value[index][0]
        prediction = classes[int(np.argmax(counts))]
        total = float(counts.sum()) or 1.0
        confidence = round(float(counts.max()) / total, 4)
        distribution = {classes[i]: int(round(float(c)))
                        for i, c in enumerate(counts)}
    else:
        prediction = round(float(tree.value[index][0][0]), 6)
        confidence = None
        distribution = None

    node: dict[str, Any] = {
        "samples": samples,
        "prediction": prediction,
        "confidence": confidence,
        "distribution": distribution,
        "feature": None,
        "label": None,
        "threshold": None,
        "children": [],
    }
    if left == right:                       # a leaf
        return node

    raw = feature_names[int(tree.feature[index])]
    threshold = float(tree.threshold[index])
    is_onehot = SEP in raw
    source = raw.split(SEP, 1)[0] if is_onehot else raw
    node["feature"] = source
    node["threshold"] = None if is_onehot else round(threshold, 6)
    node["label"] = (f"{labels[raw].replace(' is ', ' is not ', 1)}" if is_onehot
                     else f"{source} <= {round(threshold, 4)}")
    node["children"] = [
        _node(tree, left, feature_names, labels, classes),
        _node(tree, right, feature_names, labels, classes),
    ]
    return node


def decision_tree(df: pd.DataFrame, target: str,
                  predictors: list[str] | None = None,
                  max_depth: int | None = None) -> dict:
    """Fit a shallow, readable decision tree and describe it."""
    from sklearn.model_selection import train_test_split
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    if target not in df.columns:
        raise DecisionTreeError(f"Column '{target}' not found")

    depth = min(int(max_depth or DEFAULT_MAX_DEPTH), HARD_MAX_DEPTH)
    depth = max(1, depth)

    used, skipped = _usable_predictors(df, target, predictors)
    if not used:
        raise DecisionTreeError(
            "No column can be used as a predictor here. Numeric columns and "
            "categorical ones with a manageable number of values can be split "
            "on; identifiers and dates cannot.")

    frame = df[[target, *used]].dropna(subset=[target])
    sampled = len(frame) > FRAME_SAMPLE_THRESHOLD
    if sampled:
        frame = frame.sample(FRAME_SAMPLE_THRESHOLD, random_state=RANDOM_STATE)
    if len(frame) < MIN_ROWS:
        raise DecisionTreeError(
            f"Only {len(frame)} usable rows; at least {MIN_ROWS} are needed to "
            f"hold any back for testing.")

    y = frame[target]
    numeric_target = pd.api.types.is_numeric_dtype(y) and y.nunique() > MAX_TARGET_CLASSES
    if not numeric_target:
        y = y.astype(str)
        classes = sorted(y.unique())
        if len(classes) < 2:
            raise DecisionTreeError(
                f"'{target}' has only one value, so there is nothing to separate.")
        if len(classes) > MAX_TARGET_CLASSES:
            raise DecisionTreeError(
                f"'{target}' has {len(classes):,} distinct values. A tree over "
                f"that many outcomes is not readable -- group them first, or "
                f"pick a numeric measure to predict.")
    else:
        classes = None

    X, labels = _encode(frame, used)
    # Stratified where it can be: an uncommon class must appear on both sides of
    # the split, or the held-out score is measuring a different problem.
    stratify = y if classes is not None and y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=stratify)

    if classes is not None:
        model = DecisionTreeClassifier(max_depth=depth, random_state=RANDOM_STATE,
                                       min_samples_leaf=max(2, len(X_train) // 100))
        score_name = "accuracy"
    else:
        model = DecisionTreeRegressor(max_depth=depth, random_state=RANDOM_STATE,
                                      min_samples_leaf=max(2, len(X_train) // 100))
        score_name = "r2"
    model.fit(X_train, y_train)

    score = round(float(model.score(X_test, y_test)), 4)
    train_score = round(float(model.score(X_train, y_train)), 4)

    feature_names = [str(c) for c in X.columns]
    # Importance is reported per ORIGINAL column: one-hot splits a categorical
    # into several, and listing each dummy separately would make a strong
    # categorical predictor look like several weak ones.
    per_source: dict[str, float] = {}
    for name, weight in zip(feature_names, model.feature_importances_):
        source = name.split(SEP, 1)[0]
        per_source[source] = per_source.get(source, 0.0) + float(weight)
    importance = [{"column": c, "importance": round(v, 4)}
                  for c, v in sorted(per_source.items(),
                                     key=lambda kv: kv[1], reverse=True)]

    caveats = [
        "A tree describes which splits separate the outcomes in THIS data. "
        "That is association, not causation.",
        f"Scored on {len(X_test):,} rows held back from fitting.",
    ]
    if train_score - score > MEMORISED_GAP:
        caveats.append(
            f"The tree scores {train_score} on the rows it was fitted to and "
            f"{score} on rows it never saw -- it has memorised detail that does "
            f"not generalise. A shallower tree would be more trustworthy.")
    if sampled:
        caveats.append(
            f"Fitted on a random sample of {FRAME_SAMPLE_THRESHOLD:,} rows.")
    if skipped:
        caveats.append(
            f"{len(skipped)} column(s) could not be used as predictors.")

    return {
        "kind": "decision_tree",
        "task": "regression" if classes is None else "classification",
        "target": target,
        "predictors_used": used,
        "predictors_skipped": skipped,
        "tree": _node(model.tree_, 0, feature_names, labels, classes),
        "importance": importance,
        "score": score,
        "score_name": score_name,
        "train_score": train_score,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "max_depth": depth,
        "caveats": caveats,
    }
