"""Graph simplification: node merging, dead-end removal, and connectivity enforcement.

Provides a pipeline to clean up raw OSM-derived road network graphs for
downstream UXsim simulation.  The three core operations — merging nearby nodes,
removing dead-end stubs, and extracting the largest strongly connected
component — are composable individually or via the convenience
:func:`simplify_network` pipeline.

All public functions return **new** graph instances; input graphs are never
modified in place.
"""

import logging
from collections import defaultdict

import networkx as nx

from src.config import NODE_MERGE_THRESHOLD

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _spatial_cell(x: float, y: float, cell_size: float) -> tuple[int, int]:
    """Return the grid cell index for coordinates (*x*, *y*).

    Parameters
    ----------
    x, y:
        Geographic coordinates (typically longitude and latitude in degrees).
    cell_size:
        Width / height of each grid cell in the same units as *x* and *y*.

    Returns
    -------
    tuple[int, int]
        Integer cell indices ``(col, row)``.
    """
    return (int(x // cell_size), int(y // cell_size))


class _UnionFind:
    """Lightweight Union-Find (disjoint-set) data structure.

    Used internally by :func:`merge_nearby_nodes` to cluster nodes that fall
    within the merge threshold.
    """

    __slots__ = ("_parent", "_rank")

    def __init__(self, elements: list) -> None:
        self._parent: dict = {e: e for e in elements}
        self._rank: dict = {e: 0 for e in elements}

    def find(self, x: object) -> object:
        """Return the root representative of *x* with path compression."""
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: object, b: object) -> None:
        """Merge the sets containing *a* and *b* (union by rank)."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def groups(self) -> dict[object, list]:
        """Return a mapping from root representative to member list."""
        result: dict[object, list] = defaultdict(list)
        for element in self._parent:
            result[self.find(element)].append(element)
        return dict(result)


def _find_merge_groups(
    graph: nx.DiGraph,
    threshold: float,
) -> dict[object, list]:
    """Identify clusters of nodes that should be merged.

    Uses a spatial-grid acceleration structure so that the pairwise distance
    check is performed only between nodes in the same or adjacent grid cells.

    Parameters
    ----------
    graph:
        A :class:`~networkx.DiGraph` whose nodes have ``'x'`` and ``'y'``
        attributes.
    threshold:
        Maximum Euclidean distance (in the same units as ``'x'``/``'y'``) for
        two nodes to be considered merge candidates.

    Returns
    -------
    dict
        Mapping from representative node to the list of nodes in its cluster.
    """
    node_coords: dict = {}
    for node, attrs in graph.nodes(data=True):
        node_coords[node] = (attrs["x"], attrs["y"])

    # Build spatial grid
    grid: dict[tuple[int, int], list] = defaultdict(list)
    for node, (x, y) in node_coords.items():
        cell = _spatial_cell(x, y, threshold)
        grid[cell].append(node)

    uf = _UnionFind(list(node_coords.keys()))
    threshold_sq = threshold * threshold

    for (cx, cy), cell_nodes in grid.items():
        # Collect all candidate neighbours from same and adjacent cells
        neighbours: list = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbours.extend(grid.get((cx + dx, cy + dy), []))

        for n1 in cell_nodes:
            x1, y1 = node_coords[n1]
            for n2 in neighbours:
                if n1 >= n2:
                    continue
                x2, y2 = node_coords[n2]
                if (x1 - x2) ** 2 + (y1 - y2) ** 2 <= threshold_sq:
                    uf.union(n1, n2)

    return uf.groups()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def merge_nearby_nodes(
    graph: nx.DiGraph,
    threshold: float = NODE_MERGE_THRESHOLD,
) -> nx.DiGraph:
    """Merge nodes that are within *threshold* degrees of each other.

    For each cluster of nearby nodes, a single representative node is kept and
    assigned the centroid position of the cluster.  All edges incident to
    merged-away nodes are redirected to the representative.  Self-loops created
    by the merge are dropped.

    Parameters
    ----------
    graph:
        A :class:`~networkx.DiGraph` with ``'x'`` and ``'y'`` node attributes.
    threshold:
        Maximum Euclidean distance (in degrees) below which two nodes are
        merged.  Defaults to :data:`src.config.NODE_MERGE_THRESHOLD` (~50 m).

    Returns
    -------
    nx.DiGraph
        A new graph with nearby nodes merged.  The input *graph* is not
        modified.
    """
    groups = _find_merge_groups(graph, threshold)

    # Build mapping: old_node -> representative_node
    node_map: dict = {}
    for rep, members in groups.items():
        for m in members:
            node_map[m] = rep

    G = nx.DiGraph()

    # Add representative nodes with centroid coordinates
    for rep, members in groups.items():
        xs = [graph.nodes[m]["x"] for m in members]
        ys = [graph.nodes[m]["y"] for m in members]
        centroid_x = sum(xs) / len(xs)
        centroid_y = sum(ys) / len(ys)
        G.add_node(rep, x=centroid_x, y=centroid_y)

    # Re-route edges through the node mapping
    for u, v, attrs in graph.edges(data=True):
        new_u = node_map[u]
        new_v = node_map[v]
        # Skip self-loops created by merging
        if new_u == new_v:
            continue
        # If a parallel edge already exists, keep the one with greater length
        # (longer road segments are typically more important)
        if G.has_edge(new_u, new_v):
            existing_len = G[new_u][new_v].get("length", 0)
            candidate_len = attrs.get("length", 0)
            if candidate_len <= existing_len:
                continue
        G.add_edge(new_u, new_v, **attrs)

    merged_count = graph.number_of_nodes() - G.number_of_nodes()
    logger.info(
        "merge_nearby_nodes: %d → %d nodes (merged %d, threshold=%.4f)",
        graph.number_of_nodes(),
        G.number_of_nodes(),
        merged_count,
        threshold,
    )
    logger.info(
        "merge_nearby_nodes: %d → %d edges",
        graph.number_of_edges(),
        G.number_of_edges(),
    )

    return G


def remove_dead_ends(graph: nx.DiGraph) -> nx.DiGraph:
    """Iteratively remove dead-end nodes (total degree ≤ 1).

    A dead-end node is one whose combined in-degree and out-degree is at most
    one — i.e., it connects to the network through a single link.  Removal is
    repeated until no dead-ends remain.

    Parameters
    ----------
    graph:
        A :class:`~networkx.DiGraph`.

    Returns
    -------
    nx.DiGraph
        A new graph with all dead-end chains removed.  The input *graph* is
        not modified.
    """
    G = graph.copy()
    total_removed = 0

    while True:
        dead_ends = [
            n for n in G.nodes() if G.in_degree(n) + G.out_degree(n) <= 1
        ]
        if not dead_ends:
            break
        G.remove_nodes_from(dead_ends)
        total_removed += len(dead_ends)

    logger.info(
        "remove_dead_ends: removed %d dead-end nodes (%d → %d nodes)",
        total_removed,
        graph.number_of_nodes(),
        G.number_of_nodes(),
    )

    return G


def extract_largest_component(graph: nx.DiGraph) -> nx.DiGraph:
    """Extract the largest strongly connected component.

    Parameters
    ----------
    graph:
        A :class:`~networkx.DiGraph`.

    Returns
    -------
    nx.DiGraph
        A new graph containing only the nodes and edges of the largest
        strongly connected component.  The input *graph* is not modified.

    Notes
    -----
    If the graph is empty (no nodes), an empty :class:`~networkx.DiGraph` is
    returned.  The number of dropped nodes is logged at INFO level.
    """
    if graph.number_of_nodes() == 0:
        logger.warning("extract_largest_component: input graph is empty")
        return nx.DiGraph()

    components = list(nx.strongly_connected_components(graph))
    largest = max(components, key=len)

    G = graph.subgraph(largest).copy()

    dropped = graph.number_of_nodes() - G.number_of_nodes()
    logger.info(
        "extract_largest_component: kept %d / %d nodes "
        "(dropped %d across %d smaller components)",
        G.number_of_nodes(),
        graph.number_of_nodes(),
        dropped,
        len(components) - 1,
    )

    return G


def simplify_network(graph: nx.DiGraph) -> nx.DiGraph:
    """Run the full simplification pipeline on a road network graph.

    The pipeline executes three steps in order:

    1. **Merge nearby nodes** — collapses nodes within
       :data:`~src.config.NODE_MERGE_THRESHOLD` degrees (~50 m).
    2. **Remove dead-ends** — iteratively strips degree-1 stubs.
    3. **Extract largest component** — keeps only the largest strongly
       connected component to ensure full reachability.

    Parameters
    ----------
    graph:
        A :class:`~networkx.DiGraph` with ``'x'`` and ``'y'`` node attributes
        (typically produced by :func:`src.network.builder.build_graph`).

    Returns
    -------
    nx.DiGraph
        A simplified, strongly connected graph.  The input *graph* is not
        modified.
    """
    logger.info(
        "simplify_network: starting pipeline "
        "(input: %d nodes, %d edges)",
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )

    G = merge_nearby_nodes(graph)
    G = remove_dead_ends(G)
    G = extract_largest_component(G)

    logger.info(
        "simplify_network: pipeline complete "
        "(output: %d nodes, %d edges)",
        G.number_of_nodes(),
        G.number_of_edges(),
    )

    return G
