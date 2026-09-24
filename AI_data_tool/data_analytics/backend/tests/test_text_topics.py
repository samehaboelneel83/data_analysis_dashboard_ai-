"""What is this free text about? — topics from a column of comments.

The last analysis SAS has that this catalogue did not. It needs no new
dependency: scikit-learn is already here for segmentation and the decision
tree, and its NMF over TF-IDF is a better fit for short business text than LDA
over raw counts -- comments are a few dozen words, and term weighting is what
stops "the order" and "the delivery" collapsing into one topic about "the".

Three things this has to be honest about, because a topic model is unusually
easy to over-sell:

  * **A topic is a cluster of words, not a label.** "delivery late arrived
    driver" is what the model found; calling it "Logistics complaints" is the
    reader's judgement, and the result must not pretend otherwise.

  * **English stop words only.** That is what scikit-learn ships. Other
    languages still work, but their common words will dominate every topic
    unless the caller supplies a stop list -- said plainly rather than left for
    someone to discover from a topic that reads "de la el los".

  * **Sentiment is NOT included.** It needs a lexicon or a model that is not
    available here, and a naive positive/negative word list is worse than
    nothing on business text, where "not bad" and "cancelled my complaint" both
    invert.
"""
import pandas as pd
import pytest

from app.services.analysis.text_topics import TextTopicsError, text_topics

DELIVERY = ["the delivery arrived late again", "late delivery, driver lost",
            "driver was late and the delivery damaged",
            "delivery late, driver rude", "late again, delivery driver missing"]
BILLING = ["invoice charged twice this month", "billing error on my invoice",
           "charged twice, invoice wrong", "the invoice billing is incorrect",
           "billing charged me twice again"]
SUPPORT = ["support never answered the phone", "phone support unhelpful",
           "called support, phone rang out", "support phone line always busy",
           "phone support could not help"]


@pytest.fixture
def comments():
    rows = (DELIVERY * 4) + (BILLING * 4) + (SUPPORT * 4)
    return pd.DataFrame({"comment": rows,
                         "region": ["N", "S"] * (len(rows) // 2)})


class TestItFindsWhatThePeopleWroteAbout:
    def test_it_returns_the_number_of_topics_asked_for(self, comments):
        got = text_topics(comments, column="comment", topics=3)
        assert len(got["topics"]) == 3

    def test_each_topic_is_a_set_of_terms(self, comments):
        got = text_topics(comments, column="comment", topics=3)
        for topic in got["topics"]:
            assert topic["terms"]
            assert all(t["term"] and t["weight"] > 0 for t in topic["terms"])

    def test_the_three_real_subjects_are_separated(self, comments):
        """The corpus is three obvious complaints. If the model cannot keep
        delivery, billing and support apart, nothing else here matters.

        Asserted on each topic's TERM SET, not on which term leads it: TF-IDF
        ranks by discriminative power, so this corpus leads with "late",
        "twice" and "support" rather than the nouns a person would pick. Both
        are correct separations; pinning the order would pin a detail of the
        weighting rather than the result.
        """
        got = text_topics(comments, column="comment", topics=3)
        term_sets = [{t["term"] for t in topic["terms"]} for topic in got["topics"]]
        homes = {}
        for subject in ("delivery", "invoice", "phone"):
            owners = [i for i, terms in enumerate(term_sets) if subject in terms]
            assert owners, f"no topic mentions {subject}: {term_sets}"
            homes[subject] = owners[0]
        assert len(set(homes.values())) == 3, (
            f"the three subjects collapsed together: {homes} in {term_sets}")

    def test_every_document_is_counted_somewhere(self, comments):
        got = text_topics(comments, column="comment", topics=3)
        assert sum(t["documents"] for t in got["topics"]) == got["documents_used"]

    def test_each_topic_shows_real_examples(self, comments):
        # A list of words is hard to judge; the comments behind it are not.
        got = text_topics(comments, column="comment", topics=3)
        for topic in got["topics"]:
            assert topic["examples"]
            assert all(isinstance(e, str) and e for e in topic["examples"])

    def test_it_is_reproducible(self, comments):
        first = text_topics(comments, column="comment", topics=3)
        second = text_topics(comments, column="comment", topics=3)
        assert first["topics"] == second["topics"]


class TestItSaysWhatItIsNot:
    def test_a_topic_is_not_a_label(self, comments):
        got = text_topics(comments, column="comment", topics=3)
        assert any("label" in c.lower() or "name" in c.lower()
                   for c in got["caveats"])

    def test_the_language_limit_is_stated(self, comments):
        got = text_topics(comments, column="comment", topics=3)
        assert any("english" in c.lower() for c in got["caveats"])

    def test_no_sentiment_is_claimed(self, comments):
        got = text_topics(comments, column="comment", topics=3)
        assert "sentiment" not in got
        assert any("sentiment" in c.lower() for c in got["caveats"])

    def test_empty_and_short_documents_are_counted_out(self, comments):
        padded = pd.concat([comments,
                            pd.DataFrame({"comment": ["", "  ", "ok", None],
                                          "region": ["N"] * 4})])
        got = text_topics(padded, column="comment", topics=3)
        assert got["documents_skipped"] >= 4
        assert got["documents_used"] == len(comments)


class TestItRefusesRatherThanInventing:
    def test_a_missing_column(self, comments):
        with pytest.raises(TextTopicsError):
            text_topics(comments, column="nope")

    def test_a_numeric_column_is_not_text(self, comments):
        with pytest.raises(TextTopicsError) as e:
            text_topics(comments.assign(n=1), column="n")
        assert "text" in str(e.value).lower()

    def test_too_few_documents(self):
        with pytest.raises(TextTopicsError):
            text_topics(pd.DataFrame({"c": DELIVERY}), column="c", topics=3)

    def test_more_topics_than_the_text_can_support(self, comments):
        # Asking for 50 topics from 60 short comments is asking for noise.
        with pytest.raises(TextTopicsError):
            text_topics(comments, column="comment", topics=50)

    def test_a_column_with_no_vocabulary_left(self):
        """Every document is stop words. There is nothing to cluster, and
        saying so beats returning three topics about "the"."""
        df = pd.DataFrame({"c": ["the and of", "and the of", "of and the"] * 20})
        with pytest.raises(TextTopicsError) as e:
            text_topics(df, column="c", topics=2)
        assert "vocabulary" in str(e.value).lower() or "words" in str(e.value).lower()


class TestCallerSuppliedStopWords:
    def test_extra_stop_words_are_honoured(self, comments):
        """The escape hatch for the language limit: a caller working in another
        language, or with a domain word that swamps everything, can say so."""
        got = text_topics(comments, column="comment", topics=3,
                          stop_words=["delivery", "driver"])
        for topic in got["topics"]:
            assert all(t["term"] not in ("delivery", "driver") for t in topic["terms"])


class TestItIsInTheCatalogue:
    def test_registered_and_runnable(self):
        from app.services.analysis.registry import get
        spec = get("text_topics")
        assert spec is not None
        assert spec.to_dict()["runnable"] is True

    def test_the_dispatcher_runs_it(self, comments):
        from app.services.analysis.registry import run_analysis
        got = run_analysis("text_topics", comments,
                           {"column": "comment", "topics": 3})
        assert len(got["topics"]) == 3
