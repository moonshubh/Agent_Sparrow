"use client"

import React, { useMemo, useState } from 'react'
import { Brain, ChevronDown, ChevronUp } from 'lucide-react'

type ThinkingStep = {
  phase: string
  thought: string
  confidence: number
}

type ThinkingTrace = {
  confidence?: number
  thinking_steps?: ThinkingStep[]
  tool_decision?: string
  tool_confidence?: string
}

export function ThinkingTracePanel({ trace }: { trace?: ThinkingTrace }) {
  const [open, setOpen] = useState(false)
  // Compute derived values first to keep hooks order stable across renders
  const pct = Math.round(((trace?.confidence ?? 0)) * 100)
  const confidenceClass = useMemo(() => {
    if (pct >= 85) return 'bg-green-500/15 text-green-600 border-green-400/30'
    if (pct >= 60) return 'bg-yellow-500/15 text-yellow-600 border-yellow-400/30'
    return 'bg-orange-500/15 text-orange-600 border-orange-400/30'
  }, [pct])

  if (!trace) return null

  return (
    <div className="mt-3 border rounded-lg p-3 bg-gradient-to-br from-muted/30 to-background">
      <button
        className="w-full flex items-center justify-between text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2">
          <Brain className="w-3.5 h-3.5 text-mb-blue-500" />
          <span>Show Reasoning</span>
          <span className={`ml-2 px-2 py-0.5 rounded-full border text-[10px] ${confidenceClass}`}>{pct}% confidence</span>
        </span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <div className="mt-3 space-y-2 animate-in fade-in-0">
          {(trace.thinking_steps || []).map((s, idx) => (
            <div key={idx} className="text-xs pl-3 border-l-2 border-border/60">
              <div className="font-medium text-foreground/90">{s.phase}</div>
              <div className="text-muted-foreground leading-relaxed">{s.thought}</div>
            </div>
          ))}
          {trace.tool_decision && (
            <div className="text-[11px] text-muted-foreground">Tool decision: {trace.tool_decision}{trace.tool_confidence ? ` (${trace.tool_confidence})` : ''}</div>
          )}
        </div>
      )}
    </div>
  )
}
