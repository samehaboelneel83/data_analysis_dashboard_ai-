import pandas as pd
from app.services.widget_data import shape_correlation_matrix, SHAPERS


def sample_df():
    return pd.DataFrame({
        "a": [1, 2, 3, 4, 5],
        "b": [2, 4, 6, 8, 10],     # perfectly correlated with a
        "c": [5, 4, 3, 2, 1],      # perfectly anti-correlated with a
        "unrelated": ["x", "y", "z", "x", "y"],
    })


def test_matrix_is_symmetric_with_unit_diagonal():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "b", "c"]})
    assert result["type"] == "matrix"
    assert result["measures"] == ["a", "b", "c"]
    m = result["matrix"]
    assert m[0][0] == 1.0 and m[1][1] == 1.0 and m[2][2] == 1.0
    assert abs(m[0][1] - m[1][0]) < 1e-9


def test_perfect_positive_and_negative_correlation():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "b", "c"]})
    m = result["matrix"]
    assert abs(m[0][1] - 1.0) < 1e-9    # a vs b: perfectly correlated
    assert abs(m[0][2] - (-1.0)) < 1e-9  # a vs c: perfectly anti-correlated


def test_fewer_than_two_measures_returns_empty():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a"]})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_missing_measures_key_returns_empty():
    result = shape_correlation_matrix(sample_df(), {})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_nonexistent_column_in_measures_is_dropped_not_crashed():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "b", "does_not_exist"]})
    assert result["measures"] == ["a", "b"]


def test_duplicate_measure_names_deduped():
    """House rule: repeated column selection must never crash a pandas column operation.

    This test proves the dedup guard is load-bearing by verifying:
    1. The measures list is correctly deduped
    2. The matrix has the correct 2x2 shape (not 3x3 from undeduped ["a","a","b"])
    3. The matrix values are correct correlations for the deduped measures
    """
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "a", "b"]})

    # Verify deduped measures list
    assert result["measures"] == ["a", "b"]

    # Verify matrix shape is 2x2, not 3x3
    matrix = result["matrix"]
    assert len(matrix) == 2, f"Expected 2x2 matrix, got {len(matrix)}x?"
    assert len(matrix[0]) == 2, f"Expected 2x2 matrix, got ?x{len(matrix[0])}"

    # Verify matrix values are correct correlations for deduped set
    # a vs a: correlation is 1.0
    assert abs(matrix[0][0] - 1.0) < 1e-9
    # b vs b: correlation is 1.0
    assert abs(matrix[1][1] - 1.0) < 1e-9
    # a vs b: perfectly correlated (b = 2*a)
    assert abs(matrix[0][1] - 1.0) < 1e-9
    # b vs a: perfectly correlated (symmetric)
    assert abs(matrix[1][0] - 1.0) < 1e-9


def test_registered_in_shapers():
    assert SHAPERS["correlation_matrix"] is shape_correlation_matrix
