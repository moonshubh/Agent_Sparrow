"use client"

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { 
  TrendingUp,
  Clock,
  AlertTriangle,
  Eye,
  Shield,
  BarChart3
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type PredictiveInsight } from '@/lib/log-analysis-utils'

interface PredictiveInsightsCardProps {
  insights: PredictiveInsight[]
  className?: string
}

export function PredictiveInsightsCard({ insights, className }: PredictiveInsightsCardProps) {
  if (!insights || insights.length === 0) {
    return (
      <Card className={cn("w-full", className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            Predictive Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            <BarChart3 className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No predictive insights available</p>
            <p className="text-xs mt-1">Insights appear after historical data analysis</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const getProbabilityColor = (probability: number) => {
    if (probability >= 0.8) return 'text-red-600 dark:text-red-400'
    if (probability >= 0.6) return 'text-orange-600 dark:text-orange-400'
    if (probability >= 0.4) return 'text-amber-600 dark:text-amber-400'
    return 'text-green-600 dark:text-green-400'
  }

  const getProbabilityBg = (probability: number) => {
    if (probability >= 0.8) return 'bg-red-500/10 border-red-500/20'
    if (probability >= 0.6) return 'bg-orange-500/10 border-orange-500/20'
    if (probability >= 0.4) return 'bg-amber-500/10 border-amber-500/20'
    return 'bg-green-500/10 border-green-500/20'
  }

  const getConfidenceVariant = (confidence: number): "default" | "secondary" | "outline" => {
    if (confidence >= 0.8) return 'default'
    if (confidence >= 0.6) return 'outline'
    return 'secondary'
  }

  // Sort by probability descending
  const sortedInsights = [...insights].sort((a, b) => b.probability - a.probability)

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-primary" />
          Predictive Insights ({insights.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {sortedInsights.map((insight, index) => (
          <div
            key={index}
            className={cn(
              "p-4 rounded-lg border",
              getProbabilityBg(insight.probability)
            )}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1">
                <h4 className="font-medium text-foreground mb-1">
                  {insight.issue_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </h4>
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="h-3 w-3 text-muted-foreground" />
                  <span className="text-muted-foreground">Expected: {insight.timeframe}</span>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <Badge 
                  variant={getConfidenceVariant(insight.confidence_score)}
                  className="text-xs"
                >
                  {Math.round(insight.confidence_score * 100)}% confidence
                </Badge>
                <div className={cn("text-sm font-semibold", getProbabilityColor(insight.probability))}>
                  {Math.round(insight.probability * 100)}%
                </div>
              </div>
            </div>

            {/* Early Indicators */}
            {insight.early_indicators && insight.early_indicators.length > 0 && (
              <div className="mb-3">
                <div className="flex items-center gap-1 mb-2">
                  <Eye className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">
                    Early Warning Signs
                  </span>
                </div>
                <div className="space-y-1">
                  {insight.early_indicators.slice(0, 3).map((indicator, idx) => (
                    <div key={idx} className="text-xs text-foreground/80 pl-4 border-l-2 border-border">
                      {indicator}
                    </div>
                  ))}
                  {insight.early_indicators.length > 3 && (
                    <div className="text-xs text-muted-foreground pl-4">
                      +{insight.early_indicators.length - 3} more indicators
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Preventive Actions */}
            {insight.preventive_actions && insight.preventive_actions.length > 0 && (
              <div>
                <div className="flex items-center gap-1 mb-2">
                  <Shield className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">
                    Preventive Actions
                  </span>
                </div>
                <div className="space-y-1">
                  {insight.preventive_actions.slice(0, 2).map((action, idx) => (
                    <div key={idx} className="text-xs text-foreground/80 pl-4 border-l-2 border-border">
                      {action}
                    </div>
                  ))}
                  {insight.preventive_actions.length > 2 && (
                    <div className="text-xs text-muted-foreground pl-4">
                      +{insight.preventive_actions.length - 2} more actions
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* High-risk alerts */}
        {sortedInsights.some(insight => insight.probability >= 0.8) && (
          <Alert className="ring-1 ring-orange-500/40 bg-orange-900/20 border-orange-500/30">
            <AlertTriangle className="h-4 w-4 text-orange-600 dark:text-orange-400" />
            <AlertDescription className="text-sm text-orange-700 dark:text-orange-300">
              <span className="font-semibold">High-Probability Issues Detected:</span>
              <div className="mt-1 text-xs">
                Consider implementing preventive measures to avoid future problems.
              </div>
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}