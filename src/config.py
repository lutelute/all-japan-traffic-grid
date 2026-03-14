"""Global configuration constants for the All-Japan Traffic Grid system."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = DATA_DIR / "output"

# ---------------------------------------------------------------------------
# Geofabrik download URLs
# ---------------------------------------------------------------------------
GEOFABRIK_JAPAN_URL = "https://download.geofabrik.de/asia/japan-latest.osm.pbf"

GEOFABRIK_REGIONS: dict[str, str] = {
    "japan": GEOFABRIK_JAPAN_URL,
    "chubu": "https://download.geofabrik.de/asia/japan/chubu-latest.osm.pbf",
    "chugoku": "https://download.geofabrik.de/asia/japan/chugoku-latest.osm.pbf",
    "hokkaido": "https://download.geofabrik.de/asia/japan/hokkaido-latest.osm.pbf",
    "kansai": "https://download.geofabrik.de/asia/japan/kansai-latest.osm.pbf",
    "kanto": "https://download.geofabrik.de/asia/japan/kanto-latest.osm.pbf",
    "kyushu": "https://download.geofabrik.de/asia/japan/kyushu-latest.osm.pbf",
    "shikoku": "https://download.geofabrik.de/asia/japan/shikoku-latest.osm.pbf",
    "tohoku": "https://download.geofabrik.de/asia/japan/tohoku-latest.osm.pbf",
}

# ---------------------------------------------------------------------------
# Highway types to include (ordered by importance)
# Include _link variants (on-ramps, off-ramps) for network connectivity
# ---------------------------------------------------------------------------
HIGHWAY_FILTER: list[str] = [
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
]

# ---------------------------------------------------------------------------
# Japan latitude correction for UXsim
# cos(36°) ≈ 0.809 → 111000 * 0.809 ≈ 89,799
# ---------------------------------------------------------------------------
JAPAN_LAT_CENTER: float = 36.0
COEF_DEGREE_TO_METER: int = 89_799

# ---------------------------------------------------------------------------
# UXsim simulation defaults
# ---------------------------------------------------------------------------
DEFAULT_DELTAN: int = 10
DEFAULT_TMAX: int = 7200  # 2 hours in seconds

# ---------------------------------------------------------------------------
# Network simplification
# ---------------------------------------------------------------------------
NODE_MERGE_THRESHOLD: float = 0.005  # ~50 m in degrees

# ---------------------------------------------------------------------------
# Default road attributes by highway type
# Matches UXsim OSMImporter defaults for missing OSM tags
# ---------------------------------------------------------------------------
DEFAULT_SPEED_BY_TYPE: dict[str, float] = {
    "motorway": 100.0,
    "motorway_link": 60.0,
    "trunk": 60.0,
    "trunk_link": 40.0,
    "primary": 50.0,
    "primary_link": 30.0,
    "secondary": 40.0,
    "secondary_link": 30.0,
}

DEFAULT_LANES_BY_TYPE: dict[str, int] = {
    "motorway": 4,
    "motorway_link": 1,
    "trunk": 3,
    "trunk_link": 1,
    "primary": 2,
    "primary_link": 1,
    "secondary": 2,
    "secondary_link": 1,
}
