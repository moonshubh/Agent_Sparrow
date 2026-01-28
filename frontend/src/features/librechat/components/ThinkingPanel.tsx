'use client';

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import {
  AlertCircle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock,
  Database,
  FileText,
  Globe,
  ListChecks,
  Loader2,
  Search,
  Users,
} from 'lucide-react';
import type { TraceStep, TodoItem, ToolEvidenceUpdateEvent } from '@/services/ag-ui/event-types';
import type { SubagentRun } from '@/features/librechat/AgentContext';
import { extractTodosFromPayload, parseToolOutput } from '@/features/librechat/utils';
import { EnhancedMarkdown } from './EnhancedMarkdown';

interface ThinkingPanelProps {
  thinking: string | null;
  traceSteps?: TraceStep[];
  todos?: TodoItem[];
  toolEvidence?: Record<string, ToolEvidenceUpdateEvent>;
  activeStepId?: string;
  subagentActivity?: Map<string, SubagentRun>;
  isStreaming?: boolean;
}

const MAX_ARG_LENGTH = 160;
const MAX_DETAIL_LENGTH = 600;
const DEFAULT_THOUGHT_PLACEHOLDER = 'model reasoning';
const INTERNAL_TOOL_NAMES = new Set(['write_todos', 'trace_update']);
const SENSITIVE_TOOL_NAMES = new Set(['log_diagnoser', 'log_diagnoser_tool']);

type TimelineKind = 'thought' | 'tool' | 'todo' | 'result';

type TimelineItem = {
  id: string;
  kind: TimelineKind;
  step?: TraceStep;
  startStep?: TraceStep;
  endStep?: TraceStep;
  toolCallId?: string;
  toolName?: string;
  todos?: TodoItem[];
};

const normalizeWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();
const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const stripThoughtMarkers = (value: string): string => (
  value
    .replace(/:::\s*(?:thinking|think|analysis|reasoning)\s*/gi, '')
    .replace(/:::\s*/g, '')
    .replace(/<\/?\s*(?:thinking|think|analysis|reasoning)\s*>/gi, '')
    .trim()
);

const hasMeaningfulThought = (step: TraceStep): boolean => {
  if (step.type !== 'thought') return false;
  const raw = typeof step.content === 'string' ? step.content : '';
  const normalized = raw.replace(/^model reasoning[:\s]*/i, '').trim();
  return Boolean(normalized && normalized.toLowerCase() !== DEFAULT_THOUGHT_PLACEHOLDER);
};

const formatDuration = (duration?: number): string | null => {
  if (typeof duration !== 'number' || !Number.isFinite(duration)) return null;
  if (duration < 1) return '<1s';
  return `${Math.round(duration)}s`;
};

const formatDurationMs = (startTime?: string, endTime?: string): string | null => {
  if (!startTime) return null;
  const start = new Date(startTime).getTime();
  const end = endTime ? new Date(endTime).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  const seconds = Math.max(0, (end - start) / 1000);
  return formatDuration(seconds);
};

const formatToolArgs = (args: unknown): string | null => {
  if (args === null || args === undefined) return null;
  if (typeof args === 'string') {
    const trimmed = args.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith('content=')) {
      const parsed = parseToolOutput(trimmed);
      if (Object.keys(parsed).length > 0) {
        return formatToolArgs(parsed);
      }
    }
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
      try {
        return formatToolArgs(JSON.parse(trimmed));
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }
  if (typeof args === 'number' || typeof args === 'boolean') return String(args);
  if (Array.isArray(args)) {
    if (args.length === 0) return null;
    return formatToolArgs(args[0]) ?? JSON.stringify(args);
  }
  if (typeof args === 'object') {
    const record = args as Record<string, unknown>;
    if (Array.isArray(record.todos)) {
      return `${record.todos.length} todos`;
    }
    if (Array.isArray(record.items)) {
      return `${record.items.length} items`;
    }
    if (record.update && typeof record.update === 'object') {
      const nested = formatToolArgs(record.update);
      if (nested) return nested;
    }
    const preferredKeys = ['query', 'q', 'path', 'file', 'url', 'id', 'name', 'prompt', 'title', 'content', 'text'];
    for (const key of preferredKeys) {
      const value = record[key];
      if (typeof value === 'string' && value.trim()) {
        const cleaned = key === 'path' ? value.split('/').pop() || value : value;
        return cleaned.trim();
      }
      if (typeof value === 'number' || typeof value === 'boolean') {
        return String(value);
      }
    }
    const entries = Object.entries(record).filter(([, value]) => value !== undefined && value !== null);
    if (entries.length === 1) {
      const singleValue = entries[0][1];
      if (typeof singleValue === 'string') return singleValue;
      if (typeof singleValue === 'number' || typeof singleValue === 'boolean') return String(singleValue);
    }
    try {
      return JSON.stringify(record);
    } catch {
      return null;
    }
  }
  return null;
};

