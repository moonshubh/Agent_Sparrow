"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  Activity,
  Database,
  Mail,
  Folder,
  Monitor,
  Clock,
  Cpu,
  Search,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Calendar,
  BarChart3,
  AlertTriangle
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type DetailedSystemMetadata, type AnalysisMetrics, healthStatusClasses } from '@/lib/log-analysis-utils'

interface SystemAndAnalysisOverviewCardProps {
  metadata: DetailedSystemMetadata
  metrics?: AnalysisMetrics
  className?: string
}

interface MetricItem {
  label: string
  value: string | number
  icon: React.ComponentType<{ className?: string }>
  variant?: 'default' | 'health' | 'performance'
  healthStatus?: string
  color?: string
}

export function SystemAndAnalysisOverviewCard({ metadata, metrics, className }: SystemAndAnalysisOverviewCardProps) {
  const [showDetails, setShowDetails] = useState(false)

  if (!metadata) {
    return null
  }

  const formatDate = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString()
    } catch {
      return timestamp
    }
  }


  const getErrorRateColor = (percentage: number) => {
    if (percentage < 5) return 'text-green-600 dark:text-green-400'
    if (percentage < 15) return 'text-amber-600 dark:text-amber-400'
    return 'text-red-600 dark:text-red-400'
  }

  // Core metrics (always shown)
  const coreMetrics: MetricItem[] = [
    {
      label: 'Health',
      value: metadata.mailbird_version ? 'Healthy' : 'Unknown',
      icon: Activity,
      variant: 'health',
      healthStatus: metadata.mailbird_version ? 'healthy' : 'unknown'
    },
    {
      label: 'Accounts',
      value: metadata.account_count ?? 0,
      icon: Mail
    },
    {
      label: 'Folders', 
      value: metadata.folder_count ?? 0,
      icon: Folder
    },
    {
      label: 'DB Size',
      value: metadata.database_size_mb ? `${metadata.database_size_mb} MB` : '0 MB',
      icon: Database
    },
    {
      label: 'Version',
      value: metadata.mailbird_version ?? 'Unknown',
      icon: Monitor
    }
  ]

  const analysisMetrics: MetricItem[] = metrics
    ? [
        {
          label: 'Duration',
          value: `${metrics.analysis_duration_seconds?.toFixed(1) ?? '0'}s`,
          icon: Clock,
          variant: 'performance'
        },
        {
          label: 'Model',
          value: metrics.llm_model_used?.replace('gemini-', '') || 'Unknown',
          icon: Cpu
        },
        {
          label: 'Web Search',
          value: metrics.web_search_performed ? 'Used' : 'Not Used',
          icon: Search
        },
        {
          label: 'Confidence',
          value: metrics.confidence_threshold_met ? 'High' : 'Medium',
          icon: CheckCircle
        },
        {
          label: 'Parser',
          value: `v${metrics.parser_version}`,
          icon: Activity
        },
        metrics.completeness_score !== undefined
          ? {
              label: 'Completeness',
              value: `${Math.round(metrics.completeness_score * 100)}%`,
              icon: BarChart3
            }
          : null
      ].filter(Boolean as any)
    : []

  // Detailed metrics (shown when expanded)
  const detailedMetrics: MetricItem[] = [
    {
      label: 'OS Version',
      value: metadata.os_version ?? 'Unknown',
      icon: Monitor
    },
    {
      label: 'Log Entries',
      value: metadata.total_entries_parsed ?? 0,
      icon: BarChart3
    },
    {
      label: 'Error Rate',
      value: `${metadata.error_rate_percentage?.toFixed(1) ?? 0}%`,
      icon: AlertTriangle,
      color: getErrorRateColor(metadata.error_rate_percentage ?? 0)
    }
  ]

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            System Overview
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDetails(!showDetails)}
            className="text-xs h-auto p-1"
          >
            {showDetails ? (
              <>
                <ChevronUp className="h-3 w-3 mr-1" />
                Less Details
              </>
            ) : (
              <>
                <ChevronDown className="h-3 w-3 mr-1" />
                More Details
              </>
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Core Metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {coreMetrics.map((item, index) => {
            const Icon = item.icon
            const isHealthItem = item.variant === 'health'
            const healthClasses = isHealthItem && item.healthStatus 
              ? healthStatusClasses(item.healthStatus)
              : null

            return (
              <div
                key={index}
                className="flex flex-col items-center space-y-2 p-3 rounded-lg bg-muted/30 border border-border/50"
              >
                <div className="flex items-center gap-2">
                  <Icon className={cn(
                    "h-4 w-4",
                    isHealthItem && healthClasses?.icon || "text-muted-foreground"
                  )} />
                  <span className="text-xs font-medium text-muted-foreground">
                    {item.label}
                  </span>
                </div>
                
                {isHealthItem ? (
                  <Badge 
                    variant="outline" 
                    className={cn(
                      "text-xs font-semibold px-2 py-1",
                      healthClasses?.bg,
                      healthClasses?.text
                    )}
                  >
                    {item.value}
                  </Badge>
                ) : (
                  <div className="text-sm font-semibold text-foreground text-center">
                    {item.value}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {analysisMetrics.length > 0 && (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(8rem,1fr))] gap-4 pt-2">
            {analysisMetrics.map((item, index) => {
              const Icon = item.icon
              return (
                <div key={index} className="flex items-center gap-2 p-2 rounded-lg bg-muted/30 border border-border/50">
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">{item.label}</span>
                  <span className="ml-auto text-sm font-semibold" aria-label={item.label}>{item.value}</span>
                </div>
              )
            })}
          </div>
        )}

        {/* Email Providers */}
        {metadata.email_providers && metadata.email_providers.length > 0 && (
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-2">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">
                Email Providers
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {metadata.email_providers.map((provider, idx) => (
                <Badge key={idx} variant="outline" className="text-xs">
                  {provider}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Detailed Metrics (Collapsible) */}
        {showDetails && (
          <div className="space-y-3 border-t pt-4">
            <h4 className="text-sm font-medium text-foreground">Detailed Metrics</h4>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {detailedMetrics.map((item, index) => {
                const Icon = item.icon

                return (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border/50"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      <span className="text-xs font-medium text-muted-foreground truncate">
                        {item.label}
                      </span>
                    </div>
                    
                    <div className={cn("text-sm font-semibold ml-2 flex-shrink-0", item.color || "text-foreground")}>
                      {item.value}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Log Level Distribution */}
            {metadata.log_level_distribution && Object.keys(metadata.log_level_distribution).length > 0 && (
              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">
                    Log Level Distribution
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {Object.entries(metadata.log_level_distribution).map(([level, count]) => (
                    <div key={level} className="text-center">
                      <div className="text-xs text-muted-foreground">{level}</div>
                      <div className="text-sm font-semibold text-foreground">{count}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Analysis Details */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-1">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">Log Timeframe</span>
                </div>
                <div className="text-xs text-foreground">
                  {metadata.log_timeframe}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">Analyzed</span>
                </div>
                <div className="text-xs text-foreground">
                  {formatDate(metadata.analysis_timestamp)}
                </div>
              </div>
            </div>

            {/* Sync Status */}
            {metadata.sync_status && (
              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-1">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">Sync Status</span>
                </div>
                <Badge variant="outline" className="text-xs">
                  {metadata.sync_status}
                </Badge>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
