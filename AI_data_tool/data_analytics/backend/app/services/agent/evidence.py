"""Every number in an answer, traced to the cell it came from (E11).

The prose of an Ask AI answer is written by a model from the rows a query
returned (nodes/explain). The prompt forbids inventing a figure, but a prompt
is a request, not a check: a model that adds two rows up, turns a count into a
percentage, or misreads 12,431 as 12,341 writes a number that no query
computed, in the same confident sentence as the ones that were.

This module is the check. It reads the answer AFTER it is written, finds each
number it states, and looks for it among the result rows the reader is shown.
A number found there is linked to its row and column, so the chat can point at
it; a number found nowhere is marked as not traced, so the reader knows which
figures are the query's and which are the model's own.

Deterministic and model-free on purpose: the same answer over the same rows
always traces the same way, for a stored conversation as for a new one, so it
runs where the payload is built rather than being stored with the run.

What counts as a claim, and what does not:

* A number stated in the question ("top 5"), or a literal in the SQL that ran
  (``LIMIT 10``, ``year = 2024``), is the question's own parameter. It is
  returned as ``context``: shown as a number, not checked.
* Dates and times ("2024-03-01", "14:30"), numbers inside quoted names
  ("Sales 2024"), and digits that are part of a word ("Q3", "step_1") are not
  numerical claims at all and are skipped.
* Everything else is a claim: ``traced`` when a cell (or a result's row count)
  equals it at the precision it was written with, ``untraced`` otherwise.

"At the precision it was written with": "1.2 million" is any cell that rounds
to it (1,150,000 to 1,249,999.99), "38%" is 0.38 or 38 (a share stored as a
fraction or as a percentage), "12,400" is 12,350 to 12,449 (trailing zeros in a
large integer read as rounding), "-5" or "5" in "fell by 5" is a cell of -5.
Arabic-Indic digits and separators are read as their Western forms.
"""
from __future__ import annotations

import math
import re
from typing import Any

import sqlglot
from sqlglot import exp

# Arabic-Indic and Extended (Persian) digits, and the Arabic decimal and
# thousands separators and percent sign. Every replacement is one character
# for one, so a span found in the normalized text is the same span in the
# original.
_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
_DIGITS.update({ord("٫"): ".", ord("٬"): ",", ord("٪"): "%", ord("−"): "-"})

_NUMBER = re.compile(
    r"(?<![\w.,])"                      # not the tail of a word or a number
    r"(?P<sign>[-+])?"
    r"(?P<cur>[$€£¥])?"
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)"
    r"(?P<frac>\.\d+)?"
    r"(?:\s?(?P<pct>%|percent\b|per cent\b)"
    r"|\s?(?P<scale>[kKMB]\b|bn\b|thousand\b|million\b|billion\b|"
    r"ألف|آلاف|مليون|ملايين|مليار))?"
    r"(?![\w])")

# Spans that contain digits but are not numerical claims.
_NOT_CLAIMS = re.compile(
    r"\d{4}-\d{2}(?:-\d{2})?(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?"   # ISO dates
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"                                     # times
    r"|\"[^\"\n]*\"|“[^”\n]*”|«[^»\n]*»|`[^`\n]*`")                      # quoted names

_SCALES = {"k": 1e3, "thousand": 1e3, "ألف": 1e3, "آلاف": 1e3,
           "m": 1e6, "million": 1e6, "مليون": 1e6, "ملايين": 1e6,
           "b": 1e9, "bn": 1e9, "billion": 1e9, "مليار": 1e9}

# Words after a number that say it counts the result's rows.
_COUNT_NOUNS = {"rows", "records", "entries", "items", "results", "columns",
                "tables", "row", "record", "column", "table"}

# A sentence ends at . ! ? or ؟ FOLLOWED BY SPACE (the point in "4,231.2"
# does not end one), or at a line break.
_SENTENCE_END = re.compile(r"(?<=[.!?؟;])\s+|\n")


def _normalize(text: str) -> str:
    return text.translate(_DIGITS)


