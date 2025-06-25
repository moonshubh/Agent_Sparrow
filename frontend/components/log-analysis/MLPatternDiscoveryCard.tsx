"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  Brain,
  Zap,
  Search,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Target
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type MLPatternDiscovery } from '@/lib/log-analysis-utils'

interface MLPatternDiscoveryCardProps {
  discovery: MLPatternDiscovery
  className?: string
}

export function MLPatternDiscoveryCard({ discovery, className }: MLPatternDiscoveryCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!discovery) {
    return (
      <Card className={cn("w-full", className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            ML Pattern Discovery
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            <Brain className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No ML pattern data available</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const hasPatterns = discovery.patterns_discovered && discovery.patterns_discovered.length > 0
  const hasRecommendations = discovery.recommendations && discovery.recommendations.length > 0
  const clusterCount = discovery.clustering_summary?.clusters_found || 0

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return 'text-green-600 dark:text-green-400'
    if (confidence >= 0.7) return 'text-amber-600 dark:text-amber-400'
    return 'text-orange-600 dark:text-orange-400'
  }

  const getConfidenceBg = (confidence: number) => {
    if (confidence >= 0.9) return 'bg-green-500/10 border-green-500/20'
    if (confidence >= 0.7) return 'bg-amber-500/10 border-amber-500/20'
    return 'bg-orange-500/10 border-orange-500/20'
  }

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          ML Pattern Discovery
          {hasPatterns && (
            <Badge variant="secondary" className="ml-auto text-xs">
              {discovery.patterns_discovered.length} patterns found
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <Search className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Patterns</span>
            </div>
            <div className="text-sm font-semibold text-foreground">
              {discovery.patterns_discovered?.length || 0}
            </div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Clusters</span>
            </div>
            <div className="text-sm font-semibold text-foreground">
              {clusterCount}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
            <div className="flex items-center gap-2 mb-1">
              <Target className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium text-muted-foreground">Method</span>
            </div>
            <div className="text-xs font-semibold text-foreground">
              {discovery.clustering_summary?.method || 'N/A'}
            </div>
          </div>
        </div>

        {/* Discovered Patterns */}
        {hasPatterns && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-foreground">Discovered Patterns</h4>
              {discovery.patterns_discovered.length > 2 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="text-xs h-auto p-1"
                >
                  {isExpanded ? (
                    <>
                      <ChevronUp className="h-3 w-3 mr-1" />
                      Show Less
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3 mr-1" />
                      Show All ({discovery.patterns_discovered.length})
                    </>
                  )}
                </Button>
              )}
            </div>

            <div className="space-y-2">
              {(isExpanded ? discovery.patterns_discovered : discovery.patterns_discovered.slice(0, 2))
                .map((pattern, index) => {
                  const confidence = Object.values(discovery.pattern_confidence || {})[index] as number || 0.5
                  
                  return (
                    <div
                      key={index}
                      className={cn(
                        "p-3 rounded-lg border",
                        getConfidenceBg(confidence)
                      )}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <h5 className="text-sm font-medium text-foreground mb-1">
                            Pattern #{index + 1}
                          </h5>
                          {pattern.description && (
                            <p className="text-xs text-foreground/80">
                              {pattern.description}
                            </p>
                          )}
                          {pattern.pattern_type && (
                            <Badge variant="outline" className="text-xs mt-1">
                              {pattern.pattern_type}
                            </Badge>
                          )}
                        </div>
                        
                        <div className={cn("text-xs font-semibold", getConfidenceColor(confidence))}>
                          {Math.round(confidence * 100)}%
                        </div>
                      </div>

                      {pattern.frequency && (
                        <div className="text-xs text-muted-foreground">
                          Frequency: {pattern.frequency}
                        </div>
                      )}
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {/* ML Recommendations */}
        {hasRecommendations && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
              <Zap className="h-3 w-3 text-primary" />
              ML Recommendations
            </h4>
            <div className="space-y-1">
              {discovery.recommendations.map((recommendation, index) => (
                <div
                  key={index}
                  className="text-xs text-foreground/80 pl-4 py-1 border-l-2 border-primary/30 bg-primary/5 rounded-r"
                >
                  {recommendation}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {!hasPatterns && !hasRecommendations && (
          <div className="text-center py-4 text-muted-foreground">
            <Brain className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No patterns discovered</p>
            <p className="text-xs mt-1">ML analysis requires sufficient log data</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}