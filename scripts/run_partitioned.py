#!/usr/bin/env python3
"""Run partitioned MATSim simulation across multiple sub-areas.

Usage:
    python scripts/run_partitioned.py --preset kanto --iterations 3
    python scripts/run_partitioned.py --preset kanto --agents-multiplier 2
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.matsim.partitioned import (
    KANTO_PARTITIONS,
    JAPAN_PARTITIONS,
    run_partitioned_pipeline,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run partitioned MATSim simulation for Japan"
    )
    parser.add_argument(
        "--preset",
        default="kanto",
        choices=["kanto", "japan"],
        help="Partition preset (default: kanto)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="MATSim iterations per area (default: 3)",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=0.1,
        help="Capacity factor (default: 0.1)",
    )
    parser.add_argument(
        "--jvm-memory",
        default="4g",
        help="JVM heap per area (default: 4g)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help="Max concurrent simulations (default: 2)",
    )
    parser.add_argument(
        "--agents-multiplier",
        type=float,
        default=1.0,
        help="Multiply default agent counts (default: 1.0)",
    )
    parser.add_argument(
        "--single-pass",
        action="store_true",
        help="Skip two-pass boundary exchange",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Get partitions and apply multiplier
    if args.preset == "kanto":
        partitions = KANTO_PARTITIONS
    else:
        partitions = JAPAN_PARTITIONS

    if args.agents_multiplier != 1.0:
        for p in partitions:
            p.agents = int(p.agents * args.agents_multiplier)

    results = run_partitioned_pipeline(
        partitions=partitions,
        iterations=args.iterations,
        sample_rate=args.sample_rate,
        jvm_memory=args.jvm_memory,
        max_workers=args.max_workers,
        output_dir=args.output_dir,
        two_pass=not args.single_pass,
    )

    print("\n" + "=" * 60)
    print("Partitioned Pipeline Complete")
    print("=" * 60)
    total_agents = sum(p.agents for p in partitions)
    print(f"  Areas: {len(partitions)}")
    print(f"  Total agents: {total_agents:,}")
    for key, value in results.items():
        print(f"  {key}: {value}")
    print(f"\nCopy viz data: cp {results.get('trajectories', '').parent}/* web/data/")


if __name__ == "__main__":
    main()
