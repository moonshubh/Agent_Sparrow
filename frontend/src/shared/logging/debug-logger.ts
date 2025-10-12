/**
 * Debug logger utility for conditional logging based on environment variables
 * Only logs when NEXT_PUBLIC_DEBUG_CHAT is set to 'true'
 */

type LoggableValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Date
  | LoggableValue[]
  | { [key: string]: LoggableValue }

const isDebugEnabled = process.env.NEXT_PUBLIC_DEBUG_CHAT === 'true'

/**
 * Debug logger that only logs when debug mode is enabled
 * @param module - Module or component name for context
 * @param message - Log message
 * @param data - Optional data to log (will be sanitized)
 */
export function debugLog(module: string, message: string, data?: LoggableValue): void {
  if (!isDebugEnabled) return

  const sanitizedData = data ? sanitizeData(data) : undefined

  if (typeof sanitizedData === 'undefined') {
    console.log(`[${module}] ${message}`)
  } else {
    console.log(`[${module}] ${message}`, sanitizedData)
  }
}

/**
 * Sanitize data to remove or redact sensitive information
 * @param data - Data to sanitize
 * @returns Sanitized data
 */
function sanitizeData(data: LoggableValue): LoggableValue {
  if (data === null || data === undefined) return data

  if (Array.isArray(data)) {
    return data.map((item) => sanitizeData(item))
  }

  if (data instanceof Date) {
    return data
  }

  if (typeof data === 'object') {
    const entries = Object.entries(data as Record<string, LoggableValue>).map(([key, value]) => {
      if (isSensitiveField(key)) {
        return [key, '[REDACTED]'] as const
      }

      if (isContentField(key)) {
        if (typeof value === 'string') {
          return [key, `[Content: ${value.length} chars]`] as const
        }
        return [key, '[Content]'] as const
      }

      if (isIdField(key)) {
        if (typeof value === 'string' && value.length > 8) {
          return [key, `${value.slice(0, 4)}...${value.slice(-4)}`] as const
        }
        return [key, value]
      }

      return [key, sanitizeData(value)] as const
    })

    return Object.fromEntries(entries)
  }

  return data
}

/**
 * Check if a field name indicates sensitive data
 */
function isSensitiveField(fieldName: string): boolean {
  const sensitivePatterns = [
    'password',
    'token',
    'secret',
    'api_key',
    'apikey',
    'auth',
    'credential',
    'private'
  ]

  const lowerFieldName = fieldName.toLowerCase()
  return sensitivePatterns.some((pattern) => lowerFieldName.includes(pattern))
}

/**
 * Check if a field contains content that should be abbreviated
 */
function isContentField(fieldName: string): boolean {
  const contentPatterns = [
    'content',
    'message',
    'text',
    'body',
    'response',
    'query',
    'answer',
    'backendmessage'
  ]

  const lowerFieldName = fieldName.toLowerCase()
  return contentPatterns.some((pattern) => lowerFieldName.includes(pattern))
}

/**
 * Check if a field is an ID field that should be partially shown
 */
function isIdField(fieldName: string): boolean {
  const idPatterns = [
    'id',
    'uuid',
    'sessionid',
    'messageid',
    'userid',
    'conversationid'
  ]

  const lowerFieldName = fieldName.toLowerCase()
  return idPatterns.some((pattern) => lowerFieldName.includes(pattern))
}

/**
 * Strict numeric validation for session IDs
 * Only accepts strings that are fully numeric (no UUID starting with digits)
 * @param value - Value to validate
 * @returns true if value is a valid numeric string
 */
export function isStrictNumericId(value: string): boolean {
  if (!value || typeof value !== 'string') return false

  const strictNumericRegex = /^\d+$/

  if (value.length > 20) return false
  if (value.length > 1 && value.startsWith('0')) return false

  return strictNumericRegex.test(value)
}
