/**
 * Application-wide configuration constants
 * Centralized location for all timeout values, thresholds, and magic numbers
 */

// API & Network Configuration
export const API_CONFIG = {
  // Timeout values in milliseconds
  TIMEOUTS: {
    DEFAULT: 30000,        // 30 seconds - default API timeout
    UPLOAD: 120000,        // 2 minutes - file upload timeout
    LONG_POLL: 300000,     // 5 minutes - long polling timeout
    RETRY_DELAY: 1000,     // 1 second - base retry delay
    MAX_RETRY_DELAY: 30000, // 30 seconds - max retry delay
    DEBOUNCE: 300,         // 300ms - input debounce
    THROTTLE: 100,         // 100ms - scroll/resize throttle
    AUTO_SAVE: 2000,       // 2 seconds - auto-save delay
  },

  // Request limits
  LIMITS: {
    MAX_RETRIES: 3,
    MAX_CONCURRENT_REQUESTS: 6,
    CACHE_TTL: 300000,     // 5 minutes cache TTL
    RATE_LIMIT_WINDOW: 60000, // 1 minute rate limit window
  },

  // Performance thresholds
  PERFORMANCE: {
    SLOW_REQUEST_THRESHOLD: 3000, // 3 seconds
    CRITICAL_THRESHOLD: 10000,    // 10 seconds
    WARNING_THRESHOLD: 5000,       // 5 seconds
  }
} as const

// UI Configuration
export const UI_CONFIG = {
  // Animation durations in milliseconds
  ANIMATIONS: {
    FAST: 150,
    NORMAL: 300,
    SLOW: 500,
    TOAST_DURATION: 5000,
    ERROR_TOAST_DURATION: 7000,
  },

  // List virtualization
  VIRTUALIZATION: {
    ITEM_HEIGHT: 60,          // Default item height in pixels
    OVERSCAN: 5,              // Number of items to render outside viewport
    THRESHOLD: 100,           // Minimum items before virtualization kicks in
    SCROLL_DEBOUNCE: 150,     // Scroll event debounce
  },

  // Pagination
  PAGINATION: {
    DEFAULT_PAGE_SIZE: 20,
    MAX_PAGE_SIZE: 100,
    INFINITE_SCROLL_THRESHOLD: 200, // px from bottom to trigger load
  },

  // Form validation
  VALIDATION: {
    MIN_PASSWORD_LENGTH: 8,
    MAX_INPUT_LENGTH: 500,
    MAX_TEXTAREA_LENGTH: 5000,
    MAX_FILE_SIZE: 10485760,  // 10MB in bytes
    ALLOWED_FILE_TYPES: ['image/jpeg', 'image/png', 'image/gif', 'application/pdf'],
  }
} as const

// Error Recovery Configuration
export const ERROR_CONFIG = {
  // Error boundary settings
  ERROR_BOUNDARY: {
    AUTO_RECOVER_DELAY: 30000,    // 30 seconds
    MAX_ERROR_COUNT: 3,            // Max errors before giving up
    RESET_WINDOW: 60000,           // Reset error count after 1 minute
  },

  // Retry logic
  RETRY: {
    EXPONENTIAL_BASE: 2,
    JITTER_FACTOR: 0.3,
    MAX_ATTEMPTS: 3,
  }
} as const

// Storage Configuration
export const STORAGE_CONFIG = {
  // Session storage keys
  SESSION_KEYS: {
    USER_PREFERENCES: 'user_prefs',
    DRAFT_DATA: 'draft_data',
    API_CACHE: 'api_cache',
  },

  // Local storage keys
  LOCAL_KEYS: {
    THEME: 'app_theme',
    LOCALE: 'app_locale',
    LAST_SYNC: 'last_sync',
  },

  // Storage limits
  LIMITS: {
    MAX_CACHE_SIZE: 5242880,     // 5MB in bytes
    MAX_CACHE_ITEMS: 100,
    CACHE_EXPIRY: 86400000,       // 24 hours in ms
  }
} as const

// Security Configuration
export const SECURITY_CONFIG = {
  // Content Security Policy
  CSP: {
    ALLOWED_DOMAINS: ['https://api.example.com', 'https://cdn.example.com'],
    ALLOWED_PROTOCOLS: ['https:', 'wss:'] as const,
  },

  // Sanitization
  SANITIZATION: {
    ALLOWED_HTML_TAGS: [
      'p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li',
      'code', 'pre', 'blockquote', 'h1', 'h2', 'h3', 'img'
    ],
    ALLOWED_ATTRIBUTES: ['href', 'target', 'rel', 'src', 'alt', 'class'],
    ALLOWED_CLASSES: ['agent-name', 'customer-name'],
  },

  // Rate limiting
  RATE_LIMITS: {
    API_CALLS_PER_MINUTE: 60,
    FILE_UPLOADS_PER_HOUR: 100,
    AUTH_ATTEMPTS_PER_HOUR: 5,
  }
} as const

// Feature Flags
export const FEATURE_FLAGS = {
  ENABLE_VIRTUALIZATION: true,
  ENABLE_API_CACHING: true,
  ENABLE_ERROR_REPORTING: process.env.NODE_ENV === 'production',
  ENABLE_PERFORMANCE_MONITORING: process.env.NODE_ENV === 'production',
  ENABLE_DEBUG_LOGGING: process.env.NODE_ENV === 'development',
} as const

// Application Metadata
export const APP_CONFIG = {
  NAME: 'FeedMe',
  VERSION: process.env.NEXT_PUBLIC_APP_VERSION || '1.0.0',
  ENVIRONMENT: process.env.NODE_ENV,
  API_BASE_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  WS_BASE_URL: process.env.NEXT_PUBLIC_WS_URL || (typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss://localhost:8000' : 'ws://localhost:8000'),
} as const

// Type helper for config categories
type ConfigCategories = {
  API_CONFIG: typeof API_CONFIG
  UI_CONFIG: typeof UI_CONFIG
  ERROR_CONFIG: typeof ERROR_CONFIG
  STORAGE_CONFIG: typeof STORAGE_CONFIG
  SECURITY_CONFIG: typeof SECURITY_CONFIG
  FEATURE_FLAGS: typeof FEATURE_FLAGS
  APP_CONFIG: typeof APP_CONFIG
}

// Export type-safe config getter
export function getConfig<
  C extends keyof ConfigCategories,
  K extends keyof ConfigCategories[C]
>(
  category: C,
  key: K
): ConfigCategories[C][K] {
  const configs: ConfigCategories = {
    API_CONFIG,
    UI_CONFIG,
    ERROR_CONFIG,
    STORAGE_CONFIG,
    SECURITY_CONFIG,
    FEATURE_FLAGS,
    APP_CONFIG,
  }

  return configs[category][key]
}

// Type exports for TypeScript
export type ApiConfig = typeof API_CONFIG
export type UiConfig = typeof UI_CONFIG
export type ErrorConfig = typeof ERROR_CONFIG
export type StorageConfig = typeof STORAGE_CONFIG
export type SecurityConfig = typeof SECURITY_CONFIG
export type FeatureFlags = typeof FEATURE_FLAGS
export type AppConfig = typeof APP_CONFIG