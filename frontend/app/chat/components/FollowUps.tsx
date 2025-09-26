"use client"

import React from 'react'
import { Sparkles, MessageSquare } from 'lucide-react'

export function FollowUps({
  questions,
  onClick,
  disabled,
}: {
  questions?: string[]
  onClick: (q: string) => void
  disabled?: boolean
}) {
  if (!questions || questions.length === 0) return null
  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Sparkles className="w-3.5 h-3.5 text-yellow-500" />
        Suggested follow-ups
      </div>
      <div className="flex flex-wrap gap-2">
        {questions.map((q) => (
          <button
            key={q}
            className="group text-xs px-3 py-1.5 rounded-full border border-border/60 bg-gradient-to-br from-background to-muted/40 hover:from-mb-blue-500/10 hover:to-mb-blue-500/20 hover:border-mb-blue-400/50 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            onClick={() => onClick(q)}
            disabled={disabled}
            title={q}
          >
            <MessageSquare className="w-3.5 h-3.5 text-mb-blue-500 group-hover:text-mb-blue-400" />
            <span className="line-clamp-1">{q}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
