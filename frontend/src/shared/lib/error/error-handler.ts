/**
 * Unified Error Handling System
 * Provides consistent error handling patterns across the application
 */

import { useCallback, useEffect } from "react";
import { logger } from "@/shared/logging/logger";
import { API_CONFIG, ERROR_CONFIG } from "@/shared/config/constants";

// Error severity levels
export enum ErrorSeverity {
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  CRITICAL = "critical",
}

// Error categories
export enum ErrorCategory {
  NETWORK = "network",
  VALIDATION = "validation",
  AUTHENTICATION = "authentication",
  AUTHORIZATION = "authorization",
  BUSINESS_LOGIC = "business_logic",
  SYSTEM = "system",
  UNKNOWN = "unknown",
}

export type ErrorContext = Record<string, unknown>;

// Base error class with additional metadata
export class AppError extends Error {
  public readonly severity: ErrorSeverity;
  public readonly category: ErrorCategory;
  public readonly code?: string;
  public readonly context?: ErrorContext;
  public readonly timestamp: Date;
  public readonly recoverable: boolean;

  constructor(
    message: string,
    options: {
      severity?: ErrorSeverity;
      category?: ErrorCategory;
      code?: string;
      context?: ErrorContext;
      recoverable?: boolean;
      cause?: Error;
    } = {},
  ) {
    super(message);
    this.name = "AppError";
    this.severity = options.severity || ErrorSeverity.MEDIUM;
    this.category = options.category || ErrorCategory.UNKNOWN;
    this.code = options.code;
    this.context = options.context;
    this.timestamp = new Date();
    this.recoverable = options.recoverable ?? true;

    if (options.cause) {
      this.cause = options.cause;
    }

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, AppError);
    }
  }
}

// Specific error types
export class NetworkError extends AppError {
  constructor(
    message: string,
    options: Omit<ConstructorParameters<typeof AppError>[1], "category"> = {},
  ) {
    super(message, { ...options, category: ErrorCategory.NETWORK });
    this.name = "NetworkError";
  }
}

export class ValidationError extends AppError {
  constructor(
    message: string,
    options: Omit<ConstructorParameters<typeof AppError>[1], "category"> = {},
  ) {
    super(message, {
      ...options,
      category: ErrorCategory.VALIDATION,
      severity: ErrorSeverity.LOW,
    });
    this.name = "ValidationError";
  }
}

export class AuthenticationError extends AppError {
  constructor(
    message: string,
    options: Omit<ConstructorParameters<typeof AppError>[1], "category"> = {},
  ) {
    super(message, {
      ...options,
      category: ErrorCategory.AUTHENTICATION,
      severity: ErrorSeverity.HIGH,
    });
    this.name = "AuthenticationError";
  }
}

// Error handler configuration
interface ErrorHandlerConfig {
  onError?: (error: AppError) => void | Promise<void>;
  onRecovery?: (error: AppError) => void | Promise<void>;
  shouldRetry?: (error: AppError, attemptNumber: number) => boolean;
  maxRetries?: number;
  retryDelay?: number;
}

// Global error handler
class ErrorHandler {
  private config: ErrorHandlerConfig = {};
  private errorHistory: AppError[] = [];
  private readonly maxHistorySize = 50;

  /**
   * Get the current configuration
   */
  getConfig(): ErrorHandlerConfig {
    return { ...this.config };
  }

  configure(config: ErrorHandlerConfig): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Handle an error with consistent logging and recovery
   */
  async handle(
    error: Error | AppError,
    options: { silent?: boolean } = {},
  ): Promise<void> {
    const appError = this.normalizeError(error);

    this.addToHistory(appError);

    if (!options.silent) {
      this.logError(appError);
    }

    if (this.config.onError) {
      try {
        await this.config.onError(appError);
      } catch (handlerError) {
        logger.error(
          "Error in custom error handler",
          handlerError instanceof Error
            ? handlerError
            : new Error(String(handlerError)),
        );
      }
    }

    if (
      appError.severity === ErrorSeverity.HIGH ||
      appError.severity === ErrorSeverity.CRITICAL
    ) {
      this.reportToService(appError);
    }
  }

