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
  const [model, setModel] = useState<string>("gemini-2.5-flash");
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [logFile, setLogFile] = useState<File | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [isLogAnalysis, setIsLogAnalysis] = useState<boolean>(false);
  const [interimVoice, setInterimVoice] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [enableFx, setEnableFx] = useState<boolean>(true);
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);
  const [history, setHistory] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [toolDecision, setToolDecision] = useState<any>(null);
  const [followUpQuestions, setFollowUpQuestions] = useState<string[] | null>(null);
  const { state, toggleSidebar } = useSidebar();
  const fallbackSessionRef = useRef<string>(crypto.randomUUID());
  const previousSessionIdRef = useRef<string>("");
  const lastPersistedSessionIdRef = useRef<string>("");

  if (!sessionId && previousSessionIdRef.current) {
    fallbackSessionRef.current = crypto.randomUUID();
  }
  previousSessionIdRef.current = sessionId;

  const effectiveSessionId = sessionId || fallbackSessionRef.current;

  const getMessageText = (m: any) =>
    (m?.parts || [])
      .filter((p: any) => p.type === "text")
      .map((p: any) => p.text)
      .join("");

  type ClientMessage = UIMessage<any, any>;

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

  const { messages, sendMessage, status, error } = useChat<ClientMessage>({
    id: effectiveSessionId,
    transport,
    onError: (e) => console.error("AI chat error:", e),
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
            agent_type: 'primary',
            content: userText,
          });
        }

        if (!isAbort && !isError && assistantText) {
          const metadataPayload: Record<string, any> = {};
          const messageMetadata = (assistantMessage as any)?.metadata;
          if (messageMetadata && Object.keys(messageMetadata).length > 0) {
            metadataPayload.messageMetadata = messageMetadata;
          }
          const dataParts = Array.isArray((assistantMessage as any)?.data)
            ? (assistantMessage as any).data
            : [];
          if (dataParts.length > 0) {
            metadataPayload.dataParts = dataParts;
          }

          await sessionsAPI.postMessage(activeSessionId, {
            message_type: 'assistant',
            agent_type: 'primary',
            content: assistantText,
            ...(Object.keys(metadataPayload).length > 0 ? { metadata: metadataPayload } : {}),
          });
        }
      } catch (persistError) {
        console.error('Failed to persist messages:', persistError);
      }
    },
  });

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
        const mapped = items
          .filter((m) => m.message_type === 'user' || m.message_type === 'assistant')
          .map((m) => ({ role: m.message_type as 'user' | 'assistant', content: m.content }));
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
      lastPersistedSessionIdRef.current = sessionId;
    } else {
      lastPersistedSessionIdRef.current = "";
    }
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
        // Create log_analysis session if we have a log file, otherwise primary
        const agentType = logFile ? "log_analysis" : "primary";
        const session = await sessionsAPI.create(agentType);
        const createdId = String(session.id);
        nextSessionId = createdId;
        setSessionId(createdId);
        fallbackSessionRef.current = createdId;
        lastPersistedSessionIdRef.current = createdId;
      }
    } catch (e) {
      console.warn("Failed to auto-create session:", e);
    }

    if (nextSessionId) {
      lastPersistedSessionIdRef.current = nextSessionId;
    }

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
          },
        },
      },
    );

    setMediaFiles([]);
    setLogFile(null);
    setIsLogAnalysis(false);
  };

  const hasContent = messages.length > 0;
  // Cap total rendered messages to 100 by reducing history slice
  const maxTotal = 100;
  const displayedHistory = history.slice(-Math.max(0, maxTotal - messages.length));
  const showFx = enableFx && !reducedMotion;
  const primaryModelLabel = model.startsWith('gpt') ? 'GPT-5 Mini' : 'Gemini 2.5 Flash';

  const handleModelSelect = (nextProvider: 'google' | 'openai', nextModel: string) => {
    setProvider(nextProvider);
    setModel(nextModel);
  };

  const handleLogAnalysisSelect = () => {
    setProvider('google');
    setModel('gemini-2.5-flash');
    setIsLogAnalysis(true);
    if (!input) {
      setInput('Please analyze the attached log file and highlight any critical errors, performance issues, and provide recommendations.');
    }
  };

  const handleResearchSelect = () => {
    setProvider('openai');
    setModel('gpt-5-mini-2025-08-07');
    if (!input) {
      setInput('Research the latest Mailbird updates and provide key insights.');
    }
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
        <header className="sticky top-0 z-50 backdrop-blur-lg border-b border-border/40 bg-[hsl(0_0%_9%/0.90)]">
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
                      <span>Primary Agent</span>
                      <span className="text-xs text-muted-foreground">{primaryModelLabel}</span>
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
                            handleModelSelect('google', 'gemini-2.5-flash');
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
                {displayedHistory.map((m, idx) => (
                  <div
                    key={`h-${idx}`}
                    className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-5 py-3 ${
                        m.role === 'user'
                          ? 'bg-primary/10 dark:bg-primary/20 text-foreground border border-primary/20'
                          : 'bg-secondary/50 dark:bg-zinc-800/50 border border-border/50'
                      }`}
                    >
                      <div className="text-[15px] leading-relaxed whitespace-pre-wrap">{m.content}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Live Messages */}
            {hasContent && (
              <div className="space-y-6">
                {messages.map((m, idx) => (
                  <div
                    key={m.id ?? idx}
                    className={`flex gap-4 animate-in slide-in-from-bottom-2 fade-in duration-300 ${
                      m.role === "user" ? "justify-end" : "justify-start"
                    }`}
                    style={{ animationDelay: `${idx * 50}ms` }}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-5 py-3 ${
                        m.role === "user"
                          ? "bg-primary/10 dark:bg-primary/20 text-foreground border border-primary/20"
                          : "bg-secondary/50 dark:bg-zinc-800/50 border border-border/50"
                      }`}
                    >
                      {m.role === "assistant" ? (
                        <AssistantMessage
                          content={getMessageText(m)}
                          metadata={(m as any).metadata}
                          isLogAnalysis={isLogAnalysis}
                        />
                      ) : (
                        <div className="text-[15px] leading-relaxed whitespace-pre-wrap">
                          {getMessageText(m)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Loading indicator */}
                {(status === "streaming" || status === "submitted") && (
                  <div className="flex gap-4 justify-start animate-in fade-in duration-300">
                    <div className="bg-secondary/50 dark:bg-zinc-800/50 rounded-2xl px-5 py-3 border border-border/50">
                      <div className="flex items-center gap-2">
                        <div className="flex gap-1">
                          <span
                            className="w-2 h-2 bg-primary/60 rounded-full animate-bounce"
                            style={{ animationDelay: "0ms" }}
                          />
                          <span
                            className="w-2 h-2 bg-primary/60 rounded-full animate-bounce"
                            style={{ animationDelay: "150ms" }}
                          />
                          <span
                            className="w-2 h-2 bg-primary/60 rounded-full animate-bounce"
                            style={{ animationDelay: "300ms" }}
                          />
                        </div>
                        <span className="text-sm text-muted-foreground">
                          Thinking...
                        </span>
                      </div>
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
                  onRemoveLog={() => setLogFile(null)}
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
                  setIsLogAnalysis(true);
                  // Auto-set agent to log analysis mode
                  if (!input) {
                    setInput('Please analyze this log file and identify any critical issues, errors, or performance problems.');
                  }
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
                    setIsLogAnalysis(true);
                    if (!input) {
                      setInput('Please analyze this log file and identify any critical issues, errors, or performance problems.');
                    }
                  } else {
                    setMediaFiles(files);
                  }
                }}
                disabled={status === "submitted" || status === "streaming"}
                placeholder="Ask anything..."
                provider={provider}
                model={model}
                onChangeProvider={(p) => {
                  setProvider(p);
                  // Model will be set by ModelSelector component based on validation
                }}
                onChangeModel={(m) => setModel(m)}
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
  const [sessionId, setSessionId] = useState<string>("");

  return (
    <SidebarProvider defaultOpen={true}>
      {/* Sidebar reserves gap and stays fixed on the left */}
      <ChatHistorySidebar
        sessionId={sessionId}
        onSelect={(id) => setSessionId(id || '')}
      />
      {/* Inset ensures main content is offset and centered */}
      <SidebarInset>
        <ChatContent sessionId={sessionId} setSessionId={setSessionId} />
      </SidebarInset>
    </SidebarProvider>
  );
}
