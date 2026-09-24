"""What the model is told about a dataset before it proposes anything.

A column list and a dtype is not enough to choose a chart. Deciding that
`department` is worth a bar chart and `encounter_id` is not needs cardinality;
deciding a date column can carry a monthly trend needs its span; deciding
whether a map is possible at all needs to know a latitude and a longitude sit
side by side. A model given only names invents plausible nonsense — and the
things it invents are exactly the eighteen blank tiles this codebase spent a day
fixing.

So the profile carries what a competent analyst would look at first: role,
cardinality, missing data, range, the commonest values, and the structural
relationships (coordinate pairs, parent-child links, hierarchies) that unlock
whole widget families.

It also carries what the model must NOT do: identifier columns it should never
sum, and PII columns it should never group by.
"""
import pandas as pd

from app.services.dataset_profile import build_profile, describe_for_prompt


def hospital():
    return pd.DataFrame({
        "encounter_id":   range(1, 61),
        "department":     ["Cardiology", "ENT", "Oncology"] * 20,
        "wait_minutes":   [30, 60, 90] * 20,
        "arrived_at":     pd.date_range("2025-01-01", periods=60, freq="D"),
        "patient_lat":    [30.05] * 60,
        "patient_lon":    [31.24] * 60,
        "staff_id":       list(range(100, 160)),
        "reports_to":     [100] * 60,
        "patient_email":  ["a@b.com"] * 60,
    })


def cols(profile):
    return {c["name"]: c for c in profile["columns"]}


class TestWhatEachColumnIs:
    def test_it_reports_a_role_per_column(self):
        got = cols(build_profile(hospital()))
        assert got["wait_minutes"]["role"] == "numeric"
        assert got["department"]["role"] == "categorical"
        assert got["arrived_at"]["role"] == "datetime"

    def test_it_counts_distinct_values(self):
        got = cols(build_profile(hospital()))
        assert got["department"]["distinct"] == 3

    def test_it_reports_the_commonest_values(self):
        """Cardinality alone does not say whether a category is worth charting;
        seeing the actual labels does."""
        got = cols(build_profile(hospital()))
        labels = [v["value"] for v in got["department"]["top_values"]]
        assert set(labels) == {"Cardiology", "ENT", "Oncology"}

    def test_it_reports_the_range_of_a_measure(self):
        got = cols(build_profile(hospital()))
        assert got["wait_minutes"]["min"] == 30
        assert got["wait_minutes"]["max"] == 90

    def test_it_reports_missing_data(self):
        df = hospital()
        df.loc[0:29, "wait_minutes"] = None
        got = cols(build_profile(df))
        assert got["wait_minutes"]["missing_pct"] == 50.0


class TestWhatMustNotBeDone:
    def test_identifier_columns_are_flagged(self):
        """Summing an identifier produces a number with no meaning — a mistake
        made on a real dashboard in this repo, twice."""
        got = cols(build_profile(hospital()))
        assert got["encounter_id"]["is_identifier"] is True
        assert got["wait_minutes"]["is_identifier"] is False

    def test_personal_columns_are_flagged(self):
        got = cols(build_profile(hospital()))
        assert got["patient_email"]["is_personal"] is True
        assert got["department"]["is_personal"] is False


class TestFlagColumns:
    """A 0/1 column is a fact about each row, and the number people want from it
    is the SHARE that are 1 -- the mortality rate, the abnormal rate. Counting it
    counts every row instead, flagged or not, which is the total dressed up as a
    rate."""

    def test_a_binary_numeric_column_is_flagged_as_a_flag(self):
        df = hospital().assign(died=[0, 1] * 30)
        got = cols(build_profile(df))
        assert got["died"]["is_flag"] is True

    def test_a_real_measure_is_not(self):
        assert cols(build_profile(hospital()))["wait_minutes"]["is_flag"] is False

    def test_the_prompt_says_how_to_use_one(self):
        df = hospital().assign(died=[0, 1] * 30)
        text = describe_for_prompt(build_profile(df))
        assert "died" in text and "share" in text.lower()


class TestStructureTheWidgetsNeed:
    def test_it_finds_coordinate_pairs(self):
        """Nine map widgets are unusable without one, and pointless to offer."""
        got = build_profile(hospital())
        assert ("patient_lat", "patient_lon") in [
            tuple(p) for p in got["structure"]["coordinate_pairs"]]

    def test_it_finds_a_parent_child_pair(self):
        got = build_profile(hospital())
        assert ["staff_id", "reports_to"] in [
            list(p) for p in got["structure"]["parent_child"]]

    def test_it_reports_the_date_span(self):
        got = build_profile(hospital())
        span = got["structure"]["date_range"]
        assert span["column"] == "arrived_at"
        assert span["from"].startswith("2025-01-01")
        assert span["days"] >= 59

    def test_it_suggests_a_granularity_that_suits_the_span(self):
        """Sixty days is a daily or weekly chart; two years is a monthly one.
        Offering 'day' over two years draws 730 columns."""
        assert build_profile(hospital())["structure"]["date_range"]["granularity"] \
            in ("day", "week")

    def test_a_long_span_gets_a_coarser_granularity(self):
        df = hospital()
        df["arrived_at"] = pd.date_range("2020-01-01", periods=60, freq="ME")
        assert build_profile(df)["structure"]["date_range"]["granularity"] == "month"


class TestTheRowCount:
    def test_it_is_reported(self):
        assert build_profile(hospital())["row_count"] == 60


