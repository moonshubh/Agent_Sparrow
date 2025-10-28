"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { flushSync } from "react-dom";
import { Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription } from "@/shared/ui/dialog";
import { Button as UIButton } from "@/shared/ui/button";
import { CopilotKit, useCopilotChat, useLangGraphInterrupt, useCoAgent } from "@copilotkit/react-core";
import { TextMessage, MessageRole } from "@copilotkit/runtime-client-gql";
import { v4 as uuidv4 } from "uuid";
import { toast } from "@/shared/ui/use-toast";
import { UI_CONFIG } from "@/shared/config/constants";

import { getAuthToken } from "@/services/auth/local-auth";
import { sessionsAPI } from "@/services/api/endpoints/sessions";
import { FeedbackDialog } from "@/features/global-knowledge/components/FeedbackDialog";
import { CorrectionDialog } from "@/features/global-knowledge/components/CorrectionDialog";
import { ModelSelector } from "@/app/chat/components/ModelSelector";
import { modelsAPI } from "@/services/api/endpoints/models";

type Props = {
  initialSessionId?: string;
  agentType?: "primary" | "log_analysis";
};

function useBearerHeader() {
  const [headers, setHeaders] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getAuthToken();
        if (!cancelled && token) setHeaders({ Authorization: `Bearer ${token}` });
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  return headers;
}

function useSessionState(initial?: string, defaultAgent: "primary" | "log_analysis" = "primary") {
  const [sessionId, setSessionId] = useState<string | undefined>(initial);
  const ensureSession = useCallback(async () => {
    if (sessionId) return sessionId;
    const session = await sessionsAPI.create(defaultAgent);
    const createdId = String(session.id);
    setSessionId(createdId);
    try {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("chat-session-updated", { detail: { sessionId: createdId, agentType: defaultAgent } }));
        window.dispatchEvent(new Event("chat-sessions:refresh"));
      }
    } catch {}
    return createdId;
  }, [sessionId, defaultAgent]);
  return { sessionId, setSessionId, ensureSession } as const;
}

function SimpleChatUI({
  apiPath,
  initialSessionId,
  agentType,
}: {
  apiPath?: string;
  initialSessionId?: string;
  agentType?: "primary" | "log_analysis";
}) {
  const headers = useBearerHeader();
  const resolvedApiPath = useMemo(() => {
    if (apiPath && apiPath.trim().length > 0) return apiPath;
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    // CopilotKit React expects a Copilot Runtime (GraphQL) endpoint
    return `${base.replace(/\/$/, "")}/api/v1/copilotkit`;
  }, [apiPath]);

  const [memoryEnabled, setMemoryEnabled] = useState<boolean>(process.env.NEXT_PUBLIC_ENABLE_MEMORY !== "false");
  const { sessionId, setSessionId, ensureSession } = useSessionState(initialSessionId, agentType || "primary");

  useEffect(() => {
    if (initialSessionId) setSessionId(initialSessionId);
  }, [initialSessionId, setSessionId]);

  const [requestProps, setRequestProps] = useState<Record<string, any>>({});
  const [mcpUrl, setMcpUrl] = useState<string>(process.env.NEXT_PUBLIC_MCP_SSE_URL || "");

  return (
    <CopilotKit
      runtimeUrl={resolvedApiPath}
      headers={headers}
      credentials="include"
      properties={{
        session_id: sessionId,
        use_server_memory: memoryEnabled,
        ...requestProps,
        ...(mcpUrl ? { mcpServers: [{ endpoint: mcpUrl }] } : {}),
      }}
      showDevConsole={false}
      threadId={sessionId}
    >
      <ChatInner
        sessionId={sessionId}
        memoryEnabled={memoryEnabled}
        setMemoryEnabled={setMemoryEnabled}
        ensureSession={ensureSession}
        setRequestProps={setRequestProps}
        agentType={agentType || "primary"}
        mcpUrl={mcpUrl}
        setMcpUrl={setMcpUrl}
      />
    </CopilotKit>
  );
}

