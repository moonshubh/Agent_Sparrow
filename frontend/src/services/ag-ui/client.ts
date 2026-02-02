/**
 * AG-UI Client Configuration
 *
 * This module provides configuration and utilities for CopilotKit integration.
 * CopilotKit v1.50 uses native AG-UI protocol for streaming.
 */

import type { AttachmentInput } from './types';
import { supabase } from '@/services/supabase';
import { getAuthToken as getLocalToken } from '@/services/auth/local-auth';

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export const AGUI_STREAM_URL = `${API_URL}/api/v1/agui/stream`;
const MAX_SSE_BUFFER_SIZE = 10_000_000; // 10MB

function isAbortError(err: unknown): boolean {
  const e = err as any;
  if (!e) return false;
  if (e.name === 'AbortError') return true;
  if (e.name === 'CanceledError') return true;
  if (typeof DOMException !== 'undefined' && err instanceof DOMException && err.name === 'AbortError') return true;
  return false;
}

export interface AgentConfig {
  sessionId: string;
  traceId: string;
  provider?: string;
  model?: string;
  agentType?: string;
  useServerMemory?: boolean;
  attachments?: AttachmentInput[];
}

/**
 * Get initial agent state for CopilotKit
 */
export function getInitialAgentState(config: AgentConfig): Record<string, unknown> {
  return {
    session_id: config.sessionId,
    trace_id: config.traceId,
    provider: config.provider || 'google',
    model: config.model || 'gemini-3-flash-preview',
    agent_type: config.agentType,
    use_server_memory: config.useServerMemory ?? true,
    attachments: config.attachments || [],
  };
}

/**
 * Get auth token from localStorage or sessionStorage
 */
export async function getAuthToken(): Promise<string> {
  if (typeof window === 'undefined') {
    return '';
  }

  const localBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true';
  if (localBypass) {
    const localToken = getLocalToken();
    if (localToken) {
      return localToken;
    }
  }

  try {
    const { data } = await supabase.auth.getSession();
    const supaToken = data.session?.access_token;
    if (supaToken) {
      return supaToken;
    }
  } catch {
    // Ignore and fall back to local storage tokens.
  }

  const token = localStorage.getItem('authToken');
  if (token) return token;

  const sessionToken = sessionStorage.getItem('authToken');
  if (sessionToken) return sessionToken;

  return '';
}

/**
 * Get headers for AG-UI streaming requests
 */
export async function getStreamHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  };

  const authToken = await getAuthToken();
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  return headers;
}

// Message type for CopilotKit compatibility
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  name?: string;
  tool_call_id?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

