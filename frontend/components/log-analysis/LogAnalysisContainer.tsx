"use client"

import React from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { 
  type LogAnalysisData,
  type LogIssue,
  type LogSolution
} from '@/lib/log-analysis-utils'
import { SystemOverviewCard } from './SystemOverviewCard'
import { IssueCard } from './IssueCard'
import { ExecutiveSummaryRenderer } from '../markdown/ExecutiveSummaryRenderer'

interface LogAnalysisContainerProps {
  data: LogAnalysisData
  className?: string
}

export function LogAnalysisContainer({ data, className }: LogAnalysisContainerProps) {
  // Extract data with fallbacks for different response formats
  const systemStats = data.system_metadata || data.system_stats || {}
  const issues = data.identified_issues || data.detailed_issues || []
  const solutions = data.proposed_solutions || data.priority_solutions || []
  // Map backend overall_summary to frontend executive_summary
  const executiveSummary = data.executive_summary || data.executive_summary_md || data.overall_summary || ''
  const immediateActions = data.immediate_actions || []

  // Group solutions by issue or by priority
  const groupSolutionsByIssue = (issues: LogIssue[], solutions: LogSolution[]) => {
    const grouped: { [key: string]: LogSolution[] } = {}
    
    issues.forEach((issue, idx) => {
      const issueKey = issue.id || issue.category || `issue-${idx}`
      grouped[issueKey] = []
    })
    
    // Try to match solutions to issues by category, affected accounts, or other criteria
    solutions.forEach(solution => {
      let matched = false
      
      // Try to match by affected accounts
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
      
      // If no match found, assign to first issue or create general group
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
  
  // Check for critical issues that need immediate attention
  const criticalIssues = issues.filter(issue => 
    issue.severity?.toLowerCase() === 'critical'
  )
  
  const hasCriticalIssues = criticalIssues.length > 0 || immediateActions.length > 0

  return (
    <div className={cn("w-full space-y-6", className)}>
      {/* System Overview */}
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
      
      {/* Issues Section */}
      {issues.length > 0 && (
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Identified Issues ({issues.length})
            </h3>
            <div className="space-y-3">
              {issues.map((issue, idx) => {
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
      )}
      
      {/* Standalone Solutions (if any don't belong to specific issues) */}
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
      
      {/* Executive Summary - Always render when available */}
      {executiveSummary && (
        <ExecutiveSummaryRenderer content={executiveSummary} />
      )}
      
      {/* Empty State */}
      {issues.length === 0 && solutions.length === 0 && !executiveSummary && (
        <div className="text-center py-8 text-muted-foreground">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">No analysis results available</p>
        </div>
      )}
    </div>
  )
}