"""An analysis result as a tile on a page (docs/discovery/PLAN.md §X-2)."""
import numpy as np
import pandas as pd

from app.services.discovery import engine, evidence, profile as store
from app.services.model_widgets import TILE_ANALYSES
from app.services.widget_data import get_widget_data_from_df
from app.services.widget_roles import REQUIRED_ROLES
from tests.test_stage_board import rows as stage_rows
from tests.test_two_groups import trial


def tile(df, analysis, params, **extra):
    return get_widget_data_from_df(df, {"analysis": analysis, "params": params, **extra}, "analysis_result")


def test_the_tile_draws_the_analysis_own_result():
    assert REQUIRED_ROLES["analysis_result"] == ()
    out = tile(trial(n=12000), "compare_two_groups", {"group_col": "arm", "outcome": "done"})
    assert out["type"] == "analysis" and out["status"] == "ok" and out["kind"] == "two_groups"
    assert out["result"]["meta"]["verdict"] == "higher" and out["result"]["meta"]["sentence_i18n"]["key"] == "an.tg.higher"


def test_it_is_run_again_on_the_rows_the_page_shows():
    df = stage_rows()
    whole = tile(df, "stage_board", {"stage_col": "state", "start_date": "began", "done_date": "done_on", "due_date": "due"})
    part = tile(df, "stage_board", {"stage_col": "state", "start_date": "began", "done_date": "done_on", "due_date": "due"},
                filters=[{"column": "kind", "op": "eq", "value": "a"}])
    assert whole["result"]["meta"]["rows"] == 2000 and 0 < part["result"]["meta"]["rows"] < 2000


def test_what_it_cannot_draw_is_said_in_words_and_is_never_an_error():
    df = trial()
    assert tile(df, "", {})["status"] == "incomplete"
    slow = tile(df, "automated_prediction", {"target": "done"})
    assert slow["status"] == "refused" and "cannot sit on a page" in slow["reason"]
    three = df.assign(arm=np.where(np.arange(len(df)) % 3 == 0, "third", df["arm"]))
    refused = tile(three, "compare_two_groups", {"group_col": "arm", "outcome": "done"})
    assert refused["status"] == "refused" and "exactly two groups" in refused["reason"]
    assert tile(df, "compare_two_groups", {"group_col": "nope", "outcome": "done"})["status"] == "refused"
    assert tile(df, "compare_two_groups", {})["status"] == "refused"                     # parameters missing


def test_every_tile_analysis_is_in_the_catalogue():
    from app.services.analysis import registry
    assert all(registry.get(name) is not None for name in TILE_ANALYSES)


def test_the_card_says_how_it_sits_on_a_page_with_the_parameters_it_ended_with():
    """After the look at the rows picked the stage column, the tile carries that choice."""
    rng = np.random.default_rng(4)
    df = stage_rows().drop(columns=["kind"])
    df.insert(3, "zone", rng.choice(["north", "south", "east", "west"], len(df)))        # ahead of `state` in the table
    prof = store.compute(df)
    base = engine.tier0(prof, {})
    cards, _ = evidence.look(list(base["cards"]), df, {})
    engine._with_tiles(cards)
    card = next(c for c in cards if c["capability"] == "stage_board")
    assert card["action"]["kind"] == "run_analysis"                                       # still an analysis to run
    assert card["tile"] == {"widget_type": "analysis_result",
                            "config": {"analysis": "stage_board", "params": card["action"]["params"]}}
    assert card["tile"]["config"]["params"]["stage_col"] == "state"
    out = get_widget_data_from_df(df, card["tile"]["config"], "analysis_result")
    assert out["status"] == "ok" and out["result"]["meta"]["open"] == 120
    assert all("tile" not in c for c in cards if c["capability"] == "automated_prediction")
