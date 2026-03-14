/**
 * Data loader for MATSim simulation output.
 * Fetches trajectories, link counts, and network GeoJSON.
 */
class DataLoader {
    constructor(dataDir = 'data') {
        this.dataDir = dataDir;
        this.trajectories = null;
        this.linkCounts = null;
        this.networkGeoJson = null;
        this.loaded = false;
    }

    async loadAll(onProgress) {
        const files = [
            { key: 'trajectories', file: 'trajectories.json' },
            { key: 'linkCounts', file: 'link_counts.json' },
            { key: 'networkGeoJson', file: 'network.geojson' },
        ];

        for (let i = 0; i < files.length; i++) {
            const { key, file } = files[i];
            const url = `${this.dataDir}/${file}`;
            if (onProgress) {
                onProgress(`${file} を読み込み中... (${i + 1}/${files.length})`);
            }
            try {
                const response = await fetch(url);
                if (response.ok) {
                    this[key] = await response.json();
                } else {
                    console.warn(`Failed to load ${url}: ${response.status}`);
                    this[key] = this._getDefault(key);
                }
            } catch (e) {
                console.warn(`Error loading ${url}:`, e);
                this[key] = this._getDefault(key);
            }
        }

        this.loaded = true;
        return this;
    }

    _getDefault(key) {
        switch (key) {
            case 'trajectories': return [];
            case 'linkCounts': return { timestamps: [], links: {} };
            case 'networkGeoJson': return { type: 'FeatureCollection', features: [] };
            default: return null;
        }
    }

    /**
     * Get active trajectories at a given time.
     * Returns array of { agent_id, position: [lon, lat], progress }
     */
    getActiveAgents(currentTime) {
        if (!this.trajectories) return [];

        const agents = [];
        for (const traj of this.trajectories) {
            const path = traj.path;
            if (!path || path.length < 2) continue;

            const startTime = path[0][2];
            const endTime = path[path.length - 1][2];

            if (currentTime < startTime || currentTime > endTime) continue;

            // Find current segment
            let segIdx = 0;
            for (let i = 0; i < path.length - 1; i++) {
                if (path[i][2] <= currentTime && path[i + 1][2] >= currentTime) {
                    segIdx = i;
                    break;
                }
            }

            const seg = path[segIdx];
            const nextSeg = path[Math.min(segIdx + 1, path.length - 1)];
            const segDuration = nextSeg[2] - seg[2];
            const t = segDuration > 0 ? (currentTime - seg[2]) / segDuration : 0;

            agents.push({
                agent_id: traj.agent_id,
                position: [
                    seg[0] + (nextSeg[0] - seg[0]) * t,
                    seg[1] + (nextSeg[1] - seg[1]) * t,
                ],
                progress: (currentTime - startTime) / (endTime - startTime),
            });
        }

        return agents;
    }

    /**
     * Get link congestion at a given time.
     * Returns map of linkId -> congestion ratio (0-1).
     */
    getLinkCongestion(currentTime, timeBinSeconds = 300) {
        if (!this.linkCounts || !this.linkCounts.links) return {};

        const bin = Math.floor(currentTime / timeBinSeconds);
        const congestion = {};
        let maxCount = 1;

        // First pass: find max count
        for (const [linkId, data] of Object.entries(this.linkCounts.links)) {
            const count = (data.counts && data.counts[bin]) || 0;
            if (count > maxCount) maxCount = count;
        }

        // Second pass: normalize
        for (const [linkId, data] of Object.entries(this.linkCounts.links)) {
            const count = (data.counts && data.counts[bin]) || 0;
            congestion[linkId] = {
                ratio: count / maxCount,
                count: count,
                coords: data.coords,
            };
        }

        return congestion;
    }
}

// Export
window.DataLoader = DataLoader;
