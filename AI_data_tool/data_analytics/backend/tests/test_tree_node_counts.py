"""HR re-test 2026-10-01: every node of a classification tree said "0 of
each class" -- scikit-learn stores class shares, which were rounded to 0."""
import pandas as pd

from app.services.analysis.decision_tree import decision_tree


def test_node_distributions_are_row_counts():
    df = pd.DataFrame({
        "dept": ["Sales"] * 60 + ["Dev"] * 60,
        "title": ["Staff"] * 50 + ["Engineer"] * 10 + ["Engineer"] * 55 + ["Staff"] * 5,
    })
    r = decision_tree(df, "title", ["dept"], 2)
    root = r["detail"]["tree"] if "detail" in r else r["tree"]
    assert sum(root["distribution"].values()) == root["samples"]
    assert root["distribution"]["Staff"] > 0 and root["distribution"]["Engineer"] > 0
    for child in root["children"]:
        assert sum(child["distribution"].values()) == child["samples"]


def test_a_clustering_widget_refuses_an_identifier():
    from app.services.model_widgets import shape_model_cluster
    df = pd.DataFrame({"emp_no": range(100), "salary": [40000 + i * 10 for i in range(100)]})
    out = shape_model_cluster(df, {"measures": ["salary", "emp_no"]})
    assert out["status"] == "refused" and "emp_no" in out["reason"]


def test_a_comparison_of_listed_models_names_its_winner():
    from app.services.model_widgets import shape_model_compare
    import numpy as np
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"title": rng.choice(["A", "B", "C"], 400)})
    df["salary"] = df["title"].map({"A": 50000, "B": 70000, "C": 90000}) + rng.normal(0, 2000, 400)
    out = shape_model_compare(df, {"compare": [
        {"model": "linear", "response": "salary", "predictors": ["title"]},
        {"model": "tree", "response": "salary", "predictors": ["title"]}]})
    assert out["status"] == "ok"
    assert out["winner"] is not None
    assert out["winner"] in {m["id"] for m in out["models"]}
