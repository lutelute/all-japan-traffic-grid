"""Tests for the PBF parser module.

Covers:
- ``src.data.parser.parse_road_network``: file validation, pyrosm delegation,
  highway filtering, and node pruning.

Pyrosm is mocked since it cannot be installed on Python 3.14 due to
pyrobuf compatibility issues.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from src.data.parser import parse_road_network


# ---------------------------------------------------------------------------
# Helper: create mock OSM data
# ---------------------------------------------------------------------------


def _make_mock_network() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Create synthetic nodes/edges GeoDataFrames mimicking pyrosm output."""
    nodes = gpd.GeoDataFrame(
        {"id": [1, 2, 3, 4]},
        geometry=[
            Point(139.70, 35.70),
            Point(139.72, 35.70),
            Point(139.70, 35.68),
            Point(139.72, 35.68),
        ],
        crs="EPSG:4326",
    )
    edges = gpd.GeoDataFrame(
        {
            "u": [1, 2, 3],
            "v": [2, 3, 1],
            "highway": ["motorway", "residential", "trunk"],
        },
        geometry=[
            LineString([(139.70, 35.70), (139.72, 35.70)]),
            LineString([(139.72, 35.70), (139.70, 35.68)]),
            LineString([(139.70, 35.68), (139.70, 35.70)]),
        ],
        crs="EPSG:4326",
    )
    return nodes, edges


# ---------------------------------------------------------------------------
# parse_road_network tests
# ---------------------------------------------------------------------------


class TestParseRoadNetwork:
    """Tests for :func:`src.data.parser.parse_road_network`."""

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Non-existent file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="PBF file not found"):
            parse_road_network(tmp_path / "missing.osm.pbf")

    def test_filters_by_highway_type(self, tmp_path: Path) -> None:
        """Only edges matching HIGHWAY_FILTER should be returned."""
        pbf_file = tmp_path / "test.osm.pbf"
        pbf_file.write_bytes(b"fake")

        nodes, edges = _make_mock_network()
        mock_osm = MagicMock()
        mock_osm.get_network.return_value = (nodes, edges)

        with patch("src.data.parser.OSM", return_value=mock_osm, create=True):
            # Patch the lazy import inside the function
            import src.data.parser as parser_mod

            with patch.object(parser_mod, "OSM", mock_osm.__class__, create=True):
                # Use a direct mock of the pyrosm.OSM class
                mock_cls = MagicMock(return_value=mock_osm)
                with patch.dict("sys.modules", {"pyrosm": MagicMock(OSM=mock_cls)}):
                    result_nodes, result_edges = parse_road_network(
                        pbf_file, include_nodes=True
                    )

        # "residential" should be filtered out; only motorway and trunk remain
        assert len(result_edges) == 2
        assert set(result_edges["highway"].unique()) == {"motorway", "trunk"}

    def test_prunes_unreferenced_nodes(self, tmp_path: Path) -> None:
        """Nodes not referenced by filtered edges should be pruned."""
        pbf_file = tmp_path / "test.osm.pbf"
        pbf_file.write_bytes(b"fake")

        nodes, edges = _make_mock_network()
        mock_osm = MagicMock()
        mock_osm.get_network.return_value = (nodes, edges)

        mock_cls = MagicMock(return_value=mock_osm)
        with patch.dict("sys.modules", {"pyrosm": MagicMock(OSM=mock_cls)}):
            result_nodes, result_edges = parse_road_network(
                pbf_file, include_nodes=True
            )

        # Only nodes referenced by motorway (u=1, v=2) and trunk (u=3, v=1)
        # should remain: nodes 1, 2, 3
        assert len(result_nodes) == 3
        assert set(result_nodes["id"]) == {1, 2, 3}

    def test_edges_only_mode(self, tmp_path: Path) -> None:
        """include_nodes=False should return only the edges GeoDataFrame."""
        pbf_file = tmp_path / "test.osm.pbf"
        pbf_file.write_bytes(b"fake")

        _, edges = _make_mock_network()
        mock_osm = MagicMock()
        mock_osm.get_network.return_value = edges

        mock_cls = MagicMock(return_value=mock_osm)
        with patch.dict("sys.modules", {"pyrosm": MagicMock(OSM=mock_cls)}):
            result = parse_road_network(
                pbf_file, include_nodes=False
            )

        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 2  # motorway + trunk

    def test_custom_highway_types(self, tmp_path: Path) -> None:
        """Custom highway_types list should override the default filter."""
        pbf_file = tmp_path / "test.osm.pbf"
        pbf_file.write_bytes(b"fake")

        nodes, edges = _make_mock_network()
        mock_osm = MagicMock()
        mock_osm.get_network.return_value = (nodes, edges)

        mock_cls = MagicMock(return_value=mock_osm)
        with patch.dict("sys.modules", {"pyrosm": MagicMock(OSM=mock_cls)}):
            result_nodes, result_edges = parse_road_network(
                pbf_file,
                highway_types=["residential"],
                include_nodes=True,
            )

        assert len(result_edges) == 1
        assert result_edges.iloc[0]["highway"] == "residential"

    def test_pyrosm_import_error(self, tmp_path: Path) -> None:
        """Should raise ImportError when pyrosm is not available."""
        pbf_file = tmp_path / "test.osm.pbf"
        pbf_file.write_bytes(b"fake")

        with patch.dict("sys.modules", {"pyrosm": None}):
            with pytest.raises(ImportError, match="pyrosm is required"):
                parse_road_network(pbf_file)
