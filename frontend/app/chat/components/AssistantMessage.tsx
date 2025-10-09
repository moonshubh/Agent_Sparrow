"use client"

import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { LogOverviewCard, type LogMetadata, type ErrorSnippet } from './LogOverviewCard'

interface AssistantMessageProps {
  content: string
  metadata?: any
  isLogAnalysis?: boolean
}

export function AssistantMessage({ content, metadata, isLogAnalysis }: AssistantMessageProps) {
  // Extract log-specific metadata if present
  const logMetadata: LogMetadata | undefined = metadata?.logMetadata
  const errorSnippets: ErrorSnippet[] | undefined = metadata?.errorSnippets
  const rootCause = metadata?.rootCause
  const confidenceLevel = typeof logMetadata?.confidence_level === 'number'
    ? Math.max(0, Math.min(1, logMetadata.confidence_level))
    : typeof metadata?.analysisResults?.confidence_level === 'number'
      ? Math.max(0, Math.min(1, metadata.analysisResults.confidence_level))
      : undefined
  const derivedIsLog = Boolean(isLogAnalysis || logMetadata || errorSnippets || rootCause)
  return (
    <div className="space-y-3">
      {/* Log Overview Card - displayed before the main message */}
      {derivedIsLog && (
        <LogOverviewCard
          metadata={logMetadata}
          errorSnippets={errorSnippets}
          rootCause={rootCause}
          confidence={confidenceLevel}
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
              }
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
