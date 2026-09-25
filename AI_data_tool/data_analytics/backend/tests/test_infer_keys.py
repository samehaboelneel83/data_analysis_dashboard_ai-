"""Stage 4 unit behaviour — each filter in isolation.

The rule this module encodes, and which most of these tests exist to protect:
names are a PRIOR, overlap is the EVIDENCE. A column called `customer_id` that
shares no values with `customers.id` is not a foreign key, and no amount of
naming should make it one.
"""
import pytest

from app.services.metadata import infer_keys


class FakeCache:
    """A stand-in for the DuckDB sample cache.

    Overlaps are stated per pair rather than derived from rows, so each test can
    isolate one filter without constructing a database to imply it.
    """

    def __init__(self, overlaps=None, distinct=None, rows=None):
        self._overlaps = overlaps or {}
        self._distinct = distinct or {}
        self._rows = rows or {}

    def overlap(self, cds, ccol, pds, pcol):
        return self._overlaps.get((cds, ccol, pds, pcol), 0.0)

    def distinct_count(self, ds, col):
        return self._distinct.get((ds, col), 100)

    def row_count(self, ds):
        return self._rows.get(ds, 100)


ORDERS = {"dataset_id": 1, "name": "orders", "columns": [
    {"name": "id", "dtype": "integer"},
    {"name": "customer_id", "dtype": "integer"},
    {"name": "amount", "dtype": "numeric"},
]}
CUSTOMERS = {"dataset_id": 2, "name": "customers", "columns": [
    {"name": "id", "dtype": "integer"},
    {"name": "name", "dtype": "text"},
]}


class TestNameScore:
    def test_textbook_case_scores_full(self):
        assert infer_keys.name_score("orders", "customer_id", "customers", "id") == 1.0

    def test_plural_forms_are_handled(self):
        assert infer_keys.name_score("orders", "company_id", "companies", "id") == 1.0

    def test_same_key_spelled_out_on_both_sides(self):
        got = infer_keys.name_score("orders", "customer_id", "customers", "customer_id")
        assert got >= 0.9

    def test_abbreviated_stem_scores_lower_but_survives(self):
        got = infer_keys.name_score("orders", "cust_id", "customers", "id")
        assert 0.5 <= got < 1.0

    def test_identical_non_key_names_score_weakly(self):
        """`name` matching `name` across two tables is a coincidence far more
        often than a key, so it must not enter the candidate set on names
        alone."""
        assert infer_keys.name_score("orders", "name", "customers", "name") <= 0.4

    def test_unrelated_names_score_zero(self):
        assert infer_keys.name_score("orders", "amount", "customers", "id") == 0.0


class TestSingularize:
    @pytest.mark.parametrize("plural,singular", [
        ("customers", "customer"),
        ("companies", "company"),
        ("addresses", "address"),
        ("orders", "order"),
    ])
    def test_common_plurals(self, plural, singular):
        assert infer_keys.singularize(plural) == singular

    def test_already_singular_is_unchanged(self):
        assert infer_keys.singularize("customer") == "customer"

    def test_short_words_are_not_mangled(self):
        """`is` must not become `i`."""
        assert infer_keys.singularize("is") == "is"


class TestTypeCompatibility:
    def test_same_family_is_compatible(self):
        assert infer_keys.types_compatible("integer", "bigint") is True

    def test_date_and_number_are_not(self):
        assert infer_keys.types_compatible("date", "numeric") is False

    def test_number_and_text_are_allowed(self):
        """Ids arrive as VARCHAR from one source and BIGINT from another far too
        often to refuse the pair outright."""
        assert infer_keys.types_compatible("integer", "varchar") is True

    def test_unknown_types_are_treated_as_compatible(self):
        """An unrecognised dtype should cost one overlap check, not silently
        drop a real relationship."""
        assert infer_keys.types_compatible("geography", "integer") is True
        assert infer_keys.types_compatible(None, "integer") is True


