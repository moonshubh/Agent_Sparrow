/**
 * Issue filtering and counting utilities
 */

import { type LogIssue } from '@/lib/log-analysis-utils'

export interface CategorizedIssues {
  critical: LogIssue[]
  high: LogIssue[]
  medium: LogIssue[]
  low: LogIssue[]
}

/**
 * Filters issues to only include active ones
 */
export const getActiveIssues = (issues: LogIssue[]) => {
  return issues.filter(issue => {
    // Check if issue has an active field (enhanced format)
    if ('active' in issue && typeof issue.active === 'boolean') {
      return issue.active
    }
    
    // Check remediation status (enhanced format)
    if (issue.remediation_status) {
      return issue.remediation_status !== 'resolved' && issue.remediation_status !== 'ignored'
    }
    
    // Default to active if no specific status indicators
    return true
  })
}

/**
 * Groups issues by severity level for detailed display
 */
export const groupIssues = (issues: LogIssue[]): CategorizedIssues => {
  const activeIssues = getActiveIssues(issues)
  
  return activeIssues.reduce((acc, issue) => {
    const severity = (issue.severity?.toLowerCase() || 'medium') as keyof CategorizedIssues
    
    if (severity in acc) {
      acc[severity].push(issue)
    } else {
      acc.medium.push(issue) // Default fallback
    }
    
    return acc
  }, {
    critical: [] as LogIssue[],
    high: [] as LogIssue[],
    medium: [] as LogIssue[],
    low: [] as LogIssue[]
  })
}

/**
 * Counts issues by severity level, only including active issues
 */
export const countBySeverity = (issues: LogIssue[]) => {
  const activeIssues = getActiveIssues(issues)
  
  return activeIssues.reduce((acc, issue) => {
    const severity = issue.severity?.toLowerCase() || 'unknown'
    const severityKey = severity as keyof typeof acc
    
    if (severityKey in acc) {
      acc[severityKey] += 1
    } else {
      acc.unknown = (acc.unknown || 0) + 1
    }
    
    return acc
  }, {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    unknown: 0
  })
}

/**
 * Gets the total count of active issues
 */
export const getActiveIssueCount = (issues: LogIssue[]) => {
  return getActiveIssues(issues).length
}

/**
 * Groups issues by severity with counts
 */
export const groupIssuesBySeverity = (issues: LogIssue[]) => {
  const activeIssues = getActiveIssues(issues)
  const counts = countBySeverity(issues)
  
  return {
    critical: {
      count: counts.critical,
      issues: activeIssues.filter(i => i.severity?.toLowerCase() === 'critical')
    },
    high: {
      count: counts.high,
      issues: activeIssues.filter(i => i.severity?.toLowerCase() === 'high')
    },
    medium: {
      count: counts.medium,
      issues: activeIssues.filter(i => i.severity?.toLowerCase() === 'medium')
    },
    low: {
      count: counts.low,
      issues: activeIssues.filter(i => i.severity?.toLowerCase() === 'low')
    }
  }
}