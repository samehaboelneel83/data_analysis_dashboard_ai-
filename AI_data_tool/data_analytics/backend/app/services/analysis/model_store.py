"""Keep the champion, and score rows it has never seen.

`automated_prediction` compares candidates and throws every fitted model away --
its own caveat says so. This packages the winner so it can be stored and used
later, which is the difference between "what could predict this" and "score
these new rows".

THE HARD PART IS FEATURE ALIGNMENT, and it is the part a naive store gets
wrong. `_encode` one-hot encodes with `pd.get_dummies`, so **the columns it
produces depend on the values present in the frame**. A model trained on regions
{North, South, East} has three dummy columns; score a frame containing only
South and get one, in a different position. sklearn either raises, or -- far
worse -- reads the wrong number as the wrong feature and returns confident
nonsense. So the training column list travels with the model and every scored
frame is reindexed onto it.

That decides the unseen-category rule too. A value the model never saw becomes
zero across all of that column's dummies, which is the honest encoding: the
model has no opinion about it. But it must be REPORTED, or somebody scores a
year of new data against a model that recognises none of it and sees only a
column of plausible-looking answers.

SECURITY. The artifact is a joblib pickle, so loading one executes code. Only
artifacts THIS SERVICE WROTE are ever loaded -- nothing accepts an uploaded
model -- and the store is org-scoped like every other row. The other rule lives
at the endpoint: a model's feature columns are recorded so a caller who has
since been DENIED one of them can be refused, because a saved model carries the
denied column's influence inside it.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .automated_prediction import (MAX_CLASSES, MIN_ROWS, TEST_SIZE,
                                   AutomatedPredictionError)
from .decision_tree import OTHER, RANDOM_STATE, _encode, _usable_predictors, group_rare


class ModelStoreError(ValueError):
    """A model cannot be fitted, stored or applied, with the reason."""


@dataclass(frozen=True)
class PackagedModel:
    """A fitted model plus everything needed to use it again.

    `features` are the columns a caller must supply. `feature_columns` are the
    ENCODED columns the estimator actually expects, in order -- the two differ
    whenever a categorical predictor is present, and confusing them is how a
    model store silently mis-aligns its inputs.
    """
    artifact: bytes
    target: str
    features: list[str]
    feature_columns: list[str]
    categories: dict[str, list[str]]
    task: str                  # 'classification' | 'regression'
    model_family: str
    score: float | None
    score_name: str
    #: E13: how this model was chosen and on what -- the comparison it won,
    #: the baseline it had to beat, the split, the rows and predictors used.
    #: The router adds what it knows (the dataset's state, the row scope).
    card: dict = field(default_factory=dict)


def _fit_estimator(task: str, family: str, leaf: int) -> Any:
    """The same candidate the comparison named, constructed the same way.

    Built from the family NAME rather than handed the fitted object, so the
    stored model is a fresh fit on the full frame -- the comparison's fit saw
    only the training split, and a model that ignores a quarter of the data it
    was given is not the model anyone wants to keep.
    """
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from .automated_prediction import with_gaps_filled
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    if task == "classification":
        table = {
            "always the most common": lambda: DummyClassifier(strategy="most_frequent"),
            "decision tree": lambda: DecisionTreeClassifier(
                max_depth=4, random_state=RANDOM_STATE, min_samples_leaf=leaf),
            "random forest": lambda: RandomForestClassifier(
                n_estimators=100, max_depth=8, random_state=RANDOM_STATE,
                min_samples_leaf=leaf, n_jobs=1),
            "logistic regression": lambda: with_gaps_filled(LogisticRegression(
                max_iter=1000, random_state=RANDOM_STATE)),
        }
    else:
        table = {
            "always the average": lambda: DummyRegressor(strategy="mean"),
            "decision tree": lambda: DecisionTreeRegressor(
                max_depth=4, random_state=RANDOM_STATE, min_samples_leaf=leaf),
            "random forest": lambda: RandomForestRegressor(
                n_estimators=100, max_depth=8, random_state=RANDOM_STATE,
                min_samples_leaf=leaf, n_jobs=1),
            "linear regression": lambda: with_gaps_filled(LinearRegression()),
        }
    if family not in table:
        raise ModelStoreError(f"Unknown model family '{family}'")
    return table[family]()


def fit_and_package(df: pd.DataFrame, target: str,
                    predictors: list[str] | None = None,
                    family: str | None = None) -> PackagedModel:
    """Choose a champion, refit it on everything, and package it for storage.

    Runs the same comparison `automated_prediction` does -- one shared split, a
    dumb baseline included -- so the reported score is a held-out score rather
    than the model grading its own homework. The KEPT model is then refit on the
    full frame: the score describes a model fitted on three quarters, and the
    model you keep should have seen all of it.
    """
    from .automated_prediction import automated_prediction

    try:
        report = automated_prediction(df, target, predictors)
    except AutomatedPredictionError as e:
        raise ModelStoreError(str(e)) from e

    champion_name = report["champion"]["model"]
    task = report["task"]
    if family:
        champion_name = family

    used, _skipped = _usable_predictors(df, target, predictors, allow_grouping=True)
    frame = df[[target, *used]].dropna(subset=[target])
    # The same grouping the comparison used; the kept values become the
    # model's category list, and scoring maps anything else to "(other)".
    frame, _grouped = group_rare(frame, used)
    if len(frame) < MIN_ROWS:
        raise ModelStoreError(
            f"Only {len(frame)} usable rows; at least {MIN_ROWS} are needed.")

    y = frame[target]
    if task == "classification":
        y = y.astype(str)

    X, _labels = _encode(frame, used)
    leaf = max(2, int(len(X) * (1 - TEST_SIZE)) // 100)
    estimator = _fit_estimator(task, champion_name, leaf)
    try:
        estimator.fit(X, y)
    except Exception as e:                       # noqa: BLE001 - reported, not swallowed
        raise ModelStoreError(
            f"The chosen model ({champion_name}) could not be refitted on the "
            f"full data: {e}") from e

    # The values each categorical predictor was trained on. Kept so scoring can
    # name the ones it has never seen instead of silently encoding them as zero.
    categories = {
        c: sorted({str(v) for v in frame[c].dropna().unique()})
        for c in used if not pd.api.types.is_numeric_dtype(frame[c])
    }

    import joblib
    buf = io.BytesIO()
    joblib.dump(estimator, buf)

    return PackagedModel(
        artifact=buf.getvalue(),
        target=target,
        features=list(used),
        feature_columns=[str(c) for c in X.columns],
        categories=categories,
        task=task,
        model_family=champion_name,
        score=report["champion"].get("score"),
        score_name=report.get("score_name", ""),
        card={
            "candidates": [{"model": c.get("model"), "score": c.get("score")}
                           for c in report.get("candidates") or []],
            "baseline_score": report.get("baseline_score"),
            "lift_over_baseline": report.get("lift_over_baseline"),
            "beats_baseline": report.get("beats_baseline"),
            "predictors_used": list(report.get("predictors_used") or used),
            "predictors_skipped": report.get("predictors_skipped") or [],
            "n_train": report.get("n_train"), "n_test": report.get("n_test"),
            "split": report.get("split"),
            # The kept model is refit on every usable row, not the training share.
            "n_fitted": int(len(frame)),
            "caveats": report.get("caveats") or [],
            # E13: what each predictor looked like in training, for drift.
            "feature_profile": feature_profile(frame, used),
        },
    )


#: Drift bins: deciles for a number, the most common values for a category.
PROFILE_BINS = 10
PROFILE_TOP_CATEGORIES = 20
#: Population stability index thresholds, as usually read.
PSI_MODERATE, PSI_MAJOR = 0.1, 0.25


def feature_profile(frame: pd.DataFrame, features: list[str]) -> dict:
    """Each predictor's distribution in the training rows, compactly.

    A number: its decile edges and the share of rows in each bin. A category:
    the share of each of its most common values and of the rest. Enough to
    compare today's rows against, without keeping any row."""
    out: dict = {}
    for col in features:
        s = frame[col].dropna()
        if s.empty:
            continue
        if pd.api.types.is_numeric_dtype(s):
            edges = sorted({float(x) for x in s.quantile([i / PROFILE_BINS for i in range(PROFILE_BINS + 1)])})
            if len(edges) < 2:
                continue
            shares = _numeric_shares(pd.to_numeric(s, errors="coerce").dropna(), edges)
            out[col] = {"kind": "number", "edges": edges, "shares": shares, "rows": int(len(s))}
        else:
            vc = s.astype(str).value_counts(normalize=True)
            top = vc.head(PROFILE_TOP_CATEGORIES)
            shares = {str(k): float(v) for k, v in top.items()}
            rest = float(max(0.0, 1.0 - sum(shares.values())))
            out[col] = {"kind": "category", "shares": shares, "other": rest, "rows": int(len(s))}
    return out


