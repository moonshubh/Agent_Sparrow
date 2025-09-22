/**
 * Centralized Logging Service
 * Provides structured logging with different levels and environments
 */

import { LOG_LEVELS, FEATURES, type LogLevel } from './constants'

interface LogContext {
  component?: string
  userId?: string
  sessionId?: string
  timestamp?: Date
  [key: string]: any
}

interface LogEntry {
  level: LogLevel
  message: string
  context?: LogContext
  error?: Error
  timestamp: Date
}

class Logger {
  private static instance: Logger
  private logLevel: number
  private buffer: LogEntry[] = []
  private readonly maxBufferSize = 100
  private readonly isDevelopment = process.env.NODE_ENV === 'development'
  private readonly isTest = process.env.NODE_ENV === 'test'

  private constructor() {
    // Set log level based on environment
    this.logLevel = this.isDevelopment ? LOG_LEVELS.DEBUG : LOG_LEVELS.INFO
  }

  static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger()
    }
    return Logger.instance
  }

  /**
   * Set the minimum log level
   */
  setLogLevel(level: LogLevel): void {
    this.logLevel = LOG_LEVELS[level]
  }

  /**
   * Log an error with context
   */
  error(message: string, error?: Error | unknown, context?: LogContext): void {
    this.log('ERROR', message, context, error)
  }

  /**
   * Log a warning
   */
  warn(message: string, context?: LogContext): void {
    this.log('WARN', message, context)
  }

  /**
   * Log informational message
   */
  info(message: string, context?: LogContext): void {
    this.log('INFO', message, context)
  }

  /**
   * Log debug information (only in development)
   */
  debug(message: string, context?: LogContext): void {
    this.log('DEBUG', message, context)
  }

  /**
   * Log trace information (verbose debugging)
   */
  trace(message: string, context?: LogContext): void {
    this.log('TRACE', message, context)
  }

  /**
   * Core logging method
   */
  private log(
    level: LogLevel,
    message: string,
    context?: LogContext,
    error?: Error | unknown
  ): void {
    // Check if we should log this level
    if (LOG_LEVELS[level] > this.logLevel) {
      return
    }

    // Don't log in test environment unless it's an error
    if (this.isTest && level !== 'ERROR') {
      return
    }

    const entry: LogEntry = {
      level,
      message,
      context,
      timestamp: new Date(),
      error: error instanceof Error ? error : undefined,
    }

    // Add to buffer for potential export
    this.addToBuffer(entry)

    // Format the message
    const formattedMessage = this.formatMessage(entry)

    // Output based on environment
    if (this.isDevelopment) {
      this.logToDevelopmentConsole(level, formattedMessage, context, error)
    } else {
      this.logToProduction(entry)
    }
  }

  /**
   * Format log message with timestamp and context
   */
  private formatMessage(entry: LogEntry): string {
    const timestamp = entry.timestamp.toISOString()
    const component = entry.context?.component ? `[${entry.context.component}]` : ''
    return `${timestamp} ${entry.level} ${component} ${entry.message}`
  }

  /**
   * Development console logging with styling
   */
  private logToDevelopmentConsole(
    level: LogLevel,
    message: string,
    context?: LogContext,
    error?: Error | unknown
  ): void {
    const styles = {
      ERROR: 'color: #ff0000; font-weight: bold',
      WARN: 'color: #ff9800; font-weight: bold',
      INFO: 'color: #2196f3',
      DEBUG: 'color: #4caf50',
      TRACE: 'color: #9e9e9e',
    }

    const consoleMethod = {
      ERROR: console.error,
      WARN: console.warn,
      INFO: console.info,
      DEBUG: console.debug,
      TRACE: console.trace,
    }[level]

    // Use group for better formatting
    if (FEATURES.DEV.VERBOSE_LOGGING && (context || error)) {
      console.group(`%c${message}`, styles[level])

      if (context && Object.keys(context).length > 0) {
        console.table(context)
      }

      if (error) {
        if (error instanceof Error) {
          console.error('Stack:', error.stack)
        } else {
          console.error('Error:', error)
        }
      }

      console.groupEnd()
    } else {
      consoleMethod(`%c${message}`, styles[level])
    }
  }

  /**
   * Production logging (send to monitoring service)
   */
  private logToProduction(entry: LogEntry): void {
    // In production, you would send to a service like Sentry, LogRocket, etc.
    // For now, we'll use a minimal console output

    const consoleMethod = {
      ERROR: console.error,
      WARN: console.warn,
      INFO: console.info,
      DEBUG: console.log,
      TRACE: console.log,
    }[entry.level]

    // Only log warnings and errors in production by default
    if (LOG_LEVELS[entry.level] <= LOG_LEVELS.WARN) {
      consoleMethod(this.formatMessage(entry))
    }

    // Send to monitoring service
    this.sendToMonitoringService(entry)
  }

  /**
   * Send logs to external monitoring service
   */
  private sendToMonitoringService(entry: LogEntry): void {
    // This would integrate with services like Sentry, DataDog, etc.
    if (typeof window !== 'undefined' && window.Sentry) {
      if (entry.level === 'ERROR' && entry.error) {
        window.Sentry.captureException(entry.error, {
          extra: entry.context,
          level: 'error',
        })
      } else if (entry.level === 'WARN') {
        window.Sentry.captureMessage(entry.message, 'warning')
      }
    }

    // You could also send to your own backend
    // this.sendToBackend(entry)
  }

  /**
   * Add entry to buffer for export/debugging
   */
  private addToBuffer(entry: LogEntry): void {
    this.buffer.push(entry)
    if (this.buffer.length > this.maxBufferSize) {
      this.buffer.shift()
    }
  }

  /**
   * Export logs for debugging
   */
  exportLogs(): string {
    return JSON.stringify(this.buffer, null, 2)
  }

  /**
   * Clear log buffer
   */
  clearBuffer(): void {
    this.buffer = []
  }

  /**
   * Get recent logs
   */
  getRecentLogs(count: number = 10): LogEntry[] {
    return this.buffer.slice(-count)
  }

  /**
   * Performance logging helper
   */
  time(label: string): void {
    if (this.isDevelopment) {
      console.time(label)
    }
  }

  timeEnd(label: string): void {
    if (this.isDevelopment) {
      console.timeEnd(label)
    }
  }

  /**
   * Group logging for related messages
   */
  group(label: string, collapsed = false): void {
    if (this.isDevelopment) {
      collapsed ? console.groupCollapsed(label) : console.group(label)
    }
  }

  groupEnd(): void {
    if (this.isDevelopment) {
      console.groupEnd()
    }
  }

  /**
   * Assert helper for debugging
   */
  assert(condition: boolean, message: string): void {
    if (this.isDevelopment) {
      console.assert(condition, message)
    }
  }
}

