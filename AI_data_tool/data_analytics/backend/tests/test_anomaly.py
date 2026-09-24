"""A3: service-level tests for services/analysis/anomaly.py -- the iqr/iforest/ecod
detectors underneath the `outlier-details` endpoint (see test_outlier_details.py for
the endpoint-level tests). Mirrors test_segment.py's lazy-import pin pattern."""
import subprocess
import sys

import pandas as pd
import pytest

from app.services.analysis.anomaly import AnomalyError, detect


def _planted_outliers() -> pd.Series:
    # 30 quiet values clustered around 10, plus 3 planted spikes far outside.
    values = [10.0 + (i % 5) * 0.1 for i in range(30)] + [500.0, -500.0, 480.0]
    return pd.Series(values)


def test_iqr_detector_unchanged_formula():
    clean = _planted_outliers()
    mask, lo, hi = detect(clean, "iqr")
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    assert lo == pytest.approx(q1 - 1.5 * iqr)
    assert hi == pytest.approx(q3 + 1.5 * iqr)
    assert mask.sum() == 3  # exactly the 3 planted spikes


def test_iforest_flags_planted_outliers():
    clean = _planted_outliers()
    mask, _, _ = detect(clean, "iforest")
    flagged = set(clean.index[mask])
    planted = set(clean.index[-3:])
    # every planted spike is caught (iforest may also flag a couple of borderline
    # quiet points at contamination=0.1 on n=33, but must never miss the extremes)
    assert planted <= flagged


def test_ecod_runs_and_returns_a_boolean_mask():
    clean = _planted_outliers()
    mask, _, _ = detect(clean, "ecod")
    assert mask.dtype == bool
    assert mask.sum() >= 1


def test_unknown_detector_raises_anomaly_error():
    with pytest.raises(AnomalyError):
        detect(_planted_outliers(), "bogus")


def test_pyod_detector_needs_at_least_3_values():
    with pytest.raises(AnomalyError):
        detect(pd.Series([1.0, 2.0]), "iforest")


def test_lazy_import_pyod_not_pulled_in_at_app_import():
    """Mirrors test_segment.py's sklearn pin and test_shape_forecast.py's
    statsforecast pin: importing app.main must never pull pyod into sys.modules --
    it's imported lazily inside _pyod_mask on first use only."""
    code = (
        "import sys; "
        "assert 'pyod' not in sys.modules; "
        "from app.main import app; "
        "assert 'pyod' not in sys.modules, "
        "'app.main import triggered a pyod import'; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
