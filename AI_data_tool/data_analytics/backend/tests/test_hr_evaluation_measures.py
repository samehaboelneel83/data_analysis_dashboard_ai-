"""HR evaluation 2026-10-01, blocker 5: salary was summed everywhere.

"M has 60% of salary", "salary in 1999-12 ran 98% below its monthly average"
and "Manager trails the other titles on salary" were all head-counts in
disguise. A salary is averaged; an amount is summed; an id is counted.
"""
import numpy as np
import pandas as pd

from app.services.insights import generate_insights, is_code_like, suggest_widgets_from_findings
from app.services.semantic_guard import default_summary, is_identifier


def hr_frame(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    dept = rng.choice(["Development", "Sales", "Human Resources", "Finance"], n, p=[.5, .2, .15, .15])
    base = {"Development": 60000, "Sales": 89000, "Human Resources": 52000, "Finance": 78000}
    salary = np.array([base[d] for d in dept]) + rng.normal(0, 4000, n)
    title = rng.choice(["Senior Staff", "Engineer", "Manager"], n, p=[.6, .39, .01])
    return pd.DataFrame({"emp_no": np.arange(10001, 10001 + n), "dept_name": dept,
                         "title": title, "salary": salary.round(0)})


TYPES = {"emp_no": "numeric", "dept_name": "categorical", "title": "categorical", "salary": "numeric"}


def test_default_summary_by_name_and_meta():
    assert default_summary("salary") == "avg"
    assert default_summary("unit_price") == "avg"
    assert default_summary("amount") == "sum"
    assert default_summary("emp_no") == "countd"
    assert default_summary("salary", {"salary": {"aggregation": "sum"}}) == "sum"
    assert is_identifier("emp_no") and is_identifier("x", {"x": {"role": "identifier"}})


def test_salary_findings_are_about_averages_not_shares():
    out = generate_insights(hr_frame(), TYPES)
    titles = [f["title"] for f in out["findings"]]
    assert not any("% of salary" in t for t in titles), titles
    assert any("highest average salary" in t and t.startswith("Sales") for t in titles), titles
    # Manager is 1% of rows: it must not "trail" on a SUM of salary
    assert not any(t.startswith("Manager trails") for t in titles), titles


def test_value_glosses_only_apply_to_codes():
    assert is_code_like("d001") and is_code_like("M") and is_code_like("3")
    assert not is_code_like("Senior Staff") and not is_code_like("Marketing")
    out = generate_insights(hr_frame(), TYPES,
                            value_labels={"dept_name": {"Sales": "Sales-level engineering role"}})
    assert not any("engineering role" in f["title"] for f in out["findings"])


def test_suggestions_average_salary():
    out = generate_insights(hr_frame(), TYPES)
    sugs = suggest_widgets_from_findings(out["findings"], {"dept_name": "categorical", "title": "categorical",
                                                           "salary": "numeric", "emp_no": "numeric"})
    pay = [s for s in sugs if s["config"].get("measure") == "salary"]
    assert pay and all(s["config"]["aggregation"] == "avg" for s in pay)


def test_parallel_scan_gives_exactly_the_sequential_answer(monkeypatch):
    """5.21: detectors run side by side on a large frame; the result must not change."""
    import numpy as np
    import pandas as pd
    from app.services import insights
    rng = np.random.default_rng(7)
    n = 3000
    df = pd.DataFrame({
        "dept": rng.choice(["Dev", "Sales", "HR", "Ops"], n, p=[.55, .2, .15, .1]),
        "amount": rng.gamma(2, 500, n), "cost": rng.gamma(2, 300, n),
        "hired": pd.date_range("2024-01-01", periods=n, freq="6h").astype(str),
    })
    df.loc[::40, "cost"] = None
    types = {"dept": "categorical", "amount": "numeric", "cost": "numeric", "hired": "datetime"}
    monkeypatch.setattr(insights, "PARALLEL_SCAN_MIN_ROWS", 10**9)
    seq = insights.generate_insights(df, types)
    monkeypatch.setattr(insights, "PARALLEL_SCAN_MIN_ROWS", 0)
    par = insights.generate_insights(df, types)
    assert par == seq and seq["findings"]
