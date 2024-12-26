// Configuration and Constants
const CONFIG = {
    REFRESH_INTERVAL: 5000,
    STATS_UPDATE_INTERVAL: 300000, // 5 minutes
    CHART_ANIMATION_DURATION: 750,
    MAX_RETRY_ATTEMPTS: 3,
    RETRY_DELAY: 2000,
};

// Main Dashboard Class
class Dashboard {
    constructor() {
        this.charts = {};
        this.counters = {};
        this.errorStates = {};
        this.initialize();
    }

    initialize() {
        this.setupEventListeners();
        this.initializeCharts();
        this.startPolling();
    }

    setupEventListeners() {
        document.addEventListener('DOMContentLoaded', () => {
            this.setupCameraFeeds();
            this.setupChartControls();
        });

        // Handle visibility change to pause/resume polling
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pausePolling();
            } else {
                this.resumePolling();
            }
        });
    }

    setupCameraFeeds() {
        const cameraFeeds = document.querySelectorAll('.camera-feed');
        cameraFeeds.forEach(feed => {
            const cameraId = feed.dataset.cameraId;
            this.initializeCameraCounter(cameraId);
        });
    }

    initializeCameraCounter(cameraId) {
        const counterElement = document.querySelector(`#counter-${cameraId}`);
        if (counterElement) {
            this.counters[cameraId] = {
                element: counterElement,
                value: 0,
                retryCount: 0
            };
            this.updateCounter(cameraId);
        }
    }

    setupChartControls() {
        const chartControls = document.querySelectorAll('.chart-control');
        chartControls.forEach(control => {
            control.addEventListener('change', (e) => {
                const branchId = e.target.dataset.branchId;
                const chartType = e.target.value;
                this.updateChartType(branchId, chartType);
            });
        });
    }

    // Polling and Updates
    startPolling() {
        this.pollCounters();
        this.pollStats();
    }

    pausePolling() {
        clearTimeout(this.counterPollTimeout);
        clearTimeout(this.statsPollTimeout);
    }

    resumePolling() {
        this.startPolling();
    }

    async pollCounters() {
        for (const cameraId in this.counters) {
            await this.updateCounter(cameraId);
        }
        this.counterPollTimeout = setTimeout(() => this.pollCounters(), CONFIG.REFRESH_INTERVAL);
    }

    async pollStats() {
        await this.updateAllStats();
        this.statsPollTimeout = setTimeout(() => this.pollStats(), CONFIG.STATS_UPDATE_INTERVAL);
    }

    // Counter Updates
    async updateCounter(cameraId) {
        try {
            const response = await fetch(`/camera-stats/${cameraId}/`);
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            this.updateCounterDisplay(cameraId, data);
            this.resetErrorState(cameraId);
        } catch (error) {
            this.handleError(cameraId, error);
        }
    }

    updateCounterDisplay(cameraId, data) {
        const counter = this.counters[cameraId];
        if (counter && counter.element) {
            const oldValue = counter.value;
            const newValue = data.current_count;
            
            this.animateCounterValue(counter.element, oldValue, newValue);
            counter.value = newValue;
            
            // Update additional stats if available
            this.updateAdditionalStats(cameraId, data);
        }
    }

    animateCounterValue(element, start, end) {
        const duration = 1000;
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const value = Math.floor(start + (end - start) * progress);
            element.textContent = `${value} people`;
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }

    updateAdditionalStats(cameraId, data) {
        const hourTotal = document.querySelector(`#hour-total-${cameraId}`);
        const dailyTotal = document.querySelector(`#daily-total-${cameraId}`);
        
        if (hourTotal) hourTotal.textContent = data.hour_total;
        if (dailyTotal) dailyTotal.textContent = data.daily_total;
    }

    // Chart Management
    initializeCharts() {
        const chartContainers = document.querySelectorAll('.chart-container');
        chartContainers.forEach(container => {
            const branchId = container.dataset.branchId;
            this.initializeChart(branchId, container);
        });
    }

    initializeChart(branchId, container) {
        const config = this.getDefaultChartConfig();
        this.charts[branchId] = new Plotly.newPlot(container, config.data, config.layout);
    }

    getDefaultChartConfig() {
        return {
            data: [{
                x: [],
                y: [],
                type: 'line',
                mode: 'lines+markers',
                line: {
                    color: '#4299e1',
                    width: 2
                },
                marker: {
                    color: '#2b6cb0',
                    size: 6
                }
            }],
            layout: {
                autosize: true,
                margin: { t: 30, r: 20, b: 40, l: 40 },
                showlegend: false,
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                xaxis: {
                    showgrid: true,
                    gridcolor: '#edf2f7'
                },
                yaxis: {
                    showgrid: true,
                    gridcolor: '#edf2f7'
                }
            }
        };
    }

    async updateAllStats() {
        const branches = document.querySelectorAll('[data-branch-id]');
        for (const branch of branches) {
            const branchId = branch.dataset.branchId;
            await this.updateBranchStats(branchId);
        }
    }

    async updateBranchStats(branchId) {
        try {
            const response = await fetch(`/stats/${branchId}/`);
            if (!response.ok) throw new Error('Failed to fetch branch stats');
            
            const data = await response.json();
            this.updateCharts(branchId, data);
            this.updateSummaryStats(branchId, data);
        } catch (error) {
            console.error(`Error updating branch ${branchId} stats:`, error);
            this.showError(branchId, 'Failed to update statistics');
        }
    }

    updateCharts(branchId, data) {
        const dailyChart = document.querySelector(`#daily-chart-${branchId}`);
        const hourlyChart = document.querySelector(`#hourly-chart-${branchId}`);

        if (dailyChart) {
            const dailyData = JSON.parse(data.daily_chart);
            Plotly.react(dailyChart, dailyData.data, dailyData.layout);
        }

        if (hourlyChart) {
            const hourlyData = JSON.parse(data.hourly_chart);
            Plotly.react(hourlyChart, hourlyData.data, hourlyData.layout);
        }
    }

    updateSummaryStats(branchId, data) {
        const summaryElements = {
            total: document.querySelector(`#total-count-${branchId}`),
            peak: document.querySelector(`#peak-count-${branchId}`),
            average: document.querySelector(`#average-count-${branchId}`)
        };

        if (summaryElements.total) summaryElements.total.textContent = data.total_count;
        if (summaryElements.peak) summaryElements.peak.textContent = data.peak_count;
        if (summaryElements.average) summaryElements.average.textContent = data.average_count;
    }

    // Error Handling
    handleError(cameraId, error) {
        console.error(`Error updating camera ${cameraId}:`, error);
        
        const counter = this.counters[cameraId];
        if (counter) {
            counter.retryCount++;
            
            if (counter.retryCount <= CONFIG.MAX_RETRY_ATTEMPTS) {
                setTimeout(() => this.updateCounter(cameraId), CONFIG.RETRY_DELAY);
            } else {
                this.showError(cameraId, 'Camera feed unavailable');
            }
        }
    }

    showError(id, message) {
        const errorElement = document.querySelector(`#error-${id}`);
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.classList.remove('hidden');
        }
    }

    resetErrorState(id) {
        const counter = this.counters[id];
        if (counter) {
            counter.retryCount = 0;
            
            const errorElement = document.querySelector(`#error-${id}`);
            if (errorElement) {
                errorElement.classList.add('hidden');
            }
        }
    }
}

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});

// Utility Functions
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

function formatDate(date) {
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    }).format(new Date(date));
}

function formatTime(time) {
    return new Intl.DateTimeFormat('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    }).format(new Date(time));
}

// Export Dashboard class if using modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Dashboard;
}

function updateStats() {
    $.get('/camera-stats/', { url: streamUrl }, function(data) {
        // Update real-time counts
        $('#currentCount').text(data.current_count || 0);
        $('#inCount').text(data.in_count || 0);
        $('#outCount').text(data.out_count || 0);
        
        // Update hourly and daily stats
        $('#hourlyTotal').text(data.hourly_total || 0);
        $('#dailyTotal').text(data.daily_total || 0);
        
        // Update chart
        updateCharts(data);
    });
}
