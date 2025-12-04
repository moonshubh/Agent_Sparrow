'use client';

import React, { useMemo, useState, useEffect, useRef, useLayoutEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle2,
  Circle,
  Loader2,
  ListTodo,
  ChevronDown,
  ChevronUp,
  Sparkles,
  AlertCircle,
  Lightbulb,
  Wrench,
  Check,
  Settings2,
  ClipboardList
} from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import type { ToolEvidenceUpdateEvent } from '@/services/ag-ui/event-types';
import './todo-sidebar.css';

/**
 * Custom hook for asymptotic progress animation
 * Progress slows down as it approaches 1, similar to LibreChat's useProgress
 */
function useToolProgress(initialProgress: number, isActive: boolean): number {
  const [progress, setProgress] = useState(initialProgress);
  const prevActiveRef = useRef(isActive);

  useEffect(() => {
    // Cleanup runs before each effect when isActive flips, so returning early still clears prior intervals
    if (!isActive) return;

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 0.99) {
          return prev;
        }
        // Asymptotic approach: progress slows as it nears 1
        const increment = (0.99 - prev) * 0.1;
        return Math.min(prev + increment, 0.99);
      });
    }, 100);

    return () => clearInterval(interval);
  }, [isActive]);

  // Reset when tool starts
  useEffect(() => {
    if (isActive && !prevActiveRef.current) {
      setProgress(initialProgress);
    }
    prevActiveRef.current = isActive;
  }, [isActive, initialProgress]);

  return isActive ? progress : 1;
}

export interface TodoItem {
  id: string;
  title?: string;
  content?: string;
  status?: 'pending' | 'in_progress' | 'done' | 'completed';
  priority?: 'low' | 'medium' | 'high';
  metadata?: Record<string, any>;
}

export interface ActiveTool {
  name: string;
  startTime?: Date;
}

interface TodoSidebarProps {
  todos: TodoItem[];
  isStreaming?: boolean;
  agentLabel?: string;
  statusMessage?: string;
  className?: string;
  /** Run status: idle, running, or error */
  runStatus?: 'idle' | 'running' | 'error';
  /** Currently active focus/operation */
  activeOperationName?: string;
  /** List of currently running tools */
  activeTools?: string[];
  /** Error message if any */
  errorMessage?: string;
  /** Completed tool evidence to mirror LibreChat-style tool call display */
  toolEvidence?: Record<string, ToolEvidenceUpdateEvent>;
}

type StatusConfigItem = {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgColor: string;
  label: string;
  animate?: boolean;
};

const statusConfig: Record<string, StatusConfigItem> = {
  pending: {
    icon: Circle,
    color: 'text-muted-foreground',
    bgColor: 'bg-muted/50',
    label: 'Pending'
  },
  in_progress: {
    icon: Loader2,
    color: 'text-terracotta-400',
    bgColor: 'bg-terracotta-400/10',
    label: 'In Progress',
    animate: true
  },
  done: {
    icon: CheckCircle2,
    color: 'text-sage-500',
    bgColor: 'bg-sage-500/10',
    label: 'Done'
  },
  completed: {
    icon: CheckCircle2,
    color: 'text-sage-500',
    bgColor: 'bg-sage-500/10',
    label: 'Done'
  }
};

type ToolCallItem = {
  id: string;
  name: string;
  status: 'running' | 'done';
  summary?: string;
  args?: string | Record<string, unknown>;
  output?: string;
};

const formatToolName = (name: string): string => {
  return name
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .trim()
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
};

const summarizeToolOutput = (output: unknown): string => {
  if (typeof output === 'string') {
    const trimmed = output.trim();
    return trimmed.length > 140 ? `${trimmed.slice(0, 140)}…` : trimmed;
  }
  if (output && typeof output === 'object') {
    try {
      const text = JSON.stringify(output);
      return text.length > 140 ? `${text.slice(0, 140)}…` : text;
    } catch {
      return '';
    }
  }
  return '';
};

/**
 * TodoSidebar - Lightweight task-focused sidebar
 * 
 * Shows:
 * - Status overview (STATUS, AGENT, FOCUS, TOOLS, TODOS)
 * - Active tool calls with progress indicators
 * - Task list with status indicators
 */
