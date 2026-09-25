"""Result snapshots (services/agent/results.py): small, JSON-safe, honest
about what was cut."""
from datetime import date, datetime
from decimal import Decimal

from app.services.agent.results import (RESULT_ROW_CAP, coerce_scalar,
                                        snapshot_rows)


class TestSnapshot:
    def test_columns_follow_first_appearance_and_rows_become_lists(self):
        snap = snapshot_rows([{"city": "Cairo", "n": 3}, {"city": "Giza", "n": 1}])
        assert snap == {"columns": ["city", "n"],
                        "rows": [["Cairo", 3], ["Giza", 1]],
                        "total": 2, "truncated": False}

    def test_a_ragged_result_still_has_one_header(self):
        snap = snapshot_rows([{"a": 1}, {"a": 2, "b": "x"}])
        assert snap["columns"] == ["a", "b"]
        assert snap["rows"] == [[1, None], [2, "x"]]

    def test_the_cap_keeps_the_true_total(self):
        rows = [{"i": i} for i in range(RESULT_ROW_CAP + 50)]
        snap = snapshot_rows(rows)
        assert len(snap["rows"]) == RESULT_ROW_CAP
        assert snap["total"] == RESULT_ROW_CAP + 50
        assert snap["truncated"] is True

    def test_an_explicit_cap_is_honoured(self):
        snap = snapshot_rows([{"i": i} for i in range(10)], cap=3)
        assert [r[0] for r in snap["rows"]] == [0, 1, 2]
        assert snap["truncated"] is True

    def test_none_stays_none_and_empty_is_empty(self):
        assert snapshot_rows(None) is None
        assert snapshot_rows([]) == {"columns": [], "rows": [], "total": 0,
                                     "truncated": False}


class TestRedaction:
    def test_credential_columns_are_masked_and_named(self):
        # Found live: "give my sample" over an application database selected
        # users.password_hash and the hashes reached the answer, the explain
        # prompt and the stored snapshot. The column survives, honestly
        # named; only its values are withheld.
        from app.services.agent.results import REDACTED, redact_credentials
        rows = [{"email": "a@b.c", "password_hash": "$2b$12$xyz", "api_key": "k1"},
                {"email": "d@e.f", "password_hash": None, "api_key": "k2"}]
        got = redact_credentials(rows)
        assert got[0] == {"email": "a@b.c", "password_hash": REDACTED,
                          "api_key": REDACTED}
        assert got[1]["password_hash"] is None      # null stays null
        assert rows[0]["password_hash"] == "$2b$12$xyz"  # input untouched

    def test_ordinary_columns_pass_through_by_identity(self):
        from app.services.agent.results import redact_credentials
        rows = [{"region": "west", "hash_total": 3, "key_account": "ACME"}]
        # Bare "hash"/"key" are legitimate analytics words; only credential
        # vocabulary triggers.
        assert redact_credentials(rows) is rows
        assert redact_credentials([]) == []
        assert redact_credentials(None) is None


class TestCells:
    def test_numbers_stay_numbers(self):
        # A chart over the snapshot needs floats; str(Decimal) would break it.
        assert coerce_scalar(Decimal("12.50")) == 12.5
        assert coerce_scalar(7) == 7
        assert coerce_scalar(True) is True

    def test_dates_become_iso_strings(self):
        assert coerce_scalar(date(2026, 9, 3)) == "2026-09-03"
        assert coerce_scalar(datetime(2026, 9, 3, 8, 30)) == "2026-09-03T08:30:00"

    def test_nan_and_inf_become_null(self):
        assert coerce_scalar(float("nan")) is None
        assert coerce_scalar(float("inf")) is None
        assert coerce_scalar(Decimal("NaN")) is None

    def test_bytes_and_unknowns_are_readable_text(self):
        assert coerce_scalar(b"\x01\x02") == "0102"

        class Odd:
            def __str__(self):
                return "odd"
        assert coerce_scalar(Odd()) == "odd"

    def test_numpy_style_scalars_unwrap(self):
        class NpLike:
            def item(self):
                return 4.25
        assert coerce_scalar(NpLike()) == 4.25
