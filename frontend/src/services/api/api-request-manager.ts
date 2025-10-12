/**
 * Request Manager for API calls
 * Handles request deduplication, cancellation, and cleanup
 */

interface ActiveRequest {
  controller: AbortController
  timestamp: number
  url: string
}

class RequestManager {
  private activeRequests = new Map<string, ActiveRequest>()
  private readonly MAX_REQUEST_AGE = 30000 // 30 seconds
  private cleanupTimer: NodeJS.Timeout | null = null

  constructor() {
    // Start periodic cleanup
    this.startCleanup()
  }

  /**
   * Get or create an abort controller for a request
   */
  getController(key: string, url: string): AbortController {
    const existing = this.activeRequests.get(key)

    if (existing) {
      // Cancel the existing request
      existing.controller.abort()
      console.log(`[RequestManager] Cancelled duplicate request: ${key}`)
    }

    // Create new controller
    const controller = new AbortController()
    this.activeRequests.set(key, {
      controller,
      timestamp: Date.now(),
      url,
    })

    return controller
  }

  /**
   * Remove a request from tracking
   */
  removeRequest(key: string): void {
    this.activeRequests.delete(key)
  }

  /**
   * Cancel a specific request
   */
  cancelRequest(key: string): boolean {
    const request = this.activeRequests.get(key)
    if (request) {
      request.controller.abort()
      this.activeRequests.delete(key)
      return true
    }
    return false
  }

  /**
   * Cancel all active requests
   */
  cancelAll(): void {
    this.activeRequests.forEach((request, key) => {
      request.controller.abort()
      console.log(`[RequestManager] Cancelled request: ${key}`)
    })
    this.activeRequests.clear()
  }

  /**
   * Clean up old requests
   */
  private cleanup(): void {
    const now = Date.now()
    const staleKeys: string[] = []

    this.activeRequests.forEach((request, key) => {
      if (now - request.timestamp > this.MAX_REQUEST_AGE) {
        staleKeys.push(key)
      }
    })

    staleKeys.forEach(key => {
      const request = this.activeRequests.get(key)
      if (request) {
        console.warn(`[RequestManager] Cleaning up stale request: ${key}`)
        request.controller.abort()
        this.activeRequests.delete(key)
      }
    })
  }

  /**
   * Start periodic cleanup
   */
  private startCleanup(): void {
    this.stopCleanup()
    this.cleanupTimer = setInterval(() => this.cleanup(), 10000) // Every 10 seconds
  }

  /**
   * Stop periodic cleanup
   */
  private stopCleanup(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer)
      this.cleanupTimer = null
    }
  }

  /**
   * Get active request count
   */
  getActiveCount(): number {
    return this.activeRequests.size
  }

  /**
   * Get active request details
   */
  getActiveRequests(): Array<{ key: string; url: string; age: number }> {
    const now = Date.now()
    return Array.from(this.activeRequests.entries()).map(([key, request]) => ({
      key,
      url: request.url,
      age: now - request.timestamp,
    }))
  }

  /**
   * Destroy the manager
   */
  destroy(): void {
    this.cancelAll()
    this.stopCleanup()
  }
}

// Create singleton instance
export const requestManager = new RequestManager()

// Clean up on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    requestManager.destroy()
  })
}