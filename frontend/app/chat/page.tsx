"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { getAuthToken, initializeLocalAuth } from "@/lib/local-auth";
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
  useSidebar,
} from "@/components/ui/sidebar";
import { PanelLeft, ChevronDown } from "lucide-react";
import { ChatHistorySidebar } from "@/app/chat/components/ChatHistorySidebar";
import { AssistantMessage } from "./components/AssistantMessage";
import { WorkingTimeline } from "./components/WorkingTimeline";
import { computeTimeline } from "@/lib/trace/computeTimeline";
import { TimelineStep } from "@/types/trace";
import { CommandBar } from "./components/CommandBar";
import { FileDropZone } from "./components/FileDropZone";
import { Attachments, formatBytes } from "./components/Attachments";
import { useChat, type UIMessage } from "@ai-sdk/react";
import { type FileUIPart } from "ai";
import { sessionsAPI } from "@/lib/api/sessions";
import { rateLimitApi } from "@/lib/api/rateLimitApi";
import { APIKeyStatusBadge } from "@/components/api-keys/APIKeyStatusBadge";
import { SessionStatusChip } from "@/components/sessions/SessionStatusChip";
import { AutoSaveIndicator } from "@/components/sessions/AutoSaveIndicator";
import { SettingsButtonV2 } from "@/components/ui/SettingsButtonV2";
import { FeedMeButton } from "@/components/ui/FeedMeButton";
import ShinyText from "@/components/ShinyText";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { createBackendChatTransport } from "@/lib/providers/unified-client";

// Defer LightRays to client only to avoid SSR/WebGL mismatches
const LightRays = dynamic(() => import("@/components/LightRays"), {
  ssr: false,
});

// Main chat content component
type ChatContentProps = {
  sessionId: string;
  setSessionId: React.Dispatch<React.SetStateAction<string>>;
};

