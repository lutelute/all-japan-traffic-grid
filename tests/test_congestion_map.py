"""Tests for static and interactive congestion map rendering.

Covers:
- ``src.visualization.congestion_map.create_static_map``: Matplotlib PNG output.
- ``src.visualization.congestion_map.create_interactive_map``: Folium HTML output.
- ``src.visualization.congestion_map._simplify_geometries``: geometry simplification.
- ``src.visualization.congestion_map._extract_coords``: coordinate extraction.
"""

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiLineString

from src.visualization.congestion_map import (
    _extract_coords,
    _simplify_geometries,
    create_interactive_map,
    create_static_map,
    get_congestion_color,
)


# ---------------------------------------------------------------------------
# Helper: create sample congestion GeoDataFrame
# ---------------------------------------------------------------------------


def _make_congestion_gdf(n_features: int = 5) -> gpd.GeoDataFrame:
    """Create a small GeoDataFrame with congestion data for testing."""
    records = []
    geometries = []
    for i in range(n_features):
        level = i / max(n_features - 1, 1)
        records.append(
            {
                "name": f"link_{i}",
                "congestion_level": level,
                "average_speed": 10.0 + i,
                "volume": 100 + i * 50,
            }
        )
        lon_start = 139.70 + i * 0.005
        lat_start = 35.70
        geometries.append(
            LineString([(lon_start, lat_start), (lon_start + 0.01, lat_start - 0.005)])
        )

    return gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")


# ---------------------------------------------------------------------------
# _extract_coords tests
# ---------------------------------------------------------------------------


class TestExtractCoords:
    """Tests for :func:`src.visualization.congestion_map._extract_coords`."""

    def test_linestring(self) -> None:
        """LineString should return its coordinates."""
        geom = LineString([(1.0, 2.0), (3.0, 4.0)])
        coords = _extract_coords(geom)
        assert len(coords) == 2
        assert coords[0] == (1.0, 2.0)

    def test_multilinestring(self) -> None:
        """MultiLineString should flatten all parts."""
        geom = MultiLineString(
            [[(0, 0), (1, 1)], [(2, 2), (3, 3)]]
        )
        coords = _extract_coords(geom)
        assert len(coords) == 4

    def test_unsupported_geometry(self) -> None:
        """Unsupported geometry types should return empty list."""
        from shapely.geometry import Point

        coords = _extract_coords(Point(0, 0))
        assert coords == []


# ---------------------------------------------------------------------------
# _simplify_geometries tests
# ---------------------------------------------------------------------------


class TestSimplifyGeometries:
    """Tests for :func:`src.visualization.congestion_map._simplify_geometries`."""

    def test_returns_new_gdf(self) -> None:
        """Should return a copy, not modify the original."""
        gdf = _make_congestion_gdf()
        result = _simplify_geometries(gdf)
        assert result is not gdf

    def test_preserves_row_count(self) -> None:
        """Simplified GeoDataFrame should have the same number of rows."""
        gdf = _make_congestion_gdf(10)
        result = _simplify_geometries(gdf)
        assert len(result) == len(gdf)


# ---------------------------------------------------------------------------
# create_static_map tests
# ---------------------------------------------------------------------------


class TestCreateStaticMap:
    """Tests for :func:`src.visualization.congestion_map.create_static_map`."""

    def test_creates_png_file(self, tmp_path: Path) -> None:
        """Should create a PNG file at the specified path."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "test_map.png"
        result = create_static_map(gdf, output)
        assert result.exists()
        assert result.suffix == ".png"
        assert result.stat().st_size > 0

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "nested" / "dir" / "map.png"
        result = create_static_map(gdf, output)
        assert result.exists()

    def test_empty_gdf_raises(self, tmp_path: Path) -> None:
        """Empty GeoDataFrame should raise ValueError."""
        gdf = gpd.GeoDataFrame(
            {"congestion_level": []},
            geometry=[],
            crs="EPSG:4326",
        )
        with pytest.raises(ValueError, match="empty"):
            create_static_map(gdf, tmp_path / "empty.png")

    def test_missing_column_raises(self, tmp_path: Path) -> None:
        """GeoDataFrame without congestion_level column should raise ValueError."""
        gdf = gpd.GeoDataFrame(
            {"other_col": [1]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        )
        with pytest.raises(ValueError, match="congestion_level"):
            create_static_map(gdf, tmp_path / "no_col.png")

    def test_returns_path(self, tmp_path: Path) -> None:
        """Should return the output path."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "result.png"
        result = create_static_map(gdf, output)
        assert isinstance(result, Path)
        assert result == output


# ---------------------------------------------------------------------------
# create_interactive_map tests
# ---------------------------------------------------------------------------


class TestCreateInteractiveMap:
    """Tests for :func:`src.visualization.congestion_map.create_interactive_map`."""

    def test_creates_html_file(self, tmp_path: Path) -> None:
        """Should create an HTML file at the specified path."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "test_map.html"
        result = create_interactive_map(gdf, output)
        assert result.exists()
        assert result.suffix == ".html"
        assert result.stat().st_size > 0

    def test_html_contains_folium_content(self, tmp_path: Path) -> None:
        """HTML output should contain Folium map elements."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "folium_test.html"
        create_interactive_map(gdf, output)
        content = output.read_text()
        assert "leaflet" in content.lower() or "folium" in content.lower()

    def test_html_contains_legend(self, tmp_path: Path) -> None:
        """HTML should include the congestion level legend."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "legend_test.html"
        create_interactive_map(gdf, output)
        content = output.read_text()
        assert "Congestion Level" in content

    def test_empty_gdf_raises(self, tmp_path: Path) -> None:
        """Empty GeoDataFrame should raise ValueError."""
        gdf = gpd.GeoDataFrame(
            {"congestion_level": []},
            geometry=[],
            crs="EPSG:4326",
        )
        with pytest.raises(ValueError, match="empty"):
            create_interactive_map(gdf, tmp_path / "empty.html")

    def test_missing_column_raises(self, tmp_path: Path) -> None:
        """GeoDataFrame without congestion_level column should raise ValueError."""
        gdf = gpd.GeoDataFrame(
            {"other_col": [1]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        )
        with pytest.raises(ValueError, match="congestion_level"):
            create_interactive_map(gdf, tmp_path / "no_col.html")

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "nested" / "dir" / "map.html"
        result = create_interactive_map(gdf, output)
        assert result.exists()

    def test_returns_path(self, tmp_path: Path) -> None:
        """Should return the output path."""
        gdf = _make_congestion_gdf()
        output = tmp_path / "result.html"
        result = create_interactive_map(gdf, output)
        assert isinstance(result, Path)
        assert result == output
