"""M1.4 - measured precision and recall of foreign-key inference.

ARCHITECTURE.md: "M1.4 is where you discover whether the metadata model is rich
enough, and you want that finding while the schema is still cheap to change."

So this is not a unit test. It builds an eight-table e-commerce schema in a REAL
DuckDB sample cache, runs the real inference pipeline over it, and scores the
result against a stated ground truth. It prints the numbers and fails below a
floor, which makes it a regression gate on inference QUALITY rather than on
inference behaviour - the unit tests cover behaviour.

The schema deliberately contains the things that make this hard:

  * a coincidental overlap  `orders.status_code` holds 1-4, and `categories.id`
                            also holds 1-4. Every value of the child appears in
                            the parent, so overlap alone scores this a perfect
                            1.0. Only the name filter rejects it. This is the
                            single most dangerous false positive in the set,
                            because joining a fact table to a lookup on a status
                            code silently multiplies rows.

  * a dangling reference    `products.supplier_id` has no supplier table. There
                            is nothing to find, and inference must not invent a
                            parent for it.

  * a non-unique parent     `order_items.order_id` values also all appear in
                            `payments.order_id`, but payments.order_id is not
                            unique, so it is not a valid parent.

  * shared column names     `customers.name` and `employees.name` are unrelated
                            and share values. Names alone would pair them.
"""
import pytest

from app.services.metadata import cache as cache_module
from app.services.metadata import infer_keys


# -- The schema --------------------------------------------------------------

TABLES = [
    {"dataset_id": 1, "name": "customers", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "name", "dtype": "text"},
        {"name": "email", "dtype": "text"},
    ]},
    {"dataset_id": 2, "name": "orders", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "customer_id", "dtype": "integer"},
        {"name": "employee_id", "dtype": "integer"},
        {"name": "status_code", "dtype": "integer"},
        {"name": "total", "dtype": "numeric"},
    ]},
    {"dataset_id": 3, "name": "order_items", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "order_id", "dtype": "integer"},
        {"name": "product_id", "dtype": "integer"},
        {"name": "qty", "dtype": "integer"},
    ]},
    {"dataset_id": 4, "name": "products", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "category_id", "dtype": "integer"},
        {"name": "supplier_id", "dtype": "integer"},
        {"name": "price", "dtype": "numeric"},
    ]},
    {"dataset_id": 5, "name": "categories", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "label", "dtype": "text"},
    ]},
    {"dataset_id": 6, "name": "addresses", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "customer_id", "dtype": "integer"},
        {"name": "city", "dtype": "text"},
    ]},
    {"dataset_id": 7, "name": "payments", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "order_id", "dtype": "integer"},
        {"name": "amount", "dtype": "numeric"},
    ]},
    {"dataset_id": 8, "name": "employees", "columns": [
        {"name": "id", "dtype": "integer"},
        {"name": "name", "dtype": "text"},
    ]},
]

#: (child_dataset, child_column, parent_dataset, parent_column)
GROUND_TRUTH = {
    (2, "customer_id", 1, "id"),
    (2, "employee_id", 8, "id"),
    (3, "order_id", 2, "id"),
    (3, "product_id", 4, "id"),
    (4, "category_id", 5, "id"),
    (6, "customer_id", 1, "id"),
    (7, "order_id", 2, "id"),
}

NAMES = ["Ada", "Bo", "Cy", "Di", "Eve", "Fay", "Gus", "Hal", "Ivy", "Jo"]


def _seed(cache):
    """Populate the cache with rows whose VALUES encode the real relationships."""
    customers = [{"id": i, "name": NAMES[i % 10], "email": f"u{i}@x.com"}
                 for i in range(1, 101)]
    employees = [{"id": i, "name": NAMES[i % 10]} for i in range(1, 21)]
    categories = [{"id": i, "label": f"cat{i}"} for i in range(1, 5)]
    products = [{"id": i, "category_id": (i % 4) + 1,
                 "supplier_id": 900 + (i % 7), "price": 10.0 + i}
                for i in range(1, 51)]
    orders = [{"id": i, "customer_id": (i % 100) + 1,
               "employee_id": (i % 20) + 1,
               # The trap: 1-4, exactly the range of categories.id.
               "status_code": (i % 4) + 1,
               "total": 99.0 + i}
              for i in range(1, 201)]
    order_items = [{"id": i, "order_id": (i % 200) + 1,
                    "product_id": (i % 50) + 1, "qty": (i % 5) + 1}
                   for i in range(1, 501)]
    # One payment per order, but only for the first 150 orders, and NOT unique:
    # two rows share an order_id, so payments.order_id is not a valid parent.
    payments = [{"id": i, "order_id": (i % 150) + 1, "amount": 50.0 + i}
                for i in range(1, 161)]
    addresses = [{"id": i, "customer_id": (i % 100) + 1, "city": "Cairo"}
                 for i in range(1, 121)]

    for dataset_id, rows in [
        (1, customers), (2, orders), (3, order_items), (4, products),
        (5, categories), (6, addresses), (7, payments), (8, employees),
    ]:
        cache.put_sample(dataset_id, rows)


