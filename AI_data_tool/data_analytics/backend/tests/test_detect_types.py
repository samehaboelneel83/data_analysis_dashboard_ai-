import pandas as pd

from app.services.analytics import detect_types


def test_detect_types_handles_numeric_and_categorical_columns():
    df = pd.DataFrame({"amount": [1, 2, 3], "region": ["east", "west", "east"]})

    result = detect_types(df)

    assert result["amount"] == "numeric"
    assert result["region"] == "categorical"


def test_detect_types_does_not_crash_on_unhashable_column_values():
    """A JSON/JSONB or array column from a real database (e.g. Postgres) can come
    back as a column of dicts/lists via psycopg2. nunique() can't hash those --
    this reproduces the 500 seen in production when creating a DirectQuery
    dataset from a table with a jsonb column, and asserts it degrades to a type
    label instead of crashing the whole schema probe."""
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "metadata": [{"a": 1}, {"b": 2}, {"a": 1}],
    })

    result = detect_types(df)

    assert result["id"] == "numeric"
    assert result["metadata"] in ("text", "categorical")


def test_detect_types_does_not_crash_on_unhashable_list_values():
    df = pd.DataFrame({"tags": [["a", "b"], ["c"], ["a", "b"]]})

    result = detect_types(df)

    assert result["tags"] in ("text", "categorical")
