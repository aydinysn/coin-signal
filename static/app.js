// Futures Intelligence Dashboard - Client-side JavaScript
// Real-time signal updates via WebSocket with filtering and search

let socket;
let allSignals = [];
let currentFilter = 'all';
let isConnected = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeWebSocket();
    setupEventListeners();
    loadInitialSignals();
});

// WebSocket Connection
function initializeWebSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('✅ WebSocket connected');
        isConnected = true;
        updateConnectionStatus(true);
        socket.emit('request_signals');
    });

    socket.on('disconnect', () => {
        console.log('❌ WebSocket disconnected');
        isConnected = false;
        updateConnectionStatus(false);
    });

    socket.on('new_signal', (data) => {
        console.log('📊 New signal received:', data.signal);
        addNewSignal(data.signal);
        playNotificationSound();
    });

    socket.on('signals_data', (data) => {
        console.log(`📥 Received ${data.signals.length} signals`);
        allSignals = data.signals;
        renderSignals();
        updateStats(); // Update header statistics
    });
}

// Load initial signals via REST API
async function loadInitialSignals() {
    try {
        const response = await fetch('/api/signals');
        const data = await response.json();

        if (data.success) {
            allSignals = data.signals;
            renderSignals();
            updateStats();
        }
    } catch (error) {
        console.error('Error loading signals:', error);
    }
}

// Add new signal to the list
// Add new signal to the list
function addNewSignal(signal) {
    allSignals.unshift(signal); // Add to beginning

    renderSignals();
    updateStats();
}

// Render signals to DOM
function renderSignals() {
    const container = document.getElementById('signalsContainer');
    const emptyState = document.getElementById('emptyState');

    // Filter signals
    let filteredSignals = allSignals;

    // Apply direction filter
    if (currentFilter !== 'all') {
        filteredSignals = filteredSignals.filter(s => s.direction === currentFilter);
    }

    // Apply search filter
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    if (searchTerm) {
        filteredSignals = filteredSignals.filter(s =>
            s.coin.toLowerCase().includes(searchTerm)
        );
    }

    // Show/hide empty state
    if (filteredSignals.length === 0) {
        container.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    // Render signal cards
    container.innerHTML = filteredSignals.map(signal => createSignalCard(signal)).join('');
}

// Create HTML for a signal card
function createSignalCard(signal) {
    const directionClass = signal.direction === 'LONG' ? 'long' : 'short';
    const changeClass = signal.change_5m.startsWith('+') ? 'positive' : 'negative';
    const timestamp = formatTimestamp(signal.timestamp);

    return `
        <div class="signal-card ${directionClass}">
            <div class="signal-header">
                <div class="signal-coin">
                    #${signal.coin}
                    <span class="signal-emoji">${signal.emoji}</span>
                </div>
                <div class="signal-time">${timestamp}</div>
            </div>
            
            <div class="signal-data">
                <div class="signal-field">
                    <div class="signal-field-label">Price</div>
                    <div class="signal-field-value">$${formatNumber(signal.price)}</div>
                </div>
                
                <div class="signal-field">
                    <div class="signal-field-label">5m Change</div>
                    <div class="signal-field-value ${changeClass}">${signal.change_5m}</div>
                </div>
                
                <div class="signal-field">
                    <div class="signal-field-label">Volume</div>
                    <div class="signal-field-value">${signal.volume}</div>
                </div>
                
                <div class="signal-field">
                    <div class="signal-field-label">Volume Spike</div>
                    <div class="signal-field-value">${formatVolumeSpike(signal.volume_spike)}x</div>
                </div>
                
                <div class="signal-field">
                    <div class="signal-field-label">BB Target</div>
                    <div class="signal-field-value">${signal.bb_target.toFixed(4)}</div>
                </div>
                
                <div class="signal-field">
                    <div class="signal-field-label">Direction</div>
                    <div class="signal-field-value">${signal.direction}</div>
                </div>
            </div>
            
            <div class="signal-actions">
                <a href="${signal.tv_link}" target="_blank" class="signal-btn">
                    📊 TradingView
                </a>
                <a href="${signal.binance_link}" target="_blank" class="signal-btn">
                    💹 Binance
                </a>
            </div>
        </div>
    `;
}

// Update statistics in header
function updateStats() {
    const total = allSignals.length;
    const longCount = allSignals.filter(s => s.direction === 'LONG').length;
    const shortCount = allSignals.filter(s => s.direction === 'SHORT').length;

    document.getElementById('totalSignals').textContent = total;
    document.getElementById('longCount').textContent = longCount;
    document.getElementById('shortCount').textContent = shortCount;
}

// Update connection status indicator
function updateConnectionStatus(connected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');

    if (connected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Disconnected';
    }
}

// Setup event listeners
function setupEventListeners() {
    // Search input
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', debounce(renderSignals, 300));

    // Filter buttons
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update active state
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Apply filter
            currentFilter = btn.dataset.filter;
            renderSignals();
        });
    });
}

// Utility: Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Utility: Format timestamp
function formatTimestamp(isoString) {
    if (!isoString) return 'Unknown';

    try {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;

        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;

        return date.toLocaleDateString('tr-TR', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return 'Unknown';
    }
}

// Utility: Format number with commas (dynamic decimal places for small prices)
function formatNumber(num) {
    if (typeof num !== 'number') return num;

    // For large prices (>= $1): 2 decimals with commas
    if (num >= 1) {
        return num.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }
    // For medium prices ($0.01 - $1): 4 decimals
    else if (num >= 0.01) {
        return num.toFixed(4);
    }
    // For very small prices (< $0.01): up to 8 decimals, trim trailing zeros
    else {
        return num.toFixed(8).replace(/\.?0+$/, '');
    }
}

// Utility: Format volume spike (1 decimal place)
function formatVolumeSpike(spike) {
    if (typeof spike !== 'number') return spike;
    return spike.toFixed(1);
}

// Utility: Play notification sound (optional)
function playNotificationSound() {
    // You can add an audio element for notification sounds
    // For now, we'll use the browser's notification API
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('New Signal!', {
            body: 'A new trading signal has been detected.',
            icon: '📊'
        });
    }
}

// Auto-refresh fallback (in case WebSocket disconnects)
setInterval(() => {
    if (!isConnected) {
        console.log('⚠️ WebSocket disconnected, using REST API fallback');
        loadInitialSignals();
    }
}, 10000); // Every 10 seconds