function ChatContent({ sessionId, setSessionId }: ChatContentProps) {
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState<"google" | "openai">("google");
  const [model, setModel] = useState<string>("gemini-2.5-flash-preview-09-2025");
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [logFile, setLogFile] = useState<File | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<'primary' | 'log_analysis' | 'research'>('primary');
  const [interimVoice, setInterimVoice] = useState<string>("");
  const [searchMode, setSearchMode] = useState<'auto'|'web'>("auto");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [enableFx, setEnableFx] = useState<boolean>(true);
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);
  type HistoryMessage = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    metadata?: Record<string, any> | null;
    agentType?: 'primary' | 'log_analysis' | 'research';
  };

  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [toolDecision, setToolDecision] = useState<any>(null);
  const [followUpQuestions, setFollowUpQuestions] = useState<string[] | null>(null);
  const liveTimelinePartsRef = useRef<Array<{ type: string; data?: any }>>([]);
  const liveTimelineMetadataRef = useRef<any>(null);
  const liveTimelineAgentRef = useRef<'primary' | 'log_analysis' | 'research' | 'router'>('primary');
  const [liveTimelineSteps, setLiveTimelineSteps] = useState<TimelineStep[]>([]);
  const { state, toggleSidebar } = useSidebar();
  const fallbackSessionRef = useRef<string>(crypto.randomUUID());
  const chatIdRef = useRef<string>(crypto.randomUUID());
  const previousSessionIdRef = useRef<string>("");
  const lastPersistedSessionIdRef = useRef<string>("");
  const hasRenamedRef = useRef<boolean>(Boolean(sessionId));

  if (!sessionId && previousSessionIdRef.current) {
    fallbackSessionRef.current = crypto.randomUUID();
  }
  previousSessionIdRef.current = sessionId;

  const effectiveSessionId = sessionId || fallbackSessionRef.current;

  const getMessageText = (m: any) =>
    (Array.isArray(m?.parts) ? m.parts : [])
      .filter((p: any) => p && p.type === "text" && typeof p.text === "string")
      .map((p: any) => p.text)
      .join("");

  const getFileParts = (m: any) =>
    (Array.isArray(m?.parts) ? m.parts : [])
      .filter((p: any) => p && p.type === "file");

  const getDataParts = (m: any) => {
    // Prefer direct data array when present
    const direct = Array.isArray((m as any)?.data)
      ? ((m as any).data as Array<{ type: string; data?: any }>).filter(Boolean)
      : [];
    if (direct.length > 0) return direct;

    // Otherwise extract all AI SDK data parts (type starts with "data-")
    const parts = Array.isArray(m?.parts) ? m.parts : [];
    return parts
      .filter((p: any) => p && typeof p.type === 'string' && p.type.startsWith('data-'))
      .map((p: any) => {
        const t = p.type as string;
        const d = (p as any).data;
        // Normalize timeline step so downstream timeline logic is consistent
        if (t === 'data-timeline-step') return { type: 'timeline-step', data: d };
        return { type: t, data: d };
      });
  };

  type ClientMessage = UIMessage<any, any>;

  const normalizeAssistantMetadata = (meta: any) => {
    if (!meta || typeof meta !== 'object') return undefined;
    const nested = (meta as any).messageMetadata;
    if (nested && typeof nested === 'object') {
      return nested;
    }
    return meta;
  };

  const transport = useMemo(
    () =>
      createBackendChatTransport({
        provider,
        model,
        sessionId: effectiveSessionId,
        getAuthToken: async () => getAuthToken(),
      }),
    [provider, model, effectiveSessionId],
  );

  const recomputeLiveTimeline = (streaming: boolean) => {
    const steps = computeTimeline({
      dataParts: liveTimelinePartsRef.current,
      metadata: liveTimelineMetadataRef.current,
      content: '',
      agentType: liveTimelineAgentRef.current,
      isStreaming: streaming,
    });
    if (process.env.NODE_ENV !== 'production') {
      try {
        // eslint-disable-next-line no-console
        console.debug('[live:recompute]', {
          streaming,
          types: liveTimelinePartsRef.current.map(p => p?.type),
          metadataKeys: liveTimelineMetadataRef.current ? Object.keys(liveTimelineMetadataRef.current || {}) : [],
          stepTitles: steps.map(s => `${s.title}:${s.status}`),
        });
      } catch {}
    }
    setLiveTimelineSteps(steps);
  };

  const resetLiveTimeline = (agent: 'primary' | 'log_analysis' | 'research' | 'router') => {
    liveTimelinePartsRef.current = [];
    liveTimelineMetadataRef.current = null;
    liveTimelineAgentRef.current = agent;
    setLiveTimelineSteps([]);
  };

  const { messages, sendMessage, status, error } = useChat<ClientMessage>({
    // Use a stable client-side chat id to avoid UI resets during initial send
    id: chatIdRef.current,
    transport,
    experimental_throttle: 60,
    onError: (e) => console.error("AI chat error:", e),
    onData: (chunk) => {
      if (!chunk) return;
      const type = (chunk as any).type;
      if (process.env.NODE_ENV !== 'production') {
        try {
          // eslint-disable-next-line no-console
          console.debug('[live:onData]', type, {
            keys: Object.keys(chunk as any),
            preview: (chunk as any)?.data ?? (chunk as any)?.messageMetadata ?? {
              delta: (chunk as any)?.delta,
              text: (chunk as any)?.text,
            },
          });
        } catch {}
      }
      if (type === 'text-start' || type === 'start') {
        recomputeLiveTimeline(true);
        return;
      }
      // AI SDK namespaced data parts (data-*) or canonical data part
      if (type === 'data' || (typeof type === 'string' && type.startsWith('data-'))) {
        const dataPart = (chunk as any).data;
        if (dataPart) {
          if (type === 'data-tool-result') {
            const toolName = dataPart?.tool_name || dataPart?.toolName || dataPart?.name || dataPart?.id || 'Tool';
            const statusRaw = (dataPart?.status || dataPart?.state || 'completed').toString().toLowerCase();
            const status = statusRaw.includes('fail') || statusRaw.includes('error')
              ? 'failed'
              : statusRaw.includes('progress')
                ? 'in_progress'
                : 'completed';
            const detail = dataPart?.reasoning || dataPart?.summary || dataPart?.output || dataPart?.result || '';
            liveTimelinePartsRef.current = [
              ...liveTimelinePartsRef.current,
              {
                type: 'timeline-step',
                data: {
                  type: `Tool: ${toolName}`,
                  description: typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2),
                  status,
                },
              },
            ];
          }
          if (type === 'data-followups') {
            const suggestions = Array.isArray(dataPart) ? dataPart.slice(0, 3).join('\n• ') : undefined;
            liveTimelinePartsRef.current = [
              ...liveTimelinePartsRef.current,
              {
                type: 'timeline-step',
                data: {
                  type: 'Follow-up suggestions',
                  description: suggestions,
                  status: 'completed',
                },
              },
            ];
          }
          // If it's a namespaced data-* chunk, keep its original type
          if (type !== 'data') {
            const namespaced = { type, data: dataPart } as any;
            liveTimelinePartsRef.current = [...liveTimelinePartsRef.current, namespaced];
          } else {
            liveTimelinePartsRef.current = [...liveTimelinePartsRef.current, dataPart];
          }
          recomputeLiveTimeline(true);
        }
        return;
      }
      // Reasoning stream (Gemini/OpenAI) → synthesize into thinking/timeline parts
      if (typeof type === 'string' && (type === 'reasoning' || type.startsWith('reasoning-'))) {
        const deltaText = (chunk as any).delta ?? (chunk as any).text ?? '';
        const end = type === 'reasoning-end' || type === 'reasoning-part-finish';
        const part = {
          type: 'timeline-step',
          data: {
            type: 'Reasoning',
            description: deltaText || (type === 'reasoning-start' ? 'Starting reasoning…' : undefined),
            status: end ? 'completed' : 'in-progress',
          },
        } as any;
        liveTimelinePartsRef.current = [...liveTimelinePartsRef.current, part];
        // Also keep a compact thinking_trace shape for computeTimeline inference
        const prev = (liveTimelineMetadataRef.current?.thinking_trace?.thinking_steps as any[]) || [];
        const merged = deltaText ? [...prev, { phase: 'REASONING', thought: deltaText }] : prev;
        liveTimelineMetadataRef.current = {
          ...(liveTimelineMetadataRef.current || {}),
          thinking_trace: { thinking_steps: merged },
        };
        recomputeLiveTimeline(true);
        return;
      }
      // Tool streaming (Gemini/OpenAI tool runtime)
      if (typeof type === 'string' && (type.startsWith('tool-') || type.startsWith('source-'))) {
        const callId = (chunk as any).toolCallId || (chunk as any).id;
        const toolName = (chunk as any).toolName || (chunk as any).name || 'Tool';
        const level = type.includes('error') ? 'failed' : (type.includes('available') || type.includes('output') || type.includes('end')) ? 'completed' : 'in-progress';
        const desc = (chunk as any).inputTextDelta || (chunk as any).errorText || '';
        const part = {
          type: 'timeline-step',
          data: {
            type: `Tool: ${toolName}`,
            description: desc,
            status: level,
            id: callId,
          },
        } as any;
        liveTimelinePartsRef.current = [...liveTimelinePartsRef.current, part];
        recomputeLiveTimeline(true);
        return;
      }
      if (type === 'message-metadata') {
        const meta = (chunk as any).messageMetadata;
        if (meta && typeof meta === 'object') {
          liveTimelineMetadataRef.current = {
            ...(liveTimelineMetadataRef.current || {}),
            ...meta,
          };
          if (!liveTimelineAgentRef.current || liveTimelineAgentRef.current === 'primary') {
            if (meta?.analysisResults || meta?.logMetadata) {
              liveTimelineAgentRef.current = 'log_analysis';
            }
          }
          recomputeLiveTimeline(true);
        }
        return;
      }
      if (type === 'text-end' || type === 'finish') {
        // Keep steps until onFinish persists message, then we clear there
        return;
      }
    },
    onFinish: async ({ message: assistantMessage, messages: chatMessages, isAbort, isError }) => {
      const activeSessionId = sessionId || lastPersistedSessionIdRef.current;
      if (!activeSessionId) return;

      try {
        const lastUser = [...chatMessages].reverse().find((m) => m.role === 'user');
        const userText = lastUser ? getMessageText(lastUser).trim() : "";
        const assistantText = getMessageText(assistantMessage).trim();

        if (userText) {
          await sessionsAPI.postMessage(activeSessionId, {
            message_type: 'user',
            agent_type: activeAgent,
            content: userText,
          });

          if (!hasRenamedRef.current) {
            const nextTitle = deriveChatTitle(userText);
            try {
              const updatedSession = await sessionsAPI.rename(activeSessionId, nextTitle);
              hasRenamedRef.current = true;

              if (typeof window !== 'undefined') {
                window.dispatchEvent(
                  new CustomEvent('chat-session-updated', {
                    detail: {
                      sessionId: String(updatedSession.id ?? activeSessionId),
                      title: updatedSession.title ?? nextTitle,
                      metadata: updatedSession.metadata,
                      agentType: updatedSession.agent_type,
                    },
                  }),
                );
              }
            } catch (renameError) {
              console.error('Failed to auto-name session:', renameError);
            }
          }
        }

        if (!isAbort && !isError && assistantText) {
          const metadataPayload: Record<string, any> = {};
          const messageMetadata = (assistantMessage as any)?.metadata;
          if (messageMetadata && Object.keys(messageMetadata).length > 0) {
            metadataPayload.messageMetadata = messageMetadata;
          }
          const dataParts = getDataParts(assistantMessage);
          if (dataParts.length > 0) {
            metadataPayload.dataParts = dataParts;
          }

          await sessionsAPI.postMessage(activeSessionId, {
            message_type: 'assistant',
            agent_type: activeAgent,
            content: assistantText,
            ...(Object.keys(metadataPayload).length > 0 ? { metadata: metadataPayload } : {}),
          });

          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('chat-sessions:refresh'));
          }
        }
      } catch (persistError) {
        console.error('Failed to persist messages:', persistError);
      }

      // Clear live timeline once the message finalizes
      resetLiveTimeline(liveTimelineAgentRef.current);

      // Ensure UI session state is linked to the created/persisted session
      try {
        if (!sessionId && lastPersistedSessionIdRef.current) {
          setSessionId(lastPersistedSessionIdRef.current);
        }
      } catch (e) {
        console.warn('Failed to sync session id after finish:', e);
      }
    },
  });

  // Ensure we show at least the minimal in-progress step as soon as message is submitted
  useEffect(() => {
    if ((status === 'submitted' || status === 'streaming') && liveTimelineSteps.length === 0) {
      recomputeLiveTimeline(true);
    }
  }, [status, liveTimelineSteps.length]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initialize local auth on mount (for development)
  useEffect(() => {
    initializeLocalAuth().catch(console.error);
  }, []);

  // Respect user settings and reduced motion for background FX
  useEffect(() => {
    try {
      const settingsRaw = localStorage.getItem("mb-sparrow-settings");
      if (settingsRaw) {
        const parsed = JSON.parse(settingsRaw);
        if (typeof parsed?.hardwareAcceleration === "boolean") {
          setEnableFx(Boolean(parsed.hardwareAcceleration));
        }
      }
    } catch {
      // ignore
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(mq.matches);
    const onChange = () => setReducedMotion(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  // Load message history when sessionId changes
  useEffect(() => {
    let mounted = true;
    const fetchHistory = async () => {
      setHistory([]);
      if (!sessionId) return;
      try {
        const items = await sessionsAPI.listMessages(sessionId, 100, 0);
        if (!mounted) return;
        const mapped: HistoryMessage[] = items
          .filter((m) => m.message_type === 'user' || m.message_type === 'assistant')
          .map((m, index) => ({
            id: String(m.id ?? `${m.message_type}-${index}`),
            role: m.message_type as 'user' | 'assistant',
            content: m.content,
            metadata: m.metadata ?? undefined,
            agentType: (m.agent_type as HistoryMessage['agentType']) || 'primary',
          }));
        setHistory(mapped);
      } catch (e) {
        console.warn('Failed to load history', e);
      }
    };
    fetchHistory();
    return () => { mounted = false };
  }, [sessionId]);

  useEffect(() => {
    if (sessionId) {
      hasRenamedRef.current = true;
      lastPersistedSessionIdRef.current = sessionId;
    } else {
      hasRenamedRef.current = false;
      fallbackSessionRef.current = crypto.randomUUID();
      lastPersistedSessionIdRef.current = "";
    }

    // Reset per-session UI state to avoid showing stale data when switching chats
    chatIdRef.current = crypto.randomUUID();
    setHistory([]);
    setFollowUpQuestions(null);
    setToolDecision(null);
    setMediaFiles([]);
    setLogFile(null);
  }, [sessionId]);

  useEffect(() => {
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
    if (!lastAssistant) {
      setFollowUpQuestions(null);
      setToolDecision(null);
      return;
    }
    const dataParts = ((lastAssistant as any).data ?? []) as Array<{ type: string; data?: any }>;
    const followupsPart = dataParts.find((part) => part.type === 'data-followups');
    setFollowUpQuestions(
      Array.isArray(followupsPart?.data) ? (followupsPart!.data as string[]) : null,
    );
    const toolPart = dataParts.find((part) => part.type === 'data-tool-result' || part.type === 'tool-result');
    setToolDecision(toolPart?.data ?? null);
  }, [messages]);

  const onSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (
      !(input.trim() || interimVoice.trim()) &&
      mediaFiles.length === 0 &&
      !logFile
    )
      return;

    // Pre-flight rate limit check for Gemini models
    try {
      if (provider === "google") {
        const modelForCheck = model.includes("pro")
          ? "gemini-2.5-pro"
          : "gemini-2.5-flash";
        const check = await rateLimitApi.checkRateLimit(modelForCheck as any);
        if (!check.allowed) {
          const retryAfter = check.retry_after ?? 30;
          alert(
            `Rate limit reached for ${modelForCheck}. Please retry in ${retryAfter}s.`,
          );
          return;
        }
      }
    } catch {
      // ignore silent failures here
    }

    let attachedLogText: string | undefined;
    if (logFile) {
      try {
        const rawText = await logFile.text();
        attachedLogText = sanitizeLogContent(rawText);
      } catch (err) {
        console.error("Failed to read log file:", err);
      }
    }

    const text = (input || interimVoice || "").trim();
    setInput("");
    setInterimVoice("");

    // Auto-create session on first send if none exists
    let nextSessionId = sessionId;
    try {
      if (!sessionId) {
        const desiredAgent = logFile
          ? 'log_analysis'
          : activeAgent === 'research'
            ? 'research'
            : 'primary';
        resetLiveTimeline(desiredAgent);
        const session = await sessionsAPI.create(desiredAgent);
        const createdId = String(session.id);
        nextSessionId = createdId;
        lastPersistedSessionIdRef.current = createdId;
        fallbackSessionRef.current = createdId;
      }
    } catch (e) {
      console.warn("Failed to auto-create session:", e);
    }

    if (nextSessionId) {
      lastPersistedSessionIdRef.current = nextSessionId;
    }

    // Reset live timeline state for new send
    const agentForTimeline = logFile
      ? 'log_analysis'
      : activeAgent === 'research'
        ? 'research'
        : activeAgent;
    resetLiveTimeline(agentForTimeline);

    // Convert File[] to FileUIPart[]
    const fileUIParts: FileUIPart[] = await Promise.all(
      mediaFiles.map(async (file) => {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (readerEvent) => {
            resolve(readerEvent.target?.result as string);
          };
          reader.onerror = (error) => reject(error);
          reader.readAsDataURL(file);
        });

        return {
          type: 'file' as const,
          mediaType: file.type,
          filename: file.name,
          url: dataUrl,
        };
      })
    );

    // Do not include the log file as a UI attachment in the user bubble

    await sendMessage(
      { text, files: fileUIParts.length ? fileUIParts : undefined },
      {
        body: {
          data: {
            ...(attachedLogText ? {
              attachedLogText,
              isLogAnalysis: true,
              logMetadata: {
                filename: logFile?.name,
                size: logFile?.size,
                lastModified: logFile?.lastModified,
              }
            } : {}),
            modelProvider: provider,
            model,
            sessionId: nextSessionId || fallbackSessionRef.current,
            useServerMemory: true,
            // Manual web search flags
            forceWebSearch: searchMode === 'web',
            webSearchMaxResults: 6,
            webSearchProfile: 'medium',
          },
        },
      },
    );

    setMediaFiles([]);
    setLogFile(null);
  };

  // Cap total rendered messages to 100 by reducing history slice
  const maxTotal = 100;
  const displayedHistory = history.slice(-Math.max(0, maxTotal - messages.length));
  const hasLiveMessages = messages.length > 0;
  const hasHistoryContent = displayedHistory.length > 0;
  const hasContent = hasLiveMessages || hasHistoryContent;
  const showFx = enableFx && !reducedMotion;
  const isLogAnalysis = activeAgent === 'log_analysis';
  const agentLabel = activeAgent === 'log_analysis'
    ? 'Log Analysis'
    : activeAgent === 'research'
      ? 'Research'
      : 'Primary Agent';
  const modelLabel = (() => {
    if (activeAgent === 'log_analysis') return 'Gemini 2.5 Pro';
    if (activeAgent === 'research') return 'GPT-5 Mini';
    return model.startsWith('gpt') ? 'GPT-5 Mini' : 'Gemini 2.5 Flash (09-2025 preview)';
  })();

  const handleModelSelect = (nextProvider: 'google' | 'openai', nextModel: string) => {
    setProvider(nextProvider);
    setModel(nextModel);
    setActiveAgent('primary');
  };

  const handleLogAnalysisSelect = () => {
    setProvider('google');
    setModel('gemini-2.5-pro');
    setActiveAgent('log_analysis');
  };

  const handleResearchSelect = () => {
    setProvider('openai');
    setModel('gpt-5-mini-2025-08-07');
    setActiveAgent('research');
  };

  return (
    <div className="relative min-h-svh">
      {/* Light rays background - scoped to inset area */}
      {showFx && (
        <div className="pointer-events-none absolute inset-0 z-0 opacity-60">
          <LightRays
            className="w-full h-full"
            raysOrigin="top-center"
            raysColor="hsl(54.9 96.7% 88%)"
            raysSpeed={0.65}
            lightSpread={1.35}
            rayLength={2.0}
            pulsating={false}
            fadeDistance={1.1}
            saturation={1}
            followMouse={true}
            mouseInfluence={0.08}
            noiseAmount={0}
            distortion={0}
          />
        </div>
      )}

      {/* Main content - centered container */}
      <div className="relative z-10 flex flex-col min-h-svh">
        {/* Header */}
        <header className="sticky top-0 z-50 backdrop-blur-lg border-b border-border/40 bg-[hsl(var(--brand-surface)/0.95)]">
          <div className="w-full px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <SidebarTrigger className="rounded-full border border-border/40 bg-background/60 hover:bg-background/80" />
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      className="flex items-center gap-2 px-3 py-2 text-sm font-medium"
                    >
                      <span>{agentLabel}</span>
                      <span className="text-xs text-muted-foreground">{modelLabel}</span>
                      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-56">
                    <DropdownMenuSub>
                      <DropdownMenuSubTrigger>Primary Agent</DropdownMenuSubTrigger>
                      <DropdownMenuSubContent>
                        <DropdownMenuItem
                          onSelect={(event) => {
                            event.preventDefault();
                            handleModelSelect('google', 'gemini-2.5-flash-preview-09-2025');
                          }}
                        >
                          Gemini 2.5 Flash
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onSelect={(event) => {
                            event.preventDefault();
                            handleModelSelect('openai', 'gpt-5-mini-2025-08-07');
                          }}
                        >
                          GPT-5 Mini
                        </DropdownMenuItem>
                      </DropdownMenuSubContent>
                    </DropdownMenuSub>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onSelect={(event) => {
                        event.preventDefault();
                        handleLogAnalysisSelect();
                      }}
                    >
                      Log Analysis
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={(event) => {
                        event.preventDefault();
                        handleResearchSelect();
                      }}
                    >
                      Research
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              <div className="flex items-center gap-3">
                {sessionId && <SessionStatusChip sessionId={sessionId} />}
                {status === "streaming" && <AutoSaveIndicator status="saving" />}
                <APIKeyStatusBadge />
                <FeedMeButton mode="navigate" />
                <SettingsButtonV2 />
              </div>
            </div>
          </div>
        </header>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-4 py-8">
            {/* Welcome state */}
            {!hasContent && (
              <div className="flex flex-col items-center justify-center min-h-[60vh] animate-in fade-in duration-500">
                <ShinyText
                  text="Agent Sparrow"
                  speed={8}
                  disabled={reducedMotion}
                  className="text-4xl font-semibold mb-2"
                />
                <p className="text-muted-foreground text-lg mb-8">
                  How can I help you today?
                </p>
              </div>
            )}

            {/* History */}
            {displayedHistory.length > 0 && (
              <div className="space-y-6 opacity-90">
                {displayedHistory.map((m) => {
                  const fullMeta = m.metadata as any;
                  const assistantMetadata = normalizeAssistantMetadata(m.metadata);
                  const isLogHistory =
                    m.role === 'assistant' && (
                      m.agentType === 'log_analysis' ||
                      Boolean(
                        assistantMetadata &&
                          (assistantMetadata.logMetadata ||
                            assistantMetadata.errorSnippets ||
                            assistantMetadata.rootCause),
                      )
                    );

                  const dataParts = (fullMeta && Array.isArray(fullMeta.dataParts) ? fullMeta.dataParts : []) as any[];
                  const timelineSteps = computeTimeline({
                    dataParts,
                    metadata: assistantMetadata,
                    content: m.content,
                    agentType: isLogHistory ? 'log_analysis' : 'primary',
                    isStreaming: false,
                  });

                  return (
                    <div
                      key={`h-${m.id}`}
                      className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-center'}`}
                    >
                      {m.role === 'assistant' ? (
                        <div className="w-full max-w-3xl mx-auto space-y-2">
                          {timelineSteps.length > 0 && (
                            <WorkingTimeline steps={timelineSteps} variant="final" />
                          )}
                          <div className="rounded-2xl px-5 py-3 border border-border/50 bg-[hsl(var(--brand-surface)/0.70)]">
                            <AssistantMessage
                              content={m.content}
                              metadata={assistantMetadata}
                              isLogAnalysis={isLogHistory}
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="max-w-[85%] rounded-2xl px-5 py-3 bg-primary/10 dark:bg-primary/20 text-foreground border border-primary/20">
                          <div className="text-[15px] leading-relaxed whitespace-pre-wrap">{m.content}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Live Messages */}
            {hasContent && (
              <div className="space-y-6">
                {messages.map((m, idx) => {
                  const isLast = idx === messages.length - 1;
                  const isStreamingMessage = (status === 'streaming' || status === 'submitted') && isLast;
                  const contentText = getMessageText(m);
                  const meta = normalizeAssistantMetadata((m as any).metadata);
                  const dataParts = getDataParts(m) as any[];
                  const logHints = Boolean(
                    (m as any)?.agentType === 'log_analysis' ||
                      meta?.logMetadata ||
                      meta?.errorSnippets ||
                      meta?.rootCause ||
                      meta?.analysisResults ||
                      (isStreamingMessage && activeAgent === 'log_analysis')
                  );
                  const agentTypeForTimeline = logHints ? 'log_analysis' : 'primary';
                  const computedSteps = computeTimeline({
                    dataParts,
                    metadata: meta,
                    content: contentText,
                    agentType: agentTypeForTimeline,
                    isStreaming: m.role === 'assistant' ? isStreamingMessage : false,
                  });
                  const stepsToRender = (m.role === 'assistant' && isStreamingMessage)
                    ? (liveTimelineSteps.length > 0 ? liveTimelineSteps : computedSteps)
                    : computedSteps;

                  return (
                    <div
                      key={m.id ?? idx}
                      className={`flex gap-4 animate-in slide-in-from-bottom-2 fade-in duration-300 ${
                        m.role === "user" ? "justify-end" : "justify-center"
                      }`}
                      style={{ animationDelay: `${idx * 50}ms` }}
                    >
                      {m.role === "assistant" ? (
                        <div className="w-full max-w-3xl mx-auto space-y-2">
                          {stepsToRender.length > 0 && (
                            <WorkingTimeline
                              steps={stepsToRender}
                              variant={isStreamingMessage ? 'live' : 'final'}
                            />
                          )}
                          <div className="rounded-2xl px-5 py-3 border border-border/50 bg-[hsl(var(--brand-surface)/0.70)]">
                            <AssistantMessage
                              content={contentText}
                              metadata={meta}
                              isLogAnalysis={logHints}
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="max-w-[85%] rounded-2xl px-5 py-3 bg-primary/10 dark:bg-primary/20 text-foreground border border-primary/20">
                          <div className="space-y-2">
                            <div className="text-[15px] leading-relaxed whitespace-pre-wrap">
                              {contentText}
                            </div>
                            {(() => {
                              const fileParts = getFileParts(m).filter((fp: any) => !(typeof fp?.mediaType === 'string' && fp.mediaType.startsWith('text/')));
                              return fileParts.length > 0 ? (
                                <div className="flex flex-wrap gap-2 pt-1">
                                  {fileParts.map((fp: any, i: number) => (
                                    <span
                                      key={i}
                                      className="inline-flex items-center gap-2 rounded-full border border-border/40 bg-background/60 px-3 py-1 text-xs text-muted-foreground"
                                    >
                                      <span className="inline-block w-2 h-2 rounded-full bg-primary/60" />
                                      {fp.filename || 'attachment'}
                                    </span>
                                  ))}
                                </div>
                              ) : null
                            })()}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Fallback live timeline when assistant message hasn't been created yet */}
                {(status === 'streaming' || status === 'submitted') && messages.length > 0 && messages[messages.length - 1]?.role !== 'assistant' && (
                  <div className="flex gap-4 justify-center animate-in fade-in duration-300">
                    <div className="w-full max-w-3xl mx-auto space-y-2">
                      <WorkingTimeline
                        steps={(liveTimelineSteps.length > 0 ? liveTimelineSteps : ([{ id: 'working-fallback', title: 'Thinking', status: 'in_progress' }] as any))}
                        variant="live"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            {toolDecision && (
              <div className="mt-6 rounded-2xl border border-border/40 bg-secondary/40 p-4 text-sm text-muted-foreground">
                <p className="font-semibold text-foreground">Tool decision</p>
                <p className="mt-1 text-foreground/80">{toolDecision.decision}</p>
                {toolDecision.reasoning && (
                  <p className="mt-2 leading-relaxed">{toolDecision.reasoning}</p>
                )}
                {Array.isArray(toolDecision.required_information) && toolDecision.required_information.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Required information</p>
                    <ul className="mt-1 list-disc list-inside space-y-1">
                      {toolDecision.required_information.map((item: string, idx: number) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="mt-4 p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive">
                <p className="text-sm">
                  {String((error as any)?.message || error)}
                </p>
              </div>
            )}

            {/* Attachments display */}
            {(mediaFiles.length > 0 || logFile) && (
              <div className="mt-4">
                <Attachments
                  mediaFiles={mediaFiles}
                  logFile={logFile}
                  onRemoveMedia={(idx) =>
                    setMediaFiles((prev) => prev.filter((_, i) => i !== idx))
                  }
                  onRemoveLog={() => {
                    setLogFile(null);
                    if (activeAgent === 'log_analysis') {
                      setActiveAgent('primary');
                      setProvider('google');
                      setModel('gemini-2.5-flash');
                    }
                  }}
                />
              </div>
            )}

            {attachError && (
              <div className="mt-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                {attachError}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input area - fixed at bottom */}
        <div className="sticky bottom-0 bg-gradient-to-t from-background via-background to-transparent">
          <div className="max-w-4xl mx-auto px-4 pb-6 pt-4">
            {followUpQuestions && followUpQuestions.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {followUpQuestions.map((question, idx) => (
                  <Button
                    key={idx}
                    variant="outline"
                    size="sm"
                    className="rounded-full border-border/40 text-xs"
                    onClick={() => setInput(question)}
                  >
                    {question}
                  </Button>
                ))}
              </div>
            )}
            <FileDropZone
              onFiles={async (files) => {
                setAttachError(null);
                const f = files[0];
                if (!f) return;

                // Enhanced log file detection
                const isLog = await detectLogFile(f);

                if (isLog) {
                  // Max 50MB for log files
                  if (f.size > 50 * 1024 * 1024) {
                    setAttachError(
                      `Log file too large: ${formatBytes(f.size)}. Max 50MB.`,
                    );
                    return;
                  }
                  setLogFile(f);
                  setActiveAgent('log_analysis');
                  setProvider('google');
                  setModel('gemini-2.5-pro');
                  // Do not override user's input; keep it free-form
                } else {
                  const max = 10 * 1024 * 1024;
                  if (f.size > max) {
                    setAttachError(
                      `Media too large: ${formatBytes(f.size)}. Max 10MB.`,
                    );
                    return;
                  }
                  setMediaFiles([f]);
                }
              }}
              className="w-full"
            >
              <CommandBar
                value={input}
                interimText={interimVoice}
                onInterim={(t) => setInterimVoice(t)}
                onChange={(v) => {
                  setInterimVoice("");
                  setInput(v);
                }}
                onSubmit={() => onSend()}
                onPickFiles={async (fileList) => {
                  if (!fileList || fileList.length === 0) return;
                  const files = Array.from(fileList);
                  const f = files[0];
                  const isLog = await detectLogFile(f);
                  if (isLog) {
                    if (f.size > 50 * 1024 * 1024) {
                      setAttachError(`Log file too large: ${formatBytes(f.size)}. Max 50MB.`);
                      return;
                    }
                    setLogFile(f);
                    setActiveAgent('log_analysis');
                    setProvider('google');
                    setModel('gemini-2.5-pro');
                    // Do not auto-insert any prompt; let user type freely
                  } else {
                    setMediaFiles(files);
                  }
                }}
                disabled={status === "submitted" || status === "streaming"}
                placeholder={logFile ? `Log attached: ${logFile.name} — ask your question…` : "Ask anything..."}
                provider={provider}
                model={model}
                onChangeProvider={(p) => {
                  setProvider(p);
                  // Model will be set by ModelSelector component based on validation
                }}
                onChangeModel={(m) => setModel(m)}
                searchMode={searchMode}
                onChangeSearchMode={setSearchMode}
              />
            </FileDropZone>
          </div>
        </div>
      </div>

      {/* Floating expand button when sidebar is collapsed */}
      {state === 'collapsed' && (
        <button
          aria-label="Open sidebar"
          onClick={toggleSidebar}
          className="fixed left-2 bottom-3 z-40 rounded-full bg-[hsl(0_0%_9%/0.95)] border border-border/50 p-2 shadow-lg hover:shadow-xl hover:bg-[hsl(0_0%_12%/0.95)] transition"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

// Helper to normalize log content before sending to backend
function sanitizeLogContent(raw: string): string {
  if (!raw) return raw;
  let sanitized = raw.replace(/\r\n/g, '\n');
  sanitized = sanitized.replace(/\u0000/g, '\n');
  sanitized = sanitized.replace(/[\u0001-\u0008\u000B\u000C\u000E-\u001F]/g, '');
  if (sanitized.charCodeAt(0) === 0xfeff) {
    sanitized = sanitized.slice(1);
  }
  const MAX_CHAR_COUNT = 50 * 1024 * 1024; // Mirror backend limit (approximate)
  if (sanitized.length > MAX_CHAR_COUNT) {
    sanitized = sanitized.slice(0, MAX_CHAR_COUNT);
  }
  return sanitized;
}

// Helper function to detect log files
async function detectLogFile(file: File): Promise<boolean> {
  // Check file extension
  const logExtensions = ['.log', '.txt', '.logs', '.json', '.csv', '.html', '.htm', '.xml'];
  const hasLogExtension = logExtensions.some(ext => file.name.toLowerCase().endsWith(ext));

  if (hasLogExtension) return true;

  // Check file content for log patterns if text file
  if (file.type.startsWith('text/') || file.type === 'application/json') {
    try {
      const sample = await file.slice(0, 1024).text();
      // Look for common log patterns
      const logPatterns = [
        /\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}/,  // Timestamps
        /\[(ERROR|WARN|INFO|DEBUG|TRACE)\]/i,  // Log levels
        /^\[.*?\]\s+/m,  // Bracketed prefixes
        /Exception|Error|Failed|Warning/i,  // Common log keywords
      ];
      return logPatterns.some(pattern => pattern.test(sample));
    } catch {
      // If we can't read it, assume it's not a log
      return false;
    }
  }

  return false;
}

export default function AIChatPage() {
  const [sessionId, setSessionId] = useState<string>('');
  const [viewKey, setViewKey] = useState(0);

  const handleSelectSession = (id?: string) => {
    setSessionId(id || '');
    setViewKey((prev) => prev + 1);
  };

  const activeSessionId = sessionId || undefined;

  return (
    <SidebarProvider defaultOpen={true}>
      {/* Sidebar reserves gap and stays fixed on the left */}
      <ChatHistorySidebar sessionId={activeSessionId} onSelect={handleSelectSession} />
      {/* Inset ensures main content is offset and centered */}
      <SidebarInset>
        <ChatContent
          key={`chat-${viewKey}-${sessionId || 'draft'}`}
          sessionId={sessionId}
          setSessionId={setSessionId}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}

function deriveChatTitle(raw: string): string {
  const normalized = raw.replace(/\s+/g, ' ').trim();
  if (!normalized) return 'New Chat';
  if (normalized.length <= 40) return normalized;
  return `${normalized.slice(0, 37).trimEnd()}...`;
}
