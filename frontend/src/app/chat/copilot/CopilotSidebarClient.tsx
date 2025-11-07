"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useCopilotChat, useCopilotReadable } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";
import { sessionsAPI } from "@/services/api/endpoints/sessions";
import { useCopilotDocuments, DocumentPointer } from "@/features/global-knowledge/hooks/useCopilotDocuments";
import { useCopilotSuggestions, Suggestion } from "@/features/chat/hooks/useCopilotSuggestions";
import { CopilotSuggestionsContext } from "./CopilotSuggestionsContext";
import { ChatHeader } from "./ChatHeader";
import { ChatActions } from "./ChatActions";
import { ChatInterrupts } from "./ChatInterrupts";
import { useAgentSelection } from "@/features/chat/hooks/useAgentSelection";

/**
 * FINAL REFACTOR - NO BRIDGES
 *
 * All logic consolidated into single component:
 * - No CopilotKnowledgeBridge
 * - No CopilotSuggestionsBridge
 * - Direct hook usage
 * - Single source of truth
 * - No circular dependencies possible
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const SESSION_BOOTSTRAP_TIMEOUT_MS = 10000;

/**
 * Inner component that USES CopilotKit hooks
 * Must be rendered inside CopilotKit provider
 */
function CopilotSidebarContent({ sessionId }: { sessionId: string }) {
  // ========================================================================
  // User Preferences
  // ========================================================================
  const [provider, setProvider] = useState<string>("google");
  const [model, setModel] = useState<string>("gemini-2.5-flash");
  const [memoryEnabled, setMemoryEnabled] = useState<boolean>(true);
  const hasReadPrefsRef = useRef(false);

  // ========================================================================
  // Agent Selection
  // ========================================================================
  const { selected: agentType, choose: setAgentType } = useAgentSelection();

  // ========================================================================
  // CopilotKit Hooks
  // ========================================================================
  const chat = useCopilotChat() as any;
  const { registerForTurn, invalidateCache } = useCopilotDocuments();

  // ========================================================================
  // Document State (formerly in CopilotKnowledgeBridge)
  // ========================================================================
  const [documents, setDocuments] = useState<DocumentPointer[]>([]);
  const lastQueryRef = useRef<string>('');
  const processedMessageIdsRef = useRef<Set<string>>(new Set());

  // ========================================================================
  // Suggestions Hook (formerly bridged via CopilotSuggestionsBridge)
  // ========================================================================
  const { suggestions, isGenerating, handleSuggestionClick, clearSuggestions } = useCopilotSuggestions({
    agentType: agentType === "auto" ? "primary" : agentType,
    availableDocuments: documents,
  });

  // ========================================================================
  // Extract message content utility
  // ========================================================================
  const extractContent = useCallback((content: unknown): string => {
    if (typeof content === 'string') return content;

    if (Array.isArray(content)) {
      return content
        .map((part) => {
          if (typeof part === 'string') return part;
          if (typeof part === 'object' && part !== null) {
            const maybeText = (part as { text?: string; value?: string }).text;
            const maybeValue = (part as { text?: string; value?: string }).value;
            return maybeText || maybeValue || '';
          }
          return '';
        })
        .join(' ');
    }

    if (typeof content === 'object' && content !== null) {
      const candidate = content as { text?: string };
      if (typeof candidate.text === 'string') return candidate.text;
    }

    return '';
  }, []);



  // ========================================================================
  // Read preferences
  // ========================================================================
  useEffect(() => {
    if (!sessionId || hasReadPrefsRef.current) return;
    hasReadPrefsRef.current = true;

    try {
      const sessionKey = `chat:prefs:${sessionId}`;
      const raw = localStorage.getItem(sessionKey);

      if (raw) {
        const prefs = JSON.parse(raw);
        if (prefs.provider) setProvider(prefs.provider);
        if (prefs.model) setModel(prefs.model);
      } else {
        const globalKey = `copilot:last-model:${agentType}`;
        const lastModel = localStorage.getItem(globalKey);
        if (lastModel) setModel(lastModel);
      }
    } catch (error) {
      console.warn("Failed to read preferences:", error);
    }
  }, [sessionId, agentType]);

  // ========================================================================
  // Write preferences
  // ========================================================================
  useEffect(() => {
    if (!sessionId || !hasReadPrefsRef.current) return;

    try {
      const sessionKey = `chat:prefs:${sessionId}`;
      localStorage.setItem(sessionKey, JSON.stringify({ provider, model }));

      const globalKey = `copilot:last-model:${agentType}`;
      localStorage.setItem(globalKey, model);
    } catch (error) {
      console.warn("Failed to write preferences:", error);
    }
  }, [provider, model, sessionId, agentType]);

  // ========================================================================
  // Watch messages and register documents
  // CONSOLIDATED: formerly in CopilotKnowledgeBridge
  // ========================================================================
  useEffect(() => {
    if (!sessionId || !chat?.messages) return;

    const messages = chat.messages as Array<{
      id?: string;
      messageId?: string;
      role: string;
      content: unknown;
      createdAt?: string;
    }>;

    const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user');

    if (!lastUserMessage) return;

    const messageKey =
      lastUserMessage.id ||
      lastUserMessage.messageId ||
      `${lastUserMessage.role}:${lastUserMessage.createdAt ?? ''}:${lastUserMessage.content ?? ''}`;

    if (processedMessageIdsRef.current.has(messageKey)) return;

    const content = extractContent(lastUserMessage.content).trim();

    if (!content) {
      processedMessageIdsRef.current.add(messageKey);
      return;
    }

    // Check if this is a new query
    if (content === lastQueryRef.current) {
      processedMessageIdsRef.current.add(messageKey);
      return;
    }

    lastQueryRef.current = content;
    processedMessageIdsRef.current.add(messageKey);

    // Register documents directly (no callback)
    registerForTurn({
      query: content,
      agentType: agentType === "auto" ? "primary" : agentType,
      sessionId,
      kbEnabled: true,
      feedmeEnabled: true,
    })
      .then((newDocuments) => {
        setDocuments(newDocuments);
        console.log(`[CopilotSidebarClient] Registered ${newDocuments.length} documents`);
      })
      .catch((error) => {
        console.error('[CopilotSidebarClient] Error registering documents:', error);
      });
  }, [sessionId, chat?.messages, extractContent, registerForTurn, agentType]);

  // ========================================================================
  // Reset on session change
  // ========================================================================
  useEffect(() => {
    processedMessageIdsRef.current.clear();
    lastQueryRef.current = '';
    setDocuments([]);
  }, [sessionId]);

  // ========================================================================
  // Invalidate cache on unmount
  // ========================================================================
  useEffect(() => {
    return () => {
      if (sessionId) {
        invalidateCache(sessionId);
      }
    };
  }, [sessionId, invalidateCache]);

  // ========================================================================
  // Format documents for CopilotKit
  // ========================================================================
  const formattedDocuments = useMemo(() => {
    if (documents.length === 0) return [];

    return documents.map((doc) => ({
      id: doc.documentId,
      title: doc.title,
      content: doc.content,
      description: doc.description || '',
      categories: doc.categories || [],
      source: doc.source,
    }));
  }, [documents]);

  // ========================================================================
  // Register documents with CopilotKit
  // ========================================================================
  useCopilotReadable({
    description: 'Available knowledge base and support documents',
    value: formattedDocuments,
    categories: ['knowledge'],
  });

  // ========================================================================
  // CopilotKit properties
  // ========================================================================
  const copilotProperties = useMemo(() => {
    const props: Record<string, any> = {
      session_id: sessionId,
      provider: provider,
      model: model,
    };

    if (agentType !== "auto") {
      props.agent_type = agentType;
    }

    return props;
  }, [sessionId, provider, model, agentType]);

  // ========================================================================
  // Observability hooks
  // ========================================================================
  const observabilityHooks = useMemo(
    () => ({
      onMessageSent: () => console.log("Message sent"),
      onChatStarted: () => console.log("Chat started"),
      onChatStopped: () => console.log("Chat stopped"),
      onFeedbackGiven: () => console.log("Feedback given"),
    }),
    []
  );

  // ========================================================================
  // Suggestions context value
  // ========================================================================
  const suggestionsContextValue = useMemo(
    () => ({
      suggestions,
      isGenerating,
      onSuggestionSelected: handleSuggestionClick,
      clearSuggestions,
    }),
    [suggestions, isGenerating, handleSuggestionClick, clearSuggestions]
  );

  // ========================================================================
  // Main render - NO BRIDGES
  // ========================================================================
  // Simple transcript that mirrors the conversation in the main (left) area
  const messages = (chat?.messages || []) as Array<{ id?: string; role?: string; content?: unknown; createdAt?: string }>;

  return (
    <>
      <ChatActions />
      <ChatInterrupts />

      <CopilotSuggestionsContext.Provider value={suggestionsContextValue}>
        <main className="h-screen w-screen flex flex-col">
          <ChatHeader
            agentType={agentType === "auto" ? "primary" : agentType}
            memoryEnabled={memoryEnabled}
            onMemoryToggle={setMemoryEnabled}
            selectedAgent={agentType}
            onAgentChange={setAgentType}
            provider={provider}
            model={model}
            onProviderChange={setProvider}
            onModelChange={setModel}
            modelsByProvider={{
              google: ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
              openai: ["gpt-4o", "gpt-4o-mini"],
            }}
          />

          <div className="flex-1 overflow-hidden">
            <CopilotSidebar
              defaultOpen={true}
              clickOutsideToClose={false}
              threadId={sessionId}
              labels={{
                title: "Agent Sparrow",
                initial: "Hi! How can I help you today?",
              }}
              observabilityHooks={observabilityHooks}
            >
              {/* Main transcript on the left side */}
              <div className="h-full w-full flex flex-col bg-gradient-to-br from-slate-50 to-slate-100">
                <div className="flex-1 overflow-auto p-6 space-y-4">
                  {messages
                    .filter((m) => (m.role || "").toLowerCase() !== "system")
                    .map((m, idx) => {
                      const role = (m.role || "assistant").toLowerCase();
                      const text = extractContent(m.content);
                      return (
                        <div key={m.id || idx} className={`max-w-3xl ${role === "user" ? "ml-auto text-right" : "mr-auto text-left"}`}>
                          <div className={`inline-block rounded-lg px-4 py-3 shadow-sm ${role === "user" ? "bg-slate-800 text-white" : "bg-white text-slate-800"}`}>
                            <div className="whitespace-pre-wrap break-words">{text}</div>
                          </div>
                        </div>
                      );
                    })}
                </div>
                <div className="px-6 pb-6 text-xs text-slate-400">
                  <span className="mr-3">Session: {sessionId}</span>
                  <span className="mr-3">Agent: {agentType}</span>
                  <span className="mr-3">Model: {provider}/{model}</span>
                  <span className="mr-3">Documents: {documents.length}</span>
                  <span>Suggestions: {suggestions.length}</span>
                </div>
              </div>
            </CopilotSidebar>
          </div>
        </main>
      </CopilotSuggestionsContext.Provider>
    </>
  );
}

