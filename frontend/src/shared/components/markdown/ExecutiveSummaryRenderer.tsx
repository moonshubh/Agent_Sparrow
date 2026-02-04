"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import rehypeAutolinkHeadings from "rehype-autolink-headings";
import { FileText } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/shared/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui/table";
import { cn } from "@/shared/lib/utils";
import { sectionPatterns, NBSP } from "@/shared/lib/text/emoji";
import "./exec-summary.css";

interface ExecutiveSummaryRendererProps {
  content: string;
  className?: string;
}

/**
 * Preprocesses markdown content to remove implementation timeline sections,
 * priority implementation order blocks, and clean up formatting for executive summaries
 */
function preprocessMarkdown(markdown: string): string {
  if (!markdown || typeof markdown !== "string") return "";

  const trimmed = markdown.trim();
  if (!trimmed) return "";

  // Split into lines for processing
  const lines = trimmed.split("\n");
  const processedLines: string[] = [];
  let skipSection = false;
  let currentHeadingLevel = 0;

  for (const line of lines) {
    // Check if this is a heading that matches timeline/priority patterns
    const headingMatch = line.match(/^(#+)\s*(.*)$/i);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const title = headingMatch[2].trim();

      // Enhanced pattern matching for both timeline and priority sections
      if (
        title.match(
          /^(implementation\s+timeline|priority\s+implementation\s+order)$/i,
        )
      ) {
        skipSection = true;
        currentHeadingLevel = level;
        continue;
      }

      // If we encounter a new heading at the same level or higher, stop skipping
      if (skipSection && level <= currentHeadingLevel) {
        skipSection = false;
      }

      // Inject emojis for h2 headings (level 2)
      if (!skipSection && level === 2) {
        const matchingPattern = sectionPatterns.find((pattern) =>
          pattern.pattern.test(title),
        );
        if (matchingPattern) {
          const emojiHeading = `## ${matchingPattern.emoji}${NBSP}${title}`;
          processedLines.push(emojiHeading);
          continue;
        }
      }
    }

    // Skip lines if we're in a blocked section
    if (skipSection) {
      continue;
    }

    // Clean up excessive whitespace and normalize line spacing
    const cleanedLine = line.replace(/\s+$/, ""); // Remove trailing whitespace
    processedLines.push(cleanedLine);
  }

  // Join and normalize multiple blank lines to single blank lines
  const result = processedLines
    .join("\n")
    .replace(/\n{3,}/g, "\n\n") // Replace 3+ newlines with 2
    .trim();

  return result;
}

export function ExecutiveSummaryRenderer({
  content,
  className,
}: ExecutiveSummaryRendererProps) {
  const processedContent = preprocessMarkdown(content);

  if (!processedContent) {
    return null;
  }

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-primary" />
          <h2 className="text-sm font-semibold tracking-wide">
            Executive Summary
          </h2>
        </div>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "prose prose-sm dark:prose-invert max-w-none",
            "exec-summary", // Apply our custom CSS overrides
            // Enhanced code and pre styling
            "prose-pre:bg-muted/60 prose-pre:rounded-lg prose-pre:border prose-pre:border-border/50",
            "prose-pre:px-4 prose-pre:py-3 prose-pre:text-sm prose-pre:overflow-x-auto",
            "prose-code:bg-muted/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded",
            "prose-code:text-foreground prose-code:font-mono prose-code:text-xs prose-code:font-medium",
            // Improved list styling
            "prose-ul:space-y-1 prose-ol:space-y-1",
            "prose-li:text-muted-foreground prose-li:leading-relaxed prose-li:my-1",
            // Enhanced emphasis and text styling
            "prose-em:text-muted-foreground prose-em:font-medium",
            "prose-p:text-muted-foreground prose-p:leading-relaxed",
            // Improved blockquote styling
            "prose-blockquote:border-l-4 prose-blockquote:border-l-accent prose-blockquote:bg-muted/30",
            "prose-blockquote:px-4 prose-blockquote:py-3 prose-blockquote:rounded-r prose-blockquote:my-4",
            "prose-blockquote:text-muted-foreground prose-blockquote:italic",
            // Enhanced table styling with shadcn utilities
            "prose-table:w-full prose-table:border-collapse prose-table:border prose-table:border-border/50",
            "prose-table:text-xs prose-table:rounded-lg prose-table:overflow-hidden",
            "prose-th:bg-muted/60 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:font-semibold",
            "prose-th:text-foreground prose-th:border-b prose-th:border-border/50",
            "prose-td:px-3 prose-td:py-2 prose-td:border-b prose-td:border-border/30 prose-td:text-muted-foreground",
            "prose-thead:bg-muted/40 prose-tbody:bg-card",
            // Improved spacing and layout
            "prose-hr:border-border/50 prose-hr:my-6",
            // Enhanced link styling
            "prose-a:text-accent prose-a:font-medium prose-a:no-underline hover:prose-a:underline",
          )}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[
              rehypeSlug,
              [
                rehypeAutolinkHeadings,
                {
                  behavior: "wrap",
                  properties: {
                    className:
                      "anchor-link hover:bg-mb-blue-300 transition-colors",
                  },
                },
              ],
            ]}
            components={{
              // Enhanced list components
              ul: ({ children, ...props }) => (
                <ul className="list-disc ml-6 space-y-1.5 my-3" {...props}>
                  {children}
                </ul>
              ),
              ol: ({ children, ...props }) => (
                <ol className="list-decimal ml-6 space-y-1.5 my-3" {...props}>
                  {children}
                </ol>
              ),
              li: ({ children, ...props }) => (
                <li
                  className="text-muted-foreground leading-relaxed pl-1"
                  {...props}
                >
                  {children}
                </li>
              ),
              // Enhanced table components using shadcn
              table: ({ children, ...props }) => (
                <div className="my-4 rounded-lg border border-border/50 overflow-hidden">
                  <Table {...props}>{children}</Table>
                </div>
              ),
              thead: ({ children, ...props }) => (
                <TableHeader {...props}>{children}</TableHeader>
              ),
              tbody: ({ children, ...props }) => (
                <TableBody {...props}>{children}</TableBody>
              ),
              tr: ({ children, ...props }) => (
                <TableRow {...props}>{children}</TableRow>
              ),
              th: ({ children, ...props }) => (
                <TableHead
                  className="text-xs font-semibold text-foreground bg-muted/60"
                  {...props}
                >
                  {children}
                </TableHead>
              ),
              td: ({ children, ...props }) => (
                <TableCell
                  className="text-xs text-muted-foreground py-2"
                  {...props}
                >
                  {children}
                </TableCell>
              ),
              // Enhanced text components
              p: ({ children, ...props }) => (
                <p
                  className="text-muted-foreground leading-relaxed mb-3 mt-0"
                  {...props}
                >
                  {children}
                </p>
              ),
              strong: ({ children, ...props }) => (
                <strong className="text-foreground font-semibold" {...props}>
                  {children}
                </strong>
              ),
              code: ({ children, ...props }) => (
                <code
                  className="bg-muted/60 px-1.5 py-0.5 rounded text-foreground font-mono text-xs font-medium"
                  {...props}
                >
                  {children}
                </code>
              ),
            }}
          >
            {processedContent}
          </ReactMarkdown>
        </div>
      </CardContent>
    </Card>
  );
}

export default ExecutiveSummaryRenderer;
