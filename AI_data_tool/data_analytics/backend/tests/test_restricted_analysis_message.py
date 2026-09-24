"""What a restricted viewer is told when an analysis cannot run.

Found by opening a dataset as a student whose row rule narrows it to their own
record. The page showed three red failures:

    need at least 30 rows with a value for 'final_grade' to find influencers;
    this has 1
    rule mining needs at least two categorical columns; this dataset has none
    Not enough complete rows to segment (need at least 20 rows with values in
    every selected column, found 1)

Every one of those is row-level security working exactly as designed. The engine
was right to refuse — one row is not a sample. But the product presented correct
behaviour as three errors, and a student reasonably concludes the data is broken.

It also leaks. "this has 1" and "need at least 30" together tell a viewer both
the size of their slice and that a larger population exists behind it. The rules
hide rows; the error message should not describe them.

So: when the asker's view IS restricted, the shortfall is explained as a limit of
their access, with no counts. When it is not restricted, the original message —
which is genuinely useful to an author — is untouched.
"""
import pytest

from app.services.analysis.restricted import explain_shortfall

ORIGINAL = ("need at least 30 rows with a value for 'final_grade' to find "
            "influencers; this has 1")


class TestARestrictedViewer:
    def test_the_message_is_replaced(self):
        out = explain_shortfall(ORIGINAL, restricted=True)
        assert out != ORIGINAL

    def test_it_names_access_as_the_reason_not_the_data(self):
        out = explain_shortfall(ORIGINAL, restricted=True).lower()
        assert "access" in out

    def test_it_reveals_no_counts(self):
        """The leak. Neither the size of the slice nor the threshold survives."""
        out = explain_shortfall(ORIGINAL, restricted=True)
        assert not any(ch.isdigit() for ch in out), out

    def test_it_does_not_blame_the_data(self):
        out = explain_shortfall(ORIGINAL, restricted=True).lower()
        for blame in ("this dataset has", "not enough", "too few"):
            assert blame not in out


class TestAnUnrestrictedViewer:
    def test_the_original_message_is_kept(self):
        """An author with full access needs the real numbers — "you need 30 rows
        and have 12" is exactly the sentence that tells them what to do next."""
        assert explain_shortfall(ORIGINAL, restricted=False) == ORIGINAL

    def test_an_empty_message_is_left_alone(self):
        assert explain_shortfall("", restricted=False) == ""


@pytest.mark.parametrize("message", [
    "rule mining needs at least two categorical columns; this dataset has none",
    "Not enough complete rows to segment (need at least 20 rows with values in "
    "every selected column, found 1)",
    "Only 1 complete rows; need at least 12",
])
def test_every_shortfall_message_is_covered(message):
    """All three the student actually saw, plus the inferential one, go through
    the same door — one wording, not four."""
    out = explain_shortfall(message, restricted=True)
    assert not any(ch.isdigit() for ch in out)
    assert "access" in out.lower()
