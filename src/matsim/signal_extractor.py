"""Extract traffic signals from OSM and generate MATSim signal XML files.

Reads highway=traffic_signals nodes from OSM PBF data, matches them to
network graph nodes, and produces the three MATSim signal system XMLs:
- signalSystems.xml
- signalGroups.xml
- signalControl.xml
"""

import logging
import math
from pathlib import Path

import networkx as nx
from lxml import etree

from src.config import (
    DEFAULT_SIGNAL_AMBER_TIME,
    DEFAULT_SIGNAL_CYCLE_TIME,
    DEFAULT_SIGNAL_GREEN_SPLIT,
)

logger = logging.getLogger(__name__)


def _compute_bearing(x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute bearing in degrees [0, 360) from point 1 to point 2."""
    dx = x2 - x1
    dy = y2 - y1
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    return bearing


def _classify_direction(bearing: float) -> str:
    """Classify bearing into NS or EW group."""
    # 0-45, 135-225, 315-360 → NS
    # 45-135, 225-315 → EW
    b = bearing % 360
    if (0 <= b < 45) or (135 <= b < 225) or (315 <= b < 360):
        return "NS"
    return "EW"


def extract_signals_from_osm(
    pbf_path: Path,
    graph: nx.DiGraph,
    match_threshold_deg: float = 0.001,
) -> list[dict]:
    """Extract traffic signal locations from OSM PBF and match to graph nodes.

    Parameters
    ----------
    pbf_path:
        Path to the OSM PBF file.
    graph:
        NetworkX DiGraph with node attributes 'x' (lon) and 'y' (lat).
    match_threshold_deg:
        Maximum distance in degrees to match an OSM signal node to a
        graph node (~111m at Japan's latitude).

    Returns
    -------
    list[dict]
        Each dict has 'node_id', 'lon', 'lat', 'osm_id'.
    """
    pbf_path = Path(pbf_path)
    if not pbf_path.is_file():
        raise FileNotFoundError(f"PBF file not found: {pbf_path}")

    try:
        from pyrosm import OSM
    except ImportError as exc:
        raise ImportError("pyrosm is required: pip install pyrosm>=0.6.2") from exc

    logger.info("Extracting traffic signals from %s", pbf_path)
    osm = OSM(str(pbf_path))

    # Extract POIs/custom data with highway=traffic_signals
    try:
        signals_gdf = osm.get_data_by_custom_criteria(
            custom_filter={"highway": ["traffic_signals"]},
            osm_keys_to_keep=["highway"],
            filter_type="keep",
        )
    except Exception:
        logger.warning("Could not extract traffic signals via custom criteria, "
                       "falling back to node-based extraction")
        signals_gdf = None

    if signals_gdf is None or len(signals_gdf) == 0:
        logger.warning("No traffic signal nodes found in PBF")
        return []

    # Filter to Point geometries only
    from shapely.geometry import Point
    signals_gdf = signals_gdf[signals_gdf.geometry.geom_type == "Point"]
    logger.info("Found %d traffic signal point features in OSM", len(signals_gdf))

    # Build spatial index of graph nodes
    graph_nodes = {}
    for node_id, attrs in graph.nodes(data=True):
        if "x" in attrs and "y" in attrs:
            graph_nodes[str(node_id)] = (attrs["x"], attrs["y"])

    # Match signal nodes to nearest graph node
    matched = []
    for _, row in signals_gdf.iterrows():
        sig_lon = row.geometry.x
        sig_lat = row.geometry.y
        osm_id = row.get("id", row.get("osm_id", ""))

        best_dist = float("inf")
        best_node = None
        for nid, (nx_, ny_) in graph_nodes.items():
            dist = math.sqrt((sig_lon - nx_) ** 2 + (sig_lat - ny_) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_node = nid

        if best_node is not None and best_dist <= match_threshold_deg:
            matched.append({
                "node_id": best_node,
                "lon": sig_lon,
                "lat": sig_lat,
                "osm_id": str(osm_id),
            })

    # Deduplicate by node_id (multiple OSM signals may map to same graph node)
    seen = set()
    unique = []
    for m in matched:
        if m["node_id"] not in seen:
            seen.add(m["node_id"])
            unique.append(m)

    logger.info("Matched %d unique signal nodes to graph (from %d OSM features)",
                len(unique), len(signals_gdf))
    return unique


def generate_signal_xmls(
    signal_nodes: list[dict],
    graph: nx.DiGraph,
    output_dir: Path,
    cycle_time: int = DEFAULT_SIGNAL_CYCLE_TIME,
) -> tuple[Path, Path, Path]:
    """Generate MATSim signal system XML files.

    Parameters
    ----------
    signal_nodes:
        List of matched signal nodes from extract_signals_from_osm.
    graph:
        NetworkX DiGraph.
    output_dir:
        Directory to write the XML files.
    cycle_time:
        Default signal cycle time in seconds.

    Returns
    -------
    tuple of 3 Paths:
        (signalSystems.xml, signalGroups.xml, signalControl.xml)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- signalSystems.xml ---
    systems_root = etree.Element("signalSystems")
    systems_root.set("xmlns", "http://www.matsim.org/files/dtd")
    systems_root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

    # --- signalGroups.xml ---
    groups_root = etree.Element("signalGroups")
    groups_root.set("xmlns", "http://www.matsim.org/files/dtd")

    # --- signalControl.xml ---
    control_root = etree.Element("signalControl")
    control_root.set("xmlns", "http://www.matsim.org/files/dtd")

    signal_count = 0

    for sig in signal_nodes:
        node_id = sig["node_id"]

        # Find incoming links (edges where this node is the target)
        incoming_edges = []
        for u, v, attrs in graph.in_edges(node_id, data=True):
            link_id = f"{u}_{v}"
            # Get bearing from predecessor to this node
            u_attrs = graph.nodes.get(u, {})
            v_attrs = graph.nodes.get(v, {})
            if "x" in u_attrs and "x" in v_attrs:
                bearing = _compute_bearing(
                    u_attrs["x"], u_attrs["y"],
                    v_attrs["x"], v_attrs["y"],
                )
            else:
                bearing = 0.0
            incoming_edges.append({
                "link_id": link_id,
                "from_node": str(u),
                "bearing": bearing,
                "lanes": attrs.get("lanes", 1),
            })

        if len(incoming_edges) < 2:
            continue  # Need at least 2 approaches for a signal

        system_id = f"signal_{node_id}"

        # --- Signal System ---
        system_elem = etree.SubElement(systems_root, "signalSystem")
        system_elem.set("id", system_id)
        signals_elem = etree.SubElement(system_elem, "signals")

        for i, edge in enumerate(incoming_edges):
            signal_elem = etree.SubElement(signals_elem, "signal")
            signal_elem.set("id", f"s_{edge['link_id']}")
            signal_elem.set("linkId", edge["link_id"])

        # --- Signal Groups (NS vs EW) ---
        groups_system = etree.SubElement(groups_root, "signalSystem")
        groups_system.set("refId", system_id)

        ns_signals = []
        ew_signals = []
        for edge in incoming_edges:
            direction = _classify_direction(edge["bearing"])
            sig_id = f"s_{edge['link_id']}"
            if direction == "NS":
                ns_signals.append(sig_id)
            else:
                ew_signals.append(sig_id)

        # Ensure both groups have at least one signal
        if not ns_signals:
            ns_signals.append(ew_signals.pop())
        if not ew_signals:
            ew_signals.append(ns_signals.pop())

        ns_group_id = f"group_NS_{node_id}"
        ew_group_id = f"group_EW_{node_id}"

        ns_group = etree.SubElement(groups_system, "signalGroup")
        ns_group.set("id", ns_group_id)
        for sid in ns_signals:
            ref = etree.SubElement(ns_group, "signal")
            ref.set("refId", sid)

        ew_group = etree.SubElement(groups_system, "signalGroup")
        ew_group.set("id", ew_group_id)
        for sid in ew_signals:
            ref = etree.SubElement(ew_group, "signal")
            ref.set("refId", sid)

        # --- Signal Control (fixed-time plan) ---
        control_system = etree.SubElement(control_root, "signalSystem")
        control_system.set("refId", system_id)

        plan = etree.SubElement(control_system, "signalPlan")
        plan.set("id", f"plan_{node_id}")

        cycle_elem = etree.SubElement(plan, "cycleTime")
        cycle_elem.set("sec", str(cycle_time))

        offset_elem = etree.SubElement(plan, "offset")
        offset_elem.set("sec", "0")

        # Compute green splits based on lane count
        ns_lanes = sum(e["lanes"] for e in incoming_edges
                       if f"s_{e['link_id']}" in ns_signals)
        ew_lanes = sum(e["lanes"] for e in incoming_edges
                       if f"s_{e['link_id']}" in ew_signals)
        total_lanes = max(ns_lanes + ew_lanes, 1)

        amber = DEFAULT_SIGNAL_AMBER_TIME
        effective_green = cycle_time - 2 * amber
        ns_green = max(int(effective_green * ns_lanes / total_lanes), 10)
        ew_green = max(effective_green - ns_green, 10)

        # NS phase: onset=0, dropping=ns_green
        ns_settings = etree.SubElement(plan, "signalGroupSettings")
        ns_settings.set("refId", ns_group_id)
        onset = etree.SubElement(ns_settings, "onset")
        onset.set("sec", "0")
        dropping = etree.SubElement(ns_settings, "dropping")
        dropping.set("sec", str(ns_green))

        # EW phase: onset=ns_green+amber, dropping=ns_green+amber+ew_green
        ew_settings = etree.SubElement(plan, "signalGroupSettings")
        ew_settings.set("refId", ew_group_id)
        onset2 = etree.SubElement(ew_settings, "onset")
        onset2.set("sec", str(ns_green + amber))
        dropping2 = etree.SubElement(ew_settings, "dropping")
        dropping2.set("sec", str(ns_green + amber + ew_green))

        signal_count += 1

    # Write files
    paths = []
    for filename, root_elem in [
        ("signalSystems.xml", systems_root),
        ("signalGroups.xml", groups_root),
        ("signalControl.xml", control_root),
    ]:
        tree = etree.ElementTree(root_elem)
        etree.indent(tree, space="  ")
        filepath = output_dir / filename
        with open(filepath, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(f, pretty_print=True, xml_declaration=False, encoding="UTF-8")
        paths.append(filepath)

    logger.info("Generated signal XMLs for %d intersections → %s", signal_count, output_dir)
    return tuple(paths)
