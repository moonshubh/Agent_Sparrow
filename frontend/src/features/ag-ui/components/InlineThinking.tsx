'use client';

import React, { useState, useCallback, memo, useId, useMemo } from 'react';
import { Lightbulb, ChevronDown, Clipboard, Check } from 'lucide-react';
import { cn } from '@/shared/lib/utils';

interface InlineThinkingProps {
  /** The thinking/reasoning text content */
  thinkingText: string;
  /** Whether to start expanded (default: false) */
  defaultExpanded?: boolean;
  /** Additional CSS classes for the container */
  className?: string;
  /** Whether the message is still streaming (shows "Thinking..." label) */
  isStreaming?: boolean;
}

/**
 * ThinkingButton - Toggle button for expanding/collapsing thinking content
 *
 * LibreChat-style icon animation:
 * - Shows lightbulb icon by default
 * - Shows chevron on hover (rotates when expanded)
 * - Copy button appears on hover when expanded
 */
const ThinkingButton = memo(function ThinkingButton({
  isExpanded,
  onClick,
  content,
  showCopyButton = true,
  contentId,
  isStreaming = false,
}: {
  isExpanded: boolean;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
  content?: string;
  showCopyButton?: boolean;
  contentId: string;
  /** Shows "Thinking..." label during streaming, "Thoughts" after complete (LibreChat pattern) */
  isStreaming?: boolean;
}) {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    if (!content) return;

    const copyWithFallback = () => {
      try {
        const textarea = document.createElement('textarea');
        textarea.value = content;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        const successful = document.execCommand('copy');
        document.body.removeChild(textarea);
        return successful;
      } catch (fallbackError) {
        console.error('Fallback clipboard copy failed:', fallbackError);
        return false;
      }
    };

    const copy = async () => {
      try {
        if (navigator?.clipboard?.writeText) {
          await navigator.clipboard.writeText(content);
          setIsCopied(true);
          setTimeout(() => setIsCopied(false), 2000);
          return;
        }
      } catch (err) {
        console.error('Failed to copy thinking content:', err);
      }

      if (copyWithFallback()) {
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
      }
    };

    void copy();
  }, [content]);

  return (
    <div className="group/thinking-container flex w-full items-center justify-between gap-2">
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'group/button flex flex-1 items-center justify-start rounded-lg py-1',
          'text-sm font-medium text-muted-foreground leading-[18px]',
          'hover:text-foreground transition-colors duration-200'
        )}
        aria-expanded={isExpanded}
        aria-controls={contentId}
      >
        {/* Icon container with hover swap animation (LibreChat pattern) */}
        <span className="relative mr-1.5 inline-flex h-[18px] w-[18px] items-center justify-center">
          <Lightbulb
            className={cn(
              'h-4 w-4 absolute text-gold-400',
              'opacity-100 transition-opacity duration-200',
              'group-hover/button:opacity-0'
            )}
          />
          <ChevronDown
            className={cn(
              'h-4 w-4 absolute text-foreground',
              'opacity-0 transform-gpu transition-all duration-300',
              'group-hover/button:opacity-100',
              isExpanded && 'rotate-180'
            )}
          />
        </span>
        {/* LibreChat pattern: "Thinking..." during streaming, "Thoughts" after complete */}
        <span className="flex items-center gap-2">
          {isStreaming ? 'Thinking' : 'Thoughts'}
          {isStreaming && (
            <span className="inline-flex gap-0.5">
              <span className="thinking-dot animate-pulse" style={{ animationDelay: '0ms' }}>.</span>
              <span className="thinking-dot animate-pulse" style={{ animationDelay: '150ms' }}>.</span>
              <span className="thinking-dot animate-pulse" style={{ animationDelay: '300ms' }}>.</span>
            </span>
          )}
        </span>
      </button>

      {/* Copy button - visible on hover when expanded */}
      {content && showCopyButton && (
        <button
          type="button"
          onClick={handleCopy}
          title={isCopied ? 'Copied!' : 'Copy thoughts'}
          className={cn(
            'rounded-lg p-1.5 text-muted-foreground transition-all duration-200',
            isExpanded
              ? 'opacity-0 group-focus-within/thinking-container:opacity-100 group-hover/thinking-container:opacity-100'
              : 'opacity-0',
            'hover:bg-secondary hover:text-foreground',
            'focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
          )}
        >
          {isCopied ? (
            <Check className="h-[18px] w-[18px] text-sage-500" />
          ) : (
            <Clipboard className="h-[18px] w-[18px]" />
          )}
        </button>
      )}
    </div>
  );
});

