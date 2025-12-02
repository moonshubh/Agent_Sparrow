'use client';

import React, { useMemo, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/shared/lib/utils';

export interface TaskItem {
  id: string;
  title?: string;
  content?: string;
  status?: 'pending' | 'in_progress' | 'done' | 'completed';
  priority?: 'low' | 'medium' | 'high';
  metadata?: Record<string, unknown>;
}

interface TaskListProps {
  todos: TaskItem[];
  className?: string;
}

const statusConfig = {
  pending: {
    icon: Circle,
    borderColor: 'border-l-muted-foreground/30',
    textColor: 'text-muted-foreground',
    animate: false,
  },
  in_progress: {
    icon: Loader2,
    borderColor: 'border-l-terracotta-400',
    textColor: 'text-foreground',
    animate: true,
  },
  done: {
    icon: CheckCircle2,
    borderColor: 'border-l-sage-500',
    textColor: 'text-muted-foreground',
    animate: false,
  },
  completed: {
    icon: CheckCircle2,
    borderColor: 'border-l-sage-500',
    textColor: 'text-muted-foreground',
    animate: false,
  },
};

/**
 * TaskItemRow - Individual task with status indicator
 */
const TaskItemRow = memo(function TaskItemRow({
  task,
  index
}: {
  task: TaskItem;
  index: number
}) {
  const status = task.status || 'pending';
  const config = statusConfig[status] || statusConfig.pending;
  const Icon = config.icon;
  const title = task.title || task.content || 'Task';

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03, duration: 0.2 }}
      className={cn(
        'flex items-start gap-2.5 py-2 px-3 border-l-2 rounded-r-lg',
        'transition-colors duration-200',
        config.borderColor,
        status === 'in_progress' && 'bg-terracotta-400/5'
      )}
    >
      <div className={cn(
        'mt-0.5 flex-shrink-0',
        status === 'in_progress' ? 'text-terracotta-400' : config.textColor
      )}>
        <Icon className={cn('w-4 h-4', config.animate && 'animate-spin')} />
      </div>
      <div className="flex-1 min-w-0">
        <p className={cn(
          'text-sm leading-snug',
          config.textColor,
          (status === 'done' || status === 'completed') && 'line-through opacity-60'
        )}>
          {title}
        </p>
      </div>
      {task.priority === 'high' && (
        <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
      )}
    </motion.div>
  );
});

/**
 * TaskList - Clean, minimal task list
 *
 * Features:
 * - Thin progress bar
 * - Left border status indicators (instead of background colors)
 * - Staggered animation on appearance
 */
export const TaskList = memo(function TaskList({
  todos,
  className,
}: TaskListProps) {
  // Normalize and sort todos
  const normalizedTodos = useMemo(() => {
    const statusOrder = { in_progress: 0, pending: 1, done: 2, completed: 2 };

    return todos
      .map(todo => ({
        ...todo,
        title: todo.title || todo.content || 'Task',
        status: ((todo.status || 'pending').toLowerCase() as TaskItem['status']),
      }))
      .sort((a, b) => {
        const orderA = statusOrder[a.status || 'pending'] ?? 1;
        const orderB = statusOrder[b.status || 'pending'] ?? 1;
        return orderA - orderB;
      });
  }, [todos]);

  // Calculate stats
  const stats = useMemo(() => {
    const total = normalizedTodos.length;
    const done = normalizedTodos.filter(t => t.status === 'done' || t.status === 'completed').length;
    const inProgress = normalizedTodos.filter(t => t.status === 'in_progress').length;
    const progressPercent = total > 0 ? Math.round((done / total) * 100) : 0;

    return { total, done, inProgress, progressPercent };
  }, [normalizedTodos]);

  // Don't render if no tasks
  if (normalizedTodos.length === 0) {
    return null;
  }

  return (
    <div className={cn('space-y-2', className)}>
      {/* Header with Counter */}
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-medium text-muted-foreground">Tasks</span>
        <span className="text-xs text-muted-foreground">
          {stats.done}/{stats.total}
        </span>
      </div>

      {/* Progress Bar - Thin and subtle */}
      <div className="h-1 bg-secondary/50 rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-gradient-to-r from-terracotta-400 to-sage-500 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${stats.progressPercent}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>

      {/* Task List */}
      <div className="space-y-1">
        <AnimatePresence mode="popLayout">
          {normalizedTodos.map((task, index) => (
            <TaskItemRow key={task.id || index} task={task} index={index} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
});

export default TaskList;
