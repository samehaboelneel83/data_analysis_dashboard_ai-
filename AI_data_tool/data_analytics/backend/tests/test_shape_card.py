import pandas as pd
from app.services.widget_data import shape_card


def test_shape_card_aggregates_each_measure_independently():
    df = pd.DataFrame({"revenue": [10, 20, 30], "cost": [5, 5, 10]})
    config = {"roles": {"measures": ["revenue", "cost"]}, "aggregation": "sum"}
    result = shape_card(df, config)
    assert result["rows"] == [{"name": "revenue", "value": 60}, {"name": "cost", "value": 20}]


def test_shape_card_respects_the_configured_aggregation():
    df = pd.DataFrame({"revenue": [10, 20, 30]})
    config = {"roles": {"measures": ["revenue"]}, "aggregation": "avg"}
    result = shape_card(df, config)
    assert result["rows"] == [{"name": "revenue", "value": 20}]


def test_a_panel_authored_card_renders(sample_df=None):
    """WidgetConfigPanel writes multi-value roles at TOP LEVEL under the role's own
    name -- `config[rf.role] = vals` -- while single roles go through configKeyFor.
    _LEGACY_ROLE_KEYS had no `measures` entry, so resolve_roles returned {} and every
    card configured through the UI rendered zero rows: configurable, and blank.

    The rest of this file exercises the `roles` form, which is why the suite stayed
    green while the widget was unusable. This asserts the form the PANEL actually
    emits."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    df = pd.DataFrame({"revenue": [10.0, 20.0], "units": [1, 2]})
    result = get_widget_data_from_df(df, {"measures": ["revenue", "units"], "aggregation": "sum"}, "card")

    assert [r["name"] for r in result["rows"]] == ["revenue", "units"]
    assert [r["value"] for r in result["rows"]] == [30.0, 3]


def test_a_panel_authored_parallel_coordinates_renders():
    """The other ROLE_SPECS entry with multi: true, pinned as a regression guard.

    It is NOT affected by the card defect -- it reads config["measures"] directly
    rather than through resolve_roles, so it renders with or without the legacy-key
    entry. Verified by removing that entry: this test still passes and only the card
    one fails. Recorded because the resemblance is misleading: the two widgets share a
    role name and a config shape but not a code path, and a future change that routed
    this one through resolve_roles would need the entry that card already relies on."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]})
    result = get_widget_data_from_df(df, {"measures": ["a", "b"]}, "parallel_coordinates")

    assert [ax["name"] for ax in result["axes"]] == ["a", "b"]
    assert len(result["lines"]) == 3
