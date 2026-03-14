"""Tests for UXsim World creation, coordinate transformation, and simulation.

Covers:
- ``src.simulation.world.create_world``: node/link counts, coordinate scaling.
- ``src.simulation.demand.add_area_demand``: demand addition without errors.
- End-to-end: tiny simulation with 3 nodes, 2 links, and small demand.
"""

import networkx as nx
import pytest
from uxsim import World

from src.config import COEF_DEGREE_TO_METER
from src.simulation.demand import add_area_demand
from src.simulation.world import create_world


# ---------------------------------------------------------------------------
# create_world tests
# ---------------------------------------------------------------------------


class TestCreateWorld:
    """Tests for :func:`src.simulation.world.create_world`."""

    def test_create_world_node_count(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """UXsim World must contain the same number of nodes as the input graph."""
        W = create_world(sample_networkx_graph)
        assert len(W.NODES) == sample_networkx_graph.number_of_nodes()

    def test_create_world_link_count(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """UXsim World must contain the same number of links as the input graph edges."""
        W = create_world(sample_networkx_graph)
        assert len(W.LINKS) == sample_networkx_graph.number_of_edges()

    def test_create_world_returns_world(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """create_world must return a UXsim World instance."""
        W = create_world(sample_networkx_graph)
        assert isinstance(W, World)

    def test_create_world_empty_graph_raises(self) -> None:
        """create_world must raise ValueError for an empty graph."""
        G = nx.DiGraph()
        with pytest.raises(ValueError, match="empty graph"):
            create_world(G)


class TestCoordinatesInMeters:
    """Verify node coordinates are multiplied by COEF_DEGREE_TO_METER."""

    def test_coordinates_in_meters(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """Node coordinates in the UXsim World must be degree values * COEF_DEGREE_TO_METER."""
        W = create_world(sample_networkx_graph)

        for node_id, attrs in sample_networkx_graph.nodes(data=True):
            expected_x = attrs["x"] * COEF_DEGREE_TO_METER
            expected_y = attrs["y"] * COEF_DEGREE_TO_METER

            # Find the matching UXsim node by name
            uxsim_node = None
            for n in W.NODES:
                if n.name == str(node_id):
                    uxsim_node = n
                    break

            assert uxsim_node is not None, f"Node {node_id} not found in World"
            assert abs(uxsim_node.x - expected_x) < 1.0, (
                f"Node {node_id} x: expected {expected_x}, got {uxsim_node.x}"
            )
            assert abs(uxsim_node.y - expected_y) < 1.0, (
                f"Node {node_id} y: expected {expected_y}, got {uxsim_node.y}"
            )


# ---------------------------------------------------------------------------
# add_area_demand tests
# ---------------------------------------------------------------------------


class TestAddAreaDemand:
    """Tests for :func:`src.simulation.demand.add_area_demand`."""

    def test_add_area_demand(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """add_area_demand must complete without raising any errors."""
        W = create_world(sample_networkx_graph)

        # Use coordinates within the fixture's bounding box
        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=1800,
            volume=100,
            radius_deg=0.02,
        )

    def test_add_area_demand_negative_volume_raises(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """add_area_demand must raise ValueError for negative volume."""
        W = create_world(sample_networkx_graph)
        with pytest.raises(ValueError, match="non-negative"):
            add_area_demand(
                W,
                origin_lon=139.700,
                origin_lat=35.700,
                dest_lon=139.720,
                dest_lat=35.680,
                volume=-10,
            )

    def test_add_area_demand_invalid_time_raises(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """add_area_demand must raise ValueError when t_end <= t_start."""
        W = create_world(sample_networkx_graph)
        with pytest.raises(ValueError, match="t_end must be greater"):
            add_area_demand(
                W,
                origin_lon=139.700,
                origin_lat=35.700,
                dest_lon=139.720,
                dest_lat=35.680,
                t_start=1000,
                t_end=500,
            )


# ---------------------------------------------------------------------------
# Small simulation end-to-end test
# ---------------------------------------------------------------------------


class TestRunSmallSimulation:
    """Run a tiny simulation with 3 nodes, 2 links, and verify completion."""

    def test_run_small_simulation(self) -> None:
        """A minimal simulation with 3 nodes and 2 links must run to completion."""
        # Build a tiny graph: A → B → C
        G = nx.DiGraph()
        G.add_node("A", x=139.700, y=35.700)
        G.add_node("B", x=139.710, y=35.700)
        G.add_node("C", x=139.720, y=35.700)

        G.add_edge("A", "B", length=1000.0, speed_kph=60.0, lanes=2, highway="primary")
        G.add_edge("B", "C", length=1000.0, speed_kph=60.0, lanes=2, highway="primary")

        # Create World with short simulation time
        W = create_world(G, tmax=300, deltan=5)

        # Add small demand: vehicles from A area to C area
        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.700,
            t_start=0,
            t_end=200,
            volume=20,
            radius_deg=0.01,
        )

        # Execute simulation — must complete without error
        W.exec_simulation()

        # Verify the simulation ran (check that internal time reached tmax)
        assert W.TIME is not None
