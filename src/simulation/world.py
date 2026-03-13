"""UXsim World factory from NetworkX road network graph.

Creates a fully configured :class:`uxsim.World` object from a processed
NetworkX :class:`~networkx.DiGraph`.  Node coordinates (lon/lat in degrees)
are transformed to approximate meters using
:data:`src.config.COEF_DEGREE_TO_METER` and each edge is converted to an
UXsim link with appropriate speed, lane, and length parameters.

The resulting World is ready for demand addition and simulation execution.
"""

import logging

import networkx as nx
from uxsim import World

from src.config import COEF_DEGREE_TO_METER, DEFAULT_DELTAN, DEFAULT_TMAX

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensible fallbacks when graph attributes are missing
# ---------------------------------------------------------------------------
_FALLBACK_LENGTH: float = 1000.0  # meters
_FALLBACK_SPEED_KPH: float = 60.0  # km/h
_FALLBACK_LANES: int = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_world(
    graph: nx.DiGraph,
    deltan: int = DEFAULT_DELTAN,
    tmax: int = DEFAULT_TMAX,
    name: str = "japan_traffic",
    random_seed: int = 0,
) -> World:
    """Create a UXsim World from a processed road network graph.

    Parameters
    ----------
    graph:
        A NetworkX directed graph.  Each node must have ``'x'`` (longitude)
        and ``'y'`` (latitude) attributes in degrees.  Each edge should have
        ``'length'`` (meters), ``'speed_kph'`` (km/h), and ``'lanes'`` (int)
        attributes; missing values are replaced with sensible defaults.
    deltan:
        UXsim platoon size parameter.  Higher values speed up simulation at
        the cost of granularity.  Defaults to
        :data:`src.config.DEFAULT_DELTAN`.
    tmax:
        Maximum simulation duration in seconds.  Defaults to
        :data:`src.config.DEFAULT_TMAX` (7200 = 2 hours).
    name:
        Descriptive name for the simulation scenario.
    random_seed:
        Random seed for reproducibility.

    Returns
    -------
    World
        A configured UXsim World with all nodes and links added, ready for
        demand generation and simulation execution.

    Raises
    ------
    ValueError
        If the input graph has no nodes.

    Notes
    -----
    - Coordinates are converted from degrees to meters via
      ``COEF_DEGREE_TO_METER`` (≈ 89 799 for Japan at ~36°N).
    - ``show_mode=0`` disables GUI popups for headless execution.
    - ``save_mode=1`` enables result persistence for post-analysis.
    - Self-loop edges are skipped because UXsim does not support zero-length
      links with identical start and end nodes.
    - Duplicate edge names are disambiguated with a numeric suffix.
    """
    if graph.number_of_nodes() == 0:
        raise ValueError("Cannot create World from an empty graph (no nodes)")

    # ------------------------------------------------------------------
    # Initialise UXsim World
    # ------------------------------------------------------------------
    W = World(
        name=name,
        deltan=deltan,
        tmax=tmax,
        print_mode=1,
        save_mode=1,
        show_mode=0,
        random_seed=random_seed,
    )

    # ------------------------------------------------------------------
    # Add nodes with coordinate transformation
    # ------------------------------------------------------------------
    node_count = 0
    for node_id, attrs in graph.nodes(data=True):
        x_deg = attrs.get("x", 0.0)
        y_deg = attrs.get("y", 0.0)
        W.addNode(
            name=str(node_id),
            x=x_deg * COEF_DEGREE_TO_METER,
            y=y_deg * COEF_DEGREE_TO_METER,
        )
        node_count += 1

    # ------------------------------------------------------------------
    # Add links (edges) with road attributes
    # ------------------------------------------------------------------
    link_count = 0
    skipped_self_loops = 0
    seen_names: set[str] = set()

    for u, v, attrs in graph.edges(data=True):
        # Skip self-loops — UXsim cannot handle links where start == end
        if u == v:
            skipped_self_loops += 1
            continue

        # Build a unique link name
        link_name = f"{u}_{v}"
        if link_name in seen_names:
            suffix = 1
            while f"{link_name}_{suffix}" in seen_names:
                suffix += 1
            link_name = f"{link_name}_{suffix}"
        seen_names.add(link_name)

        # Extract attributes with fallback defaults
        length = attrs.get("length", _FALLBACK_LENGTH)
        if length is None or length <= 0:
            length = _FALLBACK_LENGTH

        speed_kph = attrs.get("speed_kph", _FALLBACK_SPEED_KPH)
        if speed_kph is None or speed_kph <= 0:
            speed_kph = _FALLBACK_SPEED_KPH

        lanes = attrs.get("lanes", _FALLBACK_LANES)
        if lanes is None or lanes <= 0:
            lanes = _FALLBACK_LANES

        W.addLink(
            name=link_name,
            start_node=str(u),
            end_node=str(v),
            length=length,
            free_flow_speed=speed_kph / 3.6,
            number_of_lanes=int(lanes),
        )
        link_count += 1

    # ------------------------------------------------------------------
    # Log statistics
    # ------------------------------------------------------------------
    if skipped_self_loops > 0:
        logger.warning(
            "create_world: skipped %d self-loop edges", skipped_self_loops
        )

    logger.info(
        "create_world: built World '%s' with %d nodes and %d links "
        "(deltan=%d, tmax=%d)",
        name,
        node_count,
        link_count,
        deltan,
        tmax,
    )

    return W
