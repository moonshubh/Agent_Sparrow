"use client"

import React from 'react'
import { AlertCircle, RefreshCw, Home } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { useRouter } from 'next/navigation'

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ReactNode
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void
  resetKeys?: Array<string | number> // Dependencies that should trigger reset
  resetOnPropsChange?: boolean
  isolate?: boolean // Don't propagate errors to parent boundaries
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: React.ErrorInfo | null
  errorCount: number
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  private resetTimeoutId: ReturnType<typeof setTimeout> | null = null
  private previousResetKeys: Array<string | number> = []

  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0
    }
    this.previousResetKeys = props.resetKeys || []
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    // Note: getDerivedStateFromError doesn't have access to previous state
    // errorCount will be incremented in componentDidCatch
    return {
      hasError: true,
      error
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log to console for development
    console.error('ErrorBoundary caught:', error, errorInfo)

    // Store error info for display and increment error count
    this.setState(prevState => {
      const newErrorCount = prevState.errorCount + 1

      // Auto-recover after 30 seconds for transient errors
      // Check the new error count, not the old state
      if (newErrorCount < 3) {
        this.resetTimeoutId = setTimeout(() => {
          this.handleReset()
        }, 30000)
      }

      return {
        errorInfo,
        errorCount: newErrorCount
      }
    })

    // Call custom error handler
    this.props.onError?.(error, errorInfo)

    // Send telemetry (in production, this would go to your error tracking service)
    this.logErrorToService(error, errorInfo)
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    const { resetKeys, resetOnPropsChange } = this.props
    const { hasError } = this.state

    // Reset on prop changes if enabled
    if (hasError && prevProps.children !== this.props.children && resetOnPropsChange) {
      this.handleReset()
    }

    // Reset when resetKeys change (including length changes)
    if (resetKeys && this.previousResetKeys) {
      const hasResetKeyChanged = resetKeys.length !== this.previousResetKeys.length ||
        resetKeys.some((key, idx) => key !== this.previousResetKeys[idx])

      if (hasResetKeyChanged) {
        this.previousResetKeys = resetKeys
        if (hasError) {
          this.handleReset()
        }
      }
    }
  }

  componentWillUnmount() {
    if (this.resetTimeoutId) {
      clearTimeout(this.resetTimeoutId)
    }
  }

  private logErrorToService(error: Error, errorInfo: React.ErrorInfo) {
    // In production, send to error tracking service like Sentry
    const errorData = {
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      userAgent: typeof window !== 'undefined' ? window.navigator.userAgent : 'SSR',
      url: typeof window !== 'undefined' ? window.location.href : 'SSR',
      errorBoundaryProps: {
        isolate: this.props.isolate,
        hasCustomFallback: !!this.props.fallback
      }
    }

    // In development, just log to console
    if (process.env.NODE_ENV === 'development') {
      console.group('🚨 Error Telemetry')
      console.table(errorData)
      console.groupEnd()
    }

    // TODO: In production, send to your error tracking service
    // Example: window.Sentry?.captureException(error, { extra: errorData })
  }

  handleReset = () => {
    if (this.resetTimeoutId) {
      clearTimeout(this.resetTimeoutId)
      this.resetTimeoutId = null
    }
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      // Don't reset errorCount - keep track of total errors
    })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return <>{this.props.fallback}</>
      }

      return (
        <ErrorFallback
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          errorCount={this.state.errorCount}
          onReset={this.handleReset}
        />
      )
    }

    return this.props.children
  }
}

export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryProps?: Omit<ErrorBoundaryProps, 'children'>
) {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ErrorBoundary>
  )

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`

  return WrappedComponent
}

// Enhanced error fallback component with better UX
interface ErrorFallbackProps {
  error: Error | null
  errorInfo: React.ErrorInfo | null
  errorCount: number
  onReset: () => void
}

function ErrorFallback({ error, errorInfo, errorCount, onReset }: ErrorFallbackProps) {
  const [showDetails, setShowDetails] = React.useState(false)
  const [mounted, setMounted] = React.useState(false)
  const router = useRouter()

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const handleGoToDashboard = () => {
    if (mounted) {
      router.push('/feedme')
    }
  }

  return (
    <Card className="flex flex-col items-center justify-center p-8 space-y-4 m-4 max-w-2xl mx-auto">
      <AlertCircle className="h-12 w-12 text-destructive" />

      <div className="text-center space-y-2">
        <h3 className="text-lg font-semibold">
          {errorCount > 2 ? 'Persistent Error Detected' : 'Something went wrong'}
        </h3>
        <p className="text-sm text-muted-foreground max-w-md">
          {error?.message || 'An unexpected error occurred'}
        </p>

        {errorCount > 2 && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            This error has occurred {errorCount} times. You may need to refresh the page.
          </p>
        )}
      </div>

      <div className="flex gap-2 flex-wrap justify-center">
        <Button onClick={onReset} variant="outline" size="sm">
          <RefreshCw className="mr-2 h-4 w-4" />
          Try Again
        </Button>

        {mounted && (
          <Button
            onClick={handleGoToDashboard}
            variant="outline"
            size="sm"
          >
            <Home className="mr-2 h-4 w-4" />
            Go to Dashboard
          </Button>
        )}

        {process.env.NODE_ENV === 'development' && (
          <Button
            onClick={() => setShowDetails(!showDetails)}
            variant="ghost"
            size="sm"
          >
            {showDetails ? 'Hide' : 'Show'} Details
          </Button>
        )}
      </div>

      {showDetails && errorInfo && (
        <div className="mt-4 w-full">
          <div className="rounded-lg bg-destructive/10 p-4 text-left">
            <h4 className="text-sm font-semibold mb-2">Error Stack:</h4>
            <pre className="text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words">
              {error?.stack}
            </pre>

            <h4 className="text-sm font-semibold mt-4 mb-2">Component Stack:</h4>
            <pre className="text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words">
              {errorInfo.componentStack}
            </pre>
          </div>
        </div>
      )}
    </Card>
  )
}