/**
 * Application-wide constants configuration
 * Centralized location for all magic numbers and configuration values
 */

// Timing constants (in milliseconds)
export const TIMINGS = {
  // Debounce delays
  DEBOUNCE: {
    QUICK: 100,
    STANDARD: 300,
    SEARCH: 500,
    HEAVY: 1000,
  },

  // Animation durations
  ANIMATION: {
    INSTANT: 0,
    FAST: 150,
    NORMAL: 300,
    SLOW: 500,
  },

  // API timeouts
  TIMEOUT: {
    QUICK: 10000,    // 10 seconds for status checks
    STANDARD: 30000, // 30 seconds for normal requests
    HEAVY: 60000,    // 60 seconds for file uploads
    DATABASE: 45000, // 45 seconds for DB operations
  },

  // Retry delays
  RETRY: {
    MIN: 1000,       // 1 second minimum
    MAX: 8000,       // 8 seconds maximum
    JITTER: 1000,    // 0-1 second random jitter
  },

  // Auto-save intervals
  AUTOSAVE: {
    DRAFT: 30000,    // 30 seconds
    ACTIVE: 5000,    // 5 seconds when actively typing
  },

  // Error recovery
  ERROR_RECOVERY: {
    AUTO_RETRY: 30000,  // 30 seconds
    MAX_RETRIES: 3,
  },

  // Performance monitoring
  MONITORING: {
    STATS_UPDATE: 5000,        // 5 seconds
    SLOW_REQUEST: 3000,        // 3 seconds threshold
    METRICS_WINDOW: 60000,     // 1 minute window
  },
} as const

// List virtualization thresholds
export const VIRTUALIZATION = {
  MIN_ITEMS: 50,           // Minimum items before enabling virtualization
  ITEM_HEIGHT: 60,         // Default item height in pixels
  OVERSCAN: 5,             // Number of items to render outside viewport
  SCROLL_DEBOUNCE: 150,    // Debounce scroll events
} as const

// API configuration
export const API = {
  // Request retry configuration
  RETRY: {
    QUICK: { timeout: TIMINGS.TIMEOUT.QUICK, retries: 2 },
    STANDARD: { timeout: TIMINGS.TIMEOUT.STANDARD, retries: 3 },
    HEAVY: { timeout: TIMINGS.TIMEOUT.HEAVY, retries: 2 },
    DATABASE: { timeout: TIMINGS.TIMEOUT.DATABASE, retries: 2 },
  },

  // Cache configuration
  CACHE: {
    TTL: {
      SHORT: 30000,     // 30 seconds
      MEDIUM: 300000,   // 5 minutes
      LONG: 900000,     // 15 minutes
      SESSION: null,    // Until session ends
    },
    MAX_SIZE: 100,      // Maximum cached entries
  },

  // Rate limiting
  RATE_LIMIT: {
    REQUESTS_PER_SECOND: 10,
    BURST_SIZE: 20,
  },

  // Performance thresholds
  PERFORMANCE: {
    SLOW_REQUEST: TIMINGS.MONITORING.SLOW_REQUEST,
    TIMEOUT_WARNING: 0.8, // Warn at 80% of timeout
    MAX_METRICS: 100,     // Maximum metrics to track
  },
} as const

// Accessibility constants
export const A11Y = {
  // ARIA live region politeness
  LIVE_REGION: {
    POLITE: 'polite' as const,
    ASSERTIVE: 'assertive' as const,
    OFF: 'off' as const,
  },

  // Focus management
  FOCUS: {
    TRAP_DELAY: 100,      // Delay before trapping focus
    RESTORE_DELAY: 50,    // Delay before restoring focus
  },

  // Keyboard navigation
  KEYBOARD: {
    TAB: 'Tab',
    ESCAPE: 'Escape',
    ENTER: 'Enter',
    SPACE: ' ',
    ARROW_UP: 'ArrowUp',
    ARROW_DOWN: 'ArrowDown',
    ARROW_LEFT: 'ArrowLeft',
    ARROW_RIGHT: 'ArrowRight',
  },

  // Screen reader announcements
  ANNOUNCEMENTS: {
    DELAY: 100,           // Delay before announcing
    DEBOUNCE: 500,        // Debounce rapid announcements
  },
} as const

