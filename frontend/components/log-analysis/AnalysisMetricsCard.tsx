"use client"

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { 
  BarChart3,
  Clock,
  Cpu,
  Search,
  CheckCircle,
  AlertCircle,
  Activity
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type AnalysisMetrics, type ValidationSummary } from '@/lib/log-analysis-utils'

interface AnalysisMetricsCardProps {
  metrics: AnalysisMetrics
  validation?: ValidationSummary
  className?: string
}

export function AnalysisMetricsCard({ metrics, validation, className }: AnalysisMetricsCardProps) {
  if (!metrics) {
    return null
  }

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
    return `${(seconds / 3600).toFixed(1)}h`
  }

  const getPerformanceColor = (seconds: number) => {
    if (seconds < 30) return 'text-green-600 dark:text-green-400'
    if (seconds < 120) return 'text-amber-600 dark:text-amber-400'
    return 'text-orange-600 dark:text-orange-400'
  }

  const getConfidenceColor = (met: boolean) => {
    return met ? 'text-green-600 dark:text-green-400' : 'text-orange-600 dark:text-orange-400'
  }

  const completenessPercentage = metrics.completeness_score 
    ? Math.round(metrics.completeness_score * 100) 
    : null

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-primary" />
          Analysis Metrics
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Performance Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Duration</span>
            </div>
            <div className={cn("text-sm font-semibold", getPerformanceColor(metrics.analysis_duration_seconds))}>
              {formatDuration(metrics.analysis_duration_seconds)}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Model</span>
            </div>
            <div className="text-xs font-semibold text-foreground">
              {metrics.llm_model_used?.replace('gemini-', '') || 'Unknown'}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <Search className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Web Search</span>
            </div>
            <Badge variant={metrics.web_search_performed ? "default" : "secondary"} className="text-xs">
              {metrics.web_search_performed ? 'Used' : 'Not Used'}
            </Badge>
          </div>

          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Confidence</span>
            </div>
            <div className={cn("text-xs font-semibold", getConfidenceColor(metrics.confidence_threshold_met))}>
              {metrics.confidence_threshold_met ? 'High' : 'Medium'}
            </div>
          </div>
        </div>

        {/* Additional Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <Activity className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Parser Version</span>
            </div>
            <div className="text-sm font-semibold text-foreground">
              v{metrics.parser_version}
            </div>
          </div>

          {completenessPercentage !== null && (
            <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
              <div className="flex items-center gap-2 mb-1">
                <BarChart3 className="h-3 w-3 text-muted-foreground" />
                <span className="text-xs font-medium text-muted-foreground">Completeness</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="text-sm font-semibold text-foreground">
                  {completenessPercentage}%
                </div>
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-primary transition-all duration-500"
                    style={{ width: `${completenessPercentage}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Validation Summary */}
        {validation && (
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-primary" />
              Input Validation
            </h4>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-muted-foreground">Status</span>
                </div>
                <Badge variant={validation.is_valid ? "default" : "destructive"} className="text-xs">
                  {validation.is_valid ? 'Valid' : 'Issues Found'}
                </Badge>
              </div>

              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-muted-foreground">Language</span>
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {validation.detected_language?.toUpperCase() || 'Unknown'}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-muted-foreground">Platform</span>
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {validation.detected_platform || 'Unknown'}
                </div>
              </div>
            </div>

            {/* Validation Issues */}
            {validation.issues_found && validation.issues_found.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-1">
                  <AlertCircle className="h-3 w-3 text-orange-500" />
                  <span className="text-xs font-medium text-muted-foreground">
                    Issues Found ({validation.issues_found.length})
                  </span>
                </div>
                <div className="space-y-1">
                  {validation.issues_found.slice(0, 3).map((issue, idx) => (
                    <div key={idx} className="text-xs text-foreground/80 pl-4 border-l-2 border-orange-500/30">
                      {issue}
                    </div>
                  ))}
                  {validation.issues_found.length > 3 && (
                    <div className="text-xs text-muted-foreground pl-4">
                      +{validation.issues_found.length - 3} more issues
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Preprocessing Applied */}
            {validation.preprocessing_applied && (
              <div className="mt-2">
                <Badge variant="outline" className="text-xs">
                  Preprocessing Applied
                </Badge>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}