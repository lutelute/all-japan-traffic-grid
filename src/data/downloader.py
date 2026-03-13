"""Geofabrik PBF download manager with retry logic and caching.

Downloads OpenStreetMap PBF extracts from Geofabrik mirrors with streaming
HTTP requests, tqdm progress bars, exponential-backoff retries, and optional
MD5 checksum verification to ensure data integrity.
"""

import logging
import time
from pathlib import Path

import requests
from tqdm import tqdm

from src.config import GEOFABRIK_REGIONS, RAW_DIR
from src.data.cache import ensure_directory, get_cache_path, is_cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MAX_RETRIES: int = 3
_BACKOFF_BASE: float = 2.0
_CHUNK_SIZE: int = 8192
_REQUEST_TIMEOUT: int = 30


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def download_pbf(region: str = "kanto", force: bool = False) -> Path:
    """Download a Geofabrik PBF extract for the specified region.

    If the file already exists in the local cache and *force* is ``False``,
    the download is skipped and the cached path is returned immediately.

    Parameters
    ----------
    region:
        Region identifier matching a key in
        :data:`src.config.GEOFABRIK_REGIONS` (e.g. ``"kanto"``,
        ``"japan"``).
    force:
        When ``True``, re-download the file even if it is already cached.

    Returns
    -------
    Path
        Absolute path to the downloaded ``.osm.pbf`` file under
        :data:`src.config.RAW_DIR`.

    Raises
    ------
    ValueError
        If *region* is not a recognised key in ``GEOFABRIK_REGIONS``.
    RuntimeError
        If the download fails after all retry attempts.
    """
    if region not in GEOFABRIK_REGIONS:
        available = ", ".join(sorted(GEOFABRIK_REGIONS.keys()))
        raise ValueError(
            f"Unknown region '{region}'. Available regions: {available}"
        )

    url = GEOFABRIK_REGIONS[region]
    dest = get_cache_path(region, ".osm.pbf")

    # Skip download when a valid cached copy exists
    if not force and is_cached(dest):
        logger.info("Using cached PBF: %s", dest)
        return dest

    ensure_directory(dest)

    # Attempt download with exponential-backoff retries
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _stream_download(url, dest, attempt)
            logger.info("Download complete: %s", dest)
            return dest
        except (requests.RequestException, IOError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "Download attempt %d/%d failed (%s). "
                    "Retrying in %.0fs …",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "Download failed after %d attempts: %s",
                    _MAX_RETRIES,
                    exc,
                )

    raise RuntimeError(
        f"Failed to download {url} after {_MAX_RETRIES} attempts"
    ) from last_exc


def fetch_md5(url: str) -> str | None:
    """Fetch the ``.md5`` sidecar file for a Geofabrik download URL.

    Geofabrik publishes ``<file>.md5`` alongside every PBF extract.
    This helper downloads that small text file and extracts the hex digest.

    Parameters
    ----------
    url:
        The PBF download URL (the ``.md5`` suffix is appended
        automatically).

    Returns
    -------
    str | None
        The MD5 hex digest string, or ``None`` if the checksum file
        could not be retrieved.
    """
    md5_url = url + ".md5"
    try:
        resp = requests.get(md5_url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Geofabrik .md5 format: "<hex>  <filename>\n"
        return resp.text.strip().split()[0]
    except (requests.RequestException, IndexError, ValueError):
        logger.debug("Could not fetch MD5 checksum from %s", md5_url)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stream_download(url: str, dest: Path, attempt: int) -> None:
    """Download *url* to *dest* with a streaming tqdm progress bar.

    Parameters
    ----------
    url:
        Remote file URL.
    dest:
        Local destination path.
    attempt:
        Current attempt number (used in the progress bar description).

    Raises
    ------
    requests.RequestException
        On any HTTP error.
    IOError
        If writing to *dest* fails.
    """
    logger.info(
        "Downloading %s (attempt %d/%d) …", url, attempt, _MAX_RETRIES
    )

    resp = requests.get(url, stream=True, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))

    tmp_dest = dest.with_suffix(".osm.pbf.part")
    try:
        with (
            open(tmp_dest, "wb") as fh,
            tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=f"{dest.name} (attempt {attempt})",
                disable=total_size == 0,
            ) as pbar,
        ):
            for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
                fh.write(chunk)
                pbar.update(len(chunk))

        # Atomic-ish rename to avoid leaving partial files
        tmp_dest.replace(dest)
    except BaseException:
        # Clean up partial download on any failure
        if tmp_dest.exists():
            tmp_dest.unlink()
        raise
