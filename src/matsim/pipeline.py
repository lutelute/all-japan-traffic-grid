"""End-to-end MATSim simulation pipeline.

Orchestrates the full workflow from OSM data through MATSim execution
to visualization data generation. Uses osmnx for network extraction
(no pyrosm dependency required).
"""

import logging
import pickle
from pathlib import Path

import networkx as nx

from src.config import HIGHWAY_FILTER, OUTPUT_DIR

logger = logging.getLogger(__name__)

# Bounding boxes for Japanese regions [south, west, north, east]
REGION_BBOX: dict[str, tuple[float, float, float, float]] = {
    "kanto":    (35.2, 138.9, 36.3, 140.5),
    "tokyo":    (35.5, 139.4, 35.9, 139.95),
    "kansai":   (34.2, 134.8, 35.4, 136.2),
    "chubu":    (34.5, 136.0, 37.5, 139.5),
    "hokkaido": (41.3, 139.3, 45.6, 145.8),
    "tohoku":   (36.8, 139.0, 41.5, 142.1),
    "chugoku":  (33.7, 130.8, 35.7, 134.3),
    "shikoku":  (32.7, 132.0, 34.5, 134.8),
    "kyushu":   (30.9, 129.4, 34.3, 132.1),
}


def _get_osmnx_graph(region: str, cache_dir: Path) -> nx.MultiDiGraph:
    """Fetch road network via osmnx with caching."""
    import osmnx as ox

    cache_file = cache_dir / f"osmnx_{region}.pkl"
    if cache_file.exists():
        logger.info("Loading cached osmnx graph: %s", cache_file)
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    bbox = REGION_BBOX.get(region)
    if bbox is None:
        raise ValueError(f"Unknown region '{region}'. Available: {list(REGION_BBOX.keys())}")

    south, west, north, east = bbox
    logger.info("Fetching OSM network for %s via osmnx (bbox: %.1f,%.1f,%.1f,%.1f)...",
                region, south, west, north, east)

    # Use custom filter for highway types
    cf = f'["highway"~"{"|".join(HIGHWAY_FILTER)}"]'
    G = ox.graph_from_bbox(
        bbox=(west, south, east, north),
        network_type="drive",
        custom_filter=cf,
    )

    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(G, f)
    logger.info("Cached osmnx graph: %d nodes, %d edges → %s",
                G.number_of_nodes(), G.number_of_edges(), cache_file)
    return G


def _osmnx_to_simple_digraph(G_multi: nx.MultiDiGraph) -> nx.DiGraph:
    """Convert osmnx MultiDiGraph to simple DiGraph with standard attributes."""
    from src.config import DEFAULT_LANES_BY_TYPE, DEFAULT_SPEED_BY_TYPE

    G = nx.DiGraph()

    # Add nodes
    for node_id, data in G_multi.nodes(data=True):
        G.add_node(node_id, x=data.get("x", 0.0), y=data.get("y", 0.0))

    # Add edges (take first edge for multi-edges)
    for u, v, data in G_multi.edges(data=True):
        if G.has_edge(u, v):
            continue
        if u == v:
            continue

        highway = data.get("highway", "secondary")
        if isinstance(highway, list):
            highway = highway[0]

        # Speed
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

        # Lanes
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

        # Length
        length = data.get("length", 500.0)
        if isinstance(length, list):
            length = length[0]
        try:
            length = float(length)
        except (ValueError, TypeError):
            length = 500.0

        G.add_edge(u, v,
                   length=length,
                   speed_kph=speed_kph,
                   lanes=lanes,
                   highway=highway)

    logger.info("Converted to DiGraph: %d nodes, %d edges",
                G.number_of_nodes(), G.number_of_edges())
    return G


def _extract_signals_osmnx(region: str) -> list[dict]:
    """Extract traffic signal nodes via osmnx."""
    import osmnx as ox

    bbox = REGION_BBOX.get(region)
    if bbox is None:
        return []

    south, west, north, east = bbox
    logger.info("Extracting traffic signals for %s via osmnx...", region)

    try:
        signals_gdf = ox.features_from_bbox(
            bbox=(west, south, east, north),
            tags={"highway": "traffic_signals"},
        )
        # Filter to points only
        signals_gdf = signals_gdf[signals_gdf.geometry.geom_type == "Point"]
        logger.info("Found %d traffic signal nodes", len(signals_gdf))

        result = []
        for idx, row in signals_gdf.iterrows():
            result.append({
                "lon": row.geometry.x,
                "lat": row.geometry.y,
                "osm_id": str(idx),
            })
        return result
    except Exception as e:
        logger.warning("Failed to extract signals: %s", e)
        return []