const summarizeRetrievalPayload = (raw: unknown): string | null => {
  const parsed = typeof raw === 'string' ? parseToolOutput(raw) : raw;
  if (!isRecord(parsed)) return null;
  if (!('retrieval_id' in parsed || 'sources_searched' in parsed || 'results' in parsed)) return null;

  const sourcesRaw = parsed.sources_searched;
  const sources = Array.isArray(sourcesRaw)
    ? sourcesRaw.filter((item): item is string => typeof item === 'string' && item.trim())
    : [];
  const results = Array.isArray(parsed.results) ? parsed.results : [];

  if (!sources.length && !results.length) return null;

  const counts = results.reduce<Record<string, number>>((acc, item) => {
    const source = isRecord(item) && typeof item.source === 'string' ? item.source : 'other';
    acc[source] = (acc[source] || 0) + 1;
    return acc;
  }, {});
  const countsLine = Object.entries(counts)
    .map(([source, count]) => `${source}: ${count}`)
    .join(', ');
  if (countsLine) return `Results: ${countsLine}`;
  if (sources.length) return `Sources: ${sources.join(', ')}`;
  return results.length ? `Results: ${results.length}` : null;
};

const truncateLine = (value: string, maxLength: number) => {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
};

const formatTodoLine = (todo: Record<string, unknown>, index: number): string => {
  const title = typeof todo.title === 'string'
    ? todo.title
    : typeof todo.content === 'string'
      ? todo.content
      : typeof todo.name === 'string'
        ? todo.name
        : typeof todo.task === 'string'
          ? todo.task
          : `Todo ${index + 1}`;
  const status = typeof todo.status === 'string' ? todo.status.replace(/_/g, ' ') : '';
  const description = typeof todo.description === 'string' ? todo.description : '';
  const statusSuffix = status ? ` (${status})` : '';
  const descriptionSuffix = description ? ` - ${description}` : '';
  return `${index + 1}. ${title}${statusSuffix}${descriptionSuffix}`;
};

const formatTodosBlock = (raw: unknown): string | null => {
  const normalized = typeof raw === 'string' ? parseToolOutput(raw) : raw;
  const resolved = normalized && typeof normalized === 'object' && Object.keys(normalized).length > 0
    ? normalized
    : raw;
  const todos = extractTodosFromPayload(resolved);
  if (!Array.isArray(todos) || todos.length === 0) return null;
  const lines = todos.map((todo, index) => {
    const record = typeof todo === 'object' && todo !== null ? (todo as Record<string, unknown>) : { title: String(todo) };
    return formatTodoLine(record, index);
  });
  return `Todos:\n${lines.join('\n')}`;
};

const extractErrorMessage = (raw: unknown): string | null => {
  if (!raw) return null;
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    return trimmed ? trimmed : null;
  }
  if (typeof raw === 'object') {
    const record = raw as Record<string, unknown>;
    const message = record.error ?? record.message ?? record.detail;
    if (typeof message === 'string' && message.trim()) return message.trim();
  }
  return null;
};

const getThoughtContent = (step: TraceStep): string => {
  const rawContent = typeof step.content === 'string' ? stripThoughtMarkers(step.content) : '';
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;

  const normalized = rawContent.replace(/^model reasoning[:\s]*/i, '').trim();
  if (normalized && normalized.toLowerCase() !== DEFAULT_THOUGHT_PLACEHOLDER) {
    return rawContent;
  }
  return '';
};

const getStepToolName = (step: TraceStep): string | undefined => {
  if (step.toolName) return step.toolName;
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const name = metadata.toolName ?? metadata.tool_name ?? metadata.name;
  return typeof name === 'string' ? name : undefined;
};