/**
 * ThinkingContent - Displays the actual thinking/reasoning content
 */
const ThinkingContent = memo(function ThinkingContent({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-xl border border-border/60 bg-secondary/30 p-4">
      <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
        {children}
      </p>
    </div>
  );
});

/**
 * InlineThinking - A collapsible panel for displaying AI reasoning/thinking content.
 *
 * Inspired by LibreChat's Thinking.tsx component with these features:
 * - Grid-based height animation (smoother than max-height)
 * - Sticky header for long content
 * - Icon swap animation (lightbulb → chevron on hover)
 * - Copy button appears on hover when expanded
 *
 * Pattern: :::thinking\n{content}\n:::
 */
export const InlineThinking = memo(function InlineThinking({
  thinkingText,
  defaultExpanded = false,
  className,
  isStreaming = false,
}: InlineThinkingProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // Generate unique ID for accessibility
  const instanceId = useId();
  const contentId = `thinking-content-${instanceId}`;

  const handleToggle = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    setIsExpanded((prev) => !prev);
  }, []);

  // Memoize and sanitize text content - strip :::thinking markers and prefixes
  const textContent = useMemo(() => {
    if (typeof thinkingText !== 'string') {
      return '';
    }
    // Strip :::thinking, ::: markers, and "Model reasoning" prefixes
    let sanitized = thinkingText
      // Remove ALL occurrences of "Model reasoning:::thinking" (not just at start)
      .replace(/(?:Model reasoning)?:::(?:thinking|think)\s*/gi, '')
      // Remove closing ::: markers (at end of lines or string)
      .replace(/\s*:::\s*(?=\n|$)/g, '\n')
      // Remove any remaining standalone ::: markers
      .replace(/(?:^|\n)\s*:::\s*(?=\n|$)/g, '\n')
      // Remove standalone "Model reasoning" prefix (when not followed by :::)
      .replace(/\bModel reasoning\s+(?!:::)/gi, '')
      // Clean up multiple newlines
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    return sanitized;
  }, [thinkingText]);

  // Check sanitized content, not raw input
  if (!textContent || textContent.length === 0) {
    return null;
  }

  return (
    <div className={cn('group/thinking-container mb-4', className)}>
      {/* Sticky header - stays visible when scrolling through long thinking content */}
      <div className="sticky top-0 z-10 mb-2 bg-background/95 backdrop-blur-sm pb-2 pt-2">
        <ThinkingButton
          isExpanded={isExpanded}
          onClick={handleToggle}
          content={textContent}
          contentId={contentId}
          isStreaming={isStreaming}
        />
      </div>

      {/* Collapsible content with grid-based animation (LibreChat pattern)
          - grid-template-rows: 0fr → content collapses smoothly
          - grid-template-rows: 1fr → content expands to auto height
          - This is smoother than max-height because it doesn't need a fixed max value
      */}
      <div
        id={contentId}
        className={cn(
          'grid transition-all duration-300 ease-out',
          isExpanded && 'mb-6'
        )}
        style={{
          gridTemplateRows: isExpanded ? '1fr' : '0fr',
        }}
      >
        <div className="overflow-hidden">
          <ThinkingContent>{textContent}</ThinkingContent>
        </div>
      </div>
    </div>
  );
});

ThinkingButton.displayName = 'ThinkingButton';
ThinkingContent.displayName = 'ThinkingContent';

export default InlineThinking;