class TestTheProseTheModelReads:
    def test_it_names_every_column(self):
        text = describe_for_prompt(build_profile(hospital()))
        for name in hospital().columns:
            assert name in text

    def test_it_warns_about_identifiers(self):
        text = describe_for_prompt(build_profile(hospital()))
        assert "encounter_id" in text and "identifier" in text.lower()

    def test_it_states_the_coordinate_pair(self):
        text = describe_for_prompt(build_profile(hospital()))
        assert "patient_lat" in text and "patient_lon" in text

    def test_it_is_not_unbounded(self):
        """A 300-column dataset must not produce a prompt that costs more than
        the answer is worth."""
        wide = pd.DataFrame({f"c{i}": range(5) for i in range(300)})
        assert len(describe_for_prompt(build_profile(wide))) < 20000


class TestEmptyAndOdd:
    def test_an_empty_frame_does_not_raise(self):
        got = build_profile(pd.DataFrame())
        assert got["columns"] == [] and got["row_count"] == 0

    def test_a_frame_with_no_dates_has_no_range(self):
        got = build_profile(pd.DataFrame({"a": [1, 2, 3]}))
        assert got["structure"]["date_range"] is None


# ── What the model is told the data MEANS ────────────────────────────────────
#
# Everything above describes column SHAPES. Shapes alone are how the designer
# came to draw charts that were valid and meaningless: `status (categorical, 3
# distinct)` is enough to pick a pie chart and not nearly enough to know whether
# anybody wants one. `services/knowledge.py` resolves the sentences, the coded
# values and the business terms out of the source catalog; these pin that they
# reach the prompt, and that a dataset with no catalog behind it is unchanged.

from app.services.knowledge import (ColumnKnowledge, DatasetKnowledge,
                                    GlossaryEntry, ObjectKnowledge)


def knowledge_for_hospital():
    return DatasetKnowledge(
        dataset_id=1,
        object=ObjectKnowledge(
            name="encounters", business_name="Encounter",
            description="One visit to the emergency department.",
            grain="One row per completed encounter.", is_canonical=True),
        columns={
            "department": ColumnKnowledge(
                name="department", dtype="text",
                description="Clinical department that owned the encounter."),
            "wait_minutes": ColumnKnowledge(
                name="wait_minutes", dtype="integer",
                description="Minutes from arrival to first clinician contact.",
                enum_labels=None),
            "encounter_id": ColumnKnowledge(
                name="encounter_id", dtype="integer",
                enum_labels={"1": "walk-in", "2": "ambulance"}),
        },
        glossary=[GlossaryEntry(term="door-to-doctor",
                                definition="wait_minutes, averaged.",
                                synonyms=["D2D"],
                                maps_to_column="wait_minutes")])


class TestMeaningReachesThePrompt:
    def test_without_knowledge_the_prompt_is_exactly_what_it_always_was(self):
        """The regression guard that makes the rest of this safe. A dataset with
        no catalog behind it -- every upload -- must get the identical prompt,
        byte for byte, or this change silently rewrote what every existing
        proposal was built from."""
        profile = build_profile(hospital(), {}, {})
        assert describe_for_prompt(profile) == describe_for_prompt(profile, None)
        assert "WHAT THESE ROWS ARE" not in describe_for_prompt(profile)

    def test_a_columns_sentence_sits_with_its_numbers(self):
        profile = build_profile(hospital(), {}, {})
        text = describe_for_prompt(profile, knowledge_for_hospital())
        assert "Clinical department that owned the encounter." in text
        # Attached to the column, not dumped in a block at the end -- the model
        # reads a column line and its meaning together or it reads neither.
        line = next(b for b in text.split("- ") if b.startswith("department "))
        assert "Clinical department that owned the encounter." in line

    def test_coded_values_are_spelled_out(self):
        profile = build_profile(hospital(), {}, {})
        text = describe_for_prompt(profile, knowledge_for_hospital())
        assert "values mean: 1 = walk-in, 2 = ambulance" in text

    def test_what_one_row_IS_leads_the_prompt(self):
        """The grain and the canonical marker: the two facts that most often stop
        a model double-counting or aggregating the wrong thing."""
        profile = build_profile(hospital(), {}, {})
        text = describe_for_prompt(profile, knowledge_for_hospital())
        assert text.startswith("WHAT THESE ROWS ARE")
        assert "Encounter -- One row per completed encounter" in text
        assert "source of truth" in text
        assert "One visit to the emergency department." in text

    def test_business_terms_arrive_with_their_synonyms(self):
        profile = build_profile(hospital(), {}, {})
        text = describe_for_prompt(profile, knowledge_for_hospital())
        assert "BUSINESS TERMS" in text
        assert "door-to-doctor (also D2D)" in text
        assert "-> column wait_minutes" in text

    def test_a_column_with_nothing_known_gains_no_empty_decoration(self):
        """Silence, not an empty label. A blank "description:" line teaches the
        model that descriptions are noise, and the next column that has a real
        one gets read with the same weight."""
        profile = build_profile(hospital(), {}, {})
        text = describe_for_prompt(profile, knowledge_for_hospital())
        staff = next(b for b in text.split("- ") if b.startswith("staff_id "))
        assert "values mean" not in staff
        assert staff.count(chr(10)) <= 2

    def test_a_long_label_map_is_capped_rather_than_pasted_whole(self):
        """A four-hundred-code product column is a dictionary. Pasting it would
        crowd out every other column's meaning."""
        from app.services.dataset_profile import MAX_LABELS_IN_PROMPT

        know = knowledge_for_hospital()
        know.columns["department"] = ColumnKnowledge(
            name="department", dtype="text",
            enum_labels={str(i): "code %d" % i for i in range(50)})
        text = describe_for_prompt(build_profile(hospital(), {}, {}), know)
        assert "... (50 in total)" in text
        assert "code %d" % MAX_LABELS_IN_PROMPT not in text
