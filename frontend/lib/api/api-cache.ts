/**
 * API Request Caching and Deduplication System
 * Optimizes API calls by caching responses and preventing duplicate requests
 */

import { API_CONFIG, FEATURE_FLAGS, STORAGE_CONFIG } from '../config/constants'
import { logger } from '../logging/logger'
import { errorHandler, NetworkError } from '../error/error-handler'

// Cache entry structure
interface CacheEntry<T = any> {
  data: T
  timestamp: number
  ttl: number
  etag?: string
  headers?: Record<string, string>
}

// Request queue entry
interface QueueEntry<T = any> {
  promise: Promise<T>
  timestamp: number
  abortController?: AbortController
}

// Cache key generator options
interface CacheKeyOptions {
  url: string
  method?: string
  params?: Record<string, any>
  body?: any
  headers?: Record<string, string>
  excludeHeaders?: string[]
}

// API cache configuration
export interface ApiCacheConfig {
  ttl?: number                    // Time to live in ms
  maxSize?: number                 // Max cache size in bytes
  maxEntries?: number              // Max number of entries
  storage?: 'memory' | 'session'   // Storage type
  deduplicate?: boolean            // Enable request deduplication
  respectCacheHeaders?: boolean    // Respect HTTP cache headers
  excludePatterns?: RegExp[]       // URL patterns to exclude from caching
  includePatterns?: RegExp[]       // URL patterns to include (overrides exclude)
  onCacheHit?: (key: string) => void
  onCacheMiss?: (key: string) => void
  onCacheExpired?: (key: string) => void
}

// Cache statistics
interface CacheStats {
  hits: number
  misses: number
  expired: number
  size: number
  entries: number
}

/**
 * API Cache Manager
 * Handles caching and deduplication of API requests
 */
export class ApiCache {
  private memoryCache = new Map<string, CacheEntry>()
  private requestQueue = new Map<string, QueueEntry>()
  private stats: CacheStats = {
    hits: 0,
    misses: 0,
    expired: 0,
    size: 0,
    entries: 0
  }
  private config: Required<ApiCacheConfig>

  constructor(config: ApiCacheConfig = {}) {
    this.config = {
      ttl: config.ttl ?? API_CONFIG.LIMITS.CACHE_TTL,
      maxSize: config.maxSize ?? STORAGE_CONFIG.LIMITS.MAX_CACHE_SIZE,
      maxEntries: config.maxEntries ?? STORAGE_CONFIG.LIMITS.MAX_CACHE_ITEMS,
      storage: config.storage ?? 'memory',
      deduplicate: config.deduplicate ?? true,
      respectCacheHeaders: config.respectCacheHeaders ?? true,
      excludePatterns: config.excludePatterns ?? [],
      includePatterns: config.includePatterns ?? [],
      onCacheHit: config.onCacheHit ?? (() => {}),
      onCacheMiss: config.onCacheMiss ?? (() => {}),
      onCacheExpired: config.onCacheExpired ?? (() => {})
    }

    // Load existing cache from storage if using session storage
    if (this.config.storage === 'session') {
      this.loadFromStorage()
    }

    // Set up periodic cleanup
    this.startCleanupTimer()
  }

