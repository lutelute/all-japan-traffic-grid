#!/usr/bin/env python3
"""Generate demo visualization data for the web UI without running MATSim.

Creates synthetic trajectory and link count data based on the existing
OD pair definitions, suitable for testing the SimCity web visualization.

Usage:
    python scripts/generate_demo_data.py
    python scripts/generate_demo_data.py --agents 2000 --region kanto
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# Inline OD pairs to avoid uxsim dependency for demo generation
_TOKYO_OD_PAIRS = [
    {"origin_lon": 139.6275, "origin_lat": 35.9062, "dest_lon": 139.7671, "dest_lat": 35.6812, "volume": 6000},
    {"origin_lon": 140.1233, "origin_lat": 35.6074, "dest_lon": 139.7671, "dest_lat": 35.6812, "volume": 5000},
    {"origin_lon": 139.6380, "origin_lat": 35.4437, "dest_lon": 139.7400, "dest_lat": 35.6284, "volume": 7000},
    {"origin_lon": 139.4140, "origin_lat": 35.6983, "dest_lon": 139.7003, "dest_lat": 35.6894, "volume": 4000},
    {"origin_lon": 139.7172, "origin_lat": 35.5308, "dest_lon": 139.7015, "dest_lat": 35.6580, "volume": 4500},
    {"origin_lon": 139.9828, "origin_lat": 35.6947, "dest_lon": 139.7107, "dest_lat": 35.7290, "volume": 3500},
    {"origin_lon": 139.4689, "origin_lat": 35.7990, "dest_lon": 139.7107, "dest_lat": 35.7290, "volume": 3000},
    {"origin_lon": 139.9756, "origin_lat": 35.8676, "dest_lon": 139.7745, "dest_lat": 35.7141, "volume": 3000},
]


def generate_demo_trajectories(num_agents=1000, region="kanto", seed=42):
    """Generate synthetic agent trajectories for demo visualization."""
    rng = random.Random(seed)

    od_pairs = _TOKYO_OD_PAIRS

    trajectories = []

    for i in range(num_agents):
        # Pick random OD pair (weighted by volume)
        total_vol = sum(p["volume"] for p in od_pairs)
        r = rng.random() * total_vol
        cum = 0
        pair = od_pairs[0]
        for p in od_pairs:
            cum += p["volume"]
            if r <= cum:
                pair = p
                break

        # Generate waypoints along a slightly curved path
        o_lon = pair["origin_lon"] + rng.gauss(0, 0.02)
        o_lat = pair["origin_lat"] + rng.gauss(0, 0.02)
        d_lon = pair["dest_lon"] + rng.gauss(0, 0.01)
        d_lat = pair["dest_lat"] + rng.gauss(0, 0.01)

        # Departure time: 6:00-9:00 AM
        depart_time = rng.gauss(7.5, 0.7) * 3600
        depart_time = max(5 * 3600, min(10 * 3600, depart_time))

        # Trip duration: 30-90 minutes based on distance
        dist = math.sqrt((d_lon - o_lon) ** 2 + (d_lat - o_lat) ** 2)
        duration = 1800 + dist * 50000 + rng.gauss(0, 600)
        duration = max(600, min(7200, duration))

        # Generate intermediate points with some curvature
        n_points = max(5, int(duration / 120))
        path = []
        mid_offset_lon = rng.gauss(0, 0.01)
        mid_offset_lat = rng.gauss(0, 0.01)

        for j in range(n_points):
            t = j / (n_points - 1)
            # Quadratic Bezier curve
            lon = ((1 - t) ** 2 * o_lon +
                   2 * (1 - t) * t * ((o_lon + d_lon) / 2 + mid_offset_lon) +
                   t ** 2 * d_lon)
            lat = ((1 - t) ** 2 * o_lat +
                   2 * (1 - t) * t * ((o_lat + d_lat) / 2 + mid_offset_lat) +
                   t ** 2 * d_lat)

            # Add small jitter for realism
            lon += rng.gauss(0, 0.001)
            lat += rng.gauss(0, 0.001)

            timestamp = depart_time + t * duration
            path.append([round(lon, 6), round(lat, 6), round(timestamp, 1)])

        trajectories.append({
            "agent_id": f"agent_{i}",
            "path": path,
        })

    # Add evening return trips
    for i in range(num_agents):
        traj = trajectories[i]
        if len(traj["path"]) < 2:
            continue

        # Reverse the path for return trip
        original = traj["path"]
        return_depart = rng.gauss(17.5, 0.8) * 3600
        return_depart = max(15 * 3600, min(21 * 3600, return_depart))
        duration = original[-1][2] - original[0][2]

        return_path = []
        for j, pt in enumerate(reversed(original)):
            t = j / max(len(original) - 1, 1)
            timestamp = return_depart + t * duration
            return_path.append([
                pt[0] + rng.gauss(0, 0.001),
                pt[1] + rng.gauss(0, 0.001),
                round(timestamp, 1),
            ])

        trajectories.append({
            "agent_id": f"agent_{i}_return",
            "path": return_path,
        })

    return trajectories


def generate_demo_link_counts(trajectories, time_bin=300):
    """Generate synthetic link counts from trajectories."""
    max_time = 86400
    n_bins = max_time // time_bin

    # Create a grid of virtual links
    link_data = {}
    # Use trajectory segments as virtual links
    link_counter = 0

    for traj in trajectories[:500]:  # Limit for performance
        path = traj["path"]
        for i in range(len(path) - 1):
            link_id = f"link_{link_counter}"
            link_counter += 1

            time_bin_idx = int(path[i][2] // time_bin)
            time_bin_idx = min(time_bin_idx, n_bins - 1)

            counts = [0] * n_bins
            # Vehicle present in this time bin and nearby bins
            for offset in range(-1, 3):
                idx = time_bin_idx + offset
                if 0 <= idx < n_bins:
                    counts[idx] += 1

            link_data[link_id] = {
                "coords": [path[i][:2], path[i + 1][:2]],
                "counts": counts,
            }

    timestamps = [i * time_bin for i in range(n_bins)]
    return {"timestamps": timestamps, "links": link_data}


def generate_demo_network_geojson(trajectories):
    """Generate a network GeoJSON from trajectory segments."""
    features = []
    seen = set()

    for traj in trajectories[:500]:
        path = traj["path"]
        for i in range(len(path) - 1):
            key = (round(path[i][0], 4), round(path[i][1], 4),
                   round(path[i + 1][0], 4), round(path[i + 1][1], 4))
            if key not in seen:
                seen.add(key)
                features.append({
                    "type": "Feature",
                    "properties": {"id": f"seg_{len(features)}"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [path[i][:2], path[i + 1][:2]],
                    },
                })

    return {"type": "FeatureCollection", "features": features}


def main():
    parser = argparse.ArgumentParser(description="Generate demo data for web visualization")
    parser.add_argument("--agents", type=int, default=1000, help="Number of agents")
    parser.add_argument("--region", default="kanto", help="Region")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory")
    args = parser.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "web" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating demo data: {args.agents} agents for {args.region}...")

    # Generate trajectories
    trajectories = generate_demo_trajectories(args.agents, args.region)
    traj_path = output_dir / "trajectories.json"
    with open(traj_path, "w") as f:
        json.dump(trajectories, f)
    print(f"  Trajectories: {len(trajectories)} → {traj_path}")

    # Generate link counts
    link_counts = generate_demo_link_counts(trajectories)
    counts_path = output_dir / "link_counts.json"
    with open(counts_path, "w") as f:
        json.dump(link_counts, f)
    print(f"  Link counts: {len(link_counts['links'])} links → {counts_path}")

    # Generate network GeoJSON
    network = generate_demo_network_geojson(trajectories)
    geojson_path = output_dir / "network.geojson"
    with open(geojson_path, "w") as f:
        json.dump(network, f)
    print(f"  Network: {len(network['features'])} segments → {geojson_path}")

    print(f"\nDone! Open web/index.html in a browser to view.")
    print(f"(Serve locally with: python -m http.server 8080 --directory web)")


if __name__ == "__main__":
    main()
