"""A3: PyOD anomaly detectors (iforest, ecod) alongside the pre-existing IQR fence
path used by the `outlier-details` endpoint (routers/datasets.py).

PyOD is imported LAZILY, inside `_pyod_mask`, the same discipline as segment.py's
sklearn import and widget_data.py's statsforecast import -- pyod's model classes pull
in a fair amount at import time and that cost must never land on the app-import path.

`detector` selects the mask over one column's numeric values:
  - "iqr"     (default): 1.5x-IQR fences. UNCHANGED from before this task -- same
              formula, same operator, same float math -- so existing callers see a
              byte-identical result when they don't pass `detector` at all.
  - "iforest": PyOD IsolationForest, seeded (random_state=RANDOM_STATE).
  - "ecod":    PyOD ECOD (empirical-CDF, distribution-free outlier scoring).
Both PyOD detectors use a fixed CONTAMINATION rate to turn their continuous score
into the same binary "is this row flagged" mask the IQR path already returns.
"""
from __future__ import annotations

import pandas as pd

RANDOM_STATE = 42
CONTAMINATION = 0.1
DETECTORS = ("iqr", "iforest", "ecod")


class AnomalyError(ValueError):
    """Bad detector name or too little data for it. The router maps this to HTTP 400."""


def _pyod_mask(clean: pd.Series, detector: str) -> pd.Series:
    if detector == "iforest":
        from pyod.models.iforest import IForest
        model = IForest(contamination=CONTAMINATION, random_state=RANDOM_STATE)
    elif detector == "ecod":
        from pyod.models.ecod import ECOD
        model = ECOD(contamination=CONTAMINATION)
    else:
        raise AnomalyError(f"Unknown detector: {detector}")

    X = clean.to_numpy(dtype=float).reshape(-1, 1)
    model.fit(X)
    labels = model.labels_  # PyOD convention: 1 == outlier, 0 == inlier, set at fit time
    return pd.Series(labels == 1, index=clean.index)


def detect(clean: pd.Series, detector: str = "iqr") -> tuple[pd.Series, float, float]:
    """Returns (mask aligned to `clean`'s index, fence_low, fence_high).

    The IQR fences are always computed (the box-plot the frontend renders needs them
    regardless of which detector chose the flagged rows), but only the `"iqr"`
    detector uses them to build the mask.
    """
    if detector not in DETECTORS:
        raise AnomalyError(f"Unknown detector '{detector}' (expected one of {DETECTORS})")

    q1, q3 = float(clean.quantile(0.25)), float(clean.quantile(0.75))
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr

    if detector == "iqr":
        mask = (clean < lo) | (clean > hi)
    else:
        if len(clean) < 3:
            raise AnomalyError(f"'{detector}' needs at least 3 numeric values")
        mask = _pyod_mask(clean, detector)

    return mask, lo, hi
