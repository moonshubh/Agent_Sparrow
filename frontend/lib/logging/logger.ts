/**
 * Centralized Logging Service
 * Provides structured logging with different levels and environments
 */

import { FEATURE_FLAGS, APP_CONFIG } from '../config/constants'

// Log levels
export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  CRITICAL = 4,
  NONE = 5
}

// Log entry structure
export interface LogEntry {
  timestamp: Date
  level: LogLevel
  message: string
  data?: any
  context?: string
  userId?: string
  sessionId?: string
  requestId?: string
  stack?: string
}

// Log transport interface
export interface LogTransport {
  log(entry: LogEntry): void | Promise<void>
  flush?(): Promise<void>
}

// Console transport (development)
class ConsoleTransport implements LogTransport {
  private readonly colors = {
    [LogLevel.DEBUG]: 'color: #9CA3AF',
    [LogLevel.INFO]: 'color: #3B82F6',
    [LogLevel.WARN]: 'color: #F59E0B',
    [LogLevel.ERROR]: 'color: #EF4444',
    [LogLevel.CRITICAL]: 'color: #DC2626; font-weight: bold',
  }

  log(entry: LogEntry): void {
    if (typeof window === 'undefined') {
      // Node.js environment
      this.logNode(entry)
    } else {
      // Browser environment
      this.logBrowser(entry)
    }
  }

  private logBrowser(entry: LogEntry): void {
    const timestamp = entry.timestamp.toISOString()
    const level = LogLevel[entry.level]
    const style = this.colors[entry.level] || ''

    // Group console output for better readability
    console.group(
      `%c[${timestamp}] [${level}] ${entry.message}`,
      style
    )

    if (entry.data) {
      console.log('Data:', entry.data)
    }

    if (entry.context) {
      console.log('Context:', entry.context)
    }

    if (entry.stack) {
      console.log('Stack:', entry.stack)
    }

    console.groupEnd()
  }

  private logNode(entry: LogEntry): void {
    const timestamp = entry.timestamp.toISOString()
    const level = LogLevel[entry.level]

    const output = {
      timestamp,
      level,
      message: entry.message,
      ...entry.data && { data: entry.data },
      ...entry.context && { context: entry.context },
      ...entry.stack && { stack: entry.stack }
    }

    // Use appropriate console method based on level
    switch (entry.level) {
      case LogLevel.DEBUG:
        console.debug(JSON.stringify(output))
        break
      case LogLevel.INFO:
        console.info(JSON.stringify(output))
        break
      case LogLevel.WARN:
        console.warn(JSON.stringify(output))
        break
      case LogLevel.ERROR:
      case LogLevel.CRITICAL:
        console.error(JSON.stringify(output))
        break
    }
  }
}

// Remote transport (production)
class RemoteTransport implements LogTransport {
  private buffer: LogEntry[] = []
  private readonly maxBufferSize = 100
  private flushTimer: ReturnType<typeof setInterval> | null = null
  private isFlushInProgress = false
  private readonly flushInterval = 5000 // 5 seconds

  constructor(private endpoint: string) {
    this.startAutoFlush()
  }

  log(entry: LogEntry): void {
    this.buffer.push(entry)

    if (this.buffer.length >= this.maxBufferSize) {
      this.flush()
    }
  }

  async flush(): Promise<void> {
    if (this.buffer.length === 0 || this.isFlushInProgress) return

    this.isFlushInProgress = true
    const entries = [...this.buffer]
    this.buffer = []

    try {
      await fetch(this.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          logs: entries,
          app: APP_CONFIG.NAME,
          version: APP_CONFIG.VERSION,
          environment: APP_CONFIG.ENVIRONMENT,
        }),
      })
    } catch (error) {
      // Fallback to console if remote logging fails
      console.error('Failed to send logs to remote server:', error)
      entries.forEach(entry => console.log(entry))
    } finally {
      this.isFlushInProgress = false
    }
  }

  private startAutoFlush(): void {
    this.flushTimer = setInterval(() => {
      void this.flush()
    }, this.flushInterval)

    // Flush on page unload - use sendBeacon for reliability
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        // For beforeunload, we need synchronous-like behavior
        // Use navigator.sendBeacon if available, otherwise try synchronous XHR
        if (this.buffer.length > 0) {
          const entries = [...this.buffer]
          this.buffer = []

          if (navigator.sendBeacon) {
            const blob = new Blob(
              [JSON.stringify({ entries, timestamp: new Date().toISOString() })],
              { type: 'application/json' }
            )
            navigator.sendBeacon(this.endpoint, blob)
          } else {
            // Fallback to synchronous XHR (deprecated but works)
            try {
              const xhr = new XMLHttpRequest()
              xhr.open('POST', this.endpoint, false) // false makes it synchronous
              xhr.setRequestHeader('Content-Type', 'application/json')
              xhr.send(JSON.stringify({ entries, timestamp: new Date().toISOString() }))
            } catch (error) {
              console.error('[RemoteTransport] Failed to send logs on unload:', error)
            }
          }
        }
      })
    }
  }

  destroy(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer)
    }
    void this.flush()
  }
}