def _numeric_shares(s: pd.Series, edges: list[float]) -> list[float]:
    """Shares in the training bins; values beyond the edges fall in the end bins."""
    import numpy as np
    idx = np.clip(np.searchsorted(edges, s.to_numpy(dtype=float), side="right") - 1, 0, len(edges) - 2)
    counts = np.bincount(idx, minlength=len(edges) - 1)
    total = counts.sum() or 1
    return [float(c) / total for c in counts]


def _psi(expected: list[float], actual: list[float]) -> float:
    import math
    eps = 1e-4
    return float(sum((a - e) * math.log((a + eps) / (e + eps)) for e, a in zip(expected, actual)))


def drift_report(profile: dict, frame: pd.DataFrame) -> dict:
    """How far each predictor has moved from training, as a population
    stability index: under 0.1 stable, 0.1-0.25 moderate, over that major."""
    features = []
    for col, p in (profile or {}).items():
        if col not in frame.columns:
            features.append({"feature": col, "psi": None, "level": "missing", "rows": 0})
            continue
        s = frame[col].dropna()
        if s.empty:
            features.append({"feature": col, "psi": None, "level": "missing", "rows": 0})
            continue
        if p["kind"] == "number":
            actual = _numeric_shares(pd.to_numeric(s, errors="coerce").dropna(), p["edges"])
            psi = _psi(p["shares"], actual)
            top_change = None
        else:
            vc = s.astype(str).value_counts(normalize=True)
            known = list(p["shares"])
            actual = [float(vc.get(k, 0.0)) for k in known]
            actual_other = float(max(0.0, 1.0 - sum(actual)))
            psi = _psi([*p["shares"].values(), p.get("other", 0.0)], [*actual, actual_other])
            new = [str(k) for k in vc.index if str(k) not in p["shares"]][:5]
            top_change = new or None
        level = "major" if psi >= PSI_MAJOR else "moderate" if psi >= PSI_MODERATE else "stable"
        features.append({"feature": col, "psi": round(psi, 4), "level": level, "rows": int(len(s)),
                         **({"new_values": top_change} if top_change else {})})
    rank = {"major": 0, "moderate": 1, "missing": 2, "stable": 3}
    features.sort(key=lambda f: (rank[f["level"]], -(f["psi"] or 0)))
    worst = features[0]["level"] if features else "stable"
    return {"features": features, "overall": worst, "rows": int(len(frame))}


