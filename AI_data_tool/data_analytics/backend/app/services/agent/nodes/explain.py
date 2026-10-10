"""The answer, with provenance — and a deterministic fallback, because a
correctly computed result must not be discarded when prose generation fails."""
from __future__ import annotations

import math
from decimal import Decimal

import sqlglot
from sqlglot import exp

from ..state import StepResult


#: HR evaluation (item 3.6): an Arabic question was answered in English.
LANGUAGE_RULE = ("Write in the SAME language as the user's question -- an Arabic "
                 "question gets an Arabic answer -- keeping every number, name and "
                 "data value exactly as given. Write numbers of four or more digits "
                 "with thousands separators (37,701) in every language. ")


def question_language(question: str) -> str:
    """"Arabic" or "English", decided from the question's own letters (most
    letters Arabic -> Arabic). Analyst tour, 2026-10-10: an English question
    got an Arabic answer -- "the same language as the question" was left to
    the model, and a local model does not always follow it."""
    import re
    arabic = len(re.findall(r"[\u0600-\u06FF]", question or ""))
    latin = len(re.findall(r"[A-Za-z]", question or ""))
    return "Arabic" if arabic > latin else "English"


def language_rule(question: str) -> str:
    """LANGUAGE_RULE with the language named outright."""
    lang = question_language(question)
    return (f"Write the answer in {lang}, because the question is in {lang}. " + LANGUAGE_RULE)


