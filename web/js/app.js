/**
 * Main application controller for Japan Traffic SimCity.
 */

const REGION_VIEWS = {
    japan:    { center: [137.0, 38.0], zoom: 5 },
    kanto:    { center: [139.7, 35.7], zoom: 9 },
    kansai:   { center: [135.5, 34.7], zoom: 9 },
    chubu:    { center: [137.0, 35.5], zoom: 8 },
    hokkaido: { center: [143.0, 43.0], zoom: 7 },
    tohoku:   { center: [140.5, 39.0], zoom: 7 },
    chugoku:  { center: [132.5, 34.5], zoom: 8 },
    shikoku:  { center: [133.5, 33.8], zoom: 8 },
    kyushu:   { center: [131.0, 33.0], zoom: 7 },
};

class App {
    constructor() {
        this.dataLoader = new DataLoader('data');
        this.timeline = null;
        this.layerManager = null;
        this.statsPanel = null;
        this.deckgl = null;

        this._init();
    }

    async _init() {
        // Initialize deck.gl with MapLibre base map
        this.deckgl = new deck.DeckGL({
            container: 'map-container',
            mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
            initialViewState: {
                ...REGION_VIEWS.kanto,
                pitch: 45,
                bearing: -15,
                maxPitch: 60,
            },
            controller: true,
            layers: [],
            getTooltip: ({ object }) => {
                if (object && object.agent_id) {
                    return `車両 ${object.agent_id}`;
                }
                return null;
            },
        });

        // Initialize components
        this.timeline = new Timeline();
        this.layerManager = new LayerManager(this.deckgl);
        this.statsPanel = new StatsPanel();

        // Load data
        await this.dataLoader.loadAll((msg) => {
            document.getElementById('loading-text').textContent = msg;
        });

        // Set network data
        this.layerManager.setNetworkData(this.dataLoader.networkGeoJson);

        // Hide loading overlay
        document.getElementById('loading-overlay').classList.add('hidden');

        // Connect timeline to rendering
        this.timeline.onChange((time) => this._onTimeUpdate(time));

        // Initial render
        this._onTimeUpdate(this.timeline.currentTime);

        // Region selector
        document.getElementById('region-select').addEventListener('change', (e) => {
            const view = REGION_VIEWS[e.target.value];
            if (view) {
                this.deckgl.setProps({
                    initialViewState: {
                        ...view,
                        pitch: 45,
                        bearing: -15,
                        transitionDuration: 1000,
                    },
                });
            }
        });

        // Auto-play
        this.timeline.togglePlay();
    }

    _onTimeUpdate(currentTime) {
        // Get active agents at current time
        const agents = this.dataLoader.getActiveAgents(currentTime);
        this.layerManager.setAgentData(agents);

        // Get congestion data
        const congestion = this.dataLoader.getLinkCongestion(currentTime);
        this.layerManager.setCongestionData(congestion);

        // Update layers
        this.layerManager.updateLayers();

        // Update stats
        this.statsPanel.update(currentTime, agents, congestion);
    }
}

// Start the app
window.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});