/**
 * Outer component that PROVIDES CopilotKit context
 * Handles session creation before rendering inner content
 */
export default function CopilotSidebarClient() {
  // ========================================================================
  // Session Management
  // ========================================================================
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [sessionError, setSessionError] = useState<Error | null>(null);
  const mountedRef = useRef(true);
  const bootstrapTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // ========================================================================
  // User Preferences (for CopilotKit properties)
  // ========================================================================
  const [provider] = useState<string>("google");
  const [model] = useState<string>("gemini-2.5-flash");
  const { selected: agentType } = useAgentSelection();

  // ========================================================================
  // Create session on mount
  // ========================================================================
  useEffect(() => {
    mountedRef.current = true;
    setIsCreatingSession(true);

    bootstrapTimeoutRef.current = setTimeout(() => {
      if (mountedRef.current && !sessionId) {
        const err = new Error("Session bootstrap timed out");
        console.error(err);
        setSessionError(err);
        setIsCreatingSession(false);
      }
    }, SESSION_BOOTSTRAP_TIMEOUT_MS);

    sessionsAPI
      .create("primary", "New Chat")
      .then((session) => {
        if (mountedRef.current) {
          setSessionId(String(session.id));
          setIsCreatingSession(false);
          if (bootstrapTimeoutRef.current) {
            clearTimeout(bootstrapTimeoutRef.current);
          }
        }
      })
      .catch((error) => {
        if (mountedRef.current) {
          console.error("Failed to create session:", error);
          setSessionError(error);
          setIsCreatingSession(false);
          if (bootstrapTimeoutRef.current) {
            clearTimeout(bootstrapTimeoutRef.current);
          }
        }
      });

    return () => {
      mountedRef.current = false;
      if (bootstrapTimeoutRef.current) {
        clearTimeout(bootstrapTimeoutRef.current);
      }
    };
  }, []);

  // ========================================================================
  // CopilotKit properties
  // ========================================================================
  const copilotProperties = useMemo(() => {
    const props: Record<string, any> = {
      session_id: sessionId,
      provider: provider,
      model: model,
    };

    if (agentType !== "auto") {
      props.agent_type = agentType;
    }

    return props;
  }, [sessionId, provider, model, agentType]);

  // ========================================================================
  // Loading state
  // ========================================================================
  if (isCreatingSession) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-800 mx-auto mb-4"></div>
          <p className="text-slate-600">Initializing session...</p>
        </div>
      </div>
    );
  }

  // ========================================================================
  // Error state
  // ========================================================================
  if (sessionError || !sessionId) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gradient-to-br from-red-50 to-red-100">
        <div className="text-center max-w-md p-6 bg-white rounded-lg shadow-lg">
          <h2 className="text-2xl font-bold text-red-600 mb-2">Session Error</h2>
          <p className="text-slate-600 mb-4">
            {sessionError?.message || "Failed to create session"}
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-slate-800 text-white rounded hover:bg-slate-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ========================================================================
  // Main render - CopilotKit provider wraps content
  // ========================================================================
  return (
    <CopilotKit
      runtimeUrl={`${API_URL}/api/v1/copilot/stream`}
      agent="sparrow"
      showDevConsole={false}
      properties={copilotProperties}
    >
      <CopilotSidebarContent sessionId={sessionId} />
    </CopilotKit>
  );
}
