/**
 * deck.gl layer management for SimCity visualization.
 */
class LayerManager {
    constructor(deckgl) {
        this.deckgl = deckgl;
        this.visibility = {
            trips: true,
            network: true,
            signals: false,
            heatmap: false,
        };
        this.agentData = [];
        this.networkData = null;
        this.congestionData = {};

        this._initToggles();
    }

    _initToggles() {
        const toggles = {
            'layer-trips': 'trips',
            'layer-network': 'network',
            'layer-signals': 'signals',
            'layer-heatmap': 'heatmap',
        };

        for (const [id, key] of Object.entries(toggles)) {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', (e) => {
                    this.visibility[key] = e.target.checked;
                    this.updateLayers();
                });
            }
        }
    }

    setAgentData(agents) {
        this.agentData = agents;
    }

    setNetworkData(geojson) {
        this.networkData = geojson;
    }

    setCongestionData(congestion) {
        this.congestionData = congestion;
    }

    updateLayers() {
        const layers = [];

        // Network layer (road lines)
        if (this.visibility.network && this.networkData) {
            layers.push(new deck.GeoJsonLayer({
                id: 'network-layer',
                data: this.networkData,
                stroked: true,
                filled: false,
                lineWidthMinPixels: 1,
                lineWidthMaxPixels: 3,
                getLineColor: [60, 60, 80, 120],
                getLineWidth: 1,
            }));
        }

        // Congestion overlay (colored road segments)
        if (this.visibility.network && Object.keys(this.congestionData).length > 0) {
            const congestionLines = Object.entries(this.congestionData)
                .filter(([, d]) => d.coords && d.count > 0)
                .map(([linkId, d]) => ({
                    path: d.coords,
                    ratio: d.ratio,
                    count: d.count,
                }));

            if (congestionLines.length > 0) {
                layers.push(new deck.PathLayer({
                    id: 'congestion-layer',
                    data: congestionLines,
                    getPath: d => d.path,
                    getColor: d => this._congestionColor(d.ratio),
                    getWidth: d => 2 + d.ratio * 6,
                    widthMinPixels: 1,
                    widthMaxPixels: 8,
                    opacity: 0.7,
                }));
            }
        }

        // Agent dots (vehicles)
        if (this.visibility.trips && this.agentData.length > 0) {
            layers.push(new deck.ScatterplotLayer({
                id: 'agents-layer',
                data: this.agentData,
                getPosition: d => d.position,
                getRadius: 30,
                radiusMinPixels: 2,
                radiusMaxPixels: 6,
                getFillColor: d => this._agentColor(d.progress),
                opacity: 0.9,
                updateTriggers: {
                    getPosition: [this.agentData.length],
                },
            }));
        }

        // Heatmap layer
        if (this.visibility.heatmap && this.agentData.length > 0) {
            layers.push(new deck.HeatmapLayer({
                id: 'heatmap-layer',
                data: this.agentData,
                getPosition: d => d.position,
                getWeight: 1,
                radiusPixels: 30,
                intensity: 1,
                threshold: 0.05,
                colorRange: [
                    [0, 255, 136, 25],
                    [0, 255, 136, 80],
                    [255, 170, 0, 150],
                    [255, 68, 68, 200],
                    [255, 0, 0, 255],
                ],
            }));
        }

        this.deckgl.setProps({ layers });
    }

    _congestionColor(ratio) {
        // Green → Yellow → Red
        if (ratio < 0.5) {
            const t = ratio * 2;
            return [
                Math.floor(t * 255),
                255,
                Math.floor((1 - t) * 136),
                200,
            ];
        } else {
            const t = (ratio - 0.5) * 2;
            return [
                255,
                Math.floor((1 - t) * 170),
                0,
                220,
            ];
        }
    }

    _agentColor(progress) {
        // Cyan to green based on trip progress
        return [0, 200 + Math.floor(progress * 55), 136 - Math.floor(progress * 50), 230];
    }
}

window.LayerManager = LayerManager;
