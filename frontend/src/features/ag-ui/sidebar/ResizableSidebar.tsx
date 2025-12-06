'use client';

import React, { useState, useCallback, useEffect, useRef, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import { safeGetItem, safeParseJSON, safeSetItem } from '../utils';

interface ResizableSidebarProps {
  children: React.ReactNode;
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  storageKey?: string;
  className?: string;
  /** Callback when sidebar visibility changes */
  onVisibilityChange?: (visible: boolean) => void;
  /** Controlled collapse state */
  collapsed?: boolean;
  /** Callback for collapse toggle */
  onCollapse?: (collapsed: boolean) => void;
  /** Whether to hide the built-in collapse trigger */
  hideTrigger?: boolean;
}

/**
 * ResizableSidebar - A sidebar that can be resized by dragging and collapsed
 *
 * Features:
 * - Drag to resize from left edge
 * - Collapse/expand button
 * - Persists width preference to localStorage
 * - Smooth animations
 */
export const ResizableSidebar = memo(function ResizableSidebar({
  children,
  defaultWidth = 360,
  minWidth = 280,
  maxWidth = 500,
  storageKey = 'agent-sparrow-sidebar-width',
  className,
  onVisibilityChange,
  collapsed,
  onCollapse,
  hideTrigger = false,
}: ResizableSidebarProps) {
  const loadPersistedState = useCallback((): { width: number; collapsed: boolean } => {
    const parsed = safeParseJSON<{ width?: number; collapsed?: boolean }>(
      safeGetItem(storageKey),
      {}
    );
    return {
      width: typeof parsed.width === 'number' ? parsed.width : defaultWidth,
      collapsed: parsed.collapsed === true,
    };
  }, [defaultWidth, storageKey]);

  // Load persisted state
  const [width, setWidth] = useState(() => loadPersistedState().width);

  const [internalCollapsed, setInternalCollapsed] = useState(() => loadPersistedState().collapsed);

  const isCollapsed = collapsed !== undefined ? collapsed : internalCollapsed;

  const [isDragging, setIsDragging] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef<number>(0);
  const startWidthRef = useRef<number>(0);

  // Persist state to localStorage
  useEffect(() => {
    const timeout = setTimeout(() => {
      try {
        safeSetItem(storageKey, JSON.stringify({ width, collapsed: isCollapsed }));
      } catch (err) {
        console.warn('Failed to persist sidebar state', { storageKey, width, isCollapsed, error: err });
      }
    }, 300);
    return () => clearTimeout(timeout);
  }, [width, isCollapsed, storageKey]);

  // Notify parent of visibility changes
  useEffect(() => {
    onVisibilityChange?.(!isCollapsed);
  }, [isCollapsed, onVisibilityChange]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    startXRef.current = e.clientX;
    startWidthRef.current = width;
  }, [width]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;

    const delta = startXRef.current - e.clientX;
    const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidthRef.current + delta));
    setWidth(newWidth);
  }, [isDragging, minWidth, maxWidth]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Add/remove global mouse event listeners for dragging
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  const toggleCollapse = useCallback(() => {
    const newState = !isCollapsed;
    setInternalCollapsed(newState);
    onCollapse?.(newState);
  }, [isCollapsed, onCollapse]);

  return (
    <div className={cn("relative flex", isCollapsed && "w-0 pointer-events-none")}>
      {/* Collapse/Expand Button - Conditionally visible */}
      {!hideTrigger && (
        <button
          onClick={toggleCollapse}
          className={cn(
            'absolute z-20 p-1.5 rounded-lg transition-all duration-200',
            'bg-secondary/80 hover:bg-secondary border border-border/50',
            'text-muted-foreground hover:text-foreground',
            'shadow-sm hover:shadow-md',
            isCollapsed
              ? 'left-[-44px] top-4'
              : 'left-2 top-4'
          )}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!isCollapsed}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <PanelRightOpen className="w-4 h-4" />
          ) : (
            <PanelRightClose className="w-4 h-4" />
          )}
        </button>
      )}

      <AnimatePresence mode="wait">
        {!isCollapsed && (
          <motion.div
            ref={sidebarRef}
            initial={{ width: 0, opacity: 0 }}
            animate={{
              width,
              opacity: 1,
              transition: {
                width: { duration: isDragging ? 0 : 0.2, ease: 'easeInOut' },
                opacity: { duration: 0.15 }
              }
            }}
            exit={{
              width: 0,
              opacity: 0,
              transition: { duration: 0.2, ease: 'easeInOut' }
            }}
            className={cn(
              'relative flex flex-col overflow-hidden',
              'border-l border-border bg-sidebar',
              isDragging && 'will-change-[width]',
              className
            )}
            style={{
              minWidth: isCollapsed ? 0 : minWidth,
              maxWidth: maxWidth
            }}
          >
            {/* Resize Handle */}
            <div
              onMouseDown={handleMouseDown}
              className={cn(
                'absolute left-0 top-0 bottom-0 w-1 cursor-col-resize z-10',
                'hover:bg-terracotta-400/50 transition-colors duration-150',
                isDragging && 'bg-terracotta-400/70'
              )}
              role="separator"
              aria-orientation="vertical"
              aria-valuenow={width}
              aria-valuemin={minWidth}
              aria-valuemax={maxWidth}
            />

            {/* Sidebar Content */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

export default ResizableSidebar;
