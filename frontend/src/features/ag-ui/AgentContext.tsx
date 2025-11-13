'use client';

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type { AbstractAgent } from '@ag-ui/client';
import type { Message, RunAgentInput } from '@ag-ui/core';
import type { DocumentPointer, AttachmentInput, InterruptPayload } from '@/services/ag-ui/types';

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
}

const AgentContext = createContext<AgentContextValue | null>(null);

interface AgentProviderProps {
  children: React.ReactNode;
  agent: AbstractAgent;
}

export function AgentProvider({
  children,
  agent
}: AgentProviderProps) {
  const [messages, setMessages] = useState<Message[]>(agent.messages || []);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [interrupt, setInterrupt] = useState<InterruptPayload | null>(null);
  const interruptResolverRef = useRef<((value: string) => void) | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (content: string, attachments?: AttachmentInput[]) => {
    if (!agent || isStreaming) return;

    setIsStreaming(true);
    setError(null);

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

      // Run agent with streaming updates
      await agent.runAgent(undefined, {
        signal: abortControllerRef.current.signal,

        // Handle streaming text content
        onTextMessageContentEvent: ({ event }) => {
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
        onMessagesChanged: ({ messages: agentMessages }) => {
          setMessages([...agentMessages]);
        },

        // Handle custom events (interrupts)
        onCustomEvent: ({ event }) => {
          if (event.name === 'interrupt' || event.name === 'human_input_required') {
            const payload = event.value as InterruptPayload;
            setInterrupt(payload);

            // Return a promise that will be resolved by user action
            return new Promise<string>((resolve) => {
              interruptResolverRef.current = resolve;
            });
          }
          return undefined;
        },

        // Handle state changes (for debugging)
        onStateChanged: ({ state }) => {
          console.debug('[AG-UI] State changed:', state);
        },

        // Handle tool calls (for debugging)
        onToolCallStartEvent: ({ event }) => {
          console.debug('[AG-UI] Tool call started:', event.toolName, event.args);
        },

        onToolCallResultEvent: ({ event }) => {
          console.debug('[AG-UI] Tool call result:', event.toolName, event.result);
        },

        // Handle errors
        onRunFailed: ({ error: runError }) => {
          console.error('[AG-UI] Run failed:', runError);
          setError(runError);
        },
      });

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