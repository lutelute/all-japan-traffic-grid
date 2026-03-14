"""Synthetic population and activity plan generation for MATSim.

Generates plans.xml with home-work-home activity chains for synthetic agents.
Uses the existing OD pair data and network graph to create realistic commuter
patterns across Japanese regions.
"""

import logging
import random
from pathlib import Path

import networkx as nx
from lxml import etree

from src.matsim.network_converter import get_node_coords

logger = logging.getLogger(__name__)

# Predefined population centers by region with approximate populations
REGION_CENTERS: dict[str, list[dict]] = {
    "kanto": [
        {"name": "Tokyo", "lon": 139.6917, "lat": 35.6895, "pop_weight": 0.30},
        {"name": "Yokohama", "lon": 139.6380, "lat": 35.4437, "pop_weight": 0.15},
        {"name": "Saitama", "lon": 139.6489, "lat": 35.8617, "pop_weight": 0.12},
        {"name": "Chiba", "lon": 140.1233, "lat": 35.6074, "pop_weight": 0.10},
        {"name": "Kawasaki", "lon": 139.7172, "lat": 35.5308, "pop_weight": 0.08},
        {"name": "Sagamihara", "lon": 139.3728, "lat": 35.5714, "pop_weight": 0.05},
        {"name": "Funabashi", "lon": 139.9828, "lat": 35.6947, "pop_weight": 0.04},
        {"name": "Hachioji", "lon": 139.3160, "lat": 35.6664, "pop_weight": 0.03},
        {"name": "Kashiwa", "lon": 139.9756, "lat": 35.8676, "pop_weight": 0.03},
        {"name": "Tachikawa", "lon": 139.4140, "lat": 35.6983, "pop_weight": 0.02},
    ],
    "kansai": [
        {"name": "Osaka", "lon": 135.5023, "lat": 34.6937, "pop_weight": 0.30},
        {"name": "Kobe", "lon": 135.1955, "lat": 34.6901, "pop_weight": 0.15},
        {"name": "Kyoto", "lon": 135.7681, "lat": 35.0116, "pop_weight": 0.15},
        {"name": "Sakai", "lon": 135.4830, "lat": 34.5733, "pop_weight": 0.10},
        {"name": "Himeji", "lon": 134.6889, "lat": 34.8151, "pop_weight": 0.05},
        {"name": "Nara", "lon": 135.8048, "lat": 34.6851, "pop_weight": 0.05},
    ],
    "chubu": [
        {"name": "Nagoya", "lon": 136.9066, "lat": 35.1815, "pop_weight": 0.35},
        {"name": "Hamamatsu", "lon": 137.7261, "lat": 34.7108, "pop_weight": 0.10},
        {"name": "Shizuoka", "lon": 138.3831, "lat": 34.9756, "pop_weight": 0.10},
        {"name": "Niigata", "lon": 139.0364, "lat": 37.9022, "pop_weight": 0.08},
        {"name": "Kanazawa", "lon": 136.6256, "lat": 36.5946, "pop_weight": 0.05},
    ],
    "hokkaido": [
        {"name": "Sapporo", "lon": 141.3469, "lat": 43.0618, "pop_weight": 0.50},
        {"name": "Asahikawa", "lon": 142.3700, "lat": 43.7709, "pop_weight": 0.10},
        {"name": "Hakodate", "lon": 140.7288, "lat": 41.7688, "pop_weight": 0.08},
    ],
    "tohoku": [
        {"name": "Sendai", "lon": 140.8720, "lat": 38.2682, "pop_weight": 0.30},
        {"name": "Morioka", "lon": 141.1527, "lat": 39.7036, "pop_weight": 0.08},
        {"name": "Akita", "lon": 140.1024, "lat": 39.7200, "pop_weight": 0.08},
    ],
    "chugoku": [
        {"name": "Hiroshima", "lon": 132.4596, "lat": 34.3853, "pop_weight": 0.30},
        {"name": "Okayama", "lon": 133.9350, "lat": 34.6618, "pop_weight": 0.15},
    ],
    "shikoku": [
        {"name": "Matsuyama", "lon": 132.7657, "lat": 33.8392, "pop_weight": 0.25},
        {"name": "Takamatsu", "lon": 134.0434, "lat": 34.3401, "pop_weight": 0.20},
    ],
    "kyushu": [
        {"name": "Fukuoka", "lon": 130.4017, "lat": 33.5904, "pop_weight": 0.25},
        {"name": "Kitakyushu", "lon": 130.8333, "lat": 33.8833, "pop_weight": 0.10},
        {"name": "Kumamoto", "lon": 130.7417, "lat": 32.8032, "pop_weight": 0.10},
        {"name": "Kagoshima", "lon": 130.5581, "lat": 31.5966, "pop_weight": 0.08},
    ],
}


