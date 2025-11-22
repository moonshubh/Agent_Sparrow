'use client';

import React, { useEffect, useState, useRef } from 'react';
import { createSparrowAgent } from '@/services/ag-ui/client';
import { AgentProvider } from '@/features/ag-ui/AgentContext';
import { ChatContainer } from '@/features/ag-ui/ChatContainer';
import { InterruptHandler } from '@/features/ag-ui/InterruptHandler';
import { sessionsAPI } from '@/services/api/endpoints/sessions';
import { useAgentSelection } from '@/features/ag-ui/hooks/useAgentSelection';
import { v4 as uuidv4 } from 'uuid';

const GEMINI_MODELS = [
  'gemini-2.5-flash',
  'gemini-2.5-flash-lite',
  'gemini-2.5-pro',
  'gemini-2.0-flash-exp',
] as const;

type AgentModelKey = 'primary' | 'log_analysis' | 'research';

const MODEL_DEFAULTS: Record<AgentModelKey, string> = {
  primary: GEMINI_MODELS[0],
  log_analysis: 'gemini-2.5-pro',
  research: GEMINI_MODELS[0],
};

const MODEL_OPTIONS: Record<AgentModelKey, string[]> = {
  primary: [...GEMINI_MODELS],
  research: [...GEMINI_MODELS],
  log_analysis: ['gemini-2.5-pro', 'gemini-2.5-flash'],
};

const MODEL_HELPERS: Record<AgentModelKey, string> = {
  primary: 'Flash balances speed and cost for orchestrating subagents.',
  log_analysis: 'Pro handles large log payloads; fall back to Flash if rate-limited.',
  research: 'Flash-lite is fastest for quick KB + web lookups.',
};

type SparrowAgent = ReturnType<typeof createSparrowAgent>;

export default function AgUiChatClient() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { selected: agentType, choose: setAgentType } = useAgentSelection();
  const [agent, setAgent] = useState<SparrowAgent | null>(null);

  const [modelSelections, setModelSelections] = useState<Record<AgentModelKey, string>>({
    primary: MODEL_DEFAULTS.primary,
    log_analysis: MODEL_DEFAULTS.log_analysis,
    research: MODEL_DEFAULTS.research,
  });
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const latestConfigRef = useRef({
    model: MODEL_DEFAULTS.primary,
    agentType,
    memoryEnabled,
  });

  const activeAgentKey: AgentModelKey = agentType === 'log_analysis'
    ? 'log_analysis'
    : agentType === 'research'
      ? 'research'
      : 'primary';
  const activeModel = modelSelections[activeAgentKey] || MODEL_DEFAULTS[activeAgentKey];
  const availableModels = MODEL_OPTIONS[activeAgentKey] || [...GEMINI_MODELS];
  const modelHelperText = MODEL_HELPERS[activeAgentKey];
  const recommendedModel = MODEL_DEFAULTS[activeAgentKey];

  useEffect(() => {
    latestConfigRef.current = {
      model: activeModel,
      agentType,
      memoryEnabled,
    };
  }, [activeModel, agentType, memoryEnabled]);

  // Create session on mount (keep the same session when agent type changes)
  useEffect(() => {
    if (sessionId) {
      return;
    }

    const createSession = async () => {
      setIsCreating(true);
      try {
        // Use primary as the default session type; routing is controlled via agent state
        const session = await sessionsAPI.create('primary', 'New Chat');
        setSessionId(String(session.id));
      } catch (err) {
        console.error('Failed to create session:', err);
        if (err && typeof err === 'object') {
          console.error('Error details:', JSON.stringify(err, Object.getOwnPropertyNames(err)));
        }
        setError(err as Error);
      } finally {
        setIsCreating(false);
      }
    };

    createSession();
  }, [sessionId]);

  // Initialize the AG-UI agent once per session
  useEffect(() => {
    if (!sessionId) {
      setAgent(null);
      return;
    }

    const config = latestConfigRef.current;
    const traceId = `trace-${sessionId}-${uuidv4()}`;
    try {
      const instance = createSparrowAgent({
        sessionId,
        traceId,
        provider: 'google',
        model: config.model,
        agentType: config.agentType === 'auto' ? undefined : config.agentType,
        useServerMemory: config.memoryEnabled,
      });
      setAgent(instance);
      setError(null);

      return () => {
        instance.abortRun();
      };
    } catch (err) {
      setAgent(null);
      setError(err as Error);
    }
  }, [sessionId, activeModel, agentType, memoryEnabled]);

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
  if (error) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
        <div className="text-center max-w-md p-6 bg-white rounded-lg shadow-lg">
          <h2 className="text-2xl font-bold text-red-600 mb-2">Session Error</h2>
          <p className="text-slate-600 mb-4">
            {error.message || 'Failed to create chat session'}
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

  if (!sessionId || !agent) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-800 mx-auto mb-4" />
          <p className="text-slate-600">Preparing agent...</p>
        </div>
      </div>
    );
  }

  const handleModelChange = (nextModel: string) => {
    setModelSelections((prev) => ({
      ...prev,
      [activeAgentKey]: nextModel,
    }));
  };

  return (
    <AgentProvider agent={agent}>
      <InterruptHandler />
      <ChatContainer
        sessionId={sessionId}
        agentType={agentType}
        onAgentChange={setAgentType}
        model={activeModel}
        onModelChange={handleModelChange}
        memoryEnabled={memoryEnabled}
        onMemoryToggle={setMemoryEnabled}
        models={availableModels}
        modelHelperText={modelHelperText}
        recommendedModel={recommendedModel}
      />
    </AgentProvider>
  );
}
