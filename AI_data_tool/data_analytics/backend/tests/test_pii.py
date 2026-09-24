"""PII detection and masking for the sample cache.

Two properties matter here, and the second one is easy to get wrong:

1. DETERMINISM — the same input always masks to the same token. Without this,
   two syncs of the same table produce different cached values and every
   downstream comparison breaks.

2. CARDINALITY PRESERVATION — distinct inputs must mask to distinct tokens.
   This is the subtle one. Stage 4 infers foreign keys by measuring value
   overlap between two columns IN THE MASKED SAMPLE. A masker that turned
   alice@corp.com and adam@corp.com both into "a****@c***.com" would collapse
   1000 customers into a handful of tokens, and the overlap ratio it computed
   would be meaningless — inference would confidently propose joins that do not
   exist. Shape-preserving masking alone is NOT enough; the token has to carry a
   per-value discriminator.

The masked form is still not reversible: the discriminator is an HMAC keyed on
the app secret, so it identifies a value without revealing it.
"""
import pytest

from app.services import pii


class TestDeterminism:
    def test_same_input_masks_identically_every_time(self):
        a = pii.mask_value("alice@corp.com", "email")
        b = pii.mask_value("alice@corp.com", "email")
        assert a == b

    def test_determinism_holds_across_types(self):
        for value, kind in [
            ("alice@corp.com", "email"),
            ("+201234567890", "phone"),
            ("192.168.1.10", "ip"),
            ("GB33BUKB20201555555555", "iban"),
        ]:
            assert pii.mask_value(value, kind) == pii.mask_value(value, kind)


class TestCardinalityPreservation:
    """The property that keeps foreign-key inference honest."""

    def test_distinct_emails_at_the_same_domain_stay_distinct(self):
        masked = {pii.mask_value(f"user{i}@corp.com", "email") for i in range(200)}
        assert len(masked) == 200, "masking collapsed distinct values into one token"

    def test_distinct_ids_stay_distinct(self):
        masked = {pii.mask_value(f"1234567890{i:03d}", "national_id") for i in range(200)}
        assert len(masked) == 200

    def test_overlap_between_two_columns_survives_masking(self):
        """The actual Stage 4 scenario: a child column whose values are a subset
        of a parent's must still look like a subset after masking."""
        parent = [f"user{i}@corp.com" for i in range(100)]
        child = parent[:60]

        mp = {pii.mask_value(v, "email") for v in parent}
        mc = {pii.mask_value(v, "email") for v in child}

        overlap = len(mc & mp) / len(mc)
        assert overlap == 1.0

    def test_non_overlapping_columns_do_not_become_overlapping(self):
        a = {pii.mask_value(f"a{i}@x.com", "email") for i in range(100)}
        b = {pii.mask_value(f"b{i}@y.com", "email") for i in range(100)}
        assert not (a & b)


class TestIrreversibility:
    def test_the_original_value_does_not_appear_in_the_token(self):
        masked = pii.mask_value("alice@corp.com", "email")
        assert "alice" not in masked
        assert "corp" not in masked

    def test_shape_is_preserved_so_the_column_still_reads_as_an_email(self):
        """The model and the review UI should still be able to tell WHAT this
        column is, which is the whole reason we mask instead of dropping it."""
        masked = pii.mask_value("alice@corp.com", "email")
        assert "@" in masked and masked.endswith(".com")


class TestDetection:
    @pytest.mark.parametrize("values,expected", [
        (["alice@corp.com", "bob@corp.com", "carol@x.org"], "email"),
        (["+201234567890", "+201111111111", "+201222222222"], "phone"),
        (["192.168.1.1", "10.0.0.5", "172.16.0.1"], "ip"),
        (["https://a.com", "http://b.org/x", "https://c.net"], "url"),
        (["GB33BUKB20201555555555", "DE89370400440532013000",
          "FR1420041010050500013M02606"], "iban"),
        (["4111111111111111", "5500005555555559",
          "4012888888881881"], "credit_card"),
    ])
    def test_detects_from_a_sample(self, values, expected):
        assert pii.detect_semantic_type(values) == expected

    def test_returns_none_for_ordinary_text(self):
        assert pii.detect_semantic_type(["red", "green", "blue"]) is None

    def test_returns_none_for_plain_numbers(self):
        assert pii.detect_semantic_type(["1", "2", "3", "42"]) is None

    def test_needs_a_majority_not_a_single_match(self):
        """One email address in a free-text notes column does not make the column
        an email column — masking it wholesale would destroy real data."""
        values = ["some note", "another note", "third note", "contact alice@corp.com"]
        assert pii.detect_semantic_type(values) is None

    def test_ignores_nulls_when_deciding(self):
        values = [None, "alice@corp.com", None, "bob@corp.com", "carol@corp.com"]
        assert pii.detect_semantic_type(values) == "email"

    def test_empty_sample_is_undetectable(self):
        assert pii.detect_semantic_type([]) is None
        assert pii.detect_semantic_type([None, None]) is None

    def test_luhn_check_rejects_a_number_that_merely_looks_like_a_card(self):
        """An order number of card length is not a card. Masking it would destroy
        a perfectly good join key."""
        assert pii.detect_semantic_type(
            ["1234567812345678", "1111111111111111", "1234567812345670"]
        ) != "credit_card"

    def test_too_few_values_to_judge_returns_none(self):
        """Two values are not evidence. Classifying a column from them risks
        masking away a real column on the strength of a coincidence, so the
        detector abstains below _MIN_SAMPLE rather than guessing."""
        assert pii.detect_semantic_type(["alice@corp.com", "bob@corp.com"]) is None
        assert pii.detect_semantic_type(["alice@corp.com"]) is None
        # One more value and the same evidence is now enough.
        assert pii.detect_semantic_type(
            ["alice@corp.com", "bob@corp.com", "carol@corp.com"]
        ) == "email"


class TestIsPii:
    def test_pii_types_are_flagged_and_others_are_not(self):
        assert pii.is_pii("email") is True
        assert pii.is_pii("phone") is True
        assert pii.is_pii("national_id") is True
        assert pii.is_pii("credit_card") is True
        assert pii.is_pii("iban") is True
        # Structural, not personal — these are useful to the model unmasked.
        assert pii.is_pii("url") is False
        assert pii.is_pii("currency") is False
        assert pii.is_pii(None) is False


class TestMaskRows:
    def test_masks_only_the_columns_flagged_as_pii(self):
        rows = [
            {"id": 1, "email": "alice@corp.com", "city": "Cairo"},
            {"id": 2, "email": "bob@corp.com", "city": "Giza"},
        ]
        out = pii.mask_rows(rows, {"email": "email", "city": None})

        assert out[0]["id"] == 1, "non-PII columns pass through untouched"
        assert out[0]["city"] == "Cairo"
        assert out[0]["email"] != "alice@corp.com"
        assert out[0]["email"] != out[1]["email"]

    def test_does_not_mutate_the_input_rows(self):
        rows = [{"email": "alice@corp.com"}]
        pii.mask_rows(rows, {"email": "email"})
        assert rows[0]["email"] == "alice@corp.com"

    def test_none_values_stay_none(self):
        """Masking a null into a token would invent a value that is not there and
        would corrupt the null_ratio statistic computed from the same sample."""
        out = pii.mask_rows([{"email": None}], {"email": "email"})
        assert out[0]["email"] is None
