"""Intent + ambiguity, under the enforced JSON contract.

Enforcement is structural, not semantic (spec F2 — a trend question came back
as valid JSON calling itself `lookup` with confidence 0). So the prompt
carries few-shot examples per intent, and the eval gate in evals/ is what
actually polices quality. This node only guarantees the SHAPE.
"""
from __future__ import annotations

from ..context import SchemaContext
from .followup import render_history

#: `suggest_dashboard` is the odd one out and deliberately so: the other five
#: describe a question ABOUT the data, and each ends in SQL over it. This one asks
#: the agent to design something, has no rows to return, and short-circuits in
#: graph.py before any planning happens. It lives in the same enum because the
#: classifier is the only place that reads what the person typed.
#:
#: `chat` is the enum's escape hatch, and the reason it exists is a screenshot:
#: someone typed "hi" and got ten rows of a table back, because a forced choice
#: between six DATA intents has no way to say "this message is not asking about
#: the data". `ambiguous` was not that way out either -- "hi" is not a tie
#: between two readings, it is not a reading at all -- so the run went to plan,
#: SQL and a confident narration of rows nobody asked for. A message that asks
#: for data, even partly, is never `chat`: the escape hatch must not become a
#: way to duck a real question.
#: `describe_data` is the other one that does not end in a person's own SQL:
#: it answers "what IS this data" from the CATALOG -- every table in scope and
#: what each holds -- and then lets the query run anyway, so the description
#: and the numbers arrive together. Measured live: asked to describe a
#: seventeen-table connection, the agent counted four tables it chose itself
#: and said nothing about the other thirteen. The numbers were right and the
#: answer was still a narrowing nobody was told about.
INTENTS = ["lookup", "aggregate", "trend", "compare", "explain",
           "suggest_dashboard", "chat", "describe_data"]

#: A cheap, deterministic pre-check for the one intent that must never be sent
#: back as a clarification. "Suggest a dashboard" has no missing detail to ask
#: about -- choosing IS the request -- so a clarification here is a dead end for
#: the user. Words only, no model call: this runs before classify and its answer
#: is not a matter of judgement.
_DASHBOARD_WORDS = ("dashboard", "dashboards")


def is_dashboard_request(question: str) -> bool:
    """Is the person asking to be shown a dashboard rather than a number?"""
    q = (question or "").lower()
    if not any(w in q for w in _DASHBOARD_WORDS):
        return False
    return any(v in q for v in
               ("suggest", "propose", "recommend", "build", "create", "make",
                "design", "give me", "show me", "i need", "i want"))

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "ambiguous": {"type": "boolean"},
        "ambiguity_reason": {"type": ["string", "null"]},
    },
    "required": ["intent", "ambiguous", "ambiguity_reason"],
    "additionalProperties": False,
}

_EXAMPLES = """Examples:
Q: what is customer 8842's email -> {"intent": "lookup", "ambiguous": false, "ambiguity_reason": null}
Q: total revenue by region -> {"intent": "aggregate", "ambiguous": false, "ambiguity_reason": null}
Q: how did signups change month over month -> {"intent": "trend", "ambiguous": false, "ambiguity_reason": null}
Q: cairo vs giza sales -> {"intent": "compare", "ambiguous": false, "ambiguity_reason": null}
Q: why did returns spike -> {"intent": "explain", "ambiguous": false, "ambiguity_reason": null}
Q: show me the numbers -> {"intent": "lookup", "ambiguous": true, "ambiguity_reason": "which numbers — no metric or table named"}
Q: how many student solutions are there -> {"intent": "aggregate", "ambiguous": false, "ambiguity_reason": null}
-- schema has both `student_solutions` (base table) and
-- `v_student_solutions_norm` (a normalized view derived from it); the plain,
-- undecorated phrasing names the base table, and "normalized" was never
-- said — the near-duplicate name is not ambiguity.
Q: total sales in the customers table -> {"intent": "aggregate", "ambiguous": false, "ambiguity_reason": null}
-- schema has both `customers` and `customers_archive`; the question names
-- the specific table, so the archive variant is irrelevant, not a tie.
Q: revenue by product -> {"intent": "aggregate", "ambiguous": false, "ambiguity_reason": null}
-- schema has `products` and `product_variants`; "product" (unqualified,
-- singular) most specifically matches `products` — the more granular
-- `product_variants` table is a plausible refinement, not a second reading
-- that changes the answer's shape, so this is not ambiguous.
Q: suggest a dashboard for me -> {"intent": "suggest_dashboard", "ambiguous": false, "ambiguity_reason": null}
Q: build me a dashboard for my courses -> {"intent": "suggest_dashboard", "ambiguous": false, "ambiguity_reason": null}
-- a request to DESIGN something, not to answer something. It never becomes SQL
-- over the data, and it is never ambiguous: choosing what to show IS the request,
-- so asking back "which dashboard?" returns the question to the person who asked
-- precisely because they did not want to decide.
Q: hi -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
Q: مرحبا -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
Q: thanks, that helps -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
Q: what can you do -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
-- a greeting, a thank-you, or a question about YOU rather than about the
-- data. There is no query to write for it and no row that would answer it,
-- so it is never ambiguous either: asking "which table did you mean by
-- hello?" is the wrong answer, and so is a table nobody asked for.
Q: create a new dataset -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
Q: save this as a report -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
Q: delete the orders table -> {"intent": "chat", "ambiguous": false, "ambiguity_reason": null}
-- a request to CREATE, SAVE, DELETE or CHANGE something. This chat answers
-- questions; it does not act. Sent through as a query it dumped a whole
-- table and called that "the dataset" -- an action the person asked for,
-- reported as done when nothing was done. `chat` lets the reply say plainly
-- where that action lives instead.
Q: hi, how many orders are there -> {"intent": "aggregate", "ambiguous": false, "ambiguity_reason": null}
-- a greeting WRAPPED AROUND a real question is the question. `chat` is for a
-- message that asks nothing about the data at all; any request for data in
-- it, however politely buried, wins.
Q: show me a sample of the data -> {"intent": "lookup", "ambiguous": false, "ambiguity_reason": null}
Q: i need to see the first 20 rows -> {"intent": "lookup", "ambiguous": false, "ambiguity_reason": null}
Q: show me -> {"intent": "lookup", "ambiguous": false, "ambiguity_reason": null}
-- a request to SEE the data itself — a sample, the first N rows — is a plain
-- SELECT of the columns with a LIMIT. It names no metric because it needs
-- none; asking "which metric?" back is the wrong answer. With one table in
-- scope it is that table; with several, the most specific match wins as
-- above.
Q: what does this data contain -> {"intent": "describe_data", "ambiguous": false, "ambiguity_reason": null}
Q: describe this dataset -> {"intent": "describe_data", "ambiguous": false, "ambiguity_reason": null}
Q: what tables are in here -> {"intent": "describe_data", "ambiguous": false, "ambiguity_reason": null}
Q: what columns do you have -> {"intent": "describe_data", "ambiguous": false, "ambiguity_reason": null}
-- asking what the data IS rather than what it SAYS: the tables in scope and
-- what each holds. It is answered from the catalog, so it is never ambiguous
-- and never small talk — it is a question about the data, and the person
-- asking it has just arrived and cannot name a table yet. "Show me a sample"
-- is different: that one wants ROWS, and stays `lookup`."""