  /**
   * Generate cache key from request options
   */
  generateCacheKey(options: CacheKeyOptions): string {
    const { url, method = 'GET', params, body, headers, excludeHeaders = [] } = options

    const keyParts = [
      method.toUpperCase(),
      url,
      params ? JSON.stringify(this.sortObject(params)) : '',
      body ? JSON.stringify(this.sortObject(body)) : ''
    ]

    // Include relevant headers
    if (headers) {
      const relevantHeaders = Object.entries(headers)
        .filter(([key]) => !excludeHeaders.includes(key.toLowerCase()))
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, value]) => `${key}:${value}`)
        .join(',')

      if (relevantHeaders) {
        keyParts.push(relevantHeaders)
      }
    }

    return keyParts.filter(Boolean).join('|')
  }

  /**
   * Check if URL should be cached
   */
  shouldCache(url: string, method: string = 'GET'): boolean {
    // Only cache GET requests by default
    if (method.toUpperCase() !== 'GET' && method.toUpperCase() !== 'HEAD') {
      return false
    }

    // Check if caching is enabled
    if (!FEATURE_FLAGS.ENABLE_API_CACHING) {
      return false
    }

    // Check include patterns first (higher priority)
    if (this.config.includePatterns.length > 0) {
      return this.config.includePatterns.some(pattern => pattern.test(url))
    }

    // Check exclude patterns
    if (this.config.excludePatterns.length > 0) {
      return !this.config.excludePatterns.some(pattern => pattern.test(url))
    }

    return true
  }

  /**
   * Get cached data
   */
  get<T = any>(key: string): T | null {
    const entry = this.getEntry(key)

    if (!entry) {
      this.stats.misses++
      this.config.onCacheMiss(key)
      return null
    }

    // Check if expired
    if (this.isExpired(entry)) {
      this.stats.expired++
      this.config.onCacheExpired(key)
      this.delete(key)
      return null
    }

    this.stats.hits++
    this.config.onCacheHit(key)
    logger.debug('Cache hit', { key, ttl: entry.ttl })

    return entry.data as T
  }

  /**
   * Set cached data
   */
  set<T = any>(key: string, data: T, options: { ttl?: number; headers?: Record<string, string> } = {}): void {
    const ttl = options.ttl ?? this.config.ttl
    const entry: CacheEntry<T> = {
      data,
      timestamp: Date.now(),
      ttl,
      headers: options.headers
    }

    // Check cache size limits
    if (this.memoryCache.size >= this.config.maxEntries) {
      this.evictOldest()
    }

    // Check memory size limits
    const size = this.estimateSize(entry)
    if (this.stats.size + size > this.config.maxSize) {
      this.evictUntilSize(this.config.maxSize - size)
    }

    this.memoryCache.set(key, entry)
    this.stats.entries = this.memoryCache.size
    this.stats.size += size

    // Persist to storage if configured
    if (this.config.storage === 'session') {
      this.saveToStorage()
    }

    logger.debug('Cache set', { key, ttl, size })
  }

  /**
   * Delete cached entry
   */
  delete(key: string): boolean {
    const entry = this.memoryCache.get(key)
    if (entry) {
      const size = this.estimateSize(entry)
      this.stats.size -= size
    }

    const deleted = this.memoryCache.delete(key)
    this.stats.entries = this.memoryCache.size

    if (deleted && this.config.storage === 'session') {
      this.saveToStorage()
    }

    return deleted
  }

  /**
   * Clear all cached data
   */
  clear(): void {
    this.memoryCache.clear()
    this.requestQueue.clear()
    this.stats = {
      hits: 0,
      misses: 0,
      expired: 0,
      size: 0,
      entries: 0
    }

    if (this.config.storage === 'session') {
      this.clearStorage()
    }

    logger.info('Cache cleared')
  }

  /**
   * Get cache statistics
   */
  getStats(): CacheStats {
    return { ...this.stats }
  }

  /**
   * Deduplicated fetch wrapper
   */
  async fetch<T = any>(
    url: string,
    options: RequestInit & {
      cacheKey?: string
      cacheTTL?: number
      bypassCache?: boolean
      deduplicate?: boolean
    } = {}
  ): Promise<T> {
    const method = options.method || 'GET'
    const cacheKey = options.cacheKey || this.generateCacheKey({
      url,
      method,
      body: options.body,
      headers: options.headers as Record<string, string>
    })

    // Check if caching should be used
    if (!options.bypassCache && this.shouldCache(url, method)) {
      // Check cache first
      const cached = this.get<T>(cacheKey)
      if (cached !== null) {
        return cached
      }

      // Check for in-flight request (deduplication)
      if (this.config.deduplicate && options.deduplicate !== false) {
        const queued = this.requestQueue.get(cacheKey)
        if (queued && Date.now() - queued.timestamp < API_CONFIG.TIMEOUTS.DEFAULT) {
          logger.debug('Request deduplicated', { url, method })
          return queued.promise as Promise<T>
        }
      }
    }

    // Create abort controller
    const abortController = new AbortController()

    // Create fetch promise
    const fetchPromise = this.performFetch<T>(url, {
      ...options,
      signal: abortController.signal
    }).then(result => {
      // Cache successful response
      if (!options.bypassCache && this.shouldCache(url, method)) {
        const ttl = options.cacheTTL ?? this.parseCacheHeaders(result.headers)
        this.set(cacheKey, result.data, { ttl, headers: result.headers })
      }

      // Remove from queue
      this.requestQueue.delete(cacheKey)

      return result.data
    }).catch(error => {
      // Remove from queue on error
      this.requestQueue.delete(cacheKey)
      throw error
    })

    // Add to request queue for deduplication
    if (this.config.deduplicate && options.deduplicate !== false) {
      this.requestQueue.set(cacheKey, {
        promise: fetchPromise,
        timestamp: Date.now(),
        abortController
      })
    }

    return fetchPromise
  }

  /**
   * Perform actual fetch request
   */
  private async performFetch<T>(url: string, options: RequestInit): Promise<{ data: T; headers: Record<string, string> }> {
    try {
      const response = await fetch(url, options)

      if (!response.ok) {
        throw new NetworkError(`HTTP ${response.status}: ${response.statusText}`, {
          code: `HTTP_${response.status}`,
          context: { url, status: response.status }
        })
      }

      // Parse response based on content type
      const contentType = response.headers.get('content-type') || ''
      let data: T

      if (contentType.includes('application/json')) {
        data = await response.json()
      } else if (contentType.includes('text/')) {
        data = await response.text() as any
      } else {
        data = await response.blob() as any
      }

      // Extract headers
      const headers: Record<string, string> = {}
      response.headers.forEach((value, key) => {
        headers[key] = value
      })

      return { data, headers }
    } catch (error) {
      await errorHandler.handle(error as Error)
      throw error
    }
  }

  /**
   * Parse cache control headers
   */
  private parseCacheHeaders(headers?: Record<string, string>): number {
    if (!headers || !this.config.respectCacheHeaders) {
      return this.config.ttl
    }

    // Check Cache-Control header
    const cacheControl = headers['cache-control']
    if (cacheControl) {
      // Parse max-age directive
      const maxAgeMatch = cacheControl.match(/max-age=(\d+)/)
      if (maxAgeMatch) {
        return parseInt(maxAgeMatch[1]) * 1000 // Convert to ms
      }

      // Check for no-cache or no-store
      if (cacheControl.includes('no-cache') || cacheControl.includes('no-store')) {
        return 0
      }
    }

    // Check Expires header
    const expires = headers['expires']
    if (expires) {
      const expiresTime = new Date(expires).getTime()
      const now = Date.now()
      if (expiresTime > now) {
        return expiresTime - now
      }
    }

    return this.config.ttl
  }

  // Private helper methods

  private getEntry(key: string): CacheEntry | undefined {
    return this.memoryCache.get(key)
  }

  private isExpired(entry: CacheEntry): boolean {
    return Date.now() - entry.timestamp > entry.ttl
  }

  private evictOldest(): void {
    const oldest = Array.from(this.memoryCache.entries())
      .sort(([, a], [, b]) => a.timestamp - b.timestamp)[0]

    if (oldest) {
      this.delete(oldest[0])
    }
  }

  private evictUntilSize(targetSize: number): void {
    const entries = Array.from(this.memoryCache.entries())
      .sort(([, a], [, b]) => a.timestamp - b.timestamp)

    for (const [key] of entries) {
      if (this.stats.size <= targetSize) break
      this.delete(key)
    }
  }

  private estimateSize(entry: CacheEntry): number {
    try {
      return JSON.stringify(entry).length * 2 // Approximate bytes (UTF-16)
    } catch {
      return 1024 // Default estimate
    }
  }

  private sortObject(obj: any): any {
    if (obj === null || typeof obj !== 'object') return obj
    if (Array.isArray(obj)) return obj.map(item => this.sortObject(item))

    return Object.keys(obj)
      .sort()
      .reduce((sorted: any, key) => {
        sorted[key] = this.sortObject(obj[key])
        return sorted
      }, {})
  }

  private startCleanupTimer(): void {
    setInterval(() => {
      this.cleanup()
    }, 60000) // Clean up every minute
  }

  private cleanup(): void {
    let cleaned = 0
    for (const [key, entry] of this.memoryCache.entries()) {
      if (this.isExpired(entry)) {
        this.delete(key)
        cleaned++
      }
    }

    if (cleaned > 0) {
      logger.debug('Cache cleanup completed', { cleaned })
    }
  }

  private loadFromStorage(): void {
    if (typeof window === 'undefined') return

    try {
      const stored = sessionStorage.getItem(STORAGE_CONFIG.SESSION_KEYS.API_CACHE)
      if (stored) {
        const data = JSON.parse(stored) as Array<[string, CacheEntry]>
        for (const [key, entry] of data) {
          if (!this.isExpired(entry)) {
            this.memoryCache.set(key, entry)
          }
        }
        this.stats.entries = this.memoryCache.size
        logger.debug('Cache loaded from storage', { entries: this.stats.entries })
      }
    } catch (error) {
      logger.warn('Failed to load cache from storage', { error })
    }
  }

  private saveToStorage(): void {
    if (typeof window === 'undefined') return

    try {
      const data = Array.from(this.memoryCache.entries())
      sessionStorage.setItem(STORAGE_CONFIG.SESSION_KEYS.API_CACHE, JSON.stringify(data))
    } catch (error) {
      logger.warn('Failed to save cache to storage', { error })
    }
  }

  private clearStorage(): void {
    if (typeof window === 'undefined') return

    try {
      sessionStorage.removeItem(STORAGE_CONFIG.SESSION_KEYS.API_CACHE)
    } catch {
      // Ignore storage errors
    }
  }
}

// Create singleton instance
export const apiCache = new ApiCache()

// React hook for using API cache
import { useCallback, useEffect, useState } from 'react'

export function useApiCache<T = any>(
  url: string,
  options?: RequestInit & {
    enabled?: boolean
    cacheKey?: string
    cacheTTL?: number
    bypassCache?: boolean
    onSuccess?: (data: T) => void
    onError?: (error: Error) => void
  }
) {
  const [data, setData] = useState<T | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const fetchData = useCallback(async () => {
    if (!options?.enabled ?? true) return

    setIsLoading(true)
    setError(null)

    try {
      const result = await apiCache.fetch<T>(url, options)
      setData(result)
      options?.onSuccess?.(result)
    } catch (err) {
      const error = err as Error
      setError(error)
      options?.onError?.(error)
    } finally {
      setIsLoading(false)
    }
  }, [url, options])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return {
    data,
    isLoading,
    error,
    refetch: fetchData,
    clearCache: () => apiCache.delete(options?.cacheKey || apiCache.generateCacheKey({ url }))
  }
}

// Export default
export default apiCache