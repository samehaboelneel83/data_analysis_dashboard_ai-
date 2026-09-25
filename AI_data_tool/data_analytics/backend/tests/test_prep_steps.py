"""Step-based prep pipeline: cleansing steps, ordering, validation, fail-soft."""
import numpy as np
import pandas as pd
import pytest

from app.services.prep import apply_prep_steps, validate_prep_steps


def messy():
    return pd.DataFrame({
        "region": ["  US ", "US", "ca", None, "MX"],
        "amount": [10.0, 10.0, None, 5.0, 50.0],
        "code": ["A-1", "A-1", "B-2", "C-3", "D-4"],
    })


# ── individual steps ──────────────────────────────────────────────────────────

def test_trim_then_case_then_dedupe_compose_in_order():
    # "  US " only equals "US" after trimming; "ca"->"CA" only after casing.
    out = apply_prep_steps(messy(), [
        {"kind": "trim"},
        {"kind": "case", "column": "region", "to": "upper"},
        {"kind": "drop_duplicates", "subset": ["region", "amount"]},
    ])
    assert list(out["region"].dropna()) == ["US", "CA", "MX"]


def test_fill_nulls_with_mean_and_value():
    out = apply_prep_steps(messy(), [{"kind": "fill_nulls", "column": "amount", "method": "mean"}])
    assert out["amount"].isna().sum() == 0
    assert out["amount"].iloc[2] == pytest.approx((10 + 10 + 5 + 50) / 4)
    out2 = apply_prep_steps(messy(), [{"kind": "fill_nulls", "column": "region", "method": "value", "value": "Unknown"}])
    assert out2["region"].iloc[3] == "Unknown"


def test_numeric_fill_value_keeps_the_column_numeric():
    out = apply_prep_steps(messy(), [{"kind": "fill_nulls", "column": "amount", "method": "value", "value": "0"}])
    assert pd.api.types.is_numeric_dtype(out["amount"])
    assert out["amount"].iloc[2] == 0.0


def test_drop_nulls_subset():
    out = apply_prep_steps(messy(), [{"kind": "drop_nulls", "columns": ["region"]}])
    assert len(out) == 4 and out["region"].isna().sum() == 0


def test_replace_exact_and_contains():
    exact = apply_prep_steps(messy(), [{"kind": "replace", "column": "code", "find": "A-1", "replace": "ALPHA"}])
    assert list(exact["code"])[:2] == ["ALPHA", "ALPHA"]
    # contains is a LITERAL substring, never a regex: '-' stays '-'
    sub = apply_prep_steps(messy(), [{"kind": "replace", "column": "code", "find": "-", "replace": "/", "match": "contains"}])
    assert list(sub["code"]) == ["A/1", "A/1", "B/2", "C/3", "D/4"]


def test_rename_then_downstream_step_sees_the_new_name():
    out = apply_prep_steps(messy(), [
        {"kind": "rename", "column": "amount", "to": "revenue"},
        {"kind": "fill_nulls", "column": "revenue", "method": "zero"},
    ])
    assert "amount" not in out.columns and out["revenue"].isna().sum() == 0


def test_retype_coerces_bad_values_to_nan_not_error():
    df = pd.DataFrame({"x": ["1", "2", "oops"]})
    out = apply_prep_steps(df, [{"kind": "retype", "column": "x", "to": "numeric"}])
    assert out["x"].iloc[1] == 2.0 and np.isnan(out["x"].iloc[2])


def test_split_produces_trimmed_parts():
    out = apply_prep_steps(messy(), [{"kind": "split", "column": "code", "delimiter": "-", "into": ["letter", "num"]}])
    assert list(out["letter"]) == ["A", "A", "B", "C", "D"]
    assert list(out["num"]) == ["1", "1", "2", "3", "4"]
    assert "code" in out.columns  # split adds, never destroys the source


def test_filter_rows_uses_the_expression_engine():
    out = apply_prep_steps(messy(), [{"kind": "filter_rows", "expression": "`amount` > 7"}])
    assert list(out["amount"]) == [10.0, 10.0, 50.0]


def test_remove_columns():
    out = apply_prep_steps(messy(), [{"kind": "remove_columns", "columns": ["code"]}])
    assert list(out.columns) == ["region", "amount"]


