"""Composing a chart from plot layers — SAS calls this Graph Builder.

The catalogue already had three fixed combinations (dual-axis bar, line, and
bar-line). Graph Builder's actual capability is not "more combinations"; it is
that the author decides what the combination IS — how many layers, which mark
each draws, which axis each belongs to — and can then keep the result.

Two properties decide whether this tells the truth, and both are places the
two-measure shaper it grew from already had to be careful:

**A layer aggregates in its own right.** The numbers on a multi-layer chart are
not the same KIND of number — that is why it has two axes — so "encounters
counted, wait averaged" has to be expressible per layer.

**Layers are keyed by position, never by measure name.** The same column read
two ways ("total cost" and "average cost") is a legitimate and common pair, and
keying the output by column name silently collapses it to one series.
"""
import pandas as pd
import pytest

from app.services.widget_data import shape_custom_graph


@pytest.fixture
def sales():
    return pd.DataFrame({
        "region": ["N", "N", "S", "S", "E"],
        "revenue": [10.0, 20.0, 5.0, 15.0, 40.0],
        "orders": [1, 2, 1, 1, 3],
    })


def _cfg(layers, **over):
    return {"dimension": "region", "layers": layers, **over}


class TestLayers:
    def test_one_layer_is_a_plain_chart(self, sales):
        out = shape_custom_graph(sales, _cfg([
            {"mark": "bar", "measure": "revenue", "aggregation": "sum"}]))

        assert out["type"] == "custom_graph"
        assert {r["name"] for r in out["rows"]} == {"N", "S", "E"}
        key = out["layers"][0]["key"]
        assert {r["name"]: r[key] for r in out["rows"]}["N"] == 30.0

    def test_each_layer_keeps_its_own_aggregation(self, sales):
        # The whole reason a chart has two axes: two different kinds of number.
        out = shape_custom_graph(sales, _cfg([
            {"mark": "bar", "measure": "revenue", "aggregation": "sum"},
            {"mark": "line", "measure": "revenue", "aggregation": "avg"},
        ]))

        k0, k1 = out["layers"][0]["key"], out["layers"][1]["key"]
        north = next(r for r in out["rows"] if r["name"] == "N")
        assert north[k0] == 30.0
        assert north[k1] == 15.0

    def test_the_same_measure_twice_is_two_series(self, sales):
        # Keyed by position. Keyed by measure NAME these would be one column,
        # and the chart would draw a single line where the author asked for a
        # total and an average.
        out = shape_custom_graph(sales, _cfg([
            {"mark": "bar", "measure": "revenue", "aggregation": "sum"},
            {"mark": "line", "measure": "revenue", "aggregation": "avg"},
        ]))
        assert len({lyr["key"] for lyr in out["layers"]}) == 2

    def test_a_layer_carries_its_mark_and_axis(self, sales):
        out = shape_custom_graph(sales, _cfg([
            {"mark": "bar", "measure": "revenue", "aggregation": "sum", "axis": "left"},
            {"mark": "line", "measure": "orders", "aggregation": "sum", "axis": "right"},
        ]))
        assert [lyr["mark"] for lyr in out["layers"]] == ["bar", "line"]
        assert [lyr["axis"] for lyr in out["layers"]] == ["left", "right"]

    def test_each_layer_is_labelled_for_a_legend(self, sales):
        out = shape_custom_graph(sales, _cfg([
            {"mark": "bar", "measure": "revenue", "aggregation": "sum"},
            {"mark": "line", "measure": "revenue", "aggregation": "avg"},
        ]))
        labels = [lyr["label"] for lyr in out["layers"]]
        # Distinguishable, because the two series are the same column and a
        # legend reading "revenue" twice explains nothing.
        assert len(set(labels)) == 2
        assert all("revenue" in l for l in labels)


class TestRefusals:
    def test_no_layers_is_empty_not_an_error(self, sales):
        # An author who has added the widget but not built it yet is mid-task,
        # not wrong.
        assert shape_custom_graph(sales, _cfg([]))["type"] == "empty"

    def test_a_layer_naming_a_missing_column_is_reported(self, sales):
        # Silently drawing the layers that worked would leave the author looking
        # for a series that is simply not there, with nothing to explain it.
        out = shape_custom_graph(sales, _cfg([
            {"mark": "bar", "measure": "revenue", "aggregation": "sum"},
            {"mark": "line", "measure": "gone", "aggregation": "sum"},
        ]))
        assert len(out["layers"]) == 1
        assert "gone" in out.get("skipped", [])

    def test_a_missing_dimension_is_empty(self, sales):
        out = shape_custom_graph(sales, {"dimension": "nope", "layers": [
            {"mark": "bar", "measure": "revenue", "aggregation": "sum"}]})
        assert out["type"] == "empty"

    def test_an_unknown_mark_falls_back_rather_than_failing(self, sales):
        # Marks arrive from stored config, which outlives the list of marks the
        # renderer knows. An unknown one drawn as a bar is readable; a crash is
        # not.
        out = shape_custom_graph(sales, _cfg([
            {"mark": "hexbin", "measure": "revenue", "aggregation": "sum"}]))
        assert out["layers"][0]["mark"] == "bar"


class TestSharedBehaviour:
    def test_it_honours_the_row_limit(self, sales):
        out = shape_custom_graph(sales, _cfg(
            [{"mark": "bar", "measure": "revenue", "aggregation": "sum"}], limit=2))
        assert len(out["rows"]) == 2

    def test_it_honours_filters(self, sales):
        out = shape_custom_graph(sales, _cfg(
            [{"mark": "bar", "measure": "revenue", "aggregation": "sum"}],
            filters=[{"column": "region", "op": "eq", "value": "N"}]))
        assert {r["name"] for r in out["rows"]} == {"N"}
