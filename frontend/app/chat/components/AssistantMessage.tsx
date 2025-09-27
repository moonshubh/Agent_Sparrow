"use client"

import React from 'react'
import { Bot, FileText } from 'lucide-react'
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
  return (
    <div className="space-y-3">
      {/* Log Overview Card - displayed before the main message */}
      {(isLogAnalysis || logMetadata || errorSnippets || rootCause) && (
        <LogOverviewCard
          metadata={logMetadata}
          errorSnippets={errorSnippets}
          rootCause={rootCause}
        />
      )}

      {/* Main Assistant Message */}
      <div className="relative rounded-lg border border-border/60 bg-gradient-to-br from-background to-muted/30 p-3">
        <div className="absolute -top-3 left-3 bg-background px-2 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
          {isLogAnalysis ? (
            <>
              <FileText className="w-3 h-3 text-orange-500" /> Log Analysis
            </>
          ) : (
            <>
              <Bot className="w-3 h-3 text-mb-blue-500" /> Assistant
            </>
          )}
        </div>
        <div className="mt-1 text-sm text-foreground/90 prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}
          components={{
            code({ className, children, ...props }) {
              const text = String(children)
              // Check if this is an inline code block based on the presence of a parent
              const match = /language-(\w+)/.exec(className || '')
              const isCodeBlock = match !== null

              if (!isCodeBlock && !className) {
                return (
                  <code className={`px-1.5 py-0.5 rounded bg-muted text-[0.9em]`} {...props}>
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
                <a href={href} className="text-mb-blue-500 hover:text-mb-blue-400 underline" target="_blank" rel="noreferrer" {...props}>
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
    </div>
  )
}
