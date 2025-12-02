'use client';

import React, { memo, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Lightbulb, AlertCircle } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import { ToolCallProgress } from './ToolCallProgress';
import { TaskList, type TaskItem } from './TaskList';
import './sidebar.css';

export interface ToolCallData {
  id: string;
  name: string;
  status: 'running' | 'complete' | 'cancelled' | 'error';
  args?: string | Record<string, unknown>;
  output?: string | null;
  duration?: number;
}

interface SidebarContentProps {
  /** Currently active/running tools */
  activeTools: ToolCallData[];
  /** Todo/task list */
  todos: TaskItem[];
  /** Whether the agent is currently streaming */
  isStreaming: boolean;
  /** Thinking content from the agent (:::thinking blocks or reasoning) */
  thinkingContent?: string;
  /** Current agent name */
  agentLabel?: string;
  /** Current operation name */
  activeOperationName?: string;
  /** Error message if any */
  errorMessage?: string;
  /** Run status */
  runStatus?: 'idle' | 'running' | 'error';
}

/**
 * SidebarContent - Orchestrates sidebar sections
 *
 * Layout:
 * 1. Status indicator (minimal)
 * 2. Thinking display (if available)
 * 3. Tool calls (inline, collapsible)
 * 4. Task list
 */
export const SidebarContent = memo(function SidebarContent({
  activeTools,
  todos,
  isStreaming,
  thinkingContent,
  agentLabel = 'Agent',
  activeOperationName,
  errorMessage,
  runStatus = 'idle',
}: SidebarContentProps) {
  // Filter tools by status for different displays
  const runningTools = useMemo(
    () => activeTools.filter(t => t.status === 'running'),
    [activeTools]
  );

  const completedTools = useMemo(
    () => activeTools.filter(t => t.status === 'complete' || t.status === 'cancelled' || t.status === 'error'),
    [activeTools]
  );

  const isActive = runStatus === 'running' || isStreaming || runningTools.length > 0;

  return (
    <div className="p-4 space-y-4 relative z-10 paper-texture">
      {/* Minimal Status Indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isActive ? (
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="relative"
            >
              <Loader2 className="w-4 h-4 text-terracotta-400 animate-spin" />
              <div className="absolute inset-0 w-4 h-4 rounded-full tool-active-pulse" />
            </motion.div>
          ) : (
            <div className="w-2 h-2 rounded-full bg-sage-500/50" />
          )}
          <span className="text-xs text-muted-foreground">
            {isActive ? (activeOperationName || 'Working...') : 'Ready'}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground/70 uppercase tracking-wider">
          {agentLabel}
        </span>
      </div>

      {/* Error Display */}
      <AnimatePresence>
        {errorMessage && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20"
          >
            <div className="flex items-center gap-2 text-red-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span className="text-xs">{errorMessage}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Thinking Display */}
      <AnimatePresence>
        {thinkingContent && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="sidebar-section">
              <div className="flex items-center gap-2 px-3 py-2 bg-gold-400/5 border-b border-border/40">
                <Lightbulb className="w-4 h-4 text-gold-400" />
                <span className="text-xs font-medium text-foreground">Thoughts</span>
              </div>
              <div className="p-3 max-h-48 overflow-y-auto custom-scrollbar">
                <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                  {thinkingContent}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Running Tool Calls */}
      <AnimatePresence mode="popLayout">
        {runningTools.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-1"
          >
            {runningTools.map(tool => (
              <ToolCallProgress
                key={tool.id}
                name={tool.name}
                status={tool.status}
                args={tool.args}
                output={tool.output}
                duration={tool.duration}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Completed Tool Calls (collapsed by default, showing count) */}
      {completedTools.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 px-1 mb-1">
            Recent Tools ({completedTools.length})
          </div>
          {completedTools.slice(0, 5).map(tool => (
            <ToolCallProgress
              key={tool.id}
              name={tool.name}
              status={tool.status}
              args={tool.args}
              output={tool.output}
              duration={tool.duration}
            />
          ))}
          {completedTools.length > 5 && (
            <p className="text-[10px] text-muted-foreground/50 px-1">
              +{completedTools.length - 5} more
            </p>
          )}
        </div>
      )}

      {/* Task List */}
      <TaskList todos={todos} />

      {/* Empty State */}
      {!isActive && todos.length === 0 && activeTools.length === 0 && !thinkingContent && !errorMessage && (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <p className="text-xs text-muted-foreground/50">
            Activity will appear here
          </p>
        </div>
      )}
    </div>
  );
});

export default SidebarContent;
