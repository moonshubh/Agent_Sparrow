'use client';

import React, { memo, useMemo, useEffect, useRef, useCallback, useId } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import remarkDirective from 'remark-directive';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';
import { CopyCodeButton } from './CopyCodeButton';
import { cn } from '@/shared/lib/utils';
import {
  artifactPlugin,
  extractContent,
  useArtifactActions,
  ArtifactBadgeOrButton,
  generateArtifactId,
  ARTIFACT_DEFAULTS,
} from '../artifacts';
import type { Artifact, ArtifactType } from '../artifacts';

interface EnhancedMarkdownProps {
  /** The markdown content to render */
  content: string;
  /** Whether this is the latest/streaming message */
  isLatestMessage?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Message ID for artifact association */
  messageId?: string;
}

/**
 * Preprocess LaTeX content to handle common edge cases.
 * Ensures proper escaping and formatting for KaTeX rendering.
 */
function preprocessLaTeX(content: string): string {
  // Handle common LaTeX issues:
  // 1. Ensure block math has proper newlines
  // 2. Handle inline math with single $ (convert to $$)
  let processed = content;
  
  // Fix block math that might not have proper delimiters
  processed = processed.replace(/\$\$([^$]+)\$\$/g, (_, math) => {
    return `$$${math.trim()}$$`;
  });
  
  return processed;
}

/**
 * EnhancedMarkdown - A full-featured markdown renderer with support for:
 * - GitHub Flavored Markdown (tables, task lists, strikethrough)
 * - LaTeX math (inline and block via KaTeX)
 * - Syntax highlighting for code blocks
 * - Directives (::artifact, :::thinking)
 * - Copy button for code blocks
 * 
 * Inspired by LibreChat's Markdown.tsx but adapted for Agent Sparrow.
 */
