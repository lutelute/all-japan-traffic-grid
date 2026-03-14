"""Parse MATSim events.xml.gz into visualization-ready JSON data.

Extracts agent trajectories, link-level traffic counts, and signal
state changes from MATSim event output for use with the deck.gl
web visualization.
"""

import gzip
import json
import logging
from collections import defaultdict
from pathlib import Path
from xml.etree.ElementTree import iterparse

from lxml import etree

logger = logging.getLogger(__name__)


def _load_network_coords(network_path: Path) -> dict[str, dict]:
    """Load node coordinates and link geometries from network.xml."""
    nodes = {}
    links = {}

    tree = etree.parse(str(network_path))
    root = tree.getroot()

    for node_elem in root.iter("node"):
        nid = node_elem.get("id")
        nodes[nid] = {
            "x": float(node_elem.get("x", 0)),
            "y": float(node_elem.get("y", 0)),
        }

    for link_elem in root.iter("link"):
        lid = link_elem.get("id")
        from_id = link_elem.get("from")
        to_id = link_elem.get("to")
        if from_id in nodes and to_id in nodes:
            links[lid] = {
                "from": from_id,
                "to": to_id,
                "from_coords": [nodes[from_id]["x"], nodes[from_id]["y"]],
                "to_coords": [nodes[to_id]["x"], nodes[to_id]["y"]],
            }

    return {"nodes": nodes, "links": links}


def _utm_to_lonlat(x: float, y: float, epsg: int = 32654) -> tuple[float, float]:
    """Convert UTM coordinates back to lon/lat for visualization."""
    import pyproj

    key = f"_inv_{epsg}"
    if not hasattr(_utm_to_lonlat, key):
        setattr(
            _utm_to_lonlat,
            key,
            pyproj.Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True),
        )
    tf = getattr(_utm_to_lonlat, key)
    return tf.transform(x, y)


def parse_events_to_trajectories(
    events_path: Path,
    network_path: Path,
    output_dir: Path,
    time_bin_seconds: int = 300,
    max_agents: int = 5000,
    utm_epsg: int = 32654,
) -> dict[str, Path]:
    """Parse MATSim events into visualization JSON files.

    Parameters
    ----------
    events_path:
        Path to events.xml.gz or events.xml.
    network_path:
        Path to network.xml (for link-to-coordinate mapping).
    output_dir:
        Directory to write output JSON files.
    time_bin_seconds:
        Time bin size for link count aggregation (seconds).
    max_agents:
        Maximum number of agent trajectories to extract (for performance).
    utm_epsg:
        EPSG code of the UTM zone used in the network.

    Returns
    -------
    dict[str, Path]
        Mapping of output type to file path:
        - "trajectories": agent movement paths
        - "link_counts": per-link vehicle counts over time
        - "network_geojson": network as GeoJSON for overlay
    """
    events_path = Path(events_path)
    network_path = Path(network_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading network from %s", network_path)
    net = _load_network_coords(network_path)

    logger.info("Parsing events from %s (max_agents=%d)", events_path, max_agents)

    # Track agent positions
    agent_links: dict[str, list[tuple[float, str]]] = defaultdict(list)
    # Track link occupancy
    link_vehicles: dict[str, set] = defaultdict(set)
    link_counts_by_time: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    agents_seen: set[str] = set()

    # Open events file
    if str(events_path).endswith(".gz"):
        f = gzip.open(str(events_path), "rb")
    else:
        f = open(str(events_path), "rb")

    try:
        for event, elem in iterparse(f, events=("end",)):
            if elem.tag != "event":
                elem.clear()
                continue

            event_type = elem.get("type", "")
            time = float(elem.get("time", 0))
            person = elem.get("person", "")

            # Skip transit/freight agents
            if person.startswith("pt_") or person.startswith("freight_"):
                elem.clear()
                continue

            if event_type == "entered link":
                link_id = elem.get("link", "")
                if person and link_id:
                    if len(agents_seen) < max_agents or person in agents_seen:
                        agents_seen.add(person)
                        agent_links[person].append((time, link_id))
                    # Track occupancy
                    link_vehicles[link_id].add(person)
                    time_bin = int(time // time_bin_seconds)
                    link_counts_by_time[link_id][time_bin] = len(link_vehicles[link_id])

            elif event_type == "left link":
                link_id = elem.get("link", "")
                if person and link_id:
                    link_vehicles[link_id].discard(person)

            elem.clear()
    finally:
        f.close()

    logger.info("Parsed %d agent trajectories, %d links with traffic",
                len(agent_links), len(link_counts_by_time))

    # --- Build trajectory JSON ---
    trajectories = []
    for agent_id, events_list in agent_links.items():
        path = []
        for time, link_id in events_list:
            if link_id in net["links"]:
                link_info = net["links"][link_id]
                lon, lat = _utm_to_lonlat(
                    link_info["from_coords"][0],
                    link_info["from_coords"][1],
                    utm_epsg,
                )
                path.append([lon, lat, time])
        if len(path) >= 2:
            trajectories.append({
                "agent_id": agent_id,
                "path": path,
            })

    traj_path = output_dir / "trajectories.json"
    with open(traj_path, "w") as f:
        json.dump(trajectories, f)
    logger.info("Wrote %d trajectories → %s", len(trajectories), traj_path)

    # --- Build link counts JSON ---
    max_time_bin = 0
    for link_id, bins in link_counts_by_time.items():
        if bins:
            max_time_bin = max(max_time_bin, max(bins.keys()))

    timestamps = [i * time_bin_seconds for i in range(max_time_bin + 1)]
    link_data = {}

    for link_id, bins in link_counts_by_time.items():
        if link_id not in net["links"]:
            continue
        link_info = net["links"][link_id]
        from_lon, from_lat = _utm_to_lonlat(
            link_info["from_coords"][0], link_info["from_coords"][1], utm_epsg)
        to_lon, to_lat = _utm_to_lonlat(
            link_info["to_coords"][0], link_info["to_coords"][1], utm_epsg)

        counts = [bins.get(i, 0) for i in range(max_time_bin + 1)]
        link_data[link_id] = {
            "coords": [[from_lon, from_lat], [to_lon, to_lat]],
            "counts": counts,
        }

    counts_path = output_dir / "link_counts.json"
    with open(counts_path, "w") as f:
        json.dump({"timestamps": timestamps, "links": link_data}, f)
    logger.info("Wrote link counts (%d links, %d time bins) → %s",
                len(link_data), len(timestamps), counts_path)

    # --- Build network GeoJSON ---
    features = []
    for link_id, link_info in net["links"].items():
        from_lon, from_lat = _utm_to_lonlat(
            link_info["from_coords"][0], link_info["from_coords"][1], utm_epsg)
        to_lon, to_lat = _utm_to_lonlat(
            link_info["to_coords"][0], link_info["to_coords"][1], utm_epsg)
        features.append({
            "type": "Feature",
            "properties": {"id": link_id},
            "geometry": {
                "type": "LineString",
                "coordinates": [[from_lon, from_lat], [to_lon, to_lat]],
            },
        })

    geojson_path = output_dir / "network.geojson"
    with open(geojson_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    logger.info("Wrote network GeoJSON (%d features) → %s", len(features), geojson_path)

    return {
        "trajectories": traj_path,
        "link_counts": counts_path,
        "network_geojson": geojson_path,
    }
