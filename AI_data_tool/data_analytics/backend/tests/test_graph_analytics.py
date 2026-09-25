"""Graph intelligence: communities and predicted links.

The network widget already computed degree, closeness, betweenness and reach.
Those describe how each node sits in the graph but answer neither of the two
questions people actually bring to a network chart:

  * **who clusters together** -- betweenness finds the broker BETWEEN groups
    and never names the groups;
  * **who should be connected but is not** -- absent from a chart by
    definition, since it draws only what exists.

Both are added in numpy/pure Python. No `networkx`, matching the hand-rolled
Brandes betweenness already beside them and keeping the air-gapped image
unchanged.
"""
import pandas as pd
import pytest

from app.services.widget_data import (_label_propagation, _predicted_links,
                                      shape_network)


def _adj(pairs):
    adj: dict = {}
    for a, b in pairs:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


#: Two triangles joined by ONE edge. The textbook two-community graph, and the
#: case that decided the algorithm (see TestItDoesNotCollapse).
TWO_TRIANGLES = [("a1", "a2"), ("a2", "a3"), ("a3", "a1"),
                 ("b1", "b2"), ("b2", "b3"), ("b3", "b1"),
                 ("a1", "b1")]


class TestCommunityDetection:
    def test_two_dense_groups_joined_by_a_bridge_are_two_communities(self):
        adj = _adj(TWO_TRIANGLES)
        comm = _label_propagation(adj, sorted(adj))
        assert comm["a1"] == comm["a2"] == comm["a3"]
        assert comm["b1"] == comm["b2"] == comm["b3"]
        assert comm["a1"] != comm["b1"]

    def test_disconnected_components_are_never_merged(self):
        adj = _adj([("a1", "a2"), ("b1", "b2")])
        comm = _label_propagation(adj, sorted(adj))
        assert comm["a1"] != comm["b1"]

    def test_a_single_clique_is_one_community(self):
        """The other direction. An algorithm that split everything would pass
        the tests above and be equally useless."""
        adj = _adj([(a, b) for a in "abcd" for b in "abcd" if a < b])
        assert len(set(_label_propagation(adj, sorted(adj)).values())) == 1

    def test_the_biggest_group_is_community_zero(self):
        # Renumbered densest-first, so the id means something rather than
        # recording which node happened to be visited first.
        adj = _adj([("x1", "x2"), ("x2", "x3"), ("x3", "x1"), ("x1", "x3"),
                    ("y1", "y2")])
        comm = _label_propagation(adj, sorted(adj))
        sizes: dict[int, int] = {}
        for c in comm.values():
            sizes[c] = sizes.get(c, 0) + 1
        assert sizes[0] == max(sizes.values())

    def test_it_is_deterministic(self):
        """A network that renamed its clusters on every refresh could not be
        compared across refreshes -- the same reason the layout is seeded."""
        adj = _adj(TWO_TRIANGLES)
        runs = [_label_propagation(adj, sorted(adj)) for _ in range(5)]
        assert all(r == runs[0] for r in runs)


class TestItDoesNotCollapse:
    """THE regression. Plain label propagation was tried first and returned ONE
    community for TWO_TRIANGLES: every node eventually sees the majority label
    through the bridge. On a graph a reader can see is two clusters, reporting
    one is worse than reporting none, so the algorithm was changed to greedy
    modularity -- which weighs internal edges against what chance predicts and
    therefore reads a single bridge as sparse."""

    def test_a_bridge_does_not_merge_two_clusters(self):
        adj = _adj(TWO_TRIANGLES)
        assert len(set(_label_propagation(adj, sorted(adj)).values())) == 2

    def test_a_longer_chain_between_clusters_still_separates(self):
        adj = _adj(TWO_TRIANGLES + [("b3", "c1"), ("c1", "c2"), ("c2", "c3"),
                                    ("c3", "c1")])
        comm = _label_propagation(adj, sorted(adj))
        assert comm["c1"] == comm["c2"] == comm["c3"]
        assert comm["c1"] != comm["a1"]


class TestLinkPrediction:
    def test_it_suggests_a_pair_that_shares_neighbours(self):
        # a and b both know x, y, z but not each other.
        adj = _adj([("a", "x"), ("a", "y"), ("a", "z"),
                    ("b", "x"), ("b", "y"), ("b", "z")])
        out = _predicted_links(adj, sorted(adj))
        top = {frozenset((l["source"], l["target"])) for l in out[:1]}
        assert frozenset(("a", "b")) in top

    def test_it_never_suggests_an_existing_edge(self):
        # Suggesting what the chart already draws is noise, not a prediction.
        adj = _adj(TWO_TRIANGLES)
        for link in _predicted_links(adj, sorted(adj)):
            assert link["target"] not in adj[link["source"]]

    def test_a_pair_with_no_shared_neighbours_is_not_suggested(self):
        adj = _adj([("a", "b"), ("c", "d")])
        assert _predicted_links(adj, sorted(adj)) == []

    def test_a_hub_neighbour_counts_for_less_than_a_selective_one(self):
        """Adamic-Adar, not a plain common-neighbour count: a shared neighbour
        connected to everyone says little about the pair, so it is discounted
        by 1/log(degree). Without that weighting these two pairs would tie."""
        pairs = [("a", "hub"), ("b", "hub"), ("p", "q1"), ("r", "q1")]
        pairs += [("hub", f"n{i}") for i in range(8)]     # hub is everyone's
        adj = _adj(pairs)
        out = {frozenset((l["source"], l["target"])): l["score"]
               for l in _predicted_links(adj, sorted(adj), limit=50)}
        assert out[frozenset(("p", "r"))] > out[frozenset(("a", "b"))]

    def test_the_suggestion_list_is_bounded(self):
        adj = _adj([(f"n{i}", "hub") for i in range(40)])
        assert len(_predicted_links(adj, sorted(adj), limit=10)) <= 10


class TestTheShaperShipsThem:
    """The widget payload is the only way these reach a user."""

    @pytest.fixture
    def net(self):
        df = pd.DataFrame(TWO_TRIANGLES, columns=["s", "t"])
        return shape_network(df, {"roles": {"category": "s", "category2": "t"}})

    def test_every_node_carries_its_community(self, net):
        assert all("community" in n for n in net["nodes"])
        assert net["communities"] == 2

    def test_predicted_links_are_kept_out_of_the_drawn_links(self, net):
        """An inferred edge rendered like an observed one would be the chart
        asserting something the data does not contain."""
        drawn = {frozenset((l["source"], l["target"])) for l in net["links"]}
        for s in net["suggested_links"]:
            assert frozenset((s["source"], s["target"])) not in drawn

    def test_the_existing_centralities_are_unchanged(self, net):
        # This shaper had four measures before; adding two must not disturb
        # them. a1 and b1 are the bridge, so they carry the betweenness.
        by_id = {n["id"]: n for n in net["nodes"]}
        assert by_id["a1"]["betweenness"] > by_id["a2"]["betweenness"]
        for key in ("degree", "closeness", "betweenness", "reach"):
            assert all(key in n for n in net["nodes"])
