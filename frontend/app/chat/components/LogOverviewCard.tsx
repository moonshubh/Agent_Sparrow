"use client"

import React from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Info,
  Package,
  Server,
  Users,
  Clock,
  FileText,
  Copy,
  Check
} from 'lucide-react'
import { Button } from '@/components/ui/button'

export type LogMetadata = {
  version?: string
  platform?: string
  database_size?: string
  account_count?: number
  total_entries?: number
  error_count?: number
  warning_count?: number
  time_range?: {
    start?: string
    end?: string
  }
  performance_metrics?: {
    avg_response_time?: number
    peak_memory_usage?: string
    slow_queries?: number
  }
  health_status?: 'healthy' | 'warning' | 'critical'
  confidence_level?: number
}

export type ErrorSnippet = {
  timestamp?: string
  level?: 'ERROR' | 'CRITICAL' | 'WARNING'
  message?: string
  stackTrace?: string
  context?: string
  lineNumber?: number
}

interface LogOverviewCardProps {
  metadata?: LogMetadata
  errorSnippets?: ErrorSnippet[]
  rootCause?: {
    summary?: string
    confidence?: number
    category?: string
  }
}

export function LogOverviewCard({ metadata, errorSnippets, rootCause }: LogOverviewCardProps) {
  const [copiedIndex, setCopiedIndex] = React.useState<number | null>(null)
  const copyTimeoutRef = React.useRef<NodeJS.Timeout | null>(null)

  // Cleanup timeout on unmount
  React.useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current)
      }
    }
  }, [])

  if (!metadata && !errorSnippets && !rootCause) return null

  const getHealthIcon = (status?: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
      case 'critical':
        return <AlertTriangle className="w-4 h-4 text-red-500" />
      default:
        return <Info className="w-4 h-4 text-muted-foreground" />
    }
  }

  const copyToClipboard = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedIndex(index)

      // Clear existing timeout if any
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current)
      }

      // Set new timeout and store the reference
      copyTimeoutRef.current = setTimeout(() => {
        setCopiedIndex(null)
        copyTimeoutRef.current = null
      }, 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const formatErrorSnippet = (error: ErrorSnippet) => {
    return `[${error.timestamp || 'N/A'}] ${error.level || 'ERROR'}: ${error.message || 'No message'}
${error.context ? `Context: ${error.context}` : ''}
${error.stackTrace ? `Stack: ${error.stackTrace}` : ''}`
  }

  return (
    <div className="space-y-4">
      {/* Metadata Banner */}
      {metadata && (
        <div className="rounded-lg border border-border/60 bg-gradient-to-br from-background to-muted/20 p-4">
          <div className="flex items-center gap-2 mb-3">
            {getHealthIcon(metadata.health_status)}
            <span className="text-sm font-medium">Log Analysis Overview</span>
            {rootCause?.confidence !== undefined && (
              <span className="ml-auto text-xs px-2 py-1 rounded-full bg-primary/10 text-primary">
                {Math.round(rootCause.confidence * 100)}% confidence
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Version Info */}
            {metadata.version && (
              <div className="flex items-start gap-2">
                <Package className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Version</div>
                  <div className="text-sm font-medium">{metadata.version}</div>
                </div>
              </div>
            )}

            {/* Platform */}
            {metadata.platform && (
              <div className="flex items-start gap-2">
                <Server className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Platform</div>
                  <div className="text-sm font-medium">{metadata.platform}</div>
                </div>
              </div>
            )}

            {/* Database Size */}
            {metadata.database_size && (
              <div className="flex items-start gap-2">
                <Database className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Database</div>
                  <div className="text-sm font-medium">{metadata.database_size}</div>
                </div>
              </div>
            )}

            {/* Account Count */}
            {metadata.account_count !== undefined && (
              <div className="flex items-start gap-2">
                <Users className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Accounts</div>
                  <div className="text-sm font-medium">{metadata.account_count.toLocaleString()}</div>
                </div>
              </div>
            )}

            {/* Error Count */}
            {metadata.error_count !== undefined && (
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Errors</div>
                  <div className="text-sm font-medium text-red-500">{metadata.error_count}</div>
                </div>
              </div>
            )}

            {/* Total Entries */}
            {metadata.total_entries !== undefined && (
              <div className="flex items-start gap-2">
                <FileText className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Log Entries</div>
                  <div className="text-sm font-medium">{metadata.total_entries.toLocaleString()}</div>
                </div>
              </div>
            )}

            {/* Time Range */}
            {metadata.time_range && (
              <div className="flex items-start gap-2">
                <Clock className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Time Range</div>
                  <div className="text-sm font-medium">
                    {metadata.time_range.start ? new Date(metadata.time_range.start).toLocaleDateString() : 'N/A'}
                  </div>
                </div>
              </div>
            )}

            {/* Performance Metrics */}
            {metadata.performance_metrics?.avg_response_time !== undefined && (
              <div className="flex items-start gap-2">
                <Activity className="w-4 h-4 text-muted-foreground mt-0.5" />
                <div>
                  <div className="text-xs text-muted-foreground">Avg Response</div>
                  <div className="text-sm font-medium">{metadata.performance_metrics.avg_response_time}ms</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Root Cause Badge */}
      {rootCause?.summary && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-primary mt-0.5" />
            <div className="flex-1">
              <div className="text-xs text-primary font-medium mb-1">Root Cause Analysis</div>
              <div className="text-sm">{rootCause.summary}</div>
              {rootCause.category && (
                <div className="mt-1 text-xs text-muted-foreground">Category: {rootCause.category}</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Error Snippets with Copy */}
      {errorSnippets && errorSnippets.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium mb-2">Critical Errors</div>
          {errorSnippets.slice(0, 3).map((error, index) => (
            <div key={index} className="rounded-lg border border-border/60 bg-muted/30 p-3 relative group">
              <div className="flex items-start justify-between">
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                      error.level === 'CRITICAL' ? 'bg-red-500/20 text-red-500' :
                      error.level === 'ERROR' ? 'bg-orange-500/20 text-orange-500' :
                      'bg-yellow-500/20 text-yellow-500'
                    }`}>
                      {error.level || 'ERROR'}
                    </span>
                    {error.timestamp && (
                      <span className="text-xs text-muted-foreground">{error.timestamp}</span>
                    )}
                  </div>
                  <div className="text-sm font-mono text-foreground/90">{error.message}</div>
                  {error.context && (
                    <div className="text-xs text-muted-foreground">Context: {error.context}</div>
                  )}
                  {error.stackTrace && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                        Stack trace
                      </summary>
                      <pre className="mt-1 p-2 bg-background rounded text-[10px] overflow-x-auto">
                        {error.stackTrace}
                      </pre>
                    </details>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="w-6 h-6 opacity-0 group-hover:opacity-100 focus:opacity-100 focus-visible:opacity-100 transition-opacity"
                  onClick={() => copyToClipboard(formatErrorSnippet(error), index)}
                  aria-label={`Copy error snippet ${index + 1}`}
                >
                  {copiedIndex === index ? (
                    <Check className="w-3 h-3 text-green-500" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}