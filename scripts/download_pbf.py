#!/usr/bin/env python
"""CLI script to download Geofabrik PBF extracts for Japan regions.

Usage::

    python scripts/download_pbf.py --region kanto
    python scripts/download_pbf.py --region japan --force
    python scripts/download_pbf.py --region hokkaido --output-dir /tmp/pbf
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.config import GEOFABRIK_REGIONS, RAW_DIR
from src.data.downloader import download_pbf


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the download CLI."""
    parser = argparse.ArgumentParser(
        description="Download Geofabrik PBF extracts for Japan regions.",
    )
    parser.add_argument(
        "--region",
        default="kanto",
        choices=sorted(GEOFABRIK_REGIONS.keys()),
        help="Region to download (default: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file is already cached",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Output directory for downloaded PBF (default: {RAW_DIR})",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the download_pbf CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result_path = download_pbf(region=args.region, force=args.force)

    # If a custom output directory was specified, move the file there
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        dest = args.output_dir / result_path.name
        if dest != result_path:
            import shutil

            shutil.copy2(result_path, dest)
            result_path = dest

    print(result_path)


if __name__ == "__main__":
    main()
