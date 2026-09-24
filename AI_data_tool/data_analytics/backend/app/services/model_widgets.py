"""Models as canvas widgets (MASTER_PLAN Phase 3).

SAS VA's statistics objects are its strongest work: drop Logistic Regression on
the page, assign a response and predictors, and it fits and renders a header
(event, fit statistic, population) over tabbed diagnostics. The mathematics was
already here -- the analysis registry's `regression`, `glm_logistic`,
`decision_tree` and `segment` -- but only as one-shot results in a panel. These
shapers make the same fits into widgets: live on the page, fed the secured
frame every other widget reads, re-fitting when cross-filters narrow it.

Each shaper REUSES the registry's fitting code, so a coefficient here is the
number the Statistics panel shows for the same data. What this module adds:

  * population -- rows in the frame, rows the model used, and WHICH columns
    dropped the rest (SAS: "Observations: 646K of 2.3M");
  * diagnostics computed from the model's own coefficients, not a second fit,
    so the residual plot cannot describe a different model than the table;
  * a "just guess" baseline beside every score, the house rule since
    `automated_prediction`: a model is only as good as its margin over it.

Results are `{"type": "model", "status": "ok"|"incomplete"|"refused", ...}`;
a refusal carries its reason in words (constitution rule 1).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

#: Points returned for scatter diagnostics -- enough to see a pattern, few
#: enough to draw as SVG. Picked evenly (deterministically), never randomly.
DIAG_POINTS = 400
#: The comparison's shared split. Fixed so the verdict is reproducible.
SPLIT_SEED = 42
TEST_SHARE = 0.3
ROC_STEPS = 20


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, 6)


def _even_sample(n: int, k: int = DIAG_POINTS) -> np.ndarray:
    return np.unique(np.linspace(0, n - 1, num=min(n, k)).astype(int)) if n else np.array([], dtype=int)


def _population(df: pd.DataFrame, numeric: list[str], raw: list[str], used: int) -> dict:
    """Rows in, rows used, and which columns cost the difference."""
    dropped_by: dict[str, int] = {}
    for c in numeric:
        if c in df.columns:
            n = int(pd.to_numeric(df[c], errors="coerce").isna().sum())
            if n:
                dropped_by[c] = n
    for c in raw:
        if c in df.columns:
            n = int(df[c].isna().sum())
            if n:
                dropped_by[c] = n
    total = int(len(df))
    return {"rows_total": total, "rows_used": int(used),
            "rows_dropped": max(0, total - int(used)), "dropped_by": dropped_by}


def _incomplete(needs: list[str]) -> dict:
    return {"type": "model", "status": "incomplete", "needs": needs, "rows": []}


def _refused(reason: str, population: dict | None = None) -> dict:
    return {"type": "model", "status": "refused", "reason": reason,
            "population": population, "rows": []}


def _predictors(config: dict, target: str | None) -> list[str]:
    raw = config.get("predictors") or config.get("measures") or []
    return [p for p in raw if isinstance(p, str) and p and p != target]


#: A text predictor becomes one indicator per level; past this many levels the
#: coefficient table stops being readable and the fit stops being stable.
MAX_LEVELS = 12


class _Design:
    """Predictors made numeric: text columns one-hot against a reference level.

    `regression` and `glm_logistic` are numeric-only, so "churn ~ tenure +
    region" used to be impossible. Region is expanded here to `region=South`,
    `region=West`, ... each read against the most common level, and the
    reference is REPORTED (`encodings`) -- a coefficient for "South" means
    nothing until the reader knows what it is compared with."""

    def __init__(self, df: pd.DataFrame, target: str, preds: list[str]):
        self.frame = pd.DataFrame({target: df[target]}, index=df.index)
        self.columns: list[str] = []
        self.numeric: list[str] = []
        self.categorical: list[str] = []
        self.encodings: dict[str, dict] = {}
        self.expanded: dict[str, list[str]] = {}
        self.refusal: str | None = None
        for p in preds:
            raw = df[p]
            num = pd.to_numeric(raw, errors="coerce")
            present = raw.notna()
            if present.any() and num[present].notna().mean() >= 0.9:
                self.frame[p] = num
                self.columns.append(p); self.numeric.append(p); self.expanded[p] = [p]
                continue
            counts = raw.dropna().astype(str).value_counts()
            if len(counts) < 2:
                self.refusal = f"'{p}' has only one value in these rows, so it cannot explain anything."
                return
            if len(counts) > MAX_LEVELS:
                self.refusal = (f"'{p}' has {len(counts)} different values; a text predictor can carry at "
                                f"most {MAX_LEVELS}. Group it into fewer categories first.")
                return
            ref = str(counts.index[0])
            as_text = raw.astype(str).where(present)
            cols = []
            for lvl in counts.index[1:]:
                name = f"{p}={lvl}"
                self.frame[name] = (as_text == str(lvl)).astype(float).where(present)
                cols.append(name)
            self.columns.extend(cols); self.categorical.append(p); self.expanded[p] = cols
            self.encodings[p] = {"reference": ref, "levels": [str(x) for x in counts.index]}


def _linear_predict(frame: pd.DataFrame, coefficients: list[dict]) -> np.ndarray:
    yhat = np.zeros(len(frame))
    for c in coefficients:
        b = c.get("coefficient") or 0.0
        yhat = yhat + (b if c["term"] == "const" else b * frame[c["term"]].to_numpy(dtype=float))
    return yhat


# ── Linear regression ────────────────────────────────────────────────────────

def _partition(df: pd.DataFrame, config: dict):
    """(train_mask, validation_mask, column) from the Partition role, or a
    refusal string, or None when no partition is assigned.

    Rows whose label starts with "train" (any case) are training rows; every
    other labelled row is validation. Matches `prep.partition_column`'s
    "Training"/"Validation", and a hand-made 1/0 or train/test column too."""
    col = config.get("partition")
    if not col:
        return None
    if col not in df.columns:
        return f"Partition column '{col}' is not in this dataset."
    labels = df[col].astype(str).str.strip().str.lower()
    present = df[col].notna()
    train = present & (labels.str.startswith("train") | (labels == "1"))
    valid = present & ~train
    return train, valid, col


def _partition_refusal(col: str, n_train: int, n_valid: int) -> str | None:
    if n_train < 10 or n_valid < 5:
        return (f"Partition '{col}' leaves {n_train} training and {n_valid} validation rows here "
                f"(after filters and missing values); need at least 10 and 5.")
    return None


def shape_model_linear(df: pd.DataFrame, config: dict) -> dict:
    from .analysis.inferential import StatisticalError, regression

    target = config.get("measure")
    preds = _predictors(config, target)
    needs = ([] if target else ["Response"]) + ([] if preds else ["Predictors"])
    if needs:
        return _incomplete(needs)
    d = _Design(df, target, preds)
    pop = lambda used: _population(df, [target, *d.numeric], d.categorical, used)  # noqa: E731
    if d.refusal:
        return _refused(d.refusal, pop(0))
    part = _partition(df, config)
    if isinstance(part, str):
        return _refused(part, pop(0))

    work = d.frame.apply(pd.to_numeric, errors="coerce").dropna()
    train_idx = work.index if part is None else work.index[part[0].reindex(work.index).to_numpy()]
    valid_idx = None if part is None else work.index[part[1].reindex(work.index).to_numpy()]
    if part is not None:
        why = _partition_refusal(part[2], len(train_idx), len(valid_idx))
        if why:
            return _refused(why, pop(len(work)))
    try:
        r = regression(d.frame.loc[train_idx], target, d.columns).to_dict()
    except StatisticalError as e:
        return _refused(str(e), pop(0))

    coefs = r["detail"]["coefficients"]
    y = work[target].to_numpy(dtype=float)
    yhat = _linear_predict(work, coefs)
    resid = y - yhat
    idx = _even_sample(len(work))
    y_tr = work.loc[train_idx, target].to_numpy(dtype=float)
    fit: dict[str, Any] = {"name": "R²", "value": r["detail"].get("r_squared"),
                           "secondary": {"adjusted R²": r["detail"].get("adj_r_squared")}}
    if part is None:
        rmse = float(np.sqrt(np.mean(resid ** 2))) if len(resid) else None
        # "Just guess the mean": its RMSE is the target's own spread. A model that
        # does not beat it has learnt nothing, whatever its p-values say.
        fit["secondary"].update({"RMSE": _num(rmse), "RMSE of guessing the mean": _num(np.std(y) if len(y) else None)})
        population = pop(r["n"])
    else:
        # With a partition the headline is the score on rows the model never
        # saw; the training R² moves to the side, where it belongs.
        vmask = work.index.isin(valid_idx)
        y_va, e_va = y[vmask], resid[vmask]
        sst = float(np.sum((y_va - y_tr.mean()) ** 2)) or float("nan")
        fit = {"name": "R² on validation rows", "value": _num(1 - float(np.sum(e_va ** 2)) / sst),
               "secondary": {"R² on training rows": r["detail"].get("r_squared"),
                             "RMSE on validation rows": _num(np.sqrt(np.mean(e_va ** 2))),
                             "RMSE of guessing the training mean": _num(np.sqrt(np.mean((y_va - y_tr.mean()) ** 2)))}}
        population = pop(len(work))
        population["partition"] = {"column": part[2], "train_rows": int(len(train_idx)),
                                   "validation_rows": int(len(valid_idx))}
    return {
        "type": "model", "status": "ok", "model": "linear", "target": target,
        "predictors": preds, "encodings": d.encodings, "result": r,
        "population": population, "fit": fit,
        "diagnostics": {
            "residuals": [[_num(yhat[i]), _num(resid[i])] for i in idx],
            "actual_predicted": [[_num(y[i]), _num(yhat[i])] for i in idx],
        },
        "rows": [{"name": c["term"], "value": c["coefficient"]} for c in coefs],
    }


# ── Logistic regression ──────────────────────────────────────────────────────

def _auc(y: np.ndarray, p: np.ndarray) -> float | None:
    """Mann-Whitney AUC -- the probability a random event scores above a random non-event."""
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _roc(y: np.ndarray, p: np.ndarray) -> list[list[float | None]]:
    pts = []
    P, N = max(int((y == 1).sum()), 1), max(int((y == 0).sum()), 1)
    for t in np.linspace(1, 0, ROC_STEPS + 1):
        pred = p >= t
        pts.append([_num(((pred) & (y == 0)).sum() / N), _num(((pred) & (y == 1)).sum() / P)])
    # A curve always runs from "call nothing positive" (0,0): a model whose
    # scores reach exactly 1 (a pure tree leaf) would otherwise start mid-plot.
    if pts and pts[0] != [0.0, 0.0]:
        pts.insert(0, [0.0, 0.0])
    return pts


def shape_model_logistic(df: pd.DataFrame, config: dict) -> dict:
    from .analysis.inferential import StatisticalError, glm_logistic

    target = config.get("response")
    preds = _predictors(config, target)
    needs = ([] if target else ["Response"]) + ([] if preds else ["Predictors"])
    if needs:
        return _incomplete(needs)
    event = config.get("event_value") or None
    d = _Design(df, target, preds)
    pop = lambda used: _population(df, d.numeric, [target, *d.categorical], used)  # noqa: E731
    if d.refusal:
        return _refused(d.refusal, pop(0))
    part = _partition(df, config)
    if isinstance(part, str):
        return _refused(part, pop(0))
    work = d.frame.dropna()
    train_idx = work.index if part is None else work.index[part[0].reindex(work.index).to_numpy()]
    if part is not None:
        n_valid = int(part[1].reindex(work.index).sum())
        why = _partition_refusal(part[2], len(train_idx), n_valid)
        if why:
            return _refused(why, pop(len(work)))
    try:
        r = glm_logistic(d.frame.loc[train_idx], target, d.columns, event).to_dict()
    except StatisticalError as e:
        return _refused(str(e), pop(0))

    positive = r["detail"].get("positive_outcome")
    # Diagnostics describe the rows the verdict is about: the held-out rows
    # when there is a partition, otherwise every row the model used.
    scored = work if part is None else work[part[1].reindex(work.index).to_numpy()]
    y = (scored[target].astype(str) == str(positive)).to_numpy(dtype=int)
    logit = _linear_predict(scored, r["detail"]["coefficients"])
    p = 1 / (1 + np.exp(-np.clip(logit, -40, 40)))
    pred = (p >= 0.5).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    n = max(len(y), 1)
    base = max(y.mean(), 1 - y.mean()) if len(y) else None
    where = "" if part is None else " on validation rows"
    population = pop(r["n"] if part is None else len(work))
    if part is not None:
        population["partition"] = {"column": part[2], "train_rows": int(len(train_idx)),
                                   "validation_rows": int(len(scored))}
    return {
        "type": "model", "status": "ok", "model": "logistic", "target": target,
        "event": positive, "predictors": preds, "encodings": d.encodings, "result": r,
        "population": population,
        "fit": {"name": f"AUC{where}", "value": _num(_auc(y, p)),
                "secondary": {f"accuracy at 0.5{where}": _num((tp + tn) / n),
                              "accuracy of always guessing the commoner outcome": _num(base),
                              "McFadden pseudo-R² (training)" if part is not None else "McFadden pseudo-R²":
                                  r.get("effect_size")}},
        "diagnostics": {"confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "threshold": 0.5},
                        "roc": _roc(y, p)},
        "rows": [{"name": c["term"], "value": c.get("odds_ratio")} for c in r["detail"]["coefficients"]],
    }


# ── Decision tree ────────────────────────────────────────────────────────────

def shape_model_tree(df: pd.DataFrame, config: dict) -> dict:
    from .analysis.decision_tree import DecisionTreeError, decision_tree

    target = config.get("response")
    preds = _predictors(config, target) or None
    if not target:
        return _incomplete(["Response"])
    try:
        r = decision_tree(df, target, preds, config.get("max_depth"))
    except DecisionTreeError as e:
        return _refused(str(e), _population(df, [], [target, *(preds or [])], 0))
    used = int(r.get("n_train", 0)) + int(r.get("n_test", 0))
    importance = (r["importance"].items() if isinstance(r.get("importance"), dict)
                  else [(i.get("column") or i.get("name"), i.get("importance")) for i in (r.get("importance") or [])])
    importance = [(k, _num(v)) for k, v in importance]
    warnings = []
    # One column that decides everything, with a near-perfect score, is almost
    # always a relabelling of the response (product -> category), not a finding.
    top = max(importance, key=lambda kv: kv[1] or 0, default=None)
    if top and (top[1] or 0) >= 0.98 and (_num(r.get("score")) or 0) >= 0.98:
        warnings.append(f"'{top[0]}' alone determines {target}. It is probably another name for the "
                        f"answer rather than a predictor; leave it out to learn something new.")
    return {
        "type": "model", "status": "ok", "model": "tree", "target": target,
        "predictors": r.get("predictors_used", []), "result": r,
        "population": _population(df, [], [target, *(r.get("predictors_used") or [])], used),
        "fit": {"name": r.get("score_name") or "score", "value": _num(r.get("score")),
                "secondary": {"on the rows it trained on": _num(r.get("train_score")),
                              "rows held out for scoring": r.get("n_test")}},
        "warnings": warnings,
        "rows": [{"name": k, "value": v} for k, v in importance],
    }


# ── Clustering ───────────────────────────────────────────────────────────────

def shape_model_cluster(df: pd.DataFrame, config: dict) -> dict:
    from .analysis.segment import SegmentError, segment_dataframe

    cols = [c for c in (config.get("measures") or []) if isinstance(c, str) and c]
    if len(cols) < 2:
        return _incomplete(["Variables (at least two)"])
    try:
        out = segment_dataframe(df, cols).to_dict()
    except SegmentError as e:
        return _refused(str(e), _population(df, cols, [], 0))
    meta = out.get("meta", {})
    centroids = meta.get("centroids", [])
    return {
        "type": "model", "status": "ok", "model": "cluster", "variables": cols, "result": out,
        "population": {**_population(df, cols, [], meta.get("n_rows_used", 0)),
                       **({"sampled_from": meta.get("n_rows_total")} if meta.get("sampled") else {})},
        "fit": {"name": "silhouette", "value": _num(meta.get("silhouette")),
                "secondary": {"segments": meta.get("params", {}).get("k")}},
        "warnings": out.get("warnings", []),
        "rows": [{"name": f"Segment {c['cluster'] + 1}", "value": c.get("size")} for c in centroids],
    }


# ── Model comparison ─────────────────────────────────────────────────────────

def _is_classification(y: pd.Series) -> bool:
    return not pd.api.types.is_numeric_dtype(y) or y.nunique(dropna=True) <= 2


def shape_model_compare(df: pd.DataFrame, config: dict) -> dict:
    """Fit every chosen model on ONE shared, seeded split and name the winner.

    Comparing each model's own in-sample statistic would reward whichever
    over-fits most, and an R² cannot be set beside an AUC. So every candidate
    is refitted here on the same 70% and scored on the same unseen 30%, with
    the "just guess" baseline scored the same way."""
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.metrics import r2_score, roc_auc_score
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    specs = [s for s in (config.get("compare") or []) if isinstance(s, dict)]
    responses = {s.get("response") for s in specs if s.get("response")}
    if len(specs) < 2:
        return _refused("Model comparison needs at least two models on this page. Add a "
                        "regression, logistic or decision-tree widget, then choose them here.")
    if len(responses) != 1:
        return _refused("These models predict different things (" + ", ".join(sorted(map(str, responses)))
                        + "). Only models of the same response can be compared.")
    target = responses.pop()
    if target not in df.columns:
        return _refused(f"Column '{target}' is not in this dataset.")
    # A tree left on "every other column" has no stored predictor list; it
    # competes on every other column, as it would if refitted by hand.
    def _spec_preds(s: dict) -> list[str]:
        listed = [p for p in (s.get("predictors") or []) if p in df.columns and p != target]
        return listed if listed or s.get("model") != "tree" else [c for c in df.columns if c != target]
    wanted = sorted({p for s in specs for p in _spec_preds(s)})
    # Text predictors enter the shared refit one-hot, like the models' own fits;
    # a column that cannot (too many levels) is NAMED and left out, never silently.
    usable, skipped_cols = [], {}
    for p in wanted:
        probe = _Design(df, target, [p])
        if probe.refusal:
            skipped_cols[p] = probe.refusal
        else:
            usable.append(p)
    if not usable:
        return _refused("None of the chosen models has a usable predictor.")
    d = _Design(df, target, usable)
    cols = d.columns
    work = d.frame.copy()
    work[cols] = work[cols].apply(pd.to_numeric, errors="coerce")
    work = work.dropna()
    if len(work) < 30:
        return _refused(f"Only {len(work)} complete rows across the compared models' columns; need at least 30.")
    classification = _is_classification(work[target])
    # A shared Partition, when the models were given one, IS the split: the
    # comparison then grades them on exactly the rows each already holds out.
    part_cols = {s.get("partition") for s in specs if s.get("partition")}
    if len(part_cols) > 1:
        return _refused("These models hold out different partitions (" + ", ".join(sorted(part_cols))
                        + "). Give them the same one to compare them fairly.")
    part = _partition(df, {"partition": next(iter(part_cols))}) if part_cols else None
    if isinstance(part, str):
        return _refused(part)
    if part is None:
        rng = np.random.default_rng(SPLIT_SEED)
        test_mask = rng.random(len(work)) < TEST_SHARE
    else:
        test_mask = part[1].reindex(work.index).fillna(False).to_numpy(dtype=bool)
        keep = (part[0] | part[1]).reindex(work.index).fillna(False).to_numpy(dtype=bool)
        work, test_mask = work[keep], test_mask[keep]
    train, test = work[~test_mask], work[test_mask]
    if part is not None:
        why = _partition_refusal(part[2], len(train), len(test))
        if why:
            return _refused(why)
    if classification:
        classes = work[target].astype(str)
        event = next((s.get("event_value") for s in specs if s.get("event_value")), None) \
            or classes.value_counts().idxmin()
        y_tr = (train[target].astype(str) == str(event)).astype(int)
        y_te = (test[target].astype(str) == str(event)).astype(int)
        if y_tr.nunique() < 2 or y_te.nunique() < 2:
            return _refused("One side of the split holds only one outcome; the models cannot be scored.")
    else:
        y_tr, y_te = train[target].astype(float), test[target].astype(float)

    # Two widgets both called "Linear Regression" would make the verdict
    # unreadable; a repeated title is told apart by its formula.
    title_counts: dict[str, int] = {}
    for s in specs:
        t = s.get("title") or s.get("model") or "model"
        title_counts[t] = title_counts.get(t, 0) + 1

    results = []
    for s in specs:
        wanted_s = _spec_preds(s)
        skipped = [p for p in wanted_s if p in skipped_cols]
        preds = [c for p in wanted_s if p not in skipped_cols for c in d.expanded.get(p, [])]
        name = s.get("title") or s.get("model") or "model"
        if title_counts.get(name, 0) > 1:
            name = f"{name} ({' + '.join(p for p in wanted_s if p not in skipped_cols) or 'no predictors'})"
        if not preds:
            results.append({"id": s.get("id"), "title": name, "model": s.get("model"), "score": None,
                            "note": "no usable predictor"})
            continue
        kind = s.get("model")
        if classification:
            est = (DecisionTreeClassifier(max_depth=int(s.get("max_depth") or 4), random_state=SPLIT_SEED)
                   if kind == "tree" else LogisticRegression(max_iter=1000))
            est.fit(train[preds], y_tr)
            proba = est.predict_proba(test[preds])[:, 1]
            score = float(roc_auc_score(y_te, proba))
            # The comparison's ROC overlay: every model's curve on the SAME
            # held-out rows, so the curves are comparable point for point.
            roc_curve = _roc(np.asarray(y_te), np.asarray(proba))
        else:
            est = (DecisionTreeRegressor(max_depth=int(s.get("max_depth") or 4), random_state=SPLIT_SEED)
                   if kind == "tree" else LinearRegression())
            est.fit(train[preds], y_tr)
            score = float(r2_score(y_te, est.predict(test[preds])))
        entry = {"id": s.get("id"), "title": name, "model": kind,
                 "predictors": [p for p in wanted_s if p not in skipped_cols], "score": _num(score)}
        if classification:
            entry["roc"] = roc_curve
        if skipped:
            entry["note"] = "left out of the shared refit: " + "; ".join(skipped_cols[p] for p in skipped)
        results.append(entry)

    scored = [r for r in results if r["score"] is not None]
    winner = max(scored, key=lambda r: r["score"]) if scored else None
    baseline = 0.5 if classification else 0.0
    return {
        "type": "model", "status": "ok", "model": "compare", "target": target,
        "metric": "AUC on held-out rows" if classification else "R² on held-out rows",
        "baseline": {"title": "Just guess", "score": baseline,
                     "note": "AUC 0.5 is a coin toss" if classification else "R² 0 is guessing the mean"},
        "models": results,
        "winner": winner["id"] if winner else None,
        "winner_beats_baseline": bool(winner and winner["score"] > baseline),
        "population": {"rows_total": int(len(df)), "rows_used": int(len(work)),
                       "rows_dropped": int(len(df) - len(work)), "dropped_by": {},
                       "train_rows": int(len(train)), "test_rows": int(len(test)),
                       **({"partition": {"column": part[2], "train_rows": int(len(train)),
                                         "validation_rows": int(len(test))}} if part is not None else {})},
        "rows": [{"name": r["title"], "value": r["score"]} for r in results],
    }


# ── Scoring with a saved model ───────────────────────────────────────────────

#: Saved models the widget router has cleared for THIS request, keyed by
#: "id:created_at". Shapers are pure (frame, config) functions and cannot read
#: the database; the router does the security checks, parks the unpickled
#: package here, and passes only the key in the config -- so the result cache
#: keys on the model's identity and version, never on its bytes.
_SCORING: "OrderedDict[str, tuple[Any, str]]"
from collections import OrderedDict  # noqa: E402
_SCORING = OrderedDict()
_SCORING_MAX = 16


def register_scoring_model(key: str, pkg: Any, name: str) -> None:
    _SCORING[key] = (pkg, name)
    _SCORING.move_to_end(key)
    while len(_SCORING) > _SCORING_MAX:
        _SCORING.popitem(last=False)


def shape_model_score(df: pd.DataFrame, config: dict) -> dict:
    """Apply a saved champion to the rows on the page, live.

    The page's filters narrow the frame before this runs, so "predicted churn
    by region" re-scores as the reader clicks. When the frame still carries the
    real outcome, the widget also grades the model on these rows beside the
    score it had at training -- the drift check a saved model otherwise never
    gets."""
    from .analysis.model_store import ModelStoreError, score_frame

    if not config.get("prediction_model_id"):
        return _incomplete(["Saved model"])
    entry = _SCORING.get(str(config.get("__model__")))
    if entry is None:
        return _refused("The saved model could not be loaded for this request. Reload the page.")
    pkg, name = entry
    try:
        res = score_frame(pkg, df)
    except ModelStoreError as e:
        return _refused(str(e), {"rows_total": int(len(df)), "rows_used": 0,
                                 "rows_dropped": int(len(df)), "dropped_by": {}})
    pred = pd.Series(res["predictions"], index=df.index[:len(res["predictions"])])
    by = config.get("dimension")
    by = by if isinstance(by, str) and by in df.columns else None
    value_format = "number"
    classification = pkg.task == "classification"
    event = None
    if classification:
        counts = pred.astype(str).value_counts()
        wanted = config.get("event_value")
        event = str(wanted) if wanted and str(wanted) in counts.index else (
            str(counts.index[-1]) if len(counts) else None)
    if by:
        groups = df.loc[pred.index, by].astype(str).where(df.loc[pred.index, by].notna(), "(blank)")
        if classification:
            agg = (pred.astype(str) == event).groupby(groups).mean().sort_values(ascending=False)
            measure = f"share predicted {event}"
            value_format = "percent"
        else:
            agg = pred.astype(float).groupby(groups).mean().sort_values(ascending=False)
            measure = f"average predicted {pkg.target}"
        rows = [{"name": k, "value": _num(v)} for k, v in agg.head(50).items()]
    elif classification:
        measure = "rows predicted"
        rows = [{"name": k, "value": int(v)} for k, v in pred.astype(str).value_counts().items()]
    else:
        measure = f"predicted {pkg.target}"
        qs = pred.astype(float).quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        rows = [{"name": f"{int(q * 100)}th percentile", "value": _num(v)} for q, v in qs.items()]

    fit = {"name": "score at training (" + (pkg.score_name or "score") + ")", "value": _num(pkg.score),
           "secondary": {}}
    if pkg.target in df.columns:
        actual = df.loc[pred.index, pkg.target]
        known = actual.notna()
        if known.sum() >= 5:
            if classification:
                now = float((actual[known].astype(str) == pred[known].astype(str)).mean())
                label = "accuracy on these rows"
            else:
                a = pd.to_numeric(actual[known], errors="coerce")
                ok = a.notna()
                p = pred[known][ok].astype(float)
                sst = float(((a[ok] - a[ok].mean()) ** 2).sum()) or float("nan")
                now = 1 - float(((a[ok] - p) ** 2).sum()) / sst
                label = "R² on these rows"
            fit["secondary"][label] = _num(now)
            fit["secondary"]["rows with a known outcome"] = int(known.sum())
    return {
        "type": "model", "status": "ok", "model": "score", "target": pkg.target,
        "saved": {"id": config.get("prediction_model_id"), "name": name,
                  "family": pkg.model_family, "task": pkg.task},
        "predictors": list(pkg.features), "event": event, "breakdown": by, "measure": measure,
        "value_format": value_format,
        "unseen_values": res.get("unseen_values") or {},
        "population": {"rows_total": int(len(df)), "rows_used": int(res["n_scored"]),
                       "rows_dropped": int(len(df) - res["n_scored"]), "dropped_by": {}},
        "fit": fit,
        "rows": rows,
    }


def _living(shaper):
    """Apply the widget's filters -- its own, and the cross-filters and page
    selections the canvas folds into them -- BEFORE fitting, so a model on the
    page re-fits as the reader clicks, the way every chart beside it re-draws.

    Every series shaper does this itself; a model that skipped it would sit
    unmoved while the rest of the page answered the click, and would say so
    nowhere. When the filters did narrow the rows, the population says by how
    much ("re-fitted on 12K of 2.3M")."""
    def run(df: pd.DataFrame, config: dict) -> dict:
        from .widget_data import _apply_filters
        filters = config.get("filters") or []
        before = len(df)
        if filters:
            df = _apply_filters(df, filters)
        out = shaper(df, config)
        pop = out.get("population")
        if filters and isinstance(pop, dict) and len(df) < before:
            pop["rows_before_filters"] = int(before)
        return out
    run.__name__ = shaper.__name__
    run.__doc__ = shaper.__doc__
    return run


MODEL_SHAPERS: dict[str, Any] = {
    "model_linear": _living(shape_model_linear),
    "model_logistic": _living(shape_model_logistic),
    "model_tree": _living(shape_model_tree),
    "model_cluster": _living(shape_model_cluster),
    "model_compare": _living(shape_model_compare),
    "model_score": _living(shape_model_score),
}
