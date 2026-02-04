/**
 * Unified Error Boundary Component
 * Consolidates error handling across the application with proper logging and recovery
 */

import React from "react";
import { AlertCircle, RefreshCw, Home } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Card } from "@/shared/ui/card";
import { useRouter } from "next/navigation";
import { logger } from "@/shared/logging/logger";
import { TIMINGS, FEATURES } from "@/shared/config/constants";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
  resetKeys?: Array<string | number>;
  resetOnPropsChange?: boolean;
  isolate?: boolean;
  variant?: "full" | "inline" | "dialog";
  fallbackTitle?: string;
  showDetails?: boolean;
  autoRetry?: boolean;
  maxRetries?: number;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
  errorCount: number;
  retryCount: number;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  private resetTimeoutId: NodeJS.Timeout | null = null;
  private previousResetKeys: Array<string | number> = [];

  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
      retryCount: 0,
    };
    this.previousResetKeys = props.resetKeys || [];
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error with proper service
    logger.error("Component Error Boundary triggered", error, {
      component: errorInfo.componentStack || undefined,
      errorBoundary: {
        variant: this.props.variant || "full",
        isolate: this.props.isolate,
        autoRetry: this.props.autoRetry,
      },
    });

    // Update state with error info
    this.setState((prevState) => ({
      errorInfo,
      errorCount: prevState.errorCount + 1,
    }));

    // Call custom error handler
    this.props.onError?.(error, errorInfo);

    // Auto-retry logic if enabled
    if (
      this.props.autoRetry &&
      this.state.retryCount <
        (this.props.maxRetries || TIMINGS.ERROR_RECOVERY.MAX_RETRIES)
    ) {
      this.scheduleAutoRetry();
    }
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    const { resetKeys, resetOnPropsChange } = this.props;
    const { hasError } = this.state;

    // Reset on prop changes if enabled
    if (
      hasError &&
      prevProps.children !== this.props.children &&
      resetOnPropsChange
    ) {
      this.handleReset();
    }

    // Reset when resetKeys change
    if (resetKeys && this.previousResetKeys) {
      const hasResetKeyChanged = resetKeys.some(
        (key, idx) => key !== this.previousResetKeys[idx],
      );
      if (hasResetKeyChanged) {
        this.previousResetKeys = resetKeys;
        if (hasError) {
          this.handleReset();
        }
      }
    }
  }

  componentWillUnmount() {
    if (this.resetTimeoutId) {
      clearTimeout(this.resetTimeoutId);
    }
  }

  private scheduleAutoRetry(): void {
    const delay = TIMINGS.ERROR_RECOVERY.AUTO_RETRY;
    logger.info(`Scheduling auto-retry in ${delay}ms`);

    this.resetTimeoutId = setTimeout(() => {
      this.setState((prevState) => ({
        retryCount: prevState.retryCount + 1,
      }));
      this.handleReset();
    }, delay);
  }

  handleReset = () => {
    if (this.resetTimeoutId) {
      clearTimeout(this.resetTimeoutId);
      this.resetTimeoutId = null;
    }

    logger.info("Resetting error boundary");

    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      // Keep track of total errors and retries
    });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return <>{this.props.fallback}</>;
      }

      const variant = this.props.variant || "full";

      switch (variant) {
        case "dialog":
          return (
            <DialogErrorFallback
              error={this.state.error}
              errorCount={this.state.errorCount}
              retryCount={this.state.retryCount}
              fallbackTitle={this.props.fallbackTitle}
              onReset={this.handleReset}
            />
          );
        case "inline":
          return (
            <InlineErrorFallback
              error={this.state.error}
              errorCount={this.state.errorCount}
              onReset={this.handleReset}
            />
          );
        default:
          return (
            <FullErrorFallback
              error={this.state.error}
              errorInfo={this.state.errorInfo}
              errorCount={this.state.errorCount}
              retryCount={this.state.retryCount}
              showDetails={this.props.showDetails}
              onReset={this.handleReset}
            />
          );
      }
    }

    return this.props.children;
  }
}

// Full page error fallback
interface FullErrorFallbackProps {
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
  errorCount: number;
  retryCount: number;
  showDetails?: boolean;
  onReset: () => void;
}

