"""Making each proposed chart actually useful before it is built.

A proposal that passes validation is *valid*, not *good*. The first dashboards
the designer produced were bar charts of 400 courses with no limit, tables sorted
by nothing in particular, and a line chart of raw per-second timestamps. Every one
of them ran, rendered, and told the instructor nothing.

The engine reads more than dimension/measure/aggregation: `limit`, `sort`,
`sort_by`, `dimension_granularity` and `running` all change what a chart says. The
designer was not setting any of them, so this is a second pass that does — the
model looks at each widget beside the real column types and the first row of the
query's output, and fills those in.

WHY A SEPARATE PASS
-------------------
Asking for good attributes in the first prompt makes one prompt do two jobs and
gets neither reliably: the first pass is about WHICH tables answer this person's
question, this one is about how to draw the answer. Separating them also means the
second pass can see the query's actual result columns, which do not exist until
the first pass has run.

Each suggestion carries a `note` saying why, shown under the widget in the chat.
An attribute the person cannot see the reason for is one they cannot overrule.
"""
import pytest

from app.services.widget_review import (ATTRIBUTE_SCHEMA, apply_attributes,
                                        build_review_prompt, review_attributes)

WIDGETS = [
    {"widget_type": "bar", "title": "Courses by department", "dimension": "department",
     "measure": "course_id", "aggregation": "countd"},
    {"widget_type": "line", "title": "Activity over time", "dimension": "last_seen",
     "measure": "student_id", "aggregation": "countd"},
]
COLUMN_TYPES = {"department": "categorical", "course_id": "numeric",
                "last_seen": "datetime", "student_id": "numeric"}


class TestPrompt:
    def test_it_shows_the_model_the_real_column_types(self):
        text = " ".join(m["content"] for m in
                        build_review_prompt(WIDGETS, COLUMN_TYPES, sample_row={}))
        assert "last_seen" in text and "datetime" in text

    def test_it_offers_only_attributes_the_engine_reads(self):
        """Colours and axis labels are frontend concerns the query engine ignores.
        Offering them produces settings that look applied and do nothing."""
        text = " ".join(m["content"] for m in
                        build_review_prompt(WIDGETS, COLUMN_TYPES, sample_row={}))
        for offered in ("limit", "sort", "dimension_granularity", "running"):
            assert offered in text
        for not_offered in ("colour", "color", "axis_label"):
            assert not_offered not in text.lower()

    def test_it_carries_a_sample_row_so_scale_is_visible(self):
        """"Should this be limited to 10?" is unanswerable without knowing whether
        the dimension has 5 values or 400."""
        text = " ".join(m["content"] for m in build_review_prompt(
            WIDGETS, COLUMN_TYPES, sample_row={"department": "Engineering"}))
        assert "Engineering" in text


class TestApplying:
    def test_an_improved_attribute_is_applied_to_the_right_widget(self):
        out = apply_attributes(WIDGETS, [
            {"index": 0, "limit": 10, "sort": "desc", "sort_by": "value",
             "dimension_granularity": "", "running": "", "note": "400 courses; top 10 reads"},
        ])
        assert out[0]["limit"] == 10
        assert out[0]["sort"] == "desc"
        assert out[0]["note"] == "400 courses; top 10 reads"

    def test_widgets_the_model_did_not_mention_are_untouched(self):
        out = apply_attributes(WIDGETS, [{"index": 0, "limit": 10, "sort": "desc",
                                          "sort_by": "value", "dimension_granularity": "",
                                          "running": "", "note": "x"}])
        assert "limit" not in out[1]

    def test_an_empty_attribute_is_not_written(self):
        """The engine treats "" as a real value for granularity and would try to
        bucket by it. Absent must stay absent."""
        out = apply_attributes(WIDGETS, [
            {"index": 1, "limit": 0, "sort": "", "sort_by": "",
             "dimension_granularity": "week", "running": "", "note": "per week"},
        ])
        assert out[1]["dimension_granularity"] == "week"
        assert "running" not in out[1]
        assert "limit" not in out[1]

    def test_an_index_out_of_range_is_ignored(self):
        out = apply_attributes(WIDGETS, [{"index": 99, "limit": 10, "sort": "desc",
                                          "sort_by": "", "dimension_granularity": "",
                                          "running": "", "note": "x"}])
        assert len(out) == 2

    def test_the_original_widgets_are_not_mutated(self):
        apply_attributes(WIDGETS, [{"index": 0, "limit": 10, "sort": "desc",
                                    "sort_by": "", "dimension_granularity": "",
                                    "running": "", "note": "x"}])
        assert "limit" not in WIDGETS[0]


