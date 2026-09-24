"""The answer, with provenance — and a deterministic fallback, because a
correctly computed result must not be discarded when prose generation fails."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from ..state import StepResult


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


def _label(r: StepResult) -> str:
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
        return f"rows from {', '.join(tables)}"
    return "query result"


def _facts(results: dict[str, StepResult],
           sink_ids: set[str] | None = None) -> str:
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
            lines.append(f"{_label(r)} ({n} {_row_noun(r)}, showing {shown}): "
                        f"{r.rows[:20]!r}")
    return "\n".join(lines)


def render_fallback(results: dict[str, StepResult], concerns: list[str],
                    sink_ids: set[str] | None = None) -> str:
    text = "Result:\n" + _facts(results, sink_ids)
    if concerns:
        text += "\nNotes: " + "; ".join(concerns)
    return text


async def describe(question: str, results: dict[str, StepResult],
                   concerns: list[str], client,
                   sink_ids: set[str] | None = None) -> str | None:
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
            "You are describing a result the person is ALREADY LOOKING AT. It "
            "has been computed and is on their screen, drawn as a table or a "
            "chart. Say what it shows in 2-4 sentences: how many rows and "
            "what the columns are, the notable values (the largest, the "
            "smallest, anything constant across every row, anything "
            "surprising), and whatever their message asks about it.\n"
            "Use ONLY the figures given and state numbers exactly; never "
            "invent one, and never describe a value you were not given. "
            "Refer to data by its TABLE names as the figures label them; "
            "never call anything a step, a result set or a figure. "
            "NEVER say the result cannot be shown, drawn, charted or "
            "determined — it is already shown; your job is to describe it, "
            "not to judge whether it can be displayed. If notes are present, "
            "work them into the description honestly: a note that the "
            "figures are a sample of a larger result means you describe the "
            "sample AS a sample.")},
         {"role": "user", "content": (
             f"Their message: {question}\n\nFigures:\n{_facts(results, sink_ids)}\n\n"
             f"Notes: {'; '.join(concerns) or 'none'}")}],
        max_tokens=300, temperature=0.2)
    return got.strip() if got else None


async def explain(question: str, results: dict[str, StepResult],
                  concerns: list[str], client,
                  sink_ids: set[str] | None = None) -> str | None:
    got = await client.complete(
        [{"role": "system", "content": (
            "Answer the user's question in 1-3 sentences from ONLY the "
            "figures given. State numbers exactly; do not invent any. Refer "
            "to data by its TABLE names as the figures label them; never "
            "call anything a step, a result set or a figure. Each block "
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
             f"Question: {question}\n\nFigures:\n{_facts(results, sink_ids)}\n\n"
             f"Notes: {'; '.join(concerns) or 'none'}")}],
        max_tokens=250, temperature=0.2)
    return got.strip() if got else None
