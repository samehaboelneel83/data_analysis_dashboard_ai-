"""The one-click chart suggestions must not sum an identifier.

`suggest_widgets_from_findings` turns a finding into a chart by taking the first
numeric column the finding names and summing it. An id column is numeric, so a
finding about `encounter_id` produced "sum of encounter_id by department" — a
total of identity numbers, which has no meaning at all.

Two places surface these: the Insights panel's one-click "add this chart", and
the no-model dashboard suggestion. On a hospital dataset three of eight
suggestions were this exact mistake, and the newer path rejected them at its own
gate; the older one has been offering them to users unchallenged.

Counting the same column is the useful question ("how many encounters"), so the
aggregation is corrected rather than the chart dropped.
"""
from app.services.insights import suggest_widgets_from_findings

ROLES = {"department": "categorical", "encounter_id": "numeric",
         "wait_minutes": "numeric", "arrived_at": "datetime"}


def finding(kind, columns, title="something stands out"):
    return {"kind": kind, "columns": columns, "title": title, "score": 1.0}


def only(suggestions, wt):
    return [s for s in suggestions if s["widget_type"] == wt]


class TestAnIdentifierIsCounted:
    def test_a_bar_over_an_identifier_counts_it(self):
        got = suggest_widgets_from_findings(
            [finding("standout", ["department", "encounter_id"])], ROLES)
        assert only(got, "bar")[0]["config"]["aggregation"] == "count"

    def test_a_trend_over_an_identifier_counts_it(self):
        got = suggest_widgets_from_findings(
            [finding("trend", ["arrived_at", "encounter_id"])], ROLES)
        assert only(got, "line")[0]["config"]["aggregation"] == "count"

    def test_the_measure_itself_is_kept(self):
        """Counting `encounter_id` is counting encounters -- the column still
        names what is being counted."""
        got = suggest_widgets_from_findings(
            [finding("standout", ["department", "encounter_id"])], ROLES)
        assert only(got, "bar")[0]["config"]["measure"] == "encounter_id"


class TestARealMeasureIsUnchanged:
    def test_a_bar_still_sums_a_real_measure(self):
        got = suggest_widgets_from_findings(
            [finding("standout", ["department", "wait_minutes"])], ROLES)
        assert only(got, "bar")[0]["config"]["aggregation"] == "sum"

    def test_a_trend_still_sums_a_real_measure(self):
        got = suggest_widgets_from_findings(
            [finding("trend", ["arrived_at", "wait_minutes"])], ROLES)
        assert only(got, "line")[0]["config"]["aggregation"] == "sum"

    def test_a_scatter_of_two_real_measures_still_averages(self):
        got = suggest_widgets_from_findings(
            [finding("correlation", ["wait_minutes", "encounter_id"])], ROLES)
        # x is a real measure here; the y is the identifier, and averaging
        # identity numbers is the same mistake on the other axis.
        assert only(got, "scatter") == [] or \
            only(got, "scatter")[0]["config"]["measure"] != "encounter_id"

    def test_suggestions_are_still_produced(self):
        got = suggest_widgets_from_findings(
            [finding("standout", ["department", "wait_minutes"]),
             finding("trend", ["arrived_at", "wait_minutes"])], ROLES)
        assert len(got) == 2


# ── effective_roles speaks the identifier vocabulary ─────────────────────────
#
# The missing link. Step 2 of the automation chain writes classify_roles
# answer into Dataset.column_meta using the metadata planes vocabulary
# (identifier / dimension / measure / timestamp). effective_roles spoke the
# Fields-pane vocabulary (category / measure / hidden) and mapped everything
# else to the DETECTED type -- so a column recorded as an identifier came back
# out as numeric, and every consumer went on treating it as a measure. The
# value was written and ignored.
#
# identifier is an explicit OUTCOME rather than a reason to drop the column.
# A column missing from the role map reads as unknown, not as an identifier,
# and each consumer would then invent its own meaning for absence -- which is
# the distributed-inference problem this whole change removes.

from app.services.insights import effective_roles


class TestEffectiveRolesCarriesIdentifierThrough:
    def test_an_authored_identifier_comes_out_as_identifier(self):
        got = effective_roles(
            {"student_id": "numeric"},
            {"student_id": {"role": "identifier", "role_source": "inferred"}})
        assert got["student_id"] == "identifier"

    def test_the_column_is_still_present_in_the_map(self):
        """Dropping it would be indistinguishable from never having seen it."""
        got = effective_roles(
            {"student_id": "numeric", "score": "numeric"},
            {"student_id": {"role": "identifier"}})
        assert set(got) == {"student_id", "score"}

    def test_the_detected_type_does_not_win_over_the_recorded_role(self):
        """student_id is numeric by dtype. That is precisely the case where
        detection is wrong and the recorded role is right."""
        got = effective_roles({"student_id": "numeric"},
                              {"student_id": {"role": "identifier"}})
        assert got["student_id"] != "numeric"

    def test_the_fields_pane_vocabulary_is_unchanged(self):
        got = effective_roles(
            {"a": "numeric", "b": "categorical", "c": "numeric"},
            {"a": {"role": "category"}, "b": {"role": "measure"}})
        assert got == {"a": "categorical", "b": "numeric", "c": "numeric"}

    def test_the_metadata_planes_own_words_are_understood_too(self):
        """classify_role emits dimension/timestamp alongside identifier, and
        step 2 writes whatever it emits. These aliases only EARN anything when
        detection disagrees -- a date stored as text detects as categorical --
        so that is the case asserted. A mutation run showed that testing them
        on well-detected columns proves nothing: the fallback gives the same
        answer and the alias can be deleted unnoticed."""
        got = effective_roles(
            {"opened_on": "categorical", "branch": "numeric"},
            {"opened_on": {"role": "timestamp"}, "branch": {"role": "dimension"}})
        assert got["opened_on"] == "datetime"
        assert got["branch"] == "categorical"

    def test_hidden_still_removes_the_column_entirely(self):
        got = effective_roles({"a": "numeric", "secret": "numeric"},
                              {"secret": {"hidden": True}})
        assert set(got) == {"a"}


class TestTheConsumersHandleTheNewValue:
    """Every consumer filters by exact equality, so identifier matches none of
    numeric/categorical/datetime -- which is what an identifier is. These pin
    that reading rather than trusting it."""

    def test_generate_insights_does_not_treat_an_identifier_as_a_measure(self):
        import pandas as pd
        from app.services.insights import generate_insights

        n = 60
        df = pd.DataFrame({
            "student_id": range(1000, 1000 + n),
            "faculty": ["eng", "law", "med", "arts"] * (n // 4),
            "score": [70.0, 65.0, 88.0, 59.0] * (n // 4),
        })
        out = generate_insights(
            df, {"student_id": "numeric", "faculty": "categorical", "score": "numeric"},
            {"student_id": {"role": "identifier"}})
        named = " ".join(str(f.get("columns")) for f in out.get("findings") or [])
        assert "student_id" not in named, f"an identifier reached a finding: {named}"

    def test_a_suggestion_never_sums_a_column_the_roles_call_an_identifier(self):
        got = suggest_widgets_from_findings(
            [finding("standout", ["department", "encounter_id"])],
            {"department": "categorical", "encounter_id": "identifier",
             "wait_minutes": "numeric"})
        for s in got:
            cfg = s.get("config") or {}
            if cfg.get("measure") == "encounter_id":
                assert cfg.get("aggregation") == "count"
