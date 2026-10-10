"""Plain words for a formula that does not work, and a summary of one that does
(calculated-column builder, 2026-10-10).

The Test button showed Python: `name 'cot' is not defined`, `invalid syntax
(<unknown>, line 1)`. `explain` turns the raw error into a problem CODE with its
details (the frontend words it, in English or Arabic) -- "There is no column
called cot. Did you mean cost?" -- and keeps the raw text for "Show details".

`summarize` answers what six sample values could not: for labels, how many rows
got each one (a band that no row reached is usually a mistake); for numbers,
the lowest, average and highest, and how many rows came out empty or infinite.
"""
from __future__ import annotations

import difflib
import math
import re

import numpy as np
import pandas as pd

#: The functions a formula may call (kept in step with widget_data's namespace;
#: only used for "did you mean").
KNOWN_FUNCTIONS = (
    "abs round min max int float str len pow log sqrt exp floor ceil IF SWITCH isnull "
    "SENTIMENT SENTIMENT_LABEL UPPER LOWER TRIM LEN REVERSE LEFT RIGHT SUBSTRING CONCAT "
    "REPLACE FIND CONTAINS STARTSWITH ENDSWITH SPLIT YEAR QUARTER MONTH DAY WEEKDAY "
    "DAYOFYEAR MONTHNAME DAYNAME DATE DATEADD DATEDIFF TODAY NOW "
    # measures
    "SUM AVG MEDIAN COUNT COUNTD STDEV VARIANCE MIN MAX TOTAL BYGROUP SCOPE ISINSCOPE CALC"
).split()

_OPERATORS = ("+", "-", "*", "/", "%", "**", "==", "!=", ">", "<", ">=", "<=", ",", "and", "or", "not")


def _closest(name: str, candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in candidates}
    if name.lower() in lower:                 # wrong case: Round -> round, region -> Region
        return lower[name.lower()]
    hit = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
    return hit[0] if hit else None


def explain(raw: str, expression: str, columns: list[str]) -> dict:
    """{"code", ...details} for the frontend to word; code "other" when the
    error is not one we recognise (the raw text is then all there is)."""
    text = (expression or "").strip()

    m = re.search(r"name '([^']+)' is not defined", raw) or re.search(r"Unknown column[^:]*: name '([^']+)'", raw)
    if m:
        name = m.group(1)
        out = {"code": "unknown_name", "name": name}
        suggest = _closest(name, list(columns) + list(KNOWN_FUNCTIONS))
        if suggest and suggest != name:
            out["suggest"] = suggest
        return out

    m = re.search(r"(\w+)\(\) takes (\d+) positional arguments? but (\d+) (?:were|was) given", raw)
    if m:
        return {"code": "wrong_count", "function": m.group(1).split(".")[-1],
                "expected": int(m.group(2)), "given": int(m.group(3))}

    m = re.search(r"(\w+)\(\) missing (\d+) required positional argument", raw)
    if m:
        return {"code": "missing_value", "function": m.group(1), "missing": int(m.group(2))}

    m = re.search(r"unsupported operand type\(s\) for ([^:]+): '(\w+)' and '(\w+)'", raw)
    if m or "can only concatenate str" in raw or "can't multiply sequence" in raw:
        return {"code": "text_math", "operator": (m.group(1).strip() if m else "+")}

    if "Expression is not valid" in raw or "invalid syntax" in raw or "was never closed" in raw \
            or "unmatched" in raw or "unexpected EOF" in raw or "SyntaxError" in raw:
        opened, closed = text.count("("), text.count(")")
        if opened != closed:
            return {"code": "brackets", "open": opened, "close": closed}
        if re.search(r"(^|[^=!<>])=([^=]|$)", text):
            return {"code": "single_equals"}
        for op in sorted(_OPERATORS, key=len, reverse=True):
            if text.endswith(op) and (op.isalpha() is False or re.search(rf"\b{op}$", text)):
                return {"code": "ends_with_operator", "operator": op}
        if text.count("'") % 2 or text.count('"') % 2:
            return {"code": "open_quote"}
        return {"code": "syntax"}

    if "disallowed" in raw:
        return {"code": "not_allowed"}
    return {"code": "other"}


def _plain(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v if isinstance(v, (int, float, bool, str)) else str(v)


def summarize(result) -> dict | None:
    """What the whole result looks like, or None for a single value."""
    if isinstance(result, np.ndarray):
        result = pd.Series(result)
    if not isinstance(result, pd.Series):
        return None
    rows = int(len(result))
    if result.dtype == object:
        # IF(units == 0, None, revenue / units) is numbers with gaps: still numbers.
        present = result.dropna()
        if len(present) and all(isinstance(v, (int, float, np.number)) and not isinstance(v, bool)
                                for v in present):
            result = pd.to_numeric(result, errors="coerce")
    if pd.api.types.is_bool_dtype(result) or not pd.api.types.is_numeric_dtype(result):
        blank = result.isna()
        if result.dtype == object:
            blank = blank | (result.astype(str).str.strip() == "")
        vc = result[~blank].astype(str).value_counts()
        return {"kind": "labels", "rows": rows, "empty": int(blank.sum()), "distinct": int(len(vc)),
                "top": [[k, int(n)] for k, n in vc.head(8).items()]}
    numbers = pd.to_numeric(result, errors="coerce")
    infinite = int(np.isinf(numbers).sum())
    finite = numbers[np.isfinite(numbers)]
    return {"kind": "number", "rows": rows, "empty": int(numbers.isna().sum()), "infinite": infinite,
            "min": _plain(finite.min()) if len(finite) else None,
            "mean": _plain(finite.mean()) if len(finite) else None,
            "max": _plain(finite.max()) if len(finite) else None}
