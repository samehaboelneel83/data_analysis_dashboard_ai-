"""The engine speaks no trade's language (docs/discovery/PLAN.md, phase 0).

Datalytics is a general-purpose platform. The modules that decide what a
column is, what is worth suggesting, and what the model is told must not
contain the nouns of one field of work -- not in a word list, not in a prompt
example. What such a column is comes from its values and its stored
classification (services/column_classes.py).

This test reads the STRINGS of those modules (word lists, regexes, prompt
text). Comments and docstrings are free to tell the story of the database a
rule was learnt on; so are tests and demo content.
"""
import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

#: The modules that hold the engine's judgement and its prompts.
ENGINE = [
    "services/semantic_guard.py", "services/column_classes.py", "services/insights.py",
    "services/suggest_variety.py", "services/suggest_gate.py", "services/readback.py",
    "services/derived_fields.py", "services/dataset_profile.py", "services/fact_sheet.py",
    "services/analyst_panel.py", "services/suggest_dataset_dashboard.py", "services/suggest_dashboard.py",
    "services/source_brief.py", "services/suggest_inputs.py", "services/suggest_from_insights.py",
    "services/widget_review.py", "services/ai_policy.py", "services/explain.py",
    "services/metadata/infer_semantic.py",
    "services/guided_setup", "services/agent/nodes", "services/agent/without_model.py",
    "services/agent/validate.py", "services/analysis",
]

#: Nouns that belong to one field of work. Words every organisation's books
#: share (amount, cost, fee, revenue, income, expense, budget) and words for
#: structure and measurement (id, rate, price, count, region) are not here.
TRADE_WORDS = [
    # people at work
    "salary", "salaries", "wage", "wages", "payroll", "employee", "employees", "headcount", "hire", "hires",
    "hired", "hiring", "tenure",
    # commerce and logistics
    "customer", "customers", "seller", "sellers", "shipment", "shipments", "shipped", "parcel", "parcels",
    "freight", "sku", "commodity", "commodities", "churn", "invoice", "invoices", "checkout", "cart",
    # things for sale
    "mileage", "odometer", "bedroom", "bedrooms", "bathroom", "bathrooms",
    # health, education, telecom, places
    "patient", "patients", "hospital", "tuition", "imei", "imsi", "msisdn", "iccid",
    "olist", "cairo", "giza", "egp",
]
_WORD = re.compile(r"(?<![A-Za-z])(" + "|".join(TRADE_WORDS) + r")(?![A-Za-z])", re.I)

#: Strings allowed to keep a listed word, with the reason. Keep this short.
ALLOWED = {
    # Personal-data detection is privacy, not suggestion logic: a device or
    # subscriber number is personal whatever the business.
}


def _files():
    for entry in ENGINE:
        path = APP / entry
        yield from (sorted(path.rglob("*.py")) if path.is_dir() else [path])


def _docstrings(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def trade_words_in_strings() -> list[str]:
    hits = []
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                for m in _WORD.finditer(node.value):
                    key = f"{path.relative_to(APP)}:{m.group(1).lower()}"
                    if key not in ALLOWED:
                        hits.append(f"{path.relative_to(APP)}:{node.lineno}: {m.group(1)!r} in "
                                    f"{node.value[max(0, m.start() - 30):m.end() + 30]!r}")
    return hits


def test_no_trade_noun_in_the_engines_word_lists_or_prompts():
    hits = trade_words_in_strings()
    assert not hits, "one field of work's vocabulary in the engine:\n" + "\n".join(hits[:60])


def test_the_scan_sees_what_it_should():
    """The check is only worth having if it would catch a regression."""
    assert _WORD.search("a salary is averaged") and _WORD.search("_NAMES = ('imei', 'x')")
    assert not _WORD.search("the amount by region, per category")
    assert not _WORD.search("hired_gun_x".replace("hired", "wired"))
