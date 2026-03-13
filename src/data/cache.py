"""Local file caching utilities for downloaded and processed data.

Provides file-existence-based caching with optional MD5 checksum verification
to avoid redundant downloads and reprocessing of OSM data.
"""

import hashlib
from pathlib import Path

from src.config import PROCESSED_DIR, RAW_DIR

# ---------------------------------------------------------------------------
# Cache path helpers
# ---------------------------------------------------------------------------


def get_cache_path(region: str, suffix: str) -> Path:
    """Return the expected cache file path for a given region and suffix.

    Raw data files (e.g. ``.osm.pbf``) are stored under ``RAW_DIR``;
    all other suffixes are treated as processed artefacts and go under
    ``PROCESSED_DIR``.

    Parameters
    ----------
    region:
        Region identifier (e.g. ``"kanto"``, ``"japan"``).
    suffix:
        File extension **including** the leading dot (e.g. ``".osm.pbf"``,
        ``".parquet"``).

    Returns
    -------
    Path
        Absolute path where the cached file should reside.
    """
    if suffix == ".osm.pbf":
        return RAW_DIR / f"{region}-latest{suffix}"
    return PROCESSED_DIR / f"{region}{suffix}"


def is_cached(path: Path) -> bool:
    """Check whether a cached file exists and is non-empty.

    Parameters
    ----------
    path:
        Path to the file to check.

    Returns
    -------
    bool
        ``True`` if *path* exists, is a regular file, and has size > 0.
    """
    return path.is_file() and path.stat().st_size > 0


def validate_checksum(path: Path, expected_md5: str) -> bool:
    """Verify the MD5 checksum of a file against an expected value.

    Parameters
    ----------
    path:
        Path to the file to check.
    expected_md5:
        Hexadecimal MD5 digest string to compare against.

    Returns
    -------
    bool
        ``True`` if the file exists and its MD5 matches *expected_md5*.
    """
    if not path.is_file():
        return False

    md5 = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            md5.update(chunk)

    return md5.hexdigest() == expected_md5.lower().strip()


def ensure_directory(path: Path) -> None:
    """Create a directory (and parents) if it does not already exist.

    If *path* points to a file, the **parent** directory is created instead.

    Parameters
    ----------
    path:
        Directory path to ensure exists, or a file path whose parent
        directory should exist.
    """
    target = path if path.suffix == "" else path.parent
    target.mkdir(parents=True, exist_ok=True)
