"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  Network,
  Clock,
  Users,
  AlertTriangle,
  TrendingUp,
  GitBranch,
  ChevronDown,
  ChevronUp,
  Activity
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type CorrelationAnalysis } from '@/lib/log-analysis-utils'

interface CorrelationAnalysisCardProps {
  analysis: CorrelationAnalysis
  className?: string
}

interface CorrelationNode {
  id: string
  label: string
  strength: number
  type: 'temporal' | 'account' | 'issue_type'
  metadata?: Record<string, any>
}

interface CorrelationEdge {
  source: string
  target: string
  strength: number
  correlation_type: string
  confidence: number
}

export function CorrelationAnalysisCard({ analysis, className }: CorrelationAnalysisCardProps) {
  const [selectedTab, setSelectedTab] = useState<'temporal' | 'account' | 'issue_type'>('temporal')
  const [showDetails, setShowDetails] = useState(false)
  
  if (!analysis || !analysis.analysis_summary) {
    return (
      <Card className={cn("w-full", className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Network className="h-4 w-4 text-primary" />
            Correlation Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            <Network className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No correlation data available</p>
            <p className="text-xs mt-1">Correlations appear with sufficient data patterns</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const getCorrelationStrengthColor = (strength: number) => {
    if (strength >= 0.8) return 'text-red-600 dark:text-red-400'
    if (strength >= 0.6) return 'text-orange-600 dark:text-orange-400'
    if (strength >= 0.4) return 'text-amber-600 dark:text-amber-400'
    return 'text-green-600 dark:text-green-400'
  }

  const getCorrelationStrengthBg = (strength: number) => {
    if (strength >= 0.8) return 'bg-red-500/10 border-red-500/20'
    if (strength >= 0.6) return 'bg-orange-500/10 border-orange-500/20'
    if (strength >= 0.4) return 'bg-amber-500/10 border-amber-500/20'
    return 'bg-green-500/10 border-green-500/20'
  }

  const formatCorrelationStrength = (strength: number): string => {
    if (strength >= 0.8) return 'Very Strong'
    if (strength >= 0.6) return 'Strong'
    if (strength >= 0.4) return 'Moderate'
    if (strength >= 0.2) return 'Weak'
    return 'Very Weak'
  }

  // Extract correlation data from analysis
  const temporalCorrelations = analysis.temporal_correlations || []
  const accountCorrelations = analysis.account_correlations || []
  const issueTypeCorrelations = analysis.issue_type_correlations || []
  const analysisOverview = analysis.analysis_summary || {}

  const totalCorrelations = temporalCorrelations.length + accountCorrelations.length + issueTypeCorrelations.length
  const strongCorrelations = [
    ...temporalCorrelations,
    ...accountCorrelations,
    ...issueTypeCorrelations
  ].filter(corr => (corr.strength || corr.correlation_strength || 0) >= 0.6).length

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Network className="h-4 w-4 text-primary" />
            Correlation Analysis
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
        {/* Overview Metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Total Found</div>
            <div className="text-lg font-semibold text-foreground">{totalCorrelations}</div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Strong Links</div>
            <div className="text-lg font-semibold text-orange-600 dark:text-orange-400">{strongCorrelations}</div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Confidence</div>
            <div className="text-lg font-semibold text-green-600 dark:text-green-400">
              {Math.round((analysisOverview.average_confidence || 0.75) * 100)}%
            </div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Complexity</div>
            <div className="text-lg font-semibold text-foreground">
              {analysisOverview.complexity_score ? 
                Math.round(analysisOverview.complexity_score * 10) / 10 : 
                'Medium'
              }
            </div>
          </div>
        </div>

        {/* Correlation Type Tabs */}
        <Tabs value={selectedTab} onValueChange={setSelectedTab as (value: string) => void} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="temporal" className="flex items-center gap-2">
              <Clock className="h-3 w-3" />
              Temporal ({temporalCorrelations.length})
            </TabsTrigger>
            <TabsTrigger value="account" className="flex items-center gap-2">
              <Users className="h-3 w-3" />
              Account ({accountCorrelations.length})
            </TabsTrigger>
            <TabsTrigger value="issue_type" className="flex items-center gap-2">
              <AlertTriangle className="h-3 w-3" />
              Issue Type ({issueTypeCorrelations.length})
            </TabsTrigger>
          </TabsList>

          {/* Temporal Correlations */}
          <TabsContent value="temporal" className="space-y-3">
            {temporalCorrelations.length > 0 ? (
              <div className="space-y-2">
                {temporalCorrelations.slice(0, showDetails ? 10 : 3).map((correlation, index) => {
                  const strength = correlation.strength || correlation.correlation_strength || 0
                  return (
                    <div
                      key={index}
                      className={cn(
                        "p-3 rounded-lg border",
                        getCorrelationStrengthBg(strength)
                      )}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <h4 className="font-medium text-foreground text-sm">
                            {correlation.pattern_name || correlation.name || `Temporal Pattern ${index + 1}`}
                          </h4>
                          <p className="text-xs text-muted-foreground mt-1">
                            {correlation.description || correlation.pattern_description || 
                             `Issues occurring ${correlation.time_pattern || 'in related timeframes'}`}
                          </p>
                        </div>
                        
                        <div className="flex items-center gap-2 ml-3">
                          <Badge variant="outline" className="text-xs">
                            {formatCorrelationStrength(strength)}
                          </Badge>
                          <div className={cn("text-xs font-semibold", getCorrelationStrengthColor(strength))}>
                            {Math.round(strength * 100)}%
                          </div>
                        </div>
                      </div>
                      
                      {correlation.time_windows && (
                        <div className="text-xs text-foreground/80 mt-2">
                          <span className="font-medium">Time Windows: </span>
                          {correlation.time_windows.slice(0, 3).join(', ')}
                          {correlation.time_windows.length > 3 && ` (+${correlation.time_windows.length - 3} more)`}
                        </div>
                      )}
                      
                      {correlation.affected_operations && (
                        <div className="text-xs text-foreground/80 mt-1">
                          <span className="font-medium">Operations: </span>
                          {correlation.affected_operations.slice(0, 2).join(', ')}
                          {correlation.affected_operations.length > 2 && ` (+${correlation.affected_operations.length - 2} more)`}
                        </div>
                      )}
                    </div>
                  )
                })}
                
                {temporalCorrelations.length > 3 && !showDetails && (
                  <div className="text-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowDetails(true)}
                      className="text-xs"
                    >
                      Show {temporalCorrelations.length - 3} more temporal correlations
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground">
                <Clock className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No temporal correlations found</p>
              </div>
            )}
          </TabsContent>

          {/* Account Correlations */}
          <TabsContent value="account" className="space-y-3">
            {accountCorrelations.length > 0 ? (
              <div className="space-y-2">
                {accountCorrelations.slice(0, showDetails ? 10 : 3).map((correlation, index) => {
                  const strength = correlation.strength || correlation.correlation_strength || 0
                  return (
                    <div
                      key={index}
                      className={cn(
                        "p-3 rounded-lg border",
                        getCorrelationStrengthBg(strength)
                      )}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <h4 className="font-medium text-foreground text-sm">
                            {correlation.account_pattern || correlation.name || `Account Pattern ${index + 1}`}
                          </h4>
                          <p className="text-xs text-muted-foreground mt-1">
                            {correlation.description || 
                             `${correlation.affected_accounts?.length || 'Multiple'} accounts showing similar issues`}
                          </p>
                        </div>
                        
                        <div className="flex items-center gap-2 ml-3">
                          <Badge variant="outline" className="text-xs">
                            {formatCorrelationStrength(strength)}
                          </Badge>
                          <div className={cn("text-xs font-semibold", getCorrelationStrengthColor(strength))}>
                            {Math.round(strength * 100)}%
                          </div>
                        </div>
                      </div>
                      
                      {correlation.affected_accounts && (
                        <div className="text-xs text-foreground/80 mt-2">
                          <span className="font-medium">Accounts: </span>
                          {correlation.affected_accounts.slice(0, 3).join(', ')}
                          {correlation.affected_accounts.length > 3 && 
                           ` (+${correlation.affected_accounts.length - 3} more)`}
                        </div>
                      )}
                      
                      {correlation.common_issues && (
                        <div className="text-xs text-foreground/80 mt-1">
                          <span className="font-medium">Common Issues: </span>
                          {correlation.common_issues.slice(0, 2).join(', ')}
                        </div>
                      )}
                    </div>
                  )
                })}
                
                {accountCorrelations.length > 3 && !showDetails && (
                  <div className="text-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowDetails(true)}
                      className="text-xs"
                    >
                      Show {accountCorrelations.length - 3} more account correlations
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground">
                <Users className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No account correlations found</p>
              </div>
            )}
          </TabsContent>

          {/* Issue Type Correlations */}
          <TabsContent value="issue_type" className="space-y-3">
            {issueTypeCorrelations.length > 0 ? (
              <div className="space-y-2">
                {issueTypeCorrelations.slice(0, showDetails ? 10 : 3).map((correlation, index) => {
                  const strength = correlation.strength || correlation.correlation_strength || 0
                  return (
                    <div
                      key={index}
                      className={cn(
                        "p-3 rounded-lg border",
                        getCorrelationStrengthBg(strength)
                      )}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <h4 className="font-medium text-foreground text-sm">
                            {correlation.issue_relationship || correlation.name || `Issue Relationship ${index + 1}`}
                          </h4>
                          <p className="text-xs text-muted-foreground mt-1">
                            {correlation.description || 
                             `${correlation.primary_issue || 'Issues'} often occur together with ${correlation.secondary_issue || 'related problems'}`}
                          </p>
                        </div>
                        
                        <div className="flex items-center gap-2 ml-3">
                          <Badge variant="outline" className="text-xs">
                            {formatCorrelationStrength(strength)}
                          </Badge>
                          <div className={cn("text-xs font-semibold", getCorrelationStrengthColor(strength))}>
                            {Math.round(strength * 100)}%
                          </div>
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-3 mt-2">
                        {correlation.primary_issue && (
                          <div className="text-xs">
                            <span className="text-muted-foreground">Primary: </span>
                            <span className="font-medium text-foreground">{correlation.primary_issue}</span>
                          </div>
                        )}
                        
                        {correlation.secondary_issue && (
                          <div className="text-xs">
                            <span className="text-muted-foreground">Secondary: </span>
                            <span className="font-medium text-foreground">{correlation.secondary_issue}</span>
                          </div>
                        )}
                      </div>
                      
                      {correlation.co_occurrence_rate && (
                        <div className="text-xs text-foreground/80 mt-2">
                          <span className="font-medium">Co-occurrence Rate: </span>
                          {Math.round(correlation.co_occurrence_rate * 100)}%
                        </div>
                      )}
                    </div>
                  )
                })}
                
                {issueTypeCorrelations.length > 3 && !showDetails && (
                  <div className="text-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowDetails(true)}
                      className="text-xs"
                    >
                      Show {issueTypeCorrelations.length - 3} more issue correlations
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground">
                <AlertTriangle className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No issue type correlations found</p>
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Correlation Matrix Visualization (if available) */}
        {analysis.correlation_matrix && Object.keys(analysis.correlation_matrix).length > 0 && showDetails && (
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
              <GitBranch className="h-3 w-3 text-primary" />
              Correlation Matrix
            </h4>
            <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
              <div className="text-xs text-muted-foreground mb-2">
                Strength of relationships between different issue types and patterns
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                {Object.entries(analysis.correlation_matrix).slice(0, 6).map(([key, value]) => (
                  <div key={key} className="flex justify-between">
                    <span className="truncate mr-2">{key.replace(/_/g, ' ')}</span>
                    <span className={cn("font-medium", getCorrelationStrengthColor(value as number))}>
                      {Math.round((value as number) * 100)}%
                    </span>
                  </div>
                ))}
              </div>
              {Object.keys(analysis.correlation_matrix).length > 6 && (
                <div className="text-xs text-muted-foreground mt-2">
                  +{Object.keys(analysis.correlation_matrix).length - 6} more correlations
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
