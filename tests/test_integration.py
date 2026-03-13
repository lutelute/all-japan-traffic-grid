"""Integration tests for the traffic simulation pipeline.

Verifies that adjacent pipeline stages interoperate correctly using
synthetic data from :mod:`tests.conftest`.  All tests use small in-memory
data and require no network access or real PBF files.

Pipeline stages tested:

1. **Parse → Build**: GeoDataFrame (nodes + edges) converts to a valid
   NetworkX :class:`~networkx.DiGraph` with expected attributes.
2. **Build → Simulate**: A constructed graph creates a runnable UXsim
   :class:`~uxsim.World` that can execute a short simulation.
3. **Simulate → Export**: Simulation results serialize to valid GeoJSON
   with the correct ``FeatureCollection`` structure.
4. **Full Pipeline (synthetic)**: End-to-end from synthetic network →
   graph → World → simulate → export.
"""

import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import LineString
from uxsim import World

from src.network.builder import build_graph
from src.simulation.demand import add_area_demand
from src.simulation.runner import run_simulation
from src.simulation.world import create_world
from src.visualization.export import extract_link_congestion, to_geojson


# ---------------------------------------------------------------------------
# Parse → Build integration tests
# ---------------------------------------------------------------------------


class TestParseToBuild:
    """Verify that parsed GeoDataFrames convert to a valid NetworkX graph.

    Simulates the output of :func:`src.data.parser.parse_road_network` using
    the synthetic fixtures from :mod:`tests.conftest` and feeds them into
    :func:`src.network.builder.build_graph`.
    """

    @pytest.fixture()
    def graph(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> nx.DiGraph:
        """Build a graph from the synthetic GeoDataFrame fixtures."""
        return build_graph(sample_nodes_gdf, sample_edges_gdf)

    def test_returns_digraph(self, graph: nx.DiGraph) -> None:
        """build_graph must return a NetworkX DiGraph."""
        assert isinstance(graph, nx.DiGraph)

    def test_node_count_matches(
        self,
        graph: nx.DiGraph,
        sample_nodes_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Graph node count must equal the input GeoDataFrame row count."""
        assert graph.number_of_nodes() == len(sample_nodes_gdf)

    def test_edge_count_matches(
        self,
        graph: nx.DiGraph,
        sample_edges_gdf: gpd.GeoDataFrame,
    ) -> None:
        """Graph edge count must equal the input GeoDataFrame row count."""
        assert graph.number_of_edges() == len(sample_edges_gdf)

    def test_nodes_have_coordinates(self, graph: nx.DiGraph) -> None:
        """Every node in the built graph must have 'x' and 'y' attributes."""
        for node_id, attrs in graph.nodes(data=True):
            assert "x" in attrs, f"Node {node_id} missing 'x'"
            assert "y" in attrs, f"Node {node_id} missing 'y'"

    def test_edges_have_required_attributes(self, graph: nx.DiGraph) -> None:
        """Every edge must carry length, speed_kph, lanes, highway, and geometry."""
        required_keys = {"length", "speed_kph", "lanes", "highway", "geometry"}
        for u, v, attrs in graph.edges(data=True):
            missing = required_keys - set(attrs)
            assert not missing, (
                f"Edge ({u}, {v}) missing attributes: {missing}"
            )

    def test_edge_lengths_positive(self, graph: nx.DiGraph) -> None:
        """All edge lengths must be positive (in meters)."""
        for u, v, attrs in graph.edges(data=True):
            assert attrs["length"] > 0, f"Edge ({u}, {v}) has non-positive length"

    def test_edge_geometries_are_linestrings(self, graph: nx.DiGraph) -> None:
        """All edge geometries must be LineString instances."""
        for _, _, attrs in graph.edges(data=True):
            assert isinstance(attrs["geometry"], LineString)


# ---------------------------------------------------------------------------
# Build → Simulate integration tests
# ---------------------------------------------------------------------------


class TestBuildToSimulate:
    """Verify that a constructed graph creates a runnable UXsim World.

    Tests the transition from :func:`src.network.builder.build_graph` output
    to :func:`src.simulation.world.create_world` and a short simulation run.
    """

    @pytest.fixture()
    def world(self, sample_networkx_graph: nx.DiGraph) -> World:
        """Create a UXsim World from the sample graph fixture."""
        return create_world(
            sample_networkx_graph,
            tmax=300,
            deltan=5,
            name="integration_test",
        )

    def test_world_is_uxsim_world(self, world: World) -> None:
        """create_world must return a UXsim World instance."""
        assert isinstance(world, World)

    def test_world_node_count(
        self,
        world: World,
        sample_networkx_graph: nx.DiGraph,
    ) -> None:
        """UXsim World node count must match the input graph."""
        assert len(world.NODES) == sample_networkx_graph.number_of_nodes()

    def test_world_link_count(
        self,
        world: World,
        sample_networkx_graph: nx.DiGraph,
    ) -> None:
        """UXsim World link count must match the input graph edge count."""
        assert len(world.LINKS) == sample_networkx_graph.number_of_edges()

    def test_simulation_runs_to_completion(self, world: World) -> None:
        """A UXsim World built from a valid graph must run without errors.

        Adds a small demand between nodes in the fixture's bounding box
        and verifies the simulation executes to ``tmax``.
        """
        add_area_demand(
            world,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=200,
            volume=30,
            radius_deg=0.02,
        )

        world.exec_simulation()

        # Simulation must have advanced through time
        assert world.TIME is not None

    def test_simulation_produces_links_with_data(
        self, sample_networkx_graph: nx.DiGraph
    ) -> None:
        """After simulation, links must have cumulative arrival/departure data."""
        W = create_world(
            sample_networkx_graph,
            tmax=300,
            deltan=5,
            name="link_data_test",
        )

        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=200,
            volume=30,
            radius_deg=0.02,
        )

        W.exec_simulation()

        # At least some links should exist
        assert len(W.LINKS) > 0

        # Links should have cumulative data attributes after simulation
        for link in W.LINKS:
            assert hasattr(link, "cum_arrival")
            assert hasattr(link, "cum_departure")


# ---------------------------------------------------------------------------
# Simulate → Export integration tests
# ---------------------------------------------------------------------------


class TestSimulateToExport:
    """Verify that simulation results serialize to valid GeoJSON.

    Runs a small simulation and feeds the completed World through
    :func:`src.visualization.export.extract_link_congestion` and
    :func:`src.visualization.export.to_geojson`.
    """

    @pytest.fixture()
    def completed_world(self, sample_networkx_graph: nx.DiGraph) -> World:
        """Run a short simulation and return the completed World."""
        W = create_world(
            sample_networkx_graph,
            tmax=300,
            deltan=5,
            name="export_test",
        )

        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=200,
            volume=30,
            radius_deg=0.02,
        )

        W.exec_simulation()
        return W

    @pytest.fixture()
    def congestion_data(self, completed_world: World) -> list[dict]:
        """Extract link congestion data from the completed simulation."""
        return extract_link_congestion(completed_world)

    @pytest.fixture()
    def geojson_path(
        self,
        congestion_data: list[dict],
        tmp_output_dir: Path,
    ) -> Path:
        """Write congestion data to GeoJSON and return the file path."""
        output = tmp_output_dir / "integration_congestion.geojson"
        to_geojson(congestion_data, output)
        return output

    @pytest.fixture()
    def geojson_data(self, geojson_path: Path) -> dict:
        """Load the GeoJSON file as a Python dictionary."""
        with open(geojson_path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_congestion_data_not_empty(
        self, congestion_data: list[dict]
    ) -> None:
        """extract_link_congestion must return at least one link result."""
        assert len(congestion_data) > 0

    def test_congestion_entries_have_required_keys(
        self, congestion_data: list[dict]
    ) -> None:
        """Each congestion entry must contain all required fields."""
        required_keys = {
            "name",
            "coords",
            "congestion_level",
            "average_speed",
            "volume",
            "free_flow_speed",
            "capacity",
        }
        for entry in congestion_data:
            missing = required_keys - set(entry)
            assert not missing, f"Entry '{entry.get('name')}' missing keys: {missing}"

    def test_congestion_levels_in_range(
        self, congestion_data: list[dict]
    ) -> None:
        """All congestion_level values must be in [0.0, 1.0]."""
        for entry in congestion_data:
            level = entry["congestion_level"]
            assert 0.0 <= level <= 1.0, (
                f"Link '{entry['name']}' has congestion_level={level} "
                f"outside [0, 1]"
            )

    def test_geojson_is_feature_collection(self, geojson_data: dict) -> None:
        """GeoJSON root type must be 'FeatureCollection'."""
        assert geojson_data["type"] == "FeatureCollection"

    def test_geojson_feature_count(
        self,
        geojson_data: dict,
        congestion_data: list[dict],
    ) -> None:
        """Number of GeoJSON features must match the congestion data."""
        assert len(geojson_data["features"]) == len(congestion_data)

    def test_geojson_features_are_linestrings(
        self, geojson_data: dict
    ) -> None:
        """Every GeoJSON feature geometry must be a LineString."""
        for feature in geojson_data["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "LineString"

    def test_geojson_features_have_coordinates(
        self, geojson_data: dict
    ) -> None:
        """Every LineString geometry must have at least 2 coordinate pairs."""
        for feature in geojson_data["features"]:
            coords = feature["geometry"]["coordinates"]
            assert isinstance(coords, list)
            assert len(coords) >= 2

    def test_geojson_properties_complete(self, geojson_data: dict) -> None:
        """Every feature must have all required congestion properties."""
        required_props = {
            "name",
            "congestion_level",
            "average_speed",
            "volume",
            "free_flow_speed",
            "capacity",
        }
        for feature in geojson_data["features"]:
            props = feature["properties"]
            missing = required_props - set(props)
            assert not missing, (
                f"Feature '{props.get('name')}' missing properties: {missing}"
            )

    def test_geojson_file_is_valid_json(self, geojson_path: Path) -> None:
        """The written GeoJSON file must be parseable as valid JSON."""
        with open(geojson_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert "type" in data
        assert "features" in data


# ---------------------------------------------------------------------------
# Full pipeline integration test (synthetic)
# ---------------------------------------------------------------------------


class TestFullPipelineSynthetic:
    """End-to-end pipeline: synthetic network → graph → World → simulate → export.

    Exercises the complete pipeline from GeoDataFrame construction through
    simulation execution and GeoJSON serialization, using only synthetic
    data with no network access.
    """

    def test_full_pipeline_synthetic(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
        tmp_output_dir: Path,
    ) -> None:
        """Complete pipeline must execute without errors and produce valid output.

        Steps:
            1. Build NetworkX graph from synthetic GeoDataFrames.
            2. Create UXsim World from the graph.
            3. Add traffic demand.
            4. Run simulation.
            5. Extract congestion data.
            6. Export to GeoJSON.
            7. Verify output structure and values.
        """
        # --- Step 1: Build graph from synthetic GeoDataFrames ---
        graph = build_graph(sample_nodes_gdf, sample_edges_gdf)
        assert isinstance(graph, nx.DiGraph)
        assert graph.number_of_nodes() == len(sample_nodes_gdf)
        assert graph.number_of_edges() == len(sample_edges_gdf)

        # --- Step 2: Create UXsim World ---
        W = create_world(
            graph,
            tmax=300,
            deltan=5,
            name="full_pipeline_test",
        )
        assert isinstance(W, World)
        assert len(W.NODES) == graph.number_of_nodes()
        assert len(W.LINKS) == graph.number_of_edges()

        # --- Step 3: Add traffic demand ---
        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=200,
            volume=30,
            radius_deg=0.02,
        )

        # --- Step 4: Run simulation ---
        W = run_simulation(W)
        assert W.TIME is not None

        # --- Step 5: Extract congestion data ---
        congestion_data = extract_link_congestion(W)
        assert len(congestion_data) > 0

        for entry in congestion_data:
            assert 0.0 <= entry["congestion_level"] <= 1.0
            assert entry["average_speed"] >= 0.0
            assert entry["free_flow_speed"] > 0.0
            assert len(entry["coords"]) >= 2

        # --- Step 6: Export to GeoJSON ---
        geojson_path = tmp_output_dir / "full_pipeline.geojson"
        result_path = to_geojson(congestion_data, geojson_path)
        assert result_path.exists()

        # --- Step 7: Verify GeoJSON structure ---
        with open(result_path, encoding="utf-8") as fh:
            geojson = json.load(fh)

        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == len(congestion_data)

        for feature in geojson["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "LineString"
            assert len(feature["geometry"]["coordinates"]) >= 2

            props = feature["properties"]
            assert "congestion_level" in props
            assert "average_speed" in props
            assert "volume" in props
            assert "free_flow_speed" in props
            assert "capacity" in props
            assert "name" in props

    def test_full_pipeline_congestion_values_are_numeric(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
        tmp_output_dir: Path,
    ) -> None:
        """All congestion metrics in the exported GeoJSON must be numeric."""
        graph = build_graph(sample_nodes_gdf, sample_edges_gdf)
        W = create_world(graph, tmax=300, deltan=5, name="numeric_check")

        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=200,
            volume=30,
            radius_deg=0.02,
        )

        W.exec_simulation()

        congestion_data = extract_link_congestion(W)
        geojson_path = tmp_output_dir / "numeric_check.geojson"
        to_geojson(congestion_data, geojson_path)

        with open(geojson_path, encoding="utf-8") as fh:
            geojson = json.load(fh)

        for feature in geojson["features"]:
            props = feature["properties"]
            assert isinstance(props["congestion_level"], (int, float))
            assert isinstance(props["average_speed"], (int, float))
            assert isinstance(props["volume"], (int, float))
            assert isinstance(props["free_flow_speed"], (int, float))
            assert isinstance(props["capacity"], (int, float))

    def test_full_pipeline_geojson_coordinates_in_degrees(
        self,
        sample_nodes_gdf: gpd.GeoDataFrame,
        sample_edges_gdf: gpd.GeoDataFrame,
        tmp_output_dir: Path,
    ) -> None:
        """GeoJSON coordinates must be in degrees (not meters).

        Longitude values around Tokyo should be ~139–140°; latitude ~35–36°.
        Values in meters (e.g. 12_500_000) would indicate a conversion error.
        """
        graph = build_graph(sample_nodes_gdf, sample_edges_gdf)
        W = create_world(graph, tmax=300, deltan=5, name="coords_check")

        add_area_demand(
            W,
            origin_lon=139.700,
            origin_lat=35.700,
            dest_lon=139.720,
            dest_lat=35.680,
            t_start=0,
            t_end=200,
            volume=30,
            radius_deg=0.02,
        )

        W.exec_simulation()

        congestion_data = extract_link_congestion(W)
        geojson_path = tmp_output_dir / "coords_check.geojson"
        to_geojson(congestion_data, geojson_path)

        with open(geojson_path, encoding="utf-8") as fh:
            geojson = json.load(fh)

        for feature in geojson["features"]:
            for lon, lat in feature["geometry"]["coordinates"]:
                assert 130.0 < lon < 150.0, (
                    f"Longitude {lon} appears to be in meters, not degrees"
                )
                assert 30.0 < lat < 40.0, (
                    f"Latitude {lat} appears to be in meters, not degrees"
                )
