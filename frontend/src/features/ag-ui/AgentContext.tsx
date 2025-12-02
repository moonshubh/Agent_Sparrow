'use client';

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type { AbstractAgent } from '@ag-ui/client';
import type { Message, RunAgentInput } from '@ag-ui/core';
import type { DocumentPointer, AttachmentInput, InterruptPayload } from '@/services/ag-ui/types';
import type { TimelineOperation } from './timeline/AgenticTimelineView';
import type { TraceStep } from './types/thinkingTrace';
import { formatLogAnalysisResult } from './formatters/logFormatter';
import { getGlobalArtifactStore } from './artifacts/ArtifactContext';
import type { ImageArtifactEvent } from '@/services/ag-ui/event-types';

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
}

const stripCodeFence = (text: string) => {
  const trimmed = text.trim();
  const fenceMatch = trimmed.match(/^```[a-zA-Z0-9]*\s*([\s\S]*?)```$/m);
  return fenceMatch ? fenceMatch[1].trim() : trimmed;
};

const extractTodosFromPayload = (input: any): any[] => {
  const queue: any[] = [input];
  while (queue.length) {
    const raw = queue.shift();
    if (!raw) continue;

    if (typeof raw === 'string') {
      const stripped = stripCodeFence(raw);
      const direct = stripped.trim();
      const hasJsonFence = direct.startsWith('{') || direct.startsWith('[');
      if (hasJsonFence) {
        try {
          queue.push(JSON.parse(direct));
        } catch {
          // ignore
        }
      } else {
        // Try to extract the first JSON object/array from noisy strings like "content={...}"
        const braceIdx = direct.indexOf('{');
        const bracketIdx = direct.indexOf('[');
        const candidates = [braceIdx, bracketIdx].filter((i) => i >= 0);
        const startIdx = candidates.length ? Math.min(...candidates) : -1;
        if (startIdx >= 0) {
          const candidate = direct.slice(startIdx);
          try {
            queue.push(JSON.parse(candidate));
          } catch {
            // ignore parse failure and continue
          }
        }
      }
      continue;
    }

    if (Array.isArray(raw)) {
      // If the raw payload is already a list of todo-like objects, return it.
      return raw;
    }

    if (typeof raw === 'object') {
      if (Array.isArray(raw.todos)) return raw.todos;
      if (Array.isArray((raw as any).result?.todos)) return (raw as any).result.todos;
      if (Array.isArray((raw as any).items)) return (raw as any).items;
      if (Array.isArray((raw as any).steps)) return (raw as any).steps;
      if (Array.isArray((raw as any).value)) return (raw as any).value;
      // Explore nested containers for todos
      const nestedKeys = ['output', 'data', 'result', 'payload', 'content'];
      nestedKeys.forEach((key) => {
        if (raw && typeof raw === 'object' && key in raw) {
          queue.push((raw as any)[key]);
        }
      });
    }
  }
  return [];
};

const parseStructuredLogSegments = (content: string): any[] | null => {
  const trimmed = stripCodeFence(content);
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) {
    return null;
  }

  try {
    const parsed = JSON.parse(trimmed);
    const segments = Array.isArray(parsed)
      ? parsed
      : Array.isArray((parsed as any).sections)
        ? (parsed as any).sections
        : Array.isArray((parsed as any).items)
          ? (parsed as any).items
          : Array.isArray((parsed as any).segments)
            ? (parsed as any).segments
            : null;
    if (!segments || !Array.isArray(segments)) return null;
    const normalized = segments.filter((seg) => typeof seg === 'object');
    return normalized.length ? normalized : null;
  } catch {
    return null;
  }
};

