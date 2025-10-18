"use client"

import * as React from "react"
import { Streamdown, type StreamdownProps } from "streamdown"
import type { Components } from "react-markdown"
import { cn } from "@/shared/lib/utils"

export interface ResponseProps extends Omit<StreamdownProps, "children"> {
  children?: React.ReactNode
  className?: string
  reduceMotion?: boolean
}

const baseClasses =
  "prose prose-sm dark:prose-invert max-w-none prose-pre:bg-muted/70 prose-pre:border prose-pre:border-border/60 prose-pre:rounded-lg prose-pre:px-4 prose-pre:py-3 prose-code:bg-muted/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-[0.95em] prose-p:leading-relaxed prose-li:my-1 prose-table:overflow-hidden prose-table:border-border/60 prose-th:bg-muted/60"

const defaultComponents: Components = {
  code({ className, children, ...props }) {
    const raw = String(children ?? "")
    const hasLanguage = /language-\w+/.test(className ?? "")
    if (!hasLanguage) {
      return (
        <code
          className={cn("rounded bg-muted px-1.5 py-0.5 text-[0.95em]", className)}
          {...props}
        >
          {raw}
        </code>
      )
    }
    return (
      <pre className="overflow-x-auto rounded-lg border border-border/60 bg-muted/70 p-3">
        <code className={className} {...props}>
          {raw}
        </code>
      </pre>
    )
  },
  a({ className, ...props }) {
    return (
      <a
        className={cn(
          "text-mb-blue-500 underline decoration-mb-blue-500/70 underline-offset-2 transition hover:text-mb-blue-400",
          className,
        )}
        target="_blank"
        rel="noreferrer noopener"
        {...props}
      />
    )
  },
}

export const Response = React.memo(function Response({
  children,
  className,
  reduceMotion,
  components,
  remarkPlugins,
  rehypePlugins,
  ...rest
}: ResponseProps) {
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const isAnimating = React.useMemo(() => !(reduceMotion ?? prefersReduced), [reduceMotion, prefersReduced])

  const mergedComponents = React.useMemo<Components>(() => {
    if (!components) return defaultComponents
    return {
      ...defaultComponents,
      ...components,
    }
  }, [components])

  const streamdownProps: StreamdownProps = {
    ...rest,
    isAnimating,
    components: mergedComponents,
    className: cn(baseClasses, 'prose-headings:mt-3 prose-headings:mb-2 prose-p:my-2 prose-pre:my-3 prose-blockquote:my-3', className),
  }

  if (remarkPlugins) {
    // Only override when explicitly provided; otherwise, use Streamdown defaults
    ;(streamdownProps as any).remarkPlugins = remarkPlugins
  }
  if (rehypePlugins) {
    ;(streamdownProps as any).rehypePlugins = rehypePlugins
  }

  return <Streamdown {...streamdownProps}>{children}</Streamdown>
})

Response.displayName = "Response"

export default Response
