"""A2: KMeans segmentation with automatic k selection.

scikit-learn is a heavy import (model-selection/BLAS setup adds real cold-start
cost) so it is imported LAZILY, inside `segment_dataframe`, never at module or
app-import time -- the same discipline as the telemetry/statsforecast lazy
imports elsewhere in this tier. `services/analysis/__init__.py` and this
module's own top level stay free of any sklearn import so importing
`app.main` can never pull it into `sys.modules`.

Algorithm (per the tier-5 plan): standardize the selected numeric columns,
then fit KMeans for k in 2..min(8, n_rows // 10), picking the k with the best
silhouette score. `random_state=42` everywhere stochastic so results are
reproducible across runs on the same data.
"""
from __future__ import annotations

import pandas as pd

from ..analysis_contract import AnalysisContract

RANDOM_STATE = 42
MAX_K = 8
MIN_ROWS = MAX_K * 10  # smallest n for which max_k (== MAX_K) is reachable
# silhouette_score is O(n^2) in the number of rows scored; on a large dataset
# evaluating it for up to 7 candidate k values would make the endpoint hang.
# Capping the sample it scores over keeps the endpoint responsive while still
# comparing candidates on a representative subset -- recorded in meta.params
# rather than silently deviating from the literal "score the whole set" spec.
SILHOUETTE_SAMPLE_CAP = 10_000
# The frame itself is capped before clustering even starts, at the same
# threshold sibling DirectQuery analyses use (direct_query.DEFAULT_ROW_CAP) --
# fitting up to 7 KMeans models plus a silhouette pass over an unbounded,
# million-row import frame would turn one request into ~70 full-frame fits.
# A fixed, seeded random sample keeps the endpoint bounded and reproducible;
# `meta.sampled`/`meta.sample_size` tell the caller it happened.
FRAME_SAMPLE_THRESHOLD = 10_000
# Per-row cluster labels are opt-in (`include_rows=True`) and capped even then
# -- nobody renders per-row labels for thousands of rows, and shipping them
# unconditionally on a large frame is pure wasted JSON. The per-cluster
# centroid summary in meta is what UIs actually read.
ROWS_RESPONSE_CAP = 1_000


class SegmentError(ValueError):
    """Degenerate input (too few usable numeric columns/rows). The router
    maps this to HTTP 400."""


def segment_dataframe(
    df: pd.DataFrame, columns: list[str] | None = None, include_rows: bool = False,
) -> AnalysisContract:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    total_rows = len(df)
    sampled = total_rows > FRAME_SAMPLE_THRESHOLD
    if sampled:
        df = df.sample(n=FRAME_SAMPLE_THRESHOLD, random_state=RANDOM_STATE)

    if columns:
        usable = [c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])
                  and not pd.api.types.is_bool_dtype(df[c])]
    else:
        usable = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
                  and not pd.api.types.is_bool_dtype(df[c])]

    if len(usable) < 2:
        raise SegmentError("Segmentation needs at least 2 usable numeric columns")

    sub = df[usable].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(sub)

    max_k = min(MAX_K, n // 10)
    if max_k < 2:
        raise SegmentError(
            f"Not enough complete rows to segment (need at least {MIN_ROWS // MAX_K * 2} "
            f"rows with values in every selected column, found {n})"
        )

    scaler = StandardScaler()
    X = scaler.fit_transform(sub.to_numpy())
    sil_sample = min(n, SILHOUETTE_SAMPLE_CAP)

    best_k = None
    best_score = -2.0
    best_labels = None
    best_model = None
    for k in range(2, max_k + 1):
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = model.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(X, labels, sample_size=sil_sample, random_state=RANDOM_STATE)
        if score > best_score:
            best_k, best_score, best_labels, best_model = k, score, labels, model

    if best_k is None:
        raise SegmentError("Could not find a stable clustering (every candidate k collapsed to one cluster)")

    rows: list[dict] = []
    rows_truncated = False
    if include_rows:
        pairs = list(zip(sub.index, best_labels))
        if len(pairs) > ROWS_RESPONSE_CAP:
            rows_truncated = True
            pairs = pairs[:ROWS_RESPONSE_CAP]
        rows = [{"row_index": int(idx), "cluster": int(label)} for idx, label in pairs]

    centroids = scaler.inverse_transform(best_model.cluster_centers_)
    centroid_rows = []
    for label in range(best_k):
        size = int((best_labels == label).sum())
        centroid = {"cluster": label, "size": size}
        for col, val in zip(usable, centroids[label]):
            centroid[col] = float(val)
        centroid_rows.append(centroid)

    columns_meta = [{"name": c, "dtype": "numeric"} for c in usable]
    meta = {
        "method": "kmeans",
        "params": {
            "k": best_k, "k_range": [2, max_k], "columns": usable,
            "random_state": RANDOM_STATE, "silhouette_sample_size": sil_sample,
        },
        "silhouette": float(best_score),
        "centroids": centroid_rows,
        "n_rows_used": n,
        "n_rows_total": total_rows,
        "sampled": sampled,
    }
    if sampled:
        meta["sample_size"] = len(df)
    if include_rows:
        meta["rows_truncated"] = rows_truncated

    warnings = []
    if sampled:
        warnings.append(f"Clustered a random sample of {len(df):,} of {total_rows:,} rows")
    if n < len(df):
        warnings.append(f"{len(df) - n} rows excluded (missing or non-numeric values in the selected columns)")

    return AnalysisContract(kind="segment", columns=columns_meta, rows=rows, meta=meta, warnings=warnings)
