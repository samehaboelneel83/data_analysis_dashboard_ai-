"""query_examples: verified question->SQL pairs, recalled as few-shot.

Written only on a successful, sane run (graph.py) — a failed query in the
memory would teach the model its own mistakes.

Source-mode rows (data_source_id set, dataset_key NULL) and dataset-mode
rows (dataset_key set to the sorted, comma-joined dataset ids, e.g. "3,17")
are kept mutually invisible: source-mode SQL names DirectQuery objects that
may not exist in a dataset's DuckDB catalog, and vice versa. `dataset_key`
given to recall/remember switches to dataset-mode scoping (source_id is
then ignored); its absence keeps the original source-mode behaviour, now
additionally filtered to dataset_key IS NULL so dataset rows never leak in.

Task R2 (spec section 6): `recall` gains an optional `question` that, when
given, ranks a wider recency-ordered candidate pool by similarity to the
question (`retrieval.rank_documents`) rather than returning the plain
recency-ordered `limit`. Write side (`remember`) is untouched -- this is a
read-time re-ranking only.
"""
from __future__ import annotations

from sqlalchemy import select

from ...models.models import QueryExample
from ..retrieval import Document, rank_documents

#: How much wider than `limit` the recency-ordered candidate pool is when a
#: `question` is given, before it gets re-ranked down to `limit` by
#: similarity. Wide enough that a similarity-best example outside the plain
#: top-`limit` recency window still has a chance to be seen and promoted,
#: bounded so this stays a cheap, single query rather than scanning the
#: whole table.
RECALL_CANDIDATE_MULTIPLIER = 4


async def recall(db, org_id: int, source_id: int | None,
                 dataset_key: str | None = None, limit: int = 5,
                 question: str | None = None) -> list[dict]:
    fetch_limit = limit * RECALL_CANDIDATE_MULTIPLIER if question else limit
    q = (select(QueryExample)
         .where(QueryExample.org_id == org_id)
         .order_by(QueryExample.id.desc()).limit(fetch_limit))
    if dataset_key is not None:
        q = q.where(QueryExample.dataset_key == dataset_key)
    else:
        q = q.where(QueryExample.dataset_key.is_(None))
        if source_id is not None:
            q = q.where(QueryExample.data_source_id == source_id)
    rows = (await db.execute(q)).scalars().all()
    if not question or len(rows) <= 1:
        return [{"question": r.question, "sql": r.sql} for r in rows[:limit]]

    # Retrieval-rank the recency-ordered candidate pool by similarity to the
    # question. `rank_documents` never raises (retrieval.py's contract); a
    # scorer failure returns [], and an empty ranking here falls back to
    # plain recency (today's behaviour truncated to `limit`) rather than
    # breaking recall.
    by_id = {str(r.id): r for r in rows}
    docs = [Document(id=str(r.id), text=r.question) for r in rows]
    ranked = rank_documents(docs, question, limit)
    if not ranked:
        return [{"question": r.question, "sql": r.sql} for r in rows[:limit]]
    chosen = [by_id[doc_id] for doc_id, _ in ranked if doc_id in by_id]
    return [{"question": r.question, "sql": r.sql} for r in chosen]


async def remember(db, org_id: int, source_id: int | None,
                   question: str, sql: str, user_id: int | None = None,
                   dataset_key: str | None = None) -> None:
    db.add(QueryExample(org_id=org_id, data_source_id=source_id,
                        question=question, sql=sql, confirmed_by=user_id,
                        dataset_key=dataset_key))