def _sample_location_near(
    center_lon: float,
    center_lat: float,
    radius_deg: float,
    rng: random.Random,
) -> tuple[float, float]:
    """Sample a random point within radius_deg of center."""
    angle = rng.uniform(0, 2 * 3.14159265)
    r = radius_deg * rng.uniform(0, 1) ** 0.5
    return center_lon + r * 1.23 * __import__("math").cos(angle), \
           center_lat + r * __import__("math").sin(angle)


def _departure_time(rng: random.Random, mean_hour: float = 7.5, std_hours: float = 0.5) -> str:
    """Generate a departure time string (HH:MM:SS) normally distributed."""
    hours = rng.gauss(mean_hour, std_hours)
    hours = max(5.0, min(hours, 10.0))
    h = int(hours)
    m = int((hours - h) * 60)
    s = int(((hours - h) * 60 - m) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _return_time(rng: random.Random, mean_hour: float = 17.5, std_hours: float = 0.75) -> str:
    """Generate a return departure time string."""
    hours = rng.gauss(mean_hour, std_hours)
    hours = max(15.0, min(hours, 21.0))
    h = int(hours)
    m = int((hours - h) * 60)
    s = int(((hours - h) * 60 - m) * 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def generate_population(
    graph: nx.DiGraph,
    output_path: Path,
    region: str = "kanto",
    total_agents: int = 10000,
    random_seed: int = 42,
) -> Path:
    """Generate MATSim plans.xml with synthetic home-work-home agents.

    Parameters
    ----------
    graph:
        NetworkX DiGraph (used for coordinate transformation).
    output_path:
        Where to write plans.xml.
    region:
        Region name (must be a key in REGION_CENTERS).
    total_agents:
        Number of agents to generate.
    random_seed:
        Random seed for reproducibility.

    Returns
    -------
    Path
        The output file path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(random_seed)

    # Get node coords for UTM projection
    node_coords = get_node_coords(graph)

    # Get population centers
    region_lower = region.lower()
    centers = REGION_CENTERS.get(region_lower, REGION_CENTERS.get("kanto"))

    # Normalize weights
    total_weight = sum(c["pop_weight"] for c in centers)
    for c in centers:
        c["_norm_weight"] = c["pop_weight"] / total_weight

    # Determine centroid for UTM conversion
    from src.matsim.network_converter import _deg_to_utm
    lons = [d["x"] for _, d in graph.nodes(data=True) if "x" in d]
    centroid_lon = sum(lons) / len(lons) if lons else 139.7

    logger.info("Generating %d agents for region '%s' with %d population centers",
                total_agents, region, len(centers))

    root = etree.Element("population")

    for i in range(total_agents):
        # Select home center (weighted by population)
        r = rng.random()
        cumulative = 0.0
        home_center = centers[0]
        for c in centers:
            cumulative += c["_norm_weight"]
            if r <= cumulative:
                home_center = c
                break

        # Select work center (different from home, weighted)
        work_candidates = [c for c in centers if c["name"] != home_center["name"]]
        if not work_candidates:
            work_candidates = centers
        work_total = sum(c["pop_weight"] for c in work_candidates)
        r = rng.random() * work_total
        cumulative = 0.0
        work_center = work_candidates[0]
        for c in work_candidates:
            cumulative += c["pop_weight"]
            if r <= cumulative:
                work_center = c
                break

        # Sample exact locations
        home_lon, home_lat = _sample_location_near(
            home_center["lon"], home_center["lat"], 0.03, rng)
        work_lon, work_lat = _sample_location_near(
            work_center["lon"], work_center["lat"], 0.02, rng)

        # Convert to UTM
        home_x, home_y = _deg_to_utm(home_lon, home_lat, centroid_lon)
        work_x, work_y = _deg_to_utm(work_lon, work_lat, centroid_lon)

        # Build plan
        person = etree.SubElement(root, "person")
        person.set("id", f"agent_{i}")

        plan = etree.SubElement(person, "plan")
        plan.set("selected", "yes")

        # Home → Work
        home_act = etree.SubElement(plan, "activity")
        home_act.set("type", "home")
        home_act.set("x", f"{home_x:.2f}")
        home_act.set("y", f"{home_y:.2f}")
        home_act.set("end_time", _departure_time(rng))

        leg1 = etree.SubElement(plan, "leg")
        leg1.set("mode", "car")

        # Work
        work_act = etree.SubElement(plan, "activity")
        work_act.set("type", "work")
        work_act.set("x", f"{work_x:.2f}")
        work_act.set("y", f"{work_y:.2f}")
        work_act.set("end_time", _return_time(rng))

        leg2 = etree.SubElement(plan, "leg")
        leg2.set("mode", "car")

        # Home (return)
        home_return = etree.SubElement(plan, "activity")
        home_return.set("type", "home")
        home_return.set("x", f"{home_x:.2f}")
        home_return.set("y", f"{home_y:.2f}")

    # Write XML
    tree = etree.ElementTree(root)
    etree.indent(tree, space="  ")
    with open(output_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b'<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n')
        tree.write(f, pretty_print=True, xml_declaration=False, encoding="UTF-8")

    logger.info("Wrote %d agents to %s", total_agents, output_path)
    return output_path
