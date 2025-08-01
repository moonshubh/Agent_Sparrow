"use client"

import React from 'react'
import { Button } from '@/components/ui/button'
import { AlertTriangle, RefreshCw, Bug } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
  errorInfo?: React.ErrorInfo
}

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ComponentType<ErrorFallbackProps>
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void
  className?: string
  showDetails?: boolean
}

interface ErrorFallbackProps {
  error: Error
  errorInfo?: React.ErrorInfo
  resetError: () => void
  showDetails?: boolean
  className?: string
}

function DefaultErrorFallback({ 
  error, 
  errorInfo, 
  resetError, 
  showDetails = false,
  className 
}: ErrorFallbackProps) {
  const [showFullError, setShowFullError] = React.useState(false)

  return (
    <div className={cn(
      "flex flex-col items-center justify-center p-6 bg-destructive/5 border border-destructive/20 rounded-lg",
      className
    )}>
      <div className="flex items-center gap-3 mb-4">
        <AlertTriangle className="w-8 h-8 text-destructive" />
        <div className="text-center">
          <h2 className="text-lg font-semibold text-foreground">Something went wrong</h2>
          <p className="text-sm text-muted-foreground">
            An unexpected error occurred. Please try refreshing the page.
          </p>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <Button
          onClick={resetError}
          variant="outline"
          size="sm"
          className="gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Try Again
        </Button>
        
        {showDetails && (
          <Button
            onClick={() => setShowFullError(!showFullError)}
            variant="ghost"
            size="sm"
            className="gap-2"
          >
            <Bug className="w-4 h-4" />
            {showFullError ? 'Hide' : 'Show'} Details
          </Button>
        )}
      </div>

      {showDetails && showFullError && (
        <div className="w-full max-w-2xl">
          <details className="bg-muted/50 rounded p-4 text-sm">
            <summary className="cursor-pointer font-medium mb-2">Error Details</summary>
            <div className="space-y-2">
              <div>
                <strong>Error:</strong>
                <pre className="mt-1 text-xs bg-destructive/10 p-2 rounded overflow-auto">
                  {error.message}
                </pre>
              </div>
              {error.stack && (
                <div>
                  <strong>Stack Trace:</strong>
                  <pre className="mt-1 text-xs bg-destructive/10 p-2 rounded overflow-auto max-h-32">
                    {error.stack}
                  </pre>
                </div>
              )}
              {errorInfo && (
                <div>
                  <strong>Component Stack:</strong>
                  <pre className="mt-1 text-xs bg-destructive/10 p-2 rounded overflow-auto max-h-32">
                    {errorInfo.componentStack}
                  </pre>
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  )
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      error
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    
    this.setState({
      error,
      errorInfo
    })

    // Call the onError callback if provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }
  }

  resetError = () => {
    this.setState({ 
      hasError: false, 
      error: undefined, 
      errorInfo: undefined 
    })
  }

  render() {
    if (this.state.hasError && this.state.error) {
      const ErrorFallback = this.props.fallback || DefaultErrorFallback

      return (
        <ErrorFallback
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          resetError={this.resetError}
          showDetails={this.props.showDetails}
          className={this.props.className}
        />
      )
    }

    return this.props.children
  }
}

// Hook version for functional components
export function useErrorHandler() {
  const [error, setError] = React.useState<Error | null>(null)

  const resetError = React.useCallback(() => {
    setError(null)
  }, [])

  const handleError = React.useCallback((error: Error) => {
    console.error('useErrorHandler caught an error:', error)
    setError(error)
  }, [])

  React.useEffect(() => {
    if (error) {
      // You could also report to an error tracking service here
      // Note: Error already logged in handleError, avoid duplicate logging
    }
  }, [error])

  return {
    error,
    resetError,
    handleError
  }
}

// Wrapper component for easier usage
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