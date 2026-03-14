"""Partitioned MATSim simulation for large-scale Japan-wide runs.

Splits Japan into sub-areas, runs MATSim independently per area with
boundary demand exchange, and merges results into unified visualization.

Two-pass approach:
  Pass 1: Run all areas independently, extract boundary crossings
  Pass 2: Re-run with injected cross-boundary demand, merge results
"""

import json
import logging
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PartitionArea:
    """Definition of a simulation sub-area."""
    name: str
    core_bbox: tuple[float, float, float, float]  # (south, west, north, east)
    buffer_deg: float = 0.05  # ~5km buffer
    agents: int = 10000
    neighbors: list[str] = field(default_factory=list)

    @property
    def extended_bbox(self) -> tuple[float, float, float, float]:
        s, w, n, e = self.core_bbox
        b = self.buffer_deg
        return (s - b, w - b, n + b, e + b)


@dataclass
class BoundaryLink:
    link_id: str
    from_node: str
    to_node: str
    from_area: str
    to_area: str


@dataclass
class CrossBoundaryRecord:
    agent_id: str
    time: float
    link_id: str
    from_area: str
    to_area: str
    lon: float
    lat: float


# ---------------------------------------------------------------------------
# Predefined partition areas for Kanto
# ---------------------------------------------------------------------------

KANTO_PARTITIONS: list[PartitionArea] = [
    PartitionArea(
        name="tokyo_central",
        core_bbox=(35.60, 139.60, 35.78, 139.85),
        agents=15000,
        neighbors=["tokyo_west", "saitama", "chiba", "kawasaki"],
    ),
    PartitionArea(
        name="tokyo_west",
        core_bbox=(35.60, 139.30, 35.80, 139.60),
        agents=8000,
        neighbors=["tokyo_central", "saitama"],
    ),
    PartitionArea(
        name="yokohama",
        core_bbox=(35.30, 139.50, 35.52, 139.75),
        agents=10000,
        neighbors=["kawasaki"],
    ),
    PartitionArea(
        name="kawasaki",
        core_bbox=(35.48, 139.55, 35.60, 139.80),
        agents=6000,
        neighbors=["tokyo_central", "yokohama"],
    ),
    PartitionArea(
        name="saitama",
        core_bbox=(35.78, 139.40, 36.10, 139.90),
        agents=8000,
        neighbors=["tokyo_central", "tokyo_west", "chiba"],
    ),
    PartitionArea(
        name="chiba",
        core_bbox=(35.50, 139.85, 35.90, 140.30),
        agents=8000,
        neighbors=["tokyo_central", "saitama"],
    ),
]

