"""Shared pytest fixtures for all-japan-traffic-grid tests.

Provides reusable synthetic test data (GeoDataFrames, NetworkX graphs, and
temporary directories) so that individual test modules can focus on logic
rather than data setup.  All fixtures use synthetic data — no real PBF files
are required.

The test network models a small fragment of Tokyo-area roads with 8 nodes
and 10 directed edges spanning all 8 highway types defined in
:data:`src.config.HIGHWAY_FILTER`.  The topology includes a strongly
connected component (6 nodes) and two dead-end nodes, making it suitable
for testing graph simplification routines.
"""

from pathlib import Path

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import LineString, Point


# ---------------------------------------------------------------------------
# Node definitions (Tokyo-area coordinates, EPSG:4326)
# ---------------------------------------------------------------------------
# Layout:
#
#          N8 (139.710, 35.710)
#           |
#  N7------N1------N2------N6
# (dead)   |  \    |       |
#           |   N5--+-------+
#           |    |  |
#          N3------N4
#
# Strongly connected component: {N1, N2, N3, N4, N5, N6}
# Dead-end nodes: N7 (out-degree 1), N8 (out-degree 1)

_NODE_DATA: list[dict] = [
    {"id": 1001, "lon": 139.700, "lat": 35.700},
    {"id": 1002, "lon": 139.720, "lat": 35.700},
    {"id": 1003, "lon": 139.700, "lat": 35.680},
    {"id": 1004, "lon": 139.720, "lat": 35.680},
    {"id": 1005, "lon": 139.710, "lat": 35.690},
    {"id": 1006, "lon": 139.730, "lat": 35.690},
    {"id": 1007, "lon": 139.690, "lat": 35.690},
    {"id": 1008, "lon": 139.710, "lat": 35.710},
]

# ---------------------------------------------------------------------------
# Edge definitions
# ---------------------------------------------------------------------------
# 10 directed edges covering all 8 highway types from HIGHWAY_FILTER.
# The 6-node cycle ensures a strongly connected component; N7 and N8 are
# dead-end stubs.

_EDGE_DATA: list[dict] = [
    {"u": 1001, "v": 1002, "highway": "motorway", "maxspeed": "100", "lanes": "4"},
    {"u": 1002, "v": 1004, "highway": "trunk", "maxspeed": "60", "lanes": "3"},
    {"u": 1004, "v": 1003, "highway": "primary", "maxspeed": "50", "lanes": "2"},
    {"u": 1003, "v": 1001, "highway": "secondary", "maxspeed": "40", "lanes": "2"},
    {"u": 1001, "v": 1005, "highway": "motorway_link", "maxspeed": "60", "lanes": "1"},
    {"u": 1005, "v": 1004, "highway": "trunk_link", "maxspeed": "40", "lanes": "1"},
    {"u": 1002, "v": 1006, "highway": "primary_link", "maxspeed": "30", "lanes": "1"},
    {"u": 1006, "v": 1004, "highway": "secondary_link", "maxspeed": "30", "lanes": "1"},
    {"u": 1007, "v": 1003, "highway": "secondary", "maxspeed": "40", "lanes": "2"},
    {"u": 1008, "v": 1002, "highway": "trunk", "maxspeed": "60", "lanes": "3"},
]


# ---------------------------------------------------------------------------
# Fixtures — GeoDataFrames
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_nodes_gdf() -> gpd.GeoDataFrame:
    """Small GeoDataFrame with 8 test nodes around Tokyo.

    Columns: ``id``, ``geometry`` (Point in EPSG:4326).
    Compatible with :func:`src.network.builder.build_graph`.
    """
    ids = [n["id"] for n in _NODE_DATA]
    geometries = [Point(n["lon"], n["lat"]) for n in _NODE_DATA]
    gdf = gpd.GeoDataFrame({"id": ids}, geometry=geometries, crs="EPSG:4326")
    return gdf


@pytest.fixture()
def sample_edges_gdf() -> gpd.GeoDataFrame:
    """Small GeoDataFrame with 10 test edges spanning all 8 highway types.

    Columns: ``u``, ``v``, ``highway``, ``maxspeed``, ``lanes``,
    ``geometry`` (LineString in EPSG:4326).
    Compatible with :func:`src.network.builder.build_graph`.
    """
    # Build a coordinate lookup from node data
    coords = {n["id"]: (n["lon"], n["lat"]) for n in _NODE_DATA}

    records: list[dict] = []
    geometries: list[LineString] = []

    for edge in _EDGE_DATA:
        start = coords[edge["u"]]
        end = coords[edge["v"]]
        records.append(
            {
                "u": edge["u"],
                "v": edge["v"],
                "highway": edge["highway"],
                "maxspeed": edge["maxspeed"],
                "lanes": edge["lanes"],
            }
        )
        geometries.append(LineString([start, end]))

    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    return gdf


# ---------------------------------------------------------------------------
# Fixtures — NetworkX graph
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_networkx_graph() -> nx.DiGraph:
    """Pre-built NetworkX DiGraph matching the sample node/edge data.

    Node attributes: ``x`` (longitude), ``y`` (latitude).
    Edge attributes: ``length`` (meters), ``speed_kph``, ``lanes``,
    ``highway``, ``geometry`` (LineString).

    Equivalent to calling :func:`src.network.builder.build_graph` on
    :func:`sample_nodes_gdf` and :func:`sample_edges_gdf`.
    """
    coords = {n["id"]: (n["lon"], n["lat"]) for n in _NODE_DATA}

    G = nx.DiGraph()

    # Add nodes
    for node in _NODE_DATA:
        G.add_node(node["id"], x=node["lon"], y=node["lat"])

    # Add edges with realistic attributes
    _MEAN_DEGREE_TO_METER: float = 100_560.0  # matches builder.py

    for edge in _EDGE_DATA:
        start = coords[edge["u"]]
        end = coords[edge["v"]]
        geom = LineString([start, end])

        G.add_edge(
            edge["u"],
            edge["v"],
            length=geom.length * _MEAN_DEGREE_TO_METER,
            speed_kph=float(edge["maxspeed"]),
            lanes=int(edge["lanes"]),
            highway=edge["highway"],
            geometry=geom,
        )

    return G


# ---------------------------------------------------------------------------
# Fixtures — Temporary directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_output_dir(tmp_path: Path) -> Path:
    """Temporary directory for test outputs (auto-cleaned by pytest).

    Creates a dedicated ``output`` subdirectory within pytest's
    ``tmp_path`` fixture so tests can write files without polluting the
    project tree.

    Returns
    -------
    Path
        Path to the temporary output directory.
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
