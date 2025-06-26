/**
 * Tests for issue filtering and counting utilities
 */

import { describe, it, expect } from 'vitest'
import { getActiveIssues, getActiveIssueCount, countBySeverity } from '../issueHelpers'
import { type LogIssue } from '@/lib/log-analysis-utils'

describe('issueHelpers', () => {
  const mockIssues: LogIssue[] = [
    {
      id: '1',
      severity: 'critical',
      category: 'email',
      title: 'Critical email issue',
      active: true
    },
    {
      id: '2', 
      severity: 'high',
      category: 'sync',
      title: 'High sync issue',
      active: true
    },
    {
      id: '3',
      severity: 'medium',
      category: 'performance',
      title: 'Medium perf issue',
      active: false
    },
    {
      id: '4',
      severity: 'low',
      category: 'ui',
      title: 'Low UI issue',
      remediation_status: 'resolved'
    },
    {
      id: '5',
      severity: 'critical',
      category: 'database',
      title: 'Another critical issue',
      remediation_status: 'pending'
    }
  ]

  describe('getActiveIssues', () => {
    it('filters out inactive issues', () => {
      const activeIssues = getActiveIssues(mockIssues)
      expect(activeIssues).toHaveLength(3)
      expect(activeIssues.every(issue => issue.active !== false)).toBe(true)
    })

    it('filters out resolved issues', () => {
      const activeIssues = getActiveIssues(mockIssues)
      const resolvedIssue = activeIssues.find(issue => issue.remediation_status === 'resolved')
      expect(resolvedIssue).toBeUndefined()
    })

    it('includes issues with pending remediation status', () => {
      const activeIssues = getActiveIssues(mockIssues)
      const pendingIssue = activeIssues.find(issue => issue.remediation_status === 'pending')
      expect(pendingIssue).toBeDefined()
    })
  })

  describe('getActiveIssueCount', () => {
    it('returns correct count of active issues', () => {
      const count = getActiveIssueCount(mockIssues)
      expect(count).toBe(3)
    })

    it('returns 0 for empty array', () => {
      const count = getActiveIssueCount([])
      expect(count).toBe(0)
    })
  })

  describe('countBySeverity', () => {
    it('counts active issues by severity level', () => {
      const counts = countBySeverity(mockIssues)
      
      expect(counts.critical).toBe(2) // Issues 1 and 5
      expect(counts.high).toBe(1)     // Issue 2
      expect(counts.medium).toBe(0)   // Issue 3 is inactive
      expect(counts.low).toBe(0)      // Issue 4 is resolved
    })

    it('handles empty array', () => {
      const counts = countBySeverity([])
      
      expect(counts.critical).toBe(0)
      expect(counts.high).toBe(0)
      expect(counts.medium).toBe(0)
      expect(counts.low).toBe(0)
    })
  })
})