function FullErrorFallback({
  error,
  errorInfo,
  errorCount,
  retryCount,
  showDetails = FEATURES.DEV.SHOW_ERROR_DETAILS,
  onReset,
}: FullErrorFallbackProps) {
  const [showDetailsState, setShowDetailsState] = React.useState(false);

  // Client-side navigation helper
  const NavigationButtons = () => {
    const router = useRouter();
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
      setMounted(true);
    }, []);

    if (!mounted) return null;

    return (
      <Button
        onClick={() => router.push("/feedme-revamped")}
        variant="outline"
        size="sm"
        aria-label="Navigate to dashboard"
      >
        <Home className="mr-2 h-4 w-4" aria-hidden="true" />
        Go to Dashboard
      </Button>
    );
  };

  return (
    <Card
      className="flex flex-col items-center justify-center p-8 space-y-4 m-4 max-w-2xl mx-auto"
      role="alert"
      aria-live="assertive"
    >
      <AlertCircle className="h-12 w-12 text-destructive" aria-hidden="true" />

      <div className="text-center space-y-2">
        <h3 className="text-lg font-semibold">
          {errorCount > 2
            ? "Persistent Error Detected"
            : retryCount > 0
              ? `Retry Attempt ${retryCount}`
              : "Something went wrong"}
        </h3>
        <p className="text-sm text-muted-foreground max-w-md">
          {error?.message || "An unexpected error occurred"}
        </p>

        {errorCount > 2 && (
          <p
            className="text-xs text-amber-600 dark:text-amber-400"
            role="status"
          >
            This error has occurred {errorCount} times. You may need to refresh
            the page.
          </p>
        )}
      </div>

      <div className="flex gap-2 flex-wrap justify-center">
        <Button
          onClick={onReset}
          variant="outline"
          size="sm"
          aria-label="Try again"
        >
          <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
          Try Again
        </Button>

        <NavigationButtons />

        {showDetails && (
          <Button
            onClick={() => setShowDetailsState(!showDetailsState)}
            variant="ghost"
            size="sm"
            aria-expanded={showDetailsState}
            aria-label={
              showDetailsState ? "Hide error details" : "Show error details"
            }
          >
            {showDetailsState ? "Hide" : "Show"} Details
          </Button>
        )}
      </div>

      {showDetailsState && errorInfo && (
        <div className="mt-4 w-full" role="region" aria-label="Error details">
          <div className="rounded-lg bg-destructive/10 p-4 text-left">
            <h4 className="text-sm font-semibold mb-2">Error Stack:</h4>
            <pre className="text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words">
              {error?.stack}
            </pre>

            <h4 className="text-sm font-semibold mt-4 mb-2">
              Component Stack:
            </h4>
            <pre className="text-xs overflow-auto max-h-40 whitespace-pre-wrap break-words">
              {errorInfo.componentStack}
            </pre>
          </div>
        </div>
      )}
    </Card>
  );
}

// Dialog error fallback (for modals)
interface DialogErrorFallbackProps {
  error: Error | null;
  errorCount: number;
  retryCount: number;
  fallbackTitle?: string;
  onReset: () => void;
}

function DialogErrorFallback({
  error,
  errorCount,
  retryCount,
  fallbackTitle,
  onReset,
}: DialogErrorFallbackProps) {
  return (
    <div
      className="flex flex-col items-center justify-center p-8 space-y-4"
      role="alert"
      aria-live="assertive"
    >
      <AlertCircle className="h-12 w-12 text-destructive" aria-hidden="true" />
      <div className="text-center space-y-2">
        <h3 className="text-lg font-semibold">
          {fallbackTitle || "Something went wrong"}
        </h3>
        <p className="text-sm text-muted-foreground">
          {error?.message || "An unexpected error occurred"}
        </p>
        {(errorCount > 1 || retryCount > 0) && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            {retryCount > 0
              ? `Retry ${retryCount}`
              : `Error count: ${errorCount}`}
          </p>
        )}
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={onReset}
        aria-label="Try again"
      >
        Try Again
      </Button>
    </div>
  );
}

// Inline error fallback (for smaller components)
interface InlineErrorFallbackProps {
  error: Error | null;
  errorCount: number;
  onReset: () => void;
}

function InlineErrorFallback({
  error,
  errorCount,
  onReset,
}: InlineErrorFallbackProps) {
  return (
    <div
      className="flex items-center gap-2 p-2 rounded-md bg-destructive/10"
      role="alert"
      aria-live="polite"
    >
      <AlertCircle className="h-4 w-4 text-destructive" aria-hidden="true" />
      <span className="text-sm text-destructive">
        {error?.message || "Error loading content"}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={onReset}
        aria-label="Retry loading"
      >
        Retry
      </Button>
    </div>
  );
}

// HOC for wrapping components with error boundary
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryProps?: Omit<ErrorBoundaryProps, "children">,
) {
  const WrappedComponent = (props: P) => (
    <ErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ErrorBoundary>
  );

  WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name})`;

  return WrappedComponent;
}

// Re-export for backwards compatibility
export { ErrorBoundary as DialogErrorBoundary };
export default ErrorBoundary;
