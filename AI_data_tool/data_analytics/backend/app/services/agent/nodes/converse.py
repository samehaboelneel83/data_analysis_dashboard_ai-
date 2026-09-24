"""The reply to a message that is not a question about the data.

Every other node in this package exists to turn a question into SQL. This one
exists because not every message is a question: "hi", "thanks", "what can you
do". Before it, the pipeline had no way to say so -- classify's enum was six
data intents wide and `ambiguous` was the only non-answer -- so a greeting was
classified as `lookup`, planned, queried, and narrated as if ten rows of a
table had been asked for. The screenshot of that is why `chat` and this node
exist.

Two rules make this safe rather than just friendly:

* **No figures, ever.** Nothing has been queried when this runs, so any number
  in the reply would be invented. The prompt forbids counts and values
  outright, and the schema block deliberately carries names and descriptions
  only -- there are no row values in it to leak or to misread as a result.
* **No false modesty.** An earlier version of this prompt said "do not offer
  to do anything this page cannot do", and the model turned that into "I
  can't generate charts directly" -- to a person looking at a product whose
  entire job is charts. A reply that understates the product is as wrong as
  one that overstates it, so the prompt now lists what it CAN do and forbids
  denying any of it.
* **A deterministic fallback.** The model endpoint being down must not turn
  "hi" into a failed run; a greeting is answerable without a model.

The reply is prose and nothing else: no steps, no SQL, no snapshot. The chat
renders it as a plain answer bubble, which is what it is.
"""
from __future__ import annotations

from ..context import SchemaContext
from .followup import render_history

#: What to say when the model is unreachable. Deliberately not chatty: it has
#: to be true of every message that reaches this node, from "hi" to "who are
#: you", without knowing which one it was.
FALLBACK = ("I answer questions about the data you have selected. "
            "Ask me anything about it and I will query it for you.")

#: The names alone are enough to say what the data is about; the enrichment
#: pass (dtypes, labels) is for the node that writes SQL, and none is written
#: here. Small on purpose -- this call is pure overhead on "hi".
_CONTEXT_CHARS = 2000


async def converse(question: str, context: SchemaContext | None, client,
                   history: list[dict] | None = None) -> str | None:
    """A short, plain reply. None when the model could not be reached, which
    the caller answers with FALLBACK rather than failing the run."""
    schema_block = (context.render(max_chars=_CONTEXT_CHARS, question=question)
                    if context is not None and context.objects else "")
    conversation = (f"Conversation so far:\n{render_history(history)}\n\n"
                    if history else "")
    got = await client.complete(
        [{"role": "system", "content": (
            "You are the assistant on a data chat page. The person's message "
            "is NOT a question about the data — it is a greeting, a "
            "thank-you, small talk, or a question about you. Reply in one or "
            "two short sentences, in the language they wrote in.\n"
            "You have NOT queried anything, so you MUST NOT state any row "
            "count, total, average, date range or value from the data — not "
            "even an approximate one. You may say what the data is ABOUT "
            "using the table and column names below, and you may invite a "
            "question about it. Do not write SQL here.\n"
            "You CAN do all of these, and you must NEVER say you cannot: "
            "answer a question about this data by querying it, show the "
            "matching rows, draw a bar, line or pie chart of a result, "
            "explain a result in words, and export it as CSV, Excel or PDF. "
            "If their message asks for one of those, do not do it in this "
            "reply and do not refuse it either — say what you need from them "
            "in order to do it (which columns to chart, which question to "
            "answer).\n"
            "You take NO actions: you do not create, save, delete or change "
            "datasets, dashboards, tables or anything else. If asked to, say "
            "so in one sentence and say where it is done — datasets are "
            "created and edited on the Datasets page, dashboards on the "
            "Dashboards page — and that any answer here can be exported as "
            "CSV, Excel or PDF. Never describe an action as done.")},
         {"role": "user", "content": (
             (f"The data available:\n{schema_block}\n\n" if schema_block else "")
             + f"{conversation}Message: {question}")}],
        max_tokens=160, temperature=0.3)
    return got.strip() if got and got.strip() else None
