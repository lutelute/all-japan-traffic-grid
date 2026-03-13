"""Static and interactive congestion map rendering.

Produces congestion heatmaps from a :class:`~geopandas.GeoDataFrame`
containing road-segment geometries and a ``congestion_level`` column
(0.0 = free flow, 1.0 = fully congested).

Two output formats are supported:

* **Static** — a Matplotlib figure saved as a PNG image, with road
  segments colored on a green-yellow-red gradient.
* **Interactive** — a Folium HTML map with colored
  :class:`~folium.PolyLine` overlays, popups showing congestion
  details, and a colour legend.

For large datasets (>50 000 features) geometry simplification via
:meth:`shapely.geometry.base.BaseGeometry.simplify` is applied
automatically to keep rendering responsive.
"""

import logging
from pathlib import Path

import folium
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from shapely.geometry import LineString, MultiLineString

from src.config import JAPAN_LAT_CENTER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LARGE_DATASET_THRESHOLD: int = 50_000
"""Feature count above which geometry simplification is applied."""

_SIMPLIFY_TOLERANCE: float = 0.001
"""Shapely simplify tolerance in degrees (~100 m at Japan latitude)."""


# ---------------------------------------------------------------------------
# Colour mapping
# ---------------------------------------------------------------------------


def get_congestion_color(level: float) -> str:
    """Map a congestion level to a hex colour on a green-yellow-red gradient.

    The mapping uses a two-segment linear interpolation:

    * ``0.0`` → green  (``#00FF00``)
    * ``0.5`` → yellow (``#FFFF00``)
    * ``1.0`` → red    (``#FF0000``)

    Values outside ``[0, 1]`` are clamped.

    Parameters
    ----------
    level:
        Congestion level in the range ``[0.0, 1.0]``.

    Returns
    -------
    str
        A hex colour string (e.g. ``'#00FF00'``).
    """
    level = max(0.0, min(1.0, float(level)))

    if level <= 0.5:
        # Green → Yellow: R increases from 0→255, G stays 255
        t = level / 0.5
        r = int(255 * t)
        g = 255
    else:
        # Yellow → Red: R stays 255, G decreases from 255→0
        t = (level - 0.5) / 0.5
        r = 255
        g = int(255 * (1.0 - t))

    return f"#{r:02X}{g:02X}00"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _simplify_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Apply Shapely simplify to all geometries in *gdf*.

    Used for datasets exceeding :data:`_LARGE_DATASET_THRESHOLD`
    features to improve rendering performance.  A copy of the
    GeoDataFrame is returned; the original is not modified.

    Parameters
    ----------
    gdf:
        GeoDataFrame with a geometry column.

    Returns
    -------
    gpd.GeoDataFrame
        A copy with simplified geometries.
    """
    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].simplify(
        tolerance=_SIMPLIFY_TOLERANCE,
        preserve_topology=True,
    )
    logger.info(
        "_simplify_geometries: simplified %d geometries (tolerance=%.4f)",
        len(gdf),
        _SIMPLIFY_TOLERANCE,
    )
    return gdf


def _extract_coords(geom: object) -> list[tuple[float, float]]:
    """Extract a flat list of ``(lon, lat)`` coordinate pairs from a geometry.

    Handles :class:`~shapely.geometry.LineString` and
    :class:`~shapely.geometry.MultiLineString` inputs.

    Parameters
    ----------
    geom:
        A Shapely geometry object.

    Returns
    -------
    list[tuple[float, float]]
        Coordinate pairs, or an empty list if the geometry type is
        unsupported.
    """
    if isinstance(geom, LineString):
        return list(geom.coords)
    if isinstance(geom, MultiLineString):
        coords: list[tuple[float, float]] = []
        for part in geom.geoms:
            coords.extend(part.coords)
        return coords
    return []


# ---------------------------------------------------------------------------
# Public API — static map
# ---------------------------------------------------------------------------


def create_static_map(
    congestion_gdf: gpd.GeoDataFrame,
    output_path: str | Path,
    figsize: tuple[int, int] = (20, 20),
    title: str = "Traffic Congestion",
) -> Path:
    """Render a static congestion map and save as a PNG image.

    Road segments are drawn as coloured lines on a Matplotlib figure
    using a green-yellow-red gradient that corresponds to
    ``congestion_level``.  For datasets with more than
    :data:`_LARGE_DATASET_THRESHOLD` features, geometries are
    simplified via :func:`_simplify_geometries` before rendering.

    Parameters
    ----------
    congestion_gdf:
        A GeoDataFrame with at least a ``congestion_level`` column
        (float, 0-1) and LineString/MultiLineString geometries in
        EPSG:4326.
    output_path:
        Destination file path for the PNG output.  Parent directories
        are created automatically if they do not exist.
    figsize:
        Matplotlib figure size in inches ``(width, height)``.
    title:
        Title displayed at the top of the figure.

    Returns
    -------
    Path
        Absolute path to the saved PNG file.

    Raises
    ------
    ValueError
        If *congestion_gdf* is empty or missing the
        ``congestion_level`` column.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if congestion_gdf.empty:
        raise ValueError("congestion_gdf is empty — nothing to render")
    if "congestion_level" not in congestion_gdf.columns:
        raise ValueError("congestion_gdf must contain a 'congestion_level' column")

    # ------------------------------------------------------------------
    # Simplify large datasets
    # ------------------------------------------------------------------
    gdf = congestion_gdf
    if len(gdf) > _LARGE_DATASET_THRESHOLD:
        logger.info(
            "create_static_map: %d features exceed threshold (%d), "
            "applying geometry simplification",
            len(gdf),
            _LARGE_DATASET_THRESHOLD,
        )
        gdf = _simplify_geometries(gdf)

    # ------------------------------------------------------------------
    # Build line segments and colours for LineCollection
    # ------------------------------------------------------------------
    segments: list[list[tuple[float, float]]] = []
    colors: list[str] = []

    for _, row in gdf.iterrows():
        coords = _extract_coords(row.geometry)
        if len(coords) < 2:
            continue
        segments.append(coords)
        colors.append(get_congestion_color(row["congestion_level"]))

    if not segments:
        raise ValueError("No renderable line segments found in congestion_gdf")

    # ------------------------------------------------------------------
    # Render with Matplotlib
    # ------------------------------------------------------------------
    # Use non-interactive backend to avoid GUI popups
    matplotlib.use("Agg")

    fig, ax = plt.subplots(figsize=figsize)

    lc = LineCollection(segments, colors=colors, linewidths=1.0)
    ax.add_collection(lc)
    ax.autoscale()
    ax.set_aspect("equal")

    ax.set_title(title, fontsize=16)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    # ------------------------------------------------------------------
    # Add colour bar
    # ------------------------------------------------------------------
    sm = plt.cm.ScalarMappable(
        cmap=plt.cm.RdYlGn_r,
        norm=plt.Normalize(vmin=0, vmax=1),
    )
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Congestion Level")

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(
        "create_static_map: saved static map with %d segments to %s",
        len(segments),
        output_path,
    )

    return output_path


