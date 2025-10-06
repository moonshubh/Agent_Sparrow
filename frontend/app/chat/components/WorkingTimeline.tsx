"use client"

import React, { useMemo, useState } from 'react'
import { CheckCircle2, Circle, ChevronDown, ChevronRight, AlertTriangle, Loader2 } from 'lucide-react'
import { TimelineStep } from '@/types/trace'

type WorkingTimelineProps = {
  steps: TimelineStep[]
  variant: 'live' | 'final'
}

const statusIcon = (status: TimelineStep['status']) => {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground" />
    case 'failed':
      return <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
    case 'in_progress':
      return <Loader2 className="w-3.5 h-3.5 animate-spin text-mb-blue-500" />
    default:
      return <Circle className="w-3.5 h-3.5 text-muted-foreground" />
  }
}

const DetailBlock = ({ step }: { step: TimelineStep }) => {
  const toolJson = useMemo(() => {
    if (!step.details?.toolIO) return null
    try {
      return JSON.stringify(step.details.toolIO, null, 2)
    } catch {
      return String(step.details.toolIO)
    }
  }, [step.details?.toolIO])

  return (
    <div className="mt-2 space-y-2 text-xs text-muted-foreground">
      {step.details?.text && (
        <div className="whitespace-pre-wrap leading-relaxed">{step.details.text}</div>
      )}
      {toolJson && (
        <pre className="max-h-56 overflow-auto rounded border border-border/50 bg-muted/40 p-2 whitespace-pre-wrap break-words">{toolJson}</pre>
      )}
    </div>
  )
}

const StepRow = ({ step, isLast }: { step: TimelineStep; isLast: boolean }) => {
  const [open, setOpen] = useState(false)
  const canExpand = Boolean(step.details?.text || step.details?.toolIO)

  return (
    <div className="relative pl-5">
      <div
        className={`absolute left-1 top-2 w-px ${isLast ? 'h-2' : 'h-full'} bg-border/50`}
        aria-hidden
      />
      <button
        type="button"
        onClick={() => canExpand && setOpen(v => !v)}
        className={`flex w-full items-center gap-2 py-1 text-sm text-foreground/90 ${canExpand ? 'hover:text-foreground transition-colors' : 'cursor-default'}`}
      >
        {canExpand ? (
          open ? <ChevronDown className="w-3 h-3 text-muted-foreground" /> : <ChevronRight className="w-3 h-3 text-muted-foreground" />
        ) : (
          <span className="w-3" />
        )}
        {statusIcon(step.status)}
        <span className="truncate text-left">{step.title}</span>
      </button>
      {open && canExpand && <DetailBlock step={step} />}
    </div>
  )
}

export function WorkingTimeline({ steps, variant }: WorkingTimelineProps) {
  if (!steps || steps.length === 0) return null

  // Hide the synthetic "Answer" step from the visible timeline
  const visibleSteps = steps.filter(s => s.title.trim().toLowerCase() !== 'answer')
  if (visibleSteps.length === 0) return null

  // TODO(UX-1762): Introduce variant-specific spacing once live/progress themes diverge.
  void variant

  return (
    <div className="px-1 py-0.5">
      <div className="space-y-1">
        {visibleSteps.map((step, idx) => (
          <StepRow key={step.id} step={step} isLast={idx === visibleSteps.length - 1} />
        ))}
      </div>
    </div>
  )
}

export default WorkingTimeline
