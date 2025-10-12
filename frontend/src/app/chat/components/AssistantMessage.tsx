"use client"

import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { LogOverviewCard, type LogMetadata, type ErrorSnippet } from './LogOverviewCard'
import { type ChatMessageMetadata } from '@/shared/types/chat'

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

export function AssistantMessage({ content, metadata, isLogAnalysis }: AssistantMessageProps) {
  const logMetadata = toLogMetadata(metadata?.logMetadata)
  const errorSnippets = toErrorSnippets(metadata?.errorSnippets)
  const rootCause = toRootCause(metadata?.rootCause)
  const analysisResults = isRecord(metadata?.analysisResults)
    ? metadata?.analysisResults
    : undefined
  const analysisConfidence = analysisResults
    ? toNumber(analysisResults['confidence_level'])
    : undefined
  const confidenceLevel = toNumber(logMetadata?.confidence_level) ?? analysisConfidence
  const normalizedConfidence = (
    confidenceLevel !== undefined ? Math.max(0, Math.min(1, confidenceLevel)) : undefined
  )
  const derivedIsLog = Boolean(isLogAnalysis || logMetadata || errorSnippets || rootCause)

  return (
    <div className="space-y-3">
      {/* Log Overview Card - displayed before the main message */}
      {derivedIsLog && (
        <LogOverviewCard
          metadata={logMetadata}
          errorSnippets={errorSnippets}
          rootCause={rootCause}
          confidence={normalizedConfidence}
        />
      )}

      {/* Main Assistant Message */}
      <div className="relative rounded-lg border border-border/60 p-3 bg-[hsl(var(--brand-surface))]">
        <div className="mt-1 text-sm text-foreground/90 prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const text = String(children)
                const match = /language-(\w+)/.exec(className || '')
                const isCodeBlock = match !== null

                if (!isCodeBlock && !className) {
                  return (
                    <code className="px-1.5 py-0.5 rounded bg-muted text-[0.9em]" {...props}>
                      {text}
                    </code>
                  )
                }
                return (
                  <pre className="rounded border border-border/60 bg-muted p-3 overflow-x-auto">
                    <code className={className} {...props}>{text}</code>
                  </pre>
                )
              },
              a({ children, href, ...props }) {
                return (
                  <a
                    href={href}
                    className="text-mb-blue-500 hover:text-mb-blue-400 underline"
                    target="_blank"
                    rel="noreferrer noopener"
                    {...props}
                  >
                    {children}
                  </a>
                )
              },
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
      {/* No extra pills or badges under the message */}
    </div>
  )
}
