"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { v4 as uuidv4 } from "uuid";

import { getAuthToken } from "@/services/auth/local-auth";
import { sessionsAPI } from "@/services/api/endpoints/sessions";
import { modelsAPI } from "@/services/api/endpoints/models";
import { ChatHeader } from "./ChatHeader";
import { ChatActions } from "./ChatActions";
import { ChatInterrupts } from "./ChatInterrupts";
import { CustomAssistantMessage } from "./CustomAssistantMessage";
import { CustomUserMessage } from "./CustomUserMessage";
import { CopilotKnowledgeBridge } from "./CopilotKnowledgeBridge";
import { CopilotSuggestionsBridge } from "./CopilotSuggestionsBridge";
import { CopilotSuggestionsContext } from "./CopilotSuggestionsContext";
import type { DocumentPointer } from "@/features/global-knowledge/hooks/useCopilotDocuments";
import type { Suggestion } from "@/features/chat/hooks/useCopilotSuggestions";
import { useAgentSelection, type AgentChoice } from "@/features/chat/hooks/useAgentSelection";

/**
 * Phase 3 + Phase 4: Full CopilotKit Integration with Document & Suggestion Features
 *
 * Main component that replaces CopilotChatClient.tsx with polished CopilotKit UI.
 *
 * Architecture:
 * - CopilotKit provider with stream/GraphQL endpoint
 * - CopilotSidebar for polished chat UI
 * - Custom message components (AssistantMessage with ReasoningPanel)
 * - Actions for /feedback and /correct
 * - useLangGraphInterrupt for human-in-the-loop
 * - ChatHeader outside sidebar for model selector and memory toggle
 *
 * Phase 4 Additions:
 * - CopilotKnowledgeBridge for KB + FeedMe document integration
 * - CopilotSuggestionsBridge for smart suggestion generation
 * - Knowledge source toggles in ChatHeader
 *
 * Removes:
 * - Manual message rendering loops
 * - Custom file upload UI (uses built-in)
 * - Manual interrupt queue
 * - Custom input handling
 * - Manual slash command detection
 */

type Props = {
  initialSessionId?: string;
  agentType?: "primary" | "log_analysis";
};

// Custom hook for bearer token header
function useBearerHeader() {
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getAuthToken();
        if (!cancelled) {
          setHeaders(token ? { Authorization: `Bearer ${token}` } : {});
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        if (process.env.NODE_ENV !== "production") console.warn("Failed to load auth token:", err);
        if (!cancelled) setHeaders({});
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { headers, isLoading } as const;
}

// Custom hook for session state management
function useSessionState(
  initial?: string,
  defaultAgent: "primary" | "log_analysis" = "primary"
) {
  const [sessionId, setSessionId] = useState<string | undefined>(initial);

  const ensureSession = useCallback(async () => {
    if (sessionId) return sessionId;

    const session = await sessionsAPI.create(defaultAgent);
    const createdId = String(session.id);
    setSessionId(createdId);

    try {
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("chat-session-updated", {
            detail: { sessionId: createdId, agentType: defaultAgent },
          })
        );
        window.dispatchEvent(new Event("chat-sessions:refresh"));
      }
    } catch {
      // Silent fail
    }

    return createdId;
  }, [sessionId, defaultAgent]);

  return { sessionId, setSessionId, ensureSession } as const;
}