// Local storage transport (for debugging)
class LocalStorageTransport implements LogTransport {
  private readonly maxLogs = 1000
  private readonly storageKey = 'app_logs'

  log(entry: LogEntry): void {
    if (typeof window === 'undefined') return

    try {
      const stored = localStorage.getItem(this.storageKey)
      const logs = stored ? JSON.parse(stored) : []

      logs.push({
        ...entry,
        timestamp: entry.timestamp.toISOString()
      })

      // Keep only recent logs
      if (logs.length > this.maxLogs) {
        logs.splice(0, logs.length - this.maxLogs)
      }

      localStorage.setItem(this.storageKey, JSON.stringify(logs))
    } catch (error) {
      // Ignore storage errors
    }
  }

  getLogs(): LogEntry[] {
    if (typeof window === 'undefined') return []

    try {
      const stored = localStorage.getItem(this.storageKey)
      return stored ? JSON.parse(stored) : []
    } catch {
      return []
    }
  }

  clear(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(this.storageKey)
    }
  }
}

// Main Logger class
class Logger {
  private level: LogLevel = LogLevel.INFO
  private transports: LogTransport[] = []
  private context?: string
  private metadata: Record<string, any> = {}

  constructor() {
    this.initialize()
  }

  private initialize(): void {
    // Set log level based on environment
    if (APP_CONFIG.ENVIRONMENT === 'production') {
      this.level = LogLevel.WARN
    } else if (APP_CONFIG.ENVIRONMENT === 'development') {
      this.level = LogLevel.DEBUG
    } else {
      this.level = LogLevel.INFO
    }

    // Add transports based on environment
    if (FEATURE_FLAGS.ENABLE_DEBUG_LOGGING) {
      this.addTransport(new ConsoleTransport())
      this.addTransport(new LocalStorageTransport())
    }

    if (FEATURE_FLAGS.ENABLE_ERROR_REPORTING && APP_CONFIG.ENVIRONMENT === 'production') {
      // Add remote transport for production
      const logEndpoint = process.env.NEXT_PUBLIC_LOG_ENDPOINT
      if (logEndpoint) {
        this.addTransport(new RemoteTransport(logEndpoint))
      }
    }
  }

  // Configuration methods

  setLevel(level: LogLevel): void {
    this.level = level
  }

  setContext(context: string): void {
    this.context = context
  }

  setMetadata(metadata: Record<string, any>): void {
    this.metadata = { ...this.metadata, ...metadata }
  }

  addTransport(transport: LogTransport): void {
    this.transports.push(transport)
  }

  removeTransport(transport: LogTransport): void {
    const index = this.transports.indexOf(transport)
    if (index > -1) {
      this.transports.splice(index, 1)
    }
  }

  // Logging methods

  debug(message: string, data?: any): void {
    this.log(LogLevel.DEBUG, message, data)
  }

  info(message: string, data?: any): void {
    this.log(LogLevel.INFO, message, data)
  }

  warn(message: string, data?: any): void {
    this.log(LogLevel.WARN, message, data)
  }

  error(message: string, data?: any): void {
    this.log(LogLevel.ERROR, message, data)
  }

  critical(message: string, data?: any): void {
    this.log(LogLevel.CRITICAL, message, data)
  }

  // Performance logging
  time(label: string): void {
    if (typeof window !== 'undefined') {
      performance.mark(`${label}-start`)
    }
  }

