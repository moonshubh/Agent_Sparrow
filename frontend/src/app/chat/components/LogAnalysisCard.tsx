"use client"

import React, { useState } from 'react'

type LogIssue =
  | string
  | {
      title?: string
      impact?: string
      details?: string
      summary?: string
    }

type LogSolution =
  | string
  | {
      title?: string
      steps?: string[]
      summary?: string
    }

type LogAnalysisData = {
  overall_summary?: string
  health_status?: string
  priority_concerns?: string[]
  identified_issues?: LogIssue[]
  proposed_solutions?: LogSolution[]
}

const describeIssue = (issue: LogIssue): string => {
  if (typeof issue === 'string') return issue
  return (
    issue.title || issue.summary || issue.details || issue.impact || 'Issue'
  )
}

const describeSolution = (solution: LogSolution): string => {
  if (typeof solution === 'string') return solution
  return solution.title || solution.summary || 'Solution'
}

export function LogAnalysisCard({ data }: { data?: LogAnalysisData }) {
  const [open, setOpen] = useState(true)
  if (!data) return null
  return (
    <div className="mt-3 border rounded p-3 bg-muted/30">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Log Analysis</div>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setOpen((value) => !value)}
          type="button"
        >
          {open ? 'Hide' : 'Show'}
        </button>
      </div>
      {open && (
        <div className="mt-2 space-y-3">
          {data.health_status && (
            <div className="text-xs">
              <span className="text-muted-foreground">Health:</span> {data.health_status}
            </div>
          )}
          {data.overall_summary && (
            <div className="text-sm whitespace-pre-wrap">{data.overall_summary}</div>
          )}
          {Array.isArray(data.priority_concerns) && data.priority_concerns.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">Priority Concerns</div>
              <ul className="list-disc ml-5 text-sm">
                {data.priority_concerns.slice(0, 5).map((concern, idx) => (
                  <li key={`priority-${idx}`}>{String(concern)}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(data.identified_issues) && data.identified_issues.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">Identified Issues</div>
              <ul className="list-disc ml-5 text-sm">
                {data.identified_issues.map((issue, idx) => (
                  <li key={`issue-${idx}`}>{describeIssue(issue)}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(data.proposed_solutions) && data.proposed_solutions.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">Proposed Solutions</div>
              <ul className="list-disc ml-5 text-sm">
                {data.proposed_solutions.map((solution, idx) => (
                  <li key={`solution-${idx}`}>{describeSolution(solution)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