def _period_key(v) -> float | None:
    """A sortable number for a period label: 2002, '2002', '2002-08', '2002-Q3'."""
    import re
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})(?:[-/](\d{1,2}))?(?:-(\d{1,2}))?", s)
    if m:
        y = int(m.group(1))
        if not 1900 <= y <= 2200:
            return None
        return y + (int(m.group(2)) / 100 if m.group(2) else 0)
    m = re.fullmatch(r"(\d{4})-Q([1-4])", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 10
    return None


def partial_period_note(r: StepResult) -> str | None:
    """A series by period whose LAST period drops sharply -- often a period the
    data only partly covers (HR evaluation: leavers in 2002 looked like an
    improvement, but the data stops in August). Said as a possibility, never
    as a finding."""
    rows = r.rows or []
    if len(rows) < 4 or not isinstance(rows[0], dict):
        return None
    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None
    period, value = keys[0], next((k for k in keys[1:]
                                   if isinstance(rows[0].get(k), (int, float, Decimal))), None)
    if value is None:
        return None
    pts = [(_period_key(row.get(period)), row.get(value), row.get(period)) for row in rows]
    if any(p is None or not isinstance(v, (int, float, Decimal)) for p, v, _ in pts):
        return None
    pts.sort(key=lambda t: t[0])
    last, prev = float(pts[-1][1]), float(pts[-2][1])
    if prev > 0 and last < prev * 0.7:
        return (f"the last period ({pts[-1][2]}) is much lower than the one before it; "
                f"it may be a period the data only partly covers")
    return None


def _catalog_is_columns(r: StepResult) -> bool:
    """Whether the catalog step is describing ONE object's columns.

    `catalog_overview` has two shapes: one row per column when a single
    dataset or one-table connection is in scope, one row per table otherwise.
    """
    first = (r.rows or [None])[0]
    return isinstance(first, dict) and list(first.keys())[:2] == ["column", "type"]


def _row_noun(r: StepResult) -> str:
    """What one of this result's rows IS.

    The count sits next to the sample so the prose can never claim a figure
    its own data disproves -- but "rows" is only the right word when the rows
    are the data. The catalog step in single-object scope has one row per
    COLUMN, and calling those 13 rows is how "what is this data?" came back
    as "13 rows" for a 13-COLUMN dataset: a true count of the wrong noun,
    which reads as a plain error to anyone who knows the dataset.
    """
    if r.step_id == "catalog":
        return "columns" if _catalog_is_columns(r) else "tables"
    return "rows"


def _display(table: str, names: dict[str, str] | None) -> str:
    """A dataset's own name for its query table (BUG-032). Dataset mode queries
    each dataset under a sanitized table name ("QA_CHROME_sales" becomes
    qa_chrome_sales), and answers used to repeat that internal name to the
    person who named the data. A real database table (source mode) has no
    other name and stays as it is."""
    shown = (names or {}).get(table)
    return f'"{shown}"' if shown else table


def _label(r: StepResult, names: dict[str, str] | None = None) -> str:
    """What a result IS, for the model that will describe it.

    The figures used to be labelled `step step_1 (...)`, and the model read
    that label as a NAME: live, "choose the best table to draw a graph" was
    answered with "the best table is step_1, which contains 10 rows of grade
    data" -- an internal id presented to a person as if it were a table, while
    the real table (mdl_grade_grades) sat unmentioned in the SQL. So the label
    now says where the rows came from, in the reader's own terms: the tables
    the SQL read. The step id never reaches the prose at all."""
    if r.step_id == "catalog":
        return ("the data catalog (the columns of the data in scope, and their types)"
                if _catalog_is_columns(r)
                else "the data catalog (every table in scope, and what each holds)")
    tables: list[str] = []
    if r.sql:
        try:
            tables = sorted({t.name for t in sqlglot.parse_one(r.sql).find_all(exp.Table)
                             if t.name})
        except Exception:
            tables = []
    if tables:
        return f"rows from {', '.join(_display(t, names) for t in tables)}"
    return "query result"


def _tidy(v):
    """A number as a person writes it (BUG-032): a float64 sum reached the
    model as 2580.0 and was repeated that way. Whole values lose the ".0".

    HR re-test 2026-10-01: the model repeats what it is handed, so an average
    salary reached the reader as "71963.5708" in both languages. From 100 up
    two decimals are all an answer ever needs (money, counts, averages of
    either); small values -- rates, ratios -- keep four."""
    if isinstance(v, bool) or not isinstance(v, (float, Decimal)):
        return v
    f = float(v)
    if math.isnan(f) or math.isinf(f):
        return v
    if f.is_integer() and abs(f) < 1e15:
        return int(f)
    return round(f, 2) if abs(f) >= 100 else round(f, 4)


def _is_number(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _ordered(r: StepResult) -> list:
    """The rows in the order a reader expects (BUG-032). With no ORDER BY the
    engine returns groups in whatever order it likes, and the answer listed
    them that way; then the rows go largest first by their LAST numeric
    column -- the measure, which a SELECT puts after its dimensions. An
    explicit ORDER BY is the author's order and is kept. Only the copy the
    prose is written from is sorted; the stored result is untouched."""
    rows = list(r.rows or [])
    if r.step_id == "catalog" or len(rows) < 2 or not isinstance(rows[0], dict):
        return rows
    try:
        if not r.sql or sqlglot.parse_one(r.sql).args.get("order") is not None:
            return rows
    except Exception:
        return rows
    numeric = [k for k in rows[0]
               if all(row.get(k) is None or _is_number(row.get(k)) for row in rows)
               and any(row.get(k) is not None for row in rows)]
    if not numeric:
        return rows
    key = numeric[-1]
    return sorted(rows, key=lambda row: (row.get(key) is None, -float(row.get(key) or 0)))


def _whole_result(rows: list) -> str:
    """Each numeric column's smallest and largest value over EVERY row, with
    the row it came from, and its total. Live QA 2026-09-28: shown the first
    20 of 194 days, the answer said volume "ranged from 20 to 4125" -- the
    true range was 1 to 918,127,301. A range the model reads from a sample is
    a range it invents."""
    if not rows or not isinstance(rows[0], dict):
        return ""
    keys = list(rows[0])
    numeric = [k for k in keys if any(_is_number(r.get(k)) for r in rows)
               and all(r.get(k) is None or _is_number(r.get(k)) for r in rows)]
    label = next((k for k in keys if k not in numeric), None)
    from ...semantic_guard import non_additive_kind
    parts = []
    for k in numeric:
        kind = non_additive_kind(k)
        if kind == "identifier":
            # An identifier's range or total is not a figure anyone asked for
            # ("19,610,370,001,963 total A_NUMBER", live QA 2026-09-28).
            continue
        vals = [r for r in rows if _is_number(r.get(k))]
        if not vals:
            continue
        lo = min(vals, key=lambda r: r[k])
        hi = max(vals, key=lambda r: r[k])
        at = (lambda r: f" at {_tidy(r.get(label))}") if label else (lambda r: "")
        total = "" if kind else f", total {_tidy(sum(float(r[k]) for r in vals))}"
        parts.append(f"{k}: smallest {_tidy(lo[k])}{at(lo)}, largest {_tidy(hi[k])}{at(hi)}{total}")
    return "; ".join(parts)


def _facts(results: dict[str, StepResult],
           sink_ids: set[str] | None = None,
           names: dict[str, str] | None = None) -> str:
    """Only SINK steps' rows are ever shown to the model (H6 follow-up): a
    multi-step run's intermediate steps exist purely to feed a later step's
    SQL — their rows were already consumed by generate_sql's parent_facts —
    and handing them to explain again invited it to redo that arithmetic
    itself, wrong, on top of an already-correct final result. `sink_ids=None`
    means "every result is a sink" (a single-step run, or any caller that
    hasn't computed the DAG's sinks — see state.sink_step_ids), so existing
    single-step behaviour is unchanged."""
    if sink_ids is None:
        sink_ids = set(results.keys())
    lines = []
    for r in results.values():
        if r.step_id in sink_ids and r.status == "ok" and r.rows is not None:
            n = len(r.rows)
            shown = min(n, 20)
            # Round-5 false-refusal: prose contradicted its own figures
            # because the shown sample carried no total count. Stating the
            # TOTAL next to the sample means the prose can never claim a
            # count its own figures disprove.
            sample = [{k: _tidy(v) for k, v in row.items()} if isinstance(row, dict) else row
                      for row in _ordered(r)[:20]]
            # "all shown" when nothing is hidden: told "(1 rows, showing 1)"
            # beside a rule about samples, the model called a one-row answer
            # incomplete (live QA 2026-09-28).
            seen = "all shown" if shown >= n else f"showing {shown}"
            lines.append(f"{_label(r, names)} ({n} {_row_noun(r)}, {seen}): "
                        f"{sample!r}")
            if n > shown:
                whole = _whole_result(r.rows)
                if whole:
                    lines.append(f"  Across ALL {n} {_row_noun(r)} (not just those shown): {whole}")
            note = partial_period_note(r)
            if note:
                lines.append(f"  Note: {note} -- mention this possibility.")
    return "\n".join(lines)


def render_fallback(results: dict[str, StepResult], concerns: list[str],
                    sink_ids: set[str] | None = None,
                    names: dict[str, str] | None = None) -> str:
    text = "Result:\n" + _facts(results, sink_ids, names)
    if concerns:
        text += "\nNotes: " + "; ".join(concerns)
    return text


async def describe(question: str, results: dict[str, StepResult],
                   concerns: list[str], client,
                   sink_ids: set[str] | None = None,
                   names: dict[str, str] | None = None) -> str | None:
    """"Explain this chart" -- the rows are already on the person's screen.

    A separate prompt from `explain`, not a separate module: both write prose
    from `_facts` and neither may invent a number, but they are asked
    different things. Run through `explain`'s prompt -- which answers a
    QUESTION from figures -- "explain this chart" produced "the first 10 rows
    cannot be displayed as a bar chart because the provided figures only
    contain tabular data": a refusal to draw something that was already drawn.
    Measured live, not reasoned about. So this prompt says what the job is:
    the result exists, describe what is in it."""
    got = await client.complete(
        [{"role": "system", "content": (
            language_rule(question) +
            "You are describing a result the person is ALREADY LOOKING AT. It "
            "has been computed and is on their screen, drawn as a table or a "
            "chart. Say what it shows in 2-4 sentences: how many rows and "
            "what the columns are, the notable values (the largest, the "
            "smallest, anything constant across every row, anything "
            "surprising), and whatever their message asks about it.\n"
            "Use ONLY the figures given and state numbers exactly; never "
            "invent one, and never describe a value you were not given. "
            "Take the largest, smallest and totals from a block's 'Across "
            "ALL' line when it has one -- the rows shown are a sample. "
            "Refer to data by the names the figures label it with -- a "
            "quoted name is the dataset's own name, used as written; "
            "never call anything a step, a result set or a figure. "
            "Do not suggest further analyses, and never mention a column "
            "that is not in the figures. "
            "NEVER say the result cannot be shown, drawn, charted or "
            "determined — it is already shown; your job is to describe it, "
            "not to judge whether it can be displayed. If notes are present, "
            "work them into the description honestly: a note that the "
            "figures are a sample of a larger result means you describe the "
            "sample AS a sample.")},
         {"role": "user", "content": (
             f"Their message: {question}\n\nFigures:\n{_facts(results, sink_ids, names)}\n\n"
             f"Notes: {'; '.join(concerns) or 'none'}")}],
        max_tokens=300, temperature=0.2)
    return got.strip() if got else None


async def explain(question: str, results: dict[str, StepResult],
                  concerns: list[str], client,
                  sink_ids: set[str] | None = None,
                  names: dict[str, str] | None = None) -> str | None:
    got = await client.complete(
        [{"role": "system", "content": (
            language_rule(question) +
            "Answer the user's question in 1-3 sentences from ONLY the "
            "figures given. State numbers exactly; do not invent any. When a "
            "block shows only some of its rows, take every smallest, largest, "
            "total or range from its 'Across ALL' line -- never from the rows "
            "shown, which are a sample. A block marked 'all shown' is "
            "complete: when a top-N question returns fewer rows than N, "
            "that many exist -- say so plainly, never that the list cannot "
            "be completed. Refer "
            "to data by the names the figures label it with -- a quoted "
            "name is the dataset's own name, used as written; never "
            "call anything a step, a result set or a figure. Do not "
            "suggest further analyses, and never mention a column that is "
            "not in the figures. List groups in the order given. Each block "
            "states what its entries ARE -- rows, columns or tables -- so "
            "use that noun: a catalog listing 13 columns must never be "
            "described as 13 rows. If "
            "notes are present, work them into the answer honestly. "
            "When figures are present below, you MUST state them in your "
            "answer — it is FORBIDDEN to make ANY claim that the data is "
            "unavailable, unknown, or indeterminate when a sink step "
            "returned one or more rows; the rows ARE the answer, use them. "
            "This rule is about the CLAIM you make, not specific wording: "
            "'cannot determine', 'impossible to determine', and 'no data "
            "available' are example phrasings of this forbidden claim, not "
            "an exhaustive list — any equivalent wording is equally "
            "forbidden. An empty result (no rows for a step) is answered "
            "as 'none found' — never as 'cannot determine' or 'impossible "
            "to determine', which misrepresent a real, computed empty "
            "result as a failure.")},
         {"role": "user", "content": (
             f"Question: {question}\n\nFigures:\n{_facts(results, sink_ids, names)}\n\n"
             f"Notes: {'; '.join(concerns) or 'none'}")}],
        max_tokens=250, temperature=0.2)
    return got.strip() if got else None
