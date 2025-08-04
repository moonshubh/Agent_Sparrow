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
  // Always log the current environment for debugging
  if (typeof window !== 'undefined') {
    console.log('🔍 API URL Resolution:', {
      isProduction,
      isDevelopment,
      NODE_ENV: process.env.NODE_ENV,
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
      hasApiUrl: !!process.env.NEXT_PUBLIC_API_URL
    });
  }
  
  // If NEXT_PUBLIC_API_URL is set, use it
  if (process.env.NEXT_PUBLIC_API_URL) {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    
    // Warn if using localhost in production
    if (isProduction && apiUrl.includes('localhost') && typeof window !== 'undefined') {
      console.error('⚠️ WARNING: Using localhost API URL in production!', apiUrl);
      console.error('Please set NEXT_PUBLIC_API_URL in your deployment platform');
    }
    
    console.log('✅ Using API URL:', apiUrl);
    return apiUrl;
  }
  
  // Otherwise, use localhost for development
  if (isDevelopment || !isProduction) {
    console.info('📍 Using default localhost:8000 for development');
    return 'http://localhost:8000'
  }
  
  // For production, this should never happen if env vars are set correctly
  if (typeof window !== 'undefined') {
    console.error('🚨 CRITICAL: NEXT_PUBLIC_API_URL not set in production!');
    console.error('Your app will not be able to connect to the backend.');
    console.error('Please set NEXT_PUBLIC_API_URL in your Railway service variables.');
    console.error('The build must have this variable set, not just at runtime.');
    
    // Show alert to make it obvious
    alert('Configuration Error: Backend URL not set. Please contact support.');
  }
  
  // Never default to localhost in production - return empty to make errors obvious
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