export const TodoSidebar: React.FC<TodoSidebarProps> = ({
  todos,
  isStreaming = false,
  agentLabel = 'Agent',
  statusMessage,
  className,
  runStatus = 'idle',
  activeOperationName,
  activeTools = [],
  errorMessage,
  toolEvidence = {},
}) => {
  const [isTasksExpanded, setIsTasksExpanded] = useState(true);
  const [isToolsExpanded, setIsToolsExpanded] = useState(true);

  // Normalize todos
  const normalizedTodos = useMemo(() => {
    return todos.map(todo => ({
      ...todo,
      title: todo.title || todo.content || 'Task',
      status: ((todo.status || 'pending').toLowerCase() as TodoItem['status'])
    }));
  }, [todos]);

  // Calculate stats
  const stats = useMemo(() => {
    const total = normalizedTodos.length;
    const done = normalizedTodos.filter(t => t.status === 'done' || t.status === 'completed').length;
    const inProgress = normalizedTodos.filter(t => t.status === 'in_progress').length;
    const pending = total - done - inProgress;
    const progressPercent = total > 0 ? Math.round((done / total) * 100) : 0;

    return { total, done, inProgress, pending, progressPercent };
  }, [normalizedTodos]);

  // Sort todos: in_progress first, then pending, then done
  const sortedTodos = useMemo(() => {
    const statusOrder = { in_progress: 0, pending: 1, done: 2, completed: 2 };
    return [...normalizedTodos].sort((a, b) => {
      const orderA = statusOrder[a.status || 'pending'] ?? 1;
      const orderB = statusOrder[b.status || 'pending'] ?? 1;
      return orderA - orderB;
    });
  }, [normalizedTodos]);

  // Build tool call list: running tools + recent completed tool calls from evidence
  const toolCallItems = useMemo(() => {
    const items: ToolCallItem[] = [];
    const seen = new Set<string>();

    activeTools.forEach((name, idx) => {
      const id = `running-${idx}-${name}`;
      if (seen.has(id)) return;
      seen.add(id);
      items.push({
        id,
        name,
        status: 'running',
        summary: 'Processing...',
      });
    });

    // Recent evidence (most recent first)
    const entries = Object.entries(toolEvidence || {}).slice(-6).reverse();
    entries.forEach(([id, evidence]) => {
      if (!evidence || seen.has(id)) return;
      seen.add(id);
      const name = evidence.toolName || id || 'tool';
      const summary = summarizeToolOutput(evidence.summary ?? evidence.output);
      // Format output for display (tool evidence doesn't include args)
      let output: string | undefined;
      if (evidence.output) {
        output = typeof evidence.output === 'string'
          ? evidence.output
          : JSON.stringify(evidence.output, null, 2);
      }
      items.push({
        id,
        name,
        status: 'done',
        summary,
        output,
      });
    });

    return items;
  }, [activeTools, toolEvidence]);

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {/* Status Overview Section - Like EnhancedReasoningPanel status pills */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 bg-secondary/30 border-b border-border">
          <div className="p-1.5 rounded-lg bg-yellow-500/10">
            <Lightbulb className="w-4 h-4 text-yellow-500 animate-spin-slow bulb-glow" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Agent Status</h3>
          </div>
        </div>

        {/* Status Pills Grid */}
        <div className="p-3 space-y-2">
          <StatusPill
            label="STATUS"
            value={runStatus === 'running' ? 'Running' : runStatus === 'error' ? 'Error' : 'Idle'}
            variant={runStatus}
          />
          <StatusPill
            label="AGENT"
            value={agentLabel}
            variant="idle"
          />
          <StatusPill
            label="FOCUS"
            value={activeOperationName || 'Standing by'}
            variant={activeOperationName ? 'running' : 'idle'}
          />
          <StatusPill
            label="TOOLS"
            value={activeTools.length > 0
              ? `${activeTools.length} running`
              : 'No tools running'
            }
            variant={activeTools.length > 0 ? 'running' : 'idle'}
          />
          <StatusPill
            label="TODOS"
            value={stats.total === 0
              ? 'None'
              : `${stats.total} (${stats.inProgress} doing, ${stats.pending} pending)`
            }
            variant={stats.inProgress > 0 ? 'running' : 'idle'}
          />
        </div>

        {/* Error Message */}
        {errorMessage && (
          <div className="mx-3 mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
            <div className="flex items-center gap-2 text-red-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span className="text-xs">{errorMessage}</span>
            </div>
          </div>
        )}
      </div>

      {/* Tool Calls Section - LibreChat-inspired tool progress */}
      {toolCallItems.length > 0 && (
        <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
          <div
            className="flex items-center justify-between px-4 py-2.5 bg-secondary/30 border-b border-border cursor-pointer hover:bg-secondary/50 transition-colors"
            onClick={() => setIsToolsExpanded(!isToolsExpanded)}
          >
            <div className="flex items-center gap-2">
              <Settings2 className="w-4 h-4 text-amber-500 icon-glow" />
              <span className="text-sm font-medium text-foreground">Tool Calls</span>
              <span className="px-1.5 py-0.5 text-[10px] rounded-full bg-amber-500/20 text-amber-500">
                {toolCallItems.length}
              </span>
            </div>
            {isToolsExpanded ? (
              <ChevronUp className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            )}
          </div>

          <AnimatePresence>
            {isToolsExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="p-2 space-y-1">
                  {toolCallItems.map((tool) => (
                    <ToolCallRow key={tool.id} tool={tool} />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Tasks Section */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        <div
          className="flex items-center justify-between px-4 py-2.5 bg-secondary/30 border-b border-border cursor-pointer hover:bg-secondary/50 transition-colors"
          onClick={() => setIsTasksExpanded(!isTasksExpanded)}
        >
          <div className="flex items-center gap-2">
            <ListTodo className="w-4 h-4 text-sage-500" />
            <span className="text-sm font-medium text-foreground">Tasks</span>
            {stats.total > 0 && (
              <span className="text-xs text-muted-foreground">
                {stats.done}/{stats.total}
              </span>
            )}
          </div>
          {isTasksExpanded ? (
            <ChevronUp className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          )}
        </div>

        {/* Progress Bar */}
        {stats.total > 0 && (
          <div className="px-3 py-2 bg-background/50">
            <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-terracotta-400 to-sage-500 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${stats.progressPercent}%` }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
              />
            </div>
          </div>
        )}

        <AnimatePresence>
          {isTasksExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="p-2 space-y-1 max-h-[300px] overflow-y-auto custom-scrollbar">
                {sortedTodos.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <ClipboardList className="w-5 h-5 text-muted-foreground mb-2 animate-pulse-slow" />
                    <p className="text-xs text-muted-foreground">No tasks yet</p>
                  </div>
                ) : (
                  sortedTodos.map((todo, index) => (
                    <TodoItemRow key={todo.id || index} todo={todo} index={index} />
                  ))
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

const TodoItemRow: React.FC<{ todo: TodoItem; index: number }> = ({ todo, index }) => {
  const status = todo.status || 'pending';
  const config = statusConfig[status] || statusConfig.pending;
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03 }}
      className={cn(
        'flex items-start gap-2.5 px-3 py-2 rounded-lg transition-colors',
        config.bgColor,
        status === 'in_progress' && 'ring-1 ring-terracotta-400/30'
      )}
    >
      <div className={cn('mt-0.5 flex-shrink-0', config.color)}>
        <Icon className={cn('w-4 h-4', config.animate && 'animate-spin')} />
      </div>
      <div className="flex-1 min-w-0">
        <p className={cn(
          'text-sm leading-snug',
          status === 'done' || status === 'completed'
            ? 'text-muted-foreground line-through'
            : 'text-foreground'
        )}>
          {todo.title}
        </p>
        {todo.metadata?.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
            {todo.metadata.description}
          </p>
        )}
      </div>
      {todo.priority === 'high' && (
        <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
      )}
    </motion.div>
  );
};

/**
 * StatusPill - Displays a labeled status value (like EnhancedReasoningPanel)
 */
const StatusPill: React.FC<{
  label: string;
  value: string;
  variant?: 'idle' | 'running' | 'error';
}> = ({ label, value, variant = 'idle' }) => {
  const variantClasses = {
    idle: 'bg-secondary/70 text-muted-foreground',
    running: 'bg-terracotta-400/10 text-terracotta-400 border-terracotta-400/20',
    error: 'bg-red-500/10 text-red-400 border-red-500/20'
  };

  return (
    <div className={cn(
      'flex items-center justify-between px-3 py-1.5 rounded-lg border border-transparent',
      variantClasses[variant]
    )}>
      <span className="text-[10px] font-semibold uppercase tracking-wider opacity-70">
        {label}
      </span>
      <span className={cn(
        'text-xs font-medium',
        variant === 'running' && 'shimmer-text'
      )}>
        {value}
      </span>
    </div>
  );
};

/**
 * ToolCallRow - Shows running and completed tool calls (LibreChat-inspired)
 *
 * Features:
 * - Asymptotic progress animation for running tools
 * - Expandable details panel with smooth height transition
 * - ResizeObserver for dynamic content height
 */
const ToolCallRow: React.FC<{ tool: ToolCallItem }> = ({ tool }) => {
  const displayName = formatToolName(tool.name || 'Tool');
  const isRunning = tool.status === 'running';
  const hasDetails = Boolean(tool.args || tool.output || tool.summary);

  // State for expandable details
  const [showDetails, setShowDetails] = useState(false);
  const [contentHeight, setContentHeight] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const prevShowDetailsRef = useRef(showDetails);

  // Progress animation for running tools
  const progress = useToolProgress(0.1, isRunning);

  // Handle expand/collapse with smooth animation (LibreChat pattern)
  useLayoutEffect(() => {
    if (showDetails !== prevShowDetailsRef.current) {
      prevShowDetailsRef.current = showDetails;
      setIsAnimating(true);

      if (showDetails && contentRef.current) {
        requestAnimationFrame(() => {
          if (contentRef.current) {
            const height = contentRef.current.scrollHeight;
            setContentHeight(height + 4);
          }
        });
      } else {
        setContentHeight(0);
      }

      const timer = setTimeout(() => {
        setIsAnimating(false);
      }, 400);

      return () => clearTimeout(timer);
    }
  }, [showDetails]);

  // ResizeObserver for dynamic content changes
  useEffect(() => {
    if (!contentRef.current) return;

    const resizeObserver = new ResizeObserver((entries) => {
      if (showDetails && !isAnimating) {
        for (const entry of entries) {
          if (entry.target === contentRef.current) {
            setContentHeight(entry.contentRect.height + 4);
          }
        }
      }
    });

    resizeObserver.observe(contentRef.current);
    return () => resizeObserver.disconnect();
  }, [showDetails, isAnimating]);

  const progressPercent = Math.round(progress * 100);

  return (
    <div className="relative">
      {/* Main row - clickable when details available */}
      <div
        className={cn(
          'flex items-center gap-2.5 px-3 py-2 rounded-lg border transition-all',
          isRunning
            ? 'bg-terracotta-400/5 border-terracotta-400/15'
            : 'bg-secondary/40 border-border',
          hasDetails && 'cursor-pointer hover:bg-secondary/60'
        )}
        onClick={hasDetails ? () => setShowDetails(!showDetails) : undefined}
      >
        {/* Progress icon */}
        <div className="relative flex-shrink-0">
          {isRunning ? (
            <div className="relative">
              <Loader2 className="w-4 h-4 text-terracotta-400 animate-spin" />
              {/* Progress ring overlay */}
              <svg
                className="absolute inset-0 w-4 h-4 -rotate-90"
                viewBox="0 0 16 16"
              >
                <circle
                  cx="8"
                  cy="8"
                  r="6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeDasharray={`${progress * 37.7} 37.7`}
                  className="text-terracotta-400/30"
                />
              </svg>
            </div>
          ) : (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            >
              <Check className="w-4 h-4 text-sage-500" />
            </motion.div>
          )}
        </div>

        {/* Tool name and progress text */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className={cn(
              'text-xs font-medium leading-snug truncate',
              isRunning ? 'shimmer-text text-terracotta-400' : 'text-foreground'
            )}>
              {isRunning ? `Running ${displayName}...` : displayName}
            </p>
            {isRunning && (
              <span className="text-[10px] text-terracotta-400/70">
                {progressPercent}%
              </span>
            )}
          </div>
          {!showDetails && tool.summary && !isRunning && (
            <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
              {tool.summary}
            </p>
          )}
        </div>

        {/* Expand chevron when details available */}
        {hasDetails && (
          <div className="flex-shrink-0">
            {showDetails ? (
              <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            )}
          </div>
        )}
      </div>

      {/* Expandable details panel */}
      <div
        className="relative overflow-hidden"
        style={{
          height: showDetails ? contentHeight : 0,
          transition: 'height 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
          opacity: showDetails ? 1 : 0,
        }}
      >
        <div
          ref={contentRef}
          className={cn(
            'mt-2 rounded-lg border bg-secondary/30 p-2 text-xs',
            showDetails ? 'border-border' : 'border-transparent'
          )}
          style={{
            transform: showDetails ? 'translateY(0) scale(1)' : 'translateY(-8px) scale(0.98)',
            transition: 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        >
          {tool.args && (
            <div className="mb-2">
              <span className="text-[10px] uppercase text-muted-foreground font-semibold tracking-wider">
                Input
              </span>
              <pre className="mt-1 whitespace-pre-wrap break-all text-[11px] text-foreground/80 max-h-24 overflow-y-auto">
                {typeof tool.args === 'string' ? tool.args : JSON.stringify(tool.args, null, 2)}
              </pre>
            </div>
          )}
          {(tool.output || tool.summary) && (
            <div>
              <span className="text-[10px] uppercase text-muted-foreground font-semibold tracking-wider">
                Output
              </span>
              <pre className="mt-1 whitespace-pre-wrap break-all text-[11px] text-foreground/80 max-h-32 overflow-y-auto">
                {tool.output || tool.summary}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TodoSidebar;