def _parse(m: re.Match) -> dict:
    """What a matched number says: its value, how precisely it was written,
    and whether it is a percentage."""
    digits = m.group("int").replace(",", "")
    frac = m.group("frac") or ""
    value = float(digits + frac)
    if m.group("sign") == "-":
        value = -value
    decimals = len(frac) - 1 if frac else 0
    scale_word = (m.group("scale") or "").lower()
    scale = _SCALES.get(scale_word, 1.0)
    tol = 0.5 * 10 ** -decimals
    if not frac and scale == 1.0 and len(digits) >= 4:
        # "12,400": trailing zeros in a large integer are rounding. Keep at
        # least two significant digits, so "2,000" is 1,950-2,049, not
        # anything from 1,500.
        zeros = len(digits) - len(digits.rstrip("0"))
        zeros = min(zeros, len(digits) - 2)
        if zeros > 0:
            tol = 0.5 * 10 ** zeros
    return {"value": value * scale, "tol": tol * scale + 1e-9,
            "pct": bool(m.group("pct")), "signed": m.group("sign") is not None,
            "integer": not frac and scale == 1.0}


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s:
            return None
        try:
            f = float(s)
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


def _labels(row: list) -> list[str]:
    """A row's text cells, lowercased: the names a sentence calls it by."""
    return [c.strip().lower() for c in row
            if isinstance(c, str) and _as_number(c) is None and len(c.strip()) > 1]


def _equal(claim: dict, cell: float) -> bool:
    v, tol = claim["value"], claim["tol"]
    candidates = [cell]
    if claim["pct"]:
        candidates.append(cell * 100)       # a share stored as a fraction
    for c in candidates:
        if abs(c - v) <= tol:
            return True
        # "fell by 5" states the size of a change a cell holds as -5.
        if not claim["signed"] and abs(abs(c) - v) <= tol:
            return True
    return False


def _parameters(question: str, sqls: list[str]) -> tuple[set[float], set[float]]:
    """The numbers the question states, and the numeric literals in the SQL."""
    asked = {_parse(m)["value"] for m in _NUMBER.finditer(_normalize(question or ""))}
    literals: set[float] = set()
    for sql in sqls:
        try:
            tree = sqlglot.parse_one(sql)
        except Exception:
            continue
        for lit in tree.find_all(exp.Literal):
            if lit.is_number:
                try:
                    literals.add(float(lit.this))
                except (TypeError, ValueError):
                    pass
    return asked, literals


def _sentence_at(text: str, pos: int) -> str:
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if m.start() >= pos:
            return text[start:m.start()].lower()
        start = m.end()
    return text[start:].lower()


def _next_word(text: str, end: int) -> str:
    m = re.match(r"\s*([^\W\d_]+)", text[end:])
    return m.group(1).lower() if m else ""


#: Pairwise checks (a difference, a change) look at every pair of rows; past
#: this many rows the pairs outnumber anything a sentence could be about.
_PAIR_ROWS = 50


