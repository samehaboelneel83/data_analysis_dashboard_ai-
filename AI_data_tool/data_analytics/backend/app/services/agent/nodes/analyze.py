"""Choose an analysis for a question that SQL answers in the wrong shape.

The analysis registry's prompt block told the model these analyses existed and
gave it no way to run one -- `render_prompt_block`'s docstring says so outright:
"capability discovery, not an invocation contract: today's agent only writes
SQL." So "is revenue really different across regions?" came back as four group
averages. Those four numbers are the arithmetic; whether they differ by more
than chance is a t-test, and one has been in the catalogue for months.

Two intents route, not six. `aggregate`, `trend` and `lookup` are genuinely SQL
questions and answering them with a statistic would replace a correct answer
with a worse one. `compare` and `explain` are the two whose SQL answer is most
obviously the wrong shape.

**The safety argument is the enum.** The model does not name columns; it picks
from a list built out of the frame it will be run against. It cannot invent a
column, and because dataset mode drops denied columns from the frame before the
agent sees anything (graph.py, the base-frame drop), it cannot pick one this
user is not allowed to see. Column security here is structural, not a check
somebody has to remember to write.

**Every refusal returns None, and None means "answer it with SQL".** A question
this path cannot serve still gets an answer. That is what makes the feature
additive rather than a new way to fail.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

#: Intent -> the analysis that answers it. The registry is the source of truth
#: for what these DO; this is only the routing.
ANALYSIS_FOR_INTENT = {
    "compare": "compare_groups",
    "explain": "explain_response",
}

#: `compare_groups` refuses fewer than ten rows in a group rather than report a
#: p-value nobody should act on. Checked here too, because reaching the analysis
#: only to be refused turns a working SQL answer into an error message.
_MIN_PER_GROUP = 10

#: A column with this many distinct values is an identifier or a free-text
#: field, not something to group by -- grouping on it makes as many groups as
#: there are rows.
_MAX_GROUPS = 30


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _groupable_columns(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        n = df[c].nunique(dropna=True)
        if 2 <= n <= _MAX_GROUPS:
            out.append(c)
    return out


def _big_enough_groups(df: pd.DataFrame, groupable: list[str]) -> list[str]:
    """Only columns whose smallest group could actually be tested."""
    return [c for c in groupable
            if df[c].value_counts(dropna=True).min() >= _MIN_PER_GROUP]


async def choose_analysis(question: str, intent: str, df: pd.DataFrame,
                          client) -> dict[str, Any] | None:
    """`{"analysis": name, "params": {...}}`, or None to fall through to SQL.

    `df` must be the SECURED frame -- row-filtered and with denied columns
    already dropped. Everything this function offers the model is derived from
    it, which is what makes the choice safe.
    """
    name = ANALYSIS_FOR_INTENT.get(intent)
    if name is None:
        return None

    numeric = _numeric_columns(df)
    if not numeric:
        return None

    if name == "compare_groups":
        groups = _big_enough_groups(df, _groupable_columns(df))
        if not groups:
            return None
        schema = {
            "type": "object",
            "properties": {
                "value_col": {"type": "string", "enum": numeric},
                "group_col": {"type": "string", "enum": groups},
            },
            "required": ["value_col", "group_col"],
            "additionalProperties": False,
        }
        instruction = (
            "Pick the numeric measure the question is about, and the column "
            "whose groups it is being compared across. Choose only from the "
            "lists given.")
    else:
        schema = {
            "type": "object",
            "properties": {"response": {"type": "string", "enum": numeric}},
            "required": ["response"],
            "additionalProperties": False,
        }
        instruction = (
            "Pick the numeric column the question wants explained -- the "
            "outcome, not the thing that might be causing it. Choose only "
            "from the list given.")

    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": f"Question: {question}"},
    ]
    reply = await client.complete_json(messages, schema, enforce=True,
                                       max_tokens=120, temperature=0.0)
    if not isinstance(reply, dict):
        return None

    params = {k: reply.get(k) for k in schema["required"]}
    # A model reply is untrusted input even under a constrained grammar: an
    # endpoint that ignores the grammar, or a future client that drops
    # `enforce`, must not be able to run an analysis on a column nobody
    # offered. Re-checked against the same enums, not against the frame, so
    # the two can never disagree.
    for key, value in params.items():
        if value not in (schema["properties"][key].get("enum") or []):
            return None
    return {"analysis": name, "params": params}
