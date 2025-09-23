/**
 * Unified Error Boundary Component
 * Consolidates all error boundary logic into a single, feature-rich component
 */

'use client'

import React from 'react'
import { AlertCircle, RefreshCw, Home, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useRouter } from 'next/navigation'
import { logger } from '@/lib/logging/logger'
import { ERROR_CONFIG } from '@/lib/config/constants'

// Error boundary modes
export enum ErrorBoundaryMode {
  FULL = 'full',      // Full page error with navigation
  DIALOG = 'dialog',  // Compact dialog error
  INLINE = 'inline',  // Inline error message
  SILENT = 'silent'   // Silent recovery with logging only
}

// Error boundary configuration
export interface ErrorBoundaryConfig {
  mode?: ErrorBoundaryMode
  fallback?: React.ReactNode
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void | Promise<void>
  onReset?: () => void | Promise<void>
  resetKeys?: Array<string | number>
  resetOnPropsChange?: boolean
  isolate?: boolean
  autoRecover?: boolean
  autoRecoverDelay?: number
  maxErrorCount?: number
  showDetails?: boolean
  customTitle?: string
  customMessage?: string
  homeRoute?: string
  ariaLabel?: string
  testId?: string
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: React.ErrorInfo | null
  errorCount: number
  showDetails: boolean
  isRecovering: boolean
}

export class UnifiedErrorBoundary extends React.Component<
  ErrorBoundaryConfig & { children: React.ReactNode },
  ErrorBoundaryState
