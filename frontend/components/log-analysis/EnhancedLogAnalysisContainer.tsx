"use client"

import React, { useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { 
  AlertTriangle, 
  BarChart3, 
  Brain, 
  TrendingUp, 
  Shield,
  Eye,
  ChevronDown,
  ChevronUp
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { 
  type EnhancedLogAnalysisData,
  type LogAnalysisData,
  type LogIssue,
  type LogSolution
} from '@/lib/log-analysis-utils'
import { getActiveIssues, getActiveIssueCount, countBySeverity } from '@/lib/utils/issueHelpers'

// Enhanced Components
import { SystemAndAnalysisOverviewCard } from './SystemAndAnalysisOverviewCard'
import { ActionBar } from './ActionBar'
import { PredictiveInsightsCard } from './PredictiveInsightsCard'
import { MLPatternDiscoveryCard } from './MLPatternDiscoveryCard'
import { EnhancedRecommendationsCard } from './EnhancedRecommendationsCard'
import { CorrelationAnalysisCard } from './CorrelationAnalysisCard'
import { DependencyAnalysisCard } from './DependencyAnalysisCard'

// Legacy Components (for backwards compatibility)
import { SystemOverviewCard } from './SystemOverviewCard'
import { IssueCard } from './IssueCard'
import { ExecutiveSummaryRenderer } from '../markdown/ExecutiveSummaryRenderer'

interface EnhancedLogAnalysisContainerProps {
  data: EnhancedLogAnalysisData | LogAnalysisData
  className?: string
}

export function EnhancedLogAnalysisContainer({ data, className }: EnhancedLogAnalysisContainerProps) {
  const [showAdvancedSections, setShowAdvancedSections] = useState(false)
  const [activeTab, setActiveTab] = useState('system')
  
  // Type guard to check if data is enhanced format
  const isEnhancedData = (data: any): data is EnhancedLogAnalysisData => {
    return data && typeof data === 'object' && 'system_metadata' in data && 'environmental_context' in data
  }

  const enhanced = isEnhancedData(data)

  // Extract data with fallbacks for different response formats
  if (enhanced) {
    const {
      overall_summary,
      health_status,
      priority_concerns,
      system_metadata,
      environmental_context,
      identified_issues,
      issue_summary_by_severity,
      correlation_analysis,
      dependency_analysis,
      predictive_insights,
      ml_pattern_discovery,
      proposed_solutions,
      analysis_metrics,
      validation_summary,
      immediate_actions,
      preventive_measures,
      monitoring_recommendations,
      automated_remediation_available
    } = data as EnhancedLogAnalysisData

    // Filter issues and get counts for active issues only
    const activeIssues = getActiveIssues(identified_issues || [])
    const activeIssueCount = getActiveIssueCount(identified_issues || [])
    const severityCounts = countBySeverity(identified_issues || [])
    
    // Check for critical issues that need immediate attention
    const criticalIssues = activeIssues.filter(issue => 
      issue.severity?.toLowerCase() === 'critical'
    )
    
    // Get top issue types for display
    const topIssueTypes = [...new Set(
      activeIssues
        .map(issue => issue.category || 'Unknown')
        .filter(category => category !== 'Unknown')
    )].slice(0, 3)
    
    const hasCriticalIssues = criticalIssues.length > 0 || (immediate_actions && immediate_actions.length > 0)
    const hasAdvancedFeatures = predictive_insights?.length > 0 || 
                              ml_pattern_discovery?.patterns_discovered?.length > 0 ||
                              correlation_analysis ||
                              dependency_analysis

    return (
      <article className={cn("mx-auto max-w-[65ch] w-full space-y-6", className)} data-log-container>
        {/* Critical Issues Banner */}
        {hasCriticalIssues && (
          <Alert className="ring-1 ring-red-500/40 bg-red-900/20 dark:bg-red-900/20 border-red-500/30">
            <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400" />
            <AlertDescription className="text-sm text-red-700 dark:text-red-300">
              <span className="font-semibold">Immediate Actions Required:</span>
              <div className="mt-2 space-y-1">
                {criticalIssues.length > 0 && (
                  <div>
                    {criticalIssues.length} critical issue{criticalIssues.length !== 1 ? 's' : ''} detected requiring urgent attention.
                  </div>
                )}
                {immediate_actions && immediate_actions.slice(0, 3).map((action, idx) => (
                  <div key={idx} className="text-xs">
                    • {action}
                  </div>
                ))}
                {immediate_actions && immediate_actions.length > 3 && (
                  <div className="text-xs text-red-600/80">
                    +{immediate_actions.length - 3} more actions...
                  </div>
                )}
              </div>
            </AlertDescription>
          </Alert>
        )}

        {/* ActionBar */}
        <ActionBar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          issueCount={activeIssueCount}
          criticalIssuesCount={criticalIssues.length}
          hasInsights={hasAdvancedFeatures}
          onSystemOverviewClick={() => setActiveTab('system')}
        />

        {/* Tab Content based on ActiveTab */}
        <div className="w-full">
          {activeTab === 'system' && (
            <div className="space-y-6 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-system" role="tabpanel">
              {/* System Overview Card */}
              <SystemAndAnalysisOverviewCard 
                metadata={system_metadata} 
                metrics={analysis_metrics}
              />
              
              {/* Executive Summary */}
              {overall_summary && (
                <ExecutiveSummaryRenderer content={overall_summary} />
              )}
            </div>
          )}

          {activeTab === 'issues' && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-issues" role="tabpanel">
            {activeIssues && activeIssues.length > 0 ? (
              <div className="space-y-4">
                {/* Issue Summary Header */}
                {topIssueTypes.length > 0 && (
                  <div className="mb-4 p-3 bg-muted/30 border border-border/50 rounded-lg">
                    <div className="text-sm text-muted-foreground">
                      <span className="font-medium">Detected Issue Types:</span>{' '}
                      {topIssueTypes.join(', ')}
                      {activeIssues.length > topIssueTypes.length && ' and more...'}
                    </div>
                  </div>
                )}

                {/* Issue Summary - Use active issue counts */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {Object.entries(severityCounts).filter(([_, count]) => count > 0).map(([severity, count]) => (
                    <div key={severity} className="p-3 rounded-lg bg-muted/30 border border-border/50 text-center">
                      <div className="text-xs text-muted-foreground capitalize">{severity}</div>
                      <div className="text-lg font-semibold text-foreground">{count}</div>
                    </div>
                  ))}
                </div>

                {/* Issues List */}
                {(() => {
                  // Show all active issues - backend schema versioning handled separately
                  const filteredIssues = activeIssues;
                  return (
                    <div className="space-y-3">
                      {filteredIssues.map((issue, idx) => {
                        // Find related solutions
                        const relatedSolutions = proposed_solutions?.filter(solution => 
                          solution.issue_id === issue.id || 
                          solution.affected_accounts?.some(account => 
                            issue.affected_accounts?.includes(account)
                          )
                        ) || []
                        
                        return (
                          <IssueCard
                            key={issue.id || idx}
                            issue={issue}
                            solutions={relatedSolutions}
                            isExpanded={issue.severity?.toLowerCase() === 'critical'}
                          />
                        )
                      })}
                    </div>
                  );
                })()}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No issues detected</p>
                <p className="text-xs mt-1">System appears to be functioning normally</p>
              </div>
            )}
            </div>
          )}

          {activeTab === 'insights' && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-insights" role="tabpanel">
            {hasAdvancedFeatures ? (
              <div className="space-y-4">
                <PredictiveInsightsCard insights={predictive_insights || []} />
                <MLPatternDiscoveryCard discovery={ml_pattern_discovery} />
                
                {/* Advanced Analysis Components */}
                {correlation_analysis && (
                  <CorrelationAnalysisCard analysis={correlation_analysis} />
                )}
                
                {dependency_analysis && (
                  <DependencyAnalysisCard analysis={dependency_analysis} />
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Brain className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No advanced insights available</p>
                <p className="text-xs mt-1">Insights appear with enhanced analysis</p>
              </div>
            )}
            </div>
          )}

          {activeTab === 'actions' && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-actions" role="tabpanel">
            <EnhancedRecommendationsCard
              immediateActions={immediate_actions || []}
              preventiveMeasures={preventive_measures || []}
              monitoringRecommendations={monitoring_recommendations || []}
              automatedRemediationAvailable={automated_remediation_available || false}
            />
            </div>
          )}
        </div>
      </article>
    )
  } else {
    // Legacy format - fallback to existing LogAnalysisContainer logic
    const legacyData = data as LogAnalysisData
    const systemStats = legacyData.system_metadata || legacyData.system_stats || {}
    const issues = legacyData.identified_issues || legacyData.detailed_issues || []
    const solutions = legacyData.proposed_solutions || legacyData.priority_solutions || []
    const executiveSummary = legacyData.executive_summary || legacyData.executive_summary_md || legacyData.overall_summary || ''
    const immediateActions = legacyData.immediate_actions || []

    // Group solutions by issue
    const groupSolutionsByIssue = (issues: LogIssue[], solutions: LogSolution[]) => {
      const grouped: { [key: string]: LogSolution[] } = {}
      
      issues.forEach((issue, idx) => {
        const issueKey = issue.id || issue.category || `issue-${idx}`
        grouped[issueKey] = []
      })
      
      solutions.forEach(solution => {
        let matched = false
        
        if (solution.affected_accounts?.length) {
          for (const issue of issues) {
            const issueKey = issue.id || issue.category || `issue-${issues.indexOf(issue)}`
            if (issue.affected_accounts?.some(account => 
              solution.affected_accounts?.includes(account)
            )) {
              grouped[issueKey] = grouped[issueKey] || []
              grouped[issueKey].push(solution)
              matched = true
              break
            }
          }
        }
        
        if (!matched && issues.length > 0) {
          const firstIssueKey = issues[0].id || issues[0].category || 'issue-0'
          grouped[firstIssueKey] = grouped[firstIssueKey] || []
          grouped[firstIssueKey].push(solution)
        } else if (!matched) {
          grouped['general'] = grouped['general'] || []
          grouped['general'].push(solution)
        }
      })
      
      return grouped
    }

    const groupedSolutions = groupSolutionsByIssue(issues, solutions)
    const activeIssues = getActiveIssues(issues)
    const activeIssueCount = getActiveIssueCount(issues)
    const criticalIssues = activeIssues.filter(issue => issue.severity?.toLowerCase() === 'critical')
    const topIssueTypes = [...new Set(
      activeIssues
        .map(issue => issue.category || 'Unknown')
        .filter(category => category !== 'Unknown')
    )].slice(0, 3)
    const hasCriticalIssues = criticalIssues.length > 0 || immediateActions.length > 0

    return (
      <article className={cn("mx-auto max-w-[65ch] w-full space-y-6", className)} data-log-container>
        {/* Legacy System Overview */}
        <SystemOverviewCard stats={systemStats} />
        
        {/* Critical Issues Banner */}
        {hasCriticalIssues && (
          <Alert className="ring-1 ring-red-500/40 bg-red-900/20 dark:bg-red-900/20 border-red-500/30">
            <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400" />
            <AlertDescription className="text-sm text-red-700 dark:text-red-300">
              <span className="font-semibold">Immediate Actions Required:</span>
              <div className="mt-2 space-y-1">
                {criticalIssues.length > 0 && (
                  <div>
                    {criticalIssues.length} critical issue{criticalIssues.length !== 1 ? 's' : ''} detected requiring urgent attention.
                  </div>
                )}
                {immediateActions.map((action, idx) => (
                  <div key={idx} className="text-xs">
                    • {action}
                  </div>
                ))}
              </div>
            </AlertDescription>
          </Alert>
        )}

        {/* ActionBar for Legacy */}
        <ActionBar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          issueCount={activeIssueCount}
          criticalIssuesCount={criticalIssues.length}
          hasInsights={false}
          onSystemOverviewClick={() => setActiveTab('system')}
        />

        {/* Tab Content */}
        <div className="w-full">
          {activeTab === 'system' && executiveSummary && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-system" role="tabpanel">
              <ExecutiveSummaryRenderer content={executiveSummary} />
            </div>
          )}

          {activeTab === 'issues' && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-issues" role="tabpanel">
        {/* Issues Section */}
        {activeIssues.length > 0 ? (
          <div className="space-y-4">
            {/* Issue Summary Header */}
            {topIssueTypes.length > 0 && (
              <div className="mb-4 p-3 bg-muted/30 border border-border/50 rounded-lg">
                <div className="text-sm text-muted-foreground">
                  <span className="font-medium">Detected Issue Types:</span>{' '}
                  {topIssueTypes.join(', ')}
                  {activeIssues.length > topIssueTypes.length && ' and more...'}
                </div>
              </div>
            )}

            <div>
              <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-orange-500" />
                Identified Issues ({activeIssueCount})
              </h3>
              <div className="space-y-3">
                {activeIssues.map((issue, idx) => {
                  const issueKey = issue.id || issue.category || `issue-${idx}`
                  const relatedSolutions = groupedSolutions[issueKey] || []
                  
                  return (
                    <IssueCard
                      key={issueKey}
                      issue={issue}
                      solutions={relatedSolutions}
                      isExpanded={issue.severity?.toLowerCase() === 'critical'}
                    />
                  )
                })}
              </div>
            </div>
          </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No issues detected</p>
                <p className="text-xs mt-1">System appears to be functioning normally</p>
              </div>
            )}
            </div>
          )}

          {activeTab === 'actions' && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-200 scroll-mt-24" id="panel-actions" role="tabpanel">
              {/* Standalone Solutions */}
              {groupedSolutions['general']?.length > 0 && (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-blue-500" />
                      Additional Recommendations ({groupedSolutions['general'].length})
                    </h3>
                    <div className="space-y-3">
                      {groupedSolutions['general'].map((solution, idx) => (
                        <IssueCard
                          key={`general-${idx}`}
                          issue={{
                            severity: solution.priority,
                            category: 'recommendation',
                            title: solution.title || solution.solution_summary,
                            description: solution.summary,
                            affected_accounts: solution.affected_accounts
                          }}
                          solutions={[solution]}
                          isExpanded={false}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
              {immediateActions.length > 0 && (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                      <Shield className="h-4 w-4 text-amber-500" />
                      Immediate Actions Required
                    </h3>
                    <div className="space-y-2">
                      {immediateActions.map((action, idx) => (
                        <div key={idx} className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                          <p className="text-sm text-amber-900 dark:text-amber-100">{action}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </article>
    )
  }
}