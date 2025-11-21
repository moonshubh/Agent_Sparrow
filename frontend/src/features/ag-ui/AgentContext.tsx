'use client';

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type { AbstractAgent } from '@ag-ui/client';
import type { Message, RunAgentInput } from '@ag-ui/core';
import type { DocumentPointer, AttachmentInput, InterruptPayload } from '@/services/ag-ui/types';
import type { TimelineOperation } from './timeline/AgenticTimelineView';
import type { TraceStep } from './types/thinkingTrace';
import { formatLogAnalysisResult } from './formatters/logFormatter';

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
}

const AgentContext = createContext<AgentContextValue | null>(null);

interface AgentProviderProps {
  children: React.ReactNode;
  agent: AbstractAgent;
}

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

      // Add user message to local state immediately
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
      };

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
      const forwardedProps: Record<string, any> = {
        // Prefer richer answers by default
        force_websearch: true,
      };

      // Run agent with streaming updates
      await agent.runAgent(
        {
          forwardedProps,
        },
        {
          signal: abortControllerRef.current.signal,

          // Handle streaming text content
          onTextMessageContentEvent: ({ event }: { event: any }) => {
          setMessages(prev => {
            const updated = [...prev];
            const lastMsg = updated[updated.length - 1];

            // If the last message is an assistant message, append to it
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.content = (lastMsg.content as string || '') + event.delta;
            } else {
              // Otherwise create a new assistant message
              updated.push({
                id: crypto.randomUUID(),
                role: 'assistant',
                content: event.delta,
              });
            }
            return updated;
          });
        },

          // Handle complete message updates
          onMessagesChanged: ({ messages: agentMessages }: { messages: any[] }) => {
          console.debug('[AG-UI] onMessagesChanged received:', agentMessages);
          // Ensure all messages have IDs
          const messagesWithIds = agentMessages.map(msg => ({
            ...msg,
            id: msg.id || crypto.randomUUID(),
          }));
          // If running the log analysis agent and the stream ended with a tool result, surface a readable assistant reply.
          const agentType = (agent?.state as any)?.agent_type || (agent?.state as any)?.agentType;
          if (agentType === 'log_analysis') {
            const hasAssistant = messagesWithIds.some((m) => m.role === 'assistant');
            const last = messagesWithIds[messagesWithIds.length - 1];
            if (!hasAssistant && last && last.role === 'tool') {
              const formatted = formatLogAnalysisResult(last.content);
              if (formatted) {
                messagesWithIds.push({
                  id: crypto.randomUUID(),
                  role: 'assistant',
                  content: formatted,
                });
              }
            }
          }
          if (messagesWithIds.length > 0) {
            const last = messagesWithIds[messagesWithIds.length - 1];
            console.debug('[AG-UI] onMessagesChanged last message:', {
              role: last?.role,
              preview: typeof last?.content === 'string' ? last.content.slice(0, 120) : last?.content,
            });
          }
          setMessages(messagesWithIds);
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
          } else if (event.name === 'tool_evidence_update') {
            const value = event.value || {};
            const id = value.toolCallId as string | undefined;
            if (id) {
              setToolEvidence((prev) => ({
                ...prev,
                [id]: value,
              }));
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
            const value = event.value || {};
            if (Array.isArray(value.todos)) {
              setTodos(value.todos);
            }
          }

          return undefined;
          }) as any,

          // Handle state changes (for debugging)
          onStateChanged: ({ state }: { state: any }) => {
            console.debug('[AG-UI] State changed:', state);
          },

          // Handle tool calls (for debugging + UI visibility)
          onToolCallStartEvent: ({ event }: { event: any }) => {
            console.debug('[AG-UI] Tool call started:', event.toolCallName, event.toolCallId);
            const id = event.toolCallId;
            const name = (event.toolCallName as string) || id || 'tool';
            toolNameByIdRef.current[id] = name;
            setActiveTools((prev) => (prev.includes(name) ? prev : [...prev, name]));
          },

          onToolCallResultEvent: ({ event }: { event: any }) => {
            console.debug('[AG-UI] Tool call result:', event.toolCallId);
            const id = event.toolCallId;
            const name = toolNameByIdRef.current[id];
            if (!name) {
              return;
            }
            delete toolNameByIdRef.current[id];
            setActiveTools((prev) => prev.filter((n) => n !== name));
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
