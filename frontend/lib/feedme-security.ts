/**
 * FeedMe Security Utilities
 * Production-ready security helpers for input validation, sanitization, and protection
 */

import DOMPurify from 'isomorphic-dompurify'
import { z } from 'zod'

// Security constants
export const SECURITY_CONSTANTS = {
  MAX_TEXT_LENGTH: 1000000, // 1 million characters
  MIN_TEXT_LENGTH: 1,
  MAX_TITLE_LENGTH: 255,
  MAX_DESCRIPTION_LENGTH: 1000,
  MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
  MAX_FOLDER_NAME_LENGTH: 100,
  MAX_TAG_LENGTH: 50,
  MAX_TAGS: 20,
  ALLOWED_FILE_TYPES: ['.txt', '.pdf', '.doc', '.docx'],
  RATE_LIMIT_WINDOW: 60000, // 1 minute
  RATE_LIMIT_MAX_REQUESTS: 100
} as const

// Forbidden patterns for XSS prevention
const FORBIDDEN_PATTERNS = [
  /<script[^>]*>.*?<\/script>/gi,
  /<iframe[^>]*>.*?<\/iframe>/gi,
  /javascript:/gi,
  /on\w+\s*=/gi, // Event handlers
  /<object[^>]*>.*?<\/object>/gi,
  /<embed[^>]*>/gi,
  /<link[^>]*>/gi,
  /<style[^>]*>.*?<\/style>/gi,
  /data:text\/html/gi,
  /vbscript:/gi
]

// SQL injection patterns
const SQL_INJECTION_PATTERNS = [
  /(\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\b)/gi,
  /(-{2}|\/\*|\*\/)/g, // SQL comments
  /(;|'|"|`|\\x00|\\n|\\r|\\x1a)/g // Special characters
]

// Path traversal patterns
const PATH_TRAVERSAL_PATTERNS = [
  /\.\.\//g,
  /\.\.\\\/g,
  /%2e%2e/gi,
  /%252e%252e/gi
]

/**
 * Input validation schemas using Zod
 */
export const ValidationSchemas = {
  conversationTitle: z.string()
    .min(1, 'Title is required')
    .max(SECURITY_CONSTANTS.MAX_TITLE_LENGTH, `Title must be ${SECURITY_CONSTANTS.MAX_TITLE_LENGTH} characters or less`)
    .refine(val => !FORBIDDEN_PATTERNS.some(pattern => pattern.test(val)), {
      message: 'Title contains potentially harmful content'
    }),

  conversationText: z.string()
    .min(SECURITY_CONSTANTS.MIN_TEXT_LENGTH, 'Text is required')
    .max(SECURITY_CONSTANTS.MAX_TEXT_LENGTH, `Text must be ${SECURITY_CONSTANTS.MAX_TEXT_LENGTH} characters or less`)
    .refine(val => !FORBIDDEN_PATTERNS.some(pattern => pattern.test(val)), {
      message: 'Text contains potentially harmful content'
    }),

  folderName: z.string()
    .min(1, 'Folder name is required')
    .max(SECURITY_CONSTANTS.MAX_FOLDER_NAME_LENGTH, `Folder name must be ${SECURITY_CONSTANTS.MAX_FOLDER_NAME_LENGTH} characters or less`)
    .regex(/^[a-zA-Z0-9\s\-_()]+$/, 'Folder name contains invalid characters')
    .refine(val => !PATH_TRAVERSAL_PATTERNS.some(pattern => pattern.test(val)), {
      message: 'Folder name contains path traversal attempt'
    }),

  searchQuery: z.string()
    .max(200, 'Search query is too long')
    .refine(val => !SQL_INJECTION_PATTERNS.some(pattern => pattern.test(val)), {
      message: 'Search query contains potentially harmful content'
    }),

  fileUpload: z.object({
    name: z.string().refine(name => {
      const ext = name.substring(name.lastIndexOf('.')).toLowerCase()
      return SECURITY_CONSTANTS.ALLOWED_FILE_TYPES.includes(ext)
    }, {
      message: `File type not allowed. Allowed types: ${SECURITY_CONSTANTS.ALLOWED_FILE_TYPES.join(', ')}`
    }),
    size: z.number().max(SECURITY_CONSTANTS.MAX_FILE_SIZE, 'File size exceeds maximum allowed size'),
    type: z.string()
  }),

  pagination: z.object({
    page: z.number().int().positive().max(10000),
    limit: z.number().int().positive().max(100)
  }),

  dateRange: z.object({
    from: z.date().optional(),
    to: z.date().optional()
  }).refine(data => {
    if (data.from && data.to) {
      return data.from <= data.to
    }
    return true
  }, {
    message: 'From date must be before or equal to To date'
  })
}

/**
 * Sanitize text content for safe display
 */
export function sanitizeText(text: string, options?: {
  maxLength?: number
  allowNewlines?: boolean
  stripHtml?: boolean
}): string {
  const { 
    maxLength = SECURITY_CONSTANTS.MAX_TEXT_LENGTH,
    allowNewlines = true,
    stripHtml = true
  } = options || {}

  // First, apply DOMPurify
  let sanitized = DOMPurify.sanitize(text, {
    USE_PROFILES: { html: !stripHtml },
    ALLOWED_TAGS: stripHtml ? [] : ['b', 'i', 'em', 'strong', 'a', 'br', 'p'],
    ALLOWED_ATTR: stripHtml ? [] : ['href'],
    KEEP_CONTENT: true
  })

  // Remove null bytes and other control characters
  sanitized = sanitized.replace(/\x00/g, '')

  // Handle newlines
  if (!allowNewlines) {
    sanitized = sanitized.replace(/[\r\n]+/g, ' ')
  }

  // Trim to max length
  if (sanitized.length > maxLength) {
    sanitized = sanitized.substring(0, maxLength) + '...'
  }

  return sanitized.trim()
}

/**
 * Sanitize file name for safe storage
 */
export function sanitizeFileName(fileName: string): string {
  // Remove path components
  let sanitized = fileName.split(/[/\\]/).pop() || ''
  
  // Remove dangerous characters
  sanitized = sanitized.replace(/[^a-zA-Z0-9._\-\s]/g, '')
  
  // Remove multiple dots (prevent extension spoofing)
  sanitized = sanitized.replace(/\.{2,}/g, '.')
  
  // Limit length
  const maxLength = 255
  if (sanitized.length > maxLength) {
    const ext = sanitized.substring(sanitized.lastIndexOf('.'))
    const name = sanitized.substring(0, sanitized.lastIndexOf('.'))
    sanitized = name.substring(0, maxLength - ext.length - 10) + '_truncated' + ext
  }
  
  return sanitized || 'unnamed_file'
}

/**
 * Validate and sanitize URL
 */
export function sanitizeUrl(url: string): string | null {
  try {
    const parsed = new URL(url)
    
    // Only allow http(s) protocols
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return null
    }
    
    // Prevent localhost and private IPs
    const hostname = parsed.hostname.toLowerCase()
    if (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname.startsWith('192.168.') ||
      hostname.startsWith('10.') ||
      hostname.startsWith('172.')
    ) {
      return null
    }
    
    return parsed.toString()
  } catch {
    return null
  }
}

