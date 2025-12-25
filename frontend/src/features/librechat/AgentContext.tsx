'use client';

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type { Message, RunAgentInput } from '@/services/ag-ui/client';
import type { DocumentPointer, AttachmentInput, InterruptPayload } from '@/services/ag-ui/types';
import type { Artifact } from './artifacts/types';

/**
 * Serializable artifact data for persistence in message metadata.
 * Excludes runtime fields like lastUpdateTime and messageId (which will be set on restore).
 */
export interface SerializedArtifact {
  id: string;
  type: Artifact['type'];
  title: string;
  content: string;
  language?: string;
  identifier?: string;
  index?: number;
  // Image artifact fields
  imageData?: string;
  mimeType?: string;
  altText?: string;
  aspectRatio?: string;
  resolution?: string;
}

/**
 * Abstract agent interface for CopilotKit compatibility.
 * This replaces the @ag-ui/client AbstractAgent type.
 */
export interface AbstractAgent {
  messages: Message[];
  state: Record<string, unknown>;
  addMessage: (message: Message) => void;
  setState: (state: Record<string, unknown>) => void;
  runAgent: (
    input: Partial<RunAgentInput>,
    handlers: AgentEventHandlers
  ) => Promise<void>;
  abortRun: () => void;
}

/**
 * Event handlers for agent streaming
 */
export interface AgentEventHandlers {
  signal?: AbortSignal;
  onTextMessageContentEvent?: (params: { event: unknown; textMessageBuffer?: string }) => void;
  onMessagesChanged?: (params: { messages: Message[] }) => void;
  onCustomEvent?: (params: { event: unknown }) => unknown | Promise<unknown>;
  onStateChanged?: (params: { state: unknown }) => void;
  onToolCallStartEvent?: (params: { event: unknown }) => void;
  onToolCallResultEvent?: (params: { event: unknown }) => void;
  onRunFailed?: (params: { error: unknown }) => void;
}
import type { TimelineOperation, TraceStep } from '@/services/ag-ui/event-types';
import { formatLogAnalysisResult } from './formatters/logFormatter';
import { getGlobalArtifactStore } from './artifacts/ArtifactContext';
import type { ImageArtifactEvent } from '@/services/ag-ui/event-types';
import {
  stripCodeFence,
  extractTodosFromPayload,
  formatIfStructuredLog,
} from './utils';
import { sessionsAPI } from '@/services/api/endpoints/sessions';

interface AgentContextValue {
  agent: AbstractAgent | null;
  messages: Message[];
  isStreaming: boolean;
  error: Error | null;
  sendMessage: (content: string, attachments?: AttachmentInput[]) => Promise<void>;
  abortRun: () => void;
  registerDocuments: (documents: DocumentPointer[]) => void;
  interrupt: InterruptPayload | null;
  resolveInterrupt: (value: string) => void;
  activeTools: string[];
  timelineOperations: TimelineOperation[];
  currentOperationId?: string;
  toolEvidence: Record<string, any>;
  todos: any[];
  thinkingTrace: TraceStep[];
  activeTraceStepId?: string;
  setActiveTraceStep: (stepId?: string) => void;
  isTraceCollapsed: boolean;
  setTraceCollapsed: (collapsed: boolean) => void;
  resolvedModel?: string;
  resolvedTaskType?: string;
  messageAttachments: Record<string, AttachmentInput[]>;
}

const AgentContext = createContext<AgentContextValue | null>(null);

interface AgentProviderProps {
  children: React.ReactNode;
  agent: AbstractAgent;
  sessionId?: string;
}

// Utility functions moved to ./utils

const normalizeTraceType = (rawType: unknown, content: string): TraceStep['type'] => {
  const value = typeof rawType === 'string' ? rawType.toLowerCase() : '';
  if (value === 'tool' || value === 'action') return 'tool';
  if (value === 'result') return 'result';
  if (value === 'warning' || value === 'error') return 'result';
  if (/failed|error/i.test(content)) return 'result';
  return 'thought';
};

const extractToolName = (raw: any, content: string): string | undefined => {
  const metadata = (raw?.metadata ?? {}) as Record<string, unknown>;
  const direct =
    raw?.toolName ||
    metadata.toolName ||
    metadata.tool_name ||
    metadata.name ||
    raw?.name;
  if (typeof direct === 'string' && direct.trim()) return direct.trim();

  const match = content.match(/(?:Executing|completed|failed)\s+([\w:-]+)/i);
  return match ? match[1] : undefined;
};