async def classify(question: str, context: SchemaContext, client,
                   history: list[dict] | None = None) -> dict | None:
    """Returns the verdict dict, or None when the model could not be reached
    or never satisfied the contract. None means the RUN fails honestly —
    guessing an intent is exactly what D4.3 forbids.

    `history` (the conversation so far, see nodes/followup.py) is shown
    when present: the question arrives already rewritten to stand alone,
    but the turns it grew out of still settle which table it means -- a
    follow-up must not be called ambiguous for leaning on something the
    conversation already named."""
    conversation = (
        f"Conversation so far:\n{render_history(history)}\n\n" if history else "")
    messages = [
        {"role": "system", "content": (
            "You classify a business question against a database so an agent "
            "can plan a query. `ambiguous` is true ONLY when the question maps "
            "to two or more materially different queries — two plausible "
            "metrics, two date columns, an unnamed table — AND the schema "
            "context below (table descriptions, semantic types, the join "
            "graph) cannot break the tie. Near-duplicate table names alone "
            "are NOT ambiguity: when descriptions distinguish them, or one "
            "name is more specific to what was asked, the most specific "
            "matching table wins and you classify normally. Never guess "
            "between two readings that would change the answer's shape — "
            "that is still a real tie, and stays ambiguous=true. A request "
            "to see the data itself (a sample, the first N rows, what the "
            "data contains) is a lookup and is never ambiguous: it needs no "
            "metric. Return intent=`describe_data` when the message asks what "
            "the data IS rather than what it says — describe this data, what "
            "does it contain, what tables or columns are there. That is "
            "answered from the catalog and is never ambiguous. Return "
            "intent=`chat` when the message asks NOTHING "
            "about the data — a greeting, a thank-you, small talk, or a "
            "question about you or what you can do — and also when it asks "
            "you to CREATE, SAVE, DELETE or CHANGE something: this chat "
            "answers questions and takes no actions, so that is answered "
            "with where the action is done, never with a query. `chat` is never "
            "ambiguous. A message that asks for data is never `chat`, even "
            "when it opens with a greeting: the question inside it wins. "
            "Keep "
            "`ambiguity_reason` to ONE short sentence. When a 'Conversation "
            "so far' block is present the question is a follow-up in that "
            "conversation: read it with those turns, and never call it "
            "ambiguous for referring to a table, column or filter the "
            "conversation already named.\n" + _EXAMPLES)},
        {"role": "user", "content": (
            # classify only judges WHICH tables could answer the question
            # and whether the question is ambiguous between them — object
            # names plus their short descriptions settle that, and those
            # are guaranteed present at ANY render budget by the two-pass
            # render (breadth pass 1 never drops a name; only enrichment,
            # dtypes/labels, is what depth pass 2 spends leftover budget
            # on, and generate.py — not classify — is what actually needs
            # that enrichment). A small 8000-char budget here (vs. the
            # ~24000-char default) cuts roughly 4k tokens of prefill off
            # every classify call, measured across live runs.
            f"Database:\n{context.render(max_chars=8000, question=question)}\n\n"
            f"{conversation}Question: {question}")},
    ]
    # max_tokens=400, not 200 (task H6 diagnosis): a genuinely confusing
    # multi-table schema can make the model write a long, honest
    # `ambiguity_reason` before it emits the closing brace — at 200 tokens
    # that reasoning was cut off mid-string, so the response was truncated,
    # invalid JSON on every retry (deterministic at temperature=0.0, hence
    # a 100% reproducible failure, not a transient one). This was
    # reproduced live against the maps source's Arabic-symbol compare
    # question ("...اتجاه هجوم العدو...") which the H6 measurement flagged
    # as a classify-node failure; it is NOT an encoding or non-Latin-text
    # bug — an English question over an equally confusing schema hits the
    # same truncation. Verified fix: the identical prompt/context succeeds
    # reliably at max_tokens=350+; 400 keeps headroom. The one-sentence
    # instruction above is defence in depth, not the fix.
    return await client.complete_json(messages, CLASSIFY_SCHEMA,
                                      enforce=True, max_tokens=400,
                                      temperature=0.0)