/**
 * Generate secure random ID
 */
export function generateSecureId(prefix: string = 'id'): string {
  const array = new Uint8Array(16)
  crypto.getRandomValues(array)
  const hex = Array.from(array)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
  return `${prefix}_${hex}`
}

/**
 * Hash sensitive data (client-side only, for comparison)
 */
export async function hashData(data: string): Promise<string> {
  const encoder = new TextEncoder()
  const dataBuffer = encoder.encode(data)
  const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Rate limiter for client-side operations
 */
export class RateLimiter {
  private requests: Map<string, number[]> = new Map()
  
  constructor(
    private windowMs: number = SECURITY_CONSTANTS.RATE_LIMIT_WINDOW,
    private maxRequests: number = SECURITY_CONSTANTS.RATE_LIMIT_MAX_REQUESTS
  ) {}
  
  isAllowed(key: string): boolean {
    const now = Date.now()
    const requests = this.requests.get(key) || []
    
    // Remove old requests outside the window
    const validRequests = requests.filter(time => now - time < this.windowMs)
    
    if (validRequests.length >= this.maxRequests) {
      return false
    }
    
    validRequests.push(now)
    this.requests.set(key, validRequests)
    
    // Cleanup old entries
    if (this.requests.size > 1000) {
      const cutoff = now - this.windowMs
      for (const [k, times] of this.requests.entries()) {
        if (times[times.length - 1] < cutoff) {
          this.requests.delete(k)
        }
      }
    }
    
    return true
  }
  
  reset(key: string): void {
    this.requests.delete(key)
  }
}

/**
 * Content Security Policy generator
 */
export function generateCSP(): string {
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'", // Required for Next.js
    "style-src 'self' 'unsafe-inline'", // Required for styled components
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "connect-src 'self' wss: https:",
    "media-src 'self'",
    "object-src 'none'",
    "frame-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests"
  ].join('; ')
}

/**
 * Input debouncer for validation
 */
export function createSecureDebouncer<T extends (...args: any[]) => any>(
  func: T,
  delay: number = 300
): (...args: Parameters<T>) => void {
  let timeoutId: NodeJS.Timeout | null = null
  
  return (...args: Parameters<T>) => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
    
    timeoutId = setTimeout(() => {
      func(...args)
    }, delay)
  }
}

/**
 * Escape HTML entities
 */
export function escapeHtml(unsafe: string): string {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/**
 * Validate email address
 */
export function isValidEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailRegex.test(email) && email.length <= 254
}

/**
 * Check for suspicious patterns in text
 */
export function detectSuspiciousContent(text: string): {
  isSuspicious: boolean
  reasons: string[]
} {
  const reasons: string[] = []
  
  // Check for excessive special characters
  const specialCharRatio = (text.match(/[^a-zA-Z0-9\s]/g) || []).length / text.length
  if (specialCharRatio > 0.3) {
    reasons.push('High ratio of special characters')
  }
  
  // Check for repeated characters
  if (/(.)\1{9,}/.test(text)) {
    reasons.push('Excessive character repetition')
  }
  
  // Check for encoded content
  if (/(%[0-9a-fA-F]{2}){10,}/.test(text)) {
    reasons.push('Possible encoded malicious content')
  }
  
  // Check for base64 encoded scripts
  if (/data:.*;base64,/.test(text) && text.length > 1000) {
    reasons.push('Possible base64 encoded content')
  }
  
  return {
    isSuspicious: reasons.length > 0,
    reasons
  }
}

/**
 * Secure JSON parse with validation
 */
export function secureJsonParse<T>(
  json: string,
  schema?: z.ZodSchema<T>
): T | null {
  try {
    const parsed = JSON.parse(json)
    
    if (schema) {
      const result = schema.safeParse(parsed)
      return result.success ? result.data : null
    }
    
    return parsed
  } catch {
    return null
  }
}

/**
 * Create secure headers for API requests
 */
export function createSecureHeaders(additionalHeaders?: Record<string, string>): Headers {
  const headers = new Headers({
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    ...additionalHeaders
  })
  
  return headers
}