const extractDurationSeconds = (raw: any): number | undefined => {
  const metadata = (raw?.metadata ?? {}) as Record<string, unknown>;
  const durationMs = metadata.durationMs ?? metadata.duration_ms ?? raw?.durationMs ?? raw?.duration_ms;
  if (typeof durationMs === 'number' && Number.isFinite(durationMs)) {
    return durationMs / 1000;
  }
  const durationSeconds = metadata.duration ?? raw?.duration;
  if (typeof durationSeconds === 'number' && Number.isFinite(durationSeconds)) {
    return durationSeconds;
  }
  return undefined;
};

const inferTraceStatus = (raw: any, content: string, type: TraceStep['type']): TraceStep['status'] => {
  const metadata = (raw?.metadata ?? {}) as Record<string, unknown>;
  const metaStatus = metadata.status ?? raw?.status;
  const output = metadata.output ?? metadata.result ?? metadata.data ?? metadata.value;
  const outputError = (output && typeof output === 'object')
    ? (output as Record<string, unknown>).error ?? (output as Record<string, unknown>).message
    : undefined;
  if (metaStatus === 'error' || metadata.error || outputError || /failed|error/i.test(content)) {
    return 'error';
  }
  if (type === 'result') return 'success';
  return undefined;
};

const normalizeTraceStep = (raw: any): TraceStep => {
  const id = raw?.id ? String(raw.id) : crypto.randomUUID();
  const timestampValue = raw?.timestamp
    ? new Date(raw.timestamp).toISOString()
    : new Date().toISOString();
  const contentValue = typeof raw?.content === 'string'
    ? raw.content
    : JSON.stringify(raw?.content ?? '');
  const typeValue = normalizeTraceType(raw?.type, contentValue);
  const toolName = extractToolName(raw, contentValue);
  const duration = extractDurationSeconds(raw);
  const status = inferTraceStatus(raw, contentValue, typeValue);

  return {
    id,
    type: typeValue,
    timestamp: timestampValue,
    content: contentValue,
    toolName,
    duration,
    status,
    metadata: raw?.metadata ?? {},
  };
};

const mapTraceList = (rawList: any[]): TraceStep[] => rawList.map(normalizeTraceStep);

const hasLogAttachment = (attachments?: AttachmentInput[]): boolean => {
  if (!attachments || attachments.length === 0) return false;
  return attachments.some((att) => {
    const name = typeof att?.name === 'string' ? att.name.toLowerCase() : '';
    return name.endsWith('.log');
  });
};

const looksLikeJsonPayload = (text: string): boolean => {
  const trimmed = stripCodeFence(text).trim();
  if (!trimmed) return false;
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) return false;
  return trimmed.length > 80;
};

const normalizeTextFromContentParts = (raw: any): string | null => {
  if (typeof raw === 'string') return raw;
  if (Array.isArray(raw)) {
    const text = raw
      .map((part) => {
        if (typeof part === 'string') return part;
        if (part && typeof part === 'object' && typeof (part as any).text === 'string') return (part as any).text;
        return '';
      })
      .join('');
    return text || null;
  }
  if (raw && typeof raw === 'object') {
    if (typeof (raw as any).text === 'string') return (raw as any).text;
    if (typeof (raw as any).content === 'string') return (raw as any).content;
  }
  return null;
};

const inferLogAnalysisFromMessages = (messages: any[]) => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    const formatted = formatLogAnalysisResult((msg as any)?.content);
    if (formatted) {
      return formatted;
    }
  }
  return null;
};

