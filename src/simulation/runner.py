"""Simulation execution, result serialization, and deserialization.

Provides functions to run a configured :class:`uxsim.World` simulation,
persist the results to disk as pickle files, and reload them for
post-processing (visualization, export, etc.).

Timing and logging are integrated so that simulation duration is
reported automatically.
"""

import collections
import logging
import pickle
import time
from pathlib import Path

from uxsim import World

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_simulation(W: World) -> World:
    """Execute the UXsim simulation and print summary statistics.

    Calls :meth:`uxsim.World.exec_simulation` to run the mesoscopic
    traffic simulation, then prints aggregate statistics via the built-in
    analyser.  The elapsed wall-clock time is logged for performance
    tracking.

    Parameters
    ----------
    W:
        A fully configured UXsim World with nodes, links, and demand
        already added.

    Returns
    -------
    World
        The same World object after simulation has completed.  Results
        are accessible through ``W.analyzer``.

    Raises
    ------
    RuntimeError
        If the simulation fails due to an internal UXsim error.
    """
    logger.info("run_simulation: starting simulation '%s'", W.name)

    t_start = time.perf_counter()

    try:
        W.exec_simulation()
    except Exception as exc:
        elapsed = time.perf_counter() - t_start
        logger.error(
            "run_simulation: simulation failed after %.1f s — %s",
            elapsed,
            exc,
        )
        raise RuntimeError(
            f"Simulation '{W.name}' failed: {exc}"
        ) from exc

    elapsed = time.perf_counter() - t_start

    # ------------------------------------------------------------------
    # Print summary statistics via the built-in analyser
    # ------------------------------------------------------------------
    try:
        W.analyzer.print_simple_stats()
    except Exception:
        logger.warning(
            "run_simulation: could not print analyser stats "
            "(simulation may have produced no results)"
        )

    logger.info(
        "run_simulation: simulation '%s' completed in %.1f s",
        W.name,
        elapsed,
    )

    return W


def _patch_unpicklable_defaultdicts(
    obj: object,
    _visited: set | None = None,
) -> list[tuple[object, str, collections.defaultdict]]:
    """Recursively replace unpicklable defaultdicts with plain dicts.

    Returns a list of (owner, attr_name, original_defaultdict) tuples
    so that :func:`_restore_defaultdicts` can undo the changes.
    """
    if _visited is None:
        _visited = set()

    obj_id = id(obj)
    if obj_id in _visited:
        return []
    _visited.add(obj_id)

    patches: list[tuple[object, str, collections.defaultdict]] = []

    for attr_name in list(vars(obj)):
        val = getattr(obj, attr_name, None)
        if isinstance(val, collections.defaultdict):
            factory = val.default_factory
            if factory is not None:
                try:
                    pickle.dumps(factory)
                except (pickle.PicklingError, TypeError, AttributeError):
                    patches.append((obj, attr_name, val))
                    setattr(obj, attr_name, dict(val))
        elif hasattr(val, "__dict__") and not isinstance(val, type):
            patches.extend(_patch_unpicklable_defaultdicts(val, _visited))

    return patches


def _restore_defaultdicts(
    patches: list[tuple[object, str, collections.defaultdict]],
) -> None:
    """Restore defaultdicts that were replaced by :func:`_patch_unpicklable_defaultdicts`."""
    for owner, attr_name, original in patches:
        setattr(owner, attr_name, original)


def save_results(W: World, output_path: str | Path | None = None) -> Path:
    """Serialize simulation results to a pickle file.

    Parameters
    ----------
    W:
        A UXsim World that has completed simulation.
    output_path:
        Destination file path.  If ``None``, a default path under
        :data:`src.config.OUTPUT_DIR` is generated from the World name
        (e.g. ``data/output/japan_traffic_results.pkl``).

    Returns
    -------
    Path
        The absolute path to the saved pickle file.

    Raises
    ------
    OSError
        If the file cannot be written (e.g. permission error, disk full).
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"{W.name}_results.pkl"
    else:
        output_path = Path(output_path)

    # Ensure the parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # UXsim World objects may contain defaultdict attributes whose
    # factory is a local lambda (e.g. Q_AREA in finalize_scenario,
    # od_trips in Analyzer).  Lambdas are not picklable with the
    # standard pickle module.  We temporarily replace such defaultdicts
    # with plain dicts for serialization, then restore them.
    patches = _patch_unpicklable_defaultdicts(W)

    try:
        with open(output_path, "wb") as fh:
            pickle.dump(W, fh, protocol=pickle.HIGHEST_PROTOCOL)
    finally:
        _restore_defaultdicts(patches)

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "save_results: saved results to %s (%.1f MB)",
        output_path,
        file_size_mb,
    )

    return output_path


def load_results(result_path: str | Path) -> object:
    """Load serialized simulation results from a pickle file.

    Parameters
    ----------
    result_path:
        Path to a pickle file previously created by :func:`save_results`.

    Returns
    -------
    object
        The deserialized object (typically a :class:`uxsim.World`).

    Raises
    ------
    FileNotFoundError
        If *result_path* does not exist.
    """
    result_path = Path(result_path)

    if not result_path.exists():
        raise FileNotFoundError(f"Result file not found: {result_path}")

    with open(result_path, "rb") as fh:
        data = pickle.load(fh)  # noqa: S301

    logger.info("load_results: loaded results from %s", result_path)

    return data
