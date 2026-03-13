"""Pyrosm PBF parser for extracting filtered road networks.

Parses OpenStreetMap PBF extracts via Pyrosm, extracts the driving network
as GeoDataFrames, and filters edges by highway type using the configurable
whitelist from :data:`src.config.HIGHWAY_FILTER`.
"""

import logging
from pathlib import Path

import geopandas as gpd
from pyrosm import OSM

from src.config import HIGHWAY_FILTER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_road_network(
    pbf_path: Path | str,
    highway_types: list[str] | None = None,
    include_nodes: bool = True,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame] | gpd.GeoDataFrame:
    """Parse a PBF file and extract the filtered driving road network.

    Uses Pyrosm to read the PBF extract and retrieve the driving network.
    Edges are filtered to include only the specified highway types (defaulting
    to :data:`src.config.HIGHWAY_FILTER`).  When *include_nodes* is ``True``,
    unreferenced nodes (those not connected to any filtered edge) are pruned.

    Parameters
    ----------
    pbf_path:
        Path to the ``.osm.pbf`` file to parse.
    highway_types:
        List of OSM highway type strings to keep (e.g.
        ``["motorway", "trunk"]``).  When ``None``, defaults to
        :data:`src.config.HIGHWAY_FILTER`.
    include_nodes:
        When ``True``, return both nodes and edges as a tuple.  When
        ``False``, return only the edges GeoDataFrame.

    Returns
    -------
    tuple[GeoDataFrame, GeoDataFrame] | GeoDataFrame
        If *include_nodes* is ``True``, returns ``(nodes, edges)`` where
        *nodes* contains only those referenced by the filtered edges
        (via ``u`` / ``v`` columns).  Otherwise returns the filtered
        *edges* GeoDataFrame alone.

    Raises
    ------
    FileNotFoundError
        If *pbf_path* does not exist.
    """
    pbf_path = Path(pbf_path)
    if not pbf_path.is_file():
        raise FileNotFoundError(f"PBF file not found: {pbf_path}")

    if highway_types is None:
        highway_types = HIGHWAY_FILTER

    logger.info("Parsing PBF: %s", pbf_path)
    osm = OSM(str(pbf_path))

    # ------------------------------------------------------------------
    # Extract driving network
    # ------------------------------------------------------------------
    if include_nodes:
        nodes, edges = osm.get_network(network_type="driving", nodes=True)
    else:
        edges = osm.get_network(network_type="driving")
        nodes = None

    logger.info(
        "Raw network: %d edges%s",
        len(edges),
        f", {len(nodes)} nodes" if nodes is not None else "",
    )

    # ------------------------------------------------------------------
    # Filter edges by highway type
    # ------------------------------------------------------------------
    mask = edges["highway"].isin(highway_types)
    filtered_edges = edges[mask].copy()

    logger.info(
        "Filtered edges: %d (kept %d of %d highway types)",
        len(filtered_edges),
        len(highway_types),
        edges["highway"].nunique(),
    )

    # ------------------------------------------------------------------
    # Prune unreferenced nodes
    # ------------------------------------------------------------------
    if include_nodes and nodes is not None:
        referenced_ids = set(filtered_edges["u"]).union(
            set(filtered_edges["v"])
        )
        filtered_nodes = nodes[nodes["id"].isin(referenced_ids)].copy()

        logger.info(
            "Filtered nodes: %d (pruned %d unreferenced)",
            len(filtered_nodes),
            len(nodes) - len(filtered_nodes),
        )
        return filtered_nodes, filtered_edges

    return filtered_edges