def align_frame(pkg: PackagedModel, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Encode `df` into exactly the columns the estimator expects.

    Reindexing onto `feature_columns` is what makes this safe: a category absent
    from this frame becomes a zero column rather than shifting every feature
    after it, and a category the frame has gained is dropped rather than
    appended where the estimator expects something else.
    """
    missing = [c for c in pkg.features if c not in df.columns]
    if missing:
        # Distinct from an unseen VALUE: a missing COLUMN means the caller is
        # scoring the wrong data, and filling zeros would answer from a model
        # that saw none of its inputs.
        raise ModelStoreError(
            "These columns are needed to score with this model and are not in "
            f"the data: {', '.join(missing)}")

    # TYPES COME FROM TRAINING, NOT FROM THE FRAME. `_encode` decides one-hot
    # versus numeric by DTYPE, and a scored row arrives off the wire where every
    # value may be a string. Left alone, a numeric feature sent as "50" is
    # treated as a CATEGORY: it becomes a dummy column `spend__50`, the reindex
    # below finds no `spend`, and fills 0.0 -- a confident prediction from a
    # feature the model was handed and never saw, with nothing reported, because
    # `spend` is not a tracked category. The mirror case is a categorical
    # trained on "1" arriving as the integer 1.
    frame = df[pkg.features].copy()
    for column in pkg.features:
        if column in pkg.categories:
            # Trained as text, so compare as text: 1 and "1" are one value.
            frame[column] = frame[column].astype(str).where(frame[column].notna())
        else:
            coerced = pd.to_numeric(frame[column], errors="coerce")
            # Refused, never filled. Zero is a real number for most measures,
            # so quietly substituting it answers a different question.
            broke = frame[column].notna() & coerced.isna()
            if broke.any():
                bad = frame.loc[broke, column].iloc[0]
                raise ModelStoreError(
                    f"'{column}' was a number when this model was trained, and "
                    f"{bad!r} is not one.")
            frame[column] = coerced

    unseen: dict[str, list[str]] = {}
    for column, known in pkg.categories.items():
        if OTHER in known:
            # A grouped category: anything but its kept values is "(other)",
            # exactly as in training -- not an unseen value.
            frame[column] = frame[column].where(frame[column].isin(known) | frame[column].isna(), OTHER)
            continue
        present = {str(v) for v in frame[column].dropna().unique()}
        novel = sorted(present - set(known))
        if novel:
            unseen[column] = novel

    encoded, _labels = _encode(frame, pkg.features)
    aligned = encoded.reindex(columns=pkg.feature_columns, fill_value=0.0)
    return aligned.astype(float).fillna(0.0), unseen


def score_frame(pkg: PackagedModel, df: pd.DataFrame) -> dict:
    """Predictions for rows the model has never seen.

    The target column is not required and is ignored when present -- the point
    of scoring is rows whose outcome is not known yet.
    """
    import joblib

    aligned, unseen = align_frame(pkg, df)
    estimator = joblib.load(io.BytesIO(pkg.artifact))
    raw = estimator.predict(aligned)

    if pkg.task == "classification":
        predictions: list[Any] = [str(v) for v in raw]
    else:
        predictions = [float(v) for v in raw]

    return {
        "predictions": predictions,
        "n_scored": len(predictions),
        "unseen_values": unseen,
        "target": pkg.target,
        "task": pkg.task,
        "model_family": pkg.model_family,
    }
