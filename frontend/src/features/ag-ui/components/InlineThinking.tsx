'use client';

import React, { useState, useCallback, memo, useId } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lightbulb, ChevronDown } from 'lucide-react';
import { CopyCodeButton } from './CopyCodeButton';
import { cn } from '@/shared/lib/utils';

interface InlineThinkingProps {
  /** The thinking/reasoning text content */
  thinkingText: string;
  /** Whether to start expanded (default: false) */
  defaultExpanded?: boolean;
  /** Additional CSS classes for the container */
  className?: string;
}

/**
 * InlineThinking - A collapsible panel for displaying AI reasoning/thinking content.
 * 
 * Inspired by LibreChat's Thinking.tsx component. Displays a toggleable section
 * with a lightbulb icon that expands to show the model's reasoning process.
 * 
 * Pattern: :::thinking\n{content}\n:::
 */
export const InlineThinking = memo(function InlineThinking({
  thinkingText,
  defaultExpanded = false,
  className,
}: InlineThinkingProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // Generate unique ID for accessibility (Issue #2: avoid duplicate IDs)
  const instanceId = useId();
  const contentId = `thinking-content-${instanceId}`;

  const handleToggle = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    setIsExpanded((prev) => !prev);
  }, []);

  if (!thinkingText || thinkingText.trim().length === 0) {
    return null;
  }

  return (
    <div className={cn('group/thinking-container mb-4', className)}>
      {/* Header with toggle button */}
      <div className="sticky top-0 z-10 flex items-center justify-between bg-background/95 backdrop-blur-sm py-2">
        <button
          type="button"
          onClick={handleToggle}
          className={cn(
            'group/button flex flex-1 items-center gap-2 rounded-lg py-1 pr-2',
            'text-sm font-medium text-muted-foreground',
            'hover:text-foreground transition-colors duration-200'
          )}
          aria-expanded={isExpanded}
          aria-controls={contentId}
        >
          {/* Icon container with hover swap animation */}
          <span className="relative inline-flex h-5 w-5 items-center justify-center">
            <Lightbulb 
              className={cn(
                'h-4 w-4 absolute text-gold-400 transition-opacity duration-200',
                'group-hover/button:opacity-0'
              )} 
            />
            <ChevronDown
              className={cn(
                'h-4 w-4 absolute text-foreground opacity-0 transition-all duration-200',
                'group-hover/button:opacity-100',
                isExpanded && 'rotate-180'
              )}
            />
          </span>
          <span className="text-sm">Thoughts</span>
        </button>
        
        {/* Copy button - visible on hover when expanded */}
        <div
          className={cn(
            'transition-opacity duration-200',
            isExpanded ? 'opacity-0 group-hover/thinking-container:opacity-100' : 'opacity-0'
          )}
        >
          <CopyCodeButton text={thinkingText} size="sm" />
        </div>
      </div>

      {/* Collapsible content with animation */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            id={contentId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ 
              duration: 0.25, 
              ease: [0.4, 0, 0.2, 1] 
            }}
            className="overflow-hidden"
          >
            <div className={cn(
              'rounded-xl border border-border/60 bg-secondary/30',
              'p-4 mt-2 mb-4'
            )}>
              <p className={cn(
                'text-sm text-muted-foreground leading-relaxed',
                'whitespace-pre-wrap'
              )}>
                {thinkingText}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

export default InlineThinking;