const getStepToolCallId = (step: TraceStep): string | undefined => {
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const id = metadata.toolCallId ?? metadata.tool_call_id ?? metadata.tool_callId ?? metadata.toolId ?? metadata.id;
  return typeof id === 'string' ? id : undefined;
};

const humanizeToolName = (name?: string): string => {
  if (!name) return '';
  return normalizeWhitespace(name.replace(/[_-]+/g, ' '));
};

const getToolIcon = (step: TraceStep): React.ReactNode => {
  if (step.status === 'error') return <AlertCircle className="text-red-400" size={14} />;

  const toolName = (getStepToolName(step) || '').toLowerCase();
  if (toolName.includes('read') || toolName.includes('file')) {
    return <FileText className="text-blue-400" size={14} />;
  }
  if (toolName.includes('search') || toolName.includes('tavily') || toolName.includes('google') || toolName.includes('firecrawl')) {
    return <Globe className="text-green-400" size={14} />;
  }
  if (toolName.includes('sql') || toolName.includes('db') || toolName.includes('database')) {
    return <Database className="text-amber-400" size={14} />;
  }
  return <Search className="text-slate-400" size={14} />;
};

const getThoughtKindLabel = (step: TraceStep): string => {
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const kind = typeof metadata.kind === 'string' ? metadata.kind.toLowerCase() : '';
  if (kind === 'phase') return 'Phase';
  const source = typeof metadata.source === 'string' ? metadata.source.toLowerCase() : '';
  if (source === 'provider_reasoning' || source === 'model_reasoning') return 'Model';
  if (source === 'narration') return 'Narration';
  return 'Thought';
};