> {
  private resetTimeoutId: ReturnType<typeof setTimeout> | null = null
  private previousResetKeys: Array<string | number> = []
  private errorCountResetTimeout: ReturnType<typeof setTimeout> | null = null

  constructor(props: ErrorBoundaryConfig & { children: React.ReactNode }) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
      showDetails: false,
      isRecovering: false
    }
    this.previousResetKeys = props.resetKeys || []
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    const { mode = ErrorBoundaryMode.FULL, onError, isolate } = this.props

    // Update state with error info
    this.setState(prevState => ({
      errorInfo,
      errorCount: prevState.errorCount + 1
    }))

    // Log error based on mode
    if (mode !== ErrorBoundaryMode.SILENT) {
      logger.error('Error boundary caught error', {
        error: {
          message: error.message,
          stack: error.stack,
          name: error.name
        },
        errorInfo: {
          componentStack: errorInfo.componentStack
        },
        mode,
        errorCount: this.state.errorCount + 1,
        isolate
      })
    }

    // Call custom error handler
    if (onError) {
      try {
        Promise.resolve(onError(error, errorInfo)).catch(handlerError => {
          logger.error('Error in custom error handler', { error: handlerError })
        })
      } catch (handlerError) {
        logger.error('Sync error in custom error handler', { error: handlerError })
      }
    }

    // Setup auto-recovery if enabled
    this.setupAutoRecovery()

    // Reset error count after window
    this.setupErrorCountReset()
  }

  componentDidUpdate(prevProps: ErrorBoundaryConfig & { children: React.ReactNode }) {
    const { resetKeys, resetOnPropsChange } = this.props
    const { hasError } = this.state

    // Reset on prop changes if enabled
    if (hasError && prevProps.children !== this.props.children && resetOnPropsChange) {
      this.handleReset()
    }

    // Reset when resetKeys change
    if (resetKeys && this.previousResetKeys) {
      const hasResetKeyChanged = resetKeys.some(
        (key, idx) => key !== this.previousResetKeys[idx]
      )
      if (hasResetKeyChanged) {
        this.previousResetKeys = resetKeys
        if (hasError) {
          this.handleReset()
        }
      }
    }
  }

  componentWillUnmount() {
    this.clearTimeouts()
  }

  private setupAutoRecovery = () => {
    const {
      autoRecover = true,
      autoRecoverDelay = ERROR_CONFIG.ERROR_BOUNDARY.AUTO_RECOVER_DELAY,
      maxErrorCount = ERROR_CONFIG.ERROR_BOUNDARY.MAX_ERROR_COUNT
    } = this.props

    if (!autoRecover || this.state.errorCount >= maxErrorCount) {
      return
    }

    // Clear existing timeout
    if (this.resetTimeoutId) {
      clearTimeout(this.resetTimeoutId)
    }

    // Set up new auto-recovery timeout
    this.resetTimeoutId = setTimeout(() => {
      this.setState({ isRecovering: true })
      setTimeout(() => {
        this.handleReset()
      }, 1000) // Small delay for UI feedback
    }, autoRecoverDelay)
  }

  private setupErrorCountReset = () => {
    if (this.errorCountResetTimeout) {
      clearTimeout(this.errorCountResetTimeout)
    }

    this.errorCountResetTimeout = setTimeout(() => {
      this.setState({ errorCount: 0 })
    }, ERROR_CONFIG.ERROR_BOUNDARY.RESET_WINDOW)
  }

  private clearTimeouts = () => {
    if (this.resetTimeoutId) {
      clearTimeout(this.resetTimeoutId)
      this.resetTimeoutId = null
    }
    if (this.errorCountResetTimeout) {
      clearTimeout(this.errorCountResetTimeout)
      this.errorCountResetTimeout = null
    }
  }

  handleReset = async () => {
    this.clearTimeouts()

    // Call custom reset handler
    if (this.props.onReset) {
      try {
        await Promise.resolve(this.props.onReset())
      } catch (resetError) {
        logger.error('Error in reset handler', { error: resetError })
      }
    }

    // Reset state
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      showDetails: false,
      isRecovering: false
      // Don't reset errorCount here - track total errors
    })
  }

  toggleDetails = () => {
    this.setState(prev => ({ showDetails: !prev.showDetails }))
  }

  render() {
    const { hasError, error, errorInfo, errorCount, showDetails, isRecovering } = this.state

    if (!hasError) {
      return this.props.children
    }

    const {
      mode = ErrorBoundaryMode.FULL,
      fallback,
      customTitle,
      customMessage,
      homeRoute = '/feedme-revamped',
      showDetails: allowDetails = process.env.NODE_ENV === 'development',
      maxErrorCount = ERROR_CONFIG.ERROR_BOUNDARY.MAX_ERROR_COUNT,
      ariaLabel = 'Error boundary',
      testId = 'error-boundary'
    } = this.props

    // Use custom fallback if provided
    if (fallback) {
      return <>{fallback}</>
    }

    // Silent mode - no UI, just logging
    if (mode === ErrorBoundaryMode.SILENT) {
      return null
    }

    // Determine error message and title
    const title = customTitle || (
      errorCount >= maxErrorCount
        ? 'Persistent Error Detected'
        : 'Something went wrong'
    )

    const message = customMessage || error?.message || 'An unexpected error occurred'

    // Common error content
    const errorContent = (
      <>
        <AlertCircle className="h-12 w-12 text-destructive" aria-hidden="true" />

        <div className="text-center space-y-2">
          <h3 className="text-lg font-semibold" role="heading" aria-level={3}>
            {title}
          </h3>
          <p className="text-sm text-muted-foreground max-w-md">
            {message}
          </p>

          {errorCount >= maxErrorCount && (
            <p className="text-xs text-amber-600 dark:text-amber-400" role="alert">
              This error has occurred {errorCount} times. You may need to refresh the page.
            </p>
          )}

          {isRecovering && (
            <p className="text-xs text-blue-600 dark:text-blue-400 animate-pulse">
              Attempting automatic recovery...
            </p>
          )}
        </div>

        <div className="flex gap-2 flex-wrap justify-center">
          <Button
            onClick={this.handleReset}
            variant="outline"
            size="sm"
            disabled={isRecovering}
            aria-label="Try again"
          >
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
            Try Again
          </Button>

          {mode === ErrorBoundaryMode.FULL && <NavigationButton homeRoute={homeRoute} />}

          {allowDetails && (
            <Button
              onClick={this.toggleDetails}
              variant="ghost"
              size="sm"
              aria-expanded={showDetails}
              aria-label={showDetails ? 'Hide error details' : 'Show error details'}
            >
              {showDetails ? (
                <>
                  <ChevronUp className="mr-1 h-4 w-4" aria-hidden="true" />
                  Hide Details
                </>
              ) : (
                <>
                  <ChevronDown className="mr-1 h-4 w-4" aria-hidden="true" />
                  Show Details
                </>
              )}
            </Button>
          )}
        </div>

        {showDetails && errorInfo && (
          <ErrorDetails error={error} errorInfo={errorInfo} />
        )}
      </>
    )

    // Render based on mode
    switch (mode) {
      case ErrorBoundaryMode.FULL:
        return (
          <div
            className="min-h-screen flex items-center justify-center p-4"
            role="alert"
            aria-label={ariaLabel}
            data-testid={testId}
          >
            <Card className="flex flex-col items-center justify-center p-8 space-y-4 max-w-2xl w-full">
              {errorContent}
            </Card>
          </div>
        )

      case ErrorBoundaryMode.DIALOG:
        return (
          <div
            className="flex flex-col items-center justify-center p-8 space-y-4"
            role="alert"
            aria-label={ariaLabel}
            data-testid={testId}
          >
            {errorContent}
          </div>
        )

      case ErrorBoundaryMode.INLINE:
        return (
          <div
            className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 space-y-3"
            role="alert"
            aria-label={ariaLabel}
            data-testid={testId}
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" aria-hidden="true" />
              <div className="flex-1 space-y-2">
                <p className="text-sm font-medium">{title}</p>
                <p className="text-xs text-muted-foreground">{message}</p>
                <Button
                  onClick={this.handleReset}
                  variant="outline"
                  size="sm"
                  className="mt-2"
                  disabled={isRecovering}
                >
                  <RefreshCw className="mr-2 h-3 w-3" aria-hidden="true" />
                  Retry
                </Button>
              </div>
            </div>
          </div>
        )

      default:
        return null
    }
  }
}

