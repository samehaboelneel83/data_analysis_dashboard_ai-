"""Proposing a dashboard with no model at all.

When the person says nothing about who they are, there is nothing for a model to
tailor to — and asking one anyway spends 25 seconds and a network round trip to
produce a generic answer that the statistics engine can produce instantly and
deterministically.

So an empty goal takes a different path entirely: `insights.generate_insights`
finds what stands out in the data, `suggest_widgets_from_findings` turns those
findings into charts, and this assembles them into a proposal.

What it does NOT skip is the gates. `suggest_widgets_from_findings` emits configs
that were never checked against the widget contract — a monthly granularity
regardless of the data's span, a bar chart over a column with 500 values, a
measure that is really an identifier. Those go through exactly the same
validation, polish and execution as anything a model proposes, because a blank
tile is no better for having been chosen by statistics.
"""
import pandas as pd
import pytest

from app.services.dataset_profile import build_profile
from app.services.suggest_from_insights import (
    build_relations, suggest_from_insights,
)


def clinic_df():
    return pd.DataFrame({
        "encounter_id": range(1, 121),
        "department": ["Cardiology", "ENT", "Oncology", "Renal"] * 30,
        "wait_minutes": [10, 40, 90, 130] * 30,
        "total_cost": [500, 1200, 3000, 8000] * 30,
        "arrived_at": pd.date_range("2025-01-01", periods=120, freq="D"),
    })


@pytest.fixture
def profile():
    return build_profile(clinic_df())


async def probe_ok(widget_type, config):
    return {"type": "series", "rows": [{"name": "Cardiology", "value": 3}]}


async def probe_empty(widget_type, config):
    return {"type": "empty", "rows": []}


@pytest.mark.asyncio
class TestItProposesWithoutAModel:
    async def test_it_returns_a_proposal(self, profile):
        got, why = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert got, why

    async def test_the_proposal_has_widgets(self, profile):
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert len(got[0]["widgets"]) >= 2

    async def test_every_widget_says_why_it_is_there(self, profile):
        """The finding's own sentence, which is the honest reason: it states what
        the chart shows, with the figures already in it."""
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert all(w.get("why") for w in got[0]["widgets"])

    async def test_it_says_where_it_came_from(self, profile):
        """A person looking at a generated page should know which engine made
        it. This one used no AI and should say so."""
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert got[0]["source"] == "insights"

    async def test_it_never_calls_a_model(self, profile, monkeypatch):
        def explode(*a, **k):
            raise AssertionError("a model was contacted on the no-AI path")
        monkeypatch.setattr("app.services.llm.get_client", explode)
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert got

    async def test_a_widget_that_draws_nothing_is_dropped(self, profile):
        got, why = await suggest_from_insights(clinic_df(), profile, probe=probe_empty)
        assert got == [] and why

    async def test_too_little_data_is_explained_not_crashed(self):
        tiny = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        got, why = await suggest_from_insights(tiny, build_profile(tiny), probe=probe_ok)
        assert got == [] and why


@pytest.mark.asyncio
class TestTheGatesStillApply:
    async def test_a_date_dimension_is_bucketed_for_the_span(self, profile):
        """`suggest_widgets_from_findings` hard-codes month. 120 days of daily
        data is a weekly chart; polish decides from the profile."""
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        dated = [w for w in got[0]["widgets"]
                 if w["config"].get("dimension") == "arrived_at"]
        for w in dated:
            assert w["config"]["dimension_granularity"] == \
                profile["structure"]["date_range"]["granularity"]

    async def test_nothing_sums_an_identifier(self, profile):
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        for w in got[0]["widgets"]:
            if w["config"].get("measure") == "encounter_id":
                assert w["config"].get("aggregation") not in ("sum", "avg", "median")

    async def test_every_widget_carries_the_rows_it_drew(self, profile):
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert all(w["row_count"] >= 1 for w in got[0]["widgets"])


class TestRelations:
    """What the widgets have to do with each other.

    Two charts cut by the same column are not merely both on the page: clicking
    a department in one is a question the other can answer. That is a
    cross-filter edge, and it is the only kind of relation a reader can act on.
    """

    def widgets(self):
        return [
            {"widget_type": "kpi", "title": "Total cost",
             "config": {"measure": "total_cost", "aggregation": "sum"}},
            {"widget_type": "bar", "title": "Cost by department",
             "config": {"dimension": "department", "measure": "total_cost",
                        "aggregation": "sum"}},
            {"widget_type": "box_plot", "title": "Wait by department",
             "config": {"dimension": "department", "measure": "wait_minutes"}},
            {"widget_type": "line", "title": "Cost over time",
             "config": {"dimension": "arrived_at", "measure": "total_cost",
                        "aggregation": "sum"}},
        ]

    def test_two_charts_on_the_same_column_are_related(self):
        rel = build_relations(self.widgets())
        pairs = {(r["from"], r["to"]) for r in rel}
        assert (1, 2) in pairs

    def test_the_relation_names_the_column_they_share(self):
        rel = build_relations(self.widgets())
        assert all(r["via"] == "department" for r in rel)

    def test_charts_on_different_columns_are_not_related(self):
        rel = build_relations(self.widgets())
        assert not [r for r in rel if 3 in (r["from"], r["to"])]

    def test_a_kpi_is_not_a_filter_source(self):
        """A KPI has no dimension and nothing to click. Making it broadcast
        would be an edge that can never fire."""
        rel = build_relations(self.widgets())
        assert not [r for r in rel if 0 in (r["from"], r["to"])]

    def test_the_relation_is_expressed_as_a_filter(self):
        rel = build_relations(self.widgets())
        assert all(r["mode"] == "filter" for r in rel)

    def test_it_reads_as_a_sentence(self):
        rel = build_relations(self.widgets())
        assert "department" in rel[0]["note"]
        assert "Cost by department" in rel[0]["note"]

    def test_one_widget_alone_relates_to_nothing(self):
        assert build_relations([self.widgets()[1]]) == []

    def test_it_does_not_relate_a_widget_to_itself(self):
        rel = build_relations(self.widgets())
        assert all(r["from"] != r["to"] for r in rel)


@pytest.mark.asyncio
class TestRelationsReachTheProposal:
    async def test_the_proposal_carries_them(self, profile):
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        assert "relations" in got[0]

    async def test_they_index_widgets_that_survived(self, profile):
        """Relations are built AFTER the drops, so an index can only point at a
        widget the person will actually get."""
        got, _ = await suggest_from_insights(clinic_df(), profile, probe=probe_ok)
        n = len(got[0]["widgets"])
        for r in got[0]["relations"]:
            assert 0 <= r["from"] < n and 0 <= r["to"] < n
