"""A date column should be labelled a date, not merely not-mislabelled.

Half of this was fixed earlier: an epoch integer is no longer called a
`national_id`, so it is no longer masked before the model sees it. But the result
was that thirty date columns came back typed as **nothing at all** — the catalog
knew what they were not, and nothing about what they were.

That matters in three places. The review screen shows a blank type for every date
in the database. The agent's schema context describes them as plain integers. And
`load_data_range`, which stops the dashboard designer proposing "today" on a
database whose newest row is three months old, has to guess from column NAMES
which columns hold instants.

So: a positive type. `timestamp` is not personal data — it is deliberately outside
`_PII_TYPES`, because masking a date is what caused the original damage.
"""
import pytest

from app.services import pii


class TestDetection:
    def test_a_column_of_epoch_seconds_is_a_timestamp(self):
        values = ["1771106400", "1707948000", "1726347600", "1739570400"]
        assert pii.detect_semantic_type(values) == "timestamp"

    def test_a_column_of_epoch_milliseconds_is_a_timestamp(self):
        values = ["1771106400000", "1707948000000", "1726347600000"]
        assert pii.detect_semantic_type(values) == "timestamp"

    def test_an_iso_date_column_is_a_timestamp(self):
        values = ["2026-02-14", "2024-09-14", "2025-02-14"]
        assert pii.detect_semantic_type(values) == "timestamp"

    def test_an_iso_datetime_column_is_a_timestamp(self):
        # Three values, not two: `detect_semantic_type` refuses a sample smaller
        # than `_MIN_SAMPLE` rather than guessing from one or two rows.
        values = ["2026-02-14 22:00:00", "2024-09-14T21:00:00Z",
                  "2025-02-14 08:30:00"]
        assert pii.detect_semantic_type(values) == "timestamp"


class TestItDoesNotEatOtherThings:
    def test_a_real_national_id_is_still_a_national_id(self):
        """The masking must not get weaker. Egyptian IDs are 14 digits, far
        outside the epoch window."""
        values = ["29801011234567", "28502021234568", "27703031234569"]
        assert pii.detect_semantic_type(values) == "national_id"

    def test_an_email_is_still_an_email(self):
        values = ["a@x.com", "b@y.org", "c@z.net"]
        assert pii.detect_semantic_type(values) == "email"

    def test_a_plain_measure_is_still_nothing(self):
        assert pii.detect_semantic_type(["39.65", "88.0", "45.09"]) is None

    def test_a_year_is_not_a_timestamp(self):
        """Four digits is a year or a count, not an instant."""
        assert pii.detect_semantic_type(["2024", "2025", "2026"]) is None


class TestItIsNotPersonalData:
    def test_a_timestamp_is_never_masked(self):
        """The whole reason this type exists. Masking dates is what poisoned the
        model's view of the database in the first place."""
        assert "timestamp" not in pii._PII_TYPES

    def test_masking_leaves_a_timestamp_alone(self):
        rows = [{"startdate": "1771106400", "email": "a@x.com"}]
        masked = pii.mask_rows(rows, {"startdate": "timestamp", "email": "email"})
        assert masked[0]["startdate"] == "1771106400"
        assert masked[0]["email"] != "a@x.com"


def test_the_data_range_reader_accepts_the_new_type():
    """`load_data_range` decides which columns hold instants. It guessed from the
    column NAME because nothing told it; now the type can."""
    from app.services.suggest_dashboard import _as_date
    assert _as_date("1771106400") == "2026-02-14"
    assert _as_date("2026-02-14") == "2026-02-14"
    assert _as_date("39.65") is None