def test_sort_single_and_multi_column():
    df = pd.DataFrame({"region": ["US", "US", "CA"], "amount": [2.0, 1.0, 3.0]})
    out = apply_prep_steps(df, [{"kind": "sort", "columns": [{"column": "amount", "dir": "asc"}]}])
    assert list(out["amount"]) == [1.0, 2.0, 3.0]
    out_desc = apply_prep_steps(df, [{"kind": "sort", "columns": [{"column": "amount", "dir": "desc"}]}])
    assert list(out_desc["amount"]) == [3.0, 2.0, 1.0]
    # multi-column: region asc, amount desc within region
    out_multi = apply_prep_steps(df, [{"kind": "sort", "columns": [
        {"column": "region", "dir": "asc"}, {"column": "amount", "dir": "desc"}]}])
    assert list(zip(out_multi["region"], out_multi["amount"])) == [("CA", 3.0), ("US", 2.0), ("US", 1.0)]


def test_dedupe_subset_keeps_first():
    df = pd.DataFrame({"region": ["US", "US", "CA"], "amount": [1.0, 2.0, 3.0]})
    out = apply_prep_steps(df, [{"kind": "dedupe", "subset": ["region"]}])
    assert list(out["region"]) == ["US", "CA"]
    assert list(out["amount"]) == [1.0, 3.0]  # first occurrence kept
    out_all = apply_prep_steps(pd.DataFrame({"a": [1, 1, 2]}), [{"kind": "dedupe"}])
    assert list(out_all["a"]) == [1, 2]


def test_sort_and_dedupe_validate():
    validate_prep_steps([{"kind": "sort", "columns": [{"column": "amount", "dir": "desc"}]}], {"amount"})
    with pytest.raises(ValueError, match="sort dir must be one of"):
        validate_prep_steps([{"kind": "sort", "columns": [{"column": "amount", "dir": "sideways"}]}], {"amount"})
    with pytest.raises(ValueError, match="does not exist"):
        validate_prep_steps([{"kind": "dedupe", "subset": ["missing"]}], {"amount"})


def test_disabled_step_is_skipped_but_still_validates():
    # "disabled" is a first-class, persisted pause -- validation runs the same
    # kind-specific checks (a disabled step with a bad column is still refused),
    # but apply skips it entirely: the frame is as if the step were absent.
    validate_prep_steps([{"kind": "case", "column": "region", "to": "upper", "disabled": True}],
                        {"region"})
    with pytest.raises(ValueError, match="to must be one of"):
        validate_prep_steps([{"kind": "case", "column": "region", "to": "bogus", "disabled": True}],
                            {"region"})

    out = apply_prep_steps(messy(), [
        {"kind": "case", "column": "region", "to": "upper", "disabled": True},
    ])
    assert list(out["region"]) == list(messy()["region"])  # untouched, step was paused


def test_disabled_step_does_not_block_downstream_steps():
    out = apply_prep_steps(messy(), [
        {"kind": "trim", "disabled": True},
        {"kind": "case", "column": "region", "to": "upper"},
    ])
    # trim was skipped, so the untrimmed "  US " keeps its surrounding spaces
    # (proving the disabled step contributed nothing), while the enabled case
    # step right after it still ran on every row.
    assert out["region"].iloc[0] == messy()["region"].iloc[0]  # untouched by the skipped trim
    assert out["region"].iloc[2] == "CA"  # the enabled case step still ran


def test_old_pipelines_without_the_disabled_field_apply_unchanged():
    out = apply_prep_steps(messy(), [{"kind": "trim"}, {"kind": "case", "column": "region", "to": "upper"}])
    assert list(out["region"].dropna())[:2] == ["US", "US"]


def test_sort_on_vanished_column_degrades_to_noop():
    out = apply_prep_steps(messy(), [{"kind": "sort", "columns": [{"column": "gone", "dir": "asc"}]}])
    assert len(out) == 5


def test_aggregate_pre_summarises():
    df = pd.DataFrame({"region": ["US", "US", "CA"], "amount": [1.0, 2.0, 3.0]})
    out = apply_prep_steps(df, [{"kind": "aggregate", "group_by": ["region"],
                                 "aggregations": [{"column": "amount", "agg": "sum", "as": "total"}]}])
    assert {r["region"]: r["total"] for r in out.to_dict("records")} == {"US": 3.0, "CA": 3.0}
    assert list(out.columns) == ["region", "total"]


