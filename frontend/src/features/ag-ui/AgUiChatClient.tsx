'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { createSparrowAgent } from '@/services/ag-ui/client';
import { AgentProvider } from '@/features/ag-ui/AgentContext';
import { ChatContainer } from '@/features/ag-ui/ChatContainer';
import { InterruptHandler } from '@/features/ag-ui/InterruptHandler';
import { sessionsAPI } from '@/services/api/endpoints/sessions';
import {
  modelsAPI,
  Provider,
  ProviderAvailability,
  ProviderModels,
} from '@/services/api/endpoints/models';
import { useAgentSelection } from '@/features/ag-ui/hooks/useAgentSelection';
import { v4 as uuidv4 } from 'uuid';

// Default models by provider
const DEFAULT_MODELS: Record<Provider, string> = {
  google: 'gemini-2.5-flash',
  xai: 'grok-4-1-fast-reasoning',
};

// Model descriptions by provider
const MODEL_HELPERS: Record<Provider, string> = {
  google: 'Gemini Flash balances speed and cost for orchestrating subagents.',
  xai: 'Grok 4.1 Fast provides advanced reasoning with 2M context window.',
};

type SparrowAgent = ReturnType<typeof createSparrowAgent>;

export default function AgUiChatClient() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const { selected: agentType, choose: setAgentType } = useAgentSelection();
  const [agent, setAgent] = useState<SparrowAgent | null>(null);

  // Provider state
  const [provider, setProvider] = useState<Provider>('google');
  const [availableProviders, setAvailableProviders] = useState<ProviderAvailability>({
    google: true,
    xai: false,
  });
  const [providerModels, setProviderModels] = useState<ProviderModels>({
    google: ['gemini-2.5-flash', 'gemini-2.5-pro'],
  });

  // Model state (per provider)
  const [modelByProvider, setModelByProvider] = useState<Partial<Record<Provider, string>>>({
    google: DEFAULT_MODELS.google,
    xai: DEFAULT_MODELS.xai,
  });

  const [memoryEnabled, setMemoryEnabled] = useState(true);

  // Current active model for the selected provider
  const activeModel = modelByProvider[provider] || DEFAULT_MODELS[provider];
  const availableModels = providerModels[provider] || [DEFAULT_MODELS[provider]];
  const modelHelperText = MODEL_HELPERS[provider];
  const recommendedModel = DEFAULT_MODELS[provider];

  const latestConfigRef = useRef({
    provider,
    model: activeModel,
    agentType,
    memoryEnabled,
  });

  // Capture initial provider for one-time fetch to avoid stale closure
  const initialProviderRef = useRef(provider);

  useEffect(() => {
    latestConfigRef.current = {
      provider,
      model: activeModel,
      agentType,
      memoryEnabled,
    };
  }, [provider, activeModel, agentType, memoryEnabled]);

  // Fetch available providers on mount
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const providers = await modelsAPI.getAvailableProviders();
        setAvailableProviders(providers);

        // Use ref to avoid stale closure - check if initial provider is available
        const currentProvider = initialProviderRef.current;
        if (!providers[currentProvider]) {
          const firstAvailable = (Object.keys(providers) as Provider[]).find(
            (p) => providers[p]
          );
          if (firstAvailable) {
            setProvider(firstAvailable);
          }
        }
      } catch (err) {
        console.debug('Failed to fetch providers, using defaults:', err);
      }
    };

    fetchProviders();
  }, []);

  // Fetch models when provider changes
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const models = await modelsAPI.list('primary');
        setProviderModels(models);
      } catch (err) {
        console.debug('Failed to fetch models, using defaults:', err);
      }
    };

    fetchModels();
  }, [provider]);

  // Create session on mount
  useEffect(() => {
    if (sessionId) {
      return;
    }

    const createSession = async () => {
      setIsCreating(true);
      try {
        const session = await sessionsAPI.create('primary', 'New Chat');
        setSessionId(String(session.id));
      } catch (err) {
        console.error('Failed to create session:', err);
        setError(err as Error);
      } finally {
        setIsCreating(false);
      }
    };

    createSession();
  }, [sessionId]);

  // Initialize the AG-UI agent when session or config changes
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
        provider: config.provider,
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
  }, [sessionId, provider, activeModel, agentType, memoryEnabled]);

  const handleModelChange = useCallback((nextModel: string) => {
    setModelByProvider((prev) => ({
      ...prev,
      [provider]: nextModel,
    }));
  }, [provider]);

  const handleProviderChange = useCallback((nextProvider: Provider) => {
    setProvider(nextProvider);
    // Model will be auto-selected from modelByProvider state
  }, []);

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

  return (
    <AgentProvider agent={agent}>
      <InterruptHandler />
      <ChatContainer
        sessionId={sessionId}
        agentType={agentType}
        onAgentChange={setAgentType}
        provider={provider}
        onProviderChange={handleProviderChange}
        availableProviders={availableProviders}
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
