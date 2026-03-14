"""End-to-end MATSim simulation pipeline.

Orchestrates the full workflow from OSM data download through MATSim
execution to visualization data generation, reusing the existing
OSM/NetworkX pipeline from src.data and src.network.
"""

import logging
from pathlib import Path

import networkx as nx

from src.config import OUTPUT_DIR, RAW_DIR

logger = logging.getLogger(__name__)


def run_matsim_pipeline(
    region: str = "kanto",
    total_agents: int = 10000,
    iterations: int = 10,
    with_signals: bool = True,
    output_dir: Path | None = None,
    sample_rate: float = 0.1,
    jvm_memory: str = "8g",
    skip_simulation: bool = False,
) -> dict[str, Path]:
    """Run the full MATSim pipeline: OSM → Network → Signals → Plans → Simulate → Viz.

    Parameters
    ----------
    region:
        Geographic region (must be in GEOFABRIK_REGIONS config).
    total_agents:
        Number of synthetic agents to generate.
    iterations:
        Number of MATSim iterations.
    with_signals:
        Whether to extract and use traffic signals.
    output_dir:
        Base output directory. Defaults to data/output/matsim_{region}.
    sample_rate:
        MATSim flow/storage capacity factor.
    jvm_memory:
        JVM heap size for MATSim.
    skip_simulation:
        If True, skip the actual MATSim run (useful for testing input generation).

    Returns
    -------
    dict[str, Path]
        Mapping of output type to file path.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / f"matsim_{region}"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Step 1: Download PBF (reuse existing pipeline)
    # ------------------------------------------------------------------
    logger.info("=== Step 1/8: Download PBF for region '%s' ===", region)
    from src.data.downloader import download_pbf
    pbf_path = download_pbf(region, output_dir=RAW_DIR)
    results["pbf"] = pbf_path

    # ------------------------------------------------------------------
    # Step 2: Parse road network (reuse existing pipeline)
    # ------------------------------------------------------------------
    logger.info("=== Step 2/8: Parse road network ===")
    from src.data.parser import parse_road_network
    nodes_gdf, edges_gdf = parse_road_network(pbf_path, include_nodes=True)

    # ------------------------------------------------------------------
    # Step 3: Build NetworkX graph (reuse existing pipeline)
    # ------------------------------------------------------------------
    logger.info("=== Step 3/8: Build NetworkX graph ===")
    from src.network.builder import build_graph
    graph = build_graph(nodes_gdf, edges_gdf)

    # ------------------------------------------------------------------
    # Step 4: Simplify network (reuse existing pipeline)
    # ------------------------------------------------------------------
    logger.info("=== Step 4/8: Simplify network ===")
    from src.network.simplify import simplify_graph
    graph = simplify_graph(graph)
    results["graph_nodes"] = graph.number_of_nodes()
    results["graph_edges"] = graph.number_of_edges()

    # ------------------------------------------------------------------
    # Step 5: Convert to MATSim network.xml
    # ------------------------------------------------------------------
    logger.info("=== Step 5/8: Convert to MATSim network.xml ===")
    from src.matsim.network_converter import convert_to_matsim_network
    network_path = output_dir / "network.xml"
    convert_to_matsim_network(graph, network_path)
    results["network"] = network_path

    # ------------------------------------------------------------------
    # Step 6: Extract signals (optional)
    # ------------------------------------------------------------------
    signal_paths = None
    if with_signals:
        logger.info("=== Step 6/8: Extract traffic signals ===")
        from src.matsim.signal_extractor import (
            extract_signals_from_osm,
            generate_signal_xmls,
        )
        signal_nodes = extract_signals_from_osm(pbf_path, graph)
        if signal_nodes:
            signal_paths = generate_signal_xmls(
                signal_nodes, graph, output_dir / "signals"
            )
            results["signals"] = signal_paths[0].parent
        else:
            logger.warning("No signals found, proceeding without signal systems")
    else:
        logger.info("=== Step 6/8: Skipping signals (disabled) ===")

    # ------------------------------------------------------------------
    # Step 7: Generate population
    # ------------------------------------------------------------------
    logger.info("=== Step 7/8: Generate synthetic population (%d agents) ===", total_agents)
    from src.matsim.population import generate_population
    plans_path = output_dir / "plans.xml"
    generate_population(graph, plans_path, region=region, total_agents=total_agents)
    results["plans"] = plans_path

    # ------------------------------------------------------------------
    # Step 8: Generate config and run MATSim
    # ------------------------------------------------------------------
    logger.info("=== Step 8/8: Generate config and run simulation ===")
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

    if not skip_simulation:
        from src.matsim.java_manager import check_java
        from src.matsim.runner import find_events_file, run_matsim

        check_java()
        matsim_output = run_matsim(
            config_path=config_path,
            jvm_memory=jvm_memory,
        )
        results["matsim_output"] = matsim_output

        # Parse events for visualization
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
        logger.info("Skipping MATSim simulation (skip_simulation=True)")

    logger.info("Pipeline complete. Results: %s", {k: str(v) for k, v in results.items()})
    return results
