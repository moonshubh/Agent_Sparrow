/**
 * Custom hook for handling API errors with intelligent retry and user feedback
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { ApiUnreachableError } from '@/features/feedme/services/feedme-api'
import { toast } from 'sonner'

type HttpErrorLike = Error & {
  response?: {
    status?: number
  }
  config?: {
    url?: string
  }
}

type NormalizedError = ApiUnreachableError | HttpErrorLike | Error

type AsyncOperation<T = unknown> = () => Promise<T>

interface RetryConfig {
  maxRetries?: number
  baseDelay?: number
  maxDelay?: number
  shouldRetry?: (error: NormalizedError, attemptNumber: number) => boolean
}

interface ApiErrorHandlerOptions {
  onError?: (error: NormalizedError) => void
  onRetry?: (attemptNumber: number) => void
  onSuccess?: () => void
  retryConfig?: RetryConfig
  showToast?: boolean
  toastDuration?: number
}

const isHttpError = (error: unknown): error is HttpErrorLike => {
  if (!error || typeof error !== 'object') {
    return false
  }

  const candidate = error as HttpErrorLike
  const hasResponseStatus = typeof candidate.response?.status === 'number'
  const hasConfigUrl = typeof candidate.config?.url === 'string'

  return hasResponseStatus || hasConfigUrl
}

const normalizeError = (error: unknown): NormalizedError => {
  if (error instanceof ApiUnreachableError) {
    return error
  }

  if (isHttpError(error)) {
    return error
  }

  if (error instanceof Error) {
    return error
  }

  return new Error(typeof error === 'string' ? error : 'Unknown error')
}

const getStatusCode = (error: NormalizedError): number | undefined => {
  return isHttpError(error) ? error.response?.status : undefined
}

const getRequestUrl = (error: NormalizedError): string | undefined => {
  if (error instanceof ApiUnreachableError) {
    return error.url
  }
  return isHttpError(error) ? error.config?.url : undefined
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
  const [lastError, setLastError] = useState<NormalizedError | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastOperationRef = useRef<AsyncOperation | null>(null)
  const retryLastOperationRef = useRef<() => Promise<void>>(async () => {})

  const defaultShouldRetry = useCallback((error: NormalizedError, attemptNumber: number): boolean => {
    if (attemptNumber >= maxRetries) {
      return false
    }

    if (error instanceof ApiUnreachableError) {
      if (error.errorType === 'timeout' || error.errorType === 'network') {
        return true
      }

      if (error.errorType === 'server') {
        return attemptNumber < 2
      }

      return false
    }

    const status = getStatusCode(error)
    if (typeof status === 'number') {
      if (status >= 500) {
        return true
      }

      if (status === 429) {
        return attemptNumber < maxRetries
      }

      if (status >= 400) {
        return false
      }
    }

    return false
  }, [maxRetries])

  const effectiveShouldRetry = useCallback((error: NormalizedError, attemptNumber: number) => {
    return shouldRetry ? shouldRetry(error, attemptNumber) : defaultShouldRetry(error, attemptNumber)
  }, [defaultShouldRetry, shouldRetry])

  const getRetryDelay = useCallback((attemptNumber: number): number => {
    const exponentialDelay = Math.min(baseDelay * Math.pow(2, attemptNumber), maxDelay)
    const jitter = Math.random() * 0.3 * exponentialDelay
    return exponentialDelay + jitter
  }, [baseDelay, maxDelay])

  const cancelRetry = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    setIsRetrying(false)
    setRetryCount(0)
  }, [])

  const resetError = useCallback(() => {
    setLastError(null)
    setRetryCount(0)
    lastOperationRef.current = null
    cancelRetry()
  }, [cancelRetry])

  const handleError = useCallback((rawError: unknown, customMessage?: string) => {
    const error = normalizeError(rawError)
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

      if (['timeout', 'network', 'server'].includes(error.errorType ?? '')) {
        action = () => {
          void retryLastOperationRef.current()
        }
      }
    } else {
      const status = getStatusCode(error)

      if (status === 429) {
        message = 'Too many requests. Please slow down and try again.'
        toastType = 'warning'
      } else if (status && status >= 500) {
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
      const payload = {
        duration: toastDuration,
        action: action
          ? {
              label: 'Retry',
              onClick: action,
            }
          : undefined,
      }

      if (toastType === 'error') {
        toast.error(message, payload)
      } else {
        toast.warning(message, payload)
      }
    }

    onError?.(error)

    console.error('[API Error]', {
      error,
      message,
      timestamp: new Date().toISOString(),
      url: getRequestUrl(error),
    })
  }, [showToast, toastDuration, onError])

  const retryLastOperation = useCallback(async (): Promise<void> => {
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
      if (lastOperationRef.current) {
        try {
          await lastOperationRef.current()
          resetError()
          onSuccess?.()
        } catch (error) {
          handleError(error)
        }
      }
    }, delay)
  }, [isRetrying, lastError, retryCount, effectiveShouldRetry, getRetryDelay, onRetry, resetError, onSuccess, handleError])

  useEffect(() => {
    retryLastOperationRef.current = () => retryLastOperation()
  }, [retryLastOperation])

  const wrapAsync = useCallback(
    async <T,>(
      asyncFn: AsyncOperation<T>,
      customErrorMessage?: string
    ): Promise<T | null> => {
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

export function isApiUnreachableError(error: unknown): error is ApiUnreachableError {
  return error instanceof ApiUnreachableError
}

export function isTimeoutError(error: unknown): boolean {
  return isApiUnreachableError(error) && error.errorType === 'timeout'
}

export function isNetworkError(error: unknown): boolean {
  return isApiUnreachableError(error) && error.errorType === 'network'
}

export function isServerError(error: unknown): boolean {
  return isApiUnreachableError(error) && error.errorType === 'server'
}