# Full Japan partitions — focused on metro areas (compact bboxes for fast OSM fetch)
JAPAN_PARTITIONS: list[PartitionArea] = [
    PartitionArea("sapporo", (42.85, 141.15, 43.20, 141.55), agents=5000),
    PartitionArea("sendai", (38.10, 140.70, 38.40, 141.05), agents=4000),
    PartitionArea("kanto_north", (35.78, 139.40, 36.15, 139.95), agents=10000,
                  neighbors=["kanto_south"]),
    PartitionArea("kanto_south", (35.35, 139.40, 35.78, 140.00), agents=15000,
                  neighbors=["kanto_north"]),
    PartitionArea("nagoya", (34.90, 136.70, 35.30, 137.15), agents=8000,
                  neighbors=["kansai"]),
    PartitionArea("kansai", (34.50, 135.20, 35.05, 135.85), agents=10000,
                  neighbors=["nagoya", "hiroshima"]),
    PartitionArea("hiroshima", (34.20, 132.25, 34.55, 132.65), agents=4000,
                  neighbors=["kansai", "fukuoka"]),
    PartitionArea("matsuyama", (33.70, 132.60, 33.95, 132.90), agents=3000),
    PartitionArea("fukuoka", (33.40, 130.20, 33.75, 130.60), agents=6000,
                  neighbors=["hiroshima"]),
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _point_in_bbox(lon: float, lat: float,
                   bbox: tuple[float, float, float, float]) -> bool:
    """Check if (lon, lat) is inside bbox (south, west, north, east)."""
    s, w, n, e = bbox
    return s <= lat <= n and w <= lon <= e


def identify_boundary_links(
    graph: nx.DiGraph,
    area_a: PartitionArea,
    area_b: PartitionArea,
) -> list[BoundaryLink]:
    """Find links that cross the boundary between two areas."""
    boundary = []
    for u, v, data in graph.edges(data=True):
        u_attrs = graph.nodes.get(u, {})
        v_attrs = graph.nodes.get(v, {})
        if "x" not in u_attrs or "x" not in v_attrs:
            continue

        u_in_a = _point_in_bbox(u_attrs["x"], u_attrs["y"], area_a.core_bbox)
        v_in_a = _point_in_bbox(v_attrs["x"], v_attrs["y"], area_a.core_bbox)
        u_in_b = _point_in_bbox(u_attrs["x"], u_attrs["y"], area_b.core_bbox)
        v_in_b = _point_in_bbox(v_attrs["x"], v_attrs["y"], area_b.core_bbox)

        if u_in_a and v_in_b:
            boundary.append(BoundaryLink(
                link_id=f"{u}_{v}",
                from_node=str(u), to_node=str(v),
                from_area=area_a.name, to_area=area_b.name,
            ))
        elif u_in_b and v_in_a:
            boundary.append(BoundaryLink(
                link_id=f"{u}_{v}",
                from_node=str(u), to_node=str(v),
                from_area=area_b.name, to_area=area_a.name,
            ))

    return boundary


def extract_boundary_crossings(
    events_path: Path,
    boundary_link_ids: set[str],
    area_name: str,
    boundary_link_map: dict[str, BoundaryLink],
    network_coords: dict[str, tuple[float, float]],
) -> list[CrossBoundaryRecord]:
    """Extract agents crossing boundary links from MATSim events."""
    import gzip
    from xml.etree.ElementTree import iterparse

    records = []

    if str(events_path).endswith(".gz"):
        f = gzip.open(str(events_path), "rb")
    else:
        f = open(str(events_path), "rb")

    try:
        for _, elem in iterparse(f, events=("end",)):
            if elem.tag != "event":
                elem.clear()
                continue

            event_type = elem.get("type", "")
            if event_type != "entered link":
                elem.clear()
                continue

            link_id = elem.get("link", "")
            if link_id not in boundary_link_ids:
                elem.clear()
                continue

            agent_id = elem.get("vehicle", "") or elem.get("person", "")
            time = float(elem.get("time", 0))
            bl = boundary_link_map.get(link_id)
            if bl and agent_id:
                # Get coordinate at boundary
                to_node = bl.to_node
                lon, lat = network_coords.get(to_node, (0, 0))
                records.append(CrossBoundaryRecord(
                    agent_id=f"{area_name}_{agent_id}",
                    time=time,
                    link_id=link_id,
                    from_area=bl.from_area,
                    to_area=bl.to_area,
                    lon=lon, lat=lat,
                ))

            elem.clear()
    finally:
        f.close()

    return records


# ---------------------------------------------------------------------------
# Single area simulation
# ---------------------------------------------------------------------------

def _run_single_area(
    area: PartitionArea,
    output_base: Path,
    iterations: int,
    sample_rate: float,
    jvm_memory: str,
    java_path: str,
    inbound_demand: list[dict] | None = None,
    pass_num: int = 1,
) -> dict:
    """Run MATSim for a single partition area."""
    # Import here to avoid circular imports in subprocess
    import logging
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                        datefmt='%H:%M:%S')

    from src.matsim.pipeline import (
        _get_osmnx_graph,
        _osmnx_to_simple_digraph,
        REGION_BBOX,
    )
    from src.matsim.network_converter import convert_to_matsim_network
    from src.matsim.population import generate_population
    from src.matsim.config_generator import generate_config
    from src.matsim.runner import run_matsim, find_events_file

    area_dir = output_base / f"{area.name}_pass{pass_num}"
    area_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_base / "cache"

    logger = logging.getLogger(f"partition.{area.name}")
    logger.info("=== Area '%s' Pass %d: %d agents ===", area.name, pass_num, area.agents)

    # Use extended bbox for network
    s, w, n, e = area.extended_bbox

    # Temporarily add to REGION_BBOX for osmnx fetch
    from src.matsim.pipeline import REGION_BBOX as rbbox
    rbbox[f"_part_{area.name}"] = area.extended_bbox

    G_multi = _get_osmnx_graph(f"_part_{area.name}", cache_dir)
    graph = _osmnx_to_simple_digraph(G_multi)

    # Strongly connected component
    sccs = list(nx.strongly_connected_components(graph))
    sccs.sort(key=len, reverse=True)
    graph = graph.subgraph(sccs[0]).copy()
    logger.info("SCC: %d nodes, %d edges", graph.number_of_nodes(), graph.number_of_edges())

    # Network XML
    network_path = area_dir / "network.xml"
    convert_to_matsim_network(graph, network_path)

    # Population (with optional cross-boundary demand injection)
    plans_path = area_dir / "plans.xml"

    # Determine region for population centers
    region_map = {
        "tokyo_central": "kanto", "tokyo_west": "kanto",
        "yokohama": "kanto", "kawasaki": "kanto",
        "saitama": "kanto", "chiba": "kanto",
        "kanto_north": "kanto", "kanto_south": "kanto",
        "sapporo": "hokkaido", "sendai": "tohoku",
        "nagoya": "chubu", "hiroshima": "chugoku",
        "matsuyama": "shikoku", "fukuoka": "kyushu",
    }
    pop_region = region_map.get(area.name, area.name)

    # Generate native population
    generate_population(graph, plans_path, region=pop_region,
                        total_agents=area.agents)

    # Inject boundary demand if provided (append to plans.xml)
    if inbound_demand:
        _inject_boundary_agents(plans_path, inbound_demand, graph, area)

    # Config
    config_path = generate_config(
        network_path=network_path,
        plans_path=plans_path,
        output_dir=area_dir,
        iterations=iterations,
        sample_rate=sample_rate,
    )

    # Run MATSim
    matsim_output = run_matsim(
        config_path=config_path,
        java_path=java_path,
        jvm_memory=jvm_memory,
    )

    events_file = find_events_file(matsim_output)

    # Build node coordinate map for boundary extraction
    node_coords = {}
    for nid, attrs in graph.nodes(data=True):
        if "x" in attrs and "y" in attrs:
            node_coords[str(nid)] = (attrs["x"], attrs["y"])

    return {
        "name": area.name,
        "events_path": str(events_file) if events_file else None,
        "network_path": str(network_path),
        "area_dir": str(area_dir),
        "matsim_output": str(matsim_output),
        "node_coords": node_coords,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
    }


