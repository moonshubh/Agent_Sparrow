/**
 * Debug logger utility for conditional logging based on environment variables
 * Only logs when NEXT_PUBLIC_DEBUG_CHAT is set to 'true'
 */

const isDebugEnabled = process.env.NEXT_PUBLIC_DEBUG_CHAT === 'true';

/**
 * Debug logger that only logs when debug mode is enabled
 * @param module - Module or component name for context
 * @param message - Log message
 * @param data - Optional data to log (will be sanitized)
 */
export function debugLog(module: string, message: string, data?: any) {
  if (!isDebugEnabled) return;
  
  // Sanitize data to prevent PII exposure
  const sanitizedData = data ? sanitizeData(data) : undefined;
  
  console.log(`[${module}] ${message}`, sanitizedData || '');
}

/**
 * Sanitize data to remove or redact sensitive information
 * @param data - Data to sanitize
 * @returns Sanitized data
 */
function sanitizeData(data: any): any {
  if (data === null || data === undefined) return data;
  
  // Handle arrays
  if (Array.isArray(data)) {
    return data.map(item => sanitizeData(item));
  }
  
  // Handle objects
  if (typeof data === 'object') {
    const sanitized: any = {};
    
    for (const key in data) {
      if (data.hasOwnProperty(key)) {
        // Skip sensitive fields entirely
        if (isSensitiveField(key)) {
          sanitized[key] = '[REDACTED]';
        }
        // For content fields, only show length
        else if (isContentField(key)) {
          const value = data[key];
          if (typeof value === 'string') {
            sanitized[key] = `[Content: ${value.length} chars]`;
          } else {
            sanitized[key] = '[Content]';
          }
        }
        // For IDs, show partial hash
        else if (isIdField(key)) {
          const value = data[key];
          if (typeof value === 'string' && value.length > 8) {
            sanitized[key] = `${value.substring(0, 4)}...${value.substring(value.length - 4)}`;
          } else {
            sanitized[key] = value;
          }
        }
        // Recursively sanitize nested objects
        else {
          sanitized[key] = sanitizeData(data[key]);
        }
      }
    }
    
    return sanitized;
  }
  
  // Return primitive values as-is
  return data;
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
    'apiKey',
    'auth',
    'credential',
    'private'
  ];
  
  const lowerFieldName = fieldName.toLowerCase();
  return sensitivePatterns.some(pattern => lowerFieldName.includes(pattern));
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
    'backendMessage'
  ];
  
  const lowerFieldName = fieldName.toLowerCase();
  return contentPatterns.some(pattern => lowerFieldName.includes(pattern));
}

/**
 * Check if a field is an ID field that should be partially shown
 */
function isIdField(fieldName: string): boolean {
  const idPatterns = [
    'id',
    'uuid',
    'sessionId',
    'messageId',
    'userId',
    'conversationId'
  ];
  
  const lowerFieldName = fieldName.toLowerCase();
  return idPatterns.some(pattern => lowerFieldName.includes(pattern.toLowerCase()));
}

/**
 * Strict numeric validation for session IDs
 * Only accepts strings that are fully numeric (no UUID starting with digits)
 * @param value - Value to validate
 * @returns true if value is a valid numeric string
 */
export function isStrictNumericId(value: string): boolean {
  // Must be non-empty string
  if (!value || typeof value !== 'string') return false;
  
  // Use strict regex that matches only complete numeric strings
  const strictNumericRegex = /^\d+$/;
  
  // Additional check: must be a reasonable ID (not too long, not starting with 0 unless it's just "0")
  if (value.length > 20) return false; // Database IDs shouldn't be this long
  if (value.length > 1 && value.startsWith('0')) return false; // No leading zeros except for "0"
  
  return strictNumericRegex.test(value);
}