  timeEnd(label: string): void {
    if (typeof window !== 'undefined') {
      performance.mark(`${label}-end`)
      try {
        performance.measure(label, `${label}-start`, `${label}-end`)
        const measure = performance.getEntriesByName(label)[0] as PerformanceMeasure
        this.debug(`Performance: ${label}`, { duration: measure.duration })

        // Clean up
        performance.clearMarks(`${label}-start`)
        performance.clearMarks(`${label}-end`)
        performance.clearMeasures(label)
      } catch (error) {
        // Ignore performance API errors
      }
    }
  }

  // Group logging for related messages
  group(label: string): LogGroup {
    return new LogGroup(label, this)
  }

  // Main logging method
  private log(level: LogLevel, message: string, data?: any): void {
    if (level < this.level) return

    const entry: LogEntry = {
      timestamp: new Date(),
      level,
      message,
      data,
      context: this.context,
      ...this.metadata
    }

    // Add stack trace for errors
    if (level >= LogLevel.ERROR && data instanceof Error) {
      entry.stack = data.stack
    }

    // Send to all transports
    this.transports.forEach(transport => {
      try {
        transport.log(entry)
      } catch (error) {
        // Prevent transport errors from breaking the app
        if (APP_CONFIG.ENVIRONMENT === 'development') {
          console.error('Logger transport error:', error)
        }
      }
    })
  }

  // Utility methods

  async flush(): Promise<void> {
    await Promise.all(
      this.transports
        .filter(t => t.flush)
        .map(t => t.flush!())
    )
  }

  createChild(context: string): Logger {
    const child = new Logger()
    child.level = this.level
    child.transports = [...this.transports]
    child.context = context
    child.metadata = { ...this.metadata }
    return child
  }
}

// Log group for related messages
class LogGroup {
  private logs: Array<{ level: LogLevel; message: string; data?: any }> = []

  constructor(
    private label: string,
    private logger: Logger
  ) {}

  debug(message: string, data?: any): this {
    this.logs.push({ level: LogLevel.DEBUG, message, data })
    return this
  }

  info(message: string, data?: any): this {
    this.logs.push({ level: LogLevel.INFO, message, data })
    return this
  }

  warn(message: string, data?: any): this {
    this.logs.push({ level: LogLevel.WARN, message, data })
    return this
  }

  error(message: string, data?: any): this {
    this.logs.push({ level: LogLevel.ERROR, message, data })
    return this
  }

  end(): void {
    this.logger.info(`[Group: ${this.label}]`, {
      logs: this.logs
    })
  }
}

// Create and export singleton instance
export const logger = new Logger()

// React hook for component-scoped logging
import { useEffect, useRef } from 'react'

export function useLogger(componentName: string) {
  const loggerRef = useRef<Logger | null>(null)

  // Initialize immediately to avoid undefined on first render
  if (!loggerRef.current) {
    loggerRef.current = logger.createChild(componentName)
  }

  useEffect(() => {
    // Update if componentName changes
    loggerRef.current = logger.createChild(componentName)
  }, [componentName])

  return loggerRef.current
}

// Utility function to replace console methods in production
export function replaceConsoleInProduction(): void {
  if (APP_CONFIG.ENVIRONMENT === 'production' && typeof window !== 'undefined') {
    const noop = () => {}

    // Store original methods
    const originalConsole = {
      log: console.log,
      debug: console.debug,
      info: console.info,
      warn: console.warn,
      error: console.error,
    }

    // Replace with logger or noop
    console.log = FEATURE_FLAGS.ENABLE_DEBUG_LOGGING
      ? (message: any, ...args: any[]) => logger.debug(String(message), args)
      : noop

    console.debug = FEATURE_FLAGS.ENABLE_DEBUG_LOGGING
      ? (message: any, ...args: any[]) => logger.debug(String(message), args)
      : noop

    console.info = (message: any, ...args: any[]) => logger.info(String(message), args)
    console.warn = (message: any, ...args: any[]) => logger.warn(String(message), args)
    console.error = (message: any, ...args: any[]) => logger.error(String(message), args)

    // Restore on window error to help with debugging critical issues
    window.addEventListener('error', () => {
      Object.assign(console, originalConsole)
    })
  }
}

// Export types
export type { LogEntry, LogTransport }