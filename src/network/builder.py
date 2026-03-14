"""OSM GeoDataFrame to NetworkX directed graph conversion.

Converts Pyrosm-parsed GeoDataFrame nodes and edges into a NetworkX
:class:`~networkx.DiGraph` suitable for downstream simulation.  Each node
receives geographic coordinates and each edge receives road attributes
(length, speed, lanes, highway type, geometry).

Missing OSM tags are filled with defaults from :mod:`src.network.filter`.
"""

import logging

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, MultiLineString

from src.network.filter import get_default_lanes, get_default_speed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_maxspeed(value: object) -> float | None:
    """Try to extract a numeric speed in km/h from an OSM ``maxspeed`` tag.

    Parameters
    ----------
    value:
        Raw value from the ``maxspeed`` column.  May be a string like
        ``"60"``, ``"60 km/h"``, or ``None`` / ``NaN``.

    Returns
    -------
    float | None
        Parsed speed in km/h, or ``None`` if the value cannot be parsed.
    """
    if value is None:
        return None
    try:
        text = str(value).strip().lower()
        # Remove common suffixes
        for suffix in ("km/h", "kph", "kmh"):
            text = text.replace(suffix, "").strip()
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_lanes(value: object) -> int | None:
    """Try to extract an integer lane count from an OSM ``lanes`` tag.

    Parameters
    ----------
    value:
        Raw value from the ``lanes`` column.  May be ``"2"``, ``2``,
        ``None``, or ``NaN``.

    Returns
    -------
    int | None
        Parsed lane count, or ``None`` if the value cannot be parsed.
    """
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _resolve_linestring(geom: object) -> LineString | None:
    """Return a single :class:`LineString` from *geom*.

    If *geom* is a :class:`MultiLineString`, the longest constituent segment
    (by Shapely ``length``) is returned.

    Parameters
    ----------
    geom:
        A Shapely geometry object.

    Returns
    -------
    LineString | None
        A single ``LineString``, or ``None`` if *geom* is not a supported type.
    """
    if isinstance(geom, LineString):
        return geom
    if isinstance(geom, MultiLineString):
        # Take the longest segment by Shapely length (in CRS units)
        return max(geom.geoms, key=lambda g: g.length)
    return None


def _compute_length_meters(geom: LineString) -> float:
    """Approximate length of a ``LineString`` in meters.

    Uses the Haversine-like shortcut:  ``degree_length * COEF`` where COEF
    is ~111_320 m/degree.  The Shapely ``length`` property returns degrees
    for EPSG:4326 geometries, so we multiply by a mid-latitude correction.

    For Japan (~36 N), 1 degree latitude ≈ 111 320 m, 1 degree longitude
    ≈ 89 799 m.  We use the mean of these two as a rough estimate:
    ``(111_320 + 89_799) / 2 ≈ 100_560``.

    Parameters
    ----------
    geom:
        A ``LineString`` in EPSG:4326 (lon/lat degrees).

    Returns
    -------
    float
        Approximate length in meters.
    """
    _MEAN_DEGREE_TO_METER: float = 100_560.0
    return geom.length * _MEAN_DEGREE_TO_METER


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_graph(
    nodes_gdf: gpd.GeoDataFrame,
    edges_gdf: gpd.GeoDataFrame,
) -> nx.DiGraph:
    """Convert GeoDataFrame nodes and edges into a NetworkX directed graph.

    Parameters
    ----------
    nodes_gdf:
        A GeoDataFrame of road network nodes.  Must contain an ``id`` column
        and Point geometries (from which ``x`` / ``y`` are extracted).
    edges_gdf:
        A GeoDataFrame of road edges.  Must contain ``u`` and ``v`` columns
        identifying source / target node IDs, and LineString (or
        MultiLineString) geometries.  Optional columns used for attribute
        extraction: ``highway``, ``maxspeed``, ``lanes``, ``length``.

    Returns
    -------
    nx.DiGraph
        A directed graph where:

        - Each node has ``'x'`` (longitude) and ``'y'`` (latitude) attributes.
        - Each edge has ``'length'`` (meters), ``'speed_kph'`` (km/h),
          ``'lanes'`` (int), ``'highway'`` (str), and ``'geometry'``
          (:class:`LineString`) attributes.

    Notes
    -----
    - MultiLineString geometries are resolved to the longest constituent
      segment.
    - Edges whose geometry cannot be resolved to a valid ``LineString`` are
      skipped (with a warning logged).
    - Missing ``maxspeed`` / ``lanes`` tags are filled using
      :func:`src.network.filter.get_default_speed` and
      :func:`src.network.filter.get_default_lanes`.
    """
    G = nx.DiGraph()

    # ------------------------------------------------------------------
    # Add nodes
    # ------------------------------------------------------------------
    node_count = 0
    for _, row in nodes_gdf.iterrows():
        node_id = row["id"]
        point = row.geometry
        G.add_node(node_id, x=point.x, y=point.y)
        node_count += 1

    # ------------------------------------------------------------------
    # Add edges
    # ------------------------------------------------------------------
    edge_count = 0
    skipped = 0

    has_highway = "highway" in edges_gdf.columns
    has_maxspeed = "maxspeed" in edges_gdf.columns
    has_lanes = "lanes" in edges_gdf.columns
    has_length = "length" in edges_gdf.columns

    for _, row in edges_gdf.iterrows():
        u = row["u"]
        v = row["v"]

        # Resolve geometry to a single LineString
        geom = _resolve_linestring(row.geometry)
        if geom is None:
            skipped += 1
            continue

        # Highway type
        highway_type = str(row["highway"]) if has_highway and row.get("highway") else ""

        # Length in meters: prefer OSM tag, fall back to geometry computation
        length_m: float | None = None
        if has_length:
            try:
                length_m = float(row["length"])
            except (ValueError, TypeError):
                length_m = None
        if length_m is None or length_m <= 0:
            length_m = _compute_length_meters(geom)

        # Speed in km/h: prefer maxspeed tag, fall back to default by type
        speed_kph: float | None = None
        if has_maxspeed:
            speed_kph = _parse_maxspeed(row["maxspeed"])
        if speed_kph is None or speed_kph <= 0:
            speed_kph = get_default_speed(highway_type)

        # Lane count: prefer lanes tag, fall back to default by type
        lanes: int | None = None
        if has_lanes:
            lanes = _parse_lanes(row["lanes"])
        if lanes is None or lanes <= 0:
            lanes = get_default_lanes(highway_type)

        G.add_edge(
            u,
            v,
            length=length_m,
            speed_kph=speed_kph,
            lanes=lanes,
            highway=highway_type,
            geometry=geom,
        )
        edge_count += 1

    # ------------------------------------------------------------------
    # Log statistics
    # ------------------------------------------------------------------
    if skipped > 0:
        logger.warning(
            "build_graph: skipped %d edges with unresolvable geometry", skipped
        )

    logger.info(
        "build_graph: created DiGraph with %d nodes and %d edges",
        G.number_of_nodes(),
        G.number_of_edges(),
    )

    return G
