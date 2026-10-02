"""Bugs the HR analyst panel found by drawing 80 proposed visuals on the live
workforce data (2026-10-02). Each one gave a confident wrong number or a
refusal where the chart was perfectly drawable."""
import numpy as np
import pandas as pd

from app.services.model_widgets import MODEL_SHAPERS
from app.services.widget_data import SHAPERS


def _hr(n=600, seed=0):
    rng = np.random.default_rng(seed)
    dept = rng.choice(["Sales", "Development", "Finance"], n)
    title = np.where(dept == "Sales", "Senior Staff", rng.choice(["Engineer", "Senior Engineer"], n))
    years = rng.uniform(0, 15, n)
    return pd.DataFrame({
        "emp_no": np.arange(10001, 10001 + n), "dept_name": dept, "title": title,
        "gender": rng.choice(["M", "F"], n),
        "salary": 50000 + years * 2000 + rng.normal(0, 3000, n),
        "hire_date": pd.Timestamp("2000-01-01") - pd.to_timedelta(years * 365.25, "D"),
    })


def test_sankey_counts_people_instead_of_summing_their_ids():
    df = _hr()
    r = SHAPERS["sankey"](df, {"dimension": "dept_name", "dimension2": "title",
                              "measure": "emp_no", "aggregation": "countd"})
    assert sum(link["value"] for link in r["links"]) == len(df)


def test_org_chart_counts_people_instead_of_summing_their_ids():
    df = _hr()
    r = SHAPERS["org"](df, {"widget_type": "org", "levels": ["dept_name", "title"],
                            "measure": "emp_no", "aggregation": "countd"})
    assert r["root"]["value"] == len(df)


def test_sunburst_accepts_a_distinct_count_of_a_unique_id():
    df = _hr()
    r = SHAPERS["sunburst"](df, {"widget_type": "sunburst", "levels": ["dept_name", "title"],
                                 "measure": "emp_no", "aggregation": "countd"})
    assert r["root"]["value"] == len(df) and r["additive"] is True


def test_sunburst_still_refuses_a_distinct_count_that_repeats():
    import pytest
    from app.services.widget_data import HierarchyError
    df = _hr()
    with pytest.raises(HierarchyError):
        SHAPERS["sunburst"](df, {"widget_type": "sunburst", "levels": ["dept_name"],
                                 "measure": "gender", "aggregation": "countd"})


def test_box_plot_and_waterfall_honour_the_date_grain():
    df = _hr()
    b = SHAPERS["box_plot"](df, {"dimension": "hire_date", "dimension_granularity": "year",
                                 "measure": "salary", "limit": 50})
    assert len(b["rows"]) == df.hire_date.dt.year.nunique()
    w = SHAPERS["waterfall"](df, {"dimension": "hire_date", "dimension_granularity": "year",
                                  "measure": "emp_no", "aggregation": "countd", "limit": 50})
    assert w["grand_total"] == len(df) and len(w["bars"]) == df.hire_date.dt.year.nunique()


def test_custom_graph_on_a_time_axis_runs_in_time_order():
    df = _hr()
    r = SHAPERS["custom_graph"](df, {"dimension": "hire_date", "dimension_granularity": "year",
                                     "layers": [{"mark": "bar", "measure": "emp_no", "aggregation": "countd"}]})
    names = [row["name"] for row in r["rows"]]
    assert names == sorted(names)


def test_a_date_predictor_is_years_of_service_not_5000_text_levels():
    df = _hr()
    r = MODEL_SHAPERS["model_linear"](df, {"measure": "salary", "predictors": ["title", "hire_date"]})
    assert r["status"] == "ok" and r["derived"] == {"hire_date": "years_before_latest"}
    coef = next(c for c in r["result"]["detail"]["coefficients"] if c["term"] == "hire_date")
    assert 1500 < coef["coefficient"] < 2500                  # ~2,000 per year of service
    assert r["population"]["rows_dropped"] == 0 and not r["population"]["dropped_by"]
    lg = MODEL_SHAPERS["model_logistic"](df, {"response": "gender", "event_value": "F",
                                              "predictors": ["salary", "hire_date"]})
    assert lg["status"] == "ok"


def test_clustering_accepts_a_date_as_tenure():
    df = _hr()
    r = MODEL_SHAPERS["model_cluster"](df, {"measures": ["salary", "hire_date"]})
    assert r["status"] == "ok"


def test_live_decomposition_keeps_its_node_value_as_total(tmp_path):
    """On live data the total was overwritten with the row count."""
    import sqlite3
    from types import SimpleNamespace
    from app.services.direct_query import run_direct_query
    db = tmp_path / "hr.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE emp (dept TEXT, salary REAL)")
    con.executemany("INSERT INTO emp VALUES (?, ?)", [("A", 10), ("A", 20), ("B", 60)])
    con.commit(); con.close()
    ds = SimpleNamespace(source_table="emp", source_query=None,
                         columns=[SimpleNamespace(name="dept"), SimpleNamespace(name="salary")])
    r = run_direct_query({"type": "sqlite", "filepath": str(db)}, ds,
                         {"measure": "salary", "aggregation": "avg", "split_by": "dept"},
                         widget_type="decomposition")
    assert r["total"] == 30 and r["rows_scanned"] == 3


def test_a_tiny_coefficient_is_not_rounded_to_zero_before_predicting():
    """Salary per dollar moves the odds by ~0.00005: four decimals made it 0
    and the 0.5 threshold then classified everyone as 'not Senior Staff'."""
    rng = np.random.default_rng(3)
    n = 4000
    salary = rng.normal(70000, 15000, n)
    p = 1 / (1 + np.exp(-(salary - 70000) * 0.0002))
    df = pd.DataFrame({"salary": salary, "senior": np.where(rng.random(n) < p, "yes", "no")})
    r = MODEL_SHAPERS["model_logistic"](df, {"response": "senior", "event_value": "yes",
                                             "predictors": ["salary"]})
    coef = next(c for c in r["result"]["detail"]["coefficients"] if c["term"] == "salary")
    assert coef["coefficient"] != 0
    acc = r["fit"]["secondary"]["accuracy at 0.5"]
    base = r["fit"]["secondary"]["accuracy of always guessing the commoner outcome"]
    assert acc > base + 0.1
