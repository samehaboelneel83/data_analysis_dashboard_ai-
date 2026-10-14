"""Association Rules as a model widget (added 2026-10-01): which values travel
together, live on the canvas, re-mined under the page's filters."""
import numpy as np
import pandas as pd

from app.services.analysis.patterns import association_rules
from app.services.model_widgets import MODEL_SHAPERS
from app.services.widget_roles import REQUIRED_ROLES

shape = MODEL_SHAPERS["model_rules"]


def _hr(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    dept = rng.choice(["Sales", "Development", "Finance"], n)
    title = np.where(dept == "Sales", rng.choice(["Staff", "Senior Staff"], n, p=[.8, .2]),
                     rng.choice(["Engineer", "Staff", "Senior Engineer"], n))
    salary = np.where(title == "Senior Staff", 90000, 50000) + rng.normal(0, 5000, n)
    return pd.DataFrame({
        "emp_no": range(10001, 10001 + n), "dept_name": dept, "title": title,
        "gender": rng.choice(["M", "F"], n), "salary": salary,
        "hire_date": pd.to_datetime("1990-01-01") + pd.to_timedelta(rng.integers(0, 3000, n), "D"),
    })


def test_registered_with_no_required_roles():
    assert REQUIRED_ROLES["model_rules"] == ()


def test_blank_columns_mine_every_text_column_and_skip_ids_and_numbers():
    r = shape(_hr(), {})
    assert r["status"] == "ok" and r["model"] == "rules"
    assert set(r["variables"]) == {"dept_name", "title", "gender"}
    top = r["rules"][0]
    assert (top["if"], top["then"]) == ("dept_name=Sales", "title=Senior Staff")
    assert r["fit"]["value"] == top["lift"]
    # every rule is reported with the base rate its confidence is read against
    assert all({"lift", "confidence", "base_rate", "support_rows"} <= set(x) for x in r["rules"])


def test_matches_a_count_by_hand():
    df = _hr()
    r = next(x for x in shape(df, {})["rules"]
             if x["if"] == "dept_name=Sales" and x["then"] == "title=Senior Staff")
    sales = df.dept_name == "Sales"
    joint = int((sales & (df.title == "Senior Staff")).sum())
    assert r["support_rows"] == joint
    assert abs(r["confidence"] - joint / sales.sum()) < 1e-3
    assert abs(r["base_rate"] - (df.title == "Senior Staff").mean()) < 1e-3


def test_focus_keeps_only_conclusions_about_that_column():
    r = shape(_hr(), {"response": "title"})
    assert r["rules"] and r["focus"] == "title"
    assert all(all(c == "title" for c, _ in x["then_items"]) for x in r["rules"])


def test_a_named_number_is_banded_and_said_so():
    r = shape(_hr(), {"predictors": ["dept_name", "salary"], "response": "title"})
    assert r["banded"] == {"salary": "4 equal-count bands"}
    assert any(c == "salary" for x in r["rules"] for c, _ in x["if_items"])


def test_identifier_is_refused_by_name():
    r = shape(_hr(), {"predictors": ["emp_no", "title"]})
    assert r["status"] == "refused" and "emp_no is an identifier" in r["reason"]


def test_too_few_columns_is_a_reason_not_an_error():
    r = shape(_hr()[["title"]], {})
    assert r["status"] == "refused" and "two categorical columns" in r["reason"]


def test_filters_narrow_the_rows_it_mines():
    r = shape(_hr(), {"filters": [{"column": "gender", "op": "eq", "value": "F"}]})
    assert r["population"]["rows_before_filters"] == 3000
    assert r["population"]["rows_used"] < 3000


def test_variants_of_a_certain_rule_do_not_lead():
    """'Senior Staff -> Sales' holds in every row, so it is schema and is
    suppressed; its copy with gender attached topped the HR list until the
    certain rules took their variants with them."""
    out = association_rules(_hr()[["dept_name", "title", "gender"]]).to_dict()["rows"]
    assert not any(x["if"] == "title=Senior Staff" and x["then"].startswith("dept_name=Sales")
                   for x in out)


#: The real HR mix (dept, gender, title, employees), 240,124 rows -- gender is
#: independent of the other two, so no rule should carry it.
HR_MIX = """Customer_Service|F|Assistant_Engineer|26;Customer_Service|F|Engineer|263;Customer_Service|F|Senior_Engineer|706;Customer_Service|F|Senior_Staff|4516;Customer_Service|F|Staff|1405;Customer_Service|F|Technique_Leader|91;Customer_Service|M|Assistant_Engineer|42;Customer_Service|M|Engineer|364;Customer_Service|M|Manager|1;Customer_Service|M|Senior_Engineer|1084;Customer_Service|M|Senior_Staff|6752;Customer_Service|M|Staff|2169;Customer_Service|M|Technique_Leader|150;Development|F|Assistant_Engineer|668;Development|F|Engineer|5592;Development|F|Manager|1;Development|F|Senior_Engineer|15499;Development|F|Senior_Staff|427;Development|F|Staff|135;Development|F|Technique_Leader|2211;Development|M|Assistant_Engineer|984;Development|M|Engineer|8448;Development|M|Senior_Engineer|23317;Development|M|Senior_Staff|658;Development|M|Staff|180;Development|M|Technique_Leader|3266;Finance|F|Manager|1;Finance|F|Senior_Staff|3860;Finance|F|Staff|1153;Finance|M|Senior_Staff|5685;Finance|M|Staff|1738 Human_Resources|F|Manager|1;Human_Resources|F|Senior_Staff|3940;Human_Resources|F|Staff|1206;Human_Resources|M|Senior_Staff|5884;Human_Resources|M|Staff|1867;Marketing|F|Senior_Staff|4389;Marketing|F|Staff|1475;Marketing|M|Manager|1;Marketing|M|Senior_Staff|6901;Marketing|M|Staff|2076;Production|F|Assistant_Engineer|547;Production|F|Engineer|4862;Production|F|Senior_Engineer|13451;Production|F|Senior_Staff|473;Production|F|Staff|145;Production|F|Technique_Leader|1915;Production|M|Assistant_Engineer|855;Production|M|Engineer|7219;Production|M|Manager|1;Production|M|Senior_Engineer|20174;Production|M|Senior_Staff|650;Production|M|Staff|204;Production|M|Technique_Leader|2808;Quality_Management|F|Assistant_Engineer|167;Quality_Management|F|Engineer|1345;Quality_Management|F|Senior_Engineer|3850;Quality_Management|F|Technique_Leader|510;Quality_Management|M|Assistant_Engineer|222;Quality_Management|M|Engineer|2060;Quality_Management|M|Manager|1 Quality_Management|M|Senior_Engineer|5608;Quality_Management|M|Technique_Leader|783;Research|F|Assistant_Engineer|32;Research|F|Engineer|350;Research|F|Manager|1;Research|F|Senior_Engineer|900;Research|F|Senior_Staff|3627;Research|F|Staff|1132;Research|F|Technique_Leader|139;Research|M|Assistant_Engineer|45;Research|M|Engineer|480;Research|M|Senior_Engineer|1350;Research|M|Senior_Staff|5465;Research|M|Staff|1738;Research|M|Technique_Leader|182;Sales|F|Senior_Staff|11560;Sales|F|Staff|3439;Sales|M|Manager|1;Sales|M|Senior_Staff|17237;Sales|M|Staff|5464"""


def test_a_samples_noise_does_not_promote_a_decorated_copy():
    """HR re-test 2026-10-01: on the 50,000-row sample, "Marketing -> F,
    Staff" (lift 2.44) led over "Marketing -> Staff" (2.2 in the sample; 2.32
    vs 2.35 in full) -- gender added nothing but cleared the margin by noise."""
    rows = []
    for part in HR_MIX.replace(" ", ";").split(";"):
        d, g, t, n = part.split("|")
        rows += [(d.replace("_", " "), g, t.replace("_", " "))] * int(n)
    df = pd.DataFrame(rows, columns=["dept_name", "gender", "title"])
    for frame in (df, df.sample(frac=1, random_state=7)):
        out = association_rules(frame).to_dict()["rows"]
        assert out and not any("gender" in r["if"] + r["then"] for r in out)
        assert out[0]["if"] in ("dept_name=Marketing", "title=Staff")


def test_the_same_rows_in_any_order_give_the_same_rules(monkeypatch):
    """A live source returns rows in no fixed order; the sample must not care."""
    from app.services.analysis import patterns
    monkeypatch.setattr(patterns, "FRAME_SAMPLE_THRESHOLD", 1000)
    df = _hr()[["dept_name", "title", "gender"]]
    a = association_rules(df).to_dict()["rows"]
    b = association_rules(df.sample(frac=1, random_state=3).reset_index(drop=True)).to_dict()["rows"]
    assert a == b and a