// Navigation button component (client-side only)
function NavigationButton({ homeRoute }: { homeRoute: string }) {
  const router = useRouter()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null

  return (
    <Button
      onClick={() => router.push(homeRoute)}
      variant="outline"
      size="sm"
      aria-label="Go to dashboard"
    >
      <Home className="mr-2 h-4 w-4" aria-hidden="true" />
      Go to Dashboard
    </Button>
  )
}

// Error details component
function ErrorDetails({
  error,
  errorInfo
}: {
  error: Error | null
  errorInfo: React.ErrorInfo
}) {
  return (
    <div className="mt-4 w-full" role="region" aria-label="Error details">
      <div className="rounded-lg bg-destructive/10 p-4 text-left space-y-4">
        <div>
          <h4 className="text-sm font-semibold mb-2">Error Stack:</h4>
          <pre
            className="text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words font-mono"
            aria-label="Error stack trace"
          >
            {error?.stack || 'No stack trace available'}
          </pre>
        </div>

        <div>
          <h4 className="text-sm font-semibold mb-2">Component Stack:</h4>
          <pre
            className="text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words font-mono"
            aria-label="Component stack trace"
          >
            {errorInfo.componentStack || 'No component stack available'}
          </pre>
        </div>
      </div>
    </div>
  )
}

// HOC for wrapping components with error boundary
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryConfig?: ErrorBoundaryConfig
) {
  const WrappedComponent = (props: P) => (
    <UnifiedErrorBoundary {...errorBoundaryConfig}>
      <Component {...props} />
    </UnifiedErrorBoundary>
  )

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`

  return WrappedComponent
}

// React hook for error boundaries
export function useErrorBoundary() {
  const [error, setError] = React.useState<Error | null>(null)

  const resetError = React.useCallback(() => {
    setError(null)
  }, [])

  const captureError = React.useCallback((error: Error) => {
    setError(error)
  }, [])

  // Throw error to be caught by nearest error boundary
  if (error) {
    throw error
  }

  return { captureError, resetError }
}

// Export convenience components with preset modes
export const DialogErrorBoundary: React.FC<
  Omit<ErrorBoundaryConfig, 'mode'> & { children: React.ReactNode }
> = props => <UnifiedErrorBoundary {...props} mode={ErrorBoundaryMode.DIALOG} />

export const InlineErrorBoundary: React.FC<
  Omit<ErrorBoundaryConfig, 'mode'> & { children: React.ReactNode }
> = props => <UnifiedErrorBoundary {...props} mode={ErrorBoundaryMode.INLINE} />

export const SilentErrorBoundary: React.FC<
  Omit<ErrorBoundaryConfig, 'mode'> & { children: React.ReactNode }
> = props => <UnifiedErrorBoundary {...props} mode={ErrorBoundaryMode.SILENT} />

// Default export
export default UnifiedErrorBoundary