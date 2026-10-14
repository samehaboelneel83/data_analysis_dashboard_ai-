"""The suggestions panel offers, after the ideas the data argues for, one idea
for each FURTHER widget type the data has the shape for
(suggest_variety.catalogue_suggestions) -- each with the reason it fits, each
drawn before it is offered, and none for a shape the data does not have."""
import numpy as np
import pandas as pd

from app.services import suggest_variety as sv
from app.services.insights import effective_roles, generate_insights, suggest_widgets_from_findings

N = 3000
ROLES = {"when": "datetime", "grp": "categorical", "kind": "categorical", "item": "categorical",
         "reached": "numeric", "expected": "numeric", "share": "numeric", "score": "numeric", "weight": "numeric"}
META = {"share": {"default_summary": "avg"}, "score": {"default_summary": "avg"}}


def table():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"when": pd.date_range("2023-01-01", periods=N, freq="8h"),
                       "grp": rng.choice(list("abcdefgh"), N), "kind": rng.choice(["x", "y", "z"], N),
                       "item": rng.choice([f"i{k}" for k in range(30)], N), "reached": rng.uniform(10, 100, N)})
    df["expected"] = df["reached"] * rng.uniform(.8, 1.2, N)
    df["share"] = rng.uniform(0, 1, N)
    df["score"] = rng.normal(50, 10, N)
    df["weight"] = rng.uniform(1, 5, N)
    return df


def ideas(df, roles=ROLES, meta=META):
    return sv.catalogue_suggestions(sv._Profile(df, roles, meta, None))


def test_every_idea_draws_names_real_columns_and_says_why_it_fits():
    df = table()
    got = ideas(df)
    kinds = {(s["widget_type"], s["config"].get("gauge_shape")) for s in got}
    assert {("gauge", "bullet"), ("gauge", "progress"), ("card", None), ("dot_plot", None), ("dual_axis_bar", None),
            ("butterfly", None), ("area", None), ("step", None), ("dual_axis_time_series", None),
            ("comparative_time_series", None), ("ribbon", None), ("waterfall", None), ("histogram", None),
            ("numeric_series", None), ("correlation_matrix", None), ("parallel_coordinates", None),
            ("crosstab", None), ("sankey", None), ("small_multiples", None), ("list", None),
            ("word_cloud", None)} <= kinds
    for s in got:
        assert sv.draws(s["widget_type"], s["config"], df), s["widget_type"]
        assert s["kind"] == "catalogue" and len(s["reason"]) > 20 and s["title"]
        named = [v for k, v in s["config"].items() if k in ("dimension", "dimension2", "measure", "measure2", "start",
                                                            "target", "facet_by", "color")]
        named += list(s["config"].get("measures") or [])
        assert named and all(c in df.columns for c in named), s


def test_a_shape_the_data_does_not_have_is_not_offered():
    df = table()
    # No date: nothing over time. No second number of the same size: nothing "against".
    plain = df[["grp", "kind", "reached", "score"]]
    roles = {k: v for k, v in ROLES.items() if k in plain.columns}
    types = {s["widget_type"] for s in ideas(plain, roles)}
    assert not types & {"area", "step", "ribbon", "dual_axis_time_series", "comparative_time_series", "butterfly", "card"}
    assert not any(s["config"].get("gauge_shape") == "bullet" for s in ideas(plain, roles))
    # A date covering a few weeks is not a history.
    short = df.assign(when=pd.date_range("2024-01-01", periods=N, freq="10min"))
    assert not {s["widget_type"] for s in ideas(short)} & {"area", "step", "ribbon"}
    # Two numbers of very different size are not read against each other.
    far = df.assign(expected=df["expected"] * 50)
    assert not any(s["config"].get("gauge_shape") == "bullet" for s in ideas(far))
    # A number that is not a share is not shown as progress.
    assert not any(s["config"].get("gauge_shape") == "progress"
                   for s in ideas(df.drop(columns=["share"]), {k: v for k, v in ROLES.items() if k != "share"}))


def test_the_panel_adds_them_after_its_own_ideas_one_of_each_type_and_only_when_asked():
    df = table()
    from app.services.ingest import detect_types
    from app.services import column_classes
    types = detect_types(df)
    meta, _ = column_classes.classified(df, META)
    found = generate_insights(df, types, meta)["findings"]
    roles = effective_roles(types, meta)
    base = suggest_widgets_from_findings(found, roles, None, column_meta=meta, frame=df)
    more = suggest_widgets_from_findings(found, roles, None, column_meta=meta, frame=df, catalogue=12)
    assert not any(s.get("kind") == "catalogue" for s in base)
    extra = [s for s in more if s.get("kind") == "catalogue"]
    # The ideas the data argues for come first and are unchanged; the further types follow.
    assert [s["title"] for s in more[:len(base)]] == [s["title"] for s in base] and 5 <= len(extra) <= 12
    had = {sv._type_key(s) for s in base}
    keys = [sv._type_key(s) + str(s["config"].get("gauge_shape") or "") for s in extra]
    assert len(set(keys)) == len(keys) and not {sv._type_key(s) for s in extra} & had
    assert len({s["widget_type"] for s in more}) >= len({s["widget_type"] for s in base}) + 5
