import pandas as pd
from app.services.widget_data import shape_gantt, SHAPERS


def sample_df():
    return pd.DataFrame({
        "task":  ["Design", "Build", "Test"],
        "begin": ["2026-01-01", "2026-01-05", "2026-01-15"],
        "finish":["2026-01-05", "2026-01-15", "2026-01-20"],
        "owner": ["Alice", "Bob", "Alice"],
    })


def test_builds_one_row_per_task():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish"}}
    result = shape_gantt(sample_df(), config)
    assert result["type"] == "gantt"
    assert len(result["rows"]) == 3
    build = next(r for r in result["rows"] if r["name"] == "Build")
    assert build["start"] == "2026-01-05" and build["end"] == "2026-01-15"


def test_includes_group_when_role_set():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish", "group": "owner"}}
    result = shape_gantt(sample_df(), config)
    build = next(r for r in result["rows"] if r["name"] == "Build")
    assert build["group"] == "Bob"


def test_excludes_group_key_when_role_not_set():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish"}}
    result = shape_gantt(sample_df(), config)
    assert all("group" not in r for r in result["rows"])


def test_column_collision_does_not_crash():
    """House rule: category and start resolving to the same column must not crash."""
    config = {"roles": {"category": "begin", "start": "begin", "end": "finish"}}
    result = shape_gantt(sample_df(), config)
    assert result["type"] == "gantt"
    assert len(result["rows"]) == 3


def test_missing_required_role_returns_empty():
    config = {"roles": {"category": "task", "start": "begin"}}   # no end
    result = shape_gantt(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish"}, "limit": 2}
    result = shape_gantt(sample_df(), config)
    assert len(result["rows"]) == 2


def test_registered_in_shapers():
    assert SHAPERS["schedule"] is shape_gantt
