"""Execute MATSim simulation via subprocess."""

import logging
import re
import subprocess
from pathlib import Path

from src.matsim.java_manager import ensure_matsim_jar

logger = logging.getLogger(__name__)


def run_matsim(
    config_path: Path,
    java_path: str = "java",
    matsim_jar: Path | None = None,
    jvm_memory: str = "8g",
    working_dir: Path | None = None,
) -> Path:
    """Run MATSim simulation and return the output directory.

    Parameters
    ----------
    config_path:
        Path to config.xml.
    java_path:
        Path to java executable.
    matsim_jar:
        Path to MATSim JAR. If None, auto-detected.
    jvm_memory:
        JVM heap size (e.g. "8g", "4g").
    working_dir:
        Working directory for the process.

    Returns
    -------
    Path
        Path to the MATSim output directory.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")

    if matsim_jar is None:
        matsim_jar = ensure_matsim_jar()

    if working_dir is None:
        working_dir = config_path.parent

    # Build classpath - include all JARs in the matsim dir
    jar_dir = matsim_jar.parent
    all_jars = list(jar_dir.glob("*.jar"))
    classpath = ":".join(str(j) for j in all_jars)

    cmd = [
        java_path,
        f"-Xmx{jvm_memory}",
        "-cp", classpath,
        "org.matsim.run.Controler",
        str(config_path.resolve()),
    ]

    logger.info("Starting MATSim: %s", " ".join(cmd[:4]) + " ...")
    logger.info("Config: %s", config_path)
    logger.info("Working dir: %s", working_dir)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(working_dir),
    )

    # Stream output and track progress
    iteration_pattern = re.compile(r"Iteration\s+(\d+)\s*/\s*(\d+)")

    for line in process.stdout:
        line = line.rstrip()
        if line:
            logger.info("[MATSim] %s", line)
            match = iteration_pattern.search(line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                logger.info("Progress: iteration %d/%d (%.0f%%)",
                            current, total, 100 * current / max(total, 1))

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"MATSim exited with code {process.returncode}")

    # Find output directory
    output_dir = working_dir / "output"
    if not output_dir.is_dir():
        # Try to find it from config
        output_dir = config_path.parent / "output"

    logger.info("MATSim completed. Output: %s", output_dir)
    return output_dir


def find_events_file(output_dir: Path) -> Path | None:
    """Find the final events.xml.gz in MATSim output."""
    output_dir = Path(output_dir)
    candidates = sorted(output_dir.glob("**/output_events.xml.gz"), reverse=True)
    if candidates:
        return candidates[0]
    candidates = sorted(output_dir.glob("**/*.events.xml.gz"), reverse=True)
    if candidates:
        return candidates[0]
    return None
