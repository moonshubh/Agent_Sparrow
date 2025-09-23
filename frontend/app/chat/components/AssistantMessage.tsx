"use client"

import React from 'react'
import { Bot } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function AssistantMessage({ content }: { content: string }) {
  return (
    <div className="relative rounded-lg border border-border/60 bg-gradient-to-br from-background to-muted/30 p-3">
      <div className="absolute -top-3 left-3 bg-background px-2 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
        <Bot className="w-3 h-3 text-mb-blue-500" /> Assistant
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
  )
}
