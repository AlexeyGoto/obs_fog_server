/**
 * OBS Fog Server - Main JavaScript
 */

// API Helper
const api = {
    async request(url, options = {}) {
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
        };

        const response = await fetch(url, { ...defaults, ...options });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || 'Request failed');
        }

        return response.json();
    },

    get(url) {
        return this.request(url);
    },

    post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    patch(url, data) {
        return this.request(url, {
            method: 'PATCH',
            body: JSON.stringify(data),
        });
    },

    delete(url) {
        return this.request(url, { method: 'DELETE' });
    },
};

// Notification System
const notifications = {
    show(message, type = 'info') {
        window.dispatchEvent(new CustomEvent('notify', {
            detail: { message, type }
        }));
    },

    success(message) {
        this.show(message, 'success');
    },

    error(message) {
        this.show(message, 'error');
    },

    warning(message) {
        this.show(message, 'warning');
    },

    info(message) {
        this.show(message, 'info');
    },
};

// Clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        notifications.success('Copied to clipboard!');
    } catch (err) {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        notifications.success('Copied to clipboard!');
    }
}

// Date formatting
function formatDate(dateString, options = {}) {
    const date = new Date(dateString);
    const defaults = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    };
    return date.toLocaleDateString('en-US', { ...defaults, ...options });
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHour < 24) return `${diffHour}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return formatDate(dateString, { year: 'numeric', month: 'short', day: 'numeric' });
}

// File size formatting
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Duration formatting
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    }
    if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
}

// Debounce
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

// Throttle
function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Modal helper
const modal = {
    open(id) {
        const el = document.getElementById(id);
        if (el) {
            el.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    },

    close(id) {
        const el = document.getElementById(id);
        if (el) {
            el.classList.add('hidden');
            document.body.style.overflow = '';
        }
    },
};

// Form validation
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;

    const inputs = form.querySelectorAll('[required]');
    let isValid = true;

    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('border-red-500');
            isValid = false;
        } else {
            input.classList.remove('border-red-500');
        }
    });

    return isValid;
}

// Loading state
function setLoading(buttonId, loading) {
    const button = document.getElementById(buttonId);
    if (!button) return;

    if (loading) {
        button.disabled = true;
        button.dataset.originalText = button.innerHTML;
        button.innerHTML = `
            <svg class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Loading...
        `;
    } else {
        button.disabled = false;
        if (button.dataset.originalText) {
            button.innerHTML = button.dataset.originalText;
        }
    }
}

// Confirm dialog
async function confirmAction(message, title = 'Confirm') {
    return new Promise(resolve => {
        const confirmed = window.confirm(message);
        resolve(confirmed);
    });
}

// Download file
function downloadFile(url, filename) {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || '';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Stream status checker
class StreamStatusChecker {
    constructor(pcId, callback, interval = 5000) {
        this.pcId = pcId;
        this.callback = callback;
        this.interval = interval;
        this.timer = null;
    }

    start() {
        this.check();
        this.timer = setInterval(() => this.check(), this.interval);
    }

    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    async check() {
        try {
            const data = await api.get(`/api/v1/pcs/${this.pcId}`);
            this.callback(data);
        } catch (err) {
            console.error('Failed to check stream status:', err);
        }
    }
}

// HLS Player helper (if video.js is included)
function initHLSPlayer(videoElementId, hlsUrl) {
    const video = document.getElementById(videoElementId);
    if (!video) return;

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
        // Native HLS support (Safari)
        video.src = hlsUrl;
    } else if (typeof Hls !== 'undefined' && Hls.isSupported()) {
        // hls.js
        const hls = new Hls();
        hls.loadSource(hlsUrl);
        hls.attachMedia(video);
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Auto-hide flash messages
    document.querySelectorAll('[data-auto-hide]').forEach(el => {
        const delay = parseInt(el.dataset.autoHide) || 5000;
        setTimeout(() => {
            el.style.transition = 'opacity 0.3s ease';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 300);
        }, delay);
    });

    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape to close modals
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal:not(.hidden)').forEach(modal => {
                modal.classList.add('hidden');
            });
            document.body.style.overflow = '';
        }
    });
});

// Export for use in Alpine.js components
window.OBSFog = {
    api,
    notifications,
    copyToClipboard,
    formatDate,
    formatRelativeTime,
    formatFileSize,
    formatDuration,
    debounce,
    throttle,
    modal,
    validateForm,
    setLoading,
    confirmAction,
    downloadFile,
    StreamStatusChecker,
    initHLSPlayer,
};