// UI constants
export const UI = {
  // Z-index layers
  Z_INDEX: {
    DROPDOWN: 50,
    STICKY: 100,
    OVERLAY: 200,
    MODAL: 300,
    POPOVER: 400,
    TOOLTIP: 500,
    TOAST: 600,
  },

  // Breakpoints (matching Tailwind)
  BREAKPOINTS: {
    SM: 640,
    MD: 768,
    LG: 1024,
    XL: 1280,
    '2XL': 1536,
  },

  // Layout
  LAYOUT: {
    SIDEBAR_WIDTH: 320,
    HEADER_HEIGHT: 64,
    FOOTER_HEIGHT: 48,
  },

  // Pagination
  PAGINATION: {
    DEFAULT_PAGE_SIZE: 20,
    PAGE_SIZE_OPTIONS: [10, 20, 50, 100],
  },

  // Form validation
  VALIDATION: {
    MIN_PASSWORD: 8,
    MAX_INPUT: 1000,
    MAX_TEXTAREA: 5000,
  },
} as const

// Feature flags
export const FEATURES = {
  // Development features
  DEV: {
    VERBOSE_LOGGING: process.env.NODE_ENV === 'development',
    SHOW_ERROR_DETAILS: process.env.NODE_ENV === 'development',
    API_MONITORING: true,
  },

  // Performance features
  PERFORMANCE: {
    VIRTUALIZATION: true,
    LAZY_LOADING: true,
    REQUEST_DEDUP: true,
    CACHE_API: true,
  },

  // Security features
  SECURITY: {
    SANITIZE_HTML: true,
    CSP_ENABLED: true,
    SECURE_STORAGE: true,
  },
} as const

// Logging levels
export const LOG_LEVELS = {
  ERROR: 0,
  WARN: 1,
  INFO: 2,
  DEBUG: 3,
  TRACE: 4,
} as const

// Storage keys
export const STORAGE_KEYS = {
  // Session storage
  SESSION: {
    API_METRICS: 'api-metrics-session',
    AUTH_RETURN: 'authReturnUrl',
    DRAFT_DATA: 'draft-data',
  },

  // Local storage
  LOCAL: {
    USER_PREFERENCES: 'user-preferences',
    THEME: 'theme',
    SIDEBAR_STATE: 'sidebar-state',
  },

  // IndexedDB
  INDEXED_DB: {
    API_CACHE: 'api-cache',
    OFFLINE_QUEUE: 'offline-queue',
  },
} as const

// Error messages
export const ERROR_MESSAGES = {
  NETWORK: {
    OFFLINE: 'You are offline - unable to reach the service',
    TIMEOUT: 'Request timed out - the server may be under heavy load',
    CONNECTION_FAILED: 'Network connection failed - please check your internet connection',
    SERVER_DOWN: 'Cannot connect to service - it may be temporarily down',
    SERVER_ERROR: 'Service encountered an error - please try again later',
  },

  VALIDATION: {
    REQUIRED: 'This field is required',
    INVALID_EMAIL: 'Please enter a valid email address',
    PASSWORD_TOO_SHORT: `Password must be at least ${UI.VALIDATION.MIN_PASSWORD} characters`,
    INPUT_TOO_LONG: `Input exceeds maximum length of ${UI.VALIDATION.MAX_INPUT} characters`,
  },

  GENERIC: {
    SOMETHING_WRONG: 'Something went wrong',
    TRY_AGAIN: 'An error occurred. Please try again.',
    CONTACT_SUPPORT: 'If the problem persists, please contact support.',
  },
} as const

export type LogLevel = keyof typeof LOG_LEVELS
export type StorageKey =
  | typeof STORAGE_KEYS.SESSION[keyof typeof STORAGE_KEYS.SESSION]
  | typeof STORAGE_KEYS.LOCAL[keyof typeof STORAGE_KEYS.LOCAL]
  | typeof STORAGE_KEYS.INDEXED_DB[keyof typeof STORAGE_KEYS.INDEXED_DB]