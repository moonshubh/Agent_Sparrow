'use client'

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Sparkles } from 'lucide-react'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { ReasoningTrace, type ReasoningData, type ReasoningStep } from './ReasoningTrace'

interface ThinkingTraceStep {
  phase?: string
  thought?: string
  confidence?: number | string
  [key: string]: unknown
}

interface ThinkingTracePrefaceStructured {
  thinking_trace?: ThinkingTracePayload | null
  [key: string]: unknown
}

interface ThinkingTracePreface {
  latest_thought?: string
  structured?: ThinkingTracePrefaceStructured
  [key: string]: unknown
}

interface ThinkingTracePayload {
  thinking_steps?: ThinkingTraceStep[]
  confidence?: number
  tool_confidence?: string | number
  tool_decision?: string
  tool_reasoning?: string
  knowledge_gaps?: unknown[]
  emotional_state?: string
  problem_category?: string
  complexity?: number
  critique_score?: number
  passed_critique?: boolean
  preface?: ThinkingTracePreface
  latest_thought?: string
  [key: string]: unknown
}

type ThinkingTrace = ThinkingTracePayload | null | undefined

function normalizeConfidenceLabel(value: unknown): string | undefined {
  if (value == null) return undefined
  if (typeof value === 'string') return value.toUpperCase()
  if (typeof value === 'number') {
    if (value >= 0.75) return 'HIGH'
    if (value >= 0.45) return 'MEDIUM'
    return 'LOW'
  }
  return undefined
}

function toReasoningSteps(trace: ThinkingTrace): ReasoningStep[] {
  if (!trace) return []
  const rawSteps = Array.isArray(trace?.thinking_steps) ? (trace?.thinking_steps as ThinkingTraceStep[]) : []
  return rawSteps
    .map((step) => ({
      phase: typeof step?.phase === 'string' ? step.phase : 'Step',
      thought: typeof step?.thought === 'string' ? step.thought : '',
      confidence:
        typeof step?.confidence === 'number'
          ? Math.max(0, Math.min(1, step.confidence))
          : typeof step?.confidence === 'string'
            ? parseFloat(step.confidence) || 0
            : 0,
    }))
    .filter((step) => step.thought.trim().length > 0)
}

function toReasoningData(trace: ThinkingTrace): ReasoningData | null {
  if (!trace || typeof trace !== 'object') return null

  const steps = toReasoningSteps(trace)
  const confidenceScore =
    typeof trace.confidence === 'number'
      ? Math.max(0, Math.min(1, trace.confidence))
      : undefined

  const toolConfidenceLabel = normalizeConfidenceLabel(trace.tool_confidence)

  const reasoning: ReasoningData = {
    confidence_score: confidenceScore,
    thinking_steps: steps.length > 0 ? steps : undefined,
    query_analysis:
      trace.emotional_state || trace.problem_category || trace.complexity
        ? {
            emotional_state:
              typeof trace.emotional_state === 'string' ? trace.emotional_state : undefined,
            problem_category:
              typeof trace.problem_category === 'string' ? trace.problem_category : undefined,
            technical_complexity:
              typeof trace.complexity === 'number' ? Math.max(0, Math.min(1, trace.complexity)) : undefined,
          }
        : undefined,
    tool_reasoning:
      trace.tool_decision || trace.tool_confidence || trace.knowledge_gaps
        ? {
            decision_type:
              typeof trace.tool_decision === 'string' ? trace.tool_decision : undefined,
            confidence: toolConfidenceLabel,
            reasoning:
              typeof trace.tool_reasoning === 'string' ? trace.tool_reasoning : undefined,
            recommended_tools: Array.isArray(trace.knowledge_gaps)
              ? trace.knowledge_gaps.filter((gap): gap is string => typeof gap === 'string')
              : undefined,
          }
        : undefined,
    quality_assessment:
      trace.critique_score != null || trace.passed_critique != null
        ? {
            accuracy_confidence:
              typeof trace.critique_score === 'number'
                ? Math.max(0, Math.min(1, trace.critique_score))
                : undefined,
            improvement_suggestions:
              trace.passed_critique === false
                ? ['Model self-critique flagged potential issues']
                : undefined,
          }
        : undefined,
  }

  return reasoning
}

export interface ReasoningPanelProps {
  trace: ThinkingTrace
  latestThought?: string | null
  isStreaming?: boolean
}

export function ReasoningPanel({ trace, latestThought, isStreaming = false }: ReasoningPanelProps) {
  const [collapsed, setCollapsed] = useState(true)

  const reasoningData = useMemo(() => toReasoningData(trace), [trace])
  const previewText = useMemo(() => {
    if (typeof latestThought === 'string' && latestThought.trim().length > 0) {
      return latestThought.trim()
    }
    const steps = Array.isArray(trace?.thinking_steps) ? (trace?.thinking_steps as ThinkingTraceStep[]) : []
    for (let idx = steps.length - 1; idx >= 0; idx -= 1) {
      const candidate = steps[idx]
      if (candidate && typeof candidate.thought === 'string') {
        const trimmed = candidate.thought.trim()
        if (trimmed.length > 0) {
          return trimmed
        }
      }
    }
    return undefined
  }, [latestThought, trace])

  if (!trace || (!reasoningData && !previewText)) return null

  return (
    <div className="pl-10 text-sm text-muted-foreground">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 py-1 text-xs font-medium"
          onClick={() => setCollapsed((prev) => !prev)}
          aria-expanded={!collapsed}
        >
          {collapsed ? (
            <ChevronRight className="mr-1 h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="mr-1 h-3.5 w-3.5" />
          )}
          {collapsed ? 'Show reasoning' : 'Hide reasoning'}
        </Button>
        {isStreaming && (
          <Badge variant="secondary" className="flex items-center gap-1 text-[11px]">
            <Sparkles className="h-3 w-3 animate-pulse" />
            Thinking
          </Badge>
        )}
      </div>
      {previewText && (
        <p className="mt-1 pl-1 text-xs italic text-muted-foreground/80 line-clamp-2">
          {previewText}
        </p>
      )}
      {!collapsed && reasoningData && (
        <div className="mt-3">
          <ReasoningTrace reasoning={reasoningData} />
        </div>
      )}
    </div>
  )
}
