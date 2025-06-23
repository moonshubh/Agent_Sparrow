"use client"

import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ExecutiveSummaryProps {
  content: string
  className?: string
}

export function ExecutiveSummary({ content, className }: ExecutiveSummaryProps) {
  // Check for empty or whitespace-only content
  const trimmedContent = content?.trim() || ''
  if (trimmedContent.length === 0) {
    return null
  }

  return (
    <section id="executive-summary" data-testid="executive-summary" className={cn("w-full", className)}>
      <Card className="bg-muted dark:bg-neutral-800/60 backdrop-blur">
        {/* Sticky Header */}
        <div className="sticky top-0 z-10 flex items-center gap-2 bg-background/80 backdrop-blur px-4 py-2 border-b">
          <FileText className="w-4 h-4 text-primary" />
          <h2 className="text-sm font-medium tracking-wide">Executive Summary</h2>
        </div>
        
        <CardContent className="p-4">
          <div 
            className="prose prose-base max-w-none dark:prose-invert 
                       prose-headings:text-foreground prose-headings:font-semibold prose-headings:tracking-wide
                       prose-p:text-muted-foreground prose-p:leading-relaxed
                       prose-strong:text-foreground prose-strong:font-semibold
                       prose-ul:my-2 prose-li:my-1 prose-li:text-muted-foreground prose-li:leading-6
                       prose-table:text-sm prose-table:border-collapse 
                       prose-table:border prose-table:border-border/30
                       prose-th:bg-muted/40 prose-th:font-semibold prose-th:text-foreground 
                       prose-th:p-2 prose-th:border prose-th:border-border/30 prose-th:leading-6
                       prose-td:p-2 prose-td:border prose-td:border-border/20 
                       prose-td:text-muted-foreground prose-td:leading-6
                       prose-thead:border-b prose-thead:border-border/50
                       prose-code:text-foreground prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                       prose-pre:bg-muted prose-pre:border prose-pre:border-border/30
                       prose-blockquote:border-l-primary prose-blockquote:text-muted-foreground
                       prose-hr:border-border/50"
          >
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            components={{
              // Custom table component for better responsive design
              table: ({ children, ...props }) => (
                <div className="overflow-x-auto">
                  <table {...props} className="min-w-full">
                    {children}
                  </table>
                </div>
              ),
              
              // Custom heading components with proper hierarchy
              h1: ({ children, ...props }) => (
                <h1 {...props} className="text-lg font-bold text-foreground mb-3 mt-6 first:mt-0">
                  {children}
                </h1>
              ),
              h2: ({ children, ...props }) => (
                <h2 {...props} className="text-base font-semibold text-foreground mb-2 mt-5 first:mt-0">
                  {children}
                </h2>
              ),
              h3: ({ children, ...props }) => (
                <h3 {...props} className="text-sm font-semibold text-foreground mb-2 mt-4 first:mt-0">
                  {children}
                </h3>
              ),
              h4: ({ children, ...props }) => (
                <h4 {...props} className="text-sm font-medium text-foreground mb-1 mt-3 first:mt-0">
                  {children}
                </h4>
              ),
              
              // Custom paragraph styling
              p: ({ children, ...props }) => (
                <p {...props} className="text-sm text-muted-foreground leading-relaxed mb-3">
                  {children}
                </p>
              ),
              
              // Custom list styling
              ul: ({ children, ...props }) => (
                <ul {...props} className="text-sm text-muted-foreground space-y-1 mb-3 pl-4">
                  {children}
                </ul>
              ),
              ol: ({ children, ...props }) => (
                <ol {...props} className="text-sm text-muted-foreground space-y-1 mb-3 pl-4">
                  {children}
                </ol>
              ),
              li: ({ children, ...props }) => (
                <li {...props} className="text-sm text-muted-foreground">
                  {children}
                </li>
              ),
              
              // Custom code styling
              code: ({ children, ...props }: { children?: React.ReactNode }) => {
                const { node, ...restProps } = props as any
                const isInline = !node?.parent || node.parent.type !== 'pre'
                
                if (isInline) {
                  return (
                    <code {...restProps} className="text-xs bg-muted text-foreground px-1 py-0.5 rounded font-mono">
                      {children}
                    </code>
                  )
                }
                return (
                  <code {...restProps} className="text-xs text-foreground font-mono">
                    {children}
                  </code>
                )
              },
              
              // Custom pre styling for code blocks
              pre: ({ children, ...props }) => (
                <pre {...props} className="bg-muted border border-border/30 rounded-lg p-3 text-xs overflow-x-auto mb-3">
                  {children}
                </pre>
              ),
              
              // Custom strong/bold styling
              strong: ({ children, ...props }) => (
                <strong {...props} className="font-semibold text-foreground">
                  {children}
                </strong>
              ),
              
              // Custom emphasis styling  
              em: ({ children, ...props }) => (
                <em {...props} className="italic text-muted-foreground">
                  {children}
                </em>
              )
            }}
          >
            {content}
          </ReactMarkdown>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}