#!/usr/bin/env python
"""CLI script to run the full Japan traffic simulation pipeline.

Orchestrates the complete workflow from PBF download through simulation
execution and result serialization.

Usage::

    python scripts/run_simulation.py
    python scripts/run_simulation.py --region kanto --deltan 10 --tmax 7200
    python scripts/run_simulation.py --skip-download --output data/output
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from src.config import DEFAULT_DELTAN, DEFAULT_TMAX, GEOFABRIK_REGIONS, OUTPUT_DIR
from src.data.cache import get_cache_path
from src.data.downloader import download_pbf
from src.data.parser import parse_road_network
from src.network.builder import build_graph
from src.network.simplify import simplify_network
from src.simulation.demand import generate_default_demands
from src.simulation.runner import run_simulation, save_results
from src.simulation.world import create_world

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the simulation CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the full Japan traffic simulation pipeline: "
            "download PBF → parse → filter → build graph → simplify → "
            "create World → add demand → run simulation → save results."
        ),
    )
    parser.add_argument(
        "--region",
        default="kanto",
        choices=sorted(GEOFABRIK_REGIONS.keys()),
        help="Geofabrik region to simulate (default: %(default)s)",
    )
    parser.add_argument(
        "--deltan",
        type=int,
        default=DEFAULT_DELTAN,
        help="UXsim platoon size parameter (default: %(default)s)",
    )
    parser.add_argument(
        "--tmax",
        type=int,
        default=DEFAULT_TMAX,
        help="Maximum simulation duration in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for simulation results (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip PBF download; assume the file already exists in cache",
    )
    return parser


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


def _print_stage(stage_num: int, description: str) -> float:
    """Print a progress header and return the current timestamp.

    Parameters
    ----------
    stage_num:
        Stage number for display.
    description:
        Short description of the pipeline stage.

    Returns
    -------
    float
        :func:`time.perf_counter` value for elapsed-time calculation.
    """
    print(f"\n{'='*60}")
    print(f"  Stage {stage_num}: {description}")
    print(f"{'='*60}")
    return time.perf_counter()


def _print_elapsed(t_start: float) -> None:
    """Print elapsed time since *t_start*."""
    elapsed = time.perf_counter() - t_start
    print(f"  ✓ Done in {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Entry point for the run_simulation CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    t_pipeline_start = time.perf_counter()

    print(f"Japan Traffic Simulation Pipeline")
    print(f"Region: {args.region} | deltan: {args.deltan} | tmax: {args.tmax}")

    # ------------------------------------------------------------------
    # Stage 1: Download PBF
    # ------------------------------------------------------------------
    t0 = _print_stage(1, "Download PBF")

    if args.skip_download:
        pbf_path = get_cache_path(args.region, ".osm.pbf")
        if not pbf_path.is_file():
            print(f"  ERROR: PBF file not found: {pbf_path}", file=sys.stderr)
            sys.exit(1)
        print(f"  Skipping download (using cached: {pbf_path})")
    else:
        pbf_path = download_pbf(region=args.region)
        print(f"  PBF path: {pbf_path}")

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 2: Parse road network
    # ------------------------------------------------------------------
    t0 = _print_stage(2, "Parse road network")

    nodes, edges = parse_road_network(pbf_path, include_nodes=True)
    print(f"  Nodes: {len(nodes):,} | Edges: {len(edges):,}")

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 3: Build graph
    # ------------------------------------------------------------------
    t0 = _print_stage(3, "Build NetworkX graph")

    graph = build_graph(nodes, edges)
    print(
        f"  Graph: {graph.number_of_nodes():,} nodes, "
        f"{graph.number_of_edges():,} edges"
    )

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 4: Simplify network
    # ------------------------------------------------------------------
    t0 = _print_stage(4, "Simplify network")

    graph = simplify_network(graph)
    print(
        f"  Simplified: {graph.number_of_nodes():,} nodes, "
        f"{graph.number_of_edges():,} edges"
    )

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 5: Create UXsim World
    # ------------------------------------------------------------------
    t0 = _print_stage(5, "Create UXsim World")

    W = create_world(
        graph,
        deltan=args.deltan,
        tmax=args.tmax,
        name=f"{args.region}_traffic",
    )
    print(f"  World '{W.name}' created")

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 6: Add demand
    # ------------------------------------------------------------------
    t0 = _print_stage(6, "Add traffic demand")

    # Map regions to their demand generation identifier.
    # Currently only "tokyo" OD pairs are available; Kanto is the
    # default region and covers the Tokyo metropolitan area.
    demand_region = "tokyo"
    try:
        generate_default_demands(W, region=demand_region)
        print(f"  Demand added for region '{demand_region}'")
    except ValueError:
        logger.warning(
            "No predefined demand for region '%s'; "
            "falling back to 'tokyo' OD pairs",
            demand_region,
        )
        generate_default_demands(W, region="tokyo")
        print(f"  Demand added (fallback: 'tokyo')")

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 7: Run simulation
    # ------------------------------------------------------------------
    t0 = _print_stage(7, "Run simulation")

    W = run_simulation(W)

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Stage 8: Save results
    # ------------------------------------------------------------------
    t0 = _print_stage(8, "Save results")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{W.name}_results.pkl"

    saved_path = save_results(W, output_path=result_path)
    print(f"  Results saved to: {saved_path}")

    _print_elapsed(t0)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_elapsed = time.perf_counter() - t_pipeline_start
    print(f"\n{'='*60}")
    print(f"  Pipeline complete in {total_elapsed:.1f}s")
    print(f"  Results: {saved_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
