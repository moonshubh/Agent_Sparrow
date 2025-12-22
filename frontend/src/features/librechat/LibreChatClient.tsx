/**
 * LibreChat-style Chat Client
 *
 * ChatGPT-like UI that integrates with our AG-UI backend.
 * Uses createSparrowAgent for direct SSE streaming with AgentProvider.
 */

'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { createSparrowAgent, type SparrowAgent, type Message } from '@/services/ag-ui/client';
import { sessionsAPI, type ChatMessageRecord } from '@/services/api/endpoints/sessions';
import { modelsAPI, Provider } from '@/services/api/endpoints/models';
import { AgentProvider } from '@/features/librechat/AgentContext';
import { ArtifactProvider } from '@/features/librechat/artifacts';
import { LibreChatView } from './components/LibreChatView';

// Convert backend message format to frontend Message format
function convertToMessage(record: ChatMessageRecord): Message {
  return {
    id: String(record.id),
    role: record.message_type === 'tool' ? 'tool' : record.message_type,
    content: record.content,
    metadata: record.metadata || undefined,
  };
}

// Default models by provider
const DEFAULT_MODELS: Record<Provider, string> = {
  google: 'gemini-3-flash-preview',
  xai: 'grok-4-1-fast-reasoning',
  openrouter: 'x-ai/grok-4.1-fast:free',
};

interface Conversation {
  id: string;
  title: string;
  timestamp?: Date;
}

