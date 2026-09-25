"""Preparation for analysis and modelling (2026-09-25).

Missing values, duplicates, outliers, normalization, encoding, feature
selection and extraction, balancing, train/validation/test splits, and
appending another dataset -- each a prep step, so it runs where every other
step runs: over the viewer's RLS-filtered rows, validated at save time,
replayed on every read. Values are checked, not just shapes.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.prep import (apply_prep_steps, prep_added_columns, validate_prep_steps)


def run(df, *steps, aux=None):
    validate_prep_steps(list(steps), set(df.columns),
                        {k: set(v.columns) for k, v in (aux or {}).items()})
    return apply_prep_steps(df, list(steps), aux)


class TestMissingValuesAndDuplicates:
    def test_back_fill_and_interpolate(self):
        df = pd.DataFrame({"v": [None, 2.0, None, 6.0, None]})
        assert run(df, {"kind": "fill_nulls", "column": "v", "method": "bfill"})["v"].tolist()[:4] == [2, 2, 6, 6]
        got = run(df, {"kind": "fill_nulls", "column": "v", "method": "interpolate"})["v"].tolist()
        assert got == [2.0, 2.0, 4.0, 6.0, 6.0]

    def test_dedupe_can_keep_the_last_copy_or_none(self):
        df = pd.DataFrame({"id": [1, 1, 2], "v": ["old", "new", "x"]})
        assert run(df, {"kind": "dedupe", "subset": ["id"], "keep": "last"})["v"].tolist() == ["new", "x"]
        assert run(df, {"kind": "dedupe", "subset": ["id"], "keep": "none"})["v"].tolist() == ["x"]
        with pytest.raises(ValueError):
            validate_prep_steps([{"kind": "dedupe", "keep": "middle"}], {"id"})


class TestOutliers:
    df = pd.DataFrame({"v": [10, 11, 12, 13, 14, 100], "t": list("abcdef")})

    def test_iqr_flag_remove_and_cap(self):
        flagged = run(self.df, {"kind": "outliers", "columns": ["v"], "action": "flag"})
        assert flagged["_Outlier_"].tolist() == [False] * 5 + [True]
        assert run(self.df, {"kind": "outliers", "columns": ["v"], "action": "remove"})["v"].max() == 14
        capped = run(self.df, {"kind": "outliers", "columns": ["v"], "action": "cap"})["v"]
        q1, q3 = 11.25, 13.75                           # quartiles of the six values
        assert capped.max() == pytest.approx(q3 + 1.5 * (q3 - q1))
        assert capped.tolist()[:5] == [10, 11, 12, 13, 14]

    def test_zscore_with_a_threshold(self):
        got = run(self.df, {"kind": "outliers", "columns": ["v"], "method": "zscore", "k": 2, "action": "flag",
                            "name": "odd"})
        assert got["odd"].tolist() == [False] * 5 + [True]

    def test_a_text_column_is_left_alone(self):
        got = run(self.df, {"kind": "outliers", "columns": ["t"], "action": "remove"})
        assert len(got) == 6


class TestNormalizeAndEncode:
    def test_minmax_zscore_and_log(self):
        df = pd.DataFrame({"v": [0.0, 5.0, 10.0]})
        assert run(df, {"kind": "normalize", "columns": ["v"], "method": "minmax"})["v"].tolist() == [0, 0.5, 1]
        z = run(df, {"kind": "normalize", "columns": ["v"], "method": "zscore", "suffix": "_z"})
        assert z["v"].tolist() == [0, 5, 10]            # a suffix keeps the original
        assert z["v_z"].mean() == pytest.approx(0) and z["v_z"].std(ddof=0) == pytest.approx(1)
        assert run(df, {"kind": "normalize", "columns": ["v"], "method": "log"})["v"].tolist() == \
            pytest.approx([0, np.log(6), np.log(11)])

    def test_one_hot_with_fixed_categories(self):
        df = pd.DataFrame({"region": ["N", "S", "N", None, "W"]})
        got = run(df, {"kind": "encode", "column": "region", "method": "onehot",
                       "categories": ["N", "S"], "drop_original": True})
        assert list(got.columns) == ["region_N", "region_S"]
        assert got["region_N"].tolist() == [1, 0, 1, 0, 0]   # W: a category not listed is all zeros

    def test_label_codes_follow_the_given_order(self):
        df = pd.DataFrame({"size": ["L", "S", "M", None]})
        got = run(df, {"kind": "encode", "column": "size", "method": "label", "categories": ["S", "M", "L"]})
        assert got["size_code"].tolist()[:3] == [2, 0, 1] and pd.isna(got["size_code"].iloc[3])

    def test_one_hot_needs_its_categories(self):
        with pytest.raises(ValueError, match="categories"):
            validate_prep_steps([{"kind": "encode", "column": "c", "method": "onehot"}], {"c"})


class TestFeatureExtractionAndSelection:
    def test_date_parts_are_whole_numbers_even_with_a_blank(self):
        df = pd.DataFrame({"d": ["2024-02-29", None, "2025-12-31"]})
        got = run(df, {"kind": "date_parts", "column": "d", "parts": ["year", "quarter", "weekday"]})
        assert got["d_year"].tolist()[0] == 2024 and str(got["d_year"].dtype) == "Int64"
        assert got["d_quarter"].tolist()[2] == 4
        assert got["d_weekday"].tolist()[0] == 3                 # a Thursday

    def test_feature_select_drops_empty_constant_and_correlated_columns(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4], "a2": [2, 4, 6, 8.1], "const": [7, 7, 7, 7],
                           "empty": [None, None, None, 1], "b": [4, 1, 3, 2], "keepme": [5, 5, 5, 5]})
        got = run(df, {"kind": "feature_select", "max_missing_pct": 50, "min_variance": 0,
                       "max_correlation": 0.95, "keep": ["keepme"]})
        assert list(got.columns) == ["a", "b", "keepme"]

    def test_pca_scores_are_deterministic_and_centred(self):
        rng = np.random.default_rng(0)
        x = rng.normal(size=50)
        df = pd.DataFrame({"x": x, "y": 2 * x + rng.normal(scale=0.1, size=50), "z": rng.normal(size=50)})
        a = run(df, {"kind": "pca", "columns": ["x", "y", "z"], "n": 2})
        b = run(df, {"kind": "pca", "columns": ["x", "y", "z"], "n": 2})
        assert a["PC1"].tolist() == b["PC1"].tolist()
        assert a["PC1"].mean() == pytest.approx(0, abs=1e-9)
        assert a["PC1"].var(ddof=0) > a["PC2"].var(ddof=0)       # the first carries the most

    def test_new_columns_reach_the_field_pickers_with_numeric_types(self):
        steps = [{"kind": "date_parts", "column": "d", "parts": ["month"]},
                 {"kind": "pca", "columns": ["x", "y"], "n": 1},
                 {"kind": "encode", "column": "c", "method": "onehot", "categories": ["a"]}]
        added = dict(prep_added_columns(steps, {"d": "datetime", "x": "numeric", "y": "numeric", "c": "categorical"}))
        assert added == {"PC1": "numeric", "c_a": "numeric", "d_month": "numeric"}


class TestBalancingAndSplitting:
    df = pd.DataFrame({"y": ["no"] * 8 + ["yes"] * 2 + [None], "i": range(11)})

    def test_undersample_and_oversample_are_seeded(self):
        under = run(self.df, {"kind": "balance", "column": "y", "method": "undersample", "seed": 1})
        assert under["y"].value_counts(dropna=False).to_dict() == {"no": 2, "yes": 2, None: 1}
        over = run(self.df, {"kind": "balance", "column": "y", "method": "oversample", "seed": 1})
        assert over["y"].value_counts().to_dict() == {"no": 8, "yes": 8}
        again = run(self.df, {"kind": "balance", "column": "y", "method": "undersample", "seed": 1})
        assert again["i"].tolist() == under["i"].tolist()

    def test_three_way_split_keeps_training_rows_stable(self):
        df = pd.DataFrame({"i": range(2000)})
        two = run(df, {"kind": "partition", "name": "p", "train_pct": 70})
        three = run(df, {"kind": "partition", "name": "p", "train_pct": 70, "test_pct": 15})
        shares = three["p"].value_counts(normalize=True)
        assert shares["Training"] == pytest.approx(0.70, abs=0.04)
        assert shares["Test"] == pytest.approx(0.15, abs=0.03)
        # Adding a Test share takes rows from Validation only.
        assert ((two["p"] == "Training") == (three["p"] == "Training")).all()

    def test_stratified_split_gives_a_rare_class_both_sides(self):
        df = pd.DataFrame({"y": ["common"] * 90 + ["rare"] * 10})
        got = run(df, {"kind": "partition", "name": "p", "train_pct": 70, "stratify": "y"})
        rare = got[got["y"] == "rare"]["p"].value_counts().to_dict()
        assert rare == {"Training": 7, "Validation": 3}


class TestAppend:
    def test_rows_stack_by_column_name_with_a_source_label(self):
        a = pd.DataFrame({"region": ["N"], "sales": [1]})
        b = pd.DataFrame({"region": ["S"], "sales": [2], "extra": ["x"]})
        got = run(a, {"kind": "append", "dataset_id": 7, "source_column": "source",
                      "base_label": "Cairo DB", "label": "Alex DB"}, aux={7: b})
        assert got["region"].tolist() == ["N", "S"]
        assert got["source"].tolist() == ["Cairo DB", "Alex DB"]
        assert pd.isna(got["extra"].iloc[0])

    def test_a_missing_dataset_appends_nothing(self):
        a = pd.DataFrame({"region": ["N"]})
        assert len(apply_prep_steps(a, [{"kind": "append", "dataset_id": 9}], {})) == 1


def test_balance_can_leave_the_evaluation_rows_alone():
    df = pd.DataFrame({"y": ["no"] * 6 + ["yes"] * 2 + ["no"] * 3,
                       "p": ["Training"] * 8 + ["Validation"] * 3})
    got = run(df, {"kind": "balance", "column": "y", "method": "oversample", "seed": 3,
                   "only_column": "p", "only_value": "Training"})
    train = got[got["p"] == "Training"]["y"].value_counts().to_dict()
    assert train == {"no": 6, "yes": 6}
    # Validation is exactly what it was: 3 'no' rows, none copied or dropped.
    assert got[got["p"] == "Validation"]["y"].tolist() == ["no", "no", "no"]


class TestDataQualityReport:
    """Missing values, duplicate rows, type problems, outliers and the
    author's own rules, in one report over the rows the viewer's charts use."""

    df = pd.DataFrame({
        "id": [1, 2, 2, 3, 4, 5],
        "amount": [10.0, 12.0, 12.0, -5.0, 11.0, 900.0],
        "code": ["1", "2", "2", "3", "4", "x"],          # mostly numbers, as text
        "name": [" a", "b", "b", "c", None, "e"],
        "const": ["k"] * 6,
    })

    def test_columns_duplicates_and_rules(self):
        from app.services.data_quality import quality_report
        r = quality_report(self.df, ["amount >= 0", "no_such_column > 1"])
        assert r["rows"] == 6 and r["duplicate_rows"] == 1
        assert len(r["duplicate_examples"]) == 2                     # both copies shown
        by = {c["column"]: c for c in r["column_report"]}
        assert by["name"]["missing"] == 1 and "17% missing" in by["name"]["issues"]
        assert "1 value with leading/trailing spaces" in by["name"]["issues"]
        assert "constant" in by["const"]["issues"]
        assert by["amount"]["outliers"] == 2                         # -5 and 900
        assert "mixed numbers and text" in by["code"]["issues"]      # 5 of 6 parse: 83% < 90%
        amount_rule, bad_rule = r["rules"]
        assert amount_rule["failing_rows"] == 1 and amount_rule["examples"][0]["amount"] == -5.0
        assert "error" in bad_rule                                   # reported, not raised

    async def test_the_endpoint_runs_the_rules_and_is_org_scoped(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        from app.models.models import Dataset, DatasetColumn
        path = tmp_path / "q.csv"
        pd.DataFrame({"region": ["N", "N", "S"], "salary": [1, 1, 99]}).to_csv(path, index=False)
        ds = Dataset(name="Q", filename=str(path), org_id=two_orgs["a"]["org"].id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        db_session.add_all([DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"),
                            DatasetColumn(dataset_id=ds.id, name="salary", dtype="numeric")])
        await db_session.commit()
        r = await client.post(f"/api/v1/datasets/{ds.id}/quality", json={"rules": ["salary < 50"]},
                              headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["duplicate_rows"] == 1 and r.json()["rules"][0]["failing_rows"] == 1
        assert (await client.post(f"/api/v1/datasets/{ds.id}/quality", json={},
                                  headers=auth_headers["b"])).status_code == 404
