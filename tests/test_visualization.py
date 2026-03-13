"""Tests for congestion colour mapping and GeoJSON export.

Covers:
- ``src.visualization.congestion_map.get_congestion_color``: green/yellow/red
  gradient mapping.
- ``src.visualization.export.to_geojson``: FeatureCollection structure and
  required properties.
"""

import json
from pathlib import Path

import pytest

from src.visualization.congestion_map import get_congestion_color
from src.visualization.export import to_geojson


# ---------------------------------------------------------------------------
# Congestion colour tests
# ---------------------------------------------------------------------------


class TestCongestionColor:
    """Tests for :func:`src.visualization.congestion_map.get_congestion_color`."""

    def test_level_zero_is_green(self) -> None:
        """Congestion level 0.0 must map to green (#00FF00)."""
        assert get_congestion_color(0.0) == "#00FF00"

    def test_level_half_is_yellow(self) -> None:
        """Congestion level 0.5 must map to yellow (#FFFF00)."""
        assert get_congestion_color(0.5) == "#FFFF00"

    def test_level_one_is_red(self) -> None:
        """Congestion level 1.0 must map to red (#FF0000)."""
        assert get_congestion_color(1.0) == "#FF0000"

    def test_clamps_below_zero(self) -> None:
        """Negative values must be clamped to green (#00FF00)."""
        assert get_congestion_color(-0.5) == "#00FF00"

    def test_clamps_above_one(self) -> None:
        """Values above 1.0 must be clamped to red (#FF0000)."""
        assert get_congestion_color(1.5) == "#FF0000"

    def test_returns_hex_string(self) -> None:
        """Result must be a 7-character hex colour string."""
        color = get_congestion_color(0.3)
        assert isinstance(color, str)
        assert len(color) == 7
        assert color.startswith("#")

    def test_quarter_interpolation(self) -> None:
        """Level 0.25 must be between green and yellow (R increases, G stays 255)."""
        color = get_congestion_color(0.25)
        # At 0.25: t = 0.5, R = 127, G = 255 → #7FFF00
        assert color == "#7FFF00"


# ---------------------------------------------------------------------------
# GeoJSON export structure tests
# ---------------------------------------------------------------------------

# Sample congestion data matching the format of extract_link_congestion output
_SAMPLE_CONGESTION_DATA: list[dict] = [
    {
        "name": "A_B",
        "coords": [(139.700, 35.700), (139.710, 35.700)],
        "congestion_level": 0.25,
        "average_speed": 12.5,
        "volume": 150.0,
        "free_flow_speed": 16.67,
        "capacity": 1800.0,
    },
    {
        "name": "B_C",
        "coords": [(139.710, 35.700), (139.720, 35.690)],
        "congestion_level": 0.75,
        "average_speed": 4.17,
        "volume": 200.0,
        "free_flow_speed": 16.67,
        "capacity": 1800.0,
    },
]


class TestGeoJsonExportStructure:
    """Tests for :func:`src.visualization.export.to_geojson` output structure."""

    @pytest.fixture()
    def geojson_path(self, tmp_output_dir: Path) -> Path:
        """Write sample congestion data to a GeoJSON file and return the path."""
        output = tmp_output_dir / "congestion.geojson"
        to_geojson(_SAMPLE_CONGESTION_DATA, output)
        return output

    @pytest.fixture()
    def geojson_data(self, geojson_path: Path) -> dict:
        """Load the GeoJSON file as a dictionary."""
        with open(geojson_path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_is_feature_collection(self, geojson_data: dict) -> None:
        """Root object type must be 'FeatureCollection'."""
        assert geojson_data["type"] == "FeatureCollection"

    def test_has_features_array(self, geojson_data: dict) -> None:
        """FeatureCollection must contain a 'features' array."""
        assert "features" in geojson_data
        assert isinstance(geojson_data["features"], list)

    def test_feature_count_matches_input(self, geojson_data: dict) -> None:
        """Number of features must match the input data length."""
        assert len(geojson_data["features"]) == len(_SAMPLE_CONGESTION_DATA)

    def test_features_are_linestrings(self, geojson_data: dict) -> None:
        """Every feature geometry must be a LineString."""
        for feature in geojson_data["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "LineString"

    def test_linestring_has_coordinates(self, geojson_data: dict) -> None:
        """Every LineString geometry must have a 'coordinates' array with >= 2 points."""
        for feature in geojson_data["features"]:
            coords = feature["geometry"]["coordinates"]
            assert isinstance(coords, list)
            assert len(coords) >= 2


class TestGeoJsonProperties:
    """Verify required properties exist on every GeoJSON feature."""

    @pytest.fixture()
    def features(self, tmp_output_dir: Path) -> list[dict]:
        """Write sample data and return the list of GeoJSON features."""
        output = tmp_output_dir / "congestion_props.geojson"
        to_geojson(_SAMPLE_CONGESTION_DATA, output)
        with open(output, encoding="utf-8") as fh:
            data = json.load(fh)
        return data["features"]

    def test_congestion_level_property(self, features: list[dict]) -> None:
        """Every feature must have a 'congestion_level' property."""
        for feature in features:
            assert "congestion_level" in feature["properties"]

    def test_speed_property(self, features: list[dict]) -> None:
        """Every feature must have an 'average_speed' property."""
        for feature in features:
            assert "average_speed" in feature["properties"]

    def test_volume_property(self, features: list[dict]) -> None:
        """Every feature must have a 'volume' property."""
        for feature in features:
            assert "volume" in feature["properties"]

    def test_name_property(self, features: list[dict]) -> None:
        """Every feature must have a 'name' property."""
        for feature in features:
            assert "name" in feature["properties"]

    def test_free_flow_speed_property(self, features: list[dict]) -> None:
        """Every feature must have a 'free_flow_speed' property."""
        for feature in features:
            assert "free_flow_speed" in feature["properties"]

    def test_capacity_property(self, features: list[dict]) -> None:
        """Every feature must have a 'capacity' property."""
        for feature in features:
            assert "capacity" in feature["properties"]

    def test_congestion_level_values(self, features: list[dict]) -> None:
        """congestion_level values must match the input data."""
        for feature, expected in zip(features, _SAMPLE_CONGESTION_DATA, strict=True):
            assert feature["properties"]["congestion_level"] == expected["congestion_level"]

    def test_volume_values(self, features: list[dict]) -> None:
        """volume values must match the input data."""
        for feature, expected in zip(features, _SAMPLE_CONGESTION_DATA, strict=True):
            assert feature["properties"]["volume"] == expected["volume"]
