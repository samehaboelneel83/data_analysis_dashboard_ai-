import pandas as pd
from app.services.widget_data import shape_waterfall, SHAPERS


def sample_df():
    return pd.DataFrame({
        "stage": ["Start", "Start", "Gains", "Losses", "Losses"],
        "delta": [100, 100, 50, -20, -10],
    })


def test_computes_running_total_in_order():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage", "measure": "delta"}})
    assert result["type"] == "waterfall"
    names = [b["name"] for b in result["bars"]]
    assert names == sorted(names)   # groupby-sorted category order
    gains = next(b for b in result["bars"] if b["name"] == "Gains")
    assert gains["delta"] == 50
    assert gains["end"] == gains["start"] + 50


def test_bars_chain_start_to_end():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage", "measure": "delta"}})
    bars = result["bars"]
    for i in range(1, len(bars)):
        assert bars[i]["start"] == bars[i - 1]["end"]


def test_grand_total_is_final_running_sum_not_row_count():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage", "measure": "delta"}})
    # Start: 100+100=200, Gains: +50=250, Losses: -20-10=-30 => 250-30=220
    assert result["grand_total"] == 220
    assert result["total"] == len(sample_df())   # total = row count, per every other shaper's contract
    assert result["grand_total"] != result["total"]


def test_missing_required_role_returns_empty():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage"}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["waterfall"] is shape_waterfall