export const EnhancedMarkdown = memo(function EnhancedMarkdown({
  content = '',
  isLatestMessage = false,
  className,
  messageId = 'unknown',
}: EnhancedMarkdownProps) {
  // Artifact actions for registering artifacts
  const { addArtifact } = useArtifactActions();

  // Track registered artifacts to avoid duplicates
  const registeredArtifactsRef = useRef<Set<string>>(new Set());

  // Reset registered artifacts when content or messageId changes (Issue #1: stale artifact tracking)
  useEffect(() => {
    registeredArtifactsRef.current = new Set();
  }, [content, messageId]);

  // Preprocess content for LaTeX
  const processedContent = useMemo(() => {
    if (!content) return '';
    return preprocessLaTeX(content);
  }, [content]);

  // Memoize remark plugins (including artifact detection)
  const remarkPlugins = useMemo(
    () => [
      remarkGfm,
      remarkDirective,
      artifactPlugin,
      [remarkMath, { singleDollarTextMath: false }],
    ],
    []
  );

  // Memoize rehype plugins
  const rehypePlugins = useMemo(
    () => [
      rehypeKatex,
      [
        rehypeHighlight,
        {
          detect: true,
          ignoreMissing: true,
        },
      ],
    ],
    []
  );

  // Helper to register an artifact - deferred to avoid state updates during render
  const registerArtifact = useCallback(
    (artifact: Artifact) => {
      if (!registeredArtifactsRef.current.has(artifact.id)) {
        registeredArtifactsRef.current.add(artifact.id);
        // Defer state update to avoid "Cannot update component while rendering" error
        queueMicrotask(() => {
          addArtifact(artifact);
        });
      }
    },
    [addArtifact]
  );

  // Custom components for markdown rendering
  const components: Components = useMemo(
    () => ({
      // Code blocks with syntax highlighting, copy button, and artifact detection
      // Destructure artifact props to prevent them from being spread onto DOM elements
      code({
        node,
        inline,
        className: codeClassName,
        children,
        // Extract custom props to prevent React DOM warnings
        isArtifact: _isArtifact,
        artifactType: _artifactType,
        artifactTitle: _artifactTitle,
        artifactLanguage: _artifactLanguage,
        ...props
      }: any) {
        const match = /language-(\w+)/.exec(codeClassName || '');
        const language = match ? match[1] : '';
        const codeString = String(children).replace(/\n$/, '');

        // Check for artifact metadata from the plugin (prefer hProperties over direct props)
        const hProps = node?.data?.hProperties || {};
        const isArtifact = hProps.isArtifact === true || _isArtifact === true;
        const artifactType = (hProps.artifactType || _artifactType) as ArtifactType | undefined;
        const artifactTitle = (hProps.artifactTitle || _artifactTitle) as string | undefined;

        // Inline code
        if (inline) {
          return (
            <code
              {...props}
              className={cn(
                'bg-secondary px-1.5 py-0.5 rounded-md text-xs font-mono',
                'text-terracotta-300',
                codeClassName
              )}
            >
              {children}
            </code>
          );
        }

        // Handle artifact code blocks
        if (isArtifact && artifactType) {
          const artifact: Artifact = {
            id: generateArtifactId(
              ARTIFACT_DEFAULTS.identifier,
              artifactType,
              artifactTitle || ARTIFACT_DEFAULTS.title,
              messageId
            ),
            type: artifactType,
            title: artifactTitle || ARTIFACT_DEFAULTS.title,
            content: codeString,
            messageId,
            language: language || undefined,
          };

          // Register the artifact
          registerArtifact(artifact);

          // Render artifact button instead of code block for mermaid
          if (artifactType === 'mermaid') {
            return <ArtifactBadgeOrButton artifact={artifact} variant="button" />;
          }

          // For other artifacts, show both the code and a badge
          return (
            <div className="relative">
              <div className="mb-2">
                <ArtifactBadgeOrButton artifact={artifact} variant="badge" />
              </div>
              <div className="relative group my-2 rounded-lg overflow-hidden border border-border shadow-academia-sm">
                {language && (
                  <div className="flex items-center justify-between bg-secondary px-4 py-2 border-b border-border">
                    <span className="text-xs text-muted-foreground font-mono uppercase">
                      {language}
                    </span>
                    <CopyCodeButton text={codeString} size="sm" />
                  </div>
                )}
                <div className="relative">
                  {!language && (
                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <CopyCodeButton text={codeString} size="sm" />
                    </div>
                  )}
                  <pre className="overflow-x-auto p-4 bg-[hsl(var(--code-block-bg))]">
                    <code {...props} className={cn('text-sm font-mono', codeClassName)}>
                      {children}
                    </code>
                  </pre>
                </div>
              </div>
            </div>
          );
        }

        // Regular code block (non-artifact)
        return (
          <div className="relative group my-4 rounded-lg overflow-hidden border border-border shadow-academia-sm">
            {/* Language header */}
            {language && (
              <div className="flex items-center justify-between bg-secondary px-4 py-2 border-b border-border">
                <span className="text-xs text-muted-foreground font-mono uppercase">
                  {language}
                </span>
                <CopyCodeButton text={codeString} size="sm" />
              </div>
            )}
            
            {/* Code content */}
            <div className="relative">
              {!language && (
                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <CopyCodeButton text={codeString} size="sm" />
                </div>
              )}
              <pre className="overflow-x-auto p-4 bg-[hsl(var(--code-block-bg))]">
                <code
                  {...props}
                  className={cn('text-sm font-mono', codeClassName)}
                >
                  {children}
                </code>
              </pre>
            </div>
          </div>
        );
      },

      // Artifact directive component (for ::artifact{} syntax)
      artifact({ node, children, ...props }: any) {
        const type = (props.type || ARTIFACT_DEFAULTS.type) as ArtifactType;
        const title = props.title || ARTIFACT_DEFAULTS.title;
        const identifier = props.identifier || ARTIFACT_DEFAULTS.identifier;
        const contentText = extractContent(children);

        const artifact: Artifact = {
          id: generateArtifactId(identifier, type, title, messageId),
          type,
          title,
          content: contentText,
          messageId,
          identifier,
          language: props.language,
        };

        // Register the artifact
        registerArtifact(artifact);

        return <ArtifactBadgeOrButton artifact={artifact} variant="button" />;
      },

      // Paragraphs
      p({ children, ...props }: any) {
        return (
          <p {...props} className="mb-4 last:mb-0 leading-relaxed">
            {children}
          </p>
        );
      },

      // Links - open in new tab for external
      a({ href, children, ...props }: any) {
        const isExternal = href?.startsWith('http');
        return (
          <a
            {...props}
            href={href}
            target={isExternal ? '_blank' : undefined}
            rel={isExternal ? 'noopener noreferrer' : undefined}
            className={cn(
              'text-primary hover:text-primary/80 underline underline-offset-2',
              'transition-colors duration-200'
            )}
          >
            {children}
          </a>
        );
      },

      // Tables with enhanced styling
      table({ children, ...props }: any) {
        return (
          <div className="my-4 overflow-x-auto rounded-lg border border-border">
            <table
              {...props}
              className="w-full text-sm border-collapse"
            >
              {children}
            </table>
          </div>
        );
      },

      thead({ children, ...props }: any) {
        return (
          <thead {...props} className="bg-secondary/50">
            {children}
          </thead>
        );
      },

      th({ children, ...props }: any) {
        return (
          <th
            {...props}
            className="px-4 py-3 text-left font-semibold text-foreground border-b border-border"
          >
            {children}
          </th>
        );
      },

      td({ children, ...props }: any) {
        return (
          <td
            {...props}
            className="px-4 py-3 border-b border-border/50 text-muted-foreground"
          >
            {children}
          </td>
        );
      },

      // Lists
      ul({ children, ...props }: any) {
        return (
          <ul {...props} className="list-disc list-inside my-3 space-y-1.5 ml-2">
            {children}
          </ul>
        );
      },

      ol({ children, ...props }: any) {
        return (
          <ol {...props} className="list-decimal list-inside my-3 space-y-1.5 ml-2">
            {children}
          </ol>
        );
      },

      li({ children, ...props }: any) {
        return (
          <li {...props} className="text-foreground/90">
            {children}
          </li>
        );
      },

      // Blockquotes
      blockquote({ children, ...props }: any) {
        return (
          <blockquote
            {...props}
            className={cn(
              'border-l-4 border-accent pl-4 py-2 my-4',
              'italic text-muted-foreground bg-secondary/20 rounded-r-lg'
            )}
          >
            {children}
          </blockquote>
        );
      },

      // Headings
      h1({ children, ...props }: any) {
        return (
          <h1 {...props} className="text-2xl font-bold mb-4 mt-6 first:mt-0 text-foreground">
            {children}
          </h1>
        );
      },

      h2({ children, ...props }: any) {
        return (
          <h2 {...props} className="text-xl font-bold mb-3 mt-5 first:mt-0 text-foreground">
            {children}
          </h2>
        );
      },

      h3({ children, ...props }: any) {
        return (
          <h3 {...props} className="text-lg font-semibold mb-2 mt-4 first:mt-0 text-foreground">
            {children}
          </h3>
        );
      },

      h4({ children, ...props }: any) {
        return (
          <h4 {...props} className="text-base font-semibold mb-2 mt-3 first:mt-0 text-foreground">
            {children}
          </h4>
        );
      },

      // Horizontal rule
      hr({ ...props }: any) {
        return (
          <hr {...props} className="my-6 border-border" />
        );
      },

      // Strong/emphasis
      strong({ children, ...props }: any) {
        return (
          <strong {...props} className="font-semibold text-foreground">
            {children}
          </strong>
        );
      },

      em({ children, ...props }: any) {
        return (
          <em {...props} className="italic">
            {children}
          </em>
        );
      },

      // Images with lazy loading
      img({ src, alt, ...props }: any) {
        return (
          <img
            {...props}
            src={src}
            alt={alt || ''}
            loading="lazy"
            className={cn(
              'max-w-full h-auto rounded-lg my-4',
              'border border-border shadow-academia-sm'
            )}
          />
        );
      },
    }),
    [messageId, registerArtifact]
  );

  // Empty state with optional cursor for streaming
  if (!processedContent) {
    if (isLatestMessage) {
      return (
        <div className="animate-pulse">
          <span className="inline-block w-2 h-4 bg-primary/50 rounded-sm" />
        </div>
      );
    }
    return null;
  }

  return (
    <div className={cn('enhanced-markdown', className)}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins as any}
        rehypePlugins={rehypePlugins as any}
        components={components}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
});

export default EnhancedMarkdown;
