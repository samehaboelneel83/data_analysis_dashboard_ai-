"""Persona test Phase 4.4 -- the tuning rule, kept by a test.

No text the app sends to a model or shows a person may name a table, a column
or a business of the databases the persona test used: a fix tuned to one
database must be a rule about data, not a mention of it. Checked here: every
string constant in the backend (not comments or docstrings, which explain the
history) and the English and Arabic interface text. The words are the
distinctive names from docs/persona-test/ground-truth/; plain words any
business uses ("orders", "customers") are not on the list.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

NAMES = """
ai_officer ai_officer_weigths ai_srv ai_outstanding ai_dicipline ai_eval_report ai_eval_rep_items
eval_rep_sub_item eval_rep_type mil_no sh2on_zobat
cars_hatla2ee hatla2ee realestate_aqarmap aqarmap realestate_olx realestate_propertyfinder propertyfinder
egx30_index egx30 egx COMI
conflict_events humanitarian_funding population_by_governorate rainfall_by_governorate refugees_in_egypt
undp_human_development wfp_food_prices wfp_markets who_health_indicators worldbank_indicator_info worldbank_indicators
dept_emp dept_manager current_dept_emp dept_emp_latest_date emp_no
app_sessions_log nile_express rate_codes tpep_pickup_datetime tpep_dropoff_datetime PULocationID DOLocationID
order_payments order_reviews payment_sequential product_name_lenght product_description_lenght
product_category_name_translation olist invoice_lines StockCode InvoiceNo traded_value_egp
""".split()
NAMED = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, NAMES)) + r")(?![A-Za-z0-9_])", re.I)

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
#: The demo builds its own sample tables; naming them is its job.
OWN_SAMPLES = {"demo_content.py", "demo.py", "demo_seed.py"}
I18N = [pathlib.Path(p) for p in ("/frontend/src/i18n/en.ts", "/frontend/src/i18n/ar.ts")]


def _constants(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            yield n.lineno, n.value


def test_no_backend_text_names_a_tested_database():
    found = [f"{p.relative_to(APP)}:{line}: {m.group(0)}"
             for p in APP.rglob("*.py") if p.name not in OWN_SAMPLES
             for line, text in _constants(p) for m in NAMED.finditer(text)]
    assert not found, "\n".join(found)


@pytest.mark.skipif(not all(p.exists() for p in I18N), reason="frontend sources not mounted")
def test_no_interface_text_names_a_tested_database():
    found = [f"{p.name}:{i}: {m.group(0)}" for p in I18N
             for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) for m in NAMED.finditer(line)]
    assert not found, "\n".join(found)


def test_the_rule_would_catch_one():
    assert NAMED.search("e.g. 'SUM(traded_value_egp) by ticker'")
    assert not NAMED.search("e.g. 'SUM(amount) by customer' for the orders table")