// RunAgentInput type for CopilotKit compatibility
export interface RunAgentInput {
  threadId?: string;
  runId?: string;
  state?: Record<string, unknown>;
  messages?: Message[];
  tools?: unknown[];
  context?: unknown[];
  forwardedProps?: Record<string, unknown>;
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

/**
 * Agent interface for streaming communication
 */
export interface SparrowAgent {
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
 * Create a Sparrow agent for streaming communication.
 *
 * This creates an agent that communicates with the backend via SSE streaming.
 * The agent maintains local message state and forwards requests to the AG-UI endpoint.
 */
export function createSparrowAgent(config: AgentConfig): SparrowAgent {
  let messages: Message[] = [];
  let state: Record<string, unknown> = getInitialAgentState(config);
  let abortController: AbortController | null = null;

  const agent: SparrowAgent = {
    get messages() {
      return messages;
    },
    set messages(newMessages: Message[]) {
      messages = newMessages;
    },

    get state() {
      return state;
    },
    set state(newState: Record<string, unknown>) {
      state = newState;
    },

    addMessage(message: Message) {
      messages = [...messages, message];
    },

    setState(newState: Record<string, unknown>) {
      state = { ...state, ...newState };
    },

    async runAgent(input: Partial<RunAgentInput>, handlers: AgentEventHandlers) {
      const localAbortController = new AbortController();
      abortController = localAbortController;

      if (handlers.signal) {
        if (handlers.signal.aborted) {
          localAbortController.abort();
        } else {
          handlers.signal.addEventListener('abort', () => localAbortController.abort(), { once: true });
        }
      }

      try {
        const response = await fetch(AGUI_STREAM_URL, {
          method: 'POST',
          headers: await getStreamHeaders(),
          body: JSON.stringify({
            threadId: config.sessionId,
            runId: crypto.randomUUID(),
            state,
            messages,
            tools: input.tools || [],
            context: input.context || [],
            forwardedProps: input.forwardedProps || {},
          }),
          signal: localAbortController.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let textMessageBuffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          if (buffer.length > MAX_SSE_BUFFER_SIZE) {
            console.error('[SparrowAgent] SSE buffer overflow');
            await reader.cancel();
            localAbortController.abort();
            throw new Error('Response too large. Please try with smaller attachments.');
          }
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') continue;

              try {
                const event = JSON.parse(data);
                await processEvent(event, handlers, textMessageBuffer, (newBuffer) => {
                  textMessageBuffer = newBuffer;
                });
              } catch (err) {
                console.warn('[SparrowAgent] Failed to parse SSE event:', err);
              }
            }
          }
        }
      } catch (err) {
        if (!isAbortError(err)) {
          handlers.onRunFailed?.({ error: err });
        }
        throw err;
      }
    },

    abortRun() {
      abortController?.abort();
    },
  };

  return agent;
}

/**
 * Process a single SSE event
 */
async function processEvent(
  event: Record<string, unknown>,
  handlers: AgentEventHandlers,
  textMessageBuffer: string,
  setTextBuffer: (buffer: string) => void
): Promise<void> {
  const eventType = event.type || event.event;

  switch (eventType) {
    case 'TEXT_MESSAGE_CONTENT':
    case 'text_message_content': {
      const delta = (event.delta || event.content || '') as string;
      const newBuffer = textMessageBuffer + delta;
      setTextBuffer(newBuffer);
      handlers.onTextMessageContentEvent?.({ event, textMessageBuffer: newBuffer });
      break;
    }

    case 'MESSAGES_SNAPSHOT':
    case 'messages_snapshot': {
      const msgs = (event.messages || []) as Message[];
      handlers.onMessagesChanged?.({ messages: msgs });
      break;
    }

    case 'CUSTOM':
    case 'custom':
    case 'on_custom_event': {
      await handlers.onCustomEvent?.({ event });
      break;
    }

    case 'STATE_SNAPSHOT':
    case 'state_snapshot': {
      handlers.onStateChanged?.({ state: event.state || event });
      break;
    }

    case 'TOOL_CALL_START':
    case 'tool_call_start': {
      handlers.onToolCallStartEvent?.({ event });
      break;
    }

    case 'TOOL_CALL_END':
    case 'tool_call_end':
    case 'TOOL_CALL_RESULT':
    case 'tool_call_result': {
      handlers.onToolCallResultEvent?.({ event });
      break;
    }

    case 'RUN_ERROR':
    case 'run_error': {
      const rawError = event.error;
      const hasErrorObject =
        rawError &&
        typeof rawError === 'object' &&
        !Array.isArray(rawError) &&
        Object.keys(rawError as Record<string, unknown>).length > 0;

      const normalized =
        typeof rawError === 'string' && rawError.trim()
          ? rawError
          : typeof event.message === 'string' && event.message.trim()
            ? event.message
            : hasErrorObject
              ? rawError
              : event;

      handlers.onRunFailed?.({ error: normalized });
      break;
    }

    default:
      // Unknown event type, check if it has name/value for custom events
      if (event.name && (event.value !== undefined || event.data !== undefined)) {
        await handlers.onCustomEvent?.({ event });
      }
  }
}
