"use client"

import React, { useState } from 'react'

type KbItem = {
  example_id?: string | number
  question?: string
  answer?: string
  confidence?: number
  conversation_title?: string
}

export function KbResults({ data }: { data?: { results?: KbItem[]; total_results?: number } }) {
  const [expanded, setExpanded] = useState(false)
  if (!data || !data.results || data.results.length === 0) return null
  const items = expanded ? data.results : data.results.slice(0, 3)
  return (
    <div className="mt-3 border rounded p-3 bg-muted/30">
      <div className="text-xs text-muted-foreground mb-2">
        Knowledge results {typeof data.total_results === 'number' ? `(${data.total_results})` : ''}
      </div>
      <div className="space-y-3">
        {items.map((r, idx) => (
          <div key={(r.example_id as any) ?? idx} className="text-sm">
            <div className="font-medium">{r.question || r.conversation_title || 'Result'}</div>
            {typeof r.confidence === 'number' && (
              <div className="text-xs text-muted-foreground">Confidence: {Math.round(r.confidence * 100)}%</div>
            )}
            {r.answer && (
              <div className="mt-1 text-foreground/90 whitespace-pre-wrap">
                {r.answer.length > 400 ? r.answer.slice(0, 400) + '…' : r.answer}
              </div>
            )}
          </div>
        ))}
      </div>
      {data.results.length > 3 && (
        <button
          className="mt-2 text-xs underline text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Show less' : `Show ${data.results.length - 3} more`}
        </button>
      )}
    </div>
  )
}

