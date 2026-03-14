"""Tests for simulation execution and result serialization.

Covers:
- ``src.simulation.runner.run_simulation``: execution and error handling.
- ``src.simulation.runner.save_results``: pickle serialization.
- ``src.simulation.runner.load_results``: deserialization and error handling.
"""

from pathlib import Path

import networkx as nx
import pytest
from uxsim import World

from src.simulation.demand import add_area_demand
from src.simulation.runner import load_results, run_simulation, save_results
from src.simulation.world import create_world


# ---------------------------------------------------------------------------
# Helper: create a minimal simulatable World
# ---------------------------------------------------------------------------


def _make_small_world(name: str = "test_runner") -> World:
    """Create a small 3-node World with demand for testing."""
    G = nx.DiGraph()
    G.add_node("A", x=139.700, y=35.700)
    G.add_node("B", x=139.710, y=35.700)
    G.add_node("C", x=139.720, y=35.690)
    G.add_edge("A", "B", length=1000, speed_kph=60, lanes=2, highway="primary")
    G.add_edge("B", "C", length=1200, speed_kph=50, lanes=2, highway="secondary")

    W = create_world(G, tmax=300, deltan=5, name=name)
    add_area_demand(
        W,
        origin_lon=139.700,
        origin_lat=35.700,
        dest_lon=139.720,
        dest_lat=35.690,
        t_start=0,
        t_end=200,
        volume=20,
        radius_deg=0.02,
    )
    return W


# ---------------------------------------------------------------------------
# run_simulation tests
# ---------------------------------------------------------------------------


class TestRunSimulation:
    """Tests for :func:`src.simulation.runner.run_simulation`."""

    def test_returns_world_after_completion(self) -> None:
        """run_simulation should return the same World object."""
        W = _make_small_world("run_test")
        result = run_simulation(W)
        assert result is W
        assert result.TIME is not None

    def test_simulation_completes_successfully(self) -> None:
        """Simulation should complete without errors."""
        W = _make_small_world("completion_test")
        W = run_simulation(W)
        assert len(W.LINKS) > 0


# ---------------------------------------------------------------------------
# save_results / load_results tests
# ---------------------------------------------------------------------------


class TestSaveLoadResults:
    """Tests for result serialization round-trip."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """save_results should create a pickle file at the specified path."""
        W = _make_small_world("save_test")
        run_simulation(W)

        output = tmp_path / "test_results.pkl"
        result_path = save_results(W, output)
        assert result_path.exists()
        assert result_path.stat().st_size > 0

    def test_save_default_path(self) -> None:
        """save_results with None path should use OUTPUT_DIR."""
        W = _make_small_world("default_path_test")
        run_simulation(W)

        result_path = save_results(W)
        assert result_path.exists()
        assert "default_path_test_results.pkl" in result_path.name
        # Cleanup
        result_path.unlink(missing_ok=True)

    def test_load_restores_world(self, tmp_path: Path) -> None:
        """load_results should restore a previously saved World."""
        W = _make_small_world("roundtrip_test")
        run_simulation(W)

        output = tmp_path / "roundtrip.pkl"
        save_results(W, output)

        loaded = load_results(output)
        assert hasattr(loaded, "LINKS")
        assert hasattr(loaded, "NODES")

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        """load_results on a missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Result file not found"):
            load_results(tmp_path / "missing.pkl")

    def test_save_creates_parent_directory(self, tmp_path: Path) -> None:
        """save_results should create parent directories if they don't exist."""
        W = _make_small_world("mkdir_test")
        run_simulation(W)

        output = tmp_path / "nested" / "dir" / "results.pkl"
        result_path = save_results(W, output)
        assert result_path.exists()
