"""Convert NetworkX DiGraph to MATSim network.xml.

Transforms the existing road network graph (built by src.network.builder)
into MATSim's XML network format with proper projected coordinates (UTM),
link capacities, and free-flow speeds.
"""

import logging
import math
from pathlib import Path

import networkx as nx
from lxml import etree

from src.config import DEFAULT_CAPACITY_PER_LANE

logger = logging.getLogger(__name__)

# Fallbacks
_FALLBACK_CAPACITY_PER_LANE: int = 600
_FALLBACK_SPEED_KPH: float = 40.0
_FALLBACK_LANES: int = 1
_FALLBACK_LENGTH: float = 500.0


def _auto_utm_epsg(lon: float, lat: float) -> int:
    """Determine the UTM EPSG code for a given lon/lat."""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def _deg_to_utm(lon: float, lat: float, central_meridian: float) -> tuple[float, float]:
    """Simplified UTM projection from WGS84 degrees.

    Uses a direct transverse Mercator approximation accurate to ~1m for Japan.
    """
    import pyproj

    # Cache the transformer on the function object
    key = f"_tf_{central_meridian}"
    if not hasattr(_deg_to_utm, key):
        zone = int((central_meridian + 180) / 6) + 1
        epsg = 32600 + zone  # Northern hemisphere
        setattr(
            _deg_to_utm,
            key,
            pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True),
        )
    tf = getattr(_deg_to_utm, key)
    return tf.transform(lon, lat)


def convert_to_matsim_network(
    graph: nx.DiGraph,
    output_path: Path,
    crs: str | None = None,
) -> Path:
    """Convert a NetworkX road graph to MATSim network.xml.

    Parameters
    ----------
    graph:
        NetworkX DiGraph from src.network.builder.build_graph.
        Nodes must have 'x' (lon) and 'y' (lat) attributes.
        Edges should have 'length', 'speed_kph', 'lanes', 'highway'.
    output_path:
        Where to write the network.xml file.
    crs:
        Target CRS as EPSG string (e.g. "EPSG:32654").
        If None, auto-detects UTM zone from network centroid.

    Returns
    -------
    Path
        The output file path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if graph.number_of_nodes() == 0:
        raise ValueError("Cannot convert empty graph")

    # Determine centroid for UTM projection
    lons = [d["x"] for _, d in graph.nodes(data=True) if "x" in d]
    lats = [d["y"] for _, d in graph.nodes(data=True) if "y" in d]
    centroid_lon = sum(lons) / len(lons)
    centroid_lat = sum(lats) / len(lats)

    if crs is None:
        epsg_code = _auto_utm_epsg(centroid_lon, centroid_lat)
        crs = f"EPSG:{epsg_code}"

    logger.info("Converting graph (%d nodes, %d edges) to MATSim network.xml with CRS %s",
                graph.number_of_nodes(), graph.number_of_edges(), crs)

    # Build XML
    root = etree.Element("network")
    root.set("name", "japan_traffic_network")

    # Coordinate reference system attribute
    attrs_elem = etree.SubElement(root, "attributes")
    attr_elem = etree.SubElement(attrs_elem, "attribute")
    attr_elem.set("name", "coordinateReferenceSystem")
    attr_elem.set("class", "java.lang.String")
    attr_elem.text = crs

    # Nodes
    nodes_elem = etree.SubElement(root, "nodes")
    node_coords: dict[str, tuple[float, float]] = {}

    for node_id, attrs in graph.nodes(data=True):
        lon = attrs.get("x", 0.0)
        lat = attrs.get("y", 0.0)
        x, y = _deg_to_utm(lon, lat, centroid_lon)
        node_coords[str(node_id)] = (x, y)

        node_elem = etree.SubElement(nodes_elem, "node")
        node_elem.set("id", str(node_id))
        node_elem.set("x", f"{x:.2f}")
        node_elem.set("y", f"{y:.2f}")

    # Links
    links_elem = etree.SubElement(root, "links")
    link_count = 0
    seen_names: set[str] = set()

    for u, v, attrs in graph.edges(data=True):
        if u == v:
            continue

        link_name = f"{u}_{v}"
        if link_name in seen_names:
            suffix = 1
            while f"{link_name}_{suffix}" in seen_names:
                suffix += 1
            link_name = f"{link_name}_{suffix}"
        seen_names.add(link_name)

        # Length
        length = attrs.get("length", _FALLBACK_LENGTH)
        if length is None or length <= 0:
            length = _FALLBACK_LENGTH

        # Speed
        speed_kph = attrs.get("speed_kph", _FALLBACK_SPEED_KPH)
        if speed_kph is None or speed_kph <= 0:
            speed_kph = _FALLBACK_SPEED_KPH
        freespeed = speed_kph / 3.6  # m/s

        # Lanes
        lanes = attrs.get("lanes", _FALLBACK_LANES)
        if lanes is None or lanes <= 0:
            lanes = _FALLBACK_LANES

        # Capacity
        highway_type = attrs.get("highway", "")
        cap_per_lane = DEFAULT_CAPACITY_PER_LANE.get(highway_type, _FALLBACK_CAPACITY_PER_LANE)
        capacity = cap_per_lane * lanes

        link_elem = etree.SubElement(links_elem, "link")
        link_elem.set("id", link_name)
        link_elem.set("from", str(u))
        link_elem.set("to", str(v))
        link_elem.set("length", f"{length:.2f}")
        link_elem.set("freespeed", f"{freespeed:.2f}")
        link_elem.set("capacity", f"{capacity:.1f}")
        link_elem.set("permlanes", str(int(lanes)))
        link_elem.set("modes", "car")

        link_count += 1

    # Write XML
    tree = etree.ElementTree(root)
    etree.indent(tree, space="  ")

    with open(output_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b'<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">\n')
        tree.write(f, pretty_print=True, xml_declaration=False, encoding="UTF-8")

    logger.info("Wrote MATSim network: %d nodes, %d links → %s",
                len(node_coords), link_count, output_path)
    return output_path


def get_node_coords(graph: nx.DiGraph, centroid_lon: float | None = None) -> dict[str, tuple[float, float]]:
    """Get UTM coordinates for all nodes (for use by other modules).

    Returns a dict mapping node_id (str) → (x_utm, y_utm).
    """
    if centroid_lon is None:
        lons = [d["x"] for _, d in graph.nodes(data=True) if "x" in d]
        centroid_lon = sum(lons) / len(lons)

    coords = {}
    for node_id, attrs in graph.nodes(data=True):
        lon = attrs.get("x", 0.0)
        lat = attrs.get("y", 0.0)
        x, y = _deg_to_utm(lon, lat, centroid_lon)
        coords[str(node_id)] = (x, y)
    return coords
