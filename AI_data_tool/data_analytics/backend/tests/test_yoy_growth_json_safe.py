import json
import tempfile
import pandas as pd
from app.services.widget_data import get_widget_data


def test_yoy_growth_result_is_json_serializable_when_prior_period_is_zero():
    """Regression test: when YOY_GROWTH prior-period baseline is exactly zero,
    the result must be JSON-serializable (NaN, not inf). Starlette's JSONResponse
    uses json.dumps(..., allow_nan=False), which raises on inf/Infinity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = f"{tmp_dir}/d.csv"
        pd.DataFrame({
            "d": ["2023-01-15", "2024-01-10", "2024-02-10"],
            "sales": [0, 60, 90],
        }).to_csv(path, index=False)

        result = get_widget_data(
            path,
            {"dimension": "d", "measure": "growth", "aggregation": "sum"},
            widget_type="bar",
            calculated_columns=[{"name": "growth", "expression": "YOY_GROWTH(sales, d)"}],
        )
        # json.dumps with allow_nan=False mirrors Starlette's JSONResponse behavior --
        # this must not raise "Out of range float values are not JSON compliant: inf"
        json.dumps(result, allow_nan=False, default=str)
