import pandas as pd
from app.services.widget_data import get_widget_data


def _write_csv(tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def test_rls_filter_applied_before_widget_filter_and_calculated_columns(tmp_path):
    path = _write_csv(tmp_path, [
        {"region": "North", "sales": 100}, {"region": "North", "sales": 50},
        {"region": "South", "sales": 200},
    ])

    result = get_widget_data(
        path, {"dimension": "region", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
        rls_filter_expr="region == 'North'",
    )

    assert [r["name"] for r in result["rows"]] == ["North"]
    assert result["rows"][0]["value"] == 150


def test_no_rls_filter_means_unrestricted(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])

    result = get_widget_data(
        path, {"dimension": "region", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
    )

    assert {r["name"] for r in result["rows"]} == {"North", "South"}


def test_malformed_rls_filter_fails_closed(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])

    result = get_widget_data(
        path, {"dimension": "region", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
        rls_filter_expr="not a valid expr(((",
    )

    assert result["rows"] == []
