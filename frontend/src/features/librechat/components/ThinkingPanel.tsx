'use client';

import React, { useState, useMemo, useCallback } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Brain,
  FileText,
  Globe,
  Database,
  Clock,
  Search,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import type { TraceStep } from '@/services/ag-ui/event-types';
import { extractTodosFromPayload, parseToolOutput } from '@/features/librechat/utils';

interface ThinkingPanelProps {
  thinking: string | null;
  traceSteps?: TraceStep[];
}

const MAX_ARG_LENGTH = 160;
const MAX_DETAIL_LENGTH = 480;
const DEFAULT_THOUGHT_PLACEHOLDER = 'model reasoning';

const normalizeWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();
const stripThoughtMarkers = (value: string): string => (
  value
    .replace(/:::(?:thinking|think)\s*/gi, '')
    .replace(/:::\s*/g, '')
    .replace(/<\/?(?:thinking|think)>/gi, '')
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
  const fallbackContent =
    (typeof metadata.finalOutput === 'string' && metadata.finalOutput.trim()) ||
    (typeof metadata.final_output === 'string' && metadata.final_output.trim()) ||
    (typeof metadata.content === 'string' && stripThoughtMarkers(metadata.content)) ||
    '';
  const promptPreview =
    (typeof metadata.promptPreview === 'string' && metadata.promptPreview.trim()) ||
    (typeof metadata.prompt_preview === 'string' && metadata.prompt_preview.trim()) ||
    '';

  const normalized = rawContent.replace(/^model reasoning[:\s]*/i, '').trim();
  if (normalized && normalized.toLowerCase() !== DEFAULT_THOUGHT_PLACEHOLDER) {
    return rawContent;
  }
  if (fallbackContent) return fallbackContent;
  if (promptPreview) return `Prompt preview:\n${promptPreview}`;
  return 'No transcript yet';
};

const getStepToolName = (step: TraceStep): string | undefined => {
  if (step.toolName) return step.toolName;
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const name = metadata.toolName ?? metadata.tool_name ?? metadata.name;
  return typeof name === 'string' ? name : undefined;
};

const humanizeToolName = (name?: string): string => {
  if (!name) return '';
  return normalizeWhitespace(name.replace(/[_-]+/g, ' '));
};

const getStepIcon = (step: TraceStep): React.ReactNode => {
  if (step.status === 'error') return <AlertCircle className="text-red-400" size={14} />;
  if (step.type === 'thought') return <Brain className="text-purple-400" size={14} />;

  const toolName = (getStepToolName(step) || '').toLowerCase();
  if (toolName.includes('read') || toolName.includes('file')) {
    return <FileText className="text-blue-400" size={14} />;
  }
  if (toolName.includes('search') || toolName.includes('tavily') || toolName.includes('google')) {
    return <Globe className="text-green-400" size={14} />;
  }
  if (toolName.includes('sql') || toolName.includes('db') || toolName.includes('database')) {
    return <Database className="text-amber-400" size={14} />;
  }
  return <Search className="text-slate-400" size={14} />;
};

const getThoughtSummary = (content: string): string => {
  const cleaned = content.replace(/^model reasoning[:\s]*/i, '').trim();
  const lines = cleaned.split('\n').map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return 'Thought';
  return truncateLine(lines[0], 120);
};

const getThoughtLabel = (step: TraceStep): string => {
  const durationLabel = formatDuration(step.duration);
  return durationLabel ? `Thought for ${durationLabel}` : 'Thought';
};