class TestOverlapGate:
    def test_high_overlap_is_proposed(self):
        cache = FakeCache({(1, "customer_id", 2, "id"): 1.0})
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert len(got) == 1
        assert got[0].from_column == "customer_id"
        assert got[0].to_column == "id"

    def test_low_overlap_is_discarded_entirely(self):
        """Not stored at low confidence — discarded. An unreviewed bad
        suggestion in the model is worse than a missing one."""
        cache = FakeCache({(1, "customer_id", 2, "id"): 0.3})
        assert infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache) == []

    def test_perfect_name_cannot_rescue_zero_overlap(self):
        """The central rule of this module."""
        cache = FakeCache({})
        assert infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache) == []

    def test_mid_overlap_is_proposed_for_review(self):
        cache = FakeCache({(1, "customer_id", 2, "id"): 0.8})
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert len(got) == 1
        assert got[0].evidence["high_confidence"] is False

    def test_high_overlap_is_flagged_as_high_confidence(self):
        cache = FakeCache({(1, "customer_id", 2, "id"): 0.97})
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert got[0].evidence["high_confidence"] is True


class TestParentMustBeUnique:
    def test_a_parent_column_with_repeats_is_rejected(self):
        """Joining on a non-unique parent multiplies rows and silently corrupts
        every aggregate downstream. This is the failure mode that justifies the
        whole unforgiving floor."""
        cache = FakeCache(
            overlaps={(1, "customer_id", 2, "id"): 1.0},
            distinct={(2, "id"): 40},        # 40 distinct across 100 rows
            rows={2: 100},
        )
        assert infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache) == []

    def test_a_unique_parent_is_accepted(self):
        cache = FakeCache(
            overlaps={(1, "customer_id", 2, "id"): 1.0},
            distinct={(2, "id"): 100},
            rows={2: 100},
        )
        assert len(infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)) == 1


class TestCardinality:
    def test_repeating_child_values_are_many_to_one(self):
        cache = FakeCache(
            overlaps={(1, "customer_id", 2, "id"): 1.0},
            distinct={(1, "customer_id"): 20, (2, "id"): 100},
            rows={1: 100, 2: 100},
        )
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert got[0].cardinality == "many_to_one"

    def test_unique_child_values_are_one_to_one(self):
        cache = FakeCache(
            overlaps={(1, "customer_id", 2, "id"): 1.0},
            distinct={(1, "customer_id"): 100, (2, "id"): 100},
            rows={1: 100, 2: 100},
        )
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert got[0].cardinality == "one_to_one"


class TestConfidence:
    def test_evidence_outweighs_the_name(self):
        """Perfect overlap with no name support still scores well, because the
        values are the actual proof."""
        assert infer_keys.confidence_from(1.0, 0.0) >= 0.85

    def test_a_good_name_ranks_a_candidate_higher_at_equal_overlap(self):
        assert infer_keys.confidence_from(0.9, 1.0) > infer_keys.confidence_from(0.9, 0.3)

    def test_confidence_never_exceeds_one(self):
        assert infer_keys.confidence_from(1.0, 1.0) == 1.0

    def test_a_name_cannot_manufacture_confidence_from_nothing(self):
        assert infer_keys.confidence_from(0.0, 1.0) == 0.0


