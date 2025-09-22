'use client'

import React, { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle, RefreshCw, XCircle } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import backendHealthMonitor, { HealthCheckResult } from '@/lib/backend-health-check'

export interface BackendHealthAlertProps {
  className?: string
  showWhenHealthy?: boolean
  autoHide?: boolean
  autoHideDelay?: number
}

export function BackendHealthAlert({
  className = '',
  showWhenHealthy = false,
  autoHide = true,
  autoHideDelay = 5000,
}: BackendHealthAlertProps) {
  const [healthStatus, setHealthStatus] = useState<HealthCheckResult | null>(null)
  const [isVisible, setIsVisible] = useState(false)
  const [isChecking, setIsChecking] = useState(false)

  useEffect(() => {
    // Subscribe to health changes
    const unsubscribe = backendHealthMonitor.subscribeToHealthChanges((status) => {
      setHealthStatus(status)

      // Show alert based on health status
      if (!status.healthy) {
        setIsVisible(true)
      } else if (showWhenHealthy) {
        setIsVisible(true)

        // Auto-hide after delay if healthy
        if (autoHide) {
          setTimeout(() => {
            setIsVisible(false)
          }, autoHideDelay)
        }
      } else {
        setIsVisible(false)
      }
    })

    // Perform initial health check
    backendHealthMonitor.checkHealth().catch(console.error)

    return unsubscribe
  }, [showWhenHealthy, autoHide, autoHideDelay])

  const handleRetryCheck = async () => {
    setIsChecking(true)
    try {
      await backendHealthMonitor.checkHealth()
    } catch (error) {
      console.error('Health check failed:', error)
    } finally {
      setIsChecking(false)
    }
  }

  if (!isVisible || !healthStatus) {
    return null
  }

  const isHealthy = healthStatus.healthy
  const isDevelopment = process.env.NODE_ENV === 'development'

  return (
    <Alert
      className={`${className} ${isHealthy ? 'border-green-500' : 'border-red-500'}`}
      variant={isHealthy ? 'default' : 'destructive'}
    >
      <div className="flex items-start gap-3">
        {isHealthy ? (
          <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
        ) : (
          <XCircle className="h-5 w-5 text-red-500 mt-0.5" />
        )}

        <div className="flex-1">
          <AlertTitle className="mb-2">
            {isHealthy ? 'Backend Connected' : 'Backend Connection Issue'}
          </AlertTitle>

          <AlertDescription className="space-y-2">
            {isHealthy ? (
              <p>Successfully connected to backend service at {healthStatus.backend_url}</p>
            ) : (
              <>
                <p className="font-medium">{healthStatus.error}</p>

                {healthStatus.suggestion && (
                  <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-900 rounded-md">
                    <p className="text-sm whitespace-pre-wrap">{healthStatus.suggestion}</p>
                  </div>
                )}

                {isDevelopment && (
                  <div className="mt-3 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-md border border-yellow-200 dark:border-yellow-800">
                    <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200 mb-2">
                      Developer Quick Start:
                    </p>
                    <code className="text-xs block p-2 bg-gray-900 text-gray-100 rounded">
                      # From your project root:
                      ./scripts/start_on_macos/start_system.sh
                    </code>
                  </div>
                )}
              </>
            )}
          </AlertDescription>
        </div>

        {!isHealthy && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleRetryCheck}
            disabled={isChecking}
            className="mt-1"
          >
            {isChecking ? (
              <>
                <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                Checking...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4 mr-1" />
                Retry
              </>
            )}
          </Button>
        )}
      </div>
    </Alert>
  )
}

export default BackendHealthAlert