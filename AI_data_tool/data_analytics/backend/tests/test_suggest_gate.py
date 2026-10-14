"""One gate for every suggested chart (docs/suggestions/PLAN.md, phase 3)."""
import numpy as np
import pandas as pd

from app.services import suggest_gate as gate
from app.services.insights import generate_insights, suggest_widgets_from_findings


def series(*pairs):
    return {"type": "series", "rows": [{"name": n, "value": v} for n, v in pairs]}


def test_a_drawn_chart_that_says_nothing_is_named_for_what_is_wrong():
    bar = {"widget_type": "bar", "config": {"dimension": "city", "measure": "fee", "aggregation": "avg"}}
    assert gate.says_nothing(bar, series(("Cairo", 100), ("Giza", 100.5))) == "it shows the same value everywhere"
    assert gate.says_nothing(bar, series(("Cairo", 100))) == "it has only one group to show"
    assert gate.says_nothing(bar, series(("Cairo", 100), ("Giza", 160))) is None
    kpi = {"widget_type": "kpi", "config": {"measure": "change_pct", "aggregation": "avg"}}
    assert gate.says_nothing(kpi, series(("x", 0))) == "its number is exactly zero"


def test_a_line_over_time_is_judged_as_a_line():
    line = {"widget_type": "line", "config": {"dimension": "month", "measure": "n", "aggregation": "count"}}
    assert gate.says_nothing(line, series(("2024-01", 5), ("2024-02", 9)), {"month"}) is None


def test_a_check_that_cannot_read_a_result_never_blocks_the_chart():
    assert gate.says_nothing({"widget_type": "sankey", "config": {}}, {"nodes": [1, 2]}) is None
    assert gate.says_nothing({"widget_type": "bar", "config": {}}, None) is None


def test_the_builders_suggestions_pass_the_same_gate():
    """A measure that is the same in every group is not offered as a comparison."""
    rng = np.random.default_rng(2)
    n = 2000
    df = pd.DataFrame({
        "branch": rng.choice(["A", "B", "C", "D"], n),
        "flat_fee": np.full(n, 50.0),                              # one value everywhere
        "amount": rng.uniform(10, 500, n) * pd.Series(rng.choice([1, 3], n)).to_numpy(),
        "day": pd.date_range("2024-01-01", periods=n, freq="h"),
    })
    types = {"branch": "categorical", "flat_fee": "numeric", "amount": "numeric", "day": "datetime"}
    roles = dict(types)
    meta = {"flat_fee": {"number": "level"}}                      # averaged: the same in every branch
    found = generate_insights(df, types, meta)
    out = suggest_widgets_from_findings(found["findings"], roles, column_meta=meta, frame=df)
    assert out, "something is still suggested"
    for x in out:
        cfg = x["config"]
        assert not (cfg.get("measure") == "flat_fee" and cfg.get("dimension") == "branch"), x["title"]


def test_a_level_comparison_is_kept_when_someone_asked():
    """Average pay by gender, level: with an HR goal stated, that is the answer."""
    import asyncio
    import numpy as np
    import pandas as pd
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import suggest_for_dataset
    from app.services.analytics import detect_types
    from app.services.widget_data import get_widget_data_from_df
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"gender": rng.choice(["F", "M"], 2000), "salary": rng.normal(60000, 9000, 2000),
                       "dept": rng.choice(["Sales", "Ops", "IT"], 2000)})
    profile = build_profile(df, detect_types(df), {})

    class Designer:
        async def complete_json(self, messages, schema, **kw):
            return {"proposals": [{"title": "Pay", "rationale": "r", "widgets": [
                {"widget_type": "bar", "title": "Average salary by gender",
                 "config": {"dimension": "gender", "measure": "salary", "aggregation": "avg"}}]}]}

    async def probe(wt, cfg):
        return get_widget_data_from_df(df, cfg, wt)

    asked, _ = asyncio.run(suggest_for_dataset(profile, "I run HR and watch pay", 1, client=Designer(), probe=probe))
    assert [w["title"] for p in asked for w in p["widgets"]] == ["Average salary by gender"]
