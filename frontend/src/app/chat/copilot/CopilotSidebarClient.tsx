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

/**
 * Phase 3: Full CopilotKit Integration
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getAuthToken();
        if (!cancelled && token) {
          setHeaders({ Authorization: `Bearer ${token}` });
        }
      } catch {
        // Silent fail - auth is optional
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return headers;
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
  const headers = useBearerHeader();

  // Endpoint resolution with feature flag
  const runtimeUrl = useMemo(() => {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const useStream = process.env.NEXT_PUBLIC_USE_COPILOT_STREAM === "true";

    if (useStream) {
      return `${base.replace(/\/$/, "")}/api/v1/copilot/stream`;
    }
    return `${base.replace(/\/$/, "")}/api/v1/copilotkit`;
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
      agent_type: agentType,
      trace_id: traceIdRef.current,
      ...(mcpUrl ? { mcpServers: [{ endpoint: mcpUrl }] } : {}),
    };
  }, [sessionId, memoryEnabled, provider, model, agentType, mcpUrl]);

  return (
    <div className="flex flex-col h-screen">
      {/* Header with controls outside sidebar */}
      <ChatHeader
        agentType={agentType}
        memoryEnabled={memoryEnabled}
        onMemoryToggle={setMemoryEnabled}
        provider={provider}
        model={model}
        onProviderChange={setProvider}
        onModelChange={setModel}
        modelsByProvider={modelsByProvider}
        mcpUrl={mcpUrl}
        onMcpUrlChange={setMcpUrl}
      />

      {/* CopilotKit + CopilotSidebar */}
      <div className="flex-1 overflow-hidden">
        <CopilotKit
          runtimeUrl={runtimeUrl}
          headers={headers}
          credentials="include"
          properties={properties}
          showDevConsole={false}
          threadId={sessionId}
          agent="sparrow"
        >
          {/* Actions for feedback/correction */}
          <ChatActions sessionId={sessionId} agentType={agentType} />

          {/* Interrupt handling */}
          <ChatInterrupts />

          {/* Main sidebar UI */}
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
        </CopilotKit>
      </div>
    </div>
  );
}
