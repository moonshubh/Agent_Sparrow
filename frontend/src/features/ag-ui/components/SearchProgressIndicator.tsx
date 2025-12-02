'use client';

import React, { useState, useEffect, useRef } from 'react';
import './shimmer.css';
import { motion, AnimatePresence } from 'framer-motion';
import { Globe, Check, AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/shared/lib/utils';

interface SearchSource {
  url: string;
  title?: string;
  favicon?: string;
  domain?: string;
}

interface SearchProgressIndicatorProps {
  /** Whether the search is currently in progress */
  isSearching: boolean;
  /** Current progress (0-1), auto-animates if not provided */
  progress?: number;
  /** Phase of the search operation */
  phase?: 'searching' | 'reading' | 'processing' | 'complete' | 'error';
  /** Sources being processed (for stacked favicon display) */
  sources?: SearchSource[];
  /** Error message if phase is 'error' */
  errorMessage?: string;
  /** Whether this is a subsequent search in the same turn */
  isFollowUp?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Custom hook for asymptotic progress animation
 * Progress slows down as it approaches 1, similar to LibreChat
 */
function useProgress(initialProgress: number, isActive: boolean): number {
  const [progress, setProgress] = useState(initialProgress);
  const prevActiveRef = useRef(isActive);

  useEffect(() => {
    if (!isActive) return;

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 0.99) {
          return prev;
        }
        // Asymptotic approach: progress slows as it nears 1
        const increment = (0.99 - prev) * 0.08;
        return Math.min(prev + increment, 0.99);
      });
    }, 150);

    return () => clearInterval(interval);
  }, [isActive]);

  // Reset on new search
  useEffect(() => {
    // Reset when activation toggles from false -> true
    if (isActive && !prevActiveRef.current) {
      setProgress(initialProgress);
    }
    prevActiveRef.current = isActive;
  }, [isActive, initialProgress]);

  return progress;
}

/**
 * Extract clean domain from URL
 */
function getCleanDomain(url: string): string {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.replace('www.', '');
  } catch {
    return url;
  }
}

/**
 * Stacked favicon display component
 * Shows overlapping favicon images for multiple sources
 */
function FaviconImage({ faviconUrl, domain }: { faviconUrl: string; domain: string }) {
  const [hasError, setHasError] = useState(false);

  if (hasError) {
    return (
      <div
        className="flex h-full w-full items-center justify-center text-muted-foreground"
        role="img"
        aria-label={`Favicon for ${domain}`}
      >
        <Globe className="h-3.5 w-3.5" aria-hidden />
      </div>
    );
  }

  return (
    <img
      src={faviconUrl}
      alt={domain}
      className="h-full w-full object-contain"
      onError={() => setHasError(true)}
    />
  );
}

function StackedFavicons({ sources, maxVisible = 3 }: { sources: SearchSource[]; maxVisible?: number }) {
  const visibleSources = sources.slice(0, maxVisible);

  return (
    <div className="relative flex items-center">
      {visibleSources.map((source, i) => {
        const domain = source.domain || getCleanDomain(source.url);
        const faviconUrl = source.favicon || `https://www.google.com/s2/favicons?domain=${domain}&sz=32`;

        return (
          <div
            key={`favicon-${source.url}`}
            className={cn(
              'relative h-5 w-5 rounded-full border-2 border-background bg-secondary overflow-hidden',
              i > 0 && '-ml-2'
            )}
            style={{ zIndex: maxVisible - i }}
          >
            <FaviconImage faviconUrl={faviconUrl} domain={domain} />
          </div>
        );
      })}
      {sources.length > maxVisible && (
        <div className="-ml-2 flex h-5 w-5 items-center justify-center rounded-full border-2 border-background bg-secondary text-[10px] font-medium text-muted-foreground">
          +{sources.length - maxVisible}
        </div>
      )}
    </div>
  );
}

/**
 * Progress indicator icon with state transitions
 */
function ProgressIcon({ phase, progress }: { phase: string; progress: number }) {
  if (phase === 'error') {
    return <AlertCircle className="h-4 w-4 text-destructive" />;
  }

  if (phase === 'complete' || progress >= 1) {
    return (
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      >
        <Check className="h-4 w-4 text-sage-500" />
      </motion.div>
    );
  }

  return (
    <Loader2 className="h-4 w-4 animate-spin text-terracotta-400" />
  );
}

/**
 * Get phase-appropriate text
 */
function getPhaseText(phase: string, isFollowUp: boolean): string {
  switch (phase) {
    case 'searching':
      return isFollowUp ? 'Searching again...' : 'Searching the web...';
    case 'reading':
      return 'Reading sources...';
    case 'processing':
      return 'Processing results...';
    case 'complete':
      return 'Search complete';
    case 'error':
      return 'Search failed';
    default:
      return 'Searching...';
  }
}

/**
 * SearchProgressIndicator - Shows web search progress with stacked favicons
 *
 * Inspired by LibreChat's WebSearch.tsx and ProgressText.tsx patterns:
 * - Multi-phase progress display
 * - Asymptotic progress animation
 * - Stacked favicon display for sources
 * - Shimmer effect during search
 */
export function SearchProgressIndicator({
  isSearching,
  progress: externalProgress,
  phase = 'searching',
  sources = [],
  errorMessage,
  isFollowUp = false,
  className,
}: SearchProgressIndicatorProps) {
  // Use external progress if provided, otherwise animate
  const animatedProgress = useProgress(externalProgress ?? 0.1, isSearching);
  const progress = externalProgress ?? animatedProgress;

  // Determine visibility
  const isComplete = phase === 'complete' || (!isSearching && progress >= 1);
  const isCancelled = !isSearching && progress < 1 && phase !== 'complete';
  const showShimmer = isSearching && progress < 1 && phase !== 'error';

  const phaseText = phase === 'error' && errorMessage ? errorMessage : getPhaseText(phase, isFollowUp);
  const shouldShow = (!isComplete || phase === 'error') && (!isCancelled || phase === 'error');

  return (
    <AnimatePresence>
      {shouldShow && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
          className={cn(
            'flex items-center gap-2.5 my-2.5',
            className
          )}
        >
          {/* Stacked favicons when sources are available */}
          {sources.length > 0 && (
            <div className="mr-1">
              <StackedFavicons sources={sources} />
            </div>
          )}

          {/* Progress indicator with icon */}
          <div className="relative flex items-center gap-2">
            <ProgressIcon phase={phase} progress={progress} />

            {/* Progress text with shimmer effect */}
            <span
              className={cn(
                'text-sm text-muted-foreground whitespace-nowrap',
                showShimmer && 'shimmer'
              )}
            >
              {phaseText}
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * CSS for shimmer effect (should be in globals.css or todo-sidebar.css)
 *
 * .shimmer {
 *   background: linear-gradient(
 *     90deg,
 *     currentColor 0%,
 *     color-mix(in srgb, currentColor 50%, transparent) 50%,
 *     currentColor 100%
 *   );
 *   background-size: 200% 100%;
 *   -webkit-background-clip: text;
 *   background-clip: text;
 *   -webkit-text-fill-color: transparent;
 *   animation: shimmer 1.5s ease-in-out infinite;
 * }
 *
 * @keyframes shimmer {
 *   0% { background-position: 100% 0; }
 *   100% { background-position: -100% 0; }
 * }
 */

export default SearchProgressIndicator;
