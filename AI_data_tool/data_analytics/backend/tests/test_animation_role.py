"""Phase 6.3: animation role -- frames in the field's own order, one shared axis."""
import pandas as pd

from app.services.widget_data import ANIMATION_MAX_FRAMES, get_widget_data_from_df


def _df():
    rows = []
    for m, k in (("2026-03-05", 3), ("2026-01-05", 1), ("2026-02-05", 2)):
        for region in ("N", "S"):
            rows.append({"d": m, "region": region, "sales": 10.0 * k * (2 if region == "N" else 1)})
    return pd.DataFrame(rows)


def test_frames_are_chronological_with_a_shared_domain():
    res = get_widget_data_from_df(_df(), {"dimension": "region", "measure": "sales", "animate_by": "d"}, "bar")
    assert res["type"] == "animated"
    assert [f["label"] for f in res["frames"]] == ["2026-01-05", "2026-02-05", "2026-03-05"]
    assert res["domain"] == [0.0, 60.0]
    first = {r["name"]: r["value"] for r in res["frames"][0]["result"]["rows"]}
    assert first == {"N": 20.0, "S": 10.0}


def test_granularity_buckets_frames():
    df = _df()
    df.loc[len(df)] = {"d": "2026-01-20", "region": "N", "sales": 5.0}
    res = get_widget_data_from_df(df, {"dimension": "region", "measure": "sales", "animate_by": "d",
                                       "animate_granularity": "month"}, "bar")
    assert [f["label"] for f in res["frames"]] == ["2026-01", "2026-02", "2026-03"]
    jan = {r["name"]: r["value"] for r in res["frames"][0]["result"]["rows"]}
    assert jan["N"] == 25.0


def test_numeric_frames_sort_numerically_and_the_cap_keeps_the_latest():
    df = pd.DataFrame({"yr": list(range(1, 81)), "g": "a", "v": 1.0})
    res = get_widget_data_from_df(df, {"dimension": "g", "measure": "v", "animate_by": "yr"}, "bar")
    assert len(res["frames"]) == ANIMATION_MAX_FRAMES
    assert res["frames"][0]["label"] == "21" and res["frames"][-1]["label"] == "80"
    assert "last 60 of 80" in res["animation_truncation"]["text"]


def test_missing_field_degrades_and_other_types_ignore_it():
    res = get_widget_data_from_df(_df(), {"dimension": "region", "measure": "sales", "animate_by": "gone"}, "bar")
    assert res["type"] != "animated" and "gone" in res["animation_note"]
    assert get_widget_data_from_df(_df(), {"dimension": "region", "measure": "sales",
                                           "animate_by": "d"}, "table")["type"] != "animated"
