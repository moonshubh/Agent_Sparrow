/**
 * Environment detection utility
 */

export const isProduction = process.env.NODE_ENV === 'production'
export const isDevelopment = process.env.NODE_ENV === 'development'

/**
 * Get the API URL based on environment
 * Falls back to localhost for development
 */
export function getApiUrl(): string {
  // If NEXT_PUBLIC_API_URL is set, use it
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL
  }
  
  // Otherwise, use localhost for development
  if (isDevelopment) {
    return 'http://localhost:8000'
  }
  
  // For production, this should never happen if env vars are set correctly
  console.error('⚠️ NEXT_PUBLIC_API_URL not set in production!')
  return ''
}

/**
 * Get the API base URL for v1 endpoints
 */
export function getApiBaseUrl(): string {
  const apiUrl = getApiUrl()
  return apiUrl ? `${apiUrl}/api/v1` : ''
}

/**
 * Get the API base path (alias for getApiBaseUrl)
 */
export function getApiBasePath(): string {
  return getApiBaseUrl()
}

/**
 * Log environment information for debugging
 */
export function logEnvironment(): void {
  if (typeof window !== 'undefined') {
    console.log('🌍 Environment:', {
      NODE_ENV: process.env.NODE_ENV,
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
      isDevelopment,
      isProduction,
      apiUrl: getApiUrl(),
      apiBaseUrl: getApiBaseUrl()
    })
  }
}