export default function CopilotSidebarClient({
  initialSessionId,
  agentType = "primary",
}: Props) {
  const { headers, isLoading: authLoading } = useBearerHeader();

  // Endpoint resolution with feature flag
  const runtimeUrl = useMemo(() => {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return `${base.replace(/\/$/, "")}/api/v1/copilot/stream`;
  }, []);

  // Session management
  const { sessionId, setSessionId, ensureSession } = useSessionState(
    initialSessionId,
    agentType
  );

  useEffect(() => {
    if (initialSessionId) setSessionId(initialSessionId);
  }, [initialSessionId, setSessionId]);

  // Memory toggle
  const [memoryEnabled, setMemoryEnabled] = useState<boolean>(
    process.env.NEXT_PUBLIC_ENABLE_MEMORY !== "false"
  );

  // Model/provider state
  const [provider, setProvider] = useState<"google" | "openai">("google");
  const [model, setModel] = useState<string>(
    "gemini-2.5-flash-preview-09-2025"
  );
  const [modelsByProvider, setModelsByProvider] = useState<
    Record<"google" | "openai", string[]>
  >({
    google: [],
    openai: [],
  });

  // MCP configuration
  const [mcpUrl, setMcpUrl] = useState<string>(
    process.env.NEXT_PUBLIC_MCP_SSE_URL || ""
  );

  // Phase 4: Knowledge source toggles (default: enabled, persisted to localStorage)
  // Fix: Added try-catch for localStorage access (can fail in private browsing)
  const [kbEnabled, setKbEnabled] = useState<boolean>(() => {
    try {
      if (typeof window !== 'undefined') {
        const saved = localStorage.getItem('copilot:kb-enabled')
        return saved !== null ? saved === 'true' : true
      }
    } catch (error) {
      console.warn('Failed to read KB enabled state from localStorage:', error)
    }
    return true
  })

  const [feedmeEnabled, setFeedmeEnabled] = useState<boolean>(() => {
    try {
      if (typeof window !== 'undefined') {
        const saved = localStorage.getItem('copilot:feedme-enabled')
        return saved !== null ? saved === 'true' : true
      }
    } catch (error) {
      console.warn('Failed to read FeedMe enabled state from localStorage:', error)
    }
    return true
  })

  // Phase 4: Feature flags
  const enableDocuments = process.env.NEXT_PUBLIC_ENABLE_COPILOT_DOCUMENTS === 'true'
  const enableSuggestions = process.env.NEXT_PUBLIC_ENABLE_COPILOT_SUGGESTIONS === 'true'
  const enableMultiAgent = process.env.NEXT_PUBLIC_ENABLE_MULTI_AGENT_SELECTION === 'true'
  const enableObservability = process.env.NEXT_PUBLIC_ENABLE_COPILOT_OBSERVABILITY === 'true'
  const publicLicenseKey = process.env.NEXT_PUBLIC_COPILOTKIT_LICENSE_KEY

  // Phase 5: Multi-agent selection
  const { selected, choose } = useAgentSelection()
  const selectedAgent: AgentChoice = enableMultiAgent ? selected : 'auto'
  const prevSelectedRef = useRef<AgentChoice>(selectedAgent)

  // When agent selection changes, create a new session to keep per-session invariants
  useEffect(() => {
    if (!enableMultiAgent) return
    if (prevSelectedRef.current === selectedAgent) return
    prevSelectedRef.current = selectedAgent
    const nextAgentForSession = selectedAgent === 'auto' ? 'router' : selectedAgent
    ;(async () => {
      try {
        const session = await sessionsAPI.create(nextAgentForSession as any)
        setSessionId(String(session.id))
      } catch {
        // Silent fail; user can still chat in current session
      }
    })()
  }, [enableMultiAgent, selectedAgent, setSessionId])

  const [documentPointers, setDocumentPointers] = useState<DocumentPointer[]>([])
  const [suggestionState, setSuggestionState] = useState<{
    suggestions: Suggestion[]
    isGenerating: boolean
  }>({ suggestions: [], isGenerating: false })
  const [suggestionHandlers, setSuggestionHandlers] = useState<{
    handleClick?: (suggestion: Suggestion, options?: { sendImmediately?: boolean }) => void
    clear?: () => void
  }>({})

  // Load available models
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const catalog = await modelsAPI.list(agentType);
        if (cancelled) return;

        setModelsByProvider({
          google: Array.isArray((catalog as any).google)
            ? (catalog as any).google
            : [],
          openai: Array.isArray((catalog as any).openai)
            ? (catalog as any).openai
            : [],
        });

        const list =
          ((catalog as any)[provider] as string[] | undefined) || [];
        if (list.length > 0 && !list.includes(model)) {
          setModel(list[0]);
        }
      } catch {
        // Silent fail
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentType, provider, model]);

  // Persist preferences to localStorage
  useEffect(() => {
    if (!sessionId) return;
    try {
      const raw = localStorage.getItem(`chat:prefs:${sessionId}`);
      if (raw) {
        const parsed = JSON.parse(raw) as {
          provider?: "google" | "openai";
          model?: string;
        };
        if (parsed.provider) setProvider(parsed.provider);
        if (parsed.model) setModel(parsed.model);
      }
    } catch {
      // Silent fail
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    try {
      localStorage.setItem(
        `chat:prefs:${sessionId}`,
        JSON.stringify({ provider, model })
      );
    } catch {
      // Silent fail
    }
  }, [provider, model, sessionId]);

  // Phase 4: Persist knowledge source toggles
  // Fix: Added try-catch for localStorage write (can fail in private browsing)
  useEffect(() => {
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('copilot:kb-enabled', String(kbEnabled));
      }
    } catch (error) {
      console.warn('Failed to persist KB enabled state:', error)
    }
  }, [kbEnabled]);

  useEffect(() => {
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('copilot:feedme-enabled', String(feedmeEnabled));
      }
    } catch (error) {
      console.warn('Failed to persist FeedMe enabled state:', error)
    }
  }, [feedmeEnabled]);

  // Ensure session exists when component mounts
  useEffect(() => {
    ensureSession();
  }, [ensureSession]);

  // Stable trace id: rotate only when the session changes
  const traceIdRef = useRef<string>(uuidv4());
  useEffect(() => {
    traceIdRef.current = uuidv4();
  }, [sessionId]);

  // Build properties for CopilotKit
  const properties = useMemo(() => {
    return {
      session_id: sessionId,
      use_server_memory: memoryEnabled,
      provider,
      model,
      // Phase 5: Only pass agent_type when explicitly selected (not Auto)
      ...(enableMultiAgent
        ? (selectedAgent !== 'auto' ? { agent_type: selectedAgent } : {})
        : { agent_type: agentType }
      ),
      trace_id: traceIdRef.current,
      ...(mcpUrl ? { mcpServers: [{ endpoint: mcpUrl }] } : {}),
    };
  }, [sessionId, memoryEnabled, provider, model, agentType, mcpUrl, enableMultiAgent, selectedAgent]);

  // Debug: capture minimal init info in development for troubleshooting
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return;
    try {
      if (typeof window !== 'undefined') {
        (window as any).__COPILOT_CONFIG__ = {
          runtimeUrl,
          sessionId,
          authHeadersPresent: headers && Object.keys(headers).length > 0,
        };
      }
    } catch {}
  }, [runtimeUrl, sessionId, headers]);

  // Block CopilotKit mount until auth header is resolved to avoid race conditions
  if (authLoading) {
    return (
      <div className="flex flex-col h-screen bg-background">
        <ChatHeader
          agentType={agentType}
          memoryEnabled={memoryEnabled}
          onMemoryToggle={setMemoryEnabled}
          kbEnabled={enableDocuments ? kbEnabled : undefined}
          onKbToggle={enableDocuments ? setKbEnabled : undefined}
          feedmeEnabled={enableDocuments ? feedmeEnabled : undefined}
          onFeedmeToggle={enableDocuments ? setFeedmeEnabled : undefined}
          provider={provider}
          model={model}
          onProviderChange={setProvider}
          onModelChange={setModel}
          modelsByProvider={modelsByProvider}
          mcpUrl={mcpUrl}
          onMcpUrlChange={setMcpUrl}
          selectedAgent={enableMultiAgent ? selectedAgent : undefined}
          onAgentChange={enableMultiAgent ? choose : undefined}
        />
        <div className="flex-1 overflow-hidden flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <p className="text-sm">Initializing chat…</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header with controls outside sidebar */}
      <ChatHeader
        agentType={agentType}
        memoryEnabled={memoryEnabled}
        onMemoryToggle={setMemoryEnabled}
        kbEnabled={enableDocuments ? kbEnabled : undefined}
        onKbToggle={enableDocuments ? setKbEnabled : undefined}
        feedmeEnabled={enableDocuments ? feedmeEnabled : undefined}
        onFeedmeToggle={enableDocuments ? setFeedmeEnabled : undefined}
        provider={provider}
        model={model}
        onProviderChange={setProvider}
        onModelChange={setModel}
        modelsByProvider={modelsByProvider}
        mcpUrl={mcpUrl}
        onMcpUrlChange={setMcpUrl}
        // Phase 5: Show selector only when enabled
        selectedAgent={enableMultiAgent ? selectedAgent : undefined}
        onAgentChange={enableMultiAgent ? choose : undefined}
      />

      {/* CopilotKit + CopilotSidebar */}
      <div className="flex-1 overflow-hidden">
        <CopilotKit
          runtimeUrl={runtimeUrl}
          headers={headers}
          credentials="include"
          properties={properties}
          showDevConsole={false}
          publicLicenseKey={publicLicenseKey}
          onError={(event) => {
            try {
              const payload = {
                type: event?.type,
                source: event?.context?.source,
                operation: event?.context?.request?.operation,
                latency: event?.context?.response?.latency,
                status: event?.context?.response?.status,
                timestamp: event?.timestamp,
              };
              if (typeof window !== 'undefined') {
                const errors = (window as any).__COPILOT_ERRORS__ || [];
                errors.push({ ...payload, config: (window as any).__COPILOT_CONFIG__ });
                (window as any).__COPILOT_ERRORS__ = errors.slice(-10);
                (window as any).__COPILOT_DEBUG__ = {
                  ...(window as any).__COPILOT_DEBUG__,
                  lastErrorEvent: payload,
                };
              }
              if (process.env.NODE_ENV !== 'production') {
                // eslint-disable-next-line no-console
                console.error('[CopilotKit Error]', payload);
              }
            } catch {}
          }}
          threadId={sessionId}
          agent="sparrow"
        >
          {/* Actions for feedback/correction */}
          <ChatActions sessionId={sessionId} agentType={agentType} />

          {/* Interrupt handling */}
          <ChatInterrupts />

          {/* Phase 4: Document Integration Bridge */}
          {enableDocuments && (
            <CopilotKnowledgeBridge
              sessionId={sessionId}
              agentType={agentType}
              enabled={enableDocuments}
              kbEnabled={kbEnabled}
              feedmeEnabled={feedmeEnabled}
              onDocumentsRegistered={setDocumentPointers}
            />
          )}

          {/* Phase 4: Suggestion Generation Bridge */}
          {enableSuggestions && (
            <CopilotSuggestionsBridge
              agentType={agentType}
              enabled={enableSuggestions}
              availableDocuments={documentPointers}
              onSuggestionsChange={({ suggestions, isGenerating, handleClick, clear }) => {
                setSuggestionState({ suggestions, isGenerating })
                setSuggestionHandlers({ handleClick, clear })
              }}
            />
          )}

          {/* Main sidebar UI */}
          <CopilotSuggestionsContext.Provider
            value={{
              suggestions: enableSuggestions ? suggestionState.suggestions : [],
              isGenerating: enableSuggestions ? suggestionState.isGenerating : false,
              onSuggestionSelected: enableSuggestions ? suggestionHandlers.handleClick : undefined,
              clearSuggestions: enableSuggestions ? suggestionHandlers.clear : undefined,
            }}
          >
            <CopilotSidebar
              defaultOpen={true}
              clickOutsideToClose={false}
              labels={{
                title: "Agent Sparrow",
                initial:
                  agentType === "log_analysis"
                    ? "Hi! I'm your log analysis specialist. I can help you analyze logs, identify patterns, troubleshoot issues, and provide insights."
                    : "Hi! I'm your AI assistant. I can help with general queries, research tasks, and provide information.",
              }}
              observabilityHooks={enableObservability ? {
                onChatStarted: () => {
                  try {
                    const now = Date.now()
                    if (typeof window !== 'undefined') {
                      const prev = ((window as any).__COPILOT_DEBUG__ || {})
                      ;(window as any).__COPILOT_DEBUG__ = { ...prev, metrics: { ...(prev.metrics || {}), lastStart: now } }
                    }
                  } catch {}
                },
                onChatStopped: () => {
                  try {
                    if (typeof window !== 'undefined') {
                      const dbg = (window as any).__COPILOT_DEBUG__ || {}
                      const lastStart: number | undefined = dbg.metrics?.lastStart
                      const duration = lastStart ? Math.max(0, Date.now() - lastStart) : undefined
                      ;(window as any).__COPILOT_DEBUG__ = {
                        ...dbg,
                        metrics: { ...(dbg.metrics || {}), lastDurationMs: duration },
                      }
                    }
                  } catch {}
                },
                onMessageSent: () => {
                  try {
                    if (typeof window !== 'undefined') {
                      const dbg = (window as any).__COPILOT_DEBUG__ || {}
                      const sent = (dbg.metrics?.sentCount || 0) + 1
                      ;(window as any).__COPILOT_DEBUG__ = { ...dbg, metrics: { ...(dbg.metrics || {}), sentCount: sent } }
                    }
                  } catch {}
                },
                onFeedbackGiven: () => {
                  try {
                    if (typeof window !== 'undefined') {
                      const dbg = (window as any).__COPILOT_DEBUG__ || {}
                      const fb = (dbg.metrics?.feedbackCount || 0) + 1
                      ;(window as any).__COPILOT_DEBUG__ = { ...dbg, metrics: { ...(dbg.metrics || {}), feedbackCount: fb } }
                    }
                  } catch {}
                },
                onError: (e) => {
                  try {
                    if (typeof window !== 'undefined') {
                      const dbg = (window as any).__COPILOT_DEBUG__ || {}
                      ;(window as any).__COPILOT_DEBUG__ = { ...dbg, lastHookError: { type: e?.type, ts: e?.timestamp } }
                    }
                  } catch {}
                }
              } : undefined}
              // Custom message components
              AssistantMessage={CustomAssistantMessage}
              UserMessage={CustomUserMessage}
            >
              {/* Main application content goes here */}
              <div className="flex items-center justify-center h-full p-8">
                <div className="text-center text-muted-foreground">
                  <p className="text-lg mb-2">
                    Chat interface is in the sidebar →
                  </p>
                  <p className="text-sm">
                    Open the sidebar to start a conversation with Agent Sparrow
                  </p>
                </div>
              </div>
            </CopilotSidebar>
          </CopilotSuggestionsContext.Provider>
        </CopilotKit>
      </div>
    </div>
  );
}
