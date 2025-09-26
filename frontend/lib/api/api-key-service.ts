/**
 * API Key Service for managing user API keys
 * This service handles fetching, caching, and validating user API keys from the backend
 */

import { supabase } from '@/lib/supabase-browser'
import { getApiUrl } from '@/lib/utils/environment'
import { APIKeyType } from '@/lib/api-keys'

// Re-export APIKeyType for other components to use
export { APIKeyType }

interface CachedAPIKey {
  key: string
  timestamp: number
}

interface UserAPIKey {
  api_key_type: APIKeyType
  masked_key: string
  is_active: boolean
}

// Lightweight LRU cache (no timers) to avoid memory leaks
// Cache key: `${userId}|${keyType}`
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes
const MAX_CACHE_ENTRIES = 300
const keyCache = new Map<string, CachedAPIKey>()

function makeCacheKey(userId: string, keyType: APIKeyType): string {
  return `${userId}|${keyType}`
}

function pruneIfNeeded() {
  if (keyCache.size <= MAX_CACHE_ENTRIES) return
  const excess = keyCache.size - MAX_CACHE_ENTRIES
  const it = keyCache.keys()
  for (let i = 0; i < excess; i++) {
    const k = it.next().value
    if (k) keyCache.delete(k)
  }
}

/**
 * Get a cached API key if it exists and is not expired
 */
function getCachedKey(userId: string, keyType: APIKeyType): string | null {
  const k = makeCacheKey(userId, keyType)
  const entry = keyCache.get(k)
  if (!entry) return null
  if (Date.now() - entry.timestamp > CACHE_TTL) {
    keyCache.delete(k)
    return null
  }
  // refresh recency
  keyCache.delete(k)
  keyCache.set(k, entry)
  return entry.key
}

/**
 * Set a cached API key
 */
function setCachedKey(userId: string, keyType: APIKeyType, key: string) {
  const k = makeCacheKey(userId, keyType)
  const entry: CachedAPIKey = { key, timestamp: Date.now() }
  // set and move to recent
  if (keyCache.has(k)) keyCache.delete(k)
  keyCache.set(k, entry)
  pruneIfNeeded()
}

/**
 * Clear cache for a specific user
 */
export function clearUserAPIKeyCache(userId: string) {
  // Remove all entries for the user
  const prefix = `${userId}|`
  for (const k of Array.from(keyCache.keys())) {
    if (k.startsWith(prefix)) keyCache.delete(k)
  }
}

// Clear all cache entries (useful on logout of all accounts)
export function clearAllAPIKeyCache() {
  keyCache.clear()
}

/**
 * Fetch actual API key from secure backend endpoint
 */
async function fetchActualAPIKey(
  authToken: string,
  userId: string,
  keyType: APIKeyType
): Promise<string | null> {
  try {
    const apiUrl = getApiUrl()
    
    // Use a dedicated secure endpoint for fetching actual keys
    // This endpoint should only return actual keys, never masked ones
    const response = await fetch(`${apiUrl}/api/v1/api-keys/actual/${keyType}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (response.ok) {
      const data = await response.json()
      if (data.api_key && typeof data.api_key === 'string') {
        // Validate the key format before caching
        if (!validateAPIKeyFormat(keyType, data.api_key)) {
          console.error('Invalid API key format received from backend')
          return null
        }
        return data.api_key
      }
    } else if (response.status === 404) {
      // User hasn't configured this key type
      return null
    } else if (response.status === 401 || response.status === 403) {
      console.error('Authentication failed when fetching API key')
      return null
    }

    return null
  } catch (error) {
    if (process.env.NODE_ENV === 'development') {
      console.error('Failed to fetch actual API key:', error instanceof Error ? error.message : 'Unknown error')
    }
    return null
  }
}

/**
 * Fetch user's API key from backend with caching
 */
export async function getUserAPIKey(
  authToken: string,
  keyType: APIKeyType = APIKeyType.GEMINI
): Promise<string | null> {
  try {
    // Extract user from auth token for caching
    const { data: { user } } = await supabase.auth.getUser(authToken)
    if (!user) {
      return null
    }

    // Check cache first
    const cachedKey = getCachedKey(user.id, keyType)
    if (cachedKey) {
      if (process.env.NODE_ENV === 'development') {
        console.log(`Using cached ${keyType} key`)
      }
      return cachedKey
    }

    // Fetch the actual key from secure endpoint
    const apiKey = await fetchActualAPIKey(authToken, user.id, keyType)
    
    if (apiKey) {
      // Cache the key
      setCachedKey(user.id, keyType, apiKey)
      return apiKey
    }

    return null
  } catch (error) {
    if (process.env.NODE_ENV === 'development') {
      console.error('Error fetching API key:', error instanceof Error ? error.message : 'Unknown error')
    }
    return null
  }
}

/**
 * Fetch all user's API keys (for display purposes only - returns masked keys)
 */
export async function getUserAPIKeys(authToken: string): Promise<UserAPIKey[]> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      return []
    }

    const data = await response.json()
    return data.api_keys || []
  } catch (error) {
    if (process.env.NODE_ENV === 'development') {
      console.error('Error fetching API keys:', error instanceof Error ? error.message : 'Unknown error')
    }
    return []
  }
}

/**
 * Validate API key format (client-side validation)
 * More flexible patterns to avoid false rejections
 */
export function validateAPIKeyFormat(keyType: APIKeyType, apiKey: string): boolean {
  if (!apiKey || apiKey.length < 10) return false

  switch (keyType) {
    case APIKeyType.GEMINI:
      // Gemini keys typically start with "AIza" but be flexible
      return apiKey.length >= 30 && apiKey.length <= 50
    
    case APIKeyType.TAVILY:
      // Tavily keys are alphanumeric
      return /^[a-zA-Z0-9-_]{20,50}$/.test(apiKey)
    
    case APIKeyType.FIRECRAWL:
      // Firecrawl keys have various formats
      return apiKey.length >= 20 && apiKey.length <= 100
    
    default:
      // For unknown types, just check minimum length
      return apiKey.length >= 10
  }
}

/**
 * Get API key with fallback to environment variable
 */
export async function getAPIKeyWithFallback(
  authToken: string | null,
  keyType: APIKeyType,
  envFallback?: string
): Promise<string | null> {
  // Try to get user's key first if authenticated
  if (authToken) {
    const userKey = await getUserAPIKey(authToken, keyType)
    if (userKey) {
      return userKey
    }
  }

  // Fallback to environment variable
  if (envFallback) {
    if (process.env.NODE_ENV === 'development') {
      console.log(`Using environment fallback for ${keyType}`)
    }
    return envFallback
  }

  return null
}

/**
 * Test API key connectivity
 */
export async function testAPIKeyConnectivity(
  authToken: string,
  keyType: APIKeyType,
  apiKey: string
): Promise<{ success: boolean; message: string }> {
  try {
    const apiUrl = getApiUrl()
    const response = await fetch(`${apiUrl}/api/v1/api-keys/test`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        api_key_type: keyType,
        api_key: apiKey
      })
    })

    if (!response.ok) {
      return { success: false, message: 'Failed to test API key' }
    }

    const data = await response.json()
    return { success: data.success, message: data.message }
  } catch (error) {
    return { success: false, message: 'Network error while testing API key' }
  }
}
