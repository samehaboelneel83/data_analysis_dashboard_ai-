"""D4.3: ask, do not guess. This node turns the classifier's ambiguity
reason into one short question for the person; the run ends with status
`needs_clarification`, and the user's reply arrives as a fresh question."""
from __future__ import annotations


async def clarify(question: str, reason: str, client) -> str | None:
    got = await client.complete(
        [{"role": "system", "content": (
            "A user's question was ambiguous. Write ONE short clarifying "
            "question offering the concrete interpretations. No preamble.")},
         {"role": "user", "content":
            f"Question: {question}\nWhy it is ambiguous: {reason}"}],
        max_tokens=120, temperature=0.2)
    return got.strip() if got else None
