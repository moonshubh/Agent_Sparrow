'use client';

import React, { memo, useMemo, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import remarkDirective from 'remark-directive';
import remarkSupersub from 'remark-supersub';
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

type ExtendedComponents = Components & {
  artifact?: (props: any) => React.ReactElement | null;
};

interface EnhancedMarkdownProps {
  /** The markdown content to render */
  content: string;
  /** Whether this is the latest/streaming message */
  isLatestMessage?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Message ID for artifact association */
  messageId?: string;
  /** Whether to register artifacts (disabled during streaming to avoid partial artifacts) */
  registerArtifacts?: boolean;
  /** Rendering variant for styling behavior */
  variant?: 'default' | 'librechat';
  /** Optional component overrides */
  componentsOverride?: Components;
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
  registerArtifacts = true,
  variant = 'default',
  componentsOverride,
}: EnhancedMarkdownProps) {
  // Artifact actions for registering artifacts
  const { addArtifact, setCurrentArtifact, setArtifactsVisible } = useArtifactActions();

  // Track registered artifacts to avoid duplicates
  const registeredArtifactsRef = useRef<Set<string>>(new Set());
  const artifactIndexRef = useRef(0);

  // Reset registered artifacts when content or messageId changes (Issue #1: stale artifact tracking)
  useEffect(() => {
    registeredArtifactsRef.current = new Set();
    artifactIndexRef.current = 0;
  }, [content, messageId]);

  const getNextArtifactIndex = useCallback(() => {
    const next = artifactIndexRef.current;
    artifactIndexRef.current += 1;
    return next;
  }, []);

  // Preprocess content for LaTeX and strip any markdown data URIs
  const processedContent = useMemo(() => {
    if (!content) return '';

    // CRITICAL: Strip markdown images with data URIs as final safety net
    // Pattern: ![alt text](data:image/...) - these should never reach markdown rendering
    // Images are displayed as artifacts, not embedded in chat text
    const MARKDOWN_DATA_URI_PATTERN = /!\[[^\]]*\]\(data:image\/[^)]+\)/gi;
    let sanitized = content;
    if (MARKDOWN_DATA_URI_PATTERN.test(content)) {
      sanitized = content.replace(MARKDOWN_DATA_URI_PATTERN, '').trim();
      console.debug('[EnhancedMarkdown] Stripped markdown data URI from content');
    }

    return preprocessLaTeX(sanitized);
  }, [content]);

  // Memoize remark plugins (including artifact detection)
  const remarkPlugins = useMemo(
    () => [
      remarkGfm,
      remarkDirective,
      artifactPlugin,
      remarkSupersub,  // Superscript/subscript support (e.g., H₂O, E=mc²)
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
      if (!registerArtifacts) return;
      if (!registeredArtifactsRef.current.has(artifact.id)) {
        registeredArtifactsRef.current.add(artifact.id);
        // Defer state update to avoid "Cannot update component while rendering" error
        queueMicrotask(() => {
          addArtifact(artifact);
        });
      }
    },
    [addArtifact, registerArtifacts]
  );

  // Custom components for markdown rendering
  const components: ExtendedComponents = useMemo(() => {
    const isLibreChat = variant === 'librechat';
    const artifactTheme = isLibreChat ? 'librechat' : 'default';

    const baseComponents: ExtendedComponents = {
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

        // Inline code detection for react-markdown v9+
        // The `inline` prop was removed in v9, so we detect by absence of language class
        // Inline code has no language-* class, block code does
        const isInline = inline || !codeClassName?.includes('language-');

        if (isInline) {
          if (isLibreChat) {
            return (
              <code {...props} className={codeClassName}>
                {children}
              </code>
            );
          }

          return (
            <code
              {...props}
              className={cn(
                'bg-secondary px-1 py-0.5 rounded text-[0.8em] font-semibold font-mono',
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
          const artifactIndex = getNextArtifactIndex();
          const artifact: Artifact = {
            id: generateArtifactId(
              ARTIFACT_DEFAULTS.identifier,
              artifactType,
              artifactTitle || ARTIFACT_DEFAULTS.title,
              messageId,
              artifactIndex
            ),
            type: artifactType,
            title: artifactTitle || ARTIFACT_DEFAULTS.title,
            content: codeString,
            messageId,
            language: language || undefined,
            index: artifactIndex,
          };

          // Register the artifact (only when allowed)
          registerArtifact(artifact);

          // Render artifact button instead of code block for mermaid
          if (artifactType === 'mermaid') {
            if (!registerArtifacts) {
              // During streaming, show the code block inline to avoid partial registration
              if (isLibreChat) {
                return (
                  <pre>
                    <code {...props} className={codeClassName}>
                      {children}
                    </code>
                  </pre>
                );
              }

              return (
                <div className="relative group my-2 rounded-lg overflow-hidden border border-border shadow-academia-sm">
                  <pre className="overflow-x-auto p-3 bg-[hsl(var(--code-block-bg))]">
                    <code {...props} className={cn('text-[11px] font-mono', codeClassName)}>
                      {children}
                    </code>
                  </pre>
                </div>
              );
            }
            return (
              <ArtifactBadgeOrButton
                artifact={artifact}
                variant="button"
                theme={artifactTheme}
              />
            );
          }

          // For other artifacts, show both the code and a badge
          if (isLibreChat) {
            return (
              <div className="lc-artifact-block">
                {registerArtifacts && (
                  <div className="lc-artifact-badge-wrapper">
                    <ArtifactBadgeOrButton
                      artifact={artifact}
                      variant="badge"
                      theme={artifactTheme}
                    />
                  </div>
                )}
                <pre>
                  <code {...props} className={codeClassName}>
                    {children}
                  </code>
                </pre>
              </div>
            );
          }

          return (
            <div className="relative">
              {registerArtifacts && (
                <div className="mb-2">
                  <ArtifactBadgeOrButton artifact={artifact} variant="badge" />
                </div>
              )}
              <div className="relative group my-1.5 rounded-lg overflow-hidden border border-border shadow-academia-sm">
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
                  <pre className="overflow-x-auto p-3 bg-[hsl(var(--code-block-bg))]">
                    <code {...props} className={cn('text-[11px] font-mono', codeClassName)}>
                      {children}
                    </code>
                  </pre>
                </div>
              </div>
            </div>
          );
        }

        // Regular code block (non-artifact)
        if (isLibreChat) {
          return (
            <pre>
              <code {...props} className={codeClassName}>
                {children}
              </code>
            </pre>
          );
        }

        return (
          <div className="relative group my-4 rounded-xl overflow-hidden border border-border/60 shadow-academia-sm bg-[hsl(var(--code-block-bg))]">
            {/* Language header */}
            {language && (
              <div className="flex items-center justify-between bg-secondary/30 px-4 py-2 border-b border-border/40">
                <span className="text-[10px] font-semibold text-muted-foreground font-mono uppercase tracking-wider">
                  {language}
                </span>
                <CopyCodeButton text={codeString} size="sm" />
              </div>
            )}

            {/* Code content */}
            <div className="relative">
              {!language && (
                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                  <CopyCodeButton text={codeString} size="sm" />
                </div>
              )}
              <pre className="overflow-x-auto p-4">
                <code
                  {...props}
                  className={cn('text-[12px] font-mono leading-relaxed', codeClassName)}
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
        const artifactIndex = getNextArtifactIndex();

        const artifact: Artifact = {
          id: generateArtifactId(identifier, type, title, messageId, artifactIndex),
          type,
          title,
          content: contentText,
          messageId,
          identifier,
          language: props.language,
          index: artifactIndex,
        };

        // Register the artifact (skip during streaming)
        registerArtifact(artifact);

        if (!registerArtifacts) {
          if (isLibreChat) {
            return (
              <div className="lc-artifact-block">
                <div className="lc-artifact-inline-title">Artifact: {title}</div>
                <pre>
                  <code>{contentText}</code>
                </pre>
              </div>
            );
          }

          return (
            <div className="my-2 border border-border rounded-lg p-3 bg-secondary/40">
              <div className="text-xs text-muted-foreground mb-1">Artifact: {title}</div>
              <pre className="text-[11px] font-mono overflow-x-auto">
                <code>{contentText}</code>
              </pre>
            </div>
          );
        }

        return (
          <ArtifactBadgeOrButton
            artifact={artifact}
            variant="button"
            theme={artifactTheme}
          />
        );
      },

      // Images with lazy loading and artifact support for generated images
      img({ src, alt, ...props }: any) {
        // Check if this is a base64 data URL (generated image)
        const isGeneratedImage = src?.startsWith('data:image/');

        // Handle generated images with artifact support
        if (isGeneratedImage) {
          // Extract base64 data and mime type
          const dataUrlMatch = src.match(/^data:(image\/[^;]+);base64,(.+)$/);
          const mimeType = dataUrlMatch?.[1] || 'image/png';
          const imageData = dataUrlMatch?.[2] || '';
          const artifactIndex = getNextArtifactIndex();

          // Create artifact for the generated image
          const imageArtifact: Artifact = {
            id: generateArtifactId(
              'generated-image',
              'image',
              alt || 'Generated Image',
              messageId,
              artifactIndex
            ),
            type: 'image',
            title: alt || 'Generated Image',
            content: src,
            messageId,
            imageData,
            mimeType,
            altText: alt,
            index: artifactIndex,
          };

          // Register the artifact
          registerArtifact(imageArtifact);

          const handleImageClick = () => {
            if (registerArtifacts) {
              addArtifact(imageArtifact);
              setCurrentArtifact(imageArtifact.id);
              setArtifactsVisible(true);
            }
          };

          if (isLibreChat) {
            return (
              <img
                {...props}
                src={src}
                alt={alt || 'Generated image'}
                loading="lazy"
                className={cn('lc-generated-image', props.className)}
                onClick={handleImageClick}
              />
            );
          }

          return (
            <div className="my-4 group relative">
              <img
                {...props}
                src={src}
                alt={alt || 'Generated image'}
                loading="lazy"
                className={cn(
                  'max-w-[400px] max-h-[300px] w-auto h-auto rounded-lg',
                  'border border-border shadow-academia-sm',
                  'cursor-pointer transition-all duration-200',
                  'hover:shadow-lg hover:border-primary/50'
                )}
                onClick={handleImageClick}
              />
              {registerArtifacts && (
                <div className="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={handleImageClick}
                    className={cn(
                      'px-2 py-1 rounded-md text-xs font-medium',
                      'bg-primary/90 text-primary-foreground',
                      'hover:bg-primary transition-colors',
                      'shadow-sm backdrop-blur-sm'
                    )}
                  >
                    View Full Size
                  </button>
                </div>
              )}
            </div>
          );
        }

        // Regular images (external URLs)
        if (isLibreChat) {
          return (
            <img
              {...props}
              src={src}
              alt={alt || ''}
              loading="lazy"
            />
          );
        }

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
    };

    if (!isLibreChat) {
      // Paragraphs - handle block-level children gracefully to avoid hydration errors
      // HTML spec: <p> cannot contain <div>, <pre>, etc.
      baseComponents.p = ({ children, ...props }: any) => {
        // Check if any child is a block-level element (React element with div/pre/table/etc)
        const hasBlockChild = React.Children.toArray(children).some((child) => {
          if (!React.isValidElement(child)) return false;
          const type = (child as React.ReactElement).type;
          // Check for common block-level element types
          if (typeof type === 'string') {
            return ['div', 'pre', 'table', 'ul', 'ol', 'blockquote', 'figure', 'hr', 'section', 'header', 'footer'].includes(type);
          }
          // Any custom component is treated as block-ish to avoid invalid <p> nesting
          return true;
        });

        // If we have block children, use div instead of p to avoid hydration errors
        if (hasBlockChild) {
          return (
            <div {...props} className="mb-2 last:mb-0 leading-relaxed">
              {children}
            </div>
          );
        }

        return (
          <p {...props} className="mb-2 last:mb-0 leading-relaxed">
            {children}
          </p>
        );
      };

      // Links - open in new tab for external, show clean domain names
      baseComponents.a = ({ href, children, ...props }: any) => {
        const isExternal = href?.startsWith('http');

        // Extract clean display text if children is a raw URL
        let displayText = children;
        const childStr = String(children);

        // If the link text is the same as the href (raw URL), show just the domain
        if (childStr === href && href?.startsWith('http')) {
          try {
            const url = new URL(href);
            displayText = url.hostname.replace('www.', '');
          } catch {
            // Keep original if URL parsing fails
          }
        }

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
            {displayText}
          </a>
        );
      };

      // Tables with enhanced styling
      baseComponents.table = ({ children, ...props }: any) => (
        <div className="my-4 overflow-x-auto rounded-lg border border-border">
          <table
            {...props}
            className="w-full text-sm border-collapse"
          >
            {children}
          </table>
        </div>
      );

      baseComponents.thead = ({ children, ...props }: any) => (
        <thead {...props} className="bg-secondary/50">
          {children}
        </thead>
      );

      baseComponents.th = ({ children, ...props }: any) => (
        <th
          {...props}
          className="px-4 py-3 text-left font-semibold text-foreground border-b border-border"
        >
          {children}
        </th>
      );

      baseComponents.td = ({ children, ...props }: any) => (
        <td
          {...props}
          className="px-4 py-3 border-b border-border/50 text-muted-foreground"
        >
          {children}
        </td>
      );

      // Lists - tighter spacing like LibreChat
      baseComponents.ul = ({ children, ...props }: any) => (
        <ul {...props} className="list-disc list-outside my-2 space-y-1 ml-4 pl-1">
          {children}
        </ul>
      );

      baseComponents.ol = ({ children, ...props }: any) => (
        <ol {...props} className="list-decimal list-outside my-2 space-y-1 ml-4 pl-1">
          {children}
        </ol>
      );

      baseComponents.li = ({ children, ...props }: any) => (
        <li {...props} className="text-foreground/90 pl-1">
          {children}
        </li>
      );

      // Blockquotes
      baseComponents.blockquote = ({ children, ...props }: any) => (
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

      // Headings - tighter margins like LibreChat
      baseComponents.h1 = ({ children, ...props }: any) => (
        <h1 {...props} className="text-xl font-bold mb-2 mt-4 first:mt-0 text-foreground">
          {children}
        </h1>
      );

      baseComponents.h2 = ({ children, ...props }: any) => (
        <h2 {...props} className="text-lg font-semibold mb-2 mt-3 first:mt-0 text-foreground">
          {children}
        </h2>
      );

      baseComponents.h3 = ({ children, ...props }: any) => (
        <h3 {...props} className="text-base font-semibold mb-1.5 mt-2.5 first:mt-0 text-foreground">
          {children}
        </h3>
      );

      baseComponents.h4 = ({ children, ...props }: any) => (
        <h4 {...props} className="text-sm font-medium mb-1 mt-2 first:mt-0 text-foreground">
          {children}
        </h4>
      );

      // Horizontal rule
      baseComponents.hr = ({ ...props }: any) => (
        <hr {...props} className="my-6 border-border" />
      );

      // Strong/emphasis
      baseComponents.strong = ({ children, ...props }: any) => (
        <strong {...props} className="font-semibold text-foreground">
          {children}
        </strong>
      );

      baseComponents.em = ({ children, ...props }: any) => (
        <em {...props} className="italic">
          {children}
        </em>
      );
    }

    return componentsOverride ? { ...baseComponents, ...componentsOverride } : baseComponents;
  }, [
    variant,
    componentsOverride,
    messageId,
    registerArtifact,
    addArtifact,
    setCurrentArtifact,
    setArtifactsVisible,
    registerArtifacts,
    getNextArtifactIndex,
  ]);

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

  const wrapperClassName = cn(
    variant === 'librechat' ? undefined : 'enhanced-markdown',
    className
  );

  return (
    <div className={wrapperClassName}>
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
