"use client"

import React from "react"
import remarkGfm from "remark-gfm"

import { WorkingTimeline } from "./WorkingTimeline"
import { Response } from "@/shared/components/Response"
import { type TimelineStep } from "@/shared/types/trace"
import { type AgentType } from "@/shared/types/chat"

type StreamingOverlayProps = {
  text: string
  timelineSteps: TimelineStep[]
  agentType: AgentType
  reducedMotion?: boolean
  dripDelayMs?: number
}

const agentAccent: Record<AgentType, string> = {
  primary: "from-[hsl(264,100%,92%)]/60 via-transparent to-transparent",
  research: "from-[hsl(204,100%,91%)]/60 via-transparent to-transparent",
  log_analysis: "from-[hsl(32,98%,88%)]/60 via-transparent to-transparent",
  unknown: "from-[hsl(216,20%,90%)]/50 via-transparent to-transparent",
}

export function StreamingOverlay({ text, timelineSteps, agentType, reducedMotion, dripDelayMs }: StreamingOverlayProps) {
  const hasTimeline = Array.isArray(timelineSteps) && timelineSteps.length > 0
  const hasText = Boolean(text && text.trim().length > 0)

  if (!hasTimeline && !hasText) {
    return null
  }

  const gradientClass = agentAccent[agentType] ?? agentAccent.unknown

  return (
    <section
      aria-live="polite"
      role="status"
      className={`relative isolate mb-10 overflow-hidden rounded-3xl border border-border/40 bg-[hsl(var(--brand-surface)/0.85)] px-6 py-7 shadow-lg backdrop-blur-lg transition-colors duration-300`}
    >
      <div className={`pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b ${gradientClass}`} />

      {hasTimeline && (
        <div className="mb-4">
          <WorkingTimeline steps={timelineSteps} variant="live" />
        </div>
      )}

      {hasText && (
        <Response
          className="prose-base max-w-none text-foreground/95"
          remarkPlugins={[remarkGfm]}
          parseIncompleteMarkdown
          reduceMotion={reducedMotion}
          dripDelayMs={dripDelayMs}
        >
          {text}
        </Response>
      )}
    </section>
  )
}

export default React.memo(StreamingOverlay)
