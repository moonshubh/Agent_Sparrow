/**
 * API Performance Monitor
 * Tracks API call performance and provides insights for optimization
 */

import { useEffect, useState } from 'react'
import { logger } from '@/shared/logging/logger'
import { API_CONFIG } from '@/shared/config/constants'
import { secureSessionStorage } from '@/services/security/modules/secure-storage'

interface ApiCallMetrics {
  url: string
  method: string
  duration: number
  status: number | 'timeout' | 'error'
  timestamp: Date
  size?: number
}

class ApiMonitor {
  private metrics: ApiCallMetrics[] = []
  private readonly maxMetrics = 100
  private slowRequestThreshold: number = API_CONFIG.PERFORMANCE.SLOW_REQUEST_THRESHOLD
  private listeners: Set<(metrics: ApiCallMetrics) => void> = new Set()

  // Track an API call
  track(metrics: ApiCallMetrics): void {
    this.metrics.push(metrics)

    // Keep only recent metrics
    if (this.metrics.length > this.maxMetrics) {
      this.metrics = this.metrics.slice(-this.maxMetrics)
    }

    // Notify listeners
    this.listeners.forEach(listener => listener(metrics))

    // Log slow requests
    if (metrics.duration > this.slowRequestThreshold) {
      logger.warn('Slow request detected', {
        url: metrics.url,
        duration: `${(metrics.duration / 1000).toFixed(2)}s`,
        status: metrics.status,
      })
    }

    // Store in secure storage for debugging
    if (typeof window !== 'undefined') {
      secureSessionStorage.set('api_metrics', this.getRecentMetrics(20), {
        expiry: 3600000, // 1 hour
        encrypt: false // Performance metrics don't need encryption
      }).catch(() => {
        // Ignore storage errors
      })
    }
  }

  // Get recent metrics
  getRecentMetrics(count?: number): ApiCallMetrics[] {
    return count ? this.metrics.slice(-count) : this.metrics
  }

  // Get performance statistics
  getStatistics(timeWindowMs: number = API_CONFIG.LIMITS.RATE_LIMIT_WINDOW) {
    const now = Date.now()
    const recentMetrics = this.metrics.filter(
      m => now - m.timestamp.getTime() < timeWindowMs
    )

    if (recentMetrics.length === 0) {
      return null
    }

    const durations = recentMetrics.map(m => m.duration)
    const successfulCalls = recentMetrics.filter(
      m => typeof m.status === 'number' && m.status < 400
    )

    return {
      totalCalls: recentMetrics.length,
      successfulCalls: successfulCalls.length,
      failedCalls: recentMetrics.length - successfulCalls.length,
      averageDuration: durations.reduce((a, b) => a + b, 0) / durations.length,
      medianDuration: this.getMedian(durations),
      p95Duration: this.getPercentile(durations, 95),
      slowRequests: recentMetrics.filter(m => m.duration > this.slowRequestThreshold).length,
      timeouts: recentMetrics.filter(m => m.status === 'timeout').length,
      errors: recentMetrics.filter(m => m.status === 'error').length,
    }
  }

  // Get endpoints with performance issues
  getProblematicEndpoints(threshold: number = 5): Map<string, number> {
    const problems = new Map<string, number>()

    this.metrics.forEach(metric => {
      if (
        metric.duration > this.slowRequestThreshold ||
        metric.status === 'timeout' ||
        metric.status === 'error' ||
        (typeof metric.status === 'number' && metric.status >= 500)
      ) {
        const key = `${metric.method} ${metric.url.split('?')[0]}`
        problems.set(key, (problems.get(key) || 0) + 1)
      }
    })

    // Filter by threshold
    const filtered = new Map<string, number>()
    problems.forEach((count, endpoint) => {
      if (count >= threshold) {
        filtered.set(endpoint, count)
      }
    })

    return filtered
  }

  // Subscribe to metrics updates
  subscribe(listener: (metrics: ApiCallMetrics) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  // Clear all metrics
  clear(): void {
    this.metrics = []
    if (typeof window !== 'undefined') {
      secureSessionStorage.remove('api_metrics')
    }
  }

  // Helper methods
  private getMedian(values: number[]): number {
    if (values.length === 0) return 0
    const sorted = [...values].sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
  }

  private getPercentile(values: number[], percentile: number): number {
    if (values.length === 0) return 0
    const sorted = [...values].sort((a, b) => a - b)
    const index = Math.ceil((percentile / 100) * sorted.length) - 1
    return sorted[Math.max(0, index)]
  }

  // Set custom thresholds
  setSlowRequestThreshold(ms: number): void {
    this.slowRequestThreshold = ms
  }

  // Export metrics for analysis
  exportMetrics(): string {
    return JSON.stringify(this.metrics, null, 2)
  }

  // Get a performance report
  getPerformanceReport(): string {
    const stats = this.getStatistics()
    const problems = this.getProblematicEndpoints()

    let report = '=== API Performance Report ===\n\n'

    if (stats) {
      report += 'Statistics (last minute):\n'
      report += `  Total Calls: ${stats.totalCalls}\n`
      report += `  Success Rate: ${((stats.successfulCalls / stats.totalCalls) * 100).toFixed(1)}%\n`
      report += `  Avg Duration: ${(stats.averageDuration / 1000).toFixed(2)}s\n`
      report += `  Median Duration: ${(stats.medianDuration / 1000).toFixed(2)}s\n`
      report += `  95th Percentile: ${(stats.p95Duration / 1000).toFixed(2)}s\n`
      report += `  Slow Requests: ${stats.slowRequests}\n`
      report += `  Timeouts: ${stats.timeouts}\n`
      report += `  Errors: ${stats.errors}\n`
    }

    if (problems.size > 0) {
      report += '\nProblematic Endpoints:\n'
      problems.forEach((count, endpoint) => {
        report += `  ${endpoint}: ${count} issues\n`
      })
    }

    return report
  }
}

// Create singleton instance
export const apiMonitor = new ApiMonitor()

// Wrapper to track fetch requests
export function trackFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const startTime = Date.now()
  const method = options.method || 'GET'

  return fetch(url, options)
    .then(response => {
      const duration = Date.now() - startTime

      apiMonitor.track({
        url,
        method,
        duration,
        status: response.status,
        timestamp: new Date(),
        size: parseInt(response.headers.get('content-length') || '0', 10),
      })

      return response
    })
    .catch(error => {
      const duration = Date.now() - startTime
      const isTimeout = error.name === 'AbortError'

      apiMonitor.track({
        url,
        method,
        duration,
        status: isTimeout ? 'timeout' : 'error',
        timestamp: new Date(),
      })

      throw error
    })
}

// React hook for monitoring API performance
export function useApiMonitor() {
  const [stats, setStats] = useState(apiMonitor.getStatistics())
  const [problems, setProblems] = useState(apiMonitor.getProblematicEndpoints())

  useEffect(() => {
    // Update stats periodically
    const interval = setInterval(() => {
      setStats(apiMonitor.getStatistics())
      setProblems(apiMonitor.getProblematicEndpoints())
    }, API_CONFIG.PERFORMANCE.WARNING_THRESHOLD)

    // Subscribe to real-time updates
    const unsubscribe = apiMonitor.subscribe(() => {
      setStats(apiMonitor.getStatistics())
      setProblems(apiMonitor.getProblematicEndpoints())
    })

    return () => {
      clearInterval(interval)
      unsubscribe()
    }
  }, [])

  return {
    stats,
    problems,
    clearMetrics: () => apiMonitor.clear(),
    exportReport: () => apiMonitor.getPerformanceReport(),
  }
}
