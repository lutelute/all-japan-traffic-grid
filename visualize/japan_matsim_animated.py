#!/usr/bin/env python3
"""MATSim simulation results as animated Folium/Leaflet map.

Reads the partitioned MATSim output (trajectories + link counts + network)
and renders a 24-hour animated visualization matching the style of
japan_traffic_animated.py but using real MATSim agent-based results.

Usage:
    python visualize/japan_matsim_animated.py
    python visualize/japan_matsim_animated.py --data-dir /path/to/viz/data
"""

import argparse
import json
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"


def build_animated_html(
    trajectories: list,
    link_counts: dict,
    network: dict,
    output_path: Path,
    title: str = "MATSim Japan Traffic — 24h Animation",
):
    """Build a standalone HTML with animated MATSim results."""

    # Pre-process link data for animation frames
    timestamps = link_counts.get("timestamps", [])
    links_data = link_counts.get("links", {})

    # Build compact link geometry + count data
    # Each link: [[lon1,lat1],[lon2,lat2]], counts per time bin
    compact_links = []
    for lid, ldata in links_data.items():
        coords = ldata.get("coords")
        counts = ldata.get("counts", [])
        if coords and any(c > 0 for c in counts):
            compact_links.append({
                "c": [[round(c[0], 4), round(c[1], 4)] for c in coords],
                "v": counts,
            })

    # Build compact trajectory data
    # Each traj: array of [lon, lat, time_seconds]
    compact_trajs = []
    for traj in trajectories[:8000]:  # Limit for browser perf
        path = traj.get("path", [])
        if len(path) >= 2:
            compact_trajs.append({
                "id": traj["agent_id"],
                "p": [[round(p[0], 4), round(p[1], 4), int(p[2])] for p in path],
            })

    # Build compact network for base layer
    net_features = []
    for feat in network.get("features", []):
        coords = feat["geometry"]["coordinates"]
        net_features.append(
            [[round(c[0], 4), round(c[1], 4)] for c in coords]
        )

    # Region centers for quick navigation
    regions = {
        "全国": [137.0, 38.0, 5],
        "札幌": [141.35, 43.06, 12],
        "仙台": [140.87, 38.27, 12],
        "関東": [139.70, 35.68, 10],
        "名古屋": [136.91, 35.18, 12],
        "関西": [135.50, 34.69, 10],
        "広島": [132.46, 34.39, 12],
        "松山": [132.77, 33.84, 12],
        "福岡": [130.40, 33.59, 12],
    }

    n_bins = len(timestamps) if timestamps else 1
    bin_sec = timestamps[1] - timestamps[0] if len(timestamps) > 1 else 300

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0a0a; color:#e0e0e0; font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif; }}
#map {{ width:100vw; height:100vh; }}
#controls {{
    position:absolute; bottom:20px; left:50%; transform:translateX(-50%);
    z-index:1000; background:rgba(10,10,10,0.92); backdrop-filter:blur(10px);
    padding:12px 24px; border-radius:12px; border:1px solid rgba(255,255,255,0.1);
    display:flex; align-items:center; gap:12px; min-width:500px;
}}
#stats {{
    position:absolute; top:12px; right:12px; z-index:1000;
    background:rgba(10,10,10,0.92); backdrop-filter:blur(10px);
    padding:14px 18px; border-radius:12px; border:1px solid rgba(255,255,255,0.1);
    font-size:13px; min-width:180px;
}}
#title-bar {{
    position:absolute; top:12px; left:12px; z-index:1000;
    background:rgba(10,10,10,0.92); backdrop-filter:blur(10px);
    padding:10px 16px; border-radius:12px; border:1px solid rgba(255,255,255,0.1);
}}
#title-bar h1 {{ font-size:16px; font-weight:600; }}
#title-bar .sub {{ font-size:11px; color:#888; }}
#regions {{
    position:absolute; top:80px; left:12px; z-index:1000;
    background:rgba(10,10,10,0.92); backdrop-filter:blur(10px);
    padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.1);
}}
#regions select {{ background:#1a1a1a; color:#fff; border:1px solid #333; padding:4px 8px; border-radius:4px; font-size:12px; }}
.btn {{ background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); color:#fff;
    padding:6px 14px; border-radius:6px; cursor:pointer; font-size:13px; }}
