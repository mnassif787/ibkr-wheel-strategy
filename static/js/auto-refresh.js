/**
 * Centralized Auto-Refresh Component
 * Provides consistent auto-refresh functionality across all pages
 */

class AutoRefresh {
    constructor(refreshCallback, options = {}) {
        this.refreshCallback = refreshCallback;
        this.interval = options.interval || 30000; // Default 30 seconds
        this.enabledByDefault = options.enabledByDefault || false;
        this.storageKey = options.storageKey || 'autoRefresh';
        this.intervalId = null;
        this.isEnabled = false;
        
        // Restore saved state from localStorage
        this.loadState();
        
        // Initialize if enabled by default or from saved state
        if (this.isEnabled) {
            this.start();
        }
    }
    
    /**
     * Load saved state from localStorage
     */
    loadState() {
        try {
            const saved = localStorage.getItem(this.storageKey);
            if (saved !== null) {
                this.isEnabled = saved === 'true';
            } else {
                this.isEnabled = this.enabledByDefault;
            }
        } catch (e) {
            this.isEnabled = this.enabledByDefault;
        }
    }
    
    /**
     * Save state to localStorage
     */
    saveState() {
        try {
            localStorage.setItem(this.storageKey, this.isEnabled.toString());
        } catch (e) {
            console.warn('Could not save auto-refresh state:', e);
        }
    }
    
    /**
     * Start auto-refresh
     */
    start() {
        if (this.intervalId) {
            this.stop();
        }
        
        this.isEnabled = true;
        this.intervalId = setInterval(() => {
            if (this.refreshCallback) {
                this.refreshCallback();
            }
        }, this.interval);
        
        this.saveState();
        console.log(`Auto-refresh started (interval: ${this.interval}ms)`);
    }
    
    /**
     * Stop auto-refresh
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        
        this.isEnabled = false;
        this.saveState();
        console.log('Auto-refresh stopped');
    }
    
    /**
     * Toggle auto-refresh on/off
     */
    toggle() {
        if (this.isEnabled) {
            this.stop();
        } else {
            this.start();
        }
        return this.isEnabled;
    }
    
    /**
     * Check if auto-refresh is currently enabled
     */
    isActive() {
        return this.isEnabled && this.intervalId !== null;
    }
    
    /**
     * Update the refresh interval
     */
    setInterval(newInterval) {
        this.interval = newInterval;
        if (this.isActive()) {
            this.start(); // Restart with new interval
        }
    }
}

/**
 * Create a toggle button UI component for auto-refresh
 * @param {AutoRefresh} autoRefresh - AutoRefresh instance
 * @param {string} containerId - ID of the container element
 * @param {Object} options - UI options
 */
function createAutoRefreshToggle(autoRefresh, containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn(`Container ${containerId} not found`);
        return;
    }
    
    const label = options.label || 'Auto-Refresh';
    const icon = options.icon || '🔄';
    
    const html = `
        <div class="flex items-center space-x-2">
            <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" 
                       id="autoRefreshCheckbox" 
                       class="sr-only peer"
                       ${autoRefresh.isEnabled ? 'checked' : ''}>
                <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                <span class="ms-3 text-sm font-medium text-gray-900">${icon} ${label}</span>
            </label>
            <span id="autoRefreshStatus" class="text-xs text-gray-500">
                ${autoRefresh.isEnabled ? 'Every ' + (autoRefresh.interval / 1000) + 's' : 'Off'}
            </span>
        </div>
    `;
    
    container.innerHTML = html;
    
    // Add event listener
    const checkbox = document.getElementById('autoRefreshCheckbox');
    const status = document.getElementById('autoRefreshStatus');
    
    checkbox.addEventListener('change', function() {
        const isEnabled = autoRefresh.toggle();
        status.textContent = isEnabled ? `Every ${autoRefresh.interval / 1000}s` : 'Off';
    });
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AutoRefresh, createAutoRefreshToggle };
}
