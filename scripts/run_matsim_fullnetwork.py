#!/usr/bin/env python3
"""Run MATSim on the full connected Japan-wide network.

Uses the same 9-region osmnx network as japan_traffic_animated.py,
merges into a single graph, and runs MATSim agent-based simulation.

Usage:
    python scripts/run_matsim_fullnetwork.py --agents 10000 --iterations 5
    python scripts/run_matsim_fullnetwork.py --agents 50000 --iterations 10 --jvm-memory 16g
"""

import argparse
import json
import logging
import pickle
import sys
from pathlib import Path

import networkx as nx
import osmnx as ox

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import DEFAULT_LANES_BY_TYPE, DEFAULT_SPEED_BY_TYPE, HIGHWAY_FILTER
from src.matsim.network_converter import convert_to_matsim_network
from src.matsim.population import generate_population
from src.matsim.config_generator import generate_config
from src.matsim.runner import run_matsim, find_events_file
from src.matsim.event_parser import parse_events_to_trajectories

logger = logging.getLogger(__name__)

# Same regions as japan_traffic_animated.py
REGIONS = {
    "hokkaido":  (41.3, 139.3, 45.6, 145.9),
    "tohoku":    (36.8, 139.0, 41.5, 142.1),
    "kanto":     (34.8, 138.5, 37.0, 140.9),
    "chubu":     (34.5, 135.5, 37.8, 139.0),
    "kansai":    (33.4, 134.0, 35.8, 136.5),
    "chugoku":   (33.5, 130.7, 35.7, 134.5),
    "shikoku":   (32.7, 132.0, 34.5, 134.8),
    "kyushu":    (30.2, 129.3, 34.0, 132.0),
    "okinawa":   (26.1, 127.5, 26.9, 128.0),
}

# Same road filter hierarchy as japan_traffic_animated.py
ROAD_FILTERS = [
    '["highway"~"motorway|trunk|primary"]',
    '["highway"~"motorway|trunk"]',
    '["highway"~"motorway"]',
]
MAX_LINKS_PER_REGION = 20000


def fetch_region_graph(name: str, bbox: tuple, cache_dir: Path) -> nx.MultiDiGraph | None:
    """Fetch osmnx graph for a region with caching."""
    cache_file = cache_dir / f"fullnet_{name}.pkl"
    if cache_file.exists():
        logger.info("Cached: %s", name)
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    south, west, north, east = bbox
    logger.info("Fetching %s (%.1f x %.1f deg)...", name, east - west, north - south)

    G = None
    for road_filter in ROAD_FILTERS:
        try:
            G = ox.graph_from_bbox(
                bbox=[west, south, east, north],
                network_type="drive",
                custom_filter=road_filter,
            )
            n_edges = G.number_of_edges()
            logger.info("  %s: %d edges with filter %s", name, n_edges, road_filter)
            if n_edges <= MAX_LINKS_PER_REGION * 1.1:
                break
            logger.info("  Too many edges, trying narrower filter")
            G = None
        except Exception as e:
            logger.warning("  Filter failed for %s: %s", name, e)
            G = None

    if G is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "wb") as f:
            pickle.dump(G, f)
        logger.info("  Cached %s: %d nodes, %d edges", name, G.number_of_nodes(), G.number_of_edges())

    return G


def merge_graphs(graphs: list[nx.MultiDiGraph]) -> nx.DiGraph:
    """Merge multiple osmnx MultiDiGraphs into a single DiGraph."""
    # Compose all MultiDiGraphs (OSM node IDs are shared at boundaries)
    merged = nx.MultiDiGraph()
    for G in graphs:
        merged = nx.compose(merged, G)

    logger.info("Merged MultiDiGraph: %d nodes, %d edges", merged.number_of_nodes(), merged.number_of_edges())

    # Convert to simple DiGraph with attributes
    simple = nx.DiGraph()
    for node_id, data in merged.nodes(data=True):
        simple.add_node(node_id, x=data.get("x", 0.0), y=data.get("y", 0.0))

    for u, v, data in merged.edges(data=True):
        if simple.has_edge(u, v) or u == v:
            continue

        highway = data.get("highway", "secondary")
        if isinstance(highway, list):
            highway = highway[0]

        maxspeed = data.get("maxspeed")
        if maxspeed:
            if isinstance(maxspeed, list):
                maxspeed = maxspeed[0]
            try:
                speed_kph = float(str(maxspeed).replace("km/h", "").strip())
            except (ValueError, TypeError):
                speed_kph = DEFAULT_SPEED_BY_TYPE.get(highway, 40.0)
        else:
            speed_kph = DEFAULT_SPEED_BY_TYPE.get(highway, 40.0)

        lanes = data.get("lanes")
        if lanes:
            if isinstance(lanes, list):
                lanes = lanes[0]
            try:
                lanes = int(float(str(lanes)))
            except (ValueError, TypeError):
                lanes = DEFAULT_LANES_BY_TYPE.get(highway, 1)
        else:
            lanes = DEFAULT_LANES_BY_TYPE.get(highway, 1)

        length = data.get("length", 500.0)
        if isinstance(length, list):
            length = length[0]
        try:
            length = float(length)
        except (ValueError, TypeError):
            length = 500.0

        simple.add_edge(u, v, length=length, speed_kph=speed_kph,
                        lanes=lanes, highway=highway)

    logger.info("Simple DiGraph: %d nodes, %d edges", simple.number_of_nodes(), simple.number_of_edges())

    # Strongly connected component
    sccs = list(nx.strongly_connected_components(simple))
    sccs.sort(key=len, reverse=True)
    largest = sccs[0]
    logger.info("Largest SCC: %d nodes (of %d, %d components)",
                len(largest), simple.number_of_nodes(), len(sccs))
    return simple.subgraph(largest).copy()