def _derived(claim: dict, results: list[dict], sentence: str) -> tuple[int, dict] | None:
    """A number the answer worked out from the rows, checked by doing the
    same arithmetic: a column's total or average, a row's share of the
    column, or the difference or change between two rows of one column.

    A share, a difference or a change is only taken when the sentence names
    the rows it is about (their labels appear in it): among 50 rows there are
    2,450 differences, and some number a model made up would equal one of
    them by chance. A total or an average is one number per column.

    Only over a complete result: a sum of the first 200 of 5,000 rows is not
    the total the answer means. A match is still evidence -- the figure is
    what the rows give -- and it says which rows and which operation, so the
    reader can redo it. Ranked below a direct cell match."""
    for ri, res in enumerate(results):
        rows = res.get("rows") or []
        # Fewer rows than the total: the snapshot is only the head of it.
        if len(rows) < 2 or len(rows) < (res.get("total") or 0):
            continue
        columns = [str(c) for c in (res.get("columns") or [])]
        named = {i for i, r in enumerate(rows) if any(lab in sentence for lab in _labels(r))}
        for j, col in enumerate(columns):
            vals = [(i, _as_number(r[j])) for i, r in enumerate(rows) if j < len(r)]
            vals = [(i, v) for i, v in vals if v is not None]
            if len(vals) < 2 or len(vals) < len(rows) * 0.5:
                continue
            total = sum(v for _, v in vals)
            src = {"result": ri, "row": None, "column": col}
            if not claim["pct"]:
                if _equal(claim, total):
                    return (0, {**src, "value": total, "kind": "sum"})
                if _equal(claim, total / len(vals)):
                    return (0, {**src, "value": total / len(vals), "kind": "average"})
            elif total:
                for i, v in vals:
                    if i in named and abs(v / total * 100 - claim["value"]) <= claim["tol"]:
                        return (0, {**src, "row": i, "value": v / total * 100, "kind": "share"})
            if len(vals) > _PAIR_ROWS:
                continue
            for a, va in vals:
                for b, vb in vals:
                    if a == b or a not in named or b not in named:
                        continue
                    if not claim["pct"] and va > vb and _equal(claim, va - vb):
                        return (0, {**src, "row": a, "rows": [a, b],
                                    "value": va - vb, "kind": "difference"})
                    if claim["pct"] and vb and abs(abs((va - vb) / abs(vb) * 100)
                                                    - abs(claim["value"])) <= claim["tol"] \
                            and (not claim["signed"] or (va - vb) * claim["value"] > 0):
                        return (0, {**src, "row": a, "rows": [a, b],
                                    "value": (va - vb) / abs(vb) * 100, "kind": "change"})
    return None


def trace_claims(answer: str | None, question: str | None,
                 results: list[dict], sqls: list[str]) -> dict | None:
    """The numbers `answer` states, each traced to the result rows or not.

    `results` are the snapshots the chat is given (`{columns, rows, total}`),
    in the order it is given them; a traced claim names its result by that
    index and its row by its index in `rows`, so the chat can point at the
    very cell. None when there is nothing to trace against (no result rows):
    then no number in the answer came from a query, and the chat says so in
    its own words.
    """
    if not answer or not results:
        return None
    text = _normalize(answer)
    skip = [(m.start(), m.end()) for m in _NOT_CLAIMS.finditer(text)]
    asked, literals = _parameters(question or "", sqls)

    claims: list[dict] = []
    for m in _NUMBER.finditer(text):
        if any(a <= m.start() < b for a, b in skip):
            continue
        claim = _parse(m)
        base = {"start": m.start(), "end": m.end(), "text": answer[m.start():m.end()]}
        if not claim["pct"] and any(abs(q - claim["value"]) < 1e-9 for q in asked):
            claims.append({**base, "status": "context"})
            continue
        sentence = _sentence_at(text, m.start())
        following = _next_word(text, m.end())
        best: tuple[int, dict] | None = None
        for ri, res in enumerate(results):
            columns = [str(c) for c in (res.get("columns") or [])]
            rows = res.get("rows") or []
            if claim["integer"] and not claim["pct"] and res.get("total") == claim["value"]:
                score = 1 + (2 if following in _COUNT_NOUNS
                             else 1 if following.endswith("s") else 0)
                cand = {"result": ri, "row": None, "column": None,
                        "value": res.get("total"), "kind": "count"}
                if best is None or score > best[0]:
                    best = (score, cand)
            for i, row in enumerate(rows):
                labels = _labels(row)
                for j, cell in enumerate(row):
                    num = _as_number(cell)
                    if num is None or not _equal(claim, num):
                        continue
                    col = columns[j] if j < len(columns) else None
                    score = 1
                    if any(lab in sentence for lab in labels):
                        score += 2
                    if col and col.replace("_", " ").lower() in sentence:
                        score += 1
                    if best is None or score > best[0]:
                        best = (score, {"result": ri, "row": i, "column": col,
                                        "value": cell, "kind": "cell"})
        if best is None:
            best = _derived(claim, results, sentence)
        if best is not None:
            claims.append({**base, "status": "traced", "source": best[1]})
        elif not claim["pct"] and any(abs(q - claim["value"]) < 1e-9 for q in literals):
            claims.append({**base, "status": "context"})
        else:
            claims.append({**base, "status": "untraced"})
    return {"claims": claims,
            "untraced": sum(1 for c in claims if c["status"] == "untraced")}
