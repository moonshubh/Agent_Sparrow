/**
 * API Key Service for managing user API keys
 * This service handles fetching, caching, and validating user API keys from the backend
 * 
 * FIXED VERSION: Resolves memory leak from incorrect WeakMap usage
 */

import { supabase } from '@/services/supabase/browser-client'
import { getApiUrl } from '@/shared/lib/utils/environment'
import { APIKeyType } from '@/services/api/api-keys'

// Re-export APIKeyType for other components to use
export { APIKeyType }

interface CachedAPIKey {
  key: string
  timestamp: number
  lastAccessed: number
}

interface UserAPIKey {
  api_key_type: APIKeyType
  masked_key: string
  is_active: boolean
}

/**
 * LRU Cache Implementation for API Keys
 * This properly manages memory without the WeakMap confusion
 */
class APIKeyLRUCache {
  private cache: Map<string, Map<APIKeyType, CachedAPIKey>> = new Map()
  private accessOrder: Map<string, number> = new Map()
  private accessCounter: number = 0
  private readonly maxSize: number
  private readonly ttl: number

  constructor(maxSize: number = 50, ttlMinutes: number = 5) {
    this.maxSize = maxSize
    this.ttl = ttlMinutes * 60 * 1000
  }

  get(userId: string, keyType: APIKeyType): string | null {
    const userCache = this.cache.get(userId)
    if (!userCache) return null

    const cached = userCache.get(keyType)
    if (!cached) return null

    const now = Date.now()
    
    // Check TTL
    if (now - cached.timestamp > this.ttl) {
      userCache.delete(keyType)
      if (userCache.size === 0) {
        this.cache.delete(userId)
        this.accessOrder.delete(userId)
      }
      return null
    }

    // Update access tracking for LRU
    cached.lastAccessed = now
    this.accessOrder.set(userId, ++this.accessCounter)
    
    return cached.key
  }

  set(userId: string, keyType: APIKeyType, key: string): void {
    // Get or create user cache
    let userCache = this.cache.get(userId)
    if (!userCache) {
      userCache = new Map()
      this.cache.set(userId, userCache)
    }

    const now = Date.now()
    userCache.set(keyType, {
      key,
      timestamp: now,
      lastAccessed: now
    })

    // Update access order
    this.accessOrder.set(userId, ++this.accessCounter)

    // Enforce size limit with LRU eviction
    this.evictIfNeeded()
  }

  clear(userId?: string): void {
    if (userId) {
      this.cache.delete(userId)
      this.accessOrder.delete(userId)
    } else {
      this.cache.clear()
      this.accessOrder.clear()
      this.accessCounter = 0
    }
  }

  private evictIfNeeded(): void {
    if (this.cache.size <= this.maxSize) return

    // Sort by access order (LRU)
    const sorted = Array.from(this.accessOrder.entries())
      .sort((a, b) => a[1] - b[1])

    // Remove oldest entries
    const toRemove = this.cache.size - this.maxSize
    for (let i = 0; i < toRemove; i++) {
      const [userId] = sorted[i]
      this.cache.delete(userId)
      this.accessOrder.delete(userId)
    }
  }

  cleanup(): void {
    const now = Date.now()
    const toDelete: string[] = []

    // Remove expired entries
    for (const [userId, userCache] of this.cache.entries()) {
      const keysToDelete: APIKeyType[] = []
      
      for (const [keyType, data] of userCache.entries()) {
        if (now - data.timestamp > this.ttl) {
          keysToDelete.push(keyType)
        }
      }
      
      keysToDelete.forEach(keyType => userCache.delete(keyType))
      
      if (userCache.size === 0) {
        toDelete.push(userId)
      }
    }

    toDelete.forEach(userId => {
      this.cache.delete(userId)
      this.accessOrder.delete(userId)
    })
  }

  // Get cache statistics for monitoring
  getStats(): { size: number; users: number; keys: number } {
    let totalKeys = 0
    for (const userCache of this.cache.values()) {
      totalKeys += userCache.size
    }
    return {
      size: this.cache.size,
      users: this.cache.size,
      keys: totalKeys
    }
  }
}

// Create singleton cache instance
const apiKeyCache = new APIKeyLRUCache(50, 5) // 50 users max, 5 minute TTL

// Set up periodic cleanup
let cleanupInterval: NodeJS.Timeout | null = null

if (typeof window !== 'undefined') {
  // Run cleanup every minute
  cleanupInterval = setInterval(() => {
    apiKeyCache.cleanup()
    
    // Log cache stats in development
    if (process.env.NODE_ENV === 'development') {
      const stats = apiKeyCache.getStats()
      console.log(`API Key Cache: ${stats.users} users, ${stats.keys} keys`)
    }
  }, 60 * 1000)

  // Clean up on page unload
  window.addEventListener('beforeunload', () => {
    if (cleanupInterval) {
      clearInterval(cleanupInterval)
      cleanupInterval = null
    }
    apiKeyCache.clear()
  })
}

/**
 * Clear cache for a specific user
 */
export function clearUserAPIKeyCache(userId: string) {
  apiKeyCache.clear(userId)
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
    const cachedKey = apiKeyCache.get(user.id, keyType)
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
      apiKeyCache.set(user.id, keyType, apiKey)
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
    console.error('Network error while testing API key (fixed):', error)
    return { success: false, message: 'Network error while testing API key' }
  }
}

// Export cache stats for monitoring (development only)
export function getCacheStats() {
  if (process.env.NODE_ENV === 'development') {
    return apiKeyCache.getStats()
  }
  return null
}
