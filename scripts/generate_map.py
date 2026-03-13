#!/usr/bin/env python
"""CLI script to generate congestion maps from simulation results.

Loads serialized simulation results (pickle), extracts per-link
congestion data, and produces one or more output formats: GeoJSON,
interactive HTML (Folium), and/or static PNG (Matplotlib).

Usage::

    python scripts/generate_map.py --input data/output/kanto_traffic_results.pkl
    python scripts/generate_map.py --input data/output/kanto_traffic_results.pkl --format geojson
    python scripts/generate_map.py --input data/output/kanto_traffic_results.pkl --format html --output-dir data/output
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.config import OUTPUT_DIR
from src.simulation.runner import load_results
from src.visualization.congestion_map import create_interactive_map, create_static_map
from src.visualization.export import extract_link_congestion, to_geodataframe, to_geojson

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the generate_map CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate congestion maps from simulation results. "
            "Supports GeoJSON, interactive HTML, and static PNG outputs."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to simulation results pickle file",
    )
    parser.add_argument(
        "--format",
        choices=["geojson", "html", "png", "all"],
        default="all",
        help="Output format to generate (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for generated files (default: %(default)s)",
    )
    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Entry point for the generate_map CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ------------------------------------------------------------------
    # Validate input file
    # ------------------------------------------------------------------
    input_path: Path = args.input
    if not input_path.is_file():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load simulation results
    # ------------------------------------------------------------------
    W = load_results(input_path)

    # ------------------------------------------------------------------
    # Extract congestion data
    # ------------------------------------------------------------------
    congestion_data = extract_link_congestion(W)
    if not congestion_data:
        print("ERROR: No congestion data extracted from results", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Determine output formats
    # ------------------------------------------------------------------
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Derive a base name from the input file (strip _results.pkl suffix)
    stem = input_path.stem
    if stem.endswith("_results"):
        stem = stem[: -len("_results")]

    fmt = args.format
    generate_geojson = fmt in ("geojson", "all")
    generate_html = fmt in ("html", "all")
    generate_png = fmt in ("png", "all")

    generated_files: list[Path] = []

    # ------------------------------------------------------------------
    # Generate GeoJSON
    # ------------------------------------------------------------------
    if generate_geojson:
        geojson_path = output_dir / f"{stem}.geojson"
        result = to_geojson(congestion_data, geojson_path)
        generated_files.append(result)

    # ------------------------------------------------------------------
    # Generate interactive HTML and/or static PNG
    # ------------------------------------------------------------------
    if generate_html or generate_png:
        gdf = to_geodataframe(congestion_data)

        if generate_html:
            html_path = output_dir / f"{stem}_map.html"
            result = create_interactive_map(gdf, html_path)
            generated_files.append(result)

        if generate_png:
            png_path = output_dir / f"{stem}_map.png"
            result = create_static_map(gdf, png_path)
            generated_files.append(result)

    # ------------------------------------------------------------------
    # Print generated file paths
    # ------------------------------------------------------------------
    for path in generated_files:
        print(path)


if __name__ == "__main__":
    main()
