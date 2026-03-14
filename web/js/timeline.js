/**
 * Timeline controller for simulation playback.
 */
class Timeline {
    constructor() {
        this.currentTime = 25200; // 7:00 AM
        this.playing = false;
        this.speed = 1; // multiplier
        this.speedOptions = [0.5, 1, 2, 5, 10, 30, 60];
        this.speedIndex = 1;
        this.lastFrameTime = null;
        this.callbacks = [];

        this._initUI();
    }

    _initUI() {
        this.slider = document.getElementById('timeline-slider');
        this.playBtn = document.getElementById('btn-play');
        this.speedDownBtn = document.getElementById('btn-speed-down');
        this.speedUpBtn = document.getElementById('btn-speed-up');
        this.speedDisplay = document.getElementById('speed-display');

        this.slider.addEventListener('input', (e) => {
            this.currentTime = parseInt(e.target.value);
            this._notifyCallbacks();
        });

        this.playBtn.addEventListener('click', () => this.togglePlay());
        this.speedDownBtn.addEventListener('click', () => this.changeSpeed(-1));
        this.speedUpBtn.addEventListener('click', () => this.changeSpeed(1));

        this._updateUI();
    }

    onChange(callback) {
        this.callbacks.push(callback);
    }

    _notifyCallbacks() {
        for (const cb of this.callbacks) {
            cb(this.currentTime);
        }
    }

    togglePlay() {
        this.playing = !this.playing;
        if (this.playing) {
            this.lastFrameTime = performance.now();
            this._animate();
        }
        this._updateUI();
    }

    changeSpeed(delta) {
        this.speedIndex = Math.max(0, Math.min(
            this.speedOptions.length - 1,
            this.speedIndex + delta
        ));
        this.speed = this.speedOptions[this.speedIndex];
        this._updateUI();
    }

    _animate() {
        if (!this.playing) return;

        const now = performance.now();
        const dt = (now - this.lastFrameTime) / 1000; // seconds
        this.lastFrameTime = now;

        this.currentTime += dt * this.speed * 60; // speed * 60 = sim seconds per real second

        if (this.currentTime > 86400) {
            this.currentTime = 0;
        }

        this.slider.value = Math.floor(this.currentTime);
        this._notifyCallbacks();

        requestAnimationFrame(() => this._animate());
    }

    _updateUI() {
        this.playBtn.textContent = this.playing ? '⏸' : '▶';
        this.playBtn.classList.toggle('active', this.playing);
        this.speedDisplay.textContent = `${this.speed}x`;
    }

    static formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }
}

window.Timeline = Timeline;
