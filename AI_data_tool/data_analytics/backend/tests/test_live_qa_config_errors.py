"""Settings that used to crash a widget now come back as an explained error.

`running` takes 'sum' or 'avg'. Live QA 2026-10-03: `running: true`, written
through the API, hit `.lower()` on a bool and returned a bare 500 on every
dataset. A bad value now comes back as an error tile that names the choices."""
import numpy as np
import pandas as pd
import pytest

from app.services.widget_data import get_widget_data_from_df


@pytest.fixture
def daily():
    rng = np.random.default_rng(0)
    return pd.DataFrame({"day": pd.date_range("2025-01-01", periods=120, freq="D"),
                         "score": rng.uniform(40, 95, 120)})


def line(df, running):
    return get_widget_data_from_df(df, {"measure": "score", "dimension": "day",
                                        "aggregation": "sum", "running": running,
                                        "dimension_granularity": "month"}, "line")


def test_running_sum_accumulates(daily):
    rows = line(daily, "sum")["rows"]
    assert rows[-1]["running_sum"] == pytest.approx(sum(r["value"] for r in rows), rel=1e-4)


@pytest.mark.parametrize("bad", [True, "total", 1])
def test_a_bad_value_is_an_error_not_a_crash(daily, bad):
    r = line(daily, bad)
    assert r["type"] == "error"
    assert "'sum' or 'avg'" in r["message"]


@pytest.mark.parametrize("agg,measure", [("count", None), ("countd", "st"), ("sum", "v")])
def test_a_crosstab_of_a_field_against_itself_is_explained(agg, measure):
    """Live QA 2026-10-03: the same field on Rows and Columns returned pandas'
    "The name st occurs multiple times, use a level number" to the reader."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"st": rng.choice(["a", "b"], 40), "v": rng.uniform(1, 9, 40)})
    cfg = {"dimension": "st", "dimension2": "st", "aggregation": agg}
    if measure:
        cfg["measure"] = measure
    r = get_widget_data_from_df(df, cfg, "crosstab")
    assert r["type"] == "error" and r["code"] == "same_rows_and_columns"
    assert "occurs multiple times" not in r["message"]


class TestRefusedWhenSaved:

    @pytest.mark.parametrize("config", [{"running": True}, {"running": "total"},
                                        {"split_by": ["a", "b"]}])
    def test_a_wrong_shape_is_refused(self, config):
        from app.services.widget_roles import InvalidWidget, validate_widget_payload
        with pytest.raises(InvalidWidget):
            validate_widget_payload(None, config)

    @pytest.mark.parametrize("config", [{"running": "sum"}, {"running": "AVG"},
                                        {"running": ""}, {"split_by": "region"}])
    def test_the_panel_shapes_save(self, config):
        from app.services.widget_roles import validate_widget_payload
        validate_widget_payload(None, config)

    def test_a_legacy_value_nobody_edits_does_not_block_an_edit(self):
        from app.services.widget_roles import validate_widget_payload
        validate_widget_payload(None, {"running": True, "title": "x"}, changed_keys={"title"})
