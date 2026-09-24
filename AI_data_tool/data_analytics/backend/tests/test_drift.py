"""Stage 6 — schema drift.

Two behaviours carry the weight here:

  * the fingerprint must be STABLE for an unchanged schema, or every sync
    reports drift and everyone learns to ignore drift alerts;
  * a confirmed annotation whose column disappeared must be FLAGGED, never
    deleted — it is the only data in the platform a human actually typed.
"""
from app.services.metadata import drift


def cols(*specs):
    """(table, name, dtype, nullable) tuples -> column dicts."""
    return [
        {"table": t, "name": n, "dtype": d, "nullable": nul}
        for t, n, d, nul in specs
    ]


BASE = cols(
    ("orders", "id", "integer", False),
    ("orders", "customer_id", "integer", True),
    ("orders", "total", "numeric", True),
)


class TestFingerprintStability:
    def test_identical_schemas_hash_identically(self):
        assert drift.fingerprint(BASE) == drift.fingerprint(list(BASE))

    def test_column_order_does_not_affect_the_hash(self):
        """Catalog queries do not guarantee ordering. An order-sensitive hash
        would report drift at random and train everyone to ignore it."""
        assert drift.fingerprint(BASE) == drift.fingerprint(list(reversed(BASE)))

    def test_a_type_change_changes_the_hash(self):
        changed = cols(
            ("orders", "id", "integer", False),
            ("orders", "customer_id", "text", True),      # was integer
            ("orders", "total", "numeric", True),
        )
        assert drift.fingerprint(changed) != drift.fingerprint(BASE)

    def test_a_nullability_change_changes_the_hash(self):
        changed = cols(
            ("orders", "id", "integer", False),
            ("orders", "customer_id", "integer", False),  # was nullable
            ("orders", "total", "numeric", True),
        )
        assert drift.fingerprint(changed) != drift.fingerprint(BASE)

    def test_same_column_name_in_different_tables_is_distinguished(self):
        a = cols(("orders", "id", "integer", False))
        b = cols(("customers", "id", "integer", False))
        assert drift.fingerprint(a) != drift.fingerprint(b)

    def test_empty_schema_hashes_without_error(self):
        assert isinstance(drift.fingerprint([]), str)


class TestDiff:
    def test_detects_an_added_column(self):
        current = BASE + cols(("orders", "discount", "numeric", True))
        delta = drift.diff_schemas(BASE, current)
        assert [c["name"] for c in delta["added"]] == ["discount"]
        assert delta["removed"] == [] and delta["changed"] == []

    def test_detects_a_removed_column(self):
        current = BASE[:-1]
        delta = drift.diff_schemas(BASE, current)
        assert [c["name"] for c in delta["removed"]] == ["total"]

    def test_reports_what_changed_not_merely_that_it_did(self):
        """A review UI should be able to say 'dtype: integer -> text'."""
        current = cols(
            ("orders", "id", "integer", False),
            ("orders", "customer_id", "text", True),
            ("orders", "total", "numeric", True),
        )
        delta = drift.diff_schemas(BASE, current)
        assert delta["changed"][0]["name"] == "customer_id"
        assert delta["changed"][0]["changes"]["dtype"] == {"from": "integer", "to": "text"}

    def test_an_unchanged_schema_produces_an_empty_diff(self):
        delta = drift.diff_schemas(BASE, list(BASE))
        assert delta == {"added": [], "removed": [], "changed": []}


class TestOrphanedAnnotations:
    ANNOTATIONS = [
        {"table": "orders", "name": "total", "source": "confirmed",
         "kind": "column", "detail": "Gross order value including tax"},
        {"table": "orders", "name": "customer_id", "source": "inferred",
         "kind": "column", "detail": "guessed"},
    ]

    def test_a_confirmed_annotation_on_a_removed_column_is_flagged(self):
        removed = cols(("orders", "total", "numeric", True))
        got = drift.find_orphaned_annotations(removed, self.ANNOTATIONS)
        assert len(got) == 1
        assert got[0]["name"] == "total"
        assert got[0]["detail"] == "Gross order value including tax"

    def test_an_inferred_annotation_is_not_worth_flagging(self):
        """It will simply not be regenerated. Nothing was lost."""
        removed = cols(("orders", "customer_id", "integer", True))
        assert drift.find_orphaned_annotations(removed, self.ANNOTATIONS) == []

    def test_annotations_on_surviving_columns_are_untouched(self):
        assert drift.find_orphaned_annotations([], self.ANNOTATIONS) == []


class TestDetect:
    def test_no_change_returns_none(self):
        fp = drift.fingerprint(BASE)
        assert drift.detect(fp, BASE, list(BASE)) is None

    def test_first_sync_records_a_baseline(self):
        """Recorded explicitly rather than inferred from an absence later."""
        event = drift.detect(None, None, BASE)
        assert event["is_baseline"] is True
        assert len(event["added"]) == 3

    def test_a_real_change_produces_an_event(self):
        fp = drift.fingerprint(BASE)
        current = BASE[:-1]
        event = drift.detect(fp, BASE, current)
        assert event["is_baseline"] is False
        assert event["previous_fingerprint"] == fp
        assert [c["name"] for c in event["removed"]] == ["total"]

    def test_the_event_carries_the_orphaned_annotations(self):
        fp = drift.fingerprint(BASE)
        annotations = [{"table": "orders", "name": "total",
                        "source": "confirmed", "kind": "column", "detail": "x"}]
        event = drift.detect(fp, BASE, BASE[:-1], annotations)
        assert len(event["orphaned_annotations"]) == 1


class TestSummarize:
    def test_baseline_reads_as_a_first_record(self):
        event = drift.detect(None, None, BASE)
        assert "Initial schema" in drift.summarize(event)

    def test_counts_each_kind_of_change(self):
        fp = drift.fingerprint(BASE)
        current = BASE[:-1] + cols(("orders", "discount", "numeric", True))
        text = drift.summarize(drift.detect(fp, BASE, current))
        assert "1 column(s) added" in text
        assert "1 column(s) removed" in text

    def test_orphaned_annotations_are_called_out_by_consequence(self):
        """The reader needs to know their confirmed work is at risk, not merely
        that a column went missing."""
        fp = drift.fingerprint(BASE)
        annotations = [{"table": "orders", "name": "total",
                        "source": "confirmed", "kind": "column", "detail": "x"}]
        text = drift.summarize(drift.detect(fp, BASE, BASE[:-1], annotations))
        assert "confirmed annotation" in text