# ── failure model ─────────────────────────────────────────────────────────────

def test_step_on_a_vanished_column_degrades_to_a_noop():
    # Re-upload dropped a column: the one step degrades, the frame survives.
    out = apply_prep_steps(messy(), [
        {"kind": "fill_nulls", "column": "deleted_col", "method": "zero"},
        {"kind": "drop_nulls", "columns": ["region"]},
    ])
    assert len(out) == 4


def test_validation_checks_names_against_the_evolving_pipeline():
    cols = {"region", "amount"}
    # rename then use the NEW name: valid
    validate_prep_steps([
        {"kind": "rename", "column": "amount", "to": "revenue"},
        {"kind": "fill_nulls", "column": "revenue", "method": "zero"},
    ], cols)
    # use the OLD name after renaming it away: refused
    with pytest.raises(ValueError, match="does not exist at this point"):
        validate_prep_steps([
            {"kind": "rename", "column": "amount", "to": "revenue"},
            {"kind": "fill_nulls", "column": "amount", "method": "zero"},
        ], cols)


def test_validation_refuses_unknown_kind_and_bad_params():
    with pytest.raises(ValueError, match="unknown kind"):
        validate_prep_steps([{"kind": "explode"}], {"a"})
    with pytest.raises(ValueError, match="method"):
        validate_prep_steps([{"kind": "fill_nulls", "column": "a", "method": "wish"}], {"a"})
    with pytest.raises(ValueError, match="cannot remove every column"):
        validate_prep_steps([{"kind": "remove_columns", "columns": ["a"]}], {"a"})


def test_aggregate_validation_rewrites_the_column_set():
    # After aggregate, only group_by + outputs exist for downstream steps.
    with pytest.raises(ValueError, match="does not exist"):
        validate_prep_steps([
            {"kind": "aggregate", "group_by": ["region"],
             "aggregations": [{"column": "amount", "agg": "sum", "as": "total"}]},
            {"kind": "fill_nulls", "column": "amount", "method": "zero"},
        ], {"region", "amount"})


# ── in-place cell editing, recorded as a step ─────────────────────────────────
#
# SAS edits the source table. This edits the PIPELINE: a typed correction is
# stored as a step and replayed on every load, so the source file is never
# mutated, the change is visible in the prep list, and it survives a re-upload
# of the same data. The trade is stated in the docstring rather than hidden:
# an edit is addressed by a key VALUE, not a row number, because row numbers
# do not survive a re-upload and a correction that silently lands on a
# different row is worse than one that lands on none.

def orders():
    return pd.DataFrame({
        "order_id": ["A-1", "A-2", "A-3", "A-4"],
        "region": ["Nrth", "South", "East", "Nrth"],
        "amount": [10.0, 20.0, 30.0, 40.0],
    })


def test_an_edit_changes_the_cell_it_names():
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "region",
         "edits": [{"key": "A-2", "value": "Southern"}]}])
    assert list(out["region"]) == ["Nrth", "Southern", "East", "Nrth"]


def test_several_edits_in_one_step():
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "region",
         "edits": [{"key": "A-1", "value": "North"}, {"key": "A-4", "value": "North"}]}])
    assert list(out["region"]) == ["North", "South", "East", "North"]


def test_an_edit_is_addressed_by_key_not_by_position():
    """The whole reason this is a step and not a row write: reorder the rows,
    re-run the pipeline, and the correction still lands on the same order."""
    shuffled = orders().iloc[::-1].reset_index(drop=True)
    out = apply_prep_steps(shuffled, [
        {"kind": "edit_cells", "key_column": "order_id", "column": "region",
         "edits": [{"key": "A-2", "value": "Southern"}]}])
    assert out.loc[out["order_id"] == "A-2", "region"].iloc[0] == "Southern"
    assert set(out.loc[out["order_id"] != "A-2", "region"]) == {"Nrth", "East"}