def _match_signals_to_graph(signal_points: list[dict], graph: nx.DiGraph,
                            threshold_deg: float = 0.001) -> list[dict]:
    """Match signal points to nearest graph nodes."""
    import math

    graph_nodes = {}
    for node_id, attrs in graph.nodes(data=True):
        if "x" in attrs and "y" in attrs:
            graph_nodes[str(node_id)] = (attrs["x"], attrs["y"])

    matched = []
    seen = set()
    for sig in signal_points:
        best_dist = float("inf")
        best_node = None
        for nid, (nx_, ny_) in graph_nodes.items():
            dist = math.sqrt((sig["lon"] - nx_) ** 2 + (sig["lat"] - ny_) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_node = nid

        if best_node is not None and best_dist <= threshold_deg and best_node not in seen:
            seen.add(best_node)
            matched.append({
                "node_id": best_node,
                "lon": sig["lon"],
                "lat": sig["lat"],
                "osm_id": sig["osm_id"],
            })

    logger.info("Matched %d signals to graph nodes", len(matched))
    return matched


def run_matsim_pipeline(
    region: str = "kanto",
    total_agents: int = 10000,
    iterations: int = 10,
    with_signals: bool = True,
    output_dir: Path | None = None,
    sample_rate: float = 0.1,
    jvm_memory: str = "8g",
    skip_simulation: bool = False,
    java_path: str | None = None,
) -> dict[str, Path]:
    """Run the full MATSim pipeline.

    Parameters
    ----------
    region:
        Geographic region.
    total_agents:
        Number of synthetic agents.
    iterations:
        Number of MATSim iterations.
    with_signals:
        Whether to include traffic signals.
    output_dir:
        Base output directory.
    sample_rate:
        MATSim flow/storage capacity factor.
    jvm_memory:
        JVM heap size.
    skip_simulation:
        If True, only generate input files.
    java_path:
        Path to java executable. Auto-detected if None.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / f"matsim_{region}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = output_dir / "cache"
    results: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Step 1-3: Fetch & build network via osmnx
    # ------------------------------------------------------------------
    logger.info("=== Step 1/6: Fetch road network for '%s' via osmnx ===", region)
    G_multi = _get_osmnx_graph(region, cache_dir)
    graph = _osmnx_to_simple_digraph(G_multi)

    # Extract largest strongly connected component (MATSim requires full reachability)
    logger.info("Extracting largest strongly connected component...")
    sccs = list(nx.strongly_connected_components(graph))
    sccs.sort(key=len, reverse=True)
    largest_scc = sccs[0]
    logger.info("Largest SCC: %d nodes (of %d total, %d components)",
                len(largest_scc), graph.number_of_nodes(), len(sccs))
    graph = graph.subgraph(largest_scc).copy()

    results["graph_nodes"] = graph.number_of_nodes()
    results["graph_edges"] = graph.number_of_edges()

    # ------------------------------------------------------------------
    # Step 2: Convert to MATSim network.xml
    # ------------------------------------------------------------------
    logger.info("=== Step 2/6: Convert to MATSim network.xml ===")
    from src.matsim.network_converter import convert_to_matsim_network
    network_path = output_dir / "network.xml"
    convert_to_matsim_network(graph, network_path)
    results["network"] = network_path

    # ------------------------------------------------------------------
    # Step 3: Extract signals (optional)
    # ------------------------------------------------------------------
    signal_paths = None
    if with_signals:
        logger.info("=== Step 3/6: Extract traffic signals ===")
        signal_points = _extract_signals_osmnx(region)
        if signal_points:
            matched = _match_signals_to_graph(signal_points, graph)
            if matched:
                from src.matsim.signal_extractor import generate_signal_xmls
                signal_paths = generate_signal_xmls(
                    matched, graph, output_dir / "signals"
                )
                results["signals"] = signal_paths[0].parent
            else:
                logger.warning("No signals matched to graph nodes")
        else:
            logger.warning("No signals found")
    else:
        logger.info("=== Step 3/6: Skipping signals ===")

    # ------------------------------------------------------------------
    # Step 4: Generate population
    # ------------------------------------------------------------------
    logger.info("=== Step 4/6: Generate synthetic population (%d agents) ===", total_agents)
    from src.matsim.population import generate_population
    plans_path = output_dir / "plans.xml"
    generate_population(graph, plans_path, region=region, total_agents=total_agents)
    results["plans"] = plans_path

    # ------------------------------------------------------------------
    # Step 5: Generate config
    # ------------------------------------------------------------------
    logger.info("=== Step 5/6: Generate MATSim config ===")
    from src.matsim.config_generator import generate_config
    config_path = generate_config(
        network_path=network_path,
        plans_path=plans_path,
        output_dir=output_dir,
        signal_paths=signal_paths,
        iterations=iterations,
        sample_rate=sample_rate,
    )
    results["config"] = config_path

    # ------------------------------------------------------------------
    # Step 6: Run MATSim
    # ------------------------------------------------------------------
    if not skip_simulation:
        logger.info("=== Step 6/6: Run MATSim simulation ===")
        from src.matsim.runner import find_events_file, run_matsim

        _java = java_path or "/opt/homebrew/opt/openjdk@21/bin/java"

        matsim_output = run_matsim(
            config_path=config_path,
            java_path=_java,
            jvm_memory=jvm_memory,
        )
        results["matsim_output"] = matsim_output

        events_file = find_events_file(matsim_output)
        if events_file:
            from src.matsim.event_parser import parse_events_to_trajectories
            viz_dir = output_dir / "viz"
            viz_results = parse_events_to_trajectories(
                events_path=events_file,
                network_path=network_path,
                output_dir=viz_dir,
            )
            results.update(viz_results)
    else:
        logger.info("=== Step 6/6: Skipping simulation ===")

    logger.info("Pipeline complete. Results: %s", {k: str(v) for k, v in results.items()})
    return results
