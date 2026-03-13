"""Highway filtering and default road attribute lookups.

Provides functions to filter GeoDataFrame edges by OSM highway type and to
retrieve sensible default speed / lane values when OSM tags are missing.
All defaults are sourced from :mod:`src.config`.
"""

import logging

import geopandas as gpd

from src.config import (
    DEFAULT_LANES_BY_TYPE,
    DEFAULT_SPEED_BY_TYPE,
    HIGHWAY_FILTER,
)

logger = logging.getLogger(__name__)

# Fallback values for highway types not present in the config lookup tables.
_FALLBACK_SPEED: float = 30.0  # km/h
_FALLBACK_LANES: int = 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_by_highway(
    edges_gdf: gpd.GeoDataFrame,
    highway_types: list[str] | None = None,
) -> gpd.GeoDataFrame:
    """Filter edges by highway type whitelist.

    Parameters
    ----------
    edges_gdf:
        A GeoDataFrame of road edges that must contain a ``highway`` column.
    highway_types:
        List of OSM highway type strings to keep.  When ``None``, defaults to
        :data:`src.config.HIGHWAY_FILTER`.

    Returns
    -------
    GeoDataFrame
        A copy of *edges_gdf* containing only rows whose ``highway`` value is
        in the whitelist.  Rows with missing / null ``highway`` values are
        always dropped.
    """
    if highway_types is None:
        highway_types = HIGHWAY_FILTER

    if "highway" not in edges_gdf.columns:
        logger.warning("GeoDataFrame has no 'highway' column; returning empty frame")
        return edges_gdf.iloc[0:0].copy()

    # Drop rows where highway is null, then apply whitelist
    mask = edges_gdf["highway"].notna() & edges_gdf["highway"].isin(highway_types)
    filtered = edges_gdf[mask].copy()

    logger.info(
        "filter_by_highway: kept %d / %d edges (%d highway types)",
        len(filtered),
        len(edges_gdf),
        len(highway_types),
    )
    return filtered


def get_default_speed(highway_type: str) -> float:
    """Return the default speed in km/h for *highway_type*.

    Parameters
    ----------
    highway_type:
        An OSM highway tag value (e.g. ``"motorway"``, ``"primary_link"``).

    Returns
    -------
    float
        Speed from :data:`src.config.DEFAULT_SPEED_BY_TYPE` if available,
        otherwise a conservative fallback of ``30.0`` km/h.
    """
    if not highway_type or not isinstance(highway_type, str):
        return _FALLBACK_SPEED
    return DEFAULT_SPEED_BY_TYPE.get(highway_type, _FALLBACK_SPEED)


def get_default_lanes(highway_type: str) -> int:
    """Return the default lane count for *highway_type*.

    Parameters
    ----------
    highway_type:
        An OSM highway tag value (e.g. ``"motorway"``, ``"trunk_link"``).

    Returns
    -------
    int
        Lane count from :data:`src.config.DEFAULT_LANES_BY_TYPE` if available,
        otherwise a conservative fallback of ``1``.
    """
    if not highway_type or not isinstance(highway_type, str):
        return _FALLBACK_LANES
    return DEFAULT_LANES_BY_TYPE.get(highway_type, _FALLBACK_LANES)