def test_every_row_sharing_the_key_is_edited():
    # A non-unique key edits all of its rows. Stated rather than guessed at:
    # editing only the first would depend on an order the data does not have.
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "region", "column": "amount",
         "edits": [{"key": "Nrth", "value": 99}]}])
    assert list(out["amount"]) == [99.0, 20.0, 30.0, 99.0]


def test_a_numeric_column_stays_numeric():
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "amount",
         "edits": [{"key": "A-1", "value": "15"}]}])
    assert pd.api.types.is_numeric_dtype(out["amount"])
    assert out["amount"].iloc[0] == 15.0


def test_an_unparseable_edit_does_not_corrupt_the_other_rows():
    """Typing "n/a" into a numeric column is a real thing a person does. The
    column widens to text rather than turning every other value into NaN."""
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "amount",
         "edits": [{"key": "A-1", "value": "n/a"}]}])
    assert str(out["amount"].iloc[0]) == "n/a"
    assert float(out["amount"].iloc[1]) == 20.0


def test_an_edit_can_clear_a_cell():
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "region",
         "edits": [{"key": "A-2", "value": None}]}])
    assert out["region"].isna().iloc[1]


def test_a_key_that_matches_nothing_is_a_no_op():
    # A re-upload that dropped the row: the pipeline must not sink for it.
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "region",
         "edits": [{"key": "GONE", "value": "North"}]}])
    pd.testing.assert_frame_equal(out, orders())


def test_a_vanished_column_is_a_no_op():
    out = apply_prep_steps(orders(), [
        {"kind": "edit_cells", "key_column": "order_id", "column": "nope",
         "edits": [{"key": "A-1", "value": "x"}]}])
    pd.testing.assert_frame_equal(out, orders())


def test_edits_compose_with_the_steps_around_them():
    out = apply_prep_steps(orders(), [
        {"kind": "rename", "column": "region", "to": "area"},
        {"kind": "edit_cells", "key_column": "order_id", "column": "area",
         "edits": [{"key": "A-1", "value": "North"}]},
        {"kind": "case", "column": "area", "to": "upper"},
    ])
    assert list(out["area"]) == ["NORTH", "SOUTH", "EAST", "NRTH"]


class TestEditValidation:
    def test_the_columns_must_exist(self):
        with pytest.raises(ValueError):
            validate_prep_steps([{"kind": "edit_cells", "key_column": "nope",
                                  "column": "region",
                                  "edits": [{"key": "A-1", "value": "x"}]}],
                                {"order_id", "region"})

    def test_editing_the_key_column_is_refused(self):
        # The key is how the edit finds its row; changing it inside the same
        # step makes the step's own behaviour depend on evaluation order.
        with pytest.raises(ValueError) as e:
            validate_prep_steps([{"kind": "edit_cells", "key_column": "order_id",
                                  "column": "order_id",
                                  "edits": [{"key": "A-1", "value": "B-1"}]}],
                                {"order_id", "region"})
        assert "key" in str(e.value).lower()

    def test_an_empty_edit_list_is_refused(self):
        with pytest.raises(ValueError):
            validate_prep_steps([{"kind": "edit_cells", "key_column": "order_id",
                                  "column": "region", "edits": []}],
                                {"order_id", "region"})

    def test_an_edit_needs_a_key(self):
        with pytest.raises(ValueError):
            validate_prep_steps([{"kind": "edit_cells", "key_column": "order_id",
                                  "column": "region", "edits": [{"value": "x"}]}],
                                {"order_id", "region"})

    def test_a_reasonable_number_of_edits_per_step(self):
        """A step is a correction, not a data load. Past this the user wants a
        join or a fixed source, and 10,000 edits in a JSON column is a way to
        make every widget on the dataset slow."""
        from app.services.prep import MAX_CELL_EDITS
        edits = [{"key": f"A-{i}", "value": i} for i in range(MAX_CELL_EDITS + 1)]
        with pytest.raises(ValueError):
            validate_prep_steps([{"kind": "edit_cells", "key_column": "order_id",
                                  "column": "region", "edits": edits}],
                                {"order_id", "region"})

    def test_a_valid_step_passes(self):
        validate_prep_steps([{"kind": "edit_cells", "key_column": "order_id",
                              "column": "region",
                              "edits": [{"key": "A-1", "value": "North"}]}],
                            {"order_id", "region"})