.btn:hover {{ background:rgba(255,255,255,0.2); }}
.btn.active {{ background:rgba(0,255,136,0.25); border-color:#00ff88; }}
#time-display {{ font-size:22px; font-weight:700; color:#00ff88; font-variant-numeric:tabular-nums; min-width:60px; }}
#slider {{ flex:1; accent-color:#00ff88; }}
.stat-val {{ font-size:18px; font-weight:700; color:#00ff88; }}
.stat-lbl {{ font-size:10px; color:#888; text-transform:uppercase; }}
#speed-lbl {{ color:#00ff88; font-size:13px; font-weight:600; min-width:32px; text-align:center; }}
#legend {{
    position:absolute; bottom:90px; right:12px; z-index:1000;
    background:rgba(10,10,10,0.92); backdrop-filter:blur(10px);
    padding:10px 14px; border-radius:8px; border:1px solid rgba(255,255,255,0.1);
    font-size:11px; width:120px;
}}
.legend-bar {{ height:8px; border-radius:4px; background:linear-gradient(to right,#00ff88,#ffaa00,#ff4444); margin:4px 0; }}
.legend-labels {{ display:flex; justify-content:space-between; color:#666; font-size:9px; }}
</style>
</head>
<body>
<div id="map"></div>

<div id="title-bar">
    <h1>MATSim Japan Traffic</h1>
    <div class="sub">Multi-Agent Simulation — 9 Metro Areas</div>
</div>

<div id="regions">
    <select id="region-sel" onchange="jumpRegion(this.value)">
        {"".join(f'<option value="{k}">{k}</option>' for k in regions.keys())}
    </select>
</div>

<div id="stats">
    <div><span class="stat-lbl">時刻</span><br><span class="stat-val" id="s-time">--:--</span></div>
    <div style="margin-top:8px"><span class="stat-lbl">走行車両</span><br><span class="stat-val" id="s-vehicles">0</span></div>
    <div style="margin-top:8px"><span class="stat-lbl">リンク交通量</span><br><span class="stat-val" id="s-links">0</span></div>
</div>

<div id="controls">
    <button class="btn" id="btn-play" onclick="togglePlay()">▶</button>
    <button class="btn" onclick="changeSpeed(-1)">◀◀</button>
    <span id="speed-lbl">1x</span>
    <button class="btn" onclick="changeSpeed(1)">▶▶</button>
    <span id="time-display">07:00</span>
    <input type="range" id="slider" min="0" max="{n_bins - 1}" value="0" oninput="seekTo(+this.value)">
</div>

<div id="legend">
    <div style="color:#aaa">交通量</div>
    <div class="legend-bar"></div>
    <div class="legend-labels"><span>低</span><span>中</span><span>高</span></div>
</div>

<script>
const LINKS = {json.dumps(compact_links, separators=(',',':'))};
const TRAJS = {json.dumps(compact_trajs, separators=(',',':'))};
const NET = {json.dumps(net_features[:20000], separators=(',',':'))};
const REGIONS = {json.dumps({k: v for k, v in regions.items()})};
const N_BINS = {n_bins};
const BIN_SEC = {bin_sec};

let map = L.map('map', {{
    center: [38.0, 137.0],
    zoom: 5,
    preferCanvas: true,
    zoomControl: false,
}});

L.control.zoom({{ position: 'bottomright' }}).addTo(map);

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}@2x.png', {{
    attribution: '&copy; OSM contributors &copy; CARTO',
    maxZoom: 18,
}}).addTo(map);

// Network base layer
let netLayer = L.layerGroup();
for (let seg of NET) {{
    L.polyline(seg.map(c => [c[1], c[0]]), {{
        color: '#1a2a3a', weight: 1, opacity: 0.4,
    }}).addTo(netLayer);
}}
netLayer.addTo(map);

// Link congestion layer
let linkLines = [];
for (let link of LINKS) {{
    let line = L.polyline(link.c.map(c => [c[1], c[0]]), {{
        color: '#00ff88', weight: 2, opacity: 0,
    }}).addTo(map);
    linkLines.push({{ line, counts: link.v }});
}}

// Agent dots layer
let agentMarkers = L.layerGroup().addTo(map);

// State
let currentBin = 0;
let playing = false;
let speed = 1;
let speeds = [0.5, 1, 2, 5, 10, 20];
let speedIdx = 1;
let lastFrame = 0;

function congestionColor(ratio) {{
    if (ratio < 0.33) {{
        let t = ratio * 3;
        return `rgb(${{Math.floor(t*255)}},${{255}},${{Math.floor((1-t)*136)}})`;
    }} else if (ratio < 0.66) {{
        let t = (ratio - 0.33) * 3;
        return `rgb(255,${{Math.floor((1-t)*170+t*100)}},0)`;
    }} else {{
        let t = (ratio - 0.66) * 3;
        return `rgb(255,${{Math.floor((1-t)*100)}},0)`;
    }}
}}

function updateFrame() {{
    let maxCount = 1;
    for (let ll of linkLines) {{
        let c = ll.counts[currentBin] || 0;
        if (c > maxCount) maxCount = c;
    }}

    let activeLinks = 0;
    for (let ll of linkLines) {{
        let c = ll.counts[currentBin] || 0;
        if (c > 0) {{
            let ratio = c / maxCount;
            ll.line.setStyle({{ color: congestionColor(ratio), weight: 2 + ratio * 4, opacity: 0.7 }});
            activeLinks++;
        }} else {{
            ll.line.setStyle({{ opacity: 0 }});
        }}
    }}

    // Agent positions
    agentMarkers.clearLayers();
    let simTime = currentBin * BIN_SEC;
    let agentCount = 0;
    for (let traj of TRAJS) {{
        let path = traj.p;
        if (path.length < 2) continue;
        if (simTime < path[0][2] || simTime > path[path.length-1][2]) continue;

        // Find segment
        let si = 0;
        for (let i = 0; i < path.length - 1; i++) {{
            if (path[i][2] <= simTime && path[i+1][2] >= simTime) {{ si = i; break; }}
        }}
        let a = path[si], b = path[Math.min(si+1, path.length-1)];
        let dt = b[2] - a[2];
        let t = dt > 0 ? (simTime - a[2]) / dt : 0;
        let lon = a[0] + (b[0] - a[0]) * t;
        let lat = a[1] + (b[1] - a[1]) * t;

        L.circleMarker([lat, lon], {{
            radius: 3, fillColor: '#00ffaa', fillOpacity: 0.8,
            stroke: false,
        }}).addTo(agentMarkers);
        agentCount++;
    }}

    // Update UI
    let totalSec = currentBin * BIN_SEC;
    let h = Math.floor(totalSec / 3600);
    let m = Math.floor((totalSec % 3600) / 60);
    document.getElementById('time-display').textContent = `${{String(h).padStart(2,'0')}}:${{String(m).padStart(2,'0')}}`;
    document.getElementById('s-time').textContent = `${{String(h).padStart(2,'0')}}:${{String(m).padStart(2,'0')}}`;
    document.getElementById('s-vehicles').textContent = agentCount.toLocaleString();
    document.getElementById('s-links').textContent = activeLinks.toLocaleString();
    document.getElementById('slider').value = currentBin;
}}

function animate(ts) {{
    if (!playing) return;
    if (ts - lastFrame > 100 / speed) {{
        lastFrame = ts;
        currentBin = (currentBin + 1) % N_BINS;
        updateFrame();
    }}
    requestAnimationFrame(animate);
}}

function togglePlay() {{
    playing = !playing;
    document.getElementById('btn-play').textContent = playing ? '⏸' : '▶';
    document.getElementById('btn-play').classList.toggle('active', playing);
    if (playing) {{ lastFrame = performance.now(); requestAnimationFrame(animate); }}
}}

function changeSpeed(d) {{
    speedIdx = Math.max(0, Math.min(speeds.length-1, speedIdx + d));
    speed = speeds[speedIdx];
    document.getElementById('speed-lbl').textContent = speed + 'x';
}}

function seekTo(bin) {{
    currentBin = bin;
    updateFrame();
}}

function jumpRegion(name) {{
    let r = REGIONS[name];
    if (r) map.setView([r[1], r[0]], r[2], {{ animate: true }});
}}

// Init: seek to 7AM
currentBin = Math.floor(25200 / BIN_SEC);
updateFrame();
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    size_mb = output_path.stat().st_size / 1e6
    print(f"Wrote {output_path} ({size_mb:.1f} MB)")
    print(f"  Links: {len(compact_links)}, Trajectories: {len(compact_trajs)}, Network: {len(net_features)}")


def main():
    parser = argparse.ArgumentParser(description="MATSim animated map")
    parser.add_argument("--data-dir", type=Path,
                        default=Path(__file__).parent.parent / "web" / "data",
                        help="Directory with trajectories.json, link_counts.json, network.geojson")
    parser.add_argument("--output", type=Path,
                        default=OUTPUT_DIR / "japan_matsim_animated.html")
    args = parser.parse_args()

    data_dir = args.data_dir

    print(f"Loading data from {data_dir}...")
    with open(data_dir / "trajectories.json") as f:
        trajectories = json.load(f)
    with open(data_dir / "link_counts.json") as f:
        link_counts = json.load(f)
    with open(data_dir / "network.geojson") as f:
        network = json.load(f)

    print(f"  Trajectories: {len(trajectories)}")
    print(f"  Links: {len(link_counts.get('links', {}))}")
    print(f"  Network features: {len(network.get('features', []))}")

    build_animated_html(trajectories, link_counts, network, args.output)


if __name__ == "__main__":
    main()