export default function LibreChatClient() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string>('');
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Agent state
  const [agent, setAgent] = useState<SparrowAgent | null>(null);

  // Provider state
  const [provider, setProvider] = useState<Provider>('google');
  const [model, setModel] = useState<string>(DEFAULT_MODELS.google);

  // Conversation history
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | undefined>();
  const initializedRef = useRef(false);

  const initialize = useCallback(async () => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    setIsCreating(true);
    setError(null);

    try {
      // Fetch available providers
      let activeProvider: Provider = 'google';
      let activeModel: string = DEFAULT_MODELS.google;

      try {
        const providers = await modelsAPI.getAvailableProviders();
        const availableProvider = Object.entries(providers).find(([, available]) => available)?.[0] as Provider | undefined;
        if (availableProvider) {
          activeProvider = availableProvider;
          activeModel = DEFAULT_MODELS[availableProvider];
          setProvider(activeProvider);
          setModel(activeModel);
        }
      } catch (err) {
        console.debug('Failed to fetch providers, using defaults:', err);
      }

      // Load existing sessions from backend
      let existingSessions: Conversation[] = [];
      try {
        const sessions = await sessionsAPI.list(50, 0);
        existingSessions = sessions.map((s) => ({
          id: String(s.id),
          title: s.title || 'Untitled Chat',
          timestamp: s.created_at ? new Date(s.created_at) : undefined,
        }));
      } catch (err) {
        console.debug('Failed to load existing sessions:', err);
      }

      // If we have existing sessions, use the most recent one
      if (existingSessions.length > 0) {
        setConversations(existingSessions);
        const mostRecent = existingSessions[0];

        // Load messages for the most recent session
        let messages: Message[] = [];
        try {
          const messageRecords = await sessionsAPI.listMessages(mostRecent.id, 100, 0);
          messages = messageRecords.map(convertToMessage);
        } catch (err) {
          console.debug('Failed to load messages:', err);
        }

        const newTraceId = `trace-${mostRecent.id}`;
        const newAgent = createSparrowAgent({
          sessionId: mostRecent.id,
          traceId: newTraceId,
          provider: activeProvider,
          model: activeModel,
          agentType: 'primary',
        });

        // Set loaded messages on the agent
        newAgent.messages = messages;

        setSessionId(mostRecent.id);
        setTraceId(newTraceId);
        setAgent(newAgent);
        setCurrentConversationId(mostRecent.id);
      } else {
        // No existing sessions, create a new one in backend
        const backendSession = await sessionsAPI.create('primary', 'New Chat');
        const newSessionId = String(backendSession.id);
        const newTraceId = `trace-${newSessionId}`;

        const newAgent = createSparrowAgent({
          sessionId: newSessionId,
          traceId: newTraceId,
          provider: activeProvider,
          model: activeModel,
          agentType: 'primary',
        });

        setSessionId(newSessionId);
        setTraceId(newTraceId);
        setAgent(newAgent);
        setCurrentConversationId(newSessionId);
        setConversations([{
          id: newSessionId,
          title: 'New Chat',
          timestamp: new Date(),
        }]);
      }

    } catch (err) {
      console.error('Failed to initialize:', err);
      setError(err instanceof Error ? err : new Error('Failed to initialize'));
    } finally {
      setIsCreating(false);
    }
  }, []);

  // Load existing sessions and initialize
  useEffect(() => {
    void initialize();
  }, [initialize]);

  const handleRetry = useCallback(() => {
    initializedRef.current = false;
    setSessionId(null);
    setTraceId('');
    setAgent(null);
    setCurrentConversationId(undefined);
    setConversations([]);
    setError(null);
    void initialize();
  }, [initialize]);

  // Handle new chat
  const handleNewChat = useCallback(async () => {
    try {
      // Create session in backend and use its ID
      const backendSession = await sessionsAPI.create('primary', 'New Chat');
      const newSessionId = String(backendSession.id);
      const newTraceId = `trace-${newSessionId}`;

      // Create new agent with backend's session ID
      const newAgent = createSparrowAgent({
        sessionId: newSessionId,
        traceId: newTraceId,
        provider,
        model,
        agentType: 'primary',
      });

      setSessionId(newSessionId);
      setTraceId(newTraceId);
      setAgent(newAgent);
      setCurrentConversationId(newSessionId);

      // Add to conversations
      setConversations((prev) => [
        {
          id: newSessionId,
          title: 'New Chat',
          timestamp: new Date(),
        },
        ...prev,
      ]);
    } catch (err) {
      console.error('Failed to create new chat:', err);
    }
  }, [provider, model]);

  // Handle conversation selection
  const handleSelectConversation = useCallback(async (conversationId: string) => {
    if (conversationId === currentConversationId) return;

    try {
      // Load messages for the selected conversation
      let messages: Message[] = [];
      try {
        const messageRecords = await sessionsAPI.listMessages(conversationId, 100, 0);
        messages = messageRecords.map(convertToMessage);
      } catch (err) {
        console.debug('Failed to load messages for conversation:', err);
      }

      // Create agent for selected conversation
      const selectedTraceId = `trace-${conversationId}`;
      const newAgent = createSparrowAgent({
        sessionId: conversationId,
        traceId: selectedTraceId,
        provider,
        model,
        agentType: 'primary',
      });

      // Set loaded messages on the agent
      newAgent.messages = messages;

      setSessionId(conversationId);
      setTraceId(selectedTraceId);
      setAgent(newAgent);
      setCurrentConversationId(conversationId);
    } catch (err) {
      console.error('Failed to switch conversation:', err);
    }
  }, [currentConversationId, provider, model]);

  // Handle conversation rename
  const handleRenameConversation = useCallback(async (conversationId: string, newTitle: string) => {
    // Update local state immediately
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === conversationId ? { ...conv, title: newTitle } : conv
      )
    );

    // Persist to backend
    try {
      await sessionsAPI.rename(conversationId, newTitle);
    } catch (err) {
      console.error('Failed to rename conversation in backend:', err);
      // Optionally revert on error, but for now we keep the local change
    }
  }, []);

  // Handle conversation delete
  const handleDeleteConversation = useCallback(async (conversationId: string) => {
    // Capture remaining conversations via functional update to avoid stale closure
    let remainingConversations: Conversation[] = [];

    // Remove from local state and capture the remaining list
    setConversations((prev) => {
      remainingConversations = prev.filter((conv) => conv.id !== conversationId);
      return remainingConversations;
    });

    // Delete from backend
    try {
      await sessionsAPI.remove(conversationId);
    } catch (err) {
      console.error('Failed to delete conversation from backend:', err);
    }

    // If deleting current conversation, switch to another or create new
    if (conversationId === currentConversationId) {
      if (remainingConversations.length > 0) {
        // Switch to the first remaining conversation
        handleSelectConversation(remainingConversations[0].id);
      } else {
        // Create a new chat if no conversations left
        handleNewChat();
      }
    }
  }, [currentConversationId, handleSelectConversation, handleNewChat]);

  // Handle auto-naming of current conversation based on first message
  const handleAutoName = useCallback(async (title: string) => {
    if (!currentConversationId) return;

    // Update local state
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === currentConversationId ? { ...conv, title } : conv
      )
    );

    // Persist to backend
    try {
      await sessionsAPI.rename(currentConversationId, title);
    } catch (err) {
      console.debug('Failed to persist auto-name to backend:', err);
    }
  }, [currentConversationId]);

  // Loading state
  if (isCreating || !agent) {
    return (
      <div className="lc-layout" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="lc-tool-spinner" style={{ width: '32px', height: '32px', margin: '0 auto 16px' }} />
          <p style={{ color: 'var(--lc-text-secondary)', fontSize: '14px' }}>
            Initializing Agent Sparrow...
          </p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="lc-layout" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', maxWidth: '400px' }}>
          <p style={{ color: 'var(--lc-error)', fontSize: '14px', marginBottom: '16px' }}>
            Failed to initialize: {error.message}
          </p>
          <button
            onClick={handleRetry}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: 'var(--lc-accent)',
              color: 'white',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <ArtifactProvider>
      <AgentProvider agent={agent}>
        <LibreChatView
          sessionId={sessionId || undefined}
          onNewChat={handleNewChat}
          conversations={conversations}
          currentConversationId={currentConversationId}
          onSelectConversation={handleSelectConversation}
          onRenameConversation={handleRenameConversation}
          onDeleteConversation={handleDeleteConversation}
          onAutoName={handleAutoName}
        />
      </AgentProvider>
    </ArtifactProvider>
  );
}