class TestGranularityMustMatchTheColumn:
    """The rung this needs most. `dimension_granularity` on a column that is not a
    date produces an empty chart — silently, which is the failure mode this whole
    area keeps producing."""

    def test_granularity_on_a_date_column_is_kept(self):
        out = apply_attributes(WIDGETS, [
            {"index": 1, "limit": 0, "sort": "", "sort_by": "",
             "dimension_granularity": "month", "running": "", "note": "monthly"},
        ], column_types=COLUMN_TYPES)
        assert out[1]["dimension_granularity"] == "month"

    def test_granularity_on_a_text_column_is_dropped(self):
        out = apply_attributes(WIDGETS, [
            {"index": 0, "limit": 0, "sort": "", "sort_by": "",
             "dimension_granularity": "month", "running": "", "note": "monthly"},
        ], column_types=COLUMN_TYPES)
        assert "dimension_granularity" not in out[0]

    def test_an_unknown_granularity_is_dropped(self):
        out = apply_attributes(WIDGETS, [
            {"index": 1, "limit": 0, "sort": "", "sort_by": "",
             "dimension_granularity": "fortnight", "running": "", "note": "x"},
        ], column_types=COLUMN_TYPES)
        assert "dimension_granularity" not in out[1]


class TestTheSchema:
    def test_it_is_flat_enough_for_strict_json_mode(self):
        def check(node):
            if node.get("type") == "object":
                assert node.get("properties")
                assert node.get("additionalProperties") is False
                for child in node["properties"].values():
                    check(child)
            if node.get("type") == "array":
                check(node["items"])
        check(ATTRIBUTE_SCHEMA)


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        return self.reply


async def test_review_returns_the_widgets_improved(monkeypatch):
    client = FakeClient({"attributes": [
        {"index": 0, "limit": 10, "sort": "desc", "sort_by": "value",
         "dimension_granularity": "", "running": "", "note": "top 10 of 400"}]})
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    out = await review_attributes(WIDGETS, COLUMN_TYPES, sample_row={})

    assert out[0]["limit"] == 10
    assert out[0]["note"] == "top 10 of 400"


async def test_an_unreachable_model_leaves_the_widgets_as_they_were(monkeypatch):
    """This pass is an improvement, never a requirement. A dashboard with plain
    attributes is worth having; no dashboard is not."""
    client = FakeClient(None)
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    out = await review_attributes(WIDGETS, COLUMN_TYPES, sample_row={})

    assert out == WIDGETS


# ---------------------------------------------------------------------------
# A note must not explain something that did not happen. Seen live: the model
# asked for a monthly bucket on a line chart, the date guard dropped it because
# the dimension was not a date column — and the note "ensures the x-axis displays
# distinct monthly intervals" was kept and shown to the user. The chart was
# unchanged; the sentence under it said otherwise. That is worse than no note.
# ---------------------------------------------------------------------------


def test_a_note_is_dropped_when_none_of_its_attributes_survived():
    out = apply_attributes(WIDGETS, [
        {"index": 0, "limit": 0, "sort": "", "sort_by": "",
         "dimension_granularity": "month", "running": "",
         "note": "Buckets the axis by month."},
    ], column_types=COLUMN_TYPES)          # index 0's dimension is categorical
    assert "dimension_granularity" not in out[0]
    assert "note" not in out[0], "the note outlived the change it described"


def test_a_note_is_kept_when_something_was_applied():
    out = apply_attributes(WIDGETS, [
        {"index": 0, "limit": 10, "sort": "", "sort_by": "",
         "dimension_granularity": "month", "running": "",
         "note": "Top 10, and bucketed by month."},
    ], column_types=COLUMN_TYPES)
    assert out[0]["limit"] == 10
    assert out[0]["note"] == "Top 10, and bucketed by month."


def test_a_note_alone_changes_nothing():
    """"No changes needed" is a real answer from the model. It must not attach a
    sentence to a widget it did not touch."""
    out = apply_attributes(WIDGETS, [
        {"index": 1, "limit": 0, "sort": "", "sort_by": "",
         "dimension_granularity": "", "running": "",
         "note": "No changes needed."},
    ], column_types=COLUMN_TYPES)
    assert out[1] == WIDGETS[1]
