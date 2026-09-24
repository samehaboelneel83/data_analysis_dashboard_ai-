"""Hierarchy widgets: five layouts over one shaper.

Tree, sunburst, icicle, dendrogram and org chart all come from
`shape_hierarchy`, for the reason small multiples has one shaper: a layout that
computed its own totals would be a second aggregation path, and two paths drift.

Three properties decide whether these tell the truth, and each is pinned below.

**Reconciliation.** Children plus the "Other" residual must equal their parent.
A breakdown whose parts do not sum to the whole is worse than no breakdown --
the rule the decomposition tree already lives by.

**Additive aggregations on partition charts.** A sunburst draws value as an
angle and an icicle as a width, so the parent's wedge IS the sum of its
children's. An average does not add up that way, and drawing it as area states
a falsehood the reader cannot see. Trees print the number instead, so they
accept anything.

**Cycles refused, orphans adopted.** A looping parent chain has no root and
hangs a renderer. A row whose parent is merely absent is different: row-level
security removes rows, so the honest rendering is a forest rooting where the
caller's permission begins.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.widget_data import (HIER_MAX_CHILDREN, HierarchyError,
                                      shape_hierarchy)


@pytest.fixture
def sales():
    rng = np.random.default_rng(0)
    n = 600
    return pd.DataFrame({
        "country": rng.choice(["UK", "France", "Spain"], n),
        "region": rng.choice(["North", "South", "East", "West"], n),
        "city": rng.choice([f"c{i}" for i in range(8)], n),
        "revenue": rng.integers(10, 100, n).astype(float),
    })


@pytest.fixture
def org():
    return pd.DataFrame({
        "id": ["ceo", "cto", "cfo", "eng1", "eng2", "acct1"],
        "mgr": [None, "ceo", "ceo", "cto", "cto", "cfo"],
        "name": ["Ada", "Bo", "Cy", "Dee", "Eve", "Fay"],
        "salary": [300.0, 200, 200, 120, 110, 90],
    })


def kids_total(node):
    return sum(c["value"] or 0 for c in node["children"])


class TestItReconciles:
    def test_children_sum_to_their_parent(self, sales):
        r = shape_hierarchy(sales, {"widget_type": "sunburst",
                                    "levels": ["country", "region"],
                                    "measure": "revenue", "aggregation": "sum"})
        root = r["root"]
        assert root["value"] == pytest.approx(kids_total(root))

    def test_it_reconciles_at_every_level(self, sales):
        r = shape_hierarchy(sales, {"widget_type": "icicle",
                                    "levels": ["country", "region", "city"],
                                    "measure": "revenue", "aggregation": "sum"})

        def check(node):
            if node["children"]:
                assert node["value"] == pytest.approx(kids_total(node)), node["name"]
                for c in node["children"]:
                    check(c)
        check(r["root"])

    def test_the_capped_tail_becomes_other_and_still_reconciles(self):
        """Dropping the tail would silently change the total; folding it into
        'Other' with its real value keeps the level honest."""
        rng = np.random.default_rng(1)
        wide = pd.DataFrame({"k": [f"k{i}" for i in range(30)] * 5,
                             "v": rng.integers(1, 50, 150).astype(float)})
        r = shape_hierarchy(wide, {"widget_type": "icicle", "levels": ["k"],
                                   "measure": "v", "aggregation": "sum"})
        root = r["root"]
        other = [c for c in root["children"] if c.get("is_other")]
        assert other, "the omitted tail must be represented, not dropped"
        assert root["omitted"] == 30 - HIER_MAX_CHILDREN
        assert root["value"] == pytest.approx(kids_total(root))

    def test_no_measure_counts_rows(self, sales):
        r = shape_hierarchy(sales, {"widget_type": "tree", "levels": ["country"]})
        assert r["root"]["value"] == len(sales)


class TestPartitionChartsNeedAdditiveAggregations:
    def test_a_sunburst_refuses_an_average(self, sales):
        with pytest.raises(HierarchyError, match="additive"):
            shape_hierarchy(sales, {"widget_type": "sunburst",
                                    "levels": ["country"], "measure": "revenue",
                                    "aggregation": "avg"})

    def test_an_icicle_refuses_a_maximum(self, sales):
        with pytest.raises(HierarchyError, match="additive"):
            shape_hierarchy(sales, {"widget_type": "icicle",
                                    "levels": ["country"], "measure": "revenue",
                                    "aggregation": "max"})

    def test_a_tree_accepts_one(self, sales):
        """Nothing is area-encoded, so the number is printed rather than drawn
        as a share -- there is no geometry to contradict."""
        r = shape_hierarchy(sales, {"widget_type": "tree", "levels": ["country"],
                                    "measure": "revenue", "aggregation": "avg"})
        assert r["root"]["children"]

    def test_the_refusal_names_the_alternative(self, sales):
        with pytest.raises(HierarchyError, match="tree or dendrogram"):
            shape_hierarchy(sales, {"widget_type": "sunburst",
                                    "levels": ["country"], "measure": "revenue",
                                    "aggregation": "median"})

    def test_sum_and_count_are_allowed(self, sales):
        for agg in ("sum", "count"):
            r = shape_hierarchy(sales, {"widget_type": "sunburst",
                                        "levels": ["country"],
                                        "measure": "revenue", "aggregation": agg})
            assert r["root"]["children"]

    def test_a_circle_pack_refuses_an_average_too(self, sales):
        """A circle pack nests each child INSIDE its parent, so the parent's
        area is the sum of what it contains -- the same claim a sunburst makes
        with angle. Drawn from an average, the children visibly fail to fill
        the parent and nothing tells the reader the picture is at fault rather
        than the data."""
        with pytest.raises(HierarchyError, match="additive"):
            shape_hierarchy(sales, {"widget_type": "circle_pack",
                                    "levels": ["country"], "measure": "revenue",
                                    "aggregation": "avg"})

    def test_a_circle_pack_nests_like_every_other_layout(self, sales):
        """One shaper, six layouts: the numbers must be the SAME numbers, not
        merely the same shape. A layout computing its own totals would be a
        second aggregation path, and two paths drift."""
        cfg = {"levels": ["country", "region"], "measure": "revenue",
               "aggregation": "sum"}
        pack = shape_hierarchy(sales, {**cfg, "widget_type": "circle_pack"})
        burst = shape_hierarchy(sales, {**cfg, "widget_type": "sunburst"})

        assert pack["type"] == "circle_pack"
        assert pack["root"] == burst["root"]
        assert pack["additive"] is True


class TestParentChild:
    def test_it_nests_from_id_and_parent(self, org):
        r = shape_hierarchy(org, {"widget_type": "org", "id_col": "id",
                                  "parent_col": "mgr", "label_col": "name",
                                  "measure": "salary"})
        assert r["mode"] == "parent_child"
        top = r["root"]["children"]
        assert [c["name"] for c in top] == ["Ada"]
        assert {c["name"] for c in top[0]["children"]} == {"Bo", "Cy"}

    def test_an_orphan_becomes_a_root_not_an_error(self, org):
        """Row-level security removes rows. A subtree whose manager the caller
        may not see must still render -- as a forest, rooting where their
        permission begins. Erroring would tell them their data is broken."""
        visible = org[org.id != "ceo"]
        r = shape_hierarchy(visible, {"widget_type": "org", "id_col": "id",
                                      "parent_col": "mgr", "label_col": "name"})
        assert {c["name"] for c in r["root"]["children"]} == {"Bo", "Cy"}

    def test_a_cycle_is_refused_by_name(self):
        """Following a loop hangs the renderer; breaking it silently invents a
        hierarchy that does not exist."""
        cyc = pd.DataFrame({"id": ["a", "b", "c"], "mgr": ["c", "a", "b"]})
        with pytest.raises(HierarchyError, match="loops at"):
            shape_hierarchy(cyc, {"widget_type": "org", "id_col": "id",
                                  "parent_col": "mgr"})

    def test_a_self_parent_is_not_a_cycle_but_a_root(self):
        """A row pointing at itself is a data-entry slip, not a loop; treating
        it as a root renders something useful instead of refusing."""
        df = pd.DataFrame({"id": ["a", "b"], "mgr": ["a", "a"]})
        r = shape_hierarchy(df, {"widget_type": "org", "id_col": "id",
                                 "parent_col": "mgr"})
        assert [c["name"] for c in r["root"]["children"]] == ["a"]

    def test_a_missing_column_is_named(self, org):
        with pytest.raises(HierarchyError, match="nope"):
            shape_hierarchy(org, {"widget_type": "org", "id_col": "nope",
                                  "parent_col": "mgr"})


class TestItStaysReadable:
    def test_a_high_cardinality_column_is_refused_as_a_level(self):
        """The decomposition tree's lesson: splitting by a 633-value date gives
        maximal variation and zero explanation, and a variance score cannot
        tell those apart."""
        df = pd.DataFrame({"x": [str(i) for i in range(80)], "v": 1.0})
        with pytest.raises(HierarchyError, match="list rather than a level"):
            shape_hierarchy(df, {"widget_type": "tree", "levels": ["x"],
                                 "measure": "v"})

    def test_no_levels_asks_for_them(self, sales):
        with pytest.raises(HierarchyError, match="hierarchy"):
            shape_hierarchy(sales, {"widget_type": "tree"})

    def test_depth_is_capped(self, sales):
        r = shape_hierarchy(sales, {"widget_type": "tree",
                                    "levels": ["country", "region", "city"],
                                    "measure": "revenue", "max_depth": 2})

        def depth(node):
            return 1 + max((depth(c) for c in node["children"]), default=0)
        assert depth(r["root"]) <= 3          # root + 2 levels

    def test_every_widget_type_uses_the_same_shaper(self, sales):
        """Five layouts, one set of numbers. If they diverged, two visuals of
        the same data would disagree."""
        cfg = {"levels": ["country"], "measure": "revenue", "aggregation": "sum"}
        values = {}
        for widget in ("tree", "sunburst", "icicle", "dendrogram", "org"):
            r = shape_hierarchy(sales, {**cfg, "widget_type": widget})
            values[widget] = r["root"]["value"]
        assert len(set(values.values())) == 1, values


class TestThePanelsOutputActuallyRenders:
    """The loop the unit tests on either side cannot close.

    The panel emits a config; the shaper consumes one. Both were tested
    separately and both passed while the feature was completely broken -- the
    panel had no hierarchy block at all, so it emitted nothing and every
    user-created sunburst failed with "Choose the columns that form the
    hierarchy". These assert the exact shapes the panel now produces.
    """

    def test_the_levels_config_the_panel_emits_renders(self, sales):
        # Exactly what WidgetConfigPanel writes in levels mode.
        cfg = {"widget_type": "sunburst", "levels": ["country", "region"],
               "measure": "revenue", "aggregation": "sum"}
        r = shape_hierarchy(sales, cfg)
        assert r["root"]["children"], "the panel's own config must produce a tree"

    def test_the_parent_child_config_the_panel_emits_renders(self, org):
        cfg = {"widget_type": "org", "id_col": "id", "parent_col": "mgr",
               "label_col": "name", "measure": "salary"}
        r = shape_hierarchy(org, cfg)
        assert r["mode"] == "parent_child"
        assert r["root"]["children"]

    def test_an_empty_config_still_refuses_legibly(self, sales):
        """What a user got before the panel existed. The message has to name
        the fix, because it is now reachable: the panel offers exactly this."""
        with pytest.raises(HierarchyError, match="Choose the columns"):
            shape_hierarchy(sales, {"widget_type": "sunburst"})

    def test_the_panel_cannot_emit_an_aggregation_the_shaper_refuses(self, sales):
        """The panel filters partition charts to additive aggregations. This
        pins the other half: that the filtered set is exactly what survives."""
        from app.services.widget_data import ADDITIVE_AGGREGATIONS
        for agg in ADDITIVE_AGGREGATIONS:
            r = shape_hierarchy(sales, {"widget_type": "sunburst",
                                        "levels": ["country"],
                                        "measure": "revenue", "aggregation": agg})
            assert r["additive"] is True, agg
