"""Tests for graph construction and network simplification.

Covers:
- ``src.network.builder.build_graph``: node/edge counts, attributes.
- ``src.network.simplify.merge_nearby_nodes``: node count reduction.
- ``src.network.simplify.remove_dead_ends``: dead-end removal.
- ``src.network.simplify.extract_largest_component``: connectivity.
"""

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import LineString

from src.network.builder import build_graph
from src.network.simplify import (
    extract_largest_component,
    merge_nearby_nodes,
    remove_dead_ends,
)


# ---------------------------------------------------------------------------
# build_graph tests
# ---------------------------------------------------------------------------


class TestBuildGraph:
    """Tests for :func:`src.network.builder.build_graph`."""

    def test_node_count(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Graph must contain the same number of nodes as the input GeoDataFrame."""
        G = build_graph(sample_nodes_gdf, sample_edges_gdf)
        assert G.number_of_nodes() == len(sample_nodes_gdf)

    def test_edge_count(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Graph must contain the same number of edges as the input GeoDataFrame."""
        G = build_graph(sample_nodes_gdf, sample_edges_gdf)
        assert G.number_of_edges() == len(sample_edges_gdf)

    def test_is_directed(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> None:
        """build_graph must return a directed graph."""
        G = build_graph(sample_nodes_gdf, sample_edges_gdf)
        assert isinstance(G, nx.DiGraph)

    def test_node_ids_match(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Graph node IDs must match the input GeoDataFrame 'id' column."""
        G = build_graph(sample_nodes_gdf, sample_edges_gdf)
        expected_ids = set(sample_nodes_gdf["id"])
        assert set(G.nodes()) == expected_ids

    def test_edge_endpoints_match(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Graph edge endpoints must correspond to input GeoDataFrame u/v."""
        G = build_graph(sample_nodes_gdf, sample_edges_gdf)
        expected_edges = set(
            zip(sample_edges_gdf["u"], sample_edges_gdf["v"], strict=False)
        )
        assert set(G.edges()) == expected_edges


class TestGraphAttributes:
    """Verify that nodes and edges carry all required attributes."""

    @pytest.fixture()
    def graph(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> nx.DiGraph:
        """Build a graph from the sample fixtures."""
        return build_graph(sample_nodes_gdf, sample_edges_gdf)

    def test_node_x_attribute(self, graph: nx.DiGraph) -> None:
        """Every node must have an 'x' (longitude) attribute."""
        for _, attrs in graph.nodes(data=True):
            assert "x" in attrs

    def test_node_y_attribute(self, graph: nx.DiGraph) -> None:
        """Every node must have a 'y' (latitude) attribute."""
        for _, attrs in graph.nodes(data=True):
            assert "y" in attrs

    def test_edge_length_attribute(self, graph: nx.DiGraph) -> None:
        """Every edge must have a 'length' attribute (positive meters)."""
        for u, v, attrs in graph.edges(data=True):
            assert "length" in attrs
            assert attrs["length"] > 0, f"Edge ({u}, {v}) has non-positive length"

    def test_edge_speed_kph_attribute(self, graph: nx.DiGraph) -> None:
        """Every edge must have a 'speed_kph' attribute (positive km/h)."""
        for u, v, attrs in graph.edges(data=True):
            assert "speed_kph" in attrs
            assert attrs["speed_kph"] > 0, f"Edge ({u}, {v}) has non-positive speed"

    def test_edge_lanes_attribute(self, graph: nx.DiGraph) -> None:
        """Every edge must have a 'lanes' attribute (positive integer)."""
        for u, v, attrs in graph.edges(data=True):
            assert "lanes" in attrs
            assert attrs["lanes"] > 0, f"Edge ({u}, {v}) has non-positive lanes"

    def test_edge_highway_attribute(self, graph: nx.DiGraph) -> None:
        """Every edge must have a 'highway' attribute (non-empty string)."""
        for _, _, attrs in graph.edges(data=True):
            assert "highway" in attrs
            assert isinstance(attrs["highway"], str)
            assert len(attrs["highway"]) > 0

    def test_edge_geometry_attribute(self, graph: nx.DiGraph) -> None:
        """Every edge must have a 'geometry' attribute (LineString)."""
        for _, _, attrs in graph.edges(data=True):
            assert "geometry" in attrs
            assert isinstance(attrs["geometry"], LineString)

    def test_node_coordinates_are_numeric(self, graph: nx.DiGraph) -> None:
        """Node x and y values must be float or int."""
        for _, attrs in graph.nodes(data=True):
            assert isinstance(attrs["x"], (int, float))
            assert isinstance(attrs["y"], (int, float))


# ---------------------------------------------------------------------------
# merge_nearby_nodes tests
# ---------------------------------------------------------------------------


class TestMergeNearbyNodes:
    """Tests for :func:`src.network.simplify.merge_nearby_nodes`."""

    def test_no_merge_with_small_threshold(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """With a very small threshold no nodes should be merged."""
        result = merge_nearby_nodes(sample_networkx_graph, threshold=1e-10)
        assert result.number_of_nodes() == sample_networkx_graph.number_of_nodes()

    def test_node_count_reduction(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """With a large enough threshold, some nodes must be merged."""
        # Nodes in the fixture are 0.01–0.03 degrees apart; a threshold of
        # 0.025 should cluster at least some pairs.
        result = merge_nearby_nodes(sample_networkx_graph, threshold=0.025)
        assert result.number_of_nodes() < sample_networkx_graph.number_of_nodes()

    def test_all_merge_with_huge_threshold(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """With a very large threshold all nodes merge into one (no edges)."""
        result = merge_nearby_nodes(sample_networkx_graph, threshold=1e6)
        assert result.number_of_nodes() == 1
        assert result.number_of_edges() == 0  # all become self-loops, which are dropped

    def test_returns_new_graph(self, sample_networkx_graph: nx.DiGraph) -> None:
        """merge_nearby_nodes must not modify the input graph."""
        original_node_count = sample_networkx_graph.number_of_nodes()
        merge_nearby_nodes(sample_networkx_graph, threshold=0.025)
        assert sample_networkx_graph.number_of_nodes() == original_node_count

    def test_merged_nodes_have_coordinates(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """All nodes in the merged graph must retain x/y attributes."""
        result = merge_nearby_nodes(sample_networkx_graph, threshold=0.025)
        for _, attrs in result.nodes(data=True):
            assert "x" in attrs
            assert "y" in attrs


# ---------------------------------------------------------------------------
# remove_dead_ends tests
# ---------------------------------------------------------------------------


class TestRemoveDeadEnds:
    """Tests for :func:`src.network.simplify.remove_dead_ends`."""

    def test_dead_end_removal(self, sample_networkx_graph: nx.DiGraph) -> None:
        """Dead-end nodes (N7, N8 — in-degree + out-degree ≤ 1) must be removed.

        The fixture has N7 (out-degree 1, in-degree 0) and
        N8 (out-degree 1, in-degree 0) as dead-end nodes.
        """
        result = remove_dead_ends(sample_networkx_graph)
        assert result.number_of_nodes() < sample_networkx_graph.number_of_nodes()

    def test_removes_specific_dead_ends(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """Nodes 1007 and 1008 are dead-ends and must not appear in the result."""
        result = remove_dead_ends(sample_networkx_graph)
        assert 1007 not in result.nodes()
        assert 1008 not in result.nodes()

    def test_preserves_connected_nodes(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """Core strongly connected nodes must survive dead-end removal."""
        result = remove_dead_ends(sample_networkx_graph)
        # Nodes 1001–1006 form a cycle and should all remain
        for node_id in [1001, 1002, 1003, 1004, 1005, 1006]:
            assert node_id in result.nodes(), f"Node {node_id} was incorrectly removed"

    def test_returns_new_graph(self, sample_networkx_graph: nx.DiGraph) -> None:
        """remove_dead_ends must not modify the input graph."""
        original_node_count = sample_networkx_graph.number_of_nodes()
        remove_dead_ends(sample_networkx_graph)
        assert sample_networkx_graph.number_of_nodes() == original_node_count

    def test_fully_connected_graph_unchanged(self) -> None:
        """A graph with no dead-ends should not lose any nodes."""
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 3)
        G.add_edge(3, 1)
        result = remove_dead_ends(G)
        assert result.number_of_nodes() == 3


# ---------------------------------------------------------------------------
# extract_largest_component tests
# ---------------------------------------------------------------------------


class TestExtractLargestComponent:
    """Tests for :func:`src.network.simplify.extract_largest_component`."""

    def test_connectivity(self, sample_networkx_graph: nx.DiGraph) -> None:
        """The result must be strongly connected."""
        result = extract_largest_component(sample_networkx_graph)
        assert nx.is_strongly_connected(result)

    def test_largest_component_size(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """Largest SCC of the fixture should have fewer nodes than the full graph.

        The fixture has 8 nodes but only 6 form the largest SCC (N1–N6);
        N7 and N8 are not part of any cycle.
        """
        result = extract_largest_component(sample_networkx_graph)
        assert result.number_of_nodes() < sample_networkx_graph.number_of_nodes()

    def test_preserves_scc_nodes(self, sample_networkx_graph: nx.DiGraph) -> None:
        """Nodes in the largest SCC (1001–1004) must be preserved."""
        result = extract_largest_component(sample_networkx_graph)
        # The 4-node cycle N1→N2→N4→N3→N1 is definitely strongly connected
        for node_id in [1001, 1002, 1003, 1004]:
            assert node_id in result.nodes(), (
                f"Node {node_id} missing from largest SCC"
            )

    def test_empty_graph(self) -> None:
        """An empty graph should return an empty graph."""
        G = nx.DiGraph()
        result = extract_largest_component(G)
        assert result.number_of_nodes() == 0
        assert result.number_of_edges() == 0

    def test_single_component_unchanged(self) -> None:
        """A fully strongly connected graph should be returned unchanged."""
        G = nx.DiGraph()
        G.add_edge(1, 2)
        G.add_edge(2, 3)
        G.add_edge(3, 1)
        for n in G.nodes():
            G.nodes[n]["x"] = 0.0
            G.nodes[n]["y"] = 0.0
        result = extract_largest_component(G)
        assert result.number_of_nodes() == 3
        assert result.number_of_edges() == 3

    def test_returns_new_graph(self, sample_networkx_graph: nx.DiGraph) -> None:
        """extract_largest_component must not modify the input graph."""
        original_count = sample_networkx_graph.number_of_nodes()
        extract_largest_component(sample_networkx_graph)
        assert sample_networkx_graph.number_of_nodes() == original_count