// Export singleton instance
export const logger = Logger.getInstance()

// Export convenience functions
export const log = {
  error: (message: string, error?: Error | unknown, context?: LogContext) =>
    logger.error(message, error, context),
  warn: (message: string, context?: LogContext) =>
    logger.warn(message, context),
  info: (message: string, context?: LogContext) =>
    logger.info(message, context),
  debug: (message: string, context?: LogContext) =>
    logger.debug(message, context),
  trace: (message: string, context?: LogContext) =>
    logger.trace(message, context),
  time: (label: string) => logger.time(label),
  timeEnd: (label: string) => logger.timeEnd(label),
  group: (label: string, collapsed?: boolean) => logger.group(label, collapsed),
  groupEnd: () => logger.groupEnd(),
  assert: (condition: boolean, message: string) => logger.assert(condition, message),
  setLevel: (level: LogLevel) => logger.setLogLevel(level),
  export: () => logger.exportLogs(),
  clear: () => logger.clearBuffer(),
}

// React hook for using logger with component context
import { useCallback, useMemo } from 'react'

export function useLogger(componentName: string) {
  const context = useMemo(() => ({ component: componentName }), [componentName])

  return useMemo(
    () => ({
      error: (message: string, error?: Error | unknown) =>
        logger.error(message, error, context),
      warn: (message: string) => logger.warn(message, context),
      info: (message: string) => logger.info(message, context),
      debug: (message: string) => logger.debug(message, context),
      trace: (message: string) => logger.trace(message, context),
    }),
    [context]
  )
}

// Global window interface for monitoring services
declare global {
  interface Window {
    Sentry?: any
    LogRocket?: any
    DataDog?: any
  }
}