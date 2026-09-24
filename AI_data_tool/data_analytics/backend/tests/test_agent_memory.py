"""memory.py: query_examples recall/remember (spec Task R2, section 6).

`remember` (the write side) is untouched by R2 and not re-tested here beyond
what test_agent_graph* already covers indirectly. These tests pin `recall`'s
new retrieval-ranked read path: similarity to the question beats plain
recency when a question is given, while `recall` with no question keeps its
original recency-only behaviour exactly.
"""
import pytest

from app.models.models import Organization, QueryExample
from app.services.agent import memory


@pytest.fixture
async def org(db_session):
    o = Organization(name="Acme")
    db_session.add(o)
    await db_session.flush()
    return o


class TestRecallRecencyUnchanged:
    """No `question` given: recall behaves exactly as before R2 —
    most-recent-first, capped at `limit`."""

    async def test_recall_with_no_question_returns_most_recent_first(self, db_session, org):
        for q, s in [("first question", "SELECT 1"),
                     ("second question", "SELECT 2"),
                     ("third question", "SELECT 3")]:
            db_session.add(QueryExample(org_id=org.id, question=q, sql=s))
        await db_session.commit()

        rows = await memory.recall(db_session, org.id, None, limit=2)
        assert [r["question"] for r in rows] == ["third question", "second question"]


class TestRecallSimilarityBeatsRecency:
    """Pinned scenario (spec Task R2 acceptance test): a question given to
    `recall` promotes the lexically-similar OLDER example over a lexically-
    unrelated NEWER one — recall stops being recency-only once retrieval
    ranking is wired in."""

    @pytest.fixture
    async def seeded(self, db_session, org):
        # Insertion order fixes recency: "gmv_cancelled_north" is OLDEST
        # (lowest id / least recent), the other three are progressively more
        # recent and topically unrelated to it.
        rows = [
            ("What is the total gross merchandise value across all "
             "cancelled orders in the north region?",
             "SELECT SUM(total) FROM orders WHERE status='cancelled' "
             "AND region='north'"),
            ("How many active users signed up last week?",
             "SELECT COUNT(*) FROM users WHERE signup_date >= ..."),
            ("List the top 10 products by revenue.",
             "SELECT product, SUM(revenue) FROM sales GROUP BY product "
             "ORDER BY 2 DESC LIMIT 10"),
            ("Show the average order value per customer.",
             "SELECT customer_id, AVG(total) FROM orders GROUP BY customer_id"),
        ]
        for q, s in rows:
            db_session.add(QueryExample(org_id=org.id, question=q, sql=s))
        await db_session.commit()
        return rows

    async def test_no_question_returns_the_most_recent_example(self, db_session, org, seeded):
        result = await memory.recall(db_session, org.id, None, limit=1)
        assert result[0]["question"] == seeded[-1][0]  # most recently inserted

    async def test_a_similar_question_promotes_the_older_matching_example(
        self, db_session, org, seeded,
    ):
        question = ("total gross merchandise value for cancelled orders "
                   "in the north region")
        result = await memory.recall(db_session, org.id, None, limit=1,
                                     question=question)
        # The OLDEST example wins on similarity, beating three more recent
        # but lexically unrelated examples.
        assert result[0]["question"] == seeded[0][0]


class TestRecallDegradesOnRankingFailure:
    async def test_empty_ranking_falls_back_to_recency(self, db_session, org, monkeypatch):
        for q, s in [("alpha question", "SELECT 1"),
                     ("beta question", "SELECT 2")]:
            db_session.add(QueryExample(org_id=org.id, question=q, sql=s))
        await db_session.commit()

        monkeypatch.setattr("app.services.agent.memory.rank_documents",
                            lambda *a, **k: [])
        rows = await memory.recall(db_session, org.id, None, limit=1,
                                   question="anything")
        assert rows[0]["question"] == "beta question"  # most recent, unranked fallback
