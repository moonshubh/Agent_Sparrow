/**
 * Centralized Logging Service
 * Provides structured logging with different levels and environments
 */

import { useMemo } from 'react'
import { LOG_LEVELS, FEATURES, type LogLevel } from '@/shared/config/constants'

interface LogContext {
  component?: string
  userId?: string
  sessionId?: string
  timestamp?: Date
  [key: string]: unknown
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
    this.logLevel = this.isDevelopment ? LOG_LEVELS.DEBUG : LOG_LEVELS.INFO
  }

  static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger()
    }
    return Logger.instance
  }

  setLogLevel(level: LogLevel): void {
    this.logLevel = LOG_LEVELS[level]
  }

  error(message: string, error?: Error | unknown, context?: LogContext): void {
    this.log('ERROR', message, context, error)
  }

  warn(message: string, context?: LogContext): void {
    this.log('WARN', message, context)
  }

  info(message: string, context?: LogContext): void {
    this.log('INFO', message, context)
  }

  debug(message: string, context?: LogContext): void {
    this.log('DEBUG', message, context)
  }

  trace(message: string, context?: LogContext): void {
    this.log('TRACE', message, context)
  }

  critical(message: string, error?: Error | unknown, context?: LogContext): void {
    this.log('CRITICAL', message, context, error)
  }

  private log(
    level: LogLevel,
    message: string,
    context?: LogContext,
    error?: Error | unknown
  ): void {
    if (LOG_LEVELS[level] > this.logLevel) {
      return
    }

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

    this.addToBuffer(entry)

    const formattedMessage = this.formatMessage(entry)

    if (this.isDevelopment) {
      this.logToDevelopmentConsole(level, formattedMessage, context, error)
    } else {
      this.logToProduction(entry)
    }
  }

  private formatMessage(entry: LogEntry): string {
    const timestamp = entry.timestamp.toISOString()
    const component = entry.context?.component ? `[${entry.context.component}]` : ''
    return `${timestamp} ${entry.level} ${component} ${entry.message}`.trim()
  }

  private logToDevelopmentConsole(
    level: LogLevel,
    message: string,
    context?: LogContext,
    error?: Error | unknown
  ): void {
    const styles: Record<LogLevel, string> = {
      ERROR: 'color: #ff0000; font-weight: bold',
      WARN: 'color: #ff9800; font-weight: bold',
      INFO: 'color: #2196f3',
      DEBUG: 'color: #4caf50',
      TRACE: 'color: #9e9e9e',
      CRITICAL: 'color: #b71c1c; font-weight: 800',
    }

    const consoleMethod: ((...args: unknown[]) => void) = (
      {
        ERROR: console.error,
        WARN: console.warn,
        INFO: console.info,
        DEBUG: console.debug,
        TRACE: console.trace,
        CRITICAL: console.error,
      } as Record<LogLevel, (...args: unknown[]) => void>
    )[level] ?? console.log

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

  private logToProduction(entry: LogEntry): void {
    const consoleMethod: ((...args: unknown[]) => void) = (
      {
        ERROR: console.error,
        WARN: console.warn,
        INFO: console.info,
        DEBUG: console.log,
        TRACE: console.log,
        CRITICAL: console.error,
      } as Record<LogLevel, (...args: unknown[]) => void>
    )[entry.level] ?? console.log

    if (LOG_LEVELS[entry.level] <= LOG_LEVELS.WARN) {
      consoleMethod(this.formatMessage(entry))
    }

    this.sendToMonitoringService(entry)
  }

  private sendToMonitoringService(entry: LogEntry): void {
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
  }

  private addToBuffer(entry: LogEntry): void {
    this.buffer.push(entry)
    if (this.buffer.length > this.maxBufferSize) {
      this.buffer.shift()
    }
  }

  exportLogs(): string {
    return JSON.stringify(this.buffer, null, 2)
  }

  clearBuffer(): void {
    this.buffer = []
  }

  getRecentLogs(count: number = 10): LogEntry[] {
    return this.buffer.slice(-count)
  }

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

  group(label: string, collapsed = false): void {
    if (this.isDevelopment) {
      if (collapsed) {
        console.groupCollapsed(label)
      } else {
        console.group(label)
      }
    }
  }

  groupEnd(): void {
    if (this.isDevelopment) {
      console.groupEnd()
    }
  }

  assert(condition: boolean, message: string): void {
    if (this.isDevelopment) {
      console.assert(condition, message)
    }
  }
}

export const logger = Logger.getInstance()

export const log = {
  error: (message: string, error?: Error | unknown, context?: LogContext) =>
    logger.error(message, error, context),
  warn: (message: string, context?: LogContext) => logger.warn(message, context),
  info: (message: string, context?: LogContext) => logger.info(message, context),
  debug: (message: string, context?: LogContext) => logger.debug(message, context),
  trace: (message: string, context?: LogContext) => logger.trace(message, context),
  time: (label: string) => logger.time(label),
  timeEnd: (label: string) => logger.timeEnd(label),
  group: (label: string, collapsed?: boolean) => logger.group(label, collapsed),
  groupEnd: () => logger.groupEnd(),
  assert: (condition: boolean, message: string) => logger.assert(condition, message),
  setLevel: (level: LogLevel) => logger.setLogLevel(level),
  export: () => logger.exportLogs(),
  clear: () => logger.clearBuffer(),
}

export interface LoggerApi {
  error: (message: string, error?: Error | unknown) => void
  warn: (message: string) => void
  info: (message: string) => void
  debug: (message: string) => void
  trace: (message: string) => void
}

export function useLogger(componentName: string): LoggerApi {
  const context = useMemo(() => ({ component: componentName }), [componentName])

  return useMemo(
    () => ({
      error: (message: string, error?: Error | unknown) => logger.error(message, error, context),
      warn: (message: string) => logger.warn(message, context),
      info: (message: string) => logger.info(message, context),
      debug: (message: string) => logger.debug(message, context),
      trace: (message: string) => logger.trace(message, context),
    }),
    [context]
  )
}

interface SentryLike {
  captureException: (error: Error, context?: { extra?: Record<string, unknown>; level?: string; tags?: Record<string, unknown> }) => void
  captureMessage: (message: string, level?: string) => void
}

interface LogRocketLike {
  log: (...args: unknown[]) => void
}

interface DataDogLike {
  log: (...args: unknown[]) => void
}

declare global {
  interface Window {
    Sentry?: SentryLike
    LogRocket?: LogRocketLike
    DataDog?: DataDogLike
  }
}