const getToolLabel = (step: TraceStep): string => {
  const toolName = getStepToolName(step);
  const toolNameValue = (toolName || '').toLowerCase();
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const rawArgs = metadata.input ?? metadata.args ?? metadata.arguments;
  const todoBlock = formatTodosBlock(rawArgs);
  const argPreview = formatToolArgs(rawArgs);
  const cleanedPreview = argPreview && /^[{\[]/.test(argPreview.trim()) ? null : argPreview;
  const lower = normalizeWhitespace(`${toolName ?? step.content}`).toLowerCase();

  if (toolNameValue.includes('todo') || lower.includes('todo') || todoBlock) {
    return 'Updating todos';
  }
  if (lower.includes('search') || lower.includes('tavily') || lower.includes('google')) {
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

const getToolDetail = (step: TraceStep): string | null => {
  const metadata = (step.metadata ?? {}) as Record<string, unknown>;
  const rawInput = metadata.input ?? metadata.args ?? metadata.arguments;
  const rawOutput = metadata.output ?? metadata.result ?? metadata.data ?? metadata.value;
  const detailLines: string[] = [];

  const errorMessage = extractErrorMessage(metadata.error ?? rawOutput);
  if (errorMessage) {
    detailLines.push(`Error: ${truncateLine(errorMessage, MAX_DETAIL_LENGTH)}`);
  }

  const todoOutput = formatTodosBlock(rawOutput) || formatTodosBlock(rawInput);
  if (todoOutput) {
    detailLines.push(todoOutput);
  } else {
    const inputLine = formatToolArgs(rawInput);
    if (inputLine) detailLines.push(`Input: ${truncateLine(inputLine, MAX_ARG_LENGTH)}`);

    const outputLine = formatToolArgs(rawOutput);
    if (outputLine) detailLines.push(`Output: ${truncateLine(outputLine, MAX_ARG_LENGTH)}`);
  }

  if (!detailLines.length) return null;
  return truncateLine(detailLines.join('\n'), MAX_DETAIL_LENGTH);
};

export function ThinkingPanel({ thinking, traceSteps = [] }: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedThoughtIds, setExpandedThoughtIds] = useState<Set<string>>(new Set());
  const [expandedToolIds, setExpandedToolIds] = useState<Set<string>>(new Set());

  const hasContent = thinking || traceSteps.length > 0;

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

  const groupedSteps = useMemo(() => {
    const groups: Array<{ id: string; title: string; steps: TraceStep[] }> = [];
    let currentGroup: { id: string; title: string; steps: TraceStep[] } | null = null;

    mergedTraceSteps.forEach((step) => {
      const stepType = step.type === 'action' ? 'tool' : step.type;
      if (stepType === 'thought') {
        if (currentGroup) groups.push(currentGroup);
        const thoughtContent = getThoughtContent(step);
        currentGroup = {
          id: step.id,
          title: getThoughtSummary(thoughtContent),
          steps: [step],
        };
        return;
      }

      if (!currentGroup) {
        currentGroup = {
          id: step.id,
          title: getToolLabel(step),
          steps: [step],
        };
        return;
      }

      currentGroup.steps.push(step);
    });

    if (currentGroup) groups.push(currentGroup);
    return groups;
  }, [mergedTraceSteps]);

  const toggleThought = useCallback((id: string) => {
    setExpandedThoughtIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const toggleTool = useCallback((id: string) => {
    setExpandedToolIds((prev) => {
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
          <div className={`lc-thinking-status-icon ${mergedTraceSteps.length > 0 ? 'active' : ''}`}>
            {mergedTraceSteps.length > 0 ? <Clock size={16} /> : <Brain size={16} />}
          </div>
          <span className="font-semibold text-sm">Progress Updates</span>
          <span className="lc-thinking-count">{mergedTraceSteps.length} steps</span>
        </div>
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </div>

      {isExpanded && (
        <div className="lc-thinking-content">
          <div className="lc-steps-list">
            {groupedSteps.length > 0 ? (
              groupedSteps.map((group, idx) => (
                <div key={group.id || idx} className="lc-step-group">
                  <div className="lc-step-parent">
                    <span className="lc-step-number">{idx + 1}</span>
                    <div className="lc-step-body">
                      <span className="lc-step-text">{group.title}</span>
                    </div>
                  </div>
                  <div className="lc-step-children">
                    {group.steps.map((step, stepIdx) => {
                      const stepType = step.type === 'action' ? 'tool' : step.type;
                      if (stepType === 'thought') {
                        const isOpen = expandedThoughtIds.has(step.id);
                        const thoughtContent = getThoughtContent(step);
                        return (
                          <div key={step.id || stepIdx} className="lc-step-thought">
                            <button
                              type="button"
                              className="lc-step-row lc-step-thought-row"
                              onClick={() => toggleThought(step.id)}
                            >
                              <span className="lc-step-row-content">
                                {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                <span className="lc-step-row-label">{getThoughtLabel(step)}</span>
                              </span>
                              <span className="lc-step-row-meta">{getStepIcon(step)}</span>
                            </button>
                            {isOpen && (
                              <div className="lc-thought-content">
                                {thoughtContent}
                              </div>
                            )}
                          </div>
                        );
                      }

                      const toolLabel = getToolLabel(step);
                      const toolDetail = getToolDetail(step);
                      const isToolOpen = expandedToolIds.has(step.id);
                      const errorLabel = step.status === 'error'
                        ? extractErrorMessage(step.metadata?.error ?? step.metadata?.output ?? step.metadata?.result)
                        : null;
                      const statusLabel = step.status === 'error'
                        ? truncateLine(errorLabel || 'Error', 36)
                        : stepType === 'result'
                          ? 'Done'
                          : 'Running';
                      const statusClass = step.status === 'error' ? 'error' : 'success';

                      return (
                        <div key={step.id || stepIdx} className="lc-step-tool">
                          <div className="lc-step-row">
                            <span className="lc-step-row-content">
                              <span className="lc-step-icon">{getStepIcon(step)}</span>
                              <span className="lc-step-row-label">{toolLabel}</span>
                            </span>
                            <span className="lc-step-row-meta">
                              {toolDetail && step.status === 'error' && (
                                <span className={`lc-step-status ${statusClass}`}>
                                  <AlertCircle size={12} />
                                  {statusLabel}
                                </span>
                              )}
                              {toolDetail ? (
                                <button
                                  type="button"
                                  className="lc-step-view-btn"
                                  onClick={() => toggleTool(step.id)}
                                >
                                  {isToolOpen ? 'Hide' : 'View'}
                                </button>
                              ) : stepType === 'result' ? (
                                <span className={`lc-step-status ${statusClass}`}>
                                  {step.status === 'error' ? <AlertCircle size={12} /> : <CheckCircle2 size={12} />}
                                  {statusLabel}
                                </span>
                              ) : (
                                <span className={`lc-step-status ${statusClass}`}>{statusLabel}</span>
                              )}
                            </span>
                          </div>
                          {toolDetail && isToolOpen && (
                            <div className="lc-tool-detail">
                              {toolDetail}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            ) : (
              thinking && <div className="lc-step-raw">{thinking}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ThinkingPanel;
