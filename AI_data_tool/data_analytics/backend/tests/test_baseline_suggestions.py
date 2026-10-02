"""HR re-test, item 3: suggestions must offer headcount by department and hires
per year even when no finding is about them."""
import pandas as pd

from app.services.insights import baseline_suggestions, suggest_widgets_from_findings


def _hr(n=400):
    depts = ["Development", "Production", "Sales", "Finance", "Research"]
    return pd.DataFrame({
        "emp_no": range(10001, 10001 + n),
        "gender": ["M" if i % 3 else "F" for i in range(n)],
        "dept_name": [depts[i % 5] for i in range(n)],
        "title": ["Engineer" if i % 2 else "Staff" for i in range(n)],
        "hire_date": pd.to_datetime([f"{1985 + i % 15}-03-01" for i in range(n)]),
        "to_date": pd.to_datetime(["2099-01-01"] * n),
        "salary": [40000 + (i * 37) % 60000 for i in range(n)],
    })


ROLES = {"emp_no": "numeric", "gender": "categorical", "dept_name": "categorical",
         "title": "categorical", "hire_date": "datetime", "to_date": "datetime",
         "salary": "numeric"}


def test_hr_basics_are_offered_and_counted_not_summed():
    got = {b["title"]: b["config"] for b in baseline_suggestions(_hr(), ROLES)}
    assert got["Headcount by dept name"] == {
        "dimension": "dept_name", "measure": "emp_no", "aggregation": "countd",
        "sort": "desc", "sort_by": "value"}
    assert got["Hires per year"]["dimension"] == "hire_date"
    assert got["Hires per year"]["dimension_granularity"] == "year"
    assert got["Average salary by gender"]["aggregation"] == "avg"
    assert got["Distribution of salary"] == {"measure": "salary", "bins": 20}
    # never a sum of the identifier
    assert all(c.get("measure") != "emp_no" or c.get("aggregation") == "countd"
               for c in got.values())


def test_end_dates_are_not_the_per_year_axis():
    df = _hr().drop(columns=["hire_date"])
    roles = {k: v for k, v in ROLES.items() if k != "hire_date"}
    assert all(b["config"].get("dimension") != "to_date"
               for b in baseline_suggestions(df, roles))


def test_basics_lead_and_findings_fill_the_rest():
    finding = {"kind": "standout", "title": "Sales has the highest average salary",
               "columns": ["dept_name", "salary"], "score": 50}
    out = suggest_widgets_from_findings([finding], ROLES, frame=_hr())
    assert out[0]["title"] == "Headcount by dept name"
    assert any(o["title"] == "Sales has the highest average salary" for o in out)


def test_without_a_frame_nothing_changes():
    out = suggest_widgets_from_findings([], ROLES)
    assert out == []


def test_ineligible_columns_are_respected():
    out = baseline_suggestions(_hr(), ROLES, ineligible={"salary"})
    assert all(b["config"].get("measure") != "salary" for b in out)


def test_a_model_proposal_never_sums_a_salary_or_an_id():
    """HR re-test: the automation's model proposal had a SUM-of-salary KPI."""
    from app.services.suggest_dataset_dashboard import polish_widget
    w = polish_widget({"widget_type": "kpi", "title": "Total Salary",
                       "config": {"measure": "salary", "aggregation": "sum"}}, {})
    assert w["config"]["aggregation"] == "avg" and w["title"] == "Average Salary"
    w = polish_widget({"widget_type": "kpi", "title": "Employees",
                       "config": {"measure": "emp_no", "aggregation": "sum"}}, {})
    assert w["config"]["aggregation"] == "countd"
    w = polish_widget({"widget_type": "kpi", "title": "Revenue",
                       "config": {"measure": "revenue", "aggregation": "sum"}}, {})
    assert w["config"]["aggregation"] == "sum"
