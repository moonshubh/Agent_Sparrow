/**
 * Custom hook for handling API errors with intelligent retry and user feedback
 */

import { useState, useCallback, useRef } from 'react'
import { ApiUnreachableError } from '@/lib/feedme-api'
import { toast } from 'sonner'

interface RetryConfig {
  maxRetries?: number
  baseDelay?: number
  maxDelay?: number
  shouldRetry?: (error: any, attemptNumber: number) => boolean
}

interface ApiErrorHandlerOptions {
  onError?: (error: any) => void
  onRetry?: (attemptNumber: number) => void
  onSuccess?: () => void
  retryConfig?: RetryConfig
  showToast?: boolean
  toastDuration?: number
}

export function useApiErrorHandler(options: ApiErrorHandlerOptions = {}) {
  const {
    onError,
    onRetry,
    onSuccess,
    retryConfig = {},
    showToast = true,
    toastDuration = 5000,
  } = options

  const {
    maxRetries = 3,
    baseDelay = 1000,
    maxDelay = 10000,
    shouldRetry,
  } = retryConfig

  const [isRetrying, setIsRetrying] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const [lastError, setLastError] = useState<Error | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastOperationRef = useRef<(() => Promise<any>) | null>(null)

  // Default retry logic
  const defaultShouldRetry = useCallback((error: any, attemptNumber: number): boolean => {
    if (attemptNumber >= maxRetries) return false

    if (error instanceof ApiUnreachableError) {
      // Always retry timeout errors (up to limit)
      if (error.errorType === 'timeout') return true
      // Retry network errors
      if (error.errorType === 'network') return true
      // Retry server errors with exponential backoff
      if (error.errorType === 'server') return attemptNumber < 2
    }

    // Don't retry client errors (4xx)
    if (error?.response?.status >= 400 && error?.response?.status < 500) {
      return false
    }

    return false
  }, [maxRetries])

  // Use provided shouldRetry or fall back to default
  const effectiveShouldRetry = shouldRetry || defaultShouldRetry

  // Calculate retry delay with exponential backoff and jitter
  const getRetryDelay = useCallback((attemptNumber: number): number => {
    const exponentialDelay = Math.min(baseDelay * Math.pow(2, attemptNumber), maxDelay)
    const jitter = Math.random() * 0.3 * exponentialDelay // 30% jitter
    return exponentialDelay + jitter
  }, [baseDelay, maxDelay])

  // Handle API errors with intelligent messaging
  const handleError = useCallback((error: any, customMessage?: string) => {
    setLastError(error)

    let message = customMessage || 'An unexpected error occurred'
    let toastType: 'error' | 'warning' = 'error'
    let action: (() => void) | undefined

    if (error instanceof ApiUnreachableError) {
      switch (error.errorType) {
        case 'timeout':
          message = 'The request is taking longer than expected. The server might be busy.'
          toastType = 'warning'
          break
        case 'network':
          message = 'Network connection issue. Please check your internet.'
          break
        case 'server':
          message = 'The service is temporarily unavailable. Please try again later.'
          toastType = 'warning'
          break
        default:
          message = error.message
      }

      // Add retry action for certain error types
      if (['timeout', 'network', 'server'].includes(error.errorType || '')) {
        action = () => void retryLastOperation()
      }
    } else if (error?.response) {
      // Handle HTTP error responses
      const status = error.response.status
      if (status === 429) {
        message = 'Too many requests. Please slow down and try again.'
        toastType = 'warning'
      } else if (status >= 500) {
        message = 'Server error. Our team has been notified.'
      } else if (status === 404) {
        message = 'The requested resource was not found.'
      } else if (status === 403) {
        message = 'You do not have permission to perform this action.'
      } else if (status === 401) {
        message = 'Your session has expired. Please log in again.'
      }
    }

    if (showToast) {
      if (toastType === 'error') {
        toast.error(message, {
          duration: toastDuration,
          action: action ? {
            label: 'Retry',
            onClick: action,
          } : undefined,
        })
      } else {
        toast.warning(message, {
          duration: toastDuration,
          action: action ? {
            label: 'Retry',
            onClick: action,
          } : undefined,
        })
      }
    }

    // Call custom error handler
    onError?.(error)

    // Log error for monitoring
    console.error('[API Error]', {
      error,
      message,
      timestamp: new Date().toISOString(),
      url: error instanceof ApiUnreachableError ? error.url : error?.config?.url,
    })
  }, [showToast, toastDuration, onError])

  // Retry the last failed operation
  const retryLastOperation = useCallback(async () => {
    if (isRetrying || !lastError || !lastOperationRef.current) {
      if (!lastOperationRef.current) {
        toast.error('No operation to retry. Please try again manually.')
      }
      return
    }

    const attemptNumber = retryCount + 1

    if (!effectiveShouldRetry(lastError, attemptNumber)) {
      toast.error('Unable to retry. Please try again manually.')
      return
    }

    setIsRetrying(true)
    setRetryCount(attemptNumber)

    const delay = getRetryDelay(attemptNumber)

    toast.info(`Retrying in ${Math.round(delay / 1000)} seconds...`, {
      duration: delay,
    })

    onRetry?.(attemptNumber)

    retryTimeoutRef.current = setTimeout(async () => {
      setIsRetrying(false)
      // Re-execute the failed operation
      if (lastOperationRef.current) {
        try {
          const result = await lastOperationRef.current()
          resetError()
          onSuccess?.()
          return result
        } catch (error) {
          handleError(error)
        }
      }
    }, delay)
  }, [isRetrying, lastError, retryCount, effectiveShouldRetry, getRetryDelay, onRetry, resetError, onSuccess, handleError])

  // Cancel any pending retries
  const cancelRetry = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    setIsRetrying(false)
    setRetryCount(0)
  }, [])

  // Reset error state
  const resetError = useCallback(() => {
    setLastError(null)
    setRetryCount(0)
    lastOperationRef.current = null
    cancelRetry()
  }, [cancelRetry])

  // Wrap async operations with error handling
  const wrapAsync = useCallback(
    async <T,>(
      asyncFn: () => Promise<T>,
      customErrorMessage?: string
    ): Promise<T | null> => {
      // Store the operation for potential retry
      lastOperationRef.current = asyncFn

      try {
        const result = await asyncFn()
        resetError()
        onSuccess?.()
        return result
      } catch (error) {
        handleError(error, customErrorMessage)
        return null
      }
    },
    [handleError, resetError, onSuccess]
  )

  return {
    handleError,
    wrapAsync,
    retryLastOperation,
    cancelRetry,
    resetError,
    isRetrying,
    retryCount,
    lastError,
  }
}

// Export specific error type guards
export function isApiUnreachableError(error: any): error is ApiUnreachableError {
  return error instanceof ApiUnreachableError
}

export function isTimeoutError(error: any): boolean {
  return isApiUnreachableError(error) && error.errorType === 'timeout'
}

export function isNetworkError(error: any): boolean {
  return isApiUnreachableError(error) && error.errorType === 'network'
}

export function isServerError(error: any): boolean {
  return isApiUnreachableError(error) && error.errorType === 'server'
}