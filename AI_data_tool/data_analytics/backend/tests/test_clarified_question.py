"""3.8: the reply to a clarifying question is read with the question it clarifies."""
from app.services.agent.graph import clarified_question


def _h(*turns):
    return [dict(role=r, content=c, status=s) for r, c, s in turns]


def test_reply_after_clarification_carries_the_original_question():
    hist = _h(("user", "average salary and headcount by department", None),
              ("assistant", "Do you mean current employees only, or everyone ever hired?", "needs_clarification"))
    q = clarified_question("current only", hist)
    assert q.startswith("average salary and headcount by department")
    assert "current only" in q and "every part" in q


def test_no_clarification_no_rewrite():
    hist = _h(("user", "headcount by department", None), ("assistant", "Here it is", "ok"))
    assert clarified_question("and by gender", hist) is None
    assert clarified_question("x", []) is None
    assert clarified_question("   ", hist) is None


def test_answer_numbers_are_rounded_like_a_person_writes_them():
    """HR re-test 2026-10-01: "71963.5708" reached the reader in both languages."""
    from decimal import Decimal
    from app.services.agent.nodes.explain import _tidy
    assert _tidy(71963.5708) == 71963.57
    assert _tidy(Decimal("80706.4959")) == 80706.5
    assert _tidy(0.123456) == 0.1235
    assert _tidy(2580.0) == 2580


def test_the_classifier_reads_an_arabic_value_by_its_meaning():
    from app.services.agent.nodes import classify as c
    assert "قسم المبيعات" in c._EXAMPLES
    from app.services.agent.nodes import clarify as cl
    import inspect
    assert "never invent" in inspect.getsource(cl.clarify)
