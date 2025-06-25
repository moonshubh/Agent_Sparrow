"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  GitBranch,
  Target,
  AlertTriangle,
  ArrowRight,
  ArrowDown,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Activity,
  Zap,
  Eye
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { type DependencyAnalysis } from '@/lib/log-analysis-utils'

interface DependencyAnalysisCardProps {
  analysis: DependencyAnalysis
  className?: string
}


export function DependencyAnalysisCard({ analysis, className }: DependencyAnalysisCardProps) {
  const [selectedTab, setSelectedTab] = useState<string>('overview')
  const [showDetails, setShowDetails] = useState(false)
  
  if (!analysis || !analysis.graph_summary) {
    return (
      <Card className={cn("w-full", className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            Dependency Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            <GitBranch className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No dependency data available</p>
            <p className="text-xs mt-1">Dependencies appear when issues have relationships</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const getCentralityColor = (score: number) => {
    if (score >= 0.8) return 'text-red-600 dark:text-red-400'
    if (score >= 0.6) return 'text-orange-600 dark:text-orange-400'
    if (score >= 0.4) return 'text-amber-600 dark:text-amber-400'
    return 'text-green-600 dark:text-green-400'
  }

  const getCentralityBg = (score: number) => {
    if (score >= 0.8) return 'bg-red-500/10 border-red-500/20'
    if (score >= 0.6) return 'bg-orange-500/10 border-orange-500/20'
    if (score >= 0.4) return 'bg-amber-500/10 border-amber-500/20'
    return 'bg-green-500/10 border-green-500/20'
  }

  const getImpactLevelColor = (level: string) => {
    switch (level?.toLowerCase()) {
      case 'critical':
      case 'high':
        return 'text-red-600 dark:text-red-400'
      case 'medium':
        return 'text-amber-600 dark:text-amber-400'
      case 'low':
        return 'text-green-600 dark:text-green-400'
      default:
        return 'text-muted-foreground'
    }
  }

  // Extract data from analysis
  const graphSummary = analysis.graph_summary || {}
  const rootCauses = analysis.root_causes || []
  const primarySymptoms = analysis.primary_symptoms || []
  const cyclicalDependencies = analysis.cyclical_dependencies || []
  const centralityMeasures = analysis.centrality_measures || {}
  const issueRelationships = analysis.issue_relationships || []

  const totalNodes = graphSummary.total_nodes || (rootCauses.length + primarySymptoms.length)
  const totalEdges = graphSummary.total_edges || issueRelationships.length
  const graphComplexity = graphSummary.complexity_score || 0.5

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            Dependency Analysis
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
            <div className="text-xs text-muted-foreground">Nodes</div>
            <div className="text-lg font-semibold text-foreground">{totalNodes}</div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Relations</div>
            <div className="text-lg font-semibold text-primary">{totalEdges}</div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Root Causes</div>
            <div className="text-lg font-semibold text-red-600 dark:text-red-400">{rootCauses.length}</div>
          </div>
          
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
            <div className="text-xs text-muted-foreground">Cycles</div>
            <div className="text-lg font-semibold text-orange-600 dark:text-orange-400">{cyclicalDependencies.length}</div>
          </div>
        </div>

        {/* Analysis Tabs */}
        <Tabs value={selectedTab} onValueChange={setSelectedTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="overview" className="flex items-center gap-2">
              <Eye className="h-3 w-3" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="relationships" className="flex items-center gap-2">
              <ArrowRight className="h-3 w-3" />
              Relationships ({issueRelationships.length})
            </TabsTrigger>
            <TabsTrigger value="cycles" className="flex items-center gap-2">
              <RotateCcw className="h-3 w-3" />
              Cycles ({cyclicalDependencies.length})
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-4">
            {/* Root Causes */}
            {rootCauses.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <Target className="h-3 w-3 text-red-500" />
                  Root Causes ({rootCauses.length})
                </h4>
                <div className="space-y-2">
                  {rootCauses.slice(0, showDetails ? 10 : 5).map((cause, index) => {
                    const centralityScore = centralityMeasures[cause] || 0.5
                    return (
                      <div
                        key={index}
                        className={cn(
                          "p-3 rounded-lg border",
                          getCentralityBg(centralityScore)
                        )}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <h5 className="font-medium text-foreground text-sm">
                              {cause.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            </h5>
                            <p className="text-xs text-muted-foreground mt-1">
                              Primary source of cascading issues
                            </p>
                          </div>
                          
                          <div className="flex items-center gap-2 ml-3">
                            <Badge variant="outline" className="text-xs">
                              Root Cause
                            </Badge>
                            <div className={cn("text-xs font-semibold", getCentralityColor(centralityScore))}>
                              {Math.round(centralityScore * 100)}%
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                  
                  {rootCauses.length > 5 && !showDetails && (
                    <div className="text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowDetails(true)}
                        className="text-xs"
                      >
                        Show {rootCauses.length - 5} more root causes
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Primary Symptoms */}
            {primarySymptoms.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <AlertTriangle className="h-3 w-3 text-amber-500" />
                  Primary Symptoms ({primarySymptoms.length})
                </h4>
                <div className="space-y-2">
                  {primarySymptoms.slice(0, showDetails ? 10 : 5).map((symptom, index) => {
                    const centralityScore = centralityMeasures[symptom] || 0.3
                    return (
                      <div
                        key={index}
                        className="p-3 rounded-lg bg-muted/30 border border-border/50"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <h5 className="font-medium text-foreground text-sm">
                              {symptom.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            </h5>
                            <p className="text-xs text-muted-foreground mt-1">
                              Observable effect of underlying issues
                            </p>
                          </div>
                          
                          <div className="flex items-center gap-2 ml-3">
                            <Badge variant="secondary" className="text-xs">
                              Symptom
                            </Badge>
                            <div className={cn("text-xs font-semibold", getCentralityColor(centralityScore))}>
                              {Math.round(centralityScore * 100)}%
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                  
                  {primarySymptoms.length > 5 && !showDetails && (
                    <div className="text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowDetails(true)}
                        className="text-xs"
                      >
                        Show {primarySymptoms.length - 5} more symptoms
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Graph Statistics */}
            {showDetails && Object.keys(centralityMeasures).length > 0 && (
              <div className="border-t pt-4">
                <h4 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
                  <Activity className="h-3 w-3 text-primary" />
                  Centrality Measures
                </h4>
                <div className="p-3 rounded-lg bg-muted/30 border border-border/50">
                  <div className="text-xs text-muted-foreground mb-2">
                    Importance of each issue in the dependency network
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    {Object.entries(centralityMeasures).slice(0, 8).map(([issue, score]) => (
                      <div key={issue} className="flex justify-between items-center">
                        <span className="truncate mr-2">{issue.replace(/_/g, ' ')}</span>
                        <div className="flex items-center gap-1">
                          <div className={cn("w-2 h-2 rounded-full", getCentralityBg(score as number).split(' ')[0])} />
                          <span className={cn("font-medium", getCentralityColor(score as number))}>
                            {Math.round((score as number) * 100)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          {/* Relationships Tab */}
          <TabsContent value="relationships" className="space-y-3">
            {issueRelationships.length > 0 ? (
              <div className="space-y-2">
                {issueRelationships.slice(0, showDetails ? 15 : 5).map((relationship, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg bg-muted/30 border border-border/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="text-sm font-medium text-foreground">
                          {relationship.source_issue || relationship.source || 'Issue A'}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {relationship.description || `${relationship.relationship_type || 'affects'} the following issue`}
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <ArrowRight className="h-4 w-4 text-primary" />
                        <Badge 
                          variant="outline" 
                          className={cn(
                            "text-xs",
                            relationship.relationship_type === 'causes' ? 'text-red-600' :
                            relationship.relationship_type === 'triggers' ? 'text-orange-600' :
                            relationship.relationship_type === 'correlates' ? 'text-amber-600' :
                            'text-primary'
                          )}
                        >
                          {relationship.relationship_type || 'affects'}
                        </Badge>
                      </div>
                      
                      <div className="flex-1">
                        <div className="text-sm font-medium text-foreground text-right">
                          {relationship.target_issue || relationship.target || 'Issue B'}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1 text-right">
                          {relationship.strength && (
                            <span>Strength: {Math.round((relationship.strength as number) * 100)}%</span>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    {relationship.impact_description && (
                      <div className="text-xs text-foreground/80 mt-2 pt-2 border-t border-border/30">
                        <span className="font-medium">Impact: </span>
                        {relationship.impact_description}
                      </div>
                    )}
                  </div>
                ))}
                
                {issueRelationships.length > 5 && !showDetails && (
                  <div className="text-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowDetails(true)}
                      className="text-xs"
                    >
                      Show {issueRelationships.length - 5} more relationships
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground">
                <ArrowRight className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No issue relationships found</p>
              </div>
            )}
          </TabsContent>

          {/* Cycles Tab */}
          <TabsContent value="cycles" className="space-y-3">
            {cyclicalDependencies.length > 0 ? (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
                  <div className="flex items-center gap-2 mb-2">
                    <RotateCcw className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                    <span className="text-sm font-medium text-orange-600 dark:text-orange-400">
                      Circular Dependencies Detected
                    </span>
                  </div>
                  <p className="text-xs text-orange-700 dark:text-orange-300">
                    These issues create feedback loops that can perpetuate problems. Breaking these cycles is critical for resolution.
                  </p>
                </div>
                
                {cyclicalDependencies.slice(0, showDetails ? 10 : 3).map((cycle, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg border border-orange-500/20 bg-orange-500/5"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="outline" className="text-xs text-orange-600">
                        Cycle {index + 1}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {cycle.length} issues in loop
                      </span>
                    </div>
                    
                    <div className="flex items-center gap-2 flex-wrap">
                      {cycle.map((issue, issueIndex) => (
                        <React.Fragment key={issueIndex}>
                          <span className="text-sm font-medium text-foreground px-2 py-1 rounded bg-muted/50">
                            {issue.replace(/_/g, ' ')}
                          </span>
                          {issueIndex < cycle.length - 1 && (
                            <ArrowRight className="h-3 w-3 text-orange-500" />
                          )}
                          {issueIndex === cycle.length - 1 && (
                            <RotateCcw className="h-3 w-3 text-orange-500" />
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                    
                    <div className="text-xs text-orange-700 dark:text-orange-300 mt-2">
                      <span className="font-medium">Recommendation: </span>
                      Address the root cause in this cycle to break the dependency loop.
                    </div>
                  </div>
                ))}
                
                {cyclicalDependencies.length > 3 && !showDetails && (
                  <div className="text-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowDetails(true)}
                      className="text-xs"
                    >
                      Show {cyclicalDependencies.length - 3} more cycles
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-4 text-muted-foreground">
                <Zap className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No circular dependencies found</p>
                <p className="text-xs mt-1">This is good - issues don't create feedback loops</p>
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Graph Summary */}
        {showDetails && graphSummary && Object.keys(graphSummary).length > 1 && (
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
              <GitBranch className="h-3 w-3 text-primary" />
              Network Statistics
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-2 rounded bg-muted/30 border border-border/50 text-center">
                <div className="text-xs text-muted-foreground">Complexity</div>
                <div className={cn(
                  "text-sm font-semibold",
                  graphComplexity > 0.7 ? 'text-red-600 dark:text-red-400' :
                  graphComplexity > 0.4 ? 'text-amber-600 dark:text-amber-400' :
                  'text-green-600 dark:text-green-400'
                )}>
                  {Math.round(graphComplexity * 100)}%
                </div>
              </div>
              
              {graphSummary.density && (
                <div className="p-2 rounded bg-muted/30 border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground">Density</div>
                  <div className="text-sm font-semibold text-foreground">
                    {Math.round(graphSummary.density * 100)}%
                  </div>
                </div>
              )}
              
              {graphSummary.max_depth && (
                <div className="p-2 rounded bg-muted/30 border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground">Max Depth</div>
                  <div className="text-sm font-semibold text-foreground">
                    {graphSummary.max_depth}
                  </div>
                </div>
              )}
              
              {graphSummary.avg_degree && (
                <div className="p-2 rounded bg-muted/30 border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground">Avg Degree</div>
                  <div className="text-sm font-semibold text-foreground">
                    {Math.round(graphSummary.avg_degree * 10) / 10}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
