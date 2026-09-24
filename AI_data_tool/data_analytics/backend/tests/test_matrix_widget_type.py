import pandas as pd
from app.services.widget_data import get_widget_data_from_df


def test_matrix_widget_type_uses_the_same_shaper_as_crosstab():
    df = pd.DataFrame({"region": ["East", "East", "West"], "product": ["A", "B", "A"], "sales": [10, 20, 30]})
    config = {"roles": {"category": "region", "category2": "product", "measure": "sales"}, "aggregation": "sum"}
    crosstab_result = get_widget_data_from_df(df, config, "crosstab")
    matrix_result = get_widget_data_from_df(df, config, "matrix")
    assert matrix_result == crosstab_result