# ---------------------------------------------------------------------------
# Public API — interactive map
# ---------------------------------------------------------------------------


def create_interactive_map(
    congestion_gdf: gpd.GeoDataFrame,
    output_path: str | Path,
    center_lat: float = JAPAN_LAT_CENTER,
    center_lon: float = 139.7,
    zoom_start: int = 10,
) -> Path:
    """Render an interactive congestion map and save as an HTML file.

    Creates a Folium map with road segments drawn as coloured
    :class:`~folium.PolyLine` overlays.  Each segment has a popup
    showing congestion details (congestion level, speed, volume).
    A colour legend is included.

    For datasets with more than :data:`_LARGE_DATASET_THRESHOLD`
    features, geometries are simplified via
    :func:`_simplify_geometries` before rendering.

    Parameters
    ----------
    congestion_gdf:
        A GeoDataFrame with at least a ``congestion_level`` column
        (float, 0-1) and LineString/MultiLineString geometries in
        EPSG:4326.  Optional columns ``average_speed``, ``volume``,
        and ``name`` are included in popups when present.
    output_path:
        Destination file path for the HTML output.  Parent directories
        are created automatically if they do not exist.
    center_lat:
        Initial map centre latitude.
    center_lon:
        Initial map centre longitude.
    zoom_start:
        Initial zoom level.

    Returns
    -------
    Path
        Absolute path to the saved HTML file.

    Raises
    ------
    ValueError
        If *congestion_gdf* is empty or missing the
        ``congestion_level`` column.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if congestion_gdf.empty:
        raise ValueError("congestion_gdf is empty — nothing to render")
    if "congestion_level" not in congestion_gdf.columns:
        raise ValueError("congestion_gdf must contain a 'congestion_level' column")

    # ------------------------------------------------------------------
    # Simplify large datasets
    # ------------------------------------------------------------------
    gdf = congestion_gdf
    if len(gdf) > _LARGE_DATASET_THRESHOLD:
        logger.info(
            "create_interactive_map: %d features exceed threshold (%d), "
            "applying geometry simplification",
            len(gdf),
            _LARGE_DATASET_THRESHOLD,
        )
        gdf = _simplify_geometries(gdf)

    # ------------------------------------------------------------------
    # Create Folium map
    # ------------------------------------------------------------------
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles="CartoDB positron",
    )

    # ------------------------------------------------------------------
    # Add road segments as coloured PolyLines
    # ------------------------------------------------------------------
    segment_count = 0
    for _, row in gdf.iterrows():
        coords = _extract_coords(row.geometry)
        if len(coords) < 2:
            continue

        level = float(row["congestion_level"])
        color = get_congestion_color(level)

        # Folium expects (lat, lon) — swap from Shapely's (lon, lat)
        folium_coords = [(lat, lon) for lon, lat in coords]

        # Build popup content
        popup_parts = [f"<b>Congestion:</b> {level:.2%}"]
        if "name" in gdf.columns:
            popup_parts.insert(0, f"<b>Road:</b> {row['name']}")
        if "average_speed" in gdf.columns:
            speed_kph = float(row["average_speed"]) * 3.6
            popup_parts.append(f"<b>Speed:</b> {speed_kph:.1f} km/h")
        if "volume" in gdf.columns:
            popup_parts.append(f"<b>Volume:</b> {int(row['volume'])} veh")

        popup_html = "<br>".join(popup_parts)

        folium.PolyLine(
            locations=folium_coords,
            color=color,
            weight=3,
            opacity=0.8,
            popup=folium.Popup(popup_html, max_width=200),
        ).add_to(m)

        segment_count += 1

    # ------------------------------------------------------------------
    # Add colour legend
    # ------------------------------------------------------------------
    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px; left: 30px;
        z-index: 1000;
        background-color: white;
        padding: 10px 14px;
        border: 2px solid #999;
        border-radius: 5px;
        font-size: 13px;
        line-height: 1.6;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
    ">
        <b>Congestion Level</b><br>
        <i style="background:#00FF00;width:14px;height:14px;display:inline-block;
          border:1px solid #666;"></i>&nbsp; Free flow (0%)<br>
        <i style="background:#FFFF00;width:14px;height:14px;display:inline-block;
          border:1px solid #666;"></i>&nbsp; Moderate (50%)<br>
        <i style="background:#FF0000;width:14px;height:14px;display:inline-block;
          border:1px solid #666;"></i>&nbsp; Congested (100%)
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ------------------------------------------------------------------
    # Save to HTML
    # ------------------------------------------------------------------
    m.save(str(output_path))

    logger.info(
        "create_interactive_map: saved interactive map with %d segments to %s",
        segment_count,
        output_path,
    )

    return output_path