const formatStructuredLogSegments = (segments: any[]): string => {
  return segments.map((seg, idx) => {
    const lineRange = seg.line_range || seg.lines || seg.range || seg.lineRange;
    const relevance = seg.relevance || seg.summary || seg.description;
    const keyInfo = seg.key_info || seg.key || seg.detail || seg.info;
    const parts = [];
    if (lineRange) parts.push(`Lines ${lineRange}`);
    if (relevance) parts.push(String(relevance));
    if (keyInfo) parts.push(`Key: ${keyInfo}`);
    return `${idx + 1}. ${parts.filter(Boolean).join(' — ')}`;
  }).join('\n');
};

const formatIfStructuredLog = (content: any): string | null => {
  const normalized = typeof content === 'string'
    ? content
    : Array.isArray(content)
      ? content
          .map((part) => (typeof part === 'string' ? part : (part && typeof part === 'object' && typeof (part as any).text === 'string') ? (part as any).text : ''))
          .join('')
      : '';
  if (!normalized) return null;
  const segments = parseStructuredLogSegments(normalized);
  if (!segments) return null;
  return formatStructuredLogSegments(segments);
};

const normalizeTraceStep = (raw: any): TraceStep => {
  const id = raw?.id ? String(raw.id) : crypto.randomUUID();
  const timestampValue = raw?.timestamp
    ? new Date(raw.timestamp).toISOString()
    : new Date().toISOString();
  const typeValue = (raw?.type as TraceStep['type']) || 'thought';
  const contentValue = typeof raw?.content === 'string'
    ? raw.content
    : JSON.stringify(raw?.content ?? '');

  return {
    id,
    type: typeValue,
    timestamp: timestampValue,
    content: contentValue,
    metadata: raw?.metadata ?? {},
  };
};

const mapTraceList = (rawList: any[]): TraceStep[] => rawList.map(normalizeTraceStep);

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
  agent
}: AgentProviderProps) {
  const [messages, setMessages] = useState<Message[]>(agent.messages || []);
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

    try {
      // Create abort controller for this request
      abortControllerRef.current = new AbortController();

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

      // Add user message to agent's message list
      agent.addMessage(userMessage);
      // Don't add to local state yet - let onMessagesChanged handle it

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
        model: stateModel || 'gemini-2.5-flash',
        agent_type: stateAgentType,
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
          if (agentType === 'log_analysis') {
            const formatted = formatIfStructuredLog(buffer);
            if (formatted) {
              buffer = formatted;
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
          let messagesWithIds = agentMessages.map(msg => ({
            ...msg,
            id: msg.id || crypto.randomUUID(),
          }));
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
            const hasAssistant = messagesWithIds.some((m) => m.role === 'assistant');
            const last = messagesWithIds[messagesWithIds.length - 1];
            if (!hasAssistant && last && last.role === 'tool') {
              const formatted = inferredLogAnalysis || formatLogAnalysisResult(last.content);
              if (formatted) {
                messagesWithIds.push({
                  id: crypto.randomUUID(),
                  role: 'assistant',
                  content: formatted,
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
                const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
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

          setMessages(nextMessages);
        },

          // Handle custom events (interrupts, timeline updates, tool evidence)
          onCustomEvent: (({ event }: any) => {
          if (event.name === 'interrupt' || event.name === 'human_input_required') {
            const payload = event.value as InterruptPayload;
            setInterrupt(payload);

            // Return a promise that will be resolved by user action
            return new Promise<string>((resolve) => {
              interruptResolverRef.current = resolve;
            });
          }

          if (event.name === 'agent_timeline_update') {
            const value = event.value || {};
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
            const value = event.value || {};
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
            const value = event.value || {};
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
            const payload = (event.value ?? event.data ?? {}) as any;
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
            const payload = event.value as ImageArtifactEvent;
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
            }
          } else if (event.name === 'article_artifact') {
            // Handle article artifact for research reports, articles with images
            const artPayload = event.value as { id: string; title: string; content: string };
            console.debug('[AG-UI] Article artifact event:', artPayload?.title, 'length:', artPayload?.content?.length);
            const payload = event.value as { id: string; type: string; title: string; content: string; messageId: string };
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
    }
  }, [agent, isStreaming]);

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