export function AgentProvider({
  children,
  agent,
  sessionId,
}: AgentProviderProps) {
  const [messages, setMessages] = useState<Message[]>(agent.messages || []);
  const messagesRef = useRef<Message[]>(agent.messages || []);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [interrupt, setInterrupt] = useState<InterruptPayload | null>(null);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const [timelineOperations, setTimelineOperations] = useState<TimelineOperation[]>([]);
  const [currentOperationId, setCurrentOperationId] = useState<string | undefined>(undefined);
  const [toolEvidence, setToolEvidence] = useState<Record<string, any>>({});
  const [todos, setTodos] = useState<any[]>([]);
  const [thinkingTrace, setThinkingTrace] = useState<TraceStep[]>([]);
  const [activeTraceStepId, setActiveTraceStepId] = useState<string | undefined>(undefined);
  const [isTraceCollapsed, setTraceCollapsed] = useState(true);
  const [resolvedModel, setResolvedModel] = useState<string | undefined>(undefined);
  const [resolvedTaskType, setResolvedTaskType] = useState<string | undefined>(undefined);
  const [messageAttachments, setMessageAttachments] = useState<Record<string, AttachmentInput[]>>({});
  const interruptResolverRef = useRef<((value: string) => void) | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const toolNameByIdRef = useRef<Record<string, string>>({});
  const assistantPersistedRef = useRef(false);
  // Track artifacts created during the current run for persistence
  const pendingArtifactsRef = useRef<SerializedArtifact[]>([]);

  const sendMessage = useCallback(async (content: string, attachments?: AttachmentInput[]) => {
    if (!agent || isStreaming) return;

    setIsStreaming(true);
    setError(null);
    // Reset per-run UI state
    setTimelineOperations([]);
    setCurrentOperationId(undefined);
    setToolEvidence({});
    setTodos([]);
    setThinkingTrace([]);
    setActiveTraceStepId(undefined);
    toolNameByIdRef.current = {};
    assistantPersistedRef.current = false;
    pendingArtifactsRef.current = [];

    try {
      // Create abort controller for this request
      abortControllerRef.current = new AbortController();
      try {
        (agent as any).messages = messagesRef.current;
      } catch {
        // ignore
      }

      // Add user message to local state immediately (without metadata to avoid backend validation errors)
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
      };

      // Store attachments separately by message ID for UI display (backend doesn't accept metadata)
      if (attachments && attachments.length > 0) {
        setMessageAttachments(prev => ({
          ...prev,
          [userMessage.id]: attachments,
        }));
      }

      setMessages((prev) => [...prev, userMessage]);

      // Add user message to agent's message list
      agent.addMessage(userMessage);

      // Persist user message to backend database
      if (sessionId && content.trim()) {
        // Fire-and-forget but with error logging - user experience is not blocked
        sessionsAPI.postMessage(sessionId, {
          message_type: 'user',
          content: content.trim(),
        }).catch((err) => {
          console.error('[Persistence] Failed to persist user message:', err);
        });
      }

      const shouldForceLogAnalysis = hasLogAttachment(attachments);
      if (shouldForceLogAnalysis) {
        agent.setState({
          ...agent.state,
          agent_type: 'log_analysis',
        });
      }

      // Update agent state with attachments if provided
      if (attachments && attachments.length > 0) {
        agent.setState({
          ...agent.state,
          attachments,
        });
      }

      // No need for placeholder - streaming will handle assistant messages

      // Build forwardedProps to influence backend orchestration
      const stateProvider = (agent.state as any)?.provider;
      const stateModel = (agent.state as any)?.model;
      const stateAgentType = (agent.state as any)?.agent_type || (agent.state as any)?.agentType;
      const forwardedProps: Record<string, any> = {
        // Prefer richer answers by default
        force_websearch: true,
        // Pass through provider/model to avoid backend defaulting to Gemini
        provider: stateProvider || 'google',
        model: stateModel || 'gemini-3-flash-preview',
        agent_type: hasLogAttachment(attachments) ? 'log_analysis' : stateAgentType,
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
      };

      // Run agent with streaming updates
      await agent.runAgent(
        {
          forwardedProps,
        },
        {
          signal: abortControllerRef.current.signal,

          // Handle streaming text content
          onTextMessageContentEvent: ({ event, textMessageBuffer }: { event: any; textMessageBuffer?: string }) => {
            const agentType = (agent?.state as any)?.agent_type || (agent?.state as any)?.agentType;
            let buffer =
              typeof textMessageBuffer === 'string'
                ? textMessageBuffer
                : typeof (event as any)?.delta === 'string'
                  ? (event as any).delta
                  : '';
            if (!buffer) {
              return;
            }

            // CRITICAL: Strip markdown images with data URIs - safety filter
            // Pattern: ![alt text](data:image/...)
            // The model sometimes outputs these despite prompt instructions not to.
            // Images are already displayed as artifacts, so this is just garbage in chat.
            const MARKDOWN_DATA_URI_PATTERN = /!\[[^\]]*\]\(data:image\/[^)]+\)/gi;
            if (MARKDOWN_DATA_URI_PATTERN.test(buffer)) {
              const cleaned = buffer.replace(MARKDOWN_DATA_URI_PATTERN, '').trim();
              console.debug('[AG-UI] Stripped markdown data URI from buffer, original:', buffer.length, 'cleaned:', cleaned.length);
              if (!cleaned) {
                return; // Skip if entire buffer was just a markdown image
              }
              buffer = cleaned;
            }

            if (agentType === 'log_analysis') {
              const formatted = formatIfStructuredLog(buffer);
              if (formatted) {
                buffer = formatted;
              } else if (looksLikeJsonPayload(buffer)) {
                buffer = '';
              }
            }
            setMessages(prev => {
              const updated = [...prev];
              const lastMsg = updated[updated.length - 1];

              // If the last message is an assistant message, replace its content with the latest buffer
              if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg.content = buffer;
              } else {
                // Otherwise create a new assistant message
                updated.push({
                  id: crypto.randomUUID(),
                  role: 'assistant',
                  content: buffer,
                });
              }
              return updated;
            });
          },

          // Handle complete message updates
          onMessagesChanged: ({ messages: agentMessages }: { messages: any[] }) => {
            // Log summary only to avoid RangeError with large content
            console.debug('[AG-UI] onMessagesChanged received:', agentMessages.length, 'messages');
            // Ensure all messages have IDs
            const fallbackId = (msg: any, index: number): string => {
              const role = typeof msg?.role === 'string' ? msg.role : 'unknown';
              const name = typeof msg?.name === 'string' ? msg.name : '';
              const toolCallId = typeof msg?.tool_call_id === 'string'
                ? msg.tool_call_id
                : typeof msg?.toolCallId === 'string'
                  ? msg.toolCallId
                  : '';
              const base = `${role}|${name}|${toolCallId}|${index}`;
              let hash = 0;
              for (let i = 0; i < base.length; i += 1) {
                hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
              }
              if (process.env.NODE_ENV !== 'production') {
                console.warn('[AG-UI] Message missing id; using stable fallback id', { role, name, toolCallId, index });
              }
              return `msg-${hash.toString(16)}`;
            };

            let messagesWithIds = agentMessages.map((msg, idx) => ({
              ...msg,
              id: msg.id || fallbackId(msg, idx),
            }));

            messagesWithIds = messagesWithIds.map((msg) => {
              if (msg.role !== 'assistant') return msg;
              if (typeof msg.content === 'string') return msg;
              const normalized = normalizeTextFromContentParts(msg.content);
              if (!normalized) return msg;
              return {
                ...msg,
                content: normalized,
              };
            });

            // CRITICAL: Strip markdown data URIs from all assistant messages
            // Pattern: ![alt text](data:image/...) - safety filter for final messages
            const MARKDOWN_DATA_URI_FILTER = /!\[[^\]]*\]\(data:image\/[^)]+\)/gi;
            messagesWithIds = messagesWithIds.map((msg) => {
              if (msg.role !== 'assistant') return msg;
              if (typeof msg.content !== 'string') return msg;
              if (!MARKDOWN_DATA_URI_FILTER.test(msg.content)) return msg;
              const cleaned = msg.content.replace(MARKDOWN_DATA_URI_FILTER, '').trim();
              console.debug('[AG-UI] Stripped markdown data URI from final message');
              return { ...msg, content: cleaned };
            });

            if (agent) {
              (agent as any).messages = messagesWithIds;
            }
            // If running log analysis (explicitly or inferred) and the stream ended with a tool result, surface a readable assistant reply.
            const explicitAgentType = (agent?.state as any)?.agent_type || (agent?.state as any)?.agentType;
            const inferredLogAnalysis = explicitAgentType === 'log_analysis'
              ? null
              : inferLogAnalysisFromMessages(messagesWithIds);
            const isLogAnalysis = explicitAgentType === 'log_analysis' || Boolean(inferredLogAnalysis);

            // If we inferred log analysis while in auto mode, tag the agent state so downstream formatting stays consistent.
            if (!explicitAgentType && inferredLogAnalysis && agent) {
              agent.setState({
                ...agent.state,
                agent_type: 'log_analysis',
              });
            }

            if (isLogAnalysis) {
              const lastToolFormatted = (() => {
                for (let i = messagesWithIds.length - 1; i >= 0; i -= 1) {
                  const msg = messagesWithIds[i];
                  if (msg.role !== 'tool') continue;
                  const formatted =
                    inferredLogAnalysis ||
                    formatLogAnalysisResult((msg as any).content) ||
                    formatIfStructuredLog((msg as any).content);
                  if (formatted) return formatted;
                }
                return null;
              })();

              if (lastToolFormatted) {
                const lastAssistantIdx = (() => {
                  for (let i = messagesWithIds.length - 1; i >= 0; i -= 1) {
                    if (messagesWithIds[i].role === 'assistant') return i;
                  }
                  return -1;
                })();

                if (lastAssistantIdx >= 0) {
                  const existing = messagesWithIds[lastAssistantIdx];
                  const existingText = typeof existing.content === 'string' ? existing.content.trim() : '';
                  if (!existingText || looksLikeJsonPayload(existingText)) {
                    messagesWithIds[lastAssistantIdx] = {
                      ...existing,
                      content: lastToolFormatted,
                      metadata: { ...(existing as any).metadata, structured_log: false },
                    };
                  }
                } else {
                  messagesWithIds.push({
                    id: crypto.randomUUID(),
                    role: 'assistant',
                    content: lastToolFormatted,
                  });
                }
              }
            }

            // Format or hide raw structured-log dumps for log-analysis runs
            if (isLogAnalysis) {
              messagesWithIds = messagesWithIds.map((msg) => {
                if (msg.role === 'assistant') {
                  const formatted = formatIfStructuredLog(msg.content);
                  if (formatted) {
                    return {
                      ...msg,
                      content: formatted,
                      metadata: { ...(msg as any).metadata, structured_log: true },
                    };
                  }
                }
                return msg;
              });

              const hasReadableAssistant = messagesWithIds.some(
                (msg) => msg.role === 'assistant' && !(msg as any).metadata?.structured_log,
              );
              if (hasReadableAssistant) {
                messagesWithIds = messagesWithIds.filter(
                  (msg) => !(msg.role === 'assistant' && (msg as any).metadata?.structured_log),
                );
              }
            }

            if (messagesWithIds.length > 0) {
              const last = messagesWithIds[messagesWithIds.length - 1];
              console.debug('[AG-UI] onMessagesChanged last message:', {
                role: last?.role,
                preview: typeof last?.content === 'string' ? last.content.slice(0, 120) : last?.content,
              });
            }

            // Preserve/derive an assistant reply for log analysis when the backend sends only tool/user messages.
            let nextMessages = messagesWithIds;
            if (isLogAnalysis) {
              const hasAssistant = nextMessages.some((m) => m.role === 'assistant');
              if (!hasAssistant) {
                // Prefer a formatted tool payload from the latest tool message
                const formattedFromTool = (() => {
                  for (let i = nextMessages.length - 1; i >= 0; i -= 1) {
                    const msg = nextMessages[i];
                    if (msg.role === 'tool') {
                      const formatted =
                        formatLogAnalysisResult((msg as any).content) ||
                        formatIfStructuredLog((msg as any).content);
                      if (formatted) return formatted;
                    }
                  }
                  return null;
                })();

                if (formattedFromTool) {
                  nextMessages = [
                    ...nextMessages,
                    {
                      id: crypto.randomUUID(),
                      role: 'assistant',
                      content: formattedFromTool,
                    },
                  ];
                } else {
                  // Fall back to the last assistant we already showed (e.g., from streaming buffer)
                  const lastAssistant = [...messagesRef.current].reverse().find((m) => m.role === 'assistant');
                  if (lastAssistant) {
                    nextMessages = [
                      ...nextMessages,
                      {
                        ...lastAssistant,
                        id: lastAssistant.id || crypto.randomUUID(),
                      },
                    ];
                  }
                }
              }
            }

            const uiLastMessage = messagesRef.current[messagesRef.current.length - 1];
            const uiLastAssistant =
              uiLastMessage &&
                uiLastMessage.role === 'assistant' &&
                typeof uiLastMessage.content === 'string' &&
                uiLastMessage.content.trim()
                ? uiLastMessage
                : null;

            if (uiLastAssistant) {
              const uiText = uiLastAssistant.content;
              const uiTrimmed = uiText.trim();
              if (uiTrimmed && !looksLikeJsonPayload(uiTrimmed)) {
                const lastAssistantIdx = (() => {
                  for (let i = nextMessages.length - 1; i >= 0; i -= 1) {
                    if (nextMessages[i].role === 'assistant') return i;
                  }
                  return -1;
                })();

                if (lastAssistantIdx >= 0) {
                  const snapText =
                    typeof nextMessages[lastAssistantIdx].content === 'string'
                      ? (nextMessages[lastAssistantIdx].content as string)
                      : '';
                  const snapTrimmed = snapText.trim();
                  if (!snapTrimmed || (uiTrimmed.length > snapTrimmed.length && uiTrimmed.startsWith(snapTrimmed))) {
                    nextMessages[lastAssistantIdx] = {
                      ...nextMessages[lastAssistantIdx],
                      content: uiText,
                    };
                  }
                } else {
                  nextMessages = [
                    ...nextMessages,
                    {
                      ...uiLastAssistant,
                      id: uiLastAssistant.id || crypto.randomUUID(),
                      content: uiText,
                    },
                  ];
                }
              }
            }

            if (agent) {
              (agent as any).messages = nextMessages;
            }

            // CRITICAL: Update messagesRef synchronously before setMessages
            // This ensures the finally block sees the latest messages
            // (React's useEffect that syncs messagesRef runs asynchronously after render)
            messagesRef.current = nextMessages;

            // Note: Persistence moved to finally block to ensure all artifacts are collected
            // before persisting (custom events like article_artifact arrive after onMessagesChanged)

            setMessages(nextMessages);
          },

          // Handle custom events (interrupts, timeline updates, tool evidence)
          onCustomEvent: (({ event }: any) => {
            const payloadValue = event.value ?? event.data ?? {};
            if (event.name === 'interrupt' || event.name === 'human_input_required') {
              const payload = payloadValue as InterruptPayload;
              setInterrupt(payload);

              // Return a promise that will be resolved by user action
              return new Promise<string>((resolve) => {
                interruptResolverRef.current = resolve;
              });
            }

            if (event.name === 'agent_timeline_update') {
              const value = payloadValue || {};
              const operations = Array.isArray(value.operations) ? value.operations : [];
              const normalized: TimelineOperation[] = operations.map((op: any) => ({
                ...op,
                startTime: op.startTime ? new Date(op.startTime) : undefined,
                endTime: op.endTime ? new Date(op.endTime) : undefined,
              }));
              setTimelineOperations(normalized);
              if (typeof value.currentOperationId === 'string') {
                setCurrentOperationId(value.currentOperationId);
              }
              // Fallback: extract todos from timeline operations (type === 'todo')
              const timelineTodos = operations
                .filter((op: any) => op?.type === 'todo' && op?.metadata?.todo)
                .map((op: any) => op.metadata.todo);
              if (timelineTodos.length) {
                setTodos(timelineTodos);
              }
            } else if (event.name === 'tool_evidence_update') {
              const value = payloadValue || {};
              const id = value.toolCallId as string | undefined;
              if (id) {
                setToolEvidence((prev) => ({
                  ...prev,
                  [id]: value,
                }));
              }
              if (typeof value.toolName === 'string' && value.toolName === 'write_todos') {
                const extracted = extractTodosFromPayload(value.output ?? value.result ?? value.data ?? value.value);
                if (Array.isArray(extracted) && extracted.length) {
                  setTodos(extracted);
                }
              }
            } else if (event.name === 'agent_thinking_trace') {
              const value = payloadValue || {};
              console.debug('[AG-UI] Thinking trace update:', value);
              setThinkingTrace((prev) => {
                if (Array.isArray(value.thinkingTrace)) {
                  return mapTraceList(value.thinkingTrace);
                }
                if (value.latestStep) {
                  const latest = normalizeTraceStep(value.latestStep);
                  const next = [...prev];
                  const idx = next.findIndex(step => step.id === latest.id);
                  if (idx >= 0) {
                    next[idx] = latest;
                    return next;
                  }
                  next.push(latest);
                  return next;
                }
                return prev;
              });
              if (typeof value.activeStepId === 'string') {
                setActiveTraceStepId(value.activeStepId);
              } else if (value.latestStep?.id) {
                setActiveTraceStepId(String(value.latestStep.id));
              }
            } else if (event.name === 'agent_todos_update') {
              // Some backends emit `data`, AG-UI maps it to `value`, but be defensive.
              const payload = (payloadValue ?? {}) as any;
              const todoCount = Array.isArray(payload.todos) ? payload.todos.length : 0;
              console.debug('[AG-UI] Todos update:', todoCount, 'items');
              if (Array.isArray(payload.todos)) {
                setTodos(payload.todos);
              } else {
                const extracted = extractTodosFromPayload(payload);
                if (extracted.length) {
                  setTodos(extracted);
                }
              }
            } else if (event.name === 'image_artifact') {
              // Handle image artifact from generate_image tool
              const payload = payloadValue as ImageArtifactEvent;
              // Log summary only (avoid logging large base64 imageData)
              console.debug('[AG-UI] Image artifact event:', payload?.title, 'imageData length:', payload?.imageData?.length);
              if (payload?.imageData) {
                const store = getGlobalArtifactStore();
                if (store) {
                  const state = store.getState();
                  state.addArtifact({
                    id: payload.id,
                    type: 'image',
                    title: payload.title || 'Generated Image',
                    content: payload.content || '',
                    messageId: payload.messageId,
                    imageData: payload.imageData,
                    mimeType: payload.mimeType || 'image/png',
                  });
                  state.setCurrentArtifact(payload.id);
                  state.setArtifactsVisible(true);
                }
                // Track for persistence (exclude messageId - will be set on restore)
                pendingArtifactsRef.current.push({
                  id: payload.id,
                  type: 'image',
                  title: payload.title || 'Generated Image',
                  content: payload.content || '',
                  imageData: payload.imageData,
                  mimeType: payload.mimeType || 'image/png',
                });
              }
            } else if (event.name === 'article_artifact') {
              // Handle article artifact for research reports, articles with images
              const artPayload = payloadValue as { id: string; title: string; content: string };
              console.debug('[AG-UI] Article artifact event:', artPayload?.title, 'length:', artPayload?.content?.length);
              const payload = payloadValue as { id: string; type: string; title: string; content: string; messageId: string };
              if (payload?.content) {
                const store = getGlobalArtifactStore();
                if (store) {
                  const state = store.getState();
                  state.addArtifact({
                    id: payload.id,
                    type: 'article',
                    title: payload.title || 'Article',
                    content: payload.content,
                    messageId: payload.messageId,
                  });
                  state.setCurrentArtifact(payload.id);
                  state.setArtifactsVisible(true);
                }
                // Track for persistence (exclude messageId - will be set on restore)
                pendingArtifactsRef.current.push({
                  id: payload.id,
                  type: 'article',
                  title: payload.title || 'Article',
                  content: payload.content,
                });
              }
            }

            return undefined;
          }) as any,

          // Handle state changes (for debugging)
          onStateChanged: ({ state }: { state: any }) => {
            // Log summary only to avoid RangeError with large state objects
            console.debug('[AG-UI] State changed:', Object.keys(state || {}).join(', '));
            try {
              const meta = (state?.config?.configurable?.metadata) || {};
              if (typeof meta.resolved_model === 'string') {
                setResolvedModel(meta.resolved_model);
              }
              if (typeof meta.resolved_task_type === 'string') {
                setResolvedTaskType(meta.resolved_task_type);
              }
            } catch (err) {
              console.debug('[AG-UI] meta parse failed:', err);
            }
          },

          // Handle tool calls (for debugging + UI visibility)
          onToolCallStartEvent: ({ event }: { event: any }) => {
            console.debug('[AG-UI] Tool call started:', event.toolCallName, event.toolCallId);
            const id = event.toolCallId || crypto.randomUUID();
            const name = (event.toolCallName as string) || id || 'tool';
            toolNameByIdRef.current[id] = name;
            setActiveTools((prev) => (prev.includes(name) ? prev : [...prev, name]));
          },

          onToolCallResultEvent: ({ event }: { event: any }) => {
            console.debug('[AG-UI] Tool call result:', event.toolCallId);
            const id = event.toolCallId || event.tool_call_id;
            const name = toolNameByIdRef.current[id] || event.toolCallName || event.tool_call_name;

            // Try to extract todos from the result payload even if it arrives as a JSON string
            const output = (event.result ?? event.output ?? event.data ?? {}) as any;
            const extracted = extractTodosFromPayload(output);
            if (name === 'write_todos') {
              if (Array.isArray(extracted) && extracted.length) {
                setTodos(extracted);
              }
            }

            if (name) {
              if (id) {
                delete toolNameByIdRef.current[id];
              }
              setActiveTools((prev) => prev.filter((n) => n !== name));
            }
          },

          // Handle errors
          onRunFailed: ({ error: runError }: { error: any }) => {
            console.error('[AG-UI] Run failed:', runError);
            setError(runError);
          },
        } as any,
      );

      // Clear attachments after sending
      if (attachments && attachments.length > 0) {
        agent.state = {
          ...agent.state,
          attachments: [],
        };
      }

    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        console.error('[AG-UI] Error sending message:', err);
        setError(err);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
      setActiveTools([]);

      // Persist final assistant message AFTER run completes
      // This ensures all custom events (artifacts) have been processed
      if (sessionId && !assistantPersistedRef.current) {
        const currentMessages = messagesRef.current;
        const lastAssistantMessage = [...currentMessages].reverse().find(
          (msg) => msg.role === 'assistant' && typeof msg.content === 'string' && msg.content.trim()
        );
        if (lastAssistantMessage) {
          assistantPersistedRef.current = true;
          const agentType = (agent?.state as any)?.agent_type || (agent?.state as any)?.agentType || 'primary';

          // Include artifacts in metadata for persistence
          const artifacts = pendingArtifactsRef.current.length > 0
            ? pendingArtifactsRef.current
            : undefined;

          console.debug('[Persistence] Persisting assistant message with', artifacts?.length || 0, 'artifacts');

          sessionsAPI.postMessage(sessionId, {
            message_type: 'assistant',
            content: lastAssistantMessage.content,
            agent_type: agentType,
            metadata: artifacts ? { artifacts } : undefined,
          }).then(() => {
            console.debug('[Persistence] Assistant message persisted successfully');
          }).catch((err) => {
            console.error('[Persistence] Failed to persist assistant message:', err);
            assistantPersistedRef.current = false;
          });
        }
      }
    }
  }, [agent, isStreaming, sessionId]);

  const abortRun = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
    if (agent) {
      agent.abortRun();
    }
    setActiveTools([]);
  }, [agent]);

  const registerDocuments = useCallback((documents: DocumentPointer[]) => {
    if (!agent) return;

    // Store documents in agent state for next run
    agent.state = {
      ...agent.state,
      available_documents: documents,
    };

    console.debug('[AG-UI] Registered documents:', documents.length);
  }, [agent]);

  const resolveInterrupt = useCallback((value: string) => {
    if (interruptResolverRef.current) {
      interruptResolverRef.current(value);
      interruptResolverRef.current = null;
      setInterrupt(null);
    }
  }, []);

  const setActiveTraceStep = useCallback((stepId?: string) => {
    setActiveTraceStepId(stepId);
  }, []);

  const setTraceCollapsedState = useCallback((collapsed: boolean) => {
    setTraceCollapsed(collapsed);
  }, []);

  // Initialize with agent's existing messages on mount
  useEffect(() => {
    if (agent && agent.messages) {
      setMessages(agent.messages);
    }
  }, [agent]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  return (
    <AgentContext.Provider
      value={{
        agent,
        messages,
        isStreaming,
        error,
        sendMessage,
        abortRun,
        registerDocuments,
        interrupt,
        resolveInterrupt,
        activeTools,
        timelineOperations,
        currentOperationId,
        toolEvidence,
        todos,
        thinkingTrace,
        activeTraceStepId,
        setActiveTraceStep,
        isTraceCollapsed,
        setTraceCollapsed: setTraceCollapsedState,
        resolvedModel,
        resolvedTaskType,
        messageAttachments,
      }}
    >
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgent must be used within AgentProvider');
  }
  return context;
}
