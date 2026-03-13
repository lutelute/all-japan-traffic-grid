"""Tests for configuration constants and highway filtering / default lookups.

Covers:
- ``src.config`` constants: ``COEF_DEGREE_TO_METER``, ``HIGHWAY_FILTER``,
  ``GEOFABRIK_REGIONS``.
- ``src.network.filter.filter_by_highway`` edge filtering.
- ``src.network.filter.get_default_speed`` / ``get_default_lanes`` lookups.
"""

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from src.config import (
    COEF_DEGREE_TO_METER,
    DEFAULT_LANES_BY_TYPE,
    DEFAULT_SPEED_BY_TYPE,
    GEOFABRIK_REGIONS,
    HIGHWAY_FILTER,
)
from src.network.filter import (
    filter_by_highway,
    get_default_lanes,
    get_default_speed,
)


# ---------------------------------------------------------------------------
# Config constant tests
# ---------------------------------------------------------------------------


class TestConfigConstants:
    """Verify critical configuration values match the specification."""

    def test_coef_degree_to_meter(self) -> None:
        """COEF_DEGREE_TO_METER must equal 89 799."""
        assert COEF_DEGREE_TO_METER == 89_799

    def test_highway_filter_length(self) -> None:
        """HIGHWAY_FILTER must contain exactly 8 highway types."""
        assert len(HIGHWAY_FILTER) == 8

    def test_highway_filter_entries(self) -> None:
        """HIGHWAY_FILTER must contain all expected highway types."""
        expected = {
            "motorway",
            "motorway_link",
            "trunk",
            "trunk_link",
            "primary",
            "primary_link",
            "secondary",
            "secondary_link",
        }
        assert set(HIGHWAY_FILTER) == expected

    def test_geofabrik_regions_count(self) -> None:
        """GEOFABRIK_REGIONS must have exactly 9 entries (japan + 8 sub-regions)."""
        assert len(GEOFABRIK_REGIONS) == 9

    def test_geofabrik_regions_keys(self) -> None:
        """All 8 regional Geofabrik regions plus 'japan' must be present."""
        expected_keys = {
            "japan",
            "chubu",
            "chugoku",
            "hokkaido",
            "kansai",
            "kanto",
            "kyushu",
            "shikoku",
            "tohoku",
        }
        assert set(GEOFABRIK_REGIONS.keys()) == expected_keys

    def test_geofabrik_regions_urls(self) -> None:
        """All Geofabrik region values must be valid HTTPS URLs ending in .osm.pbf."""
        for region, url in GEOFABRIK_REGIONS.items():
            assert url.startswith("https://download.geofabrik.de/"), (
                f"Region '{region}' URL does not start with expected prefix"
            )
            assert url.endswith(".osm.pbf"), (
                f"Region '{region}' URL does not end with .osm.pbf"
            )


# ---------------------------------------------------------------------------
# filter_by_highway tests
# ---------------------------------------------------------------------------


class TestFilterByHighway:
    """Tests for :func:`src.network.filter.filter_by_highway`."""

    def test_keeps_matching_edges(self, sample_edges_gdf: gpd.GeoDataFrame) -> None:
        """Filtering with default whitelist should keep all sample edges."""
        result = filter_by_highway(sample_edges_gdf)
        assert len(result) == len(sample_edges_gdf)

    def test_filters_to_subset(self, sample_edges_gdf: gpd.GeoDataFrame) -> None:
        """Filtering with a partial whitelist keeps only matching rows."""
        result = filter_by_highway(sample_edges_gdf, highway_types=["motorway"])
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "motorway"

    def test_filters_multiple_types(self, sample_edges_gdf: gpd.GeoDataFrame) -> None:
        """Filtering with two types returns only those types."""
        result = filter_by_highway(
            sample_edges_gdf, highway_types=["motorway", "trunk"]
        )
        assert set(result["highway"].unique()) == {"motorway", "trunk"}

    def test_empty_whitelist_returns_empty(
        self, sample_edges_gdf: gpd.GeoDataFrame
    ) -> None:
        """An empty whitelist should return zero edges."""
        result = filter_by_highway(sample_edges_gdf, highway_types=[])
        assert len(result) == 0

    def test_no_highway_column_returns_empty(self) -> None:
        """GeoDataFrame without 'highway' column returns empty frame."""
        gdf = gpd.GeoDataFrame(
            {"u": [1], "v": [2]},
            geometry=[LineString([(0, 0), (1, 1)])],
            crs="EPSG:4326",
        )
        result = filter_by_highway(gdf)
        assert len(result) == 0

    def test_null_highway_values_dropped(self) -> None:
        """Rows with null highway values should be dropped."""
        gdf = gpd.GeoDataFrame(
            {"highway": ["motorway", None, "trunk"]},
            geometry=[
                LineString([(0, 0), (1, 1)]),
                LineString([(1, 1), (2, 2)]),
                LineString([(2, 2), (3, 3)]),
            ],
            crs="EPSG:4326",
        )
        result = filter_by_highway(gdf)
        assert len(result) == 2
        assert list(result["highway"]) == ["motorway", "trunk"]


# ---------------------------------------------------------------------------
# get_default_speed / get_default_lanes tests
# ---------------------------------------------------------------------------


class TestGetDefaultSpeedAndLanes:
    """Tests for default speed and lane lookups."""

    @pytest.mark.parametrize(
        "highway_type,expected_speed",
        [
            ("motorway", 100.0),
            ("motorway_link", 60.0),
            ("trunk", 60.0),
            ("trunk_link", 40.0),
            ("primary", 50.0),
            ("primary_link", 30.0),
            ("secondary", 40.0),
            ("secondary_link", 30.0),
        ],
    )
    def test_default_speed_by_type(
        self, highway_type: str, expected_speed: float
    ) -> None:
        """Each highway type returns the speed defined in config."""
        assert get_default_speed(highway_type) == expected_speed

    @pytest.mark.parametrize(
        "highway_type,expected_lanes",
        [
            ("motorway", 4),
            ("motorway_link", 1),
            ("trunk", 3),
            ("trunk_link", 1),
            ("primary", 2),
            ("primary_link", 1),
            ("secondary", 2),
            ("secondary_link", 1),
        ],
    )
    def test_default_lanes_by_type(
        self, highway_type: str, expected_lanes: int
    ) -> None:
        """Each highway type returns the lane count defined in config."""
        assert get_default_lanes(highway_type) == expected_lanes

    def test_unknown_type_speed_fallback(self) -> None:
        """Unknown highway type returns fallback speed of 30.0 km/h."""
        assert get_default_speed("residential") == 30.0

    def test_unknown_type_lanes_fallback(self) -> None:
        """Unknown highway type returns fallback lane count of 1."""
        assert get_default_lanes("residential") == 1

    def test_empty_string_speed(self) -> None:
        """Empty string returns fallback speed."""
        assert get_default_speed("") == 30.0

    def test_empty_string_lanes(self) -> None:
        """Empty string returns fallback lanes."""
        assert get_default_lanes("") == 1

    def test_speed_config_matches(self) -> None:
        """All HIGHWAY_FILTER entries must be present in DEFAULT_SPEED_BY_TYPE."""
        for hw in HIGHWAY_FILTER:
            assert hw in DEFAULT_SPEED_BY_TYPE, f"Missing speed default for '{hw}'"

    def test_lanes_config_matches(self) -> None:
        """All HIGHWAY_FILTER entries must be present in DEFAULT_LANES_BY_TYPE."""
        for hw in HIGHWAY_FILTER:
            assert hw in DEFAULT_LANES_BY_TYPE, f"Missing lanes default for '{hw}'"
