"""Tests for OD demand generation.

Covers:
- ``src.simulation.demand.generate_default_demands``: region dispatch and
  error handling.
- ``src.simulation.demand.get_tokyo_od_pairs``: predefined Tokyo OD pairs.
"""

from unittest.mock import patch

import networkx as nx
import pytest
from uxsim import World

from src.simulation.demand import (
    generate_default_demands,
    get_tokyo_od_pairs,
)
from src.simulation.world import create_world


# ---------------------------------------------------------------------------
# Helper: create a minimal World
# ---------------------------------------------------------------------------


def _make_world_for_demand() -> World:
    """Create a small World for demand testing (no simulation)."""
    G = nx.DiGraph()
    G.add_node("A", x=139.700, y=35.700)
    G.add_node("B", x=139.720, y=35.700)
    G.add_node("C", x=139.700, y=35.680)
    G.add_edge("A", "B", length=2000, speed_kph=60, lanes=2, highway="motorway")
    G.add_edge("B", "C", length=2500, speed_kph=50, lanes=2, highway="trunk")
    G.add_edge("C", "A", length=2200, speed_kph=40, lanes=2, highway="primary")
    return create_world(G, tmax=300, deltan=5, name="demand_test")


# ---------------------------------------------------------------------------
# get_tokyo_od_pairs tests
# ---------------------------------------------------------------------------


class TestGetTokyoOdPairs:
    """Tests for :func:`src.simulation.demand.get_tokyo_od_pairs`."""

    def test_returns_list(self) -> None:
        """Must return a list of dictionaries."""
        pairs = get_tokyo_od_pairs()
        assert isinstance(pairs, list)
        assert len(pairs) > 0

    def test_pair_has_required_keys(self) -> None:
        """Each OD pair must contain all required keys."""
        required_keys = {
            "origin_lon",
            "origin_lat",
            "dest_lon",
            "dest_lat",
            "t_start",
            "t_end",
            "volume",
            "radius_deg",
        }
        for pair in get_tokyo_od_pairs():
            missing = required_keys - set(pair)
            assert not missing, f"Missing keys: {missing}"

    def test_volumes_are_positive(self) -> None:
        """All OD pair volumes must be positive."""
        for pair in get_tokyo_od_pairs():
            assert pair["volume"] > 0

    def test_time_windows_valid(self) -> None:
        """All OD pairs must have t_end > t_start."""
        for pair in get_tokyo_od_pairs():
            assert pair["t_end"] > pair["t_start"]

    def test_coordinates_in_tokyo_region(self) -> None:
        """All coordinates should be in the greater Tokyo area."""
        for pair in get_tokyo_od_pairs():
            for key in ("origin_lon", "dest_lon"):
                assert 139.0 < pair[key] < 141.0, (
                    f"{key}={pair[key]} outside Tokyo longitude range"
                )
            for key in ("origin_lat", "dest_lat"):
                assert 35.0 < pair[key] < 36.5, (
                    f"{key}={pair[key]} outside Tokyo latitude range"
                )

    def test_eight_pairs_defined(self) -> None:
        """Spec requires 8 predefined OD pairs for Tokyo."""
        assert len(get_tokyo_od_pairs()) == 8


# ---------------------------------------------------------------------------
# generate_default_demands tests
# ---------------------------------------------------------------------------


class TestGenerateDefaultDemands:
    """Tests for :func:`src.simulation.demand.generate_default_demands`."""

    def test_unknown_region_raises(self) -> None:
        """Unknown region must raise ValueError."""
        W = _make_world_for_demand()
        with pytest.raises(ValueError, match="Unknown region"):
            generate_default_demands(W, region="nonexistent")

    @patch("src.simulation.demand.add_area_demand")
    def test_tokyo_region_accepted(self, mock_add: object) -> None:
        """'tokyo' must be a valid region that doesn't raise."""
        W = _make_world_for_demand()
        generate_default_demands(W, region="tokyo")
        assert mock_add.call_count == 8

    @patch("src.simulation.demand.add_area_demand")
    def test_case_insensitive_region(self, mock_add: object) -> None:
        """Region name should be case-insensitive."""
        W = _make_world_for_demand()
        generate_default_demands(W, region="Tokyo")
        generate_default_demands(W, region="TOKYO")
        assert mock_add.call_count == 16
