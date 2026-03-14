#!/usr/bin/env python3
"""CLI script to run the MATSim simulation pipeline.

Usage:
    python scripts/run_matsim.py --region kanto --agents 10000 --iterations 10
    python scripts/run_matsim.py --region kanto --agents 5000 --skip-simulation  # Generate inputs only
    python scripts/run_matsim.py --region kansai --agents 20000 --with-signals
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.matsim.pipeline import run_matsim_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run MATSim simulation for Japanese traffic network"
    )
    parser.add_argument(
        "--region",
        default="kanto",
        choices=["hokkaido", "tohoku", "kanto", "chubu", "kansai",
                 "chugoku", "shikoku", "kyushu", "okinawa"],
        help="Geographic region (default: kanto)",
    )
    parser.add_argument(
        "--agents",
        type=int,
        default=10000,
        help="Number of synthetic agents (default: 10000)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of MATSim iterations (default: 10)",
    )
    parser.add_argument(
        "--with-signals",
        action="store_true",
        default=True,
        help="Include traffic signals (default: True)",
    )
    parser.add_argument(
        "--no-signals",
        action="store_true",
        help="Disable traffic signals",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=0.1,
        help="MATSim flow/storage capacity factor (default: 0.1)",
    )
    parser.add_argument(
        "--jvm-memory",
        default="8g",
        help="JVM heap size (default: 8g)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: data/output/matsim_{region})",
    )
    parser.add_argument(
        "--skip-simulation",
        action="store_true",
        help="Generate inputs only, skip MATSim execution",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    with_signals = args.with_signals and not args.no_signals

    results = run_matsim_pipeline(
        region=args.region,
        total_agents=args.agents,
        iterations=args.iterations,
        with_signals=with_signals,
        output_dir=args.output_dir,
        sample_rate=args.sample_rate,
        jvm_memory=args.jvm_memory,
        skip_simulation=args.skip_simulation,
    )

    print("\n" + "=" * 60)
    print("MATSim Pipeline Complete")
    print("=" * 60)
    for key, value in results.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
