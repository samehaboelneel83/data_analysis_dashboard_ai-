"""SQL generation — one attempt, under the enforced contract."""
from __future__ import annotations

from ..context import SchemaContext
from ...analysis.registry import render_prompt_block as render_analyses_block
from .followup import render_history

GENERATE_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
    "additionalProperties": False,
}


async def generate_sql(question: str, context: SchemaContext,
                       examples: list[dict], client, *,
                       feedback: str | None = None,
                       history: list[dict] | None = None) -> str | None:
    parts = [
        "You write ONE SQL SELECT statement answering a business question.",
        "Rules: use only the listed objects and columns; join ONLY on the "
        "listed joins; never write anything but SELECT; prefer explicit "
        "column lists over *.",
        "A request to see the data itself -- a sample, the first N rows, "
        "what the data contains -- is a SELECT of the listed columns (all of "
        "them, named explicitly, when none are asked for) with LIMIT N; "
        "use LIMIT 10 when no number is given.",
        "Never SELECT columns that hold credentials -- passwords, hashes of "
        "them, secrets, tokens, API keys -- unless the question explicitly "
        "asks for that column by name. A sample of a users table is its "
        "names, emails and dates, not its password hashes.",
        "Table choice: when several near-duplicate objects could answer the "
        "question (a base table alongside a derived, normalized, `_norm`, "
        "or versioned view of it), prefer the BASE TABLE unless the "
        "question explicitly names the derived form, or the base table "
        "lacks a column the question needs. The object descriptions state "
        "what each one actually holds — use them to decide, and always "
        "choose the most specific object that directly and completely "
        "holds the rows the question is asking about, not a table that "
        "merely happens to share related data.",
        "An object marked CANONICAL is the source of truth for what its "
        "description says it holds — prefer it over recomputing the same "
        "fact from raw tables, even over a base table.",
        "A column marked ALL NULL must never be selected, aggregated, or "
        "filtered on, even if its name matches the question — it contains "
        "no data, so derive the value another way or from a different "
        "column/table.",
        "When the question includes \"Step N returned...\" context from a "
        "parent step, your SQL must build on that step's logic — a "
        "subquery, JOIN, or reuse of its WHERE clause — never hand-copy "
        "the sampled values as SQL literals. If a parent step's result "
        "already contains the final numbers, SELECT or shape them via SQL "
        "from that same source instead of switching to a different, "
        "merely convenient column.",
        "NEVER stack different groupings into one column with UNION ALL. "
        "Measured live: asked what a sales table contained, the model wrote "
        "`SELECT region, COUNT(*) FROM t GROUP BY region UNION ALL SELECT "
        "country, COUNT(*) FROM t GROUP BY country UNION ALL ...`, and the "
        "35 rows that came back were regions AND countries AND products in "
        "one column named `region` -- charted, the axis said region and the "
        "bars were three different kinds of thing. One SELECT answers about "
        "ONE grouping; if several are genuinely wanted, put each in its own "
        "labelled column (or its own step), never one under another.",
        "When validation refuses a join as not confirmed, do not retry "
        "that join another way on repair — answer using only the "
        "permitted tables' own columns instead, degrading the answer "
        "honestly (identifiers instead of display names is a correct "
        "answer; a failed run is not).",
        "When the Glossary below maps a question phrase to a column, the "
        "glossary TERM text is the canonical STORED value — use the term "
        "verbatim in SQL predicates against that column, never the "
        "question's own spelling of it (a synonym match means the "
        "question phrased it differently; the stored data still uses the "
        "term's spelling).",
        # A4: capability discovery, not an invocation contract -- this node
        # only ever writes SQL, but telling the model that deeper analyses
        # (forecast/segment/anomaly detection) exist via their own endpoints
        # lets it mention them rather than trying to fake one in a SELECT.
        # Rendered from the SAME registry `GET /analysis/registry` serves
        # (services/analysis/registry.py), so the two can never drift apart.
        f"\n{render_analyses_block()}",
        f"\n{context.render(question=question)}",
    ]
    if examples:
        shown = "\n".join(f"Q: {e['question']}\nSQL: {e['sql']}"
                          for e in examples)
        parts.append(f"\nVerified examples from this database:\n{shown}")
    if history:
        # The question below already stands alone (nodes/followup.py
        # rewrote it); the turns are here so a follow-up that builds on an
        # earlier answer reuses that answer's tables, filters and aliases
        # instead of rediscovering them differently.
        parts.append(
            "\nConversation so far (the question below already stands alone; "
            "when it builds on an earlier answer, reuse that answer's SQL "
            "tables, filters and column choices):\n" + render_history(history))
    messages = [{"role": "system", "content": "\n".join(parts)},
                {"role": "user", "content": f"Question: {question}"}]
    if feedback:
        # D4.4: the specific error, not "try again".
        messages.append({"role": "user", "content": (
            "Your previous attempt was rejected by validation: "
            f"{feedback}. Write a corrected SELECT.")})
    got = await client.complete_json(messages, GENERATE_SCHEMA,
                                     enforce=True, max_tokens=600,
                                     temperature=0.1)
    return (got or {}).get("sql") or None