def main():
    parser = argparse.ArgumentParser(
        description="Run MATSim on full connected Japan-wide network"
    )
    parser.add_argument("--agents", type=int, default=10000)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--sample-rate", type=float, default=0.1)
    parser.add_argument("--jvm-memory", default="8g")
    parser.add_argument("--java-path", default="/opt/homebrew/opt/openjdk@21/bin/java")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-simulation", action="store_true")
    parser.add_argument("--skip-okinawa", action="store_true", default=True,
                        help="Skip Okinawa (isolated from mainland)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")

    output_dir = args.output_dir or Path("data/output/matsim_fullnetwork")
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache"

    # --- Phase 1-2: Fetch and merge networks ---
    logger.info("=== Phase 1-2: Fetch and merge 9-region network ===")

    merged_cache = cache_dir / "merged_graph.pkl"
    if merged_cache.exists():
        logger.info("Loading cached merged graph")
        with open(merged_cache, "rb") as f:
            graph = pickle.load(f)
    else:
        graphs = []
        regions = {k: v for k, v in REGIONS.items()
                   if not (args.skip_okinawa and k == "okinawa")}

        for name, bbox in regions.items():
            G = fetch_region_graph(name, bbox, cache_dir)
            if G is not None:
                graphs.append(G)
            else:
                logger.warning("Skipping %s: failed to fetch", name)

        logger.info("Merging %d regional graphs...", len(graphs))
        graph = merge_graphs(graphs)

        with open(merged_cache, "wb") as f:
            pickle.dump(graph, f)
        logger.info("Cached merged graph")

    logger.info("Full network: %d nodes, %d edges", graph.number_of_nodes(), graph.number_of_edges())

    # --- Phase 3: Convert to MATSim network.xml ---
    logger.info("=== Phase 3: Convert to MATSim network.xml ===")
    network_path = output_dir / "network.xml"
    convert_to_matsim_network(graph, network_path)

    # --- Phase 4: Generate population ---
    logger.info("=== Phase 4: Generate population (%d agents) ===", args.agents)
    plans_path = output_dir / "plans.xml"
    generate_population(graph, plans_path, region="japan", total_agents=args.agents)

    # --- Phase 5: Generate config ---
    logger.info("=== Phase 5: Generate config ===")
    config_path = generate_config(
        network_path=network_path,
        plans_path=plans_path,
        output_dir=output_dir,
        iterations=args.iterations,
        sample_rate=args.sample_rate,
    )

    # --- Phase 6: Run MATSim ---
    if not args.skip_simulation:
        logger.info("=== Phase 6: Run MATSim ===")
        matsim_output = run_matsim(
            config_path=config_path,
            java_path=args.java_path,
            jvm_memory=args.jvm_memory,
        )

        events_file = find_events_file(matsim_output)
        if events_file:
            logger.info("=== Phase 7: Parse events for visualization ===")
            viz_dir = output_dir / "viz"
            viz_results = parse_events_to_trajectories(
                events_path=events_file,
                network_path=network_path,
                output_dir=viz_dir,
                max_agents=8000,
            )

            # Copy to web/data for viewing
            web_data = Path("web/data")
            web_data.mkdir(parents=True, exist_ok=True)
            import shutil
            for key, path in viz_results.items():
                dest = web_data / Path(path).name
                shutil.copy2(path, dest)
                logger.info("Copied %s → %s", path, dest)

            # Generate Leaflet animation
            logger.info("=== Phase 8: Generate animated map ===")
            from visualize.japan_matsim_animated import build_animated_html
            with open(viz_results["trajectories"]) as f:
                trajs = json.load(f)
            with open(viz_results["link_counts"]) as f:
                lc = json.load(f)
            with open(viz_results["network_geojson"]) as f:
                net = json.load(f)

            build_animated_html(
                trajs, lc, net,
                Path("visualize/output/japan_matsim_fullnetwork.html"),
                title="MATSim Japan — Full Connected Network",
            )

    print("\n" + "=" * 60)
    print("Full-Network MATSim Pipeline Complete")
    print("=" * 60)
    print(f"  Network: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"  Agents: {args.agents}")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()