class TestStructuralRules:
    def test_self_references_are_skipped(self):
        """A manager_id pointing into the same table is a hierarchy, not a join
        path, and needs different handling."""
        employees = {"dataset_id": 1, "name": "employees", "columns": [
            {"name": "id", "dtype": "integer"},
            {"name": "manager_id", "dtype": "integer"},
        ]}
        cache = FakeCache({(1, "manager_id", 1, "id"): 1.0})
        assert infer_keys.infer_foreign_keys([employees], cache) == []

    def test_a_non_key_parent_column_is_never_a_target(self):
        cache = FakeCache({(1, "customer_id", 2, "name"): 1.0})
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert all(c.to_column != "name" for c in got)

    def test_one_child_column_yields_at_most_one_parent(self):
        """A column cannot reference two tables. When ids coincide across two
        lookup tables, the strongest wins so review asks one question."""
        other = {"dataset_id": 3, "name": "clients", "columns": [
            {"name": "id", "dtype": "integer"},
        ]}
        cache = FakeCache({
            (1, "customer_id", 2, "id"): 1.0,
            (1, "customer_id", 3, "id"): 1.0,
        })
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS, other], cache)
        assert len([c for c in got if c.from_column == "customer_id"]) == 1
        # The better-named parent wins.
        assert got[0].to_dataset_id == 2

    def test_results_are_ordered_by_confidence(self):
        cache = FakeCache({
            (1, "customer_id", 2, "id"): 1.0,
            (1, "id", 2, "id"): 0.75,
        })
        got = infer_keys.infer_foreign_keys([ORDERS, CUSTOMERS], cache)
        assert got == sorted(got, key=lambda c: c.confidence, reverse=True)

    def test_no_tables_yields_no_candidates(self):
        assert infer_keys.infer_foreign_keys([], FakeCache()) == []


class TestReciprocalProposals:
    """A pair of columns cannot reference each other.

    Where two tables share a code column, overlap is SYMMETRIC — every value
    appears on both sides — so inference scores both directions identically and
    proposes both. Seen in the running app on a real source:

        maps_states.state_level_code   -> state_symbols.state_level_code
        state_symbols.state_level_code -> maps_states.state_level_code

    listed as two separate things to confirm. Only one can be true, and asking a
    human to adjudicate a mirror is asking them to do the tool's job.
    """

    # Real column names from the source this was found on. A bare `code` would
    # be rejected earlier as a primary-key name, which is a different rule.
    FACTS = {"dataset_id": 1, "name": "maps_states",
             "columns": [{"name": "state_level_code", "dtype": "integer"}]}
    LOOKUP = {"dataset_id": 2, "name": "state_level_codes",
              "columns": [{"name": "state_level_code", "dtype": "integer"}]}

    def _mirrored(self):
        return FakeCache(
            overlaps={
                (1, "state_level_code", 2, "state_level_code"): 1.0,
                (2, "state_level_code", 1, "state_level_code"): 1.0,
            },
            distinct={(1, "state_level_code"): 6, (2, "state_level_code"): 6},
            rows={1: 100, 2: 6},
        )

    def test_only_one_direction_survives(self):
        got = infer_keys.infer_foreign_keys([self.FACTS, self.LOOKUP], self._mirrored())
        assert len(got) == 1

    def test_the_surviving_direction_points_at_the_lookup_table(self):
        """A foreign key runs from the MANY side to the ONE side. The six-row
        code table is the parent; the hundred-row fact table repeating those
        codes is the child."""
        got = infer_keys.infer_foreign_keys([self.FACTS, self.LOOKUP], self._mirrored())
        assert got[0].from_dataset_id == 1, "child should be the fact table"
        assert got[0].to_dataset_id == 2, "parent should be the lookup table"

    def test_two_distinct_edges_between_the_same_tables_both_survive(self):
        """Collapsing is per COLUMN PAIR, not per table pair. `orders` may
        legitimately reference `customers` twice."""
        # `cust_id` is matched by the abbreviated-stem rule; a prefixed name
        # like `billing_customer_id` is NOT matched by the current heuristics,
        # which is a known limit of name scoring rather than of this collapse.
        cache = FakeCache(
            overlaps={
                (1, "customer_id", 2, "id"): 1.0,
                (1, "cust_id", 2, "id"): 1.0,
            },
            distinct={(2, "id"): 100},
            rows={1: 500, 2: 100},
        )
        orders = {"dataset_id": 1, "name": "orders", "columns": [
            {"name": "customer_id", "dtype": "integer"},
            {"name": "cust_id", "dtype": "integer"},
        ]}
        customers = {"dataset_id": 2, "name": "customers",
                     "columns": [{"name": "id", "dtype": "integer"}]}

        got = infer_keys.infer_foreign_keys([orders, customers], cache)
        assert len(got) == 2
