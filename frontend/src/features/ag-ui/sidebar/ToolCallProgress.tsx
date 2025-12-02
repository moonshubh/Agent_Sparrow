'use client';

import React, { useState, useCallback, useRef, useEffect, memo, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Loader2, Check, X } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import './sidebar.css';

interface ToolCallProgressProps {
  name: string;
  status: 'running' | 'complete' | 'cancelled' | 'error';
  args?: string | Record<string, unknown>;
  output?: string | null;
  duration?: number;
}

/**
 * FinishedIcon - Green checkmark for completed tools
 */
const FinishedIcon = memo(function FinishedIcon() {
  return (
    <div className="w-5 h-5 rounded-full bg-sage-500/20 flex items-center justify-center">
      <Check className="w-3 h-3 text-sage-500" />
    </div>
  );
});

/**
 * CancelledIcon - X icon for cancelled/error tools
 */
const CancelledIcon = memo(function CancelledIcon() {
  return (
    <div className="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center">
      <X className="w-3 h-3 text-red-400" />
    </div>
  );
});

/**
 * RunningIcon - Animated spinner for running tools
 */
const RunningIcon = memo(function RunningIcon() {
  return (
    <div className="w-5 h-5 flex items-center justify-center">
      <Loader2 className="w-4 h-4 text-terracotta-400 animate-spin" />
    </div>
  );
});

/**
 * ToolCallProgress - LibreChat-style tool call with progress indicator
 *
 * Features:
 * - Shimmer text when running
 * - Collapsible input/output display
 * - Status icons (running, complete, cancelled)
 * - Smooth spring animations
 */
export const ToolCallProgress = memo(function ToolCallProgress({
  name,
  status,
  args,
  output,
  duration,
}: ToolCallProgressProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [contentHeight, setContentHeight] = useState<number>(0);
  const contentRef = useRef<HTMLDivElement>(null);

  // Format the tool name for display
  const displayName = useMemo(() => {
    return name
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .trim()
      .toLowerCase()
      .replace(/^\w/, c => c.toUpperCase());
  }, [name]);

  // Format args for display
  const formattedArgs = useMemo(() => {
    if (!args) return null;
    if (typeof args === 'string') return args;
    try {
      return JSON.stringify(args, null, 2);
    } catch {
      return String(args);
    }
  }, [args]);

  // Check if there's content to show
  const hasContent = formattedArgs || output;

  // Get status text
  const getStatusText = useCallback(() => {
    switch (status) {
      case 'running':
        return `Running ${displayName}...`;
      case 'complete':
        return `Completed ${displayName}${duration ? ` (${(duration / 1000).toFixed(1)}s)` : ''}`;
      case 'cancelled':
        return 'Cancelled';
      case 'error':
        return 'Error';
      default:
        return displayName;
    }
  }, [status, displayName, duration]);

  // Get icon based on status
  const StatusIcon = useMemo(() => {
    switch (status) {
      case 'running':
        return RunningIcon;
      case 'complete':
        return FinishedIcon;
      case 'cancelled':
      case 'error':
        return CancelledIcon;
      default:
        return RunningIcon;
    }
  }, [status]);

  // Update content height for animation
  useEffect(() => {
    if (contentRef.current && isExpanded) {
      const height = contentRef.current.scrollHeight;
      setContentHeight(height + 8); // Add padding
    } else {
      setContentHeight(0);
    }
  }, [isExpanded, formattedArgs, output]);

  // Resize observer for dynamic content
  useEffect(() => {
    if (!contentRef.current || !isExpanded) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === contentRef.current) {
          setContentHeight(entry.contentRect.height + 8);
        }
      }
    });

    resizeObserver.observe(contentRef.current);
    return () => resizeObserver.disconnect();
  }, [isExpanded]);

  const toggleExpanded = useCallback(() => {
    if (hasContent) {
      setIsExpanded(prev => !prev);
    }
  }, [hasContent]);

  return (
    <div className="mb-2">
      {/* Progress Row */}
      <div className="flex items-center gap-2.5 h-6">
        <button
          type="button"
          onClick={toggleExpanded}
          disabled={!hasContent}
          className={cn(
            'inline-flex w-full items-center gap-2',
            hasContent ? 'cursor-pointer' : 'cursor-default'
          )}
        >
          <StatusIcon />
          <span className={cn(
            'text-sm text-muted-foreground flex-1 text-left truncate',
            status === 'running' && 'shimmer-text'
          )}>
            {getStatusText()}
          </span>
          {hasContent && (
            isExpanded ? (
              <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" />
            ) : (
              <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
            )
          )}
        </button>
      </div>

      {/* Expandable Content */}
      <AnimatePresence>
        {isExpanded && hasContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{
              height: contentHeight,
              opacity: 1,
              transition: {
                height: { duration: 0.4, ease: [0.16, 1, 0.3, 1] },
                opacity: { duration: 0.3, delay: 0.1 }
              }
            }}
            exit={{
              height: 0,
              opacity: 0,
              transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] }
            }}
            className="overflow-hidden"
          >
            <div
              ref={contentRef}
              className={cn(
                'mt-2 rounded-xl border border-border/60 bg-secondary/30',
                'overflow-hidden shadow-sm'
              )}
            >
              {/* Input Section */}
              {formattedArgs && (
                <div className="px-3 py-2 border-b border-border/40">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground/70 mb-1">
                    Input
                  </div>
                  <pre className="text-xs text-foreground/80 overflow-x-auto max-h-32 overflow-y-auto">
                    {formattedArgs}
                  </pre>
                </div>
              )}

              {/* Output Section */}
              {output && (
                <div className="px-3 py-2">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground/70 mb-1">
                    Output
                  </div>
                  <pre className="text-xs text-foreground/80 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {typeof output === 'string' && output.length > 1000
                      ? `${output.slice(0, 1000)}...`
                      : output}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

export default ToolCallProgress;
