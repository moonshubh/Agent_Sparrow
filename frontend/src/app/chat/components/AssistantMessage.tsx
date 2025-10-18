"use client"

import React from 'react'
import remarkGfm from 'remark-gfm'
import { LogOverviewCard, type LogMetadata, type ErrorSnippet } from './LogOverviewCard'
import { type ChatMessageMetadata } from '@/shared/types/chat'
import { Button } from '@/shared/ui/button'
import { Badge } from '@/shared/ui/badge'
import { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from '@/shared/ui/tooltip'
import { useToast } from '@/shared/ui/use-toast'
import { Copy, Check, Sparkles, Layers, ClipboardList } from 'lucide-react'
import { Response } from '@/shared/components/Response'

interface AssistantMessageProps {
  content: string
  metadata?: ChatMessageMetadata
  isLogAnalysis?: boolean
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const toNumber = (value: unknown): number | undefined =>
  typeof value === 'number' ? value : undefined

const toLogMetadata = (value: unknown): LogMetadata | undefined =>
  (isRecord(value) ? (value as LogMetadata) : undefined)

const toErrorSnippets = (value: unknown): ErrorSnippet[] | undefined => {
  if (!Array.isArray(value)) return undefined
  const snippets: ErrorSnippet[] = []
  for (const item of value) {
    if (typeof item === 'string') {
      snippets.push({ message: item })
      continue
    }
    if (!isRecord(item)) continue
    snippets.push({
      timestamp: typeof item.timestamp === 'string' ? item.timestamp : undefined,
      level:
        typeof item.level === 'string'
          ? (item.level as ErrorSnippet['level'])
          : undefined,
      message: typeof item.message === 'string' ? item.message : undefined,
      stackTrace: typeof item.stackTrace === 'string' ? item.stackTrace : undefined,
      context: typeof item.context === 'string' ? item.context : undefined,
      lineNumber: toNumber(item.lineNumber),
    })
  }
  return snippets.length > 0 ? snippets : undefined
}

const toRootCause = (
  value: unknown,
): { summary?: string; confidence?: number; category?: string } | undefined => {
  if (!isRecord(value)) return undefined
  return {
    summary: typeof value.summary === 'string' ? value.summary : undefined,
    confidence: toNumber(value.confidence),
    category: typeof value.category === 'string' ? value.category : undefined,
  }
}

type ConfidenceLabel = 'high' | 'medium' | 'low'

type StructuredEvidenceRef = {
  source_file?: string
  line_start?: number | null
  line_end?: number | null
  signature_id?: string
}

type StructuredFinding = {
  severity: ConfidenceLabel
  title: string
  details: string
  signature_id?: string
  occurrences?: number | null
  evidence_refs?: StructuredEvidenceRef[]
}

type StructuredQuickAction = {
  label: string
  action_id: string
  kind?: string
  notes?: string | null
}

type StructuredFixStep = {
  step: string
  notes?: string | null
}

type StructuredOverview = {
  time_range?: string | null
  files?: string[]
  app_version?: string | null
  db_size?: string | null
  accounts_count?: number | null
  platform?: string | null
  confidence: ConfidenceLabel
  confidence_reason?: string | null
}

type StructuredMeta = {
  analysis_duration_ms?: number | null
  engine_version?: string | null
  coverage?: {
    lines_total?: number | null
    errors_grouped?: number | null
  }
}

type LogStructuredOutput = {
  overview: StructuredOverview
  findings: StructuredFinding[]
  quick_actions: StructuredQuickAction[]
  full_fix_steps: StructuredFixStep[]
  checks: string[]
  tips: string[]
  redactions_applied: string[]
  meta: StructuredMeta
}

const toConfidenceLabel = (value: unknown, fallback: ConfidenceLabel = 'medium'): ConfidenceLabel => {
  if (typeof value !== 'string') return fallback
  const normalized = value.toLowerCase() as ConfidenceLabel
  return normalized === 'high' || normalized === 'medium' || normalized === 'low' ? normalized : fallback
}

const toStructuredOutput = (value: unknown): LogStructuredOutput | undefined => {
  if (!isRecord(value)) return undefined

  const overviewRaw = isRecord(value.overview) ? value.overview : {}
  const overview: StructuredOverview = {
    time_range: typeof overviewRaw.time_range === 'string' ? overviewRaw.time_range : null,
    files: Array.isArray(overviewRaw.files)
      ? overviewRaw.files.filter((item): item is string => typeof item === 'string')
      : [],
    app_version: typeof overviewRaw.app_version === 'string' ? overviewRaw.app_version : null,
    db_size: typeof overviewRaw.db_size === 'string' ? overviewRaw.db_size : null,
    accounts_count: typeof overviewRaw.accounts_count === 'number' ? overviewRaw.accounts_count : null,
    platform: typeof overviewRaw.platform === 'string' ? overviewRaw.platform : null,
    confidence: toConfidenceLabel(overviewRaw.confidence),
    confidence_reason: typeof overviewRaw.confidence_reason === 'string' ? overviewRaw.confidence_reason : null,
  }

  const findings: StructuredFinding[] = Array.isArray(value.findings)
    ? value.findings
        .filter(isRecord)
        .map(item => {
          const severity = toConfidenceLabel(item.severity, 'medium')
          const evidenceRefs: StructuredEvidenceRef[] | undefined = Array.isArray(item.evidence_refs)
            ? item.evidence_refs.filter(isRecord).map(ref => ({
                source_file: typeof ref.source_file === 'string' ? ref.source_file : undefined,
                line_start: typeof ref.line_start === 'number' ? ref.line_start : null,
                line_end: typeof ref.line_end === 'number' ? ref.line_end : null,
                signature_id: typeof ref.signature_id === 'string' ? ref.signature_id : undefined,
              }))
            : undefined
          return {
            severity,
            title: typeof item.title === 'string' ? item.title : 'Finding',
            details: typeof item.details === 'string' ? item.details : '',
            signature_id: typeof item.signature?.message_fingerprint === 'string'
              ? item.signature.message_fingerprint
              : typeof item.signature_id === 'string'
                ? item.signature_id
                : undefined,
            occurrences: typeof item.occurrences === 'number' ? item.occurrences : null,
            evidence_refs: evidenceRefs,
          }
        })
    : []

  const quickActions: StructuredQuickAction[] = Array.isArray(value.quick_actions)
    ? value.quick_actions.filter(isRecord).map(action => ({
        label: typeof action.label === 'string' ? action.label : 'Action',
        action_id: typeof action.action_id === 'string' ? action.action_id : 'action',
        kind: typeof action.kind === 'string' ? action.kind : undefined,
        notes: typeof action.notes === 'string' ? action.notes : null,
      }))
    : []

  const fixSteps: StructuredFixStep[] = Array.isArray(value.full_fix_steps)
    ? value.full_fix_steps.filter(isRecord).map(step => ({
        step: typeof step.step === 'string' ? step.step : '',
        notes: typeof step.notes === 'string' ? step.notes : null,
      }))
    : []

  const checks: string[] = Array.isArray(value.checks)
    ? value.checks.filter((item): item is string => typeof item === 'string')
    : []

  const tips: string[] = Array.isArray(value.tips)
    ? value.tips.filter((item): item is string => typeof item === 'string')
    : []

  const redactions: string[] = Array.isArray(value.redactions_applied)
    ? value.redactions_applied.filter((item): item is string => typeof item === 'string')
    : []

  const metaRaw = isRecord(value.meta) ? value.meta : {}
  const meta: StructuredMeta = {
    analysis_duration_ms: typeof metaRaw.analysis_duration_ms === 'number' ? metaRaw.analysis_duration_ms : null,
    engine_version: typeof metaRaw.engine_version === 'string' ? metaRaw.engine_version : null,
    coverage: isRecord(metaRaw.coverage)
      ? {
          lines_total: typeof metaRaw.coverage.lines_total === 'number' ? metaRaw.coverage.lines_total : null,
          errors_grouped: typeof metaRaw.coverage.errors_grouped === 'number' ? metaRaw.coverage.errors_grouped : null,
        }
      : undefined,
  }

  return {
    overview,
    findings,
    quick_actions: quickActions,
    full_fix_steps: fixSteps,
    checks,
    tips,
    redactions_applied: redactions,
    meta,
  }
}

const severityClasses: Record<ConfidenceLabel, string> = {
  high: 'bg-red-500/15 text-red-500 border border-red-500/20',
  medium: 'bg-amber-500/15 text-amber-500 border border-amber-500/20',
  low: 'bg-blue-500/15 text-blue-500 border border-blue-500/20',
}

const severityLabel: Record<ConfidenceLabel, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

const confidenceToScore = (confidence?: ConfidenceLabel): number | undefined => {
  switch (confidence) {
    case 'high':
      return 0.9
    case 'medium':
      return 0.6
    case 'low':
      return 0.35
    default:
      return undefined
  }
}

const formatEvidence = (ref: StructuredEvidenceRef): string => {
  const range = ref.line_start !== null && ref.line_start !== undefined
    ? `L${ref.line_start}${ref.line_end && ref.line_end !== ref.line_start ? `-${ref.line_end}` : ''}`
    : undefined
  return [ref.source_file, range].filter(Boolean).join(' ')
}

const buildSummaryCopy = (structured: LogStructuredOutput): string => {
  const lines: string[] = []
  const overview = structured.overview
  lines.push(`Scope: ${overview.time_range ?? 'N/A'} | Files: ${(overview.files ?? []).join(', ') || 'N/A'}`)
  lines.push(
    `Environment: ${[
      overview.app_version ? `Mailbird ${overview.app_version}` : null,
      overview.platform,
      overview.db_size,
    ]
      .filter(Boolean)
      .join(' • ') || 'Not detected'}`,
  )
  const confidenceText = overview.confidence_reason
    ? `${overview.confidence.toUpperCase()} — ${overview.confidence_reason}`
    : overview.confidence.toUpperCase()
  lines.push(`Confidence: ${confidenceText}`)
  lines.push('')
  lines.push('Findings:')
  structured.findings.slice(0, 5).forEach((finding, index) => {
    lines.push(
      `${index + 1}. [${finding.severity.toUpperCase()}] ${finding.title} — ${finding.details}`,
    )
  })
  return lines.join('\n')
}

const buildStepsCopy = (structured: LogStructuredOutput): string => {
  const lines: string[] = []
  if (structured.quick_actions.length > 0) {
    lines.push('Try this now:')
    structured.quick_actions.forEach((action, index) => {
      lines.push(
        `${index + 1}. ${action.label}${action.notes ? ` — ${action.notes}` : ''}`,
      )
    })
    lines.push('')
  }
  if (structured.full_fix_steps.length > 0) {
    lines.push('Full fix steps:')
    structured.full_fix_steps.forEach((step, index) => {
      lines.push(
        `${index + 1}. ${step.step}${step.notes ? ` — ${step.notes}` : ''}`,
      )
    })
    lines.push('')
  }
  if (structured.checks.length > 0) {
    lines.push('Extra checks:')
    structured.checks.forEach(check => lines.push(`- ${check}`))
    lines.push('')
  }
  if (structured.tips.length > 0) {
    lines.push('Tips:')
    structured.tips.forEach(tip => lines.push(`- ${tip}`))
  }
  return lines.join('\n')
}

export function AssistantMessage({ content, metadata, isLogAnalysis }: AssistantMessageProps) {
  const { toast } = useToast()

  const baseLogMetadata = toLogMetadata(metadata?.logMetadata)
  const errorSnippets = toErrorSnippets(metadata?.errorSnippets)
  const rootCause = toRootCause(metadata?.rootCause)
  const analysisResults = isRecord(metadata?.analysisResults)
    ? metadata.analysisResults
    : undefined
  const structuredOutput = toStructuredOutput(analysisResults?.structured_output)

  const analysisConfidence = analysisResults
    ? toNumber(analysisResults['confidence_level'])
    : undefined

  const mergedLogMetadata = React.useMemo<LogMetadata | undefined>(() => {
    if (!structuredOutput) return baseLogMetadata
    const base: LogMetadata = { ...(baseLogMetadata ?? {}) } as LogMetadata
    if (structuredOutput.overview.app_version) base.version = structuredOutput.overview.app_version || undefined
    if (structuredOutput.overview.platform) base.platform = structuredOutput.overview.platform || undefined
    if (structuredOutput.overview.db_size) base.database_size = structuredOutput.overview.db_size || undefined
    if (structuredOutput.overview.accounts_count !== null && structuredOutput.overview.accounts_count !== undefined) {
      base.account_count = structuredOutput.overview.accounts_count ?? base.account_count
    }
    if (structuredOutput.meta.coverage?.lines_total !== null && structuredOutput.meta.coverage?.lines_total !== undefined) {
      base.total_entries = structuredOutput.meta.coverage.lines_total ?? base.total_entries
    }
    const confidence = confidenceToScore(structuredOutput.overview.confidence)
    if (confidence !== undefined) {
      base.confidence_level = confidence
    }
    return base
  }, [structuredOutput, baseLogMetadata])

  const logMetadata = mergedLogMetadata
  const confidenceLevel = toNumber(logMetadata?.confidence_level) ?? analysisConfidence
  const normalizedConfidence = confidenceLevel !== undefined ? Math.max(0, Math.min(1, confidenceLevel)) : undefined

  const derivedIsLog = React.useMemo(
    () => Boolean(isLogAnalysis || logMetadata || errorSnippets || rootCause || structuredOutput),
    [isLogAnalysis, logMetadata, errorSnippets, rootCause, structuredOutput],
  )

  const sanitizedContent = React.useMemo(() => {
    if (!derivedIsLog) return content
    if (typeof content !== 'string') return content
    const logHeaderPattern = /^```[a-zA-Z0-9_-]*\n(?:(?:#\s*)?System Information[\s\S]*?)```[\r\n]*/i
    return content.replace(logHeaderPattern, '').trimStart()
  }, [content, derivedIsLog])

  const [summaryCopied, setSummaryCopied] = React.useState(false)
  const [stepsCopied, setStepsCopied] = React.useState(false)
  const summaryTimeoutRef = React.useRef<NodeJS.Timeout | null>(null)
  const stepsTimeoutRef = React.useRef<NodeJS.Timeout | null>(null)

  React.useEffect(() => {
    return () => {
      if (summaryTimeoutRef.current) {
        clearTimeout(summaryTimeoutRef.current)
        summaryTimeoutRef.current = null
      }
      if (stepsTimeoutRef.current) {
        clearTimeout(stepsTimeoutRef.current)
        stepsTimeoutRef.current = null
      }
    }
  }, [])

  const copyText = React.useCallback(
    async (text: string, message: string, onSuccess?: () => void) => {
      if (!text) return
      try {
        await navigator.clipboard.writeText(text)
        toast({ description: message })
        onSuccess?.()
      } catch (error) {
        toast({ description: 'Unable to copy to clipboard', variant: 'destructive' })
      }
    },
    [toast],
  )

  return (
    <div className="space-y-4">
      {structuredOutput && (
        <TooltipProvider>
          <div className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  copyText(
                    buildSummaryCopy(structuredOutput),
                    'Summary copied to clipboard',
                    () => {
                      if (summaryTimeoutRef.current) {
                        clearTimeout(summaryTimeoutRef.current)
                      }
                      setSummaryCopied(true)
                      summaryTimeoutRef.current = setTimeout(() => {
                        setSummaryCopied(false)
                        summaryTimeoutRef.current = null
                      }, 2000)
                    },
                  )
                }}
                className="gap-2"
              >
                {summaryCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                Copy summary
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  copyText(
                    buildStepsCopy(structuredOutput),
                    'Steps copied to clipboard',
                    () => {
                      if (stepsTimeoutRef.current) {
                        clearTimeout(stepsTimeoutRef.current)
                      }
                      setStepsCopied(true)
                      stepsTimeoutRef.current = setTimeout(() => {
                        setStepsCopied(false)
                        stepsTimeoutRef.current = null
                      }, 2000)
                    },
                  )
                }}
                className="gap-2"
              >
                {stepsCopied ? <Check className="w-4 h-4" /> : <ClipboardList className="w-4 h-4" />}
                Copy steps
              </Button>
              <div className="ml-auto flex flex-wrap gap-2 text-xs text-muted-foreground">
                {structuredOutput.meta.coverage?.errors_grouped !== null && structuredOutput.meta.coverage?.errors_grouped !== undefined && (
                  <Badge variant="outline">Grouped errors: {structuredOutput.meta.coverage.errors_grouped}</Badge>
                )}
                {structuredOutput.meta.analysis_duration_ms !== null && structuredOutput.meta.analysis_duration_ms !== undefined && (
                  <Badge variant="outline">{structuredOutput.meta.analysis_duration_ms} ms</Badge>
                )}
                {structuredOutput.meta.engine_version && (
                  <Badge variant="outline">Engine: {structuredOutput.meta.engine_version}</Badge>
                )}
              </div>
            </div>

            {structuredOutput.findings.length > 0 && (
              <section className="space-y-2">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Findings</h3>
                  <Badge variant="outline" className="text-xs">
                    {structuredOutput.findings.length}
                  </Badge>
                </div>
                <div className="space-y-2">
                  {structuredOutput.findings.map((finding, index) => (
                    <div
                      key={finding.signature_id ?? `${finding.title}-${index}`}
                      className="rounded-md border border-border/60 bg-background/80 p-3 space-y-2"
                    >
                      <div className="flex items-center gap-2">
                        <Badge className={severityClasses[finding.severity]}>{severityLabel[finding.severity]}</Badge>
                        <span className="text-sm font-medium text-foreground/90">{finding.title}</span>
                        {typeof finding.occurrences === 'number' && (
                          <span className="text-xs text-muted-foreground ml-auto">{finding.occurrences} occurrences</span>
                        )}
                      </div>
                      <div className="text-sm text-foreground/90 leading-relaxed">{finding.details}</div>
                      {finding.evidence_refs && finding.evidence_refs.length > 0 && (
                        <details className="text-xs text-muted-foreground">
                          <summary className="cursor-pointer select-none">View evidence</summary>
                          <ul className="mt-1 space-y-1 font-mono">
                            {finding.evidence_refs.map((ref, refIndex) => (
                              <li key={`${ref.signature_id ?? 'ref'}-${refIndex}`}>{formatEvidence(ref)}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {structuredOutput.quick_actions.length > 0 && (
              <section className="space-y-2">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Try this now</h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {structuredOutput.quick_actions.map(action => (
                    <Tooltip key={action.action_id}>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => copyText(action.label, `Copied "${action.label}"`)}
                        >
                          {action.label}
                        </Button>
                      </TooltipTrigger>
                      {action.notes && <TooltipContent className="max-w-xs text-xs">{action.notes}</TooltipContent>}
                    </Tooltip>
                  ))}
                </div>
              </section>
            )}

            {structuredOutput.full_fix_steps.length > 0 && (
              <section className="space-y-2">
                <div className="flex items-center gap-2">
                  <ClipboardList className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-semibold">Full fix</h3>
                </div>
                <ol className="list-decimal space-y-1 pl-4 text-sm text-foreground/90">
                  {structuredOutput.full_fix_steps.map((step, index) => (
                    <li key={`${step.step}-${index}`}>
                      {step.step}
                      {step.notes && <span className="block text-xs text-muted-foreground">{step.notes}</span>}
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {structuredOutput.checks.length > 0 && (
              <section className="space-y-1">
                <h3 className="text-sm font-semibold">Extra checks</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {structuredOutput.checks.map((check, index) => (
                    <li key={`${check}-${index}`}>{check}</li>
                  ))}
                </ul>
              </section>
            )}

            {structuredOutput.tips.length > 0 && (
              <section className="space-y-1">
                <h3 className="text-sm font-semibold">Tips</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {structuredOutput.tips.map((tip, index) => (
                    <li key={`${tip}-${index}`}>{tip}</li>
                  ))}
                </ul>
              </section>
            )}

            {structuredOutput.redactions_applied.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>Redactions:</span>
                {structuredOutput.redactions_applied.map((label, index) => (
                  <Badge key={`${label}-${index}`} variant="outline" className="uppercase tracking-wide">
                    {label}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </TooltipProvider>
      )}

      {derivedIsLog && (
        <LogOverviewCard
          metadata={logMetadata}
          errorSnippets={errorSnippets}
          rootCause={rootCause}
          confidence={normalizedConfidence ?? confidenceToScore(structuredOutput?.overview.confidence)}
        />
      )}

      <Response
        className="mt-1 text-base leading-relaxed text-foreground"
        remarkPlugins={[remarkGfm]}
        parseIncompleteMarkdown
        reduceMotion={false}
      >
        {sanitizedContent}
      </Response>
    </div>
  )
}
