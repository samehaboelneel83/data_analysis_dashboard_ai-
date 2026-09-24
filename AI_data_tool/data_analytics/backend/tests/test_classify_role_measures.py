"""Defect 4: a decimal monetary column read as a dimension.

Found on a real upload. `tuition_fee` holds four distinct values across 240
rows, `classify_role`'s numeric branch saw low cardinality and returned
`dimension`, and the composed dashboard offered "Share of Intake by Tuition
Fee" -- slicing an intake by price band as though price were a category.

Verified before this file was written:

    classify_role('tuition_fee', 'float64', {distinct: 4, rows: 240})
      -> 'dimension'                                          (wrong)
    classify_role('star_rating', 'int64',   {distinct: 5, rows: 240})
      -> 'dimension'                                          (right)

which is what the rule has to separate. Cardinality alone cannot: both are
low. The distinguishing signals are the DTYPE (a fractional value is not a
category label -- you do not group by 8,800.50) and the NAME.

Deliberately narrow. An integer with few values stays a dimension: `year`,
`band`, `star_rating` and a 1-5 Likert are all genuinely categorical, and
reclassifying them would break every breakdown built on them.
"""
import pytest

from app.services.metadata.infer_semantic import classify_role


def _role(name, dtype, distinct, rows=240):
    return classify_role(name, dtype, {"distinct_count": distinct, "row_count": rows})


class TestTheCaseThatShipped:
    def test_tuition_fee_is_a_measure(self):
        assert _role("tuition_fee", "float64", 4) == "measure"

    def test_it_was_a_dimension_only_because_of_cardinality(self):
        """The same column with many values was always classified correctly --
        proof the defect is the cardinality shortcut, not the column."""
        assert _role("tuition_fee", "float64", 174) == "measure"


class TestMonetaryAndContinuousNames:
    @pytest.mark.parametrize("name", [
        "price", "unit_price", "amount", "total_amount", "cost", "revenue",
        "salary", "balance", "fee", "tuition_fee", "spend", "budget",
    ])
    def test_a_decimal_money_column_is_a_measure_however_few_values(self, name):
        assert _role(name, "float64", 3) == "measure"

    def test_a_decimal_with_no_telling_name_is_still_a_measure(self):
        """The dtype alone carries it: you do not group by 12.47. A fractional
        value is a quantity, whatever it is called."""
        assert _role("q4", "float64", 4) == "measure"

    def test_an_integer_money_column_is_a_measure_by_name(self):
        """Money is often stored as whole units. The name is what saves it --
        the dtype signal cannot, and this is why the rule needs both halves."""
        assert _role("revenue", "int64", 4) == "measure"


class TestGenuineCategoriesAreUntouched:
    """The boundary this rule must not cross. Each of these was verified as
    `dimension` before the change and must stay one."""

    @pytest.mark.parametrize("name,dtype,distinct", [
        ("star_rating", "int64", 5),      # a 1-5 rating IS a category to group by
        ("band", "int64", 3),
        ("year", "int64", 5),
        ("quarter", "int64", 4),
        ("floor", "int64", 8),
        ("severity", "int64", 4),
    ])
    def test_a_low_cardinality_integer_stays_a_dimension(self, name, dtype, distinct):
        assert _role(name, dtype, distinct) == "dimension"

    def test_a_text_column_is_unaffected(self):
        assert _role("faculty", "object", 4) == "dimension"

    def test_a_high_cardinality_numeric_is_still_a_measure(self):
        assert _role("final_score", "float64", 174) == "measure"


class TestTheOtherRolesStillWin:
    """Ordering matters: the new rule sits inside the numeric branch, so
    identifier and timestamp must still be decided before it."""

    def test_a_near_unique_decimal_is_an_identifier_not_a_measure(self):
        assert _role("amount", "float64", 240) == "identifier"

    def test_a_date_is_a_timestamp_whatever_its_name(self):
        assert _role("price_date", "datetime64[ns]", 4) == "timestamp"

    def test_a_named_id_is_an_identifier(self):
        assert _role("invoice_id", "int64", 240) == "identifier"