def _inject_boundary_agents(
    plans_path: Path,
    inbound_demand: list[dict],
    graph: nx.DiGraph,
    area: PartitionArea,
) -> None:
    """Append cross-boundary agents to an existing plans.xml."""
    from lxml import etree
    from src.matsim.network_converter import _deg_to_utm

    tree = etree.parse(str(plans_path))
    root = tree.getroot()

    lons = [d["x"] for _, d in graph.nodes(data=True) if "x" in d]
    centroid_lon = sum(lons) / len(lons) if lons else 139.7

    for i, demand in enumerate(inbound_demand):
        entry_x, entry_y = _deg_to_utm(demand["lon"], demand["lat"], centroid_lon)
        arrival_time = demand["time"]

        # Format time
        h = int(arrival_time // 3600)
        m = int((arrival_time % 3600) // 60)
        s = int(arrival_time % 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"

        # Create agent with simple activity
        person = etree.SubElement(root, "person")
        person.set("id", f"boundary_{demand['from_area']}_{i}")

        plan = etree.SubElement(person, "plan")
        plan.set("selected", "yes")

        # "arrive" activity at boundary point
        act1 = etree.SubElement(plan, "activity")
        act1.set("type", "home")
        act1.set("x", f"{entry_x:.2f}")
        act1.set("y", f"{entry_y:.2f}")
        act1.set("end_time", time_str)

        leg = etree.SubElement(plan, "leg")
        leg.set("mode", "car")

        # Drive to a random point within area
        import random
        rng = random.Random(i + hash(demand["from_area"]))
        s, w, n, e = area.core_bbox
        dest_lon = rng.uniform(w, e)
        dest_lat = rng.uniform(s, n)
        dest_x, dest_y = _deg_to_utm(dest_lon, dest_lat, centroid_lon)

        act2 = etree.SubElement(plan, "activity")
        act2.set("type", "work")
        act2.set("x", f"{dest_x:.2f}")
        act2.set("y", f"{dest_y:.2f}")

    etree.indent(tree, space="  ")
    with open(plans_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b'<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n')
        tree.write(f, pretty_print=True, xml_declaration=False, encoding="UTF-8")

    logger.info("Injected %d boundary agents into %s", len(inbound_demand), plans_path)


# ---------------------------------------------------------------------------
# Merge results
# ---------------------------------------------------------------------------

def merge_all_events(
    area_results: list[dict],
    output_dir: Path,
    max_agents_per_area: int = 2000,
) -> dict[str, Path]:
    """Merge events from all areas into unified visualization data."""
    from src.matsim.event_parser import (
        parse_events_to_trajectories,
        _load_network_coords,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_trajectories = []
    all_link_data = {}
    all_timestamps = []
    all_network_features = []
    seen_links = set()

    for result in area_results:
        if not result.get("events_path"):
            continue

        events_path = Path(result["events_path"])
        network_path = Path(result["network_path"])
        area_viz_dir = output_dir / f"_tmp_{result['name']}"

        logger.info("Parsing events for area '%s'", result["name"])
        viz = parse_events_to_trajectories(
            events_path=events_path,
            network_path=network_path,
            output_dir=area_viz_dir,
            max_agents=max_agents_per_area,
        )

        # Load and merge trajectories
        with open(viz["trajectories"]) as f:
            trajs = json.load(f)
        # Namespace agent IDs
        for t in trajs:
            t["agent_id"] = f"{result['name']}_{t['agent_id']}"
        all_trajectories.extend(trajs)

        # Load and merge link counts
        with open(viz["link_counts"]) as f:
            lc = json.load(f)
        if len(lc["timestamps"]) > len(all_timestamps):
            all_timestamps = lc["timestamps"]
        for link_id, data in lc["links"].items():
            ns_id = f"{result['name']}_{link_id}"
            if ns_id not in all_link_data:
                all_link_data[ns_id] = data

        # Load and merge network
        with open(viz["network_geojson"]) as f:
            net = json.load(f)
        for feat in net["features"]:
            fid = feat["properties"].get("id", "")
            ns_fid = f"{result['name']}_{fid}"
            if ns_fid not in seen_links:
                seen_links.add(ns_fid)
                feat["properties"]["id"] = ns_fid
                feat["properties"]["area"] = result["name"]
                all_network_features.append(feat)

        # Cleanup temp dir
        import shutil
        shutil.rmtree(area_viz_dir, ignore_errors=True)

    # Write merged files
    traj_path = output_dir / "trajectories.json"
    with open(traj_path, "w") as f:
        json.dump(all_trajectories, f)

    counts_path = output_dir / "link_counts.json"
    with open(counts_path, "w") as f:
        json.dump({"timestamps": all_timestamps, "links": all_link_data}, f)

    geojson_path = output_dir / "network.geojson"
    with open(geojson_path, "w") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": all_network_features,
        }, f)

    logger.info("Merged: %d trajectories, %d links, %d network features",
                len(all_trajectories), len(all_link_data), len(all_network_features))

    return {
        "trajectories": traj_path,
        "link_counts": counts_path,
        "network_geojson": geojson_path,
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_partitioned_pipeline(
    partitions: list[PartitionArea] | str = "kanto",
    iterations: int = 5,
    sample_rate: float = 0.1,
    jvm_memory: str = "4g",
    java_path: str = "/opt/homebrew/opt/openjdk@21/bin/java",
    max_workers: int = 2,
    output_dir: Path | None = None,
    two_pass: bool = True,
) -> dict[str, Path]:
    """Run partitioned MATSim simulation.

    Parameters
    ----------
    partitions:
        List of PartitionArea configs, or "kanto" / "japan" preset name.
    iterations:
        MATSim iterations per area.
    sample_rate:
        Flow/storage capacity factor.
    jvm_memory:
        JVM heap per area (keep lower since multiple JVMs run).
    java_path:
        Java executable path.
    max_workers:
        Max concurrent area simulations.
    output_dir:
        Output directory.
    two_pass:
        If True, run two passes with boundary demand exchange.
    """
    # Resolve partition preset
    if isinstance(partitions, str):
        if partitions == "kanto":
            partitions = KANTO_PARTITIONS
        elif partitions == "japan":
            partitions = JAPAN_PARTITIONS
        else:
            raise ValueError(f"Unknown partition preset: {partitions}")

    if output_dir is None:
        output_dir = OUTPUT_DIR / "matsim_partitioned"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_agents = sum(a.agents for a in partitions)
    logger.info("=== Partitioned MATSim: %d areas, %d total agents ===",
                len(partitions), total_agents)

    # ---- Pass 1: Independent runs ----
    logger.info("=== PASS 1: Independent area simulations ===")
    pass1_results = _run_areas_parallel(
        partitions, output_dir, iterations, sample_rate,
        jvm_memory, java_path, max_workers, pass_num=1,
    )

    if not two_pass:
        # Single pass — just merge
        viz_dir = output_dir / "viz"
        return merge_all_events(pass1_results, viz_dir)

    # ---- Extract boundary crossings ----
    logger.info("=== Extracting boundary crossings ===")
    area_map = {a.name: a for a in partitions}
    all_boundary_demand: dict[str, list[dict]] = {a.name: [] for a in partitions}

    for result in pass1_results:
        if not result.get("events_path") or not result.get("node_coords"):
            continue

        area = area_map[result["name"]]
        node_coords = result["node_coords"]

        # Build boundary link set for this area's neighbors
        # We need the graph — rebuild it from the network.xml node coords
        for neighbor_name in area.neighbors:
            if neighbor_name not in area_map:
                continue
            neighbor = area_map[neighbor_name]

            # Find boundary links using node coordinates
            boundary_links = {}
            for nid, (lon, lat) in node_coords.items():
                in_core = _point_in_bbox(lon, lat, area.core_bbox)
                in_neighbor = _point_in_bbox(lon, lat, neighbor.core_bbox)
                # We can't easily find links from just nodes, so use a simpler approach:
                # Any agent event on a link near the boundary is a crossing

            # Simplified: extract all events near the boundary zone
            # and treat them as boundary crossings
            boundary_band = _get_boundary_band(area.core_bbox, neighbor.core_bbox)
            if boundary_band is None:
                continue

            crossings = _extract_near_boundary(
                Path(result["events_path"]),
                Path(result["network_path"]),
                boundary_band,
                area.name, neighbor.name,
            )
            all_boundary_demand[neighbor.name].extend(crossings)

    demand_counts = {k: len(v) for k, v in all_boundary_demand.items() if v}
    logger.info("Boundary demand: %s", demand_counts)

    # ---- Pass 2: With boundary demand ----
    logger.info("=== PASS 2: With cross-boundary demand ===")
    pass2_results = _run_areas_parallel(
        partitions, output_dir, iterations, sample_rate,
        jvm_memory, java_path, max_workers, pass_num=2,
        boundary_demand=all_boundary_demand,
    )

    # ---- Merge ----
    logger.info("=== Merging all area results ===")
    viz_dir = output_dir / "viz"
    merged = merge_all_events(pass2_results, viz_dir)

    logger.info("Partitioned pipeline complete!")
    return merged


def _run_areas_parallel(
    partitions: list[PartitionArea],
    output_base: Path,
    iterations: int,
    sample_rate: float,
    jvm_memory: str,
    java_path: str,
    max_workers: int,
    pass_num: int = 1,
    boundary_demand: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Run multiple areas, sequentially (to manage memory)."""
    results = []
    for area in partitions:
        inbound = None
        if boundary_demand and area.name in boundary_demand:
            inbound = boundary_demand[area.name]

        try:
            result = _run_single_area(
                area=area,
                output_base=output_base,
                iterations=iterations,
                sample_rate=sample_rate,
                jvm_memory=jvm_memory,
                java_path=java_path,
                inbound_demand=inbound,
                pass_num=pass_num,
            )
            results.append(result)
            logger.info("Area '%s' pass %d complete: %d nodes, %d edges",
                        area.name, pass_num,
                        result.get("graph_nodes", 0), result.get("graph_edges", 0))
        except Exception as e:
            logger.error("Area '%s' pass %d failed: %s", area.name, pass_num, e)
            results.append({"name": area.name, "events_path": None})

    return results


def _get_boundary_band(
    bbox_a: tuple[float, float, float, float],
    bbox_b: tuple[float, float, float, float],
    band_width: float = 0.02,
) -> tuple[float, float, float, float] | None:
    """Get the narrow band where two bboxes meet."""
    s_a, w_a, n_a, e_a = bbox_a
    s_b, w_b, n_b, e_b = bbox_b

    # Check which edges are adjacent
    # A's north edge touches B's south edge
    if abs(n_a - s_b) < 0.1:
        return (n_a - band_width, max(w_a, w_b), s_b + band_width, min(e_a, e_b))
    # A's south edge touches B's north edge
    if abs(s_a - n_b) < 0.1:
        return (n_b - band_width, max(w_a, w_b), s_a + band_width, min(e_a, e_b))
    # A's east edge touches B's west edge
    if abs(e_a - w_b) < 0.1:
        return (max(s_a, s_b), e_a - band_width, min(n_a, n_b), w_b + band_width)
    # A's west edge touches B's east edge
    if abs(w_a - e_b) < 0.1:
        return (max(s_a, s_b), e_b - band_width, min(n_a, n_b), w_a + band_width)

    # Overlapping — find intersection
    s = max(s_a, s_b)
    w = max(w_a, w_b)
    n = min(n_a, n_b)
    e = min(e_a, e_b)
    if s < n and w < e:
        return (s, w, n, e)

    return None


def _extract_near_boundary(
    events_path: Path,
    network_path: Path,
    boundary_band: tuple[float, float, float, float],
    from_area: str,
    to_area: str,
    max_records: int = 1000,
) -> list[dict]:
    """Extract agent events near a boundary band."""
    import gzip
    from xml.etree.ElementTree import iterparse
    from src.matsim.event_parser import _load_network_coords, _utm_to_lonlat

    net = _load_network_coords(network_path)
    records = []

    if str(events_path).endswith(".gz"):
        f = gzip.open(str(events_path), "rb")
    else:
        f = open(str(events_path), "rb")

    s, w, n, e = boundary_band

    try:
        for _, elem in iterparse(f, events=("end",)):
            if elem.tag != "event":
                elem.clear()
                continue

            if elem.get("type") != "entered link":
                elem.clear()
                continue

            link_id = elem.get("link", "")
            if link_id not in net["links"]:
                elem.clear()
                continue

            link_info = net["links"][link_id]
            # Check if link endpoint is in boundary band
            to_x, to_y = link_info["to_coords"]
            lon, lat = _utm_to_lonlat(to_x, to_y)

            if s <= lat <= n and w <= lon <= e:
                agent_id = elem.get("vehicle", "") or elem.get("person", "")
                time = float(elem.get("time", 0))
                if agent_id:
                    records.append({
                        "agent_id": f"{from_area}_{agent_id}",
                        "time": time,
                        "from_area": from_area,
                        "to_area": to_area,
                        "lon": lon,
                        "lat": lat,
                    })
                    if len(records) >= max_records:
                        break

            elem.clear()
    finally:
        f.close()

    logger.info("Extracted %d boundary crossings: %s → %s", len(records), from_area, to_area)
    return records
