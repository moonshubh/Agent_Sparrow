/**
 * LRU Cache implementation for API keys
 * Production-ready implementation without memory leaks
 */

import { APIKeyType } from '@/services/api/api-keys'

interface CachedAPIKey {
  key: string
  timestamp: number
}

interface CacheStats {
  hits: number
  misses: number
  evictions: number
  size: number
}

/**
 * Proper LRU (Least Recently Used) cache implementation
 * - No WeakMap confusion, uses proper Map-based LRU
 * - Automatic TTL-based expiration
 * - Size-based eviction when cache is full
 * - Cache statistics for monitoring
 */
export class APIKeyLRUCache {
  private cache: Map<string, Map<APIKeyType, CachedAPIKey>> = new Map()
  private accessOrder: Map<string, number> = new Map()
  private stats: CacheStats = { hits: 0, misses: 0, evictions: 0, size: 0 }
  
  private readonly maxSize: number
  private readonly ttl: number
  private cleanupTimer: NodeJS.Timeout | null = null
  private accessCounter = 0

  constructor(maxSize = 50, ttlMinutes = 5) {
    this.maxSize = maxSize
    this.ttl = ttlMinutes * 60 * 1000
    
    // Start cleanup timer if in browser environment
    if (typeof window !== 'undefined') {
      this.startCleanupTimer()
      
      // Clean up on window unload
      window.addEventListener('beforeunload', () => this.destroy())
    }
  }

  /**
   * Get a cached API key
   */
  get(userId: string, keyType: APIKeyType): string | null {
    const userCache = this.cache.get(userId)
    if (!userCache) {
      this.stats.misses++
      return null
    }

    const cached = userCache.get(keyType)
    if (!cached) {
      this.stats.misses++
      return null
    }

    // Check if expired
    if (Date.now() - cached.timestamp > this.ttl) {
      userCache.delete(keyType)
      if (userCache.size === 0) {
        this.cache.delete(userId)
        this.accessOrder.delete(userId)
      }
      this.stats.misses++
      this.stats.evictions++
      return null
    }

    // Update access order for LRU
    this.accessOrder.set(userId, ++this.accessCounter)
    this.stats.hits++
    
    return cached.key
  }

  /**
   * Set a cached API key
   */
  set(userId: string, keyType: APIKeyType, key: string): void {
    // Check if we need to evict based on size
    if (!this.cache.has(userId) && this.cache.size >= this.maxSize) {
      this.evictLeastRecentlyUsed()
    }

    // Get or create user cache
    let userCache = this.cache.get(userId)
    if (!userCache) {
      userCache = new Map()
      this.cache.set(userId, userCache)
    }

    // Set the key
    userCache.set(keyType, {
      key,
      timestamp: Date.now()
    })

    // Update access order
    this.accessOrder.set(userId, ++this.accessCounter)
    this.stats.size = this.cache.size
  }

  /**
   * Clear cache for a specific user
   */
  clearUser(userId: string): void {
    if (this.cache.delete(userId)) {
      this.accessOrder.delete(userId)
      this.stats.size = this.cache.size
    }
  }

  /**
   * Clear entire cache
   */
  clear(): void {
    this.cache.clear()
    this.accessOrder.clear()
    this.stats.size = 0
    this.stats.evictions += this.cache.size
  }

  /**
   * Get cache statistics
   */
  getStats(): Readonly<CacheStats> {
    return { ...this.stats, size: this.cache.size }
  }

  /**
   * Destroy the cache and clean up resources
   */
  destroy(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer)
      this.cleanupTimer = null
    }
    this.clear()
  }

  /**
   * Evict the least recently used entry
   */
  private evictLeastRecentlyUsed(): void {
    let lruUserId: string | null = null
    let minAccessTime = Infinity

    for (const [userId, accessTime] of this.accessOrder.entries()) {
      if (accessTime < minAccessTime) {
        minAccessTime = accessTime
        lruUserId = userId
      }
    }

    if (lruUserId) {
      this.cache.delete(lruUserId)
      this.accessOrder.delete(lruUserId)
      this.stats.evictions++
      this.stats.size = this.cache.size
    }
  }

  /**
   * Remove expired entries
   */
  private removeExpiredEntries(): void {
    const now = Date.now()
    const usersToDelete: string[] = []

    for (const [userId, userCache] of this.cache.entries()) {
      const keysToDelete: APIKeyType[] = []

      for (const [keyType, cached] of userCache.entries()) {
        if (now - cached.timestamp > this.ttl) {
          keysToDelete.push(keyType)
          this.stats.evictions++
        }
      }

      // Delete expired keys
      keysToDelete.forEach(keyType => userCache.delete(keyType))

      // If user has no more cached keys, mark for deletion
      if (userCache.size === 0) {
        usersToDelete.push(userId)
      }
    }

    // Delete empty user caches
    usersToDelete.forEach(userId => {
      this.cache.delete(userId)
      this.accessOrder.delete(userId)
    })

    this.stats.size = this.cache.size
  }

  /**
   * Start the cleanup timer
   */
  private startCleanupTimer(): void {
    // Clean up expired entries every minute
    this.cleanupTimer = setInterval(() => {
      this.removeExpiredEntries()
    }, 60 * 1000)
  }
}

// Create singleton instance
let cacheInstance: APIKeyLRUCache | null = null

/**
 * Get the singleton cache instance
 */
export function getAPIKeyCache(): APIKeyLRUCache {
  if (!cacheInstance) {
    cacheInstance = new APIKeyLRUCache()
  }
  return cacheInstance
}

/**
 * Reset the cache (mainly for testing)
 */
export function resetAPIKeyCache(): void {
  if (cacheInstance) {
    cacheInstance.destroy()
    cacheInstance = null
  }
}