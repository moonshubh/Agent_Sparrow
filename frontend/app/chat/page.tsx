"use client";

import React, { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { initializeLocalAuth } from "@/lib/local-auth";
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
  useSidebar,
} from "@/components/ui/sidebar";
import { PanelLeft } from "lucide-react";
import { ChatHistorySidebar } from "@/app/chat/components/ChatHistorySidebar";
import { AssistantMessage } from "./components/AssistantMessage";
import { CommandBar } from "./components/CommandBar";
import { FileDropZone } from "./components/FileDropZone";
import { Attachments, formatBytes } from "./components/Attachments";
import { useChat, type UIMessage } from "@ai-sdk/react";
import { z } from "zod";
import type { ThinkingTrace } from "@/types/chat";
import { sessionsAPI } from "@/lib/api/sessions";
import { rateLimitApi } from "@/lib/api/rateLimitApi";
import { APIKeyStatusBadge } from "@/components/api-keys/APIKeyStatusBadge";
import { SessionStatusChip } from "@/components/sessions/SessionStatusChip";
import { AutoSaveIndicator } from "@/components/sessions/AutoSaveIndicator";
import { SettingsButtonV2 } from "@/components/ui/SettingsButtonV2";
import { FeedMeButton } from "@/components/ui/FeedMeButton";
import ShinyText from "@/components/ShinyText";

// Defer LightRays to client only to avoid SSR/WebGL mismatches
const LightRays = dynamic(() => import("@/components/LightRays"), {
  ssr: false,
});

// Main chat content component
function ChatContent() {
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState<"google" | "openai">("google");
  const [model, setModel] = useState<string>("gemini-2.5-flash");
  const [sessionId, setSessionId] = useState<string>("");
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [logFile, setLogFile] = useState<File | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [interimVoice, setInterimVoice] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [enableFx, setEnableFx] = useState<boolean>(true);
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);
  const [history, setHistory] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const { state, toggleSidebar } = useSidebar();

  type DataParts = { followups: string[]; thinking: ThinkingTrace };
  type ClientMessage = UIMessage<unknown, DataParts>;

  const { messages, sendMessage, status, error } = useChat<ClientMessage>({
    onError: (e) => console.error("AI chat error:", e),
    dataPartSchemas: {
      followups: z.array(z.string()).max(10),
      thinking: z.object({
        confidence: z.number(),
        thinking_steps: z
          .array(
            z.object({
              phase: z.string(),
              thought: z.string(),
              confidence: z.number(),
            }),
          )
          .optional(),
        tool_decision: z.string().optional(),
        tool_confidence: z.string().optional(),
        knowledge_gaps: z.array(z.string()).optional(),
        emotional_state: z.string().optional(),
        problem_category: z.string().optional(),
        complexity: z.string().optional(),
        critique_score: z.number().optional(),
        passed_critique: z.boolean().optional(),
      }),
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
        attachedLogText = await logFile.text();
      } catch (err) {
        console.error("Failed to read log file:", err);
      }
    }

    const text = (input || interimVoice || "").trim();
    setInput("");
    setInterimVoice("");

    // Auto-create session on first send if none exists
    let effectiveSessionId = sessionId;
    try {
      if (!sessionId) {
        const session = await sessionsAPI.create("primary");
        effectiveSessionId = session.id;
        setSessionId(session.id);
      }
    } catch (e) {
      console.warn("Failed to auto-create session:", e);
    }

    await sendMessage(
      { text, files: mediaFiles.length ? mediaFiles : undefined },
      {
        body: {
          data: {
            ...(attachedLogText ? { attachedLogText } : {}),
            modelProvider: provider,
            model,
            sessionId: effectiveSessionId || undefined,
            useServerMemory: true,
          },
        },
      },
    );

    setMediaFiles([]);
    setLogFile(null);
  };

  const getMessageText = (m: any) =>
    (m.parts || [])
      .filter((p: any) => p.type === "text")
      .map((p: any) => p.text)
      .join("");

  const hasContent = messages.length > 0;
  // Cap total rendered messages to 100 by reducing history slice
  const maxTotal = 100;
  const displayedHistory = history.slice(-Math.max(0, maxTotal - messages.length));
  const showFx = enableFx && !reducedMotion;

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
            <div className="flex items-center">
              {/* Left spacer to balance layout; no icons on top */}
              <div className="flex-1" />

              {/* Right section with action buttons */}
              <div className="flex items-center gap-3">
                {sessionId && <SessionStatusChip sessionId={sessionId} />}
                {status === "streaming" && <AutoSaveIndicator isSaving={true} />}
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
                        <AssistantMessage content={getMessageText(m)} />
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
            <FileDropZone
              onFiles={(files) => {
                setAttachError(null);
                const f = files[0];
                if (!f) return;
                if (/(\.txt|\.log|\.csv|\.html?)$/i.test(f.name)) {
                  if (f.size > 2 * 1024 * 1024) {
                    setAttachError(
                      `Log file too large: ${formatBytes(f.size)}. Max 2MB.`,
                    );
                    return;
                  }
                  setLogFile(f);
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
                onPickFiles={(fileList) => {
                  if (!fileList || fileList.length === 0) return;
                  const files = Array.from(fileList);
                  const f = files[0];
                  if (/\.(txt|log|csv|html?)$/i.test(f.name)) {
                    setLogFile(f);
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
                  setModel(p === "openai" ? "gpt-4o-mini" : "gemini-2.5-flash");
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
        <ChatContent />
      </SidebarInset>
    </SidebarProvider>
  );
}
