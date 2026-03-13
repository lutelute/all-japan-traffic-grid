"""GeoJSON and GeoDataFrame export for simulation congestion results.

Extracts per-link congestion data from a completed UXsim
:class:`~uxsim.World` simulation, computes congestion levels, and
exports results as GeoJSON :rfc:`7946` files or GeoPandas
:class:`~geopandas.GeoDataFrame` objects for further analysis.

Congestion level is calculated as ``1 - (actual_speed / free_flow_speed)``
and clamped to the ``[0, 1]`` range, where 0 indicates free-flow
conditions and 1 indicates fully congested (stationary traffic).
"""

import json
import logging
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, mapping

from src.config import COEF_DEGREE_TO_METER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_average_speed(link: object) -> float:
    """Estimate the average actual speed on a link from simulation data.

    Uses Little's Law applied to the cumulative arrival/departure curves:
    total vehicle-time (area between curves) divided by total departed
    vehicles gives the average travel time, from which average speed is
    derived as ``link.length / avg_travel_time``.

    Falls back to the link's free-flow speed when simulation data is
    unavailable or when no vehicles traversed the link.

    Parameters
    ----------
    link:
        A UXsim Link object (after simulation).

    Returns
    -------
    float
        Average speed in m/s.
    """
    try:
        cum_arr = link.cum_arrival
        cum_dep = link.cum_departure

        if not cum_arr or not cum_dep:
            return link.free_flow_speed

        total_departed = cum_dep[-1]
        if total_departed <= 0:
            return link.free_flow_speed

        # Determine simulation time step
        deltat = getattr(link.W, "DELTAT", 1.0) if hasattr(link, "W") else 1.0

        # Total vehicle-time = integral of vehicles-on-link over time
        n_steps = min(len(cum_arr), len(cum_dep))
        total_vehicle_time = 0.0
        for i in range(n_steps):
            vehicles_on_link = cum_arr[i] - cum_dep[i]
            total_vehicle_time += max(0.0, vehicles_on_link) * deltat

        if total_vehicle_time <= 0:
            return link.free_flow_speed

        avg_travel_time = total_vehicle_time / total_departed
        if avg_travel_time <= 0:
            return link.free_flow_speed

        return link.length / avg_travel_time

    except (AttributeError, IndexError, TypeError, ZeroDivisionError):
        return getattr(link, "free_flow_speed", 0.0)


def _compute_volume(link: object) -> float:
    """Return the total number of vehicles that completed traversal.

    Parameters
    ----------
    link:
        A UXsim Link object (after simulation).

    Returns
    -------
    float
        Total departed vehicles, or ``0.0`` if data is unavailable.
    """
    try:
        if link.cum_departure:
            return float(link.cum_departure[-1])
    except (AttributeError, IndexError, TypeError):
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_link_congestion(W: object) -> list[dict]:
    """Extract per-link congestion data from UXsim World results.

    Iterates over all links in the simulation world, computes each
    link's average actual speed from cumulative arrival/departure data,
    and derives a congestion level relative to the free-flow speed.

    Parameters
    ----------
    W:
        A :class:`uxsim.World` object that has completed simulation
        execution (i.e. ``W.exec_simulation()`` has been called).

    Returns
    -------
    list[dict]
        A list of dictionaries, one per link, each containing:

        - ``name`` (str): Link identifier.
        - ``coords`` (list[tuple[float, float]]): Coordinate pairs
          ``[(lon_start, lat_start), (lon_end, lat_end)]`` in degrees.
        - ``congestion_level`` (float): Value in ``[0.0, 1.0]`` where
          0 = free flow and 1 = fully congested.
        - ``average_speed`` (float): Average actual speed in m/s.
        - ``volume`` (float): Total vehicles that traversed the link.
        - ``free_flow_speed`` (float): Design free-flow speed in m/s.
        - ``capacity`` (float): Link capacity.
    """
    results: list[dict] = []

    for link in W.LINKS:
        # ---------------------------------------------------------------
        # Geometry: convert node coordinates from meters back to degrees
        # ---------------------------------------------------------------
        start_lon = link.start_node.x / COEF_DEGREE_TO_METER
        start_lat = link.start_node.y / COEF_DEGREE_TO_METER
        end_lon = link.end_node.x / COEF_DEGREE_TO_METER
        end_lat = link.end_node.y / COEF_DEGREE_TO_METER
        coords = [(start_lon, start_lat), (end_lon, end_lat)]

        # ---------------------------------------------------------------
        # Link attributes
        # ---------------------------------------------------------------
        free_flow_speed = getattr(link, "free_flow_speed", 0.0)
        capacity = getattr(link, "capacity", 0.0)

        # ---------------------------------------------------------------
        # Post-simulation metrics
        # ---------------------------------------------------------------
        average_speed = _compute_average_speed(link)
        volume = _compute_volume(link)

        # ---------------------------------------------------------------
        # Congestion level: 1 - (actual / free_flow), clamped to [0, 1]
        # ---------------------------------------------------------------
        if free_flow_speed > 0:
            congestion_level = 1.0 - (average_speed / free_flow_speed)
        else:
            congestion_level = 0.0

        congestion_level = max(0.0, min(1.0, congestion_level))

        results.append(
            {
                "name": link.name,
                "coords": coords,
                "congestion_level": round(congestion_level, 4),
                "average_speed": round(average_speed, 2),
                "volume": round(volume, 2),
                "free_flow_speed": round(free_flow_speed, 2),
                "capacity": round(float(capacity), 2),
            }
        )

    logger.info(
        "extract_link_congestion: extracted congestion data for %d links",
        len(results),
    )

    return results


