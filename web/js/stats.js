/**
 * Real-time statistics panel.
 */
class StatsPanel {
    constructor() {
        this.timeEl = document.getElementById('current-time');
        this.vehiclesEl = document.getElementById('active-vehicles');
        this.speedEl = document.getElementById('avg-speed');
        this.congestionEl = document.getElementById('congestion-index');
    }

    update(currentTime, activeAgents, congestionData) {
        // Time
        this.timeEl.textContent = Timeline.formatTime(currentTime);

        // Active vehicles
        const count = activeAgents ? activeAgents.length : 0;
        this.vehiclesEl.textContent = count.toLocaleString();

        // Congestion index
        if (congestionData && Object.keys(congestionData).length > 0) {
            const ratios = Object.values(congestionData)
                .filter(d => d.count > 0)
                .map(d => d.ratio);
            if (ratios.length > 0) {
                const avgCongestion = ratios.reduce((a, b) => a + b, 0) / ratios.length;
                this.congestionEl.textContent = (avgCongestion * 100).toFixed(1) + '%';

                // Color code
                if (avgCongestion < 0.3) {
                    this.congestionEl.style.color = '#00ff88';
                } else if (avgCongestion < 0.6) {
                    this.congestionEl.style.color = '#ffaa00';
                } else {
                    this.congestionEl.style.color = '#ff4444';
                }
            }
        }

        // Average speed estimation (simplified)
        if (count > 0) {
            // Estimate based on congestion level
            const freeFlowSpeed = 60; // km/h
            const congValues = Object.values(congestionData).filter(d => d.count > 0);
            if (congValues.length > 0) {
                const avgRatio = congValues.reduce((a, b) => a + b.ratio, 0) / congValues.length;
                const estSpeed = Math.max(5, freeFlowSpeed * (1 - avgRatio * 0.8));
                this.speedEl.textContent = estSpeed.toFixed(0) + ' km/h';
            }
        } else {
            this.speedEl.textContent = '-- km/h';
        }
    }
}

window.StatsPanel = StatsPanel;
