"use client"

import React, { useState } from 'react'

type KbItem = {
  example_id?: string | number
  question?: string
  answer?: string
  confidence?: number
  conversation_title?: string
}

type KbResultsPayload = {
  results?: KbItem[]
  total_results?: number
}

export function KbResults({ data }: { data?: KbResultsPayload }) {
  const [expanded, setExpanded] = useState(false)
  const results = data?.results ?? []

  if (results.length === 0) return null

  const items = expanded ? results : results.slice(0, 3)

  return (
    <div className="mt-3 border rounded p-3 bg-muted/30">
      <div className="text-xs text-muted-foreground mb-2">
        Knowledge results {typeof data?.total_results === 'number' ? `(${data.total_results})` : ''}
      </div>
      <div className="space-y-3">
        {items.map((item, idx) => {
          const itemKey = item.example_id !== undefined ? String(item.example_id) : String(idx)
          const question = item.question || item.conversation_title || 'Result'
          const answerPreview = item.answer
            ? item.answer.length > 400
              ? `${item.answer.slice(0, 400)}…`
              : item.answer
            : null

          return (
            <div key={itemKey} className="text-sm">
              <div className="font-medium">{question}</div>
              {typeof item.confidence === 'number' && (
                <div className="text-xs text-muted-foreground">
                  Confidence: {Math.round(item.confidence * 100)}%
                </div>
              )}
              {answerPreview && (
                <div className="mt-1 text-foreground/90 whitespace-pre-wrap">{answerPreview}</div>
              )}
            </div>
          )
        })}
      </div>
      {results.length > 3 && (
        <button
          className="mt-2 text-xs underline text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? 'Show less' : `Show ${results.length - 3} more`}
        </button>
      )}
    </div>
  )
}