const getTimestampMs = (value?: string): number | null => {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const getItemTimestampMs = (item: TimelineItem): number | null => {
  const step = item.step ?? item.startStep ?? item.endStep;
  return getTimestampMs(step?.timestamp);
};

const getToolLabel = (step: TraceStep): string => {
  const toolName = getStepToolName(step);
  const toolNameValue = (toolName || '').toLowerCase();
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const rawArgs = metadata.input ?? metadata.args ?? metadata.arguments;
  if (SENSITIVE_TOOL_NAMES.has(toolNameValue)) {
    const argsRecord = typeof rawArgs === 'object' && rawArgs !== null
      ? (rawArgs as Record<string, unknown>)
      : null;
    const fileName = argsRecord && typeof argsRecord.file_name === 'string' ? argsRecord.file_name : '';
    return fileName ? `Analyzing log: ${fileName}` : 'Analyzing attached logs';
  }
  const todoBlock = formatTodosBlock(rawArgs);
  const argPreview = formatToolArgs(rawArgs);
  const cleanedPreview = argPreview && /^[{\[]/.test(argPreview.trim()) ? null : argPreview;
  const lower = normalizeWhitespace(`${toolName ?? step.content}`).toLowerCase();
  const parsedArgs = (() => {
    if (!rawArgs) return null;
    if (typeof rawArgs === 'object') return rawArgs as Record<string, unknown>;
    if (typeof rawArgs === 'string') {
      const trimmed = rawArgs.trim();
      if (!trimmed) return null;
      if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
        try {
          const parsed = JSON.parse(trimmed);
          return typeof parsed === 'object' && parsed ? (parsed as Record<string, unknown>) : null;
        } catch {
          return null;
        }
      }
    }
    return null;
  })();
  if (toolNameValue === 'task') {
    const rawType = parsedArgs?.subagent_type ?? parsedArgs?.subagentType;
    const rawTask = parsedArgs?.description ?? parsedArgs?.task ?? parsedArgs?.prompt;
    const subagentType = typeof rawType === 'string' && rawType.trim() ? rawType.trim() : 'subagent';
    const taskLabel = typeof rawTask === 'string' && rawTask.trim() ? truncateLine(rawTask.trim(), 120) : '';
    const agentLabel = humanizeToolName(subagentType);
    return taskLabel ? `Delegating to ${agentLabel}: ${taskLabel}` : `Delegating to ${agentLabel}`;
  }

  if (toolNameValue.includes('todo') || lower.includes('todo') || todoBlock) {
    return 'Updating todos';
  }
  if (lower.includes('search') || lower.includes('tavily') || lower.includes('google') || lower.includes('firecrawl')) {
    return `Searching web for "${cleanedPreview ?? 'information'}"`;
  }
  if (lower.includes('read') || lower.includes('file')) {
    return `Reading ${cleanedPreview ?? 'file'}`;
  }
  if (lower.includes('write') || lower.includes('edit') || lower.includes('update') || lower.includes('replace')) {
    return `Updating ${cleanedPreview ?? 'file'}`;
  }
  if (lower.includes('sql') || lower.includes('db') || lower.includes('database')) {
    return cleanedPreview ? `Querying database for "${cleanedPreview}"` : 'Querying database';
  }
  if (toolName) {
    const label = humanizeToolName(toolName);
    return cleanedPreview ? `${label}: ${cleanedPreview}` : label;
  }
  return normalizeWhitespace(step.content || 'Tool action');
};

const buildToolDetailLines = (step: TraceStep, evidence?: ToolEvidenceUpdateEvent | null): string[] => {
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const toolName = (getStepToolName(step) || '').toLowerCase();
  if (SENSITIVE_TOOL_NAMES.has(toolName)) {
    return [];
  }
  const rawInput = metadata.input ?? metadata.args ?? metadata.arguments;
  const rawOutput = metadata.output ?? metadata.result ?? metadata.data ?? metadata.value;
  const detailLines: string[] = [];

  if (evidence?.summary) {
    detailLines.push(`Summary: ${evidence.summary}`);
  }

  if (typeof metadata.goal === 'string' && metadata.goal.trim()) {
    detailLines.push(`Goal: ${truncateLine(metadata.goal.trim(), MAX_DETAIL_LENGTH)}`);
  }

  if (step.status === 'error') {
    const errorMessage = extractErrorMessage(metadata.error ?? rawOutput);
    if (errorMessage) {
      detailLines.push(`Error: ${truncateLine(errorMessage, MAX_DETAIL_LENGTH)}`);
    }
  }

  const todoOutput = formatTodosBlock(rawOutput) || formatTodosBlock(rawInput);
  if (todoOutput) {
    detailLines.push(todoOutput);
  } else {
    const retrievalSummary = summarizeRetrievalPayload(rawOutput) || summarizeRetrievalPayload(rawInput);
    if (retrievalSummary) {
      detailLines.push(retrievalSummary);
      return detailLines;
    }

    const inputLine = formatToolArgs(rawInput);
    if (inputLine) {
      detailLines.push(`Input: ${truncateLine(normalizeWhitespace(inputLine), MAX_ARG_LENGTH)}`);
    }

    const outputLine = formatToolArgs(rawOutput);
    if (outputLine) {
      detailLines.push(`Output: ${truncateLine(normalizeWhitespace(outputLine), MAX_ARG_LENGTH)}`);
    }
  }

  return detailLines;
};

const getToolStatus = (item: TimelineItem): 'running' | 'done' | 'error' => {
  const step = item.endStep ?? item.startStep ?? item.step;
  if (step?.status === 'error') return 'error';
  if (item.endStep) return 'done';
  return 'running';
};

const getTodoProgress = (todos: TodoItem[]) => {
  const total = todos.length;
  const done = todos.filter((todo) => todo.status === 'done').length;
  return { done, total };
};

const safeHost = (url?: string): string | null => {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.host;
  } catch {
    return null;
  }
};

const buildTimelineItems = (steps: TraceStep[]): TimelineItem[] => {
  const items: TimelineItem[] = [];
  const toolItems = new Map<string, TimelineItem>();

  const pushToolItem = (step: TraceStep, toolCallId?: string) => {
    const toolName = getStepToolName(step);
    if (toolCallId && toolItems.has(toolCallId)) {
      const existing = toolItems.get(toolCallId)!;
      if (step.type === 'result') {
        existing.endStep = step;
      } else {
        existing.startStep = existing.startStep ?? step;
      }
      existing.toolName = existing.toolName ?? toolName;
      return;
    }

    const item: TimelineItem = {
      id: step.id,
      kind: 'tool',
      startStep: step.type === 'result' ? undefined : step,
      endStep: step.type === 'result' ? step : undefined,
      toolCallId,
      toolName,
    };
    if (toolCallId) {
      toolItems.set(toolCallId, item);
    }
    items.push(item);
  };

  steps.forEach((step) => {
    if (step.type === 'thought') {
      items.push({ id: step.id, kind: 'thought', step });
      return;
    }

    const toolCallId = getStepToolCallId(step);
    const toolName = getStepToolName(step);
    const looksLikeTool = Boolean(toolCallId || toolName || step.type === 'action');

    if (looksLikeTool) {
      pushToolItem(step, toolCallId);
      return;
    }

    if (step.type === 'result') {
      items.push({ id: step.id, kind: 'result', step });
      return;
    }

    items.push({ id: step.id, kind: 'tool', startStep: step, toolName });
  });

  return items;
};

export function ThinkingPanel({
  thinking,
  traceSteps = [],
  todos = [],
  toolEvidence = {},
  activeStepId,
  subagentActivity = new Map(),
  isStreaming = false,
}: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(() => isStreaming);
  const [isTodoExpanded, setIsTodoExpanded] = useState(() => isStreaming);
  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set());
  const [expandedSubagentIds, setExpandedSubagentIds] = useState<Set<string>>(new Set());
  const contentRef = useRef<HTMLDivElement | null>(null);

  const hasContent = thinking || traceSteps.length > 0 || todos.length > 0 || subagentActivity.size > 0;

  const mergedTraceSteps = useMemo(() => {
    if (!thinking) return traceSteps;
    if (traceSteps.some((step) => hasMeaningfulThought(step))) return traceSteps;
    const trimmed = thinking.trim();
    if (!trimmed) return traceSteps;
    const syntheticStep: TraceStep = {
      id: 'message-thinking',
      type: 'thought',
      timestamp: new Date().toISOString(),
      content: trimmed,
      metadata: { source: 'message_thinking' },
    };
    return [syntheticStep, ...traceSteps];
  }, [thinking, traceSteps]);

  const filteredTraceSteps = useMemo(() => {
    return mergedTraceSteps.filter((step) => {
      if (step.type === 'thought') {
        const metadata = (step.metadata ?? {}) as Record<string, unknown>;
        const kind = typeof metadata.kind === 'string' ? metadata.kind.toLowerCase() : '';
        const source = typeof metadata.source === 'string' ? metadata.source.toLowerCase() : '';
        const content = getThoughtContent(step).trim();
        if (kind === 'phase') return Boolean(step.content?.trim());
        if (content) return true;
        // Hide placeholder thought steps created for model runs that never emitted reasoning.
        return source === 'narration' || source === 'provider_reasoning' || source === 'model_reasoning';
      }

      const toolName = (getStepToolName(step) || '').toLowerCase();
      if (toolName && INTERNAL_TOOL_NAMES.has(toolName)) return false;
      return true;
    });
  }, [mergedTraceSteps]);

  const timelineItems = useMemo(() => buildTimelineItems(filteredTraceSteps), [filteredTraceSteps]);

  const { done: todosDone, total: todosTotal } = useMemo(() => getTodoProgress(todos), [todos]);
  const todoPercent = todosTotal > 0 ? Math.round((todosDone / todosTotal) * 100) : 0;

  const subagentEntries = useMemo(() => {
    const items = Array.from(subagentActivity.values());
    return items.sort((a, b) => {
      const aTime = new Date(a.startTime || 0).getTime();
      const bTime = new Date(b.startTime || 0).getTime();
      return aTime - bTime;
    });
  }, [subagentActivity]);
  const runningSubagents = useMemo(
    () => subagentEntries.filter((entry) => entry.status === 'running').length,
    [subagentEntries],
  );

  const activeItemId = useMemo(() => {
    if (!activeStepId) return undefined;
    const direct = timelineItems.find((item) => item.id === activeStepId);
    if (direct) return direct.id;
    const match = timelineItems.find((item) => (
      item.kind === 'tool'
      && (item.startStep?.id === activeStepId || item.endStep?.id === activeStepId)
    ));
    return match?.id;
  }, [activeStepId, timelineItems]);

  const derivedThoughtDurations = useMemo(() => {
    const durations = new Map<string, number>();
    const streamingEndMs = isStreaming
      ? getItemTimestampMs(timelineItems[timelineItems.length - 1] ?? { id: '', kind: 'result' })
      : null;

    for (let i = 0; i < timelineItems.length; i += 1) {
      const item = timelineItems[i];
      if (item.kind !== 'thought' || !item.step) continue;
      const startMs = getTimestampMs(item.step.timestamp);
      if (startMs === null) continue;

      let endMs: number | null = null;
      for (let j = i + 1; j < timelineItems.length; j += 1) {
        const candidateItem = timelineItems[j];
        if (candidateItem.kind !== 'thought') continue;
        const candidate = getItemTimestampMs(candidateItem);
        if (candidate !== null) {
          endMs = candidate;
          break;
        }
      }

      const effectiveEnd = endMs ?? streamingEndMs;
      if (effectiveEnd !== null && effectiveEnd > startMs) {
        durations.set(item.id, (effectiveEnd - startMs) / 1000);
      }
    }

    return durations;
  }, [isStreaming, timelineItems]);

  const scrollTargetId = useMemo(() => {
    if (activeItemId) return activeItemId;
    if (isStreaming) return timelineItems[timelineItems.length - 1]?.id;
    return undefined;
  }, [activeItemId, isStreaming, timelineItems]);

  const expandedItemIdsForRender = useMemo(() => {
    if (!isStreaming || !scrollTargetId) return expandedItemIds;
    const next = new Set(expandedItemIds);
    next.add(scrollTargetId);
    return next;
  }, [expandedItemIds, isStreaming, scrollTargetId]);

  useEffect(() => {
    if (!isExpanded) return;

    if (!scrollTargetId) return;

    const rafId = requestAnimationFrame(() => {
      try {
        const safeTargetId =
          typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
            ? CSS.escape(scrollTargetId)
            : scrollTargetId;
        const el = contentRef.current?.querySelector(
          `[data-step-id="${safeTargetId}"]`
        );
        el?.scrollIntoView({ block: 'nearest' });
      } catch {
        // noop - selector can fail on unexpected IDs
      }
    });

    return () => cancelAnimationFrame(rafId);
  }, [isExpanded, scrollTargetId]);

  const toggleItem = useCallback((id: string) => {
    setExpandedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const toggleSubagent = useCallback((id: string) => {
    setExpandedSubagentIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  if (!hasContent) return null;

  return (
    <div className="lc-thinking">
      <div
        className="lc-thinking-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="lc-thinking-title">
          <div className={`lc-thinking-status-icon ${timelineItems.length > 0 ? 'active' : ''}`}>
            {timelineItems.length > 0 ? <Clock size={16} /> : <Brain size={16} />}
          </div>
          <span className="font-semibold text-sm">Progress Updates</span>
          <span className="lc-thinking-count">{timelineItems.length} steps</span>
          {subagentEntries.length > 0 && (
            <span className={`lc-subagent-pill ${runningSubagents > 0 ? 'active' : ''}`}>
              <Users size={12} />
              {runningSubagents > 0 ? `${runningSubagents} running` : `${subagentEntries.length} total`}
            </span>
          )}
        </div>
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </div>

      {isExpanded && (
        <div className="lc-thinking-content" ref={contentRef}>
          {todosTotal > 0 && (
            <div className="lc-todo-summary">
              <button
                type="button"
                className="lc-progress-row"
                onClick={() => setIsTodoExpanded((prev) => !prev)}
                aria-expanded={isTodoExpanded}
              >
                <span className="lc-progress-row-left">
                  {isTodoExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <span className="lc-progress-icon"><ListChecks size={14} /></span>
                  <span className="lc-progress-label">{`${todosDone}/${todosTotal} tasks done`}</span>
                </span>
                <span className="lc-progress-row-right">
                  <span className="lc-progress-meta">{`${todoPercent}%`}</span>
                </span>
              </button>
              <div className="lc-todo-progress">
                <div className="lc-todo-progress-fill" style={{ width: `${todoPercent}%` }} />
              </div>
              {isTodoExpanded && (
                <div className="lc-trace-box">
                  <div className="lc-todo-list">
                    {todos.map((todo) => {
                      const status = todo.status || 'pending';
                      const statusIcon = status === 'done'
                        ? <CheckCircle2 size={14} />
                        : status === 'in_progress'
                          ? <Loader2 size={14} className="lc-spin" />
                          : <Circle size={14} />;
                      return (
                        <div key={todo.id} className={`lc-todo-item ${status}`}>
                          <span className="lc-todo-status">{statusIcon}</span>
                          <span className="lc-todo-title">{todo.title}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
          {subagentEntries.length > 0 && (
            <div className="lc-subagent-section">
              <div className="lc-subagent-header">
                <div className="lc-subagent-title">
                  <Users size={14} />
                  <span>Agents</span>
                </div>
                <span className="lc-thinking-count">{subagentEntries.length} tasks</span>
              </div>
              <div className="lc-progress-list">
                {subagentEntries.map((subagent) => {
                  const isOpen = expandedSubagentIds.has(subagent.toolCallId);
                  const status = subagent.status;
                  const statusLabel = status === 'error' ? 'Error' : status === 'success' ? 'Done' : 'Running';
                  const statusClass = status === 'error' ? 'error' : status === 'success' ? 'success' : 'running';
                  const statusIcon = status === 'error'
                    ? <AlertCircle size={12} />
                    : status === 'success'
                      ? <CheckCircle2 size={12} />
                      : <Loader2 size={12} className="lc-spin" />;
                  const durationLabel = formatDurationMs(subagent.startTime, subagent.endTime);
                  const metaLabel = durationLabel || (status === 'running' ? 'In progress' : 'Completed');
                  const title = humanizeToolName(subagent.subagentType) || subagent.subagentType || 'Subagent';
                  const taskLine = subagent.task ? truncateLine(subagent.task, 280) : '';
                  const thinkingLine = subagent.thinking ? truncateLine(subagent.thinking, 1200) : '';
                  const excerptLine = subagent.excerpt ? truncateLine(subagent.excerpt, 600) : '';
                  return (
                    <div key={subagent.toolCallId} className="lc-progress-item">
                      <button
                        type="button"
                        className="lc-progress-row"
                        onClick={() => toggleSubagent(subagent.toolCallId)}
                      >
                        <span className="lc-progress-row-left">
                          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span className="lc-progress-icon"><Users size={14} /></span>
                          <span className="lc-progress-label">{title}</span>
                        </span>
                        <span className="lc-progress-row-right">
                          <span className="lc-progress-meta">{metaLabel}</span>
                          <span className={`lc-progress-badge ${statusClass}`}>
                            {statusIcon}
                            {statusLabel}
                          </span>
                        </span>
                      </button>
                      {isOpen && (
                        <div className="lc-trace-box">
                          <div className="lc-trace-lines mono">
                            {taskLine && (
                              <div className="lc-trace-line">Task: {taskLine}</div>
                            )}
                            {thinkingLine && (
                              <div className="lc-trace-line">Thinking: {thinkingLine}</div>
                            )}
                            {excerptLine && (
                              <div className="lc-trace-line">Result: {excerptLine}</div>
                            )}
                            {subagent.reportPath && (
                              <div className="lc-trace-line">Report: {subagent.reportPath}</div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          <div className="lc-progress-list">
            {timelineItems.map((item) => {
              const isOpen = expandedItemIdsForRender.has(item.id);
              const itemStep = item.step ?? item.endStep ?? item.startStep;
              const toolCallId = item.toolCallId ?? (itemStep ? getStepToolCallId(itemStep) : undefined);
              const evidence = toolCallId ? toolEvidence[toolCallId] : undefined;

              if (item.kind === 'thought' && itemStep) {
                const thoughtContent = getThoughtContent(itemStep);
                if (!thoughtContent.trim()) return null;
                const derivedDuration = derivedThoughtDurations.get(item.id);
                const durationSeconds = itemStep.duration ?? derivedDuration;
                const durationLabel = formatDuration(durationSeconds);
                const label = durationLabel ? `Thought for ${durationLabel}` : getThoughtKindLabel(itemStep);
                const metaLabel = durationLabel ?? getThoughtKindLabel(itemStep);
                return (
                  <div key={item.id} className="lc-progress-item" data-step-id={item.id}>
                    <button
                      type="button"
                      className="lc-progress-row"
                      onClick={() => toggleItem(item.id)}
                    >
                      <span className="lc-progress-row-left">
                        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        <span className="lc-progress-icon"><Brain size={14} /></span>
                        <span className="lc-progress-label">{label}</span>
                      </span>
                      <span className="lc-progress-row-right">
                        <span className="lc-progress-meta">{metaLabel}</span>
                      </span>
                    </button>
                    {isOpen && (
                      <div className="lc-trace-box">
                        <EnhancedMarkdown
                          content={thoughtContent}
                          variant="librechat"
                          messageId={item.id}
                          registerArtifacts={false}
                        />
                      </div>
                    )}
                  </div>
                );
              }

              if (item.kind === 'tool') {
                const toolStep = itemStep;
                if (!toolStep) return null;
                const labelStep = item.startStep ?? toolStep;
                const toolLabel = getToolLabel(labelStep);
                const detailStep = item.endStep ?? item.startStep ?? toolStep;
                const toolDetailLines = buildToolDetailLines(detailStep, evidence);
                const cards = evidence?.cards ?? [];
                const toolStatus = getToolStatus(item);
                const isError = toolStatus === 'error';
                const statusLabel = isError ? 'Error' : toolStatus === 'done' ? 'Done' : 'Running';
                const statusClass = isError ? 'error' : toolStatus === 'done' ? 'success' : 'running';
                const statusIcon = isError
                  ? <AlertCircle size={12} />
                  : toolStatus === 'done'
                    ? <CheckCircle2 size={12} />
                    : <Loader2 size={12} className="lc-spin" />;
                const isCollapsible = toolDetailLines.length > 0 || cards.length > 0;
                return (
                  <div key={item.id} className="lc-progress-item" data-step-id={item.id}>
                    <div className="lc-progress-row">
                      <span className="lc-progress-row-left">
                        {isCollapsible ? (
                          <button
                            type="button"
                            className="lc-progress-toggle"
                            onClick={() => toggleItem(item.id)}
                          >
                            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </button>
                        ) : (
                          <span className="lc-progress-toggle-placeholder" />
                        )}
                        <span className="lc-progress-icon">{getToolIcon(toolStep)}</span>
                        <span className="lc-progress-label">{toolLabel}</span>
                      </span>
                      <span className="lc-progress-row-right">
                        <span className={`lc-progress-badge ${statusClass}`}>
                          {statusIcon}
                          {statusLabel}
                        </span>
                      </span>
                    </div>
                    {isCollapsible && isOpen && (
                      <div className="lc-trace-box">
                        {toolDetailLines.length > 0 && (
                          <div className="lc-trace-lines mono">
                            {toolDetailLines.map((line, idx) => (
                              <div key={`${item.id}-line-${idx}`} className="lc-trace-line">
                                {line}
                              </div>
                            ))}
                          </div>
                        )}
                        {cards.length > 0 && (
                          <div className="lc-tool-cards">
                            {cards.map((card, idx) => {
                              const hostFromMetadata = typeof card.metadata?.host === 'string' ? card.metadata.host : null;
                              const host = safeHost(card.url) || hostFromMetadata;
                              const title = card.title || `Result ${idx + 1}`;
                              const snippet = card.snippet || '';
                              const Wrapper: React.ElementType = card.url ? 'a' : 'div';
                              return (
                                <Wrapper
                                  key={`${item.id}-card-${idx}`}
                                  className="lc-tool-card"
                                  {...(card.url
                                    ? { href: card.url, target: '_blank', rel: 'noreferrer' }
                                    : {})}
                                >
                                  <div className="lc-tool-card-title">{title}</div>
                                  {snippet && <div className="lc-tool-card-snippet">{snippet}</div>}
                                  {(host || card.type) && (
                                    <div className="lc-tool-card-meta">
                                      {host || card.type}
                                    </div>
                                  )}
                                </Wrapper>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              }

              if (item.kind === 'result' && itemStep) {
                const isOpenable = Boolean(itemStep.content);
                return (
                  <div key={item.id} className="lc-progress-item" data-step-id={item.id}>
                    <div className="lc-progress-row">
                      <span className="lc-progress-row-left">
                        {isOpenable ? (
                          <button
                            type="button"
                            className="lc-progress-toggle"
                            onClick={() => toggleItem(item.id)}
                          >
                            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </button>
                        ) : (
                          <span className="lc-progress-toggle-placeholder" />
                        )}
                        <span className="lc-progress-icon"><CheckCircle2 size={14} /></span>
                        <span className="lc-progress-label">Final response ready</span>
                      </span>
                      <span className="lc-progress-row-right">
                        <span className="lc-progress-meta">Result</span>
                      </span>
                    </div>
                    {isOpen && itemStep.content && (
                      <div className="lc-trace-box">
                        <EnhancedMarkdown
                          content={itemStep.content}
                          variant="librechat"
                          messageId={item.id}
                          registerArtifacts={false}
                        />
                      </div>
                    )}
                  </div>
                );
              }

              return null;
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default ThinkingPanel;