def to_geojson(congestion_data: list[dict], output_path: str | Path) -> Path:
    """Write congestion data as a GeoJSON FeatureCollection.

    Each link becomes a GeoJSON Feature with a ``LineString`` geometry
    (from start to end node) and congestion-related properties.

    Parameters
    ----------
    congestion_data:
        List of link congestion dictionaries as returned by
        :func:`extract_link_congestion`.
    output_path:
        Destination file path for the GeoJSON output.  Parent
        directories are created automatically if they do not exist.

    Returns
    -------
    Path
        Absolute path to the written GeoJSON file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    features: list[dict] = []
    for entry in congestion_data:
        feature = {
            "type": "Feature",
            "geometry": mapping(LineString(entry["coords"])),
            "properties": {
                "name": entry["name"],
                "congestion_level": entry["congestion_level"],
                "average_speed": entry["average_speed"],
                "volume": entry["volume"],
                "free_flow_speed": entry["free_flow_speed"],
                "capacity": entry["capacity"],
            },
        }
        features.append(feature)

    collection = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(collection, fh, ensure_ascii=False, indent=2)

    logger.info(
        "to_geojson: wrote %d features to %s",
        len(features),
        output_path,
    )

    return output_path


def to_geodataframe(congestion_data: list[dict]) -> gpd.GeoDataFrame:
    """Convert congestion data to a GeoPandas GeoDataFrame.

    Creates a GeoDataFrame with ``LineString`` geometries and columns for
    all congestion metrics, using the WGS 84 (EPSG:4326) coordinate
    reference system.

    Parameters
    ----------
    congestion_data:
        List of link congestion dictionaries as returned by
        :func:`extract_link_congestion`.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame with columns: ``name``, ``congestion_level``,
        ``average_speed``, ``volume``, ``free_flow_speed``, ``capacity``,
        and ``geometry`` (LineString in EPSG:4326).
    """
    records: list[dict] = []
    geometries: list[LineString] = []

    for entry in congestion_data:
        records.append(
            {
                "name": entry["name"],
                "congestion_level": entry["congestion_level"],
                "average_speed": entry["average_speed"],
                "volume": entry["volume"],
                "free_flow_speed": entry["free_flow_speed"],
                "capacity": entry["capacity"],
            }
        )
        geometries.append(LineString(entry["coords"]))

    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")

    logger.info(
        "to_geodataframe: created GeoDataFrame with %d rows",
        len(gdf),
    )

    return gdf
