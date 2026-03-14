"""Manage MATSim JAR download and Java runtime detection."""

import logging
import subprocess
import urllib.request
from pathlib import Path

from src.config import MATSIM_JAR_DIR, MATSIM_VERSION

logger = logging.getLogger(__name__)

MATSIM_RELEASE_BASE = "https://github.com/matsim-org/matsim-libs/releases/download"
MATSIM_JAR_FILENAME = f"matsim-{MATSIM_VERSION}-release.zip"


def check_java(min_version: int = 17) -> str:
    """Check that Java is installed and meets minimum version requirement.

    Returns
    -------
    str
        The Java version string.

    Raises
    ------
    RuntimeError
        If Java is not found or version is too old.
    """
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Java outputs version to stderr
        output = result.stderr or result.stdout
        logger.info("Java version output: %s", output.strip().split("\n")[0])

        # Parse version number
        import re
        match = re.search(r'"?(\d+)[\._]', output)
        if match:
            major = int(match.group(1))
            if major == 1:
                # Old-style versioning: 1.8 = Java 8
                match2 = re.search(r'1\.(\d+)', output)
                if match2:
                    major = int(match2.group(1))
            if major < min_version:
                raise RuntimeError(
                    f"Java {major} found, but MATSim requires Java {min_version}+. "
                    f"Please install JDK {min_version} or newer."
                )
            return output.strip().split("\n")[0]
        raise RuntimeError("Could not parse Java version from output")

    except FileNotFoundError:
        raise RuntimeError(
            "Java not found. MATSim requires Java 17+. "
            "Install with: brew install openjdk@17 (macOS) or "
            "apt install openjdk-17-jdk (Ubuntu)"
        )


def ensure_matsim_jar(version: str = MATSIM_VERSION) -> Path:
    """Ensure MATSim JAR is available, downloading if necessary.

    Returns
    -------
    Path
        Path to the MATSim JAR file.
    """
    jar_dir = MATSIM_JAR_DIR
    jar_dir.mkdir(parents=True, exist_ok=True)

    # Look for existing JAR
    jar_pattern = f"matsim-{version}*.jar"
    existing = list(jar_dir.glob(jar_pattern))
    if existing:
        jar_path = existing[0]
        logger.info("Found existing MATSim JAR: %s", jar_path)
        return jar_path

    # Also check for the "all" jar which includes contribs
    all_pattern = f"matsim-*{version}*.jar"
    existing_all = list(jar_dir.glob(all_pattern))
    if existing_all:
        jar_path = existing_all[0]
        logger.info("Found existing MATSim JAR: %s", jar_path)
        return jar_path

    # Download MATSim release
    logger.info("MATSim JAR not found, downloading version %s...", version)

    # Try the direct JAR URL first
    jar_filename = f"matsim-{version}.jar"
    jar_path = jar_dir / jar_filename
    jar_url = f"{MATSIM_RELEASE_BASE}/v{version}/{jar_filename}"

    try:
        _download_file(jar_url, jar_path)
        return jar_path
    except Exception as e:
        logger.warning("Direct JAR download failed: %s. Trying release zip...", e)

    # Try downloading the release zip
    zip_filename = f"matsim-{version}-release.zip"
    zip_path = jar_dir / zip_filename
    zip_url = f"{MATSIM_RELEASE_BASE}/v{version}/{zip_filename}"

    try:
        _download_file(zip_url, zip_path)
        # Extract JAR from zip
        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            jar_names = [n for n in zf.namelist() if n.endswith(".jar") and "matsim" in n.lower()]
            if jar_names:
                # Extract the main JAR
                main_jar = jar_names[0]
                zf.extract(main_jar, jar_dir)
                extracted = jar_dir / main_jar
                logger.info("Extracted MATSim JAR: %s", extracted)
                return extracted
    except Exception as e:
        logger.error("Failed to download MATSim: %s", e)

    raise RuntimeError(
        f"Could not download MATSim {version}. Please manually download from "
        f"https://github.com/matsim-org/matsim-libs/releases and place the JAR "
        f"in {jar_dir}"
    )


def _download_file(url: str, dest: Path) -> None:
    """Download a file with progress logging."""
    logger.info("Downloading %s → %s", url, dest)
    urllib.request.urlretrieve(url, str(dest))
    logger.info("Download complete: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)


def setup_matsim(version: str = MATSIM_VERSION) -> tuple[str, Path]:
    """Check Java and ensure MATSim JAR is available.

    Returns
    -------
    tuple[str, Path]
        (java_version_string, path_to_matsim_jar)
    """
    java_version = check_java()
    jar_path = ensure_matsim_jar(version)
    logger.info("MATSim setup complete: Java=%s, JAR=%s", java_version, jar_path)
    return java_version, jar_path
