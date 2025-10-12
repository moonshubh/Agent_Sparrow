/**
 * Backend Health Check and Auto-Recovery System
 *
 * This module provides automatic detection and recovery for backend connectivity issues.
 * It includes health monitoring, automatic retry logic, and clear user feedback.
 */

import { ApiUnreachableError } from '@/features/feedme/services/feedme-api'

export interface HealthCheckResult {
  healthy: boolean
  backend_url: string
  timestamp: string
  error?: string
  suggestion?: string
}

export interface BackendHealthMonitor {
  checkHealth(): Promise<HealthCheckResult>
  getLastHealthStatus(): HealthCheckResult | null
  subscribeToHealthChanges(callback: (status: HealthCheckResult) => void): () => void
}

class BackendHealthService implements BackendHealthMonitor {
  private lastHealthStatus: HealthCheckResult | null = null
  private healthCheckInterval: NodeJS.Timeout | null = null
  private subscribers: Set<(status: HealthCheckResult) => void> = new Set()
  private isMonitoring: boolean = false
  private consecutiveFailures: number = 0
  private readonly MAX_CONSECUTIVE_FAILURES = 3
  private readonly HEALTH_CHECK_INTERVAL = 30000 // 30 seconds
  private readonly RECOVERY_CHECK_INTERVAL = 5000 // 5 seconds when unhealthy

  constructor() {
    // Start monitoring on initialization if in browser
    if (typeof window !== 'undefined') {
      this.startMonitoring()
    }
  }

  async checkHealth(): Promise<HealthCheckResult> {
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const healthEndpoint = `${backendUrl}/health`

    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout

      const response = await fetch(healthEndpoint, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
        },
      })

      clearTimeout(timeoutId)

      if (response.ok) {
        this.consecutiveFailures = 0
        const result: HealthCheckResult = {
          healthy: true,
          backend_url: backendUrl,
          timestamp: new Date().toISOString(),
        }
        this.updateHealthStatus(result)
        return result
      } else {
        throw new Error(`Health check returned status: ${response.status}`)
      }
    } catch (error) {
      this.consecutiveFailures++

      let errorMessage = 'Unknown error'
      let suggestion = 'Please check your internet connection and try again.'

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorMessage = 'Backend request timed out'
          suggestion = 'The backend service may be under heavy load. Please wait a moment and try again.'
        } else if (error.message.includes('fetch')) {
          errorMessage = 'Cannot connect to backend service'
          suggestion = this.getConnectionFailureSuggestion(backendUrl)
        } else {
          errorMessage = error.message
        }
      }

      const result: HealthCheckResult = {
        healthy: false,
        backend_url: backendUrl,
        timestamp: new Date().toISOString(),
        error: errorMessage,
        suggestion,
      }

      this.updateHealthStatus(result)
      return result
    }
  }

  private getConnectionFailureSuggestion(backendUrl: string): string {
    const isDevelopment = process.env.NODE_ENV === 'development'

    if (isDevelopment && backendUrl.includes('localhost:8000')) {
      return `The backend service is not running. Please start it using one of these methods:

        1. Run the complete system: ./scripts/start_on_macos/start_system.sh
        2. Start backend only: cd ${process.cwd()} && ./venv/bin/python -m uvicorn app.main:app --port 8000
        3. Use Docker: docker-compose up backend

        The backend must be running on ${backendUrl} for the application to work.`
    }

    return `Cannot connect to the backend service at ${backendUrl}. Please ensure:
      1. The backend service is running
      2. The API URL is correctly configured in your environment
      3. Any firewall or proxy settings allow connections to the backend`
  }

  private updateHealthStatus(status: HealthCheckResult) {
    this.lastHealthStatus = status

    // Notify all subscribers
    this.subscribers.forEach(callback => {
      try {
        callback(status)
      } catch (error) {
        console.error('[Health Monitor] Subscriber error:', error)
      }
    })

    // Adjust monitoring frequency based on health status
    if (!status.healthy && this.isMonitoring) {
      this.adjustMonitoringFrequency(true)
    } else if (status.healthy && this.isMonitoring) {
      this.adjustMonitoringFrequency(false)
    }
  }

  private adjustMonitoringFrequency(isUnhealthy: boolean) {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval)
    }

    const interval = isUnhealthy ? this.RECOVERY_CHECK_INTERVAL : this.HEALTH_CHECK_INTERVAL

    this.healthCheckInterval = setInterval(() => {
      this.checkHealth().catch(error => {
        console.error('[Health Monitor] Check failed:', error)
      })
    }, interval)
  }

  startMonitoring() {
    if (this.isMonitoring) return

    this.isMonitoring = true
    this.checkHealth() // Initial check

    this.healthCheckInterval = setInterval(() => {
      this.checkHealth().catch(error => {
        console.error('[Health Monitor] Check failed:', error)
      })
    }, this.HEALTH_CHECK_INTERVAL)
  }

  stopMonitoring() {
    this.isMonitoring = false
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval)
      this.healthCheckInterval = null
    }
  }

  getLastHealthStatus(): HealthCheckResult | null {
    return this.lastHealthStatus
  }

  subscribeToHealthChanges(callback: (status: HealthCheckResult) => void): () => void {
    this.subscribers.add(callback)

    // Send current status immediately if available
    if (this.lastHealthStatus) {
      callback(this.lastHealthStatus)
    }

    // Return unsubscribe function
    return () => {
      this.subscribers.delete(callback)
    }
  }

  /**
   * Waits for the backend to become healthy, with a timeout
   */
  async waitForHealthy(timeoutMs: number = 30000): Promise<void> {
    const startTime = Date.now()

    while (Date.now() - startTime < timeoutMs) {
      const health = await this.checkHealth()
      if (health.healthy) {
        return
      }

      // Wait before next check
      await new Promise(resolve => setTimeout(resolve, 2000))
    }

    throw new Error(`Backend did not become healthy within ${timeoutMs}ms`)
  }

  /**
   * Enhanced error handler that provides contextual recovery suggestions
   */
  handleApiError(error: Error, context?: string): Error {
    if (error instanceof ApiUnreachableError) {
      const lastHealth = this.getLastHealthStatus()

      if (lastHealth && !lastHealth.healthy) {
        // Enhance the error with health check information
        const enhancedMessage = `${error.message}\n\nBackend Status: Unhealthy\nDetails: ${lastHealth.error}\n\nSuggestion: ${lastHealth.suggestion}`

        return new ApiUnreachableError(
          enhancedMessage,
          error.originalError,
          error.errorType,
          error.url
        )
      }
    }

    return error
  }
}

// Create singleton instance
export const backendHealthMonitor = new BackendHealthService()

// Auto-start monitoring in browser environment
if (typeof window !== 'undefined') {
  backendHealthMonitor.startMonitoring()

  // Log initial status
  backendHealthMonitor.checkHealth().then(status => {
    console.log('[Backend Health]', status.healthy ? 'Healthy' : 'Unhealthy', status)
  })
}

export default backendHealthMonitor
