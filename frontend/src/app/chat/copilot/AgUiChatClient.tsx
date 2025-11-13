'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { createSparrowAgent } from '@/services/ag-ui/client';
import { AgentProvider } from '@/features/ag-ui/AgentContext';
import { ChatContainer } from '@/features/ag-ui/ChatContainer';
import { InterruptHandler } from '@/features/ag-ui/InterruptHandler';
import { sessionsAPI } from '@/services/api/endpoints/sessions';
import { useAgentSelection } from '@/features/chat/hooks/useAgentSelection';
import { v4 as uuidv4 } from 'uuid';

export default function AgUiChatClient() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { selected: agentType, choose: setAgentType } = useAgentSelection();

  const GEMINI_MODELS = [
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-2.0-flash-exp',
  ];

  const [model, setModel] = useState(GEMINI_MODELS[0]);
  const [memoryEnabled, setMemoryEnabled] = useState(true);

  // Create session on mount
  useEffect(() => {
    const createSession = async () => {
      setIsCreating(true);
      try {
        const session = await sessionsAPI.create(
          agentType === 'auto' ? 'primary' : agentType,
          'New Chat'
        );
        setSessionId(String(session.id));
      } catch (err) {
        console.error('Failed to create session:', err);
        setError(err as Error);
      } finally {
        setIsCreating(false);
      }
    };

    createSession();
  }, []); // Only run once on mount

  // Create agent instance
  const agent = useMemo(() => {
    if (!sessionId) return null;

    try {
      return createSparrowAgent({
        sessionId,
        traceId: `trace-${Date.now()}-${uuidv4()}`,
        provider: 'google',
        model,
        agentType: agentType === 'auto' ? undefined : agentType,
        useServerMemory: memoryEnabled,
      });
    } catch (err) {
      console.error('Failed to create agent:', err);
      setError(err as Error);
      return null;
    }
  }, [sessionId, model, agentType, memoryEnabled]);

  // Loading state
  if (isCreating) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-800 mx-auto mb-4" />
          <p className="text-slate-600">Initializing session...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !agent) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
        <div className="text-center max-w-md p-6 bg-white rounded-lg shadow-lg">
          <h2 className="text-2xl font-bold text-red-600 mb-2">Session Error</h2>
          <p className="text-slate-600 mb-4">
            {error?.message || 'Failed to create chat session'}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-slate-800 text-white rounded hover:bg-slate-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Model options by provider
  return (
    <AgentProvider agent={agent}>
      <InterruptHandler />
      <ChatContainer
        sessionId={sessionId}
        agentType={agentType}
        onAgentChange={setAgentType}
        model={model}
        onModelChange={setModel}
        memoryEnabled={memoryEnabled}
        onMemoryToggle={setMemoryEnabled}
        models={GEMINI_MODELS}
      />
    </AgentProvider>
  );
}