class CountingCache:
    """Wraps the real cache to add row_count, and to count overlap queries.

    The count matters: the pipeline's whole design is "cheap filters first so the
    expensive join runs rarely". If a refactor made it compare every pair, this
    is what would notice.
    """

    def __init__(self, inner, row_counts):
        self._inner = inner
        self._rows = row_counts
        self.overlap_calls = 0

    def overlap(self, *args):
        self.overlap_calls += 1
        return self._inner.overlap(*args)

    def distinct_count(self, ds, col):
        return self._inner.distinct_count(ds, col)

    def row_count(self, ds):
        return self._rows.get(ds, 0)


@pytest.fixture
def seeded(tmp_path):
    inner = cache_module.SampleCache(path=str(tmp_path / "acc.duckdb"), max_mb=64)
    _seed(inner)
    counting = CountingCache(inner, {
        1: 100, 2: 200, 3: 500, 4: 50, 5: 4, 6: 120, 7: 160, 8: 20,
    })
    yield counting
    inner.close()


def _score(found: set, truth: set):
    true_positives = found & truth
    precision = len(true_positives) / len(found) if found else 0.0
    recall = len(true_positives) / len(truth) if truth else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


class TestInferenceAccuracy:
    def test_precision_and_recall_meet_the_floor(self, seeded, capsys):
        candidates = infer_keys.infer_foreign_keys(TABLES, seeded)
        found = {(c.from_dataset_id, c.from_column, c.to_dataset_id, c.to_column)
                 for c in candidates}

        precision, recall, f1 = _score(found, GROUND_TRUTH)

        with capsys.disabled():
            print("\n  -- M1.4 foreign-key inference --")
            print(f"  precision {precision:.2%}   recall {recall:.2%}   F1 {f1:.2%}")
            print(f"  proposed {len(found)} / {len(GROUND_TRUTH)} true")
            print(f"  overlap queries: {seeded.overlap_calls}")
            for missed in sorted(GROUND_TRUTH - found):
                print(f"    MISSED {missed}")
            for wrong in sorted(found - GROUND_TRUTH):
                print(f"    FALSE+ {wrong}")

        # Precision is held to a higher bar than recall on purpose. A missing
        # join is a human adding one edge in the review UI. A WRONG join
        # silently multiplies rows and quietly corrupts every aggregate built on
        # it, with no error anywhere.
        assert precision >= 0.85, f"precision {precision:.2%} below floor"
        assert recall >= 0.70, f"recall {recall:.2%} below floor"

    def test_the_coincidental_overlap_is_rejected(self, seeded):
        """orders.status_code holds 1-4 and categories.id holds 1-4, so overlap
        alone scores this a perfect 1.0. The most dangerous false positive in
        the set, and the one the name prior exists to stop."""
        candidates = infer_keys.infer_foreign_keys(TABLES, seeded)
        assert not any(
            c.from_dataset_id == 2 and c.from_column == "status_code"
            for c in candidates
        ), "a status code was proposed as a foreign key into categories"

    def test_the_dangling_reference_invents_no_parent(self, seeded):
        """products.supplier_id has no supplier table. There is nothing to find."""
        candidates = infer_keys.infer_foreign_keys(TABLES, seeded)
        assert not any(c.from_column == "supplier_id" for c in candidates)

    def test_a_non_unique_parent_is_never_chosen(self, seeded):
        """payments.order_id repeats, so it cannot be the parent side of a key
        even though order_items.order_id values are contained in it."""
        candidates = infer_keys.infer_foreign_keys(TABLES, seeded)
        assert not any(c.to_dataset_id == 7 for c in candidates)

    def test_unrelated_shared_names_are_not_paired(self, seeded):
        """customers.name and employees.name share values and share a name."""
        candidates = infer_keys.infer_foreign_keys(TABLES, seeded)
        assert not any(c.from_column == "name" for c in candidates)

    def test_every_true_key_carries_usable_evidence(self, seeded):
        """The review UI justifies each suggestion instead of asking for blind
        trust, so evidence is part of the contract, not a debugging aid."""
        candidates = infer_keys.infer_foreign_keys(TABLES, seeded)
        for candidate in candidates:
            assert set(candidate.evidence) >= {
                "overlap", "name_score", "child_distinct", "parent_distinct"
            }
            assert 0.0 <= candidate.confidence <= 1.0

    def test_the_cheap_filters_keep_the_expensive_join_rare(self, seeded):
        """22 columns across 8 tables is 300+ cross-table column pairs. The name
        and type filters should let only a small fraction reach DuckDB."""
        infer_keys.infer_foreign_keys(TABLES, seeded)
        assert seeded.overlap_calls < 60, (
            f"{seeded.overlap_calls} overlap queries - the cheap filters "
            "are no longer doing their job"
        )