  /**
   * Handle an error with automatic retry logic
   */
  async handleWithRetry<T>(
    operation: () => Promise<T>,
    options: {
      maxRetries?: number;
      retryDelay?: number;
      shouldRetry?: (error: AppError, attemptNumber: number) => boolean;
      onRetry?: (error: AppError, attemptNumber: number) => void;
    } = {},
  ): Promise<T> {
    const maxRetries =
      options.maxRetries ??
      this.config.maxRetries ??
      ERROR_CONFIG.RETRY.MAX_ATTEMPTS;
    const baseDelay =
      options.retryDelay ??
      this.config.retryDelay ??
      API_CONFIG.TIMEOUTS.RETRY_DELAY;
    const shouldRetry =
      options.shouldRetry ?? this.config.shouldRetry ?? this.defaultShouldRetry;

    let lastError: AppError | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = this.normalizeError(error);

        if (attempt === maxRetries || !shouldRetry(lastError, attempt)) {
          await this.handle(lastError);
          throw lastError;
        }

        const delay = this.calculateRetryDelay(baseDelay, attempt);

        if (options.onRetry) {
          options.onRetry(lastError, attempt);
        }

        logger.warn(`Retrying operation (attempt ${attempt}/${maxRetries})`, {
          error: lastError.message,
          delay,
        });

        await this.delay(delay);
      }
    }

    throw lastError ?? new AppError("Unknown error during retry handling");
  }

  /**
   * Wrap an async function with error handling
   */
  wrap<TArgs extends unknown[], TResult>(
    fn: (...args: TArgs) => Promise<TResult>,
    options: { name?: string; silent?: boolean } = {},
  ): (...args: TArgs) => Promise<TResult> {
    return async (...args: TArgs) => {
      try {
        return await fn(...args);
      } catch (error) {
        await this.handle(
          error instanceof Error ? error : new Error(String(error)),
          { silent: options.silent },
        );
        throw error;
      }
    };
  }

  /**
   * Create a safe version of a function that returns a Result type
   */
  safe<TArgs extends unknown[], TResult>(
    fn: (...args: TArgs) => Promise<TResult> | TResult,
  ): (...args: TArgs) => Promise<Result<TResult, AppError>> {
    return async (...args: TArgs) => {
      try {
        const result = await fn(...args);
        return { success: true, data: result };
      } catch (error) {
        const appError = this.normalizeError(error);
        await this.handle(appError, { silent: true });
        return { success: false, error: appError };
      }
    };
  }

  /**
   * Get error history for debugging
   */
  getErrorHistory(): AppError[] {
    return [...this.errorHistory];
  }

  /**
   * Clear error history
   */
  clearHistory(): void {
    this.errorHistory = [];
  }

  // Private methods

  private normalizeError(error: unknown): AppError {
    if (error instanceof AppError) {
      return error;
    }

    if (error instanceof Error) {
      if (error.name === "NetworkError" || error.message.includes("fetch")) {
        return new NetworkError(error.message, { cause: error });
      }

      if (error.name === "ValidationError") {
        return new ValidationError(error.message, { cause: error });
      }

      if (
        error.message.includes("401") ||
        error.message.toLowerCase().includes("unauthorized")
      ) {
        return new AuthenticationError(error.message, { cause: error });
      }

      return new AppError(error.message, {
        severity: ErrorSeverity.MEDIUM,
        category: ErrorCategory.UNKNOWN,
        cause: error,
      });
    }

    return new AppError(typeof error === "string" ? error : "Unknown error", {
      severity: ErrorSeverity.MEDIUM,
      category: ErrorCategory.UNKNOWN,
    });
  }

  private logError(error: AppError): void {
    const logData = {
      message: error.message,
      severity: error.severity,
      category: error.category,
      code: error.code,
      context: error.context,
      stack: error.stack,
    };

    switch (error.severity) {
      case ErrorSeverity.CRITICAL:
        logger.critical("Critical error occurred", error, logData);
        break;
      case ErrorSeverity.HIGH:
        logger.error("High severity error", error, logData);
        break;
      case ErrorSeverity.MEDIUM:
        logger.warn("Medium severity error", logData);
        break;
      case ErrorSeverity.LOW:
        logger.info("Low severity error", logData);
        break;
    }
  }

  private addToHistory(error: AppError): void {
    this.errorHistory.push(error);
    if (this.errorHistory.length > this.maxHistorySize) {
      this.errorHistory = this.errorHistory.slice(-this.maxHistorySize);
    }
  }

  private reportToService(error: AppError): void {
    if (typeof window !== "undefined" && window.Sentry) {
      window.Sentry.captureException(error, {
        level: error.severity,
        tags: {
          category: error.category,
          code: error.code,
        },
        extra: error.context,
      });
    }
  }

  private defaultShouldRetry(error: AppError, attemptNumber: number): boolean {
    if (!error.recoverable) return false;

    if (
      error.category === ErrorCategory.VALIDATION ||
      error.category === ErrorCategory.AUTHENTICATION ||
      error.category === ErrorCategory.AUTHORIZATION
    ) {
      return false;
    }

    if (error.category === ErrorCategory.NETWORK) {
      return attemptNumber <= ERROR_CONFIG.RETRY.MAX_ATTEMPTS;
    }

    return false;
  }

  private calculateRetryDelay(baseDelay: number, attempt: number): number {
    const exponentialDelay =
      baseDelay * Math.pow(ERROR_CONFIG.RETRY.EXPONENTIAL_BASE, attempt - 1);
    const jitter =
      exponentialDelay * ERROR_CONFIG.RETRY.JITTER_FACTOR * Math.random();
    return Math.min(
      exponentialDelay + jitter,
      API_CONFIG.TIMEOUTS.MAX_RETRY_DELAY,
    );
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// Result type for safe operations
export type Result<T, E = Error> =
  | { success: true; data: T }
  | { success: false; error: E };

// Create and export singleton instance
export const errorHandler = new ErrorHandler();

export function useErrorHandler(config?: ErrorHandlerConfig) {
  useEffect(() => {
    if (!config) {
      return undefined;
    }

    const previousConfig = errorHandler.getConfig();
    errorHandler.configure(config);

    return () => {
      errorHandler.configure(previousConfig);
    };
  }, [config]);

  const handleError = useCallback(
    async (error: Error | AppError, options?: { silent?: boolean }) => {
      return errorHandler.handle(error, options);
    },
    [],
  );

  const handleWithRetry = useCallback(
    async <T>(
      operation: () => Promise<T>,
      options?: Parameters<typeof errorHandler.handleWithRetry>[1],
    ) => {
      return errorHandler.handleWithRetry(operation, options);
    },
    [],
  );

  const wrapAsync = useCallback(
    <TArgs extends unknown[], TResult>(
      fn: (...args: TArgs) => Promise<TResult>,
      options?: { name?: string; silent?: boolean },
    ) => {
      return errorHandler.wrap(fn, options);
    },
    [],
  );

  const safe = useCallback(
    <TArgs extends unknown[], TResult>(
      fn: (...args: TArgs) => Promise<TResult> | TResult,
    ) => {
      return errorHandler.safe(fn);
    },
    [],
  );

  return {
    handleError,
    handleWithRetry,
    wrapAsync,
    safe,
    AppError,
    NetworkError,
    ValidationError,
    AuthenticationError,
  };
}

export { errorHandler as default };