function ChatInner({
  sessionId,
  memoryEnabled,
  setMemoryEnabled,
  ensureSession,
  setRequestProps,
  agentType,
  mcpUrl,
  setMcpUrl,
}: {
  sessionId?: string;
  memoryEnabled: boolean;
  setMemoryEnabled: (v: boolean) => void;
  ensureSession: () => Promise<string>;
  setRequestProps: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  agentType: "primary" | "log_analysis";
  mcpUrl: string;
  setMcpUrl: (url: string) => void;
}) {
  const chat = useCopilotChat({});
  const agent = useCoAgent({ name: "sparrow" });
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [attachmentUrls, setAttachmentUrls] = useState<string[]>([]);
  const lastPersistedAssistantIdRef = useRef<string | null>(null);
  const [provider, setProvider] = useState<"google" | "openai">("google");
  const [model, setModel] = useState<string>("gemini-2.5-flash-preview-09-2025");
  const [modelsByProvider, setModelsByProvider] = useState<Record<"google" | "openai", string[]>>({ google: [], openai: [] });
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackSelected, setFeedbackSelected] = useState("");
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [incorrectText, setIncorrectText] = useState("");
  const [correctedText, setCorrectedText] = useState("");
  const [interruptQueue, setInterruptQueue] = useState<Array<{ event: any; resolve: (v: any) => void }>>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const catalog = await modelsAPI.list(agentType);
        if (cancelled) return;
        setModelsByProvider({
          google: Array.isArray((catalog as any).google) ? (catalog as any).google : [],
          openai: Array.isArray((catalog as any).openai) ? (catalog as any).openai : [],
        });
        const list = ((catalog as any)[provider] as string[] | undefined) || [];
        if (list.length > 0 && !list.includes(model)) setModel(list[0]);
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, [agentType, provider, model]);

  useEffect(() => {
    if (!sessionId) return;
    try {
      const raw = localStorage.getItem(`chat:prefs:${sessionId}`);
      if (raw) {
        const parsed = JSON.parse(raw) as { provider?: "google" | "openai"; model?: string };
        if (parsed.provider) setProvider(parsed.provider);
        if (parsed.model) setModel(parsed.model);
      }
    } catch {}
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    try {
      localStorage.setItem(`chat:prefs:${sessionId}`, JSON.stringify({ provider, model }));
    } catch {}
  }, [provider, model, sessionId]);

  const captureSelection = useCallback((): string => {
    try {
      const sel = typeof window !== "undefined" ? window.getSelection() : null;
      const t = sel && !sel.isCollapsed ? sel.toString().trim() : "";
      return t || "";
    } catch {
      return "";
    }
  }, []);

  useEffect(() => {
    const urls = attachments.map((f) => URL.createObjectURL(f));
    setAttachmentUrls(urls);
    return () => {
      urls.forEach((u) => {
        try {
          URL.revokeObjectURL(u);
        } catch {}
      });
    };
  }, [attachments]);

  const handleSlashCommand = useCallback(
    (raw: string): boolean => {
      const trimmed = raw.trim();
      if (!trimmed.startsWith("/")) return false;
      const space = trimmed.indexOf(" ");
      const command = space === -1 ? trimmed : trimmed.slice(0, space);
      const remainder = space === -1 ? "" : trimmed.slice(space + 1).trim();
      const selection = captureSelection();

      if (command === "/feedback") {
        setFeedbackText(remainder);
        setFeedbackSelected(selection);
        setFeedbackOpen(true);
        setAttachments([]);
        return true;
      }
      if (command === "/correct") {
        setIncorrectText(selection || remainder);
        setCorrectedText(selection ? "" : remainder);
        setCorrectionOpen(true);
        setAttachments([]);
        return true;
      }
      return false;
    },
    [captureSelection]
  );

  const onFilesPicked = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const next: File[] = [];
    const maxSize = UI_CONFIG.VALIDATION.MAX_FILE_SIZE;
    const allowedTypes = new Set<string>([...UI_CONFIG.VALIDATION.ALLOWED_FILE_TYPES, "text/plain", "text/markdown", "text/csv", "text/html", "application/json"]);
    const allowedExtensions = [".txt", ".log", ".md", ".csv", ".json", ".pdf", ".html", ".htm"];
    const isAllowedByExt = (name: string) => allowedExtensions.some((ext) => name.toLowerCase().endsWith(ext));

    for (let i = 0; i < files.length; i++) {
      const f = files.item(i);
      if (!f) continue;
      if (f.size > maxSize) {
        toast({ title: "File too large", description: `${f.name} exceeds ${Math.round(maxSize / (1024 * 1024))}MB limit`, variant: "destructive" } as any);
        continue;
      }
      const typeOk = !f.type || allowedTypes.has(f.type) || f.type.startsWith("image/") || f.type.startsWith("text/") || isAllowedByExt(f.name);
      if (!typeOk) {
        toast({ title: "Unsupported file type", description: `${f.name} (${f.type || "unknown"}) is not allowed`, variant: "destructive" } as any);
        continue;
      }
      next.push(f);
    }
    setAttachments((prev) => [...prev, ...next].slice(0, 4));
  }, []);

  const fileToImagePayload = async (file: File): Promise<{ format: string; bytes: string } | null> => {
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (ev) => resolve(String(ev.target?.result || ""));
        reader.onerror = (err) => reject(err);
        reader.readAsDataURL(file);
      });
      const match = dataUrl.match(/^data:(.*?);base64,(.*)$/);
      if (!match) return null;
      const format = (file.type || match[1] || "image/png").split("/")[1] || "png";
      const bytes = match[2] || "";
      return { format, bytes };
    } catch {
      return null;
    }
  };

  const fileToAttachmentPayload = async (file: File): Promise<{ filename: string; media_type: string; data_url: string }> => {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (ev) => resolve(String(ev.target?.result || ""));
      reader.onerror = (err) => reject(err);
      reader.readAsDataURL(file);
    });
    return { filename: file.name || "attachment", media_type: file.type || "application/octet-stream", data_url: dataUrl };
  };

  const send = useCallback(async () => {
    const raw = input || "";
    const text = raw.trim();
    if (!text && attachments.length === 0) return;
    if (text && handleSlashCommand(text)) {
      setInput("");
      return;
    }
    setIsSending(true);
    try {
      const sid = await ensureSession();
      const attachmentsPayload = attachments.length ? await Promise.all(attachments.map(fileToAttachmentPayload)) : [];
      const traceId = uuidv4();
      const resolvedAgent = agentType;

      if (attachments.length > 0 && attachments[0].type.startsWith("image/")) {
        const img = await fileToImagePayload(attachments[0]);
        if (img) {
          // Optionally attach image for model contexts that consume it via forwarded props/state.
        }
      }

      flushSync(() =>
        setRequestProps((prev) => ({
          ...prev,
          attachments: attachmentsPayload,
          provider,
          model,
          agent_type: resolvedAgent,
          trace_id: traceId,
        }))
      );

      // Append the user message (GQL message type) and trigger the LangGraph agent via CopilotKit runtime
      await (chat as any)?.appendMessage?.(
        new TextMessage({
          role: MessageRole.User,
          content: text,
        })
      );
      await (agent as any)?.run?.();

      await sessionsAPI.postMessage(sid, {
        message_type: "user",
        agent_type: resolvedAgent,
        content: text || (attachments.length ? `[${attachments.length} file(s) attached]` : ""),
      });
    } finally {
      setIsSending(false);
      setInput("");
      setAttachments([]);
      flushSync(() =>
        setRequestProps((prev) => {
          const next = { ...prev };
          delete (next as any).attachments;
          delete (next as any).trace_id;
          return next;
        })
      );
    }
  }, [input, attachments, handleSlashCommand, ensureSession, setRequestProps, provider, model, agentType, chat]);

  useEffect(() => {
    (async () => {
      try {
        const sid = sessionId;
        if (!sid) return;
        const last = [...(chat?.visibleMessages || [])]
          .reverse()
          .find((m) => (m as any).role === "assistant" && typeof (m as any).content === "string");
        if (!last) return;
        const assistantText = (last as any).content as string;
        if (!assistantText) return;
        const lastId = (last as any).id as string | undefined;
        if (lastId && lastPersistedAssistantIdRef.current === lastId) return;
        await sessionsAPI.postMessage(sid, { message_type: "assistant", agent_type: agentType, content: assistantText });
        if (lastId) lastPersistedAssistantIdRef.current = lastId;
      } catch {}
    })();
  }, [chat?.visibleMessages, sessionId, agentType]);

  useLangGraphInterrupt<{ prompt?: string }>(
    { render: ({ event, resolve }) => { setInterruptQueue((q) => [...q, { event, resolve }]); return null; } },
    [chat?.messages?.length]
  );

  return (
    <>
      <div className="max-w-5xl w-full mx-auto space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">Sparrow Copilot</h2>
            <span className="text-xs px-2 py-1 rounded border bg-muted/40">{agentType === "log_analysis" ? "Log Analysis" : "Primary"} Agent</span>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <UIButton asChild variant="outline" className="h-8 px-3">
              <Link href="/settings" aria-label="Open Settings">
                Settings
              </Link>
            </UIButton>
            <UIButton asChild variant="secondary" className="h-8 px-3">
              <Link href="/feedme-revamped" aria-label="Open FeedMe">
                FeedMe
              </Link>
            </UIButton>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4 ml-auto">
            <label className="inline-flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                aria-label="Use server memory"
                className="accent-primary"
                checked={memoryEnabled}
                onChange={(e) => setMemoryEnabled(e.target.checked)}
              />
              Use server memory
            </label>
            <ModelSelector
              provider={provider}
              model={model}
              onChangeProvider={setProvider}
              onChangeModel={setModel}
              align="right"
              modelsByProvider={modelsByProvider}
            />
            <input
              value={mcpUrl}
              onChange={(e) => setMcpUrl(e.target.value)}
              placeholder="MCP SSE URL"
              className="h-8 w-56 px-2 py-1 text-xs border rounded-md bg-background"
              aria-label="MCP SSE URL"
            />
          </div>
        </div>

        <div className="rounded-lg border divide-y bg-background/60">
          <div className="max-h-[50vh] overflow-auto p-4 space-y-3">
            {(chat?.visibleMessages || []).map((m, i) => {
              const role = (m as any).role as string | undefined;
              const content = (m as any).content as string | undefined;
              const meta = (m as any).metadata || (m as any).messageMetadata || {};
              const suggestions: string[] | undefined = Array.isArray(meta?.messageMetadata?.suggestions)
                ? (meta.messageMetadata.suggestions as string[])
                : Array.isArray(meta?.suggestions)
                ? (meta.suggestions as string[])
                : undefined;
              return (
                <div key={(m as any).id ?? i} className="flex flex-col gap-2">
                  <div className="flex gap-3">
                    <div className={`text-xs uppercase tracking-wide ${role === "assistant" ? "text-primary" : "text-muted-foreground"}`}>{role}</div>
                    <div className="text-[15px] whitespace-pre-wrap leading-relaxed">{content}</div>
                  </div>
                  {role === "assistant" && Array.isArray(suggestions) && suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-2 pl-10">
                      {suggestions.slice(0, 3).map((s, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setInput(s)}
                          className="text-xs rounded-full px-3 py-1 border bg-muted/30 hover:bg-muted/50 transition-colors"
                          title="Insert follow-up"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <form
            className="flex items-center gap-2 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!isSending) send();
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              className="flex-1 px-3 py-2 border rounded-md bg-background"
            />
            <label className="px-3 py-2 rounded-md border cursor-pointer bg-muted/40 text-sm">
              Attach
              <input type="file" accept="*/*" multiple className="hidden" onChange={(e) => onFilesPicked(e.target.files)} />
            </label>
            <button
              type="submit"
              disabled={isSending || (!input.trim() && attachments.length === 0)}
              className="px-4 py-2 rounded-md bg-primary text-primary-foreground disabled:opacity-50"
            >
              {isSending ? "Sending…" : "Send"}
            </button>
          </form>
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 p-3">
              {attachments.map((f, i) => {
                const url = attachmentUrls[i];
                return (
                  <a
                    key={i}
                    href={url}
                    download={f.name || "attachment"}
                    className="text-xs rounded-full px-3 py-1 border bg-muted/30 hover:bg-muted/50 transition-colors"
                    onClick={(e) => {
                      if (!url) e.preventDefault();
                    }}
                    title={f.type ? `${f.name} • ${f.type}` : f.name}
                  >
                    {f.name}
                  </a>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {interruptQueue.length > 0 &&
        (() => {
          const current = interruptQueue[0];
          const text = (current?.event?.value as any)?.prompt || "This action requires your input";
          const details = (() => {
            try {
              return JSON.stringify(current?.event?.value ?? {}, null, 2);
            } catch {
              return undefined;
            }
          })();
          const resolveAndPop = (decision: "approve" | "reject") => {
            try {
              current.resolve(decision);
            } catch {}
            setInterruptQueue((q) => q.slice(1));
          };
          return (
            <Dialog open>
              <DialogContent hideClose>
                <DialogHeader>
                  <DialogTitle>Human decision required</DialogTitle>
                  <DialogDescription>{String(text)}</DialogDescription>
                </DialogHeader>
                {details && <pre className="mt-2 max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-xs whitespace-pre-wrap">{details}</pre>}
                <DialogFooter className="mt-4">
                  <UIButton onClick={() => resolveAndPop("reject")} variant="secondary">
                    Reject
                  </UIButton>
                  <UIButton onClick={() => resolveAndPop("approve")}>Approve</UIButton>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          );
        })()}

      <FeedbackDialog
        open={feedbackOpen}
        initialFeedback={feedbackText}
        selectedText={feedbackSelected}
        sessionId={sessionId || null}
        agent={agentType}
        onClose={() => setFeedbackOpen(false)}
      />
      <CorrectionDialog
        open={correctionOpen}
        initialIncorrect={incorrectText}
        initialCorrected={correctedText}
        sessionId={sessionId || null}
        agent={agentType}
        onClose={() => setCorrectionOpen(false)}
      />
    </>
  );
}

export default function CopilotChatClient({ initialSessionId, agentType }: Props) {
  return (
    <div className="min-h-svh w-full flex items-center justify-center p-8">
      <SimpleChatUI initialSessionId={initialSessionId} agentType={agentType} />
    </div>
  );
}
