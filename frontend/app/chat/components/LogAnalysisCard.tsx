"use client"

import React, { useState } from 'react'

type LogAnalysisData = {
  overall_summary?: string
  health_status?: string
  priority_concerns?: string[]
  identified_issues?: Array<{ title?: string; impact?: string; details?: string } | any>
  proposed_solutions?: Array<{ title?: string; steps?: string[]; summary?: string } | any>
}

export function LogAnalysisCard({ data }: { data?: LogAnalysisData }) {
  const [open, setOpen] = useState(true)
  if (!data) return null
  return (
    <div className="mt-3 border rounded p-3 bg-muted/30">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Log Analysis</div>
        <button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setOpen(v => !v)}>
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
                {data.priority_concerns.slice(0, 5).map((c, idx) => (
                  <li key={idx}>{String(c)}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(data.identified_issues) && data.identified_issues.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">Identified Issues</div>
              <ul className="list-disc ml-5 text-sm">
                {data.identified_issues.map((i: any, idx: number) => (
                  <li key={idx}>{i?.title || i?.summary || (typeof i === 'string' ? i : 'Issue')}</li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(data.proposed_solutions) && data.proposed_solutions.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">Proposed Solutions</div>
              <ul className="list-disc ml-5 text-sm">
                {data.proposed_solutions.map((s: any, idx: number) => (
                  <li key={idx}>{s?.title || s?.summary || (typeof s === 'string' ? s : 'Solution')}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

