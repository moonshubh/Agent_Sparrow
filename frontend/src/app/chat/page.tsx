"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
 
import { getAuthToken, initializeLocalAuth } from "@/services/auth/local-auth";
import {
  SidebarProvider,
  SidebarInset,
  useSidebar,
} from "@/shared/ui/sidebar";
import { PanelLeft } from "lucide-react";
import AppSidebarLeft, { LeftTab } from "@/app/chat/components/AppSidebarLeft";
import RightContextSidebar from "@/app/chat/components/RightContextSidebar";
import { AssistantMessage } from "./components/AssistantMessage";
import { WorkingTimeline } from "./components/WorkingTimeline";
import StreamingOverlay from "./components/StreamingOverlay";
import { computeTimeline } from "@/services/trace/computeTimeline";
import { TimelineStep } from "@/shared/types/trace";
import { CommandBar } from "./components/CommandBar";
import { FileDropZone } from "./components/FileDropZone";
import { Attachments, formatBytes } from "./components/Attachments";
import { useChat } from "@ai-sdk/react";
import { type UIMessagePart, type FileUIPart, type UITools } from "ai";
import { sessionsAPI } from "@/services/api/endpoints/sessions";
import { rateLimitApi } from "@/services/api/endpoints/rateLimitApi";
import { APIKeyStatusBadge } from "@/features/api-keys/components/APIKeyStatusBadge";
import { SettingsButtonV2 } from "@/shared/ui/SettingsButtonV2";
import { FeedMeButton } from "@/shared/ui/FeedMeButton";
import { FeedbackDialog } from "@/features/global-knowledge/components/FeedbackDialog";
import { CorrectionDialog } from "@/features/global-knowledge/components/CorrectionDialog";
import ShinyText from "@/shared/components/ShinyText";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
 
import { Button } from "@/shared/ui/button";
import { createBackendChatTransport } from "@/services/api/providers/unified-client";
import {
  type AgentType,
  type InteractiveAgent,
  type ChatDataPart,
  type ChatDataTypes,
  type ChatMessageMetadata,
  type ChatUIMessage,
  type ToolDecisionRecord,
} from "@/shared/types/chat";
import { agentGraphApi, type HumanDecisionPayload } from "@/services/api/endpoints/agentGraphApi";
import InterruptOverlay from "./components/InterruptOverlay";
import { BackgroundBeamsWithCollision } from "@/components/ui/background-beams-with-collision";
import { MultiStepLoader } from "@/components/ui/multi-step-loader";
import { toast } from "sonner";

// Main chat content component
type ChatContentProps = {
  sessionId: string;
  setSessionId: React.Dispatch<React.SetStateAction<string>>;
};

type ChatMessage = ChatUIMessage;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

const isTextPart = (
  part: UIMessagePart<ChatDataTypes, UITools>,
): part is { type: 'text'; text: string } => part?.type === 'text' && typeof part.text === 'string';

const isFilePart = (
  part: UIMessagePart<ChatDataTypes, UITools>,
): part is FileUIPart => part?.type === 'file' && typeof part.url === 'string';

const toChatDataPart = (part: unknown): ChatDataPart | null => {
  if (!isRecord(part) || typeof part.type !== 'string') {
    return null;
  }

  if (part.type === 'data') {
    const payload = isRecord(part.data) ? part.data : {};
    const innerType = typeof payload.type === 'string' ? (payload.type as string) : 'data';
    const innerData = 'data' in payload ? (payload.data as unknown) : part.data;
    return { type: innerType, data: innerData };
  }

  if (part.type === 'data-timeline-step') {
    return { type: 'timeline-step', data: part.data };
  }

  return {
    type: part.type,
    data: part.data,
  };

};

const readStringProperty = (
  source: Record<string, unknown>,
  keys: string[],
  fallback: string,
): string => {
  for (const key of keys) {
    const candidate = source[key];
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return candidate;
    }
  }
  return fallback;
};

const DEFAULT_WORKING_STEP: TimelineStep = {
  id: 'working-fallback',
  title: 'Thinking',
  status: 'in_progress',
};

function ChatContent({ sessionId, setSessionId }: ChatContentProps) {
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState<"google" | "openai">("google");
  const [model, setModel] = useState<string>("gemini-2.5-flash");
  const [primaryProvider, setPrimaryProvider] = useState<"google" | "openai">("google");
  const [primaryModel, setPrimaryModel] = useState<string>("gemini-2.5-flash");
  const [logProvider, setLogProvider] = useState<"google" | "openai">("google");
  const [logModel, setLogModel] = useState<string>("gemini-2.5-pro");
  const [primaryModels, setPrimaryModels] = useState<string[]>([]);
  const [logModels, setLogModels] = useState<string[]>([]);
  const [mediaFiles, setMediaFiles] = useState<File[]>([]);
  const [logFile, setLogFile] = useState<File | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<InteractiveAgent>('primary');
  const [interimVoice, setInterimVoice] = useState<string>("");
  const [searchMode, setSearchMode] = useState<'auto'|'web'>("auto");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);
  const [memoryEnabled, setMemoryEnabled] = useState<boolean>(process.env.NEXT_PUBLIC_ENABLE_MEMORY !== 'false');
  const interruptsEnabled = process.env.NEXT_PUBLIC_ENABLE_INTERRUPTS !== 'false';
  const [showBeams, setShowBeams] = useState<boolean>(true);
  const [interruptOpen, setInterruptOpen] = useState<boolean>(false);
  const [interruptThreadId, setInterruptThreadId] = useState<string>("");
  const [pendingInterrupts, setPendingInterrupts] = useState<Array<Record<string, unknown>>>([]);
  const [interruptLoading, setInterruptLoading] = useState<boolean>(false);
  const interruptPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  type HistoryMessage = {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    metadata?: Record<string, unknown> | null;
    agentType?: InteractiveAgent;
  };

  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [toolDecision, setToolDecision] = useState<ToolDecisionRecord | null>(null);
  const [followUpQuestions, setFollowUpQuestions] = useState<string[] | null>(null);
  const [overlayText, setOverlayText] = useState<string>("");
  const [overlayAgent, setOverlayAgent] = useState<AgentType>('primary');
  const [isOverlayActive, setIsOverlayActive] = useState<boolean>(false);
  const streamBufferRef = useRef<string>("");
  const overlayRafRef = useRef<number | null>(null);
  const overlayQueueRef = useRef<string[]>([]);
  const overlayDripTimeoutRef = useRef<number | null>(null);
  const liveTimelinePartsRef = useRef<ChatDataPart[]>([]);
  const liveTimelineMetadataRef = useRef<ChatMessageMetadata | null>(null);
  const liveTimelineAgentRef = useRef<AgentType>('primary');
  const [liveTimelineSteps, setLiveTimelineSteps] = useState<TimelineStep[]>([]);
  const timelineRafRef = useRef<number | null>(null);
  const timelineTimeoutRef = useRef<number | null>(null);
  const lastSelectionRef = useRef<string>("");
  type FeedbackDialogState = { open: boolean; feedbackText: string; selectedText: string };
  type CorrectionDialogState = { open: boolean; incorrectText: string; correctedText: string };
  const [feedbackDialogState, setFeedbackDialogState] = useState<FeedbackDialogState>({
    open: false,
    feedbackText: "",
    selectedText: "",
  });
  const [correctionDialogState, setCorrectionDialogState] = useState<CorrectionDialogState>({
    open: false,
    incorrectText: "",
    correctedText: "",
  });
  const { state, toggleSidebar } = useSidebar();
  const fallbackSessionRef = useRef<string>(crypto.randomUUID());
  const chatIdRef = useRef<string>(crypto.randomUUID());
  const previousSessionIdRef = useRef<string>("");
  const lastPersistedSessionIdRef = useRef<string>("");
  const hasRenamedRef = useRef<boolean>(false);
  const latestCreatedSessionRef = useRef<string | null>(null);

  if (!sessionId && previousSessionIdRef.current) {
    fallbackSessionRef.current = crypto.randomUUID();
  }
  previousSessionIdRef.current = sessionId;

  const effectiveSessionId = sessionId || fallbackSessionRef.current;

  const getMessageText = (message: ChatMessage): string =>
    (Array.isArray(message?.parts) ? message.parts : [])
      .filter(isTextPart)
      .map((part) => part.text)
      .join("");

  const getFileParts = (message: ChatMessage): FileUIPart[] =>
    (Array.isArray(message?.parts) ? message.parts : []).filter(isFilePart);

  const getDataParts = (message: ChatMessage): ChatDataPart[] => {
    const rawData = (message as ChatMessage & { data?: unknown }).data;
    if (Array.isArray(rawData)) {
      const normalized = rawData
        .map(toChatDataPart)
        .filter((part): part is ChatDataPart => part !== null);
      if (normalized.length > 0) {
        return normalized;
      }
    }

    const parts = Array.isArray(message?.parts) ? message.parts : [];
    return parts
      .map(toChatDataPart)
      .filter((part): part is ChatDataPart => part !== null);
  };

  const startInterruptPolling = useCallback((threadId: string) => {
    if (interruptPollRef.current) {
      clearInterval(interruptPollRef.current);
      interruptPollRef.current = null;
    }
    interruptPollRef.current = setInterval(async () => {
      try {
        const snap = await agentGraphApi.getThreadState(threadId);
        const next = Array.isArray(snap.interrupts) ? snap.interrupts : [];
        if (!next.length) {
          setInterruptOpen(false);
          setPendingInterrupts([]);
          setInterruptThreadId("");
          if (interruptPollRef.current) {
            clearInterval(interruptPollRef.current);
            interruptPollRef.current = null;
          }
          toast.success("Run completed");
        } else {
          setPendingInterrupts(next as Array<Record<string, unknown>>);
        }
      } catch {
        // ignore transient errors
      }
    }, 2500);
  }, []);

  const handleStartSupervisedRun = useCallback(async () => {
    if (!interruptsEnabled) return;
    const query = input.trim() || "";
    let log_content: string | undefined = undefined;
    try {
      if (logFile) {
        const raw = await logFile.text();
        log_content = sanitizeLogContent(raw);
      }
    } catch {}
    try {
      setInterruptLoading(true);
      const res = await agentGraphApi.run({ query, log_content });
      if (res.status === 'interrupted' && Array.isArray(res.interrupts) && res.interrupts.length > 0) {
        setInterruptThreadId(res.thread_id);
        setPendingInterrupts(res.interrupts as Array<Record<string, unknown>>);
        setInterruptOpen(true);
        startInterruptPolling(res.thread_id);
        toast.message("Supervised run started — awaiting your decision");
      } else {
        toast.success("Run completed with no interrupts");
      }
    } catch {
      toast.error("Failed to start supervised run");
    } finally {
      setInterruptLoading(false);
    }
  }, [interruptsEnabled, input, logFile, startInterruptPolling]);

  const handleInterruptDecision = useCallback(async (payload: HumanDecisionPayload) => {
    if (!interruptThreadId) return;
    try {
      setInterruptLoading(true);
      const res = await agentGraphApi.run({ thread_id: interruptThreadId, resume: payload });
      if (res.status === 'interrupted' && Array.isArray(res.interrupts) && res.interrupts.length > 0) {
        setPendingInterrupts(res.interrupts as Array<Record<string, unknown>>);
        toast.message("Decision applied — further input required");
      } else {
        setInterruptOpen(false);
        setPendingInterrupts([]);
        setInterruptThreadId("");
        if (interruptPollRef.current) {
          clearInterval(interruptPollRef.current);
          interruptPollRef.current = null;
        }
        toast.success("Run resumed to completion");
      }
    } catch {
      toast.error("Failed to apply decision");
    } finally {
      setInterruptLoading(false);
    }
  }, [interruptThreadId]);

  useEffect(() => {
    return () => {
      if (interruptPollRef.current) {
        clearInterval(interruptPollRef.current);
        interruptPollRef.current = null;
      }
      if (timelineRafRef.current !== null) {
        cancelAnimationFrame(timelineRafRef.current);
        timelineRafRef.current = null;
      }
      if (timelineTimeoutRef.current !== null) {
        window.clearTimeout(timelineTimeoutRef.current);
        timelineTimeoutRef.current = null;
      }
    };
  }, []);

  // Track last non-empty text selection anywhere in the document
  useEffect(() => {
    const updateSelection = () => {
      try {
        const sel = window.getSelection();
        const t = sel && !sel.isCollapsed ? sel.toString().trim() : "";
        if (t) {
          lastSelectionRef.current = t;
        }
      } catch {}
    };
    document.addEventListener('selectionchange', updateSelection);
    document.addEventListener('mouseup', updateSelection);
    return () => {
      document.removeEventListener('selectionchange', updateSelection);
      document.removeEventListener('mouseup', updateSelection);
    };
  }, []);

  useEffect(() => {
    const handler = (e: Event) => {
      const anyEvt = e as CustomEvent<{ question?: string }>
      const q = anyEvt?.detail?.question
      if (typeof q === 'string') {
        setInput(q)
      }
    }
    const openFeedback = (e: Event) => {
      const detail = (e as CustomEvent<{ feedbackText?: string; selectedText?: string; metadata?: Record<string, unknown> }>).detail || {}
      setFeedbackDialogState({ open: true, feedbackText: detail.feedbackText || '', selectedText: detail.selectedText || '' })
      ;(window as any).__gk_feedback_metadata__ = detail.metadata || {}
    }
    const openCorrection = (e: Event) => {
      const detail = (e as CustomEvent<{ incorrectText?: string; correctedText?: string; explanation?: string; metadata?: Record<string, unknown> }>).detail || {}
      setCorrectionDialogState({ open: true, incorrectText: detail.incorrectText || '', correctedText: detail.correctedText || '' })
      ;(window as any).__gk_correction_meta__ = { explanation: detail.explanation || '', metadata: detail.metadata || {} }
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('chat:followup', handler as EventListener)
      window.addEventListener('chat:open-feedback-dialog', openFeedback as EventListener)
      window.addEventListener('chat:open-correction-dialog', openCorrection as EventListener)
    }
    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('chat:followup', handler as EventListener)
        window.removeEventListener('chat:open-feedback-dialog', openFeedback as EventListener)
        window.removeEventListener('chat:open-correction-dialog', openCorrection as EventListener)
      }
    }
  }, [])

  type ClientMessage = ChatUIMessage;

  const normalizeAssistantMetadata = (meta: unknown): ChatMessageMetadata | undefined => {
    if (!isRecord(meta)) return undefined;
    const nested = meta.messageMetadata;
    if (isRecord(nested)) {
      return nested as ChatMessageMetadata;
    }
    return meta as ChatMessageMetadata;
  };

  const overlayDripMs = useMemo(() => {
    const raw = process.env.NEXT_PUBLIC_STREAM_DRIP_MS
    const parsed = raw ? Number(raw) : NaN
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 16
  }, [])

  const streamInBubble = useMemo(() => {
    return process.env.NEXT_PUBLIC_STREAM_IN_BUBBLE !== 'false'
  }, [])

  const enableMultiStepLoader = useMemo(() => {
    return process.env.NEXT_PUBLIC_ENABLE_MULTI_STEP_LOADER === 'true'
  }, [])

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
    setLiveTimelineSteps(steps);
  };

  const scheduleTimelineRecompute = (streaming: boolean) => {
    if (timelineTimeoutRef.current !== null) return;
    const flush = () => {
      timelineTimeoutRef.current = null;
      if (timelineRafRef.current === null) {
        timelineRafRef.current = requestAnimationFrame(() => {
          timelineRafRef.current = null;
          const steps = computeTimeline({
            dataParts: liveTimelinePartsRef.current,
            metadata: liveTimelineMetadataRef.current,
            content: '',
            agentType: liveTimelineAgentRef.current,
            isStreaming: streaming,
          });
          setLiveTimelineSteps(steps);
        });
      }
    };
    timelineTimeoutRef.current = window.setTimeout(flush, 16);
  };

  const resetLiveTimeline = (agent: AgentType) => {
    liveTimelinePartsRef.current = [];
    liveTimelineMetadataRef.current = null;
    liveTimelineAgentRef.current = agent;
    setLiveTimelineSteps([]);
  };

  const clearOverlayQueue = () => {
    overlayQueueRef.current = [];
    if (overlayDripTimeoutRef.current !== null) {
      window.clearTimeout(overlayDripTimeoutRef.current);
      overlayDripTimeoutRef.current = null;
    }
  };


  const scheduleOverlayFlush = (immediate = false) => {
    if (overlayDripTimeoutRef.current !== null) {
      return;
    }

    const pump = () => {
      overlayDripTimeoutRef.current = null;
      const nextSegment = overlayQueueRef.current.shift();
      if (typeof nextSegment !== 'string') {
        return;
      }

      streamBufferRef.current += nextSegment;
      if (overlayRafRef.current === null) {
        overlayRafRef.current = requestAnimationFrame(() => {
          overlayRafRef.current = null;
          setOverlayText(streamBufferRef.current);
        });
      }

      if (overlayQueueRef.current.length > 0) {
        overlayDripTimeoutRef.current = window.setTimeout(pump, reducedMotion ? 0 : overlayDripMs)
      }
    };

    overlayDripTimeoutRef.current = window.setTimeout(
      pump,
      immediate || reducedMotion ? 0 : overlayDripMs,
    );
  };

  const { messages, sendMessage, status, error } = useChat<ClientMessage>({
    // Use a stable client-side chat id to avoid UI resets during initial send
    id: chatIdRef.current,
    transport,
    experimental_throttle: 16, // Slightly faster updates for in-bubble streaming
    onError: (e) => console.error("AI chat error:", e),
    onData: (chunk: unknown) => {
      if (!isRecord(chunk)) return;
      const typeValue = chunk.type;
      if (typeof typeValue !== 'string') return;
      const type = typeValue;

      if (type === 'error') {
        if (overlayRafRef.current !== null) {
          cancelAnimationFrame(overlayRafRef.current);
          overlayRafRef.current = null;
        }
        clearOverlayQueue();
        streamBufferRef.current = '';
        setOverlayText('');
        setIsOverlayActive(false);
        scheduleTimelineRecompute(false);
        return;
      }

      if (type === 'text-start' || type === 'start') {
        if (!streamInBubble) {
          streamBufferRef.current = '';
          clearOverlayQueue();
          setOverlayAgent(liveTimelineAgentRef.current ?? 'primary');
          setIsOverlayActive(true);
          setOverlayText('');
        }
        scheduleTimelineRecompute(true);
        return;
      }
      if (type === 'text-delta') {
        if (streamInBubble) {
          // Bubble handles live text; no overlay updates needed
          return;
        }
        const deltaValue = typeof (chunk as Record<string, unknown>).delta === 'string'
          ? (chunk as Record<string, unknown>).delta as string
          : '';
        if (deltaValue) {
          if (reducedMotion) {
            streamBufferRef.current += deltaValue;
            if (overlayRafRef.current === null) {
              overlayRafRef.current = requestAnimationFrame(() => {
                overlayRafRef.current = null;
                setOverlayText(streamBufferRef.current);
              });
            }
          } else {
            if (deltaValue.length > 1) {
              overlayQueueRef.current.push(...deltaValue.split(''));
            } else {
              overlayQueueRef.current.push(deltaValue);
            }
            scheduleOverlayFlush(true);
          }
        }
        return;
      }

      if (type === 'text-end') {
        if (!streamInBubble) {
          if (overlayRafRef.current !== null) {
            cancelAnimationFrame(overlayRafRef.current);
            overlayRafRef.current = null;
          }
          clearOverlayQueue();
          streamBufferRef.current = '';
          setIsOverlayActive(false);
        }
        scheduleTimelineRecompute(false);
        return;
      }

      if (type === 'data' || type.startsWith('data-')) {
        const dataPart = (chunk as Record<string, unknown>).data;
        if (dataPart !== undefined) {
          if (type === 'data-assistant-structured') {
            liveTimelinePartsRef.current = [
              ...liveTimelinePartsRef.current,
              {
                type: 'timeline-step',
                data: {
                  type: 'Structured summary',
                  description: 'Final structured payload available',
                  status: 'completed',
                },
              },
            ];
          }

          if (type.startsWith('data-interrupt-')) {
            const suffix = type.replace('data-interrupt-', '');
            const reason = isRecord(dataPart) && typeof (dataPart as any).reason === 'string' ? (dataPart as any).reason : undefined;
            const required = isRecord(dataPart) && typeof (dataPart as any).required_action === 'string' ? (dataPart as any).required_action : undefined;
            const title = 'Human approval';
            const desc = [reason, required].filter(Boolean).join(' — ');
            const status = suffix === 'pending' ? 'in_progress' : suffix === 'resumed' ? 'completed' : 'failed';
            liveTimelinePartsRef.current = [
              ...liveTimelinePartsRef.current,
              {
                type: 'timeline-step',
                data: {
                  type: title,
                  description: desc,
                  status,
                },
              },
            ];
          }

          if (type === 'data-tool-result' && isRecord(dataPart)) {
            const statusSource = dataPart.status ?? dataPart.state ?? 'completed';
            const statusRaw =
              typeof statusSource === 'string'
                ? statusSource.toLowerCase()
                : String(statusSource).toLowerCase();
            const status =
              statusRaw.includes('fail') || statusRaw.includes('error')
                ? 'failed'
                : statusRaw.includes('progress')
                  ? 'in_progress'
                  : 'completed';

            const toolName = readStringProperty(
              dataPart,
              ['tool_name', 'toolName', 'name', 'id'],
              'Tool',
            );

            const detailSource =
              dataPart.reasoning ?? dataPart.summary ?? dataPart.output ?? dataPart.result ?? '';
            const detail =
              typeof detailSource === 'string'
                ? detailSource
                : JSON.stringify(detailSource, null, 2);

            liveTimelinePartsRef.current = [
              ...liveTimelinePartsRef.current,
              {
                type: 'timeline-step',
                data: {
                  type: `Tool: ${toolName}`,
                  description: detail,
                  status,
                },
              },
            ];
          }

          if (type === 'data-followups') {
            const suggestions = isStringArray(dataPart)
              ? dataPart.slice(0, 3).join('\n• ')
              : undefined;
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

          const normalized =
            type === 'data'
              ? toChatDataPart(dataPart)
              : toChatDataPart({ type, data: dataPart });

          if (normalized) {
            liveTimelinePartsRef.current = [...liveTimelinePartsRef.current, normalized];
          } else {
            const fallbackPart: ChatDataPart = { type, data: dataPart };
            liveTimelinePartsRef.current = [...liveTimelinePartsRef.current, fallbackPart];
          }

          scheduleTimelineRecompute(true);
        }
        return;
      }

      if (type === 'reasoning' || type.startsWith('reasoning-')) {
        const recordChunk = chunk as Record<string, unknown>;
        const deltaValue =
          typeof recordChunk.delta === 'string'
            ? recordChunk.delta
            : typeof recordChunk.text === 'string'
              ? recordChunk.text
              : '';
        const isEnd = type === 'reasoning-end' || type === 'reasoning-part-finish';

        liveTimelinePartsRef.current = [
          ...liveTimelinePartsRef.current,
          {
            type: 'timeline-step',
            data: {
              type: 'Reasoning',
              description:
                deltaValue || (type === 'reasoning-start' ? 'Starting reasoning…' : undefined),
              status: isEnd ? 'completed' : 'in-progress',
            },
          },
        ];

        const currentMetadata: ChatMessageMetadata = liveTimelineMetadataRef.current ?? {};
        const prevSteps = Array.isArray(currentMetadata.thinking_trace?.thinking_steps)
          ? (currentMetadata.thinking_trace!.thinking_steps as Array<Record<string, unknown>>)
          : [];
        const mergedSteps =
          deltaValue && deltaValue.trim().length > 0
            ? [...prevSteps, { phase: 'REASONING', thought: deltaValue }]
            : prevSteps;

        liveTimelineMetadataRef.current = {
          ...currentMetadata,
          thinking_trace: { thinking_steps: mergedSteps },
        };

        scheduleTimelineRecompute(true);
        return;
      }

      if (type.startsWith('tool-') || type.startsWith('source-')) {
        const recordChunk = chunk as Record<string, unknown>;
        const callIdSource = recordChunk.toolCallId ?? recordChunk.id;
        const callId = typeof callIdSource === 'string' ? callIdSource : undefined;
        const toolName =
          typeof recordChunk.toolName === 'string'
            ? recordChunk.toolName
            : typeof recordChunk.name === 'string'
              ? recordChunk.name
              : 'Tool';
        const desc =
          typeof recordChunk.inputTextDelta === 'string'
            ? recordChunk.inputTextDelta
            : typeof recordChunk.errorText === 'string'
              ? recordChunk.errorText
              : '';

        const level =
          type.includes('error')
            ? 'failed'
            : type.includes('available') || type.includes('output') || type.includes('end')
              ? 'completed'
              : 'in-progress';

        liveTimelinePartsRef.current = [
          ...liveTimelinePartsRef.current,
          {
            type: 'timeline-step',
            data: {
              type: `Tool: ${toolName}`,
              description: desc,
              status: level,
              id: callId,
            },
          },
        ];
        scheduleTimelineRecompute(true);
        return;
      }

      if (type === 'message-metadata') {
        const meta = (chunk as Record<string, unknown>).messageMetadata;
        if (isRecord(meta)) {
          const currentMetadata: ChatMessageMetadata = liveTimelineMetadataRef.current ?? {};
          liveTimelineMetadataRef.current = {
            ...currentMetadata,
            ...meta,
          };

          if (
            (!liveTimelineAgentRef.current || liveTimelineAgentRef.current === 'primary') &&
            (meta.analysisResults || meta.logMetadata)
          ) {
            liveTimelineAgentRef.current = 'log_analysis';
          }

          const memSnippet = (meta as any)?.memory_snippet || (meta as any)?.memorySnippet || (meta as any)?.memory?.snippet;
          if (typeof memSnippet === 'string' && memSnippet.trim().length > 0) {
            liveTimelinePartsRef.current = [
              ...liveTimelinePartsRef.current,
              {
                type: 'timeline-step',
                data: {
                  type: 'Memory context',
                  description: memSnippet,
                  status: 'completed',
                },
              },
            ];
          }

          scheduleTimelineRecompute(true);
        }
        return;
      }

      if (type === 'finish') {
        if (overlayRafRef.current !== null) {
          cancelAnimationFrame(overlayRafRef.current);
          overlayRafRef.current = null;
        }
        clearOverlayQueue();
        streamBufferRef.current = '';
        setIsOverlayActive(false);
        return;
      }
    },
    onFinish: async ({ message: assistantMessage, messages: chatMessages }) => {
      if (overlayRafRef.current !== null) {
        cancelAnimationFrame(overlayRafRef.current);
        overlayRafRef.current = null;
      }
      clearOverlayQueue();
      streamBufferRef.current = '';
      setOverlayText('');
      setIsOverlayActive(false);
      const activeSessionId = sessionId || lastPersistedSessionIdRef.current;
      if (!activeSessionId) return;

      try {
        const lastUser = [...chatMessages].reverse().find((m) => m.role === 'user');
        const userText = lastUser ? getMessageText(lastUser).trim() : "";
        const assistantText = getMessageText(assistantMessage).trim();
        const timelineAgent = (liveTimelineAgentRef.current ?? activeAgent) as InteractiveAgent;
        const assistantMetadata = normalizeAssistantMetadata(assistantMessage.metadata);
        const assistantAgent: InteractiveAgent = assistantMetadata && (
          assistantMetadata.analysisResults ||
          assistantMetadata.logMetadata ||
          assistantMetadata.errorSnippets
        )
          ? 'log_analysis'
          : timelineAgent;

        if (userText) {
          await sessionsAPI.postMessage(activeSessionId, {
            message_type: 'user',
            agent_type: timelineAgent,
            content: userText,
          });

          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('chat-session-updated', {
                detail: {
                  sessionId: String(activeSessionId),
                  agentType: timelineAgent,
                },
              }),
            );
          }

          if (!hasRenamedRef.current && latestCreatedSessionRef.current === String(activeSessionId)) {
            const nextTitle = deriveChatTitle(userText);
            try {
              const updatedSession = await sessionsAPI.rename(activeSessionId, nextTitle);
              hasRenamedRef.current = true;
              latestCreatedSessionRef.current = null;

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

        if (assistantText) {
          const metadataPayload: Record<string, unknown> = {};
          const messageMetadata = assistantMessage.metadata;
          if (messageMetadata && Object.keys(messageMetadata).length > 0) {
            metadataPayload.messageMetadata = messageMetadata;
          }
          const dataParts = getDataParts(assistantMessage);
          if (dataParts.length > 0) {
            metadataPayload.dataParts = dataParts;
          }

          await sessionsAPI.postMessage(activeSessionId, {
            message_type: 'assistant',
            agent_type: assistantAgent,
            content: assistantText,
            ...(Object.keys(metadataPayload).length > 0 ? { metadata: metadataPayload } : {}),
          });

          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('chat-session-updated', {
                detail: {
                  sessionId: String(activeSessionId),
                  agentType: assistantAgent,
                },
              }),
            );
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
      scheduleTimelineRecompute(true);
    }
  }, [status, liveTimelineSteps.length]);

  useEffect(() => {
    if (status === 'submitted' || status === 'streaming') {
      setShowBeams(false);
    }
  }, [status]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initialize local auth on mount (for development)
  useEffect(() => {
    initializeLocalAuth().catch(console.error);
  }, []);

  // Sync active agent -> current provider/model from saved per-agent selections
  useEffect(() => {
    if (activeAgent === 'log_analysis') {
      setProvider(logProvider);
      setModel(logModel);
    } else {
      setProvider(primaryProvider);
      setModel(primaryModel);
    }
  }, [activeAgent]);

  // Model list fetch (parallel) on mount with graceful fallback
  useEffect(() => {
    let mounted = true;
    const fetchLists = async () => {
      const fallbackPrimary = ['gemini-2.5-flash', 'gpt-5-mini'];
      const fallbackLog = ['gemini-2.5-pro'];
      try {
        const [p, l] = await Promise.all([
          fetch('/api/v1/models?agent=primary').then(r => r.ok ? r.json() : Promise.reject()).catch(() => ({ models: fallbackPrimary })),
          fetch('/api/v1/models?agent=log_analysis').then(r => r.ok ? r.json() : Promise.reject()).catch(() => ({ models: fallbackLog })),
        ]);
        if (!mounted) return;
        const priRaw = Array.isArray(p?.models) ? (p.models as string[]) : fallbackPrimary;
        const logRaw = Array.isArray(l?.models) ? (l.models as string[]) : fallbackLog;
        // Enforce allowed sets
        const pri = priRaw.filter(m => m === 'gemini-2.5-flash' || m === 'gpt-5-mini');
        const log = logRaw.filter(m => m === 'gemini-2.5-pro');
        setPrimaryModels(pri.length ? pri : fallbackPrimary);
        setLogModels(log.length ? log : fallbackLog);
        // Ensure current selections are valid
        if (!(pri.length ? pri : fallbackPrimary).includes(primaryModel)) setPrimaryModel((pri.length ? pri : fallbackPrimary)[0]);
        if (!(log.length ? log : fallbackLog).includes(logModel)) setLogModel('gemini-2.5-pro');
      } catch {
        if (!mounted) return;
        setPrimaryModels(fallbackPrimary);
        setLogModels(fallbackLog);
      }
    };
    fetchLists();
    return () => { mounted = false };
  }, []);

  const providerForModel = (m: string): 'google' | 'openai' =>
    (m || '').toLowerCase().startsWith('gpt') ? 'openai' : 'google';

  // Respect reduced-motion preference for subtle animations
  useEffect(() => {
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
      if (latestCreatedSessionRef.current === sessionId) {
        hasRenamedRef.current = false;
      } else {
        hasRenamedRef.current = true;
      }
      lastPersistedSessionIdRef.current = sessionId;
    } else {
      fallbackSessionRef.current = crypto.randomUUID();
      lastPersistedSessionIdRef.current = "";
      latestCreatedSessionRef.current = null;
      hasRenamedRef.current = false;
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
    const dataParts = getDataParts(lastAssistant);
    const followupsPart = dataParts.find((part) => part.type === 'data-followups');
    const followupsData = followupsPart?.data;
    setFollowUpQuestions(isStringArray(followupsData) ? followupsData : null);
    const toolPart = dataParts.find(
      (part) => part.type === 'data-tool-result' || part.type === 'tool-result',
    );
    const toolData = toolPart?.data;
    setToolDecision(isRecord(toolData) ? (toolData as ToolDecisionRecord) : null);
  }, [messages]);

  const captureSelection = useCallback((): string => {
    if (typeof window === "undefined") return "";
    try {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) {
        return "";
      }
      return selection.toString().trim();
    } catch {
      return "";
    }
  }, []);

  const handleSlashCommand = useCallback(
    (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed.startsWith("/")) {
        return false;
      }

      const spaceIndex = trimmed.indexOf(" ");
      const command = spaceIndex === -1 ? trimmed : trimmed.slice(0, spaceIndex);
      const remainder = spaceIndex === -1 ? "" : trimmed.slice(spaceIndex + 1).trim();
      const selectionText = captureSelection() || lastSelectionRef.current;

      if (command === "/feedback") {
        setFeedbackDialogState({
          open: true,
          feedbackText: remainder,
          selectedText: selectionText,
        });
        setMediaFiles([]);
        setLogFile(null);
        setAttachError(null);
        if (selectionText) {
          toast.message("Selected text captured for feedback.");
        }
        return true;
      }

      if (command === "/correct") {
        setCorrectionDialogState({
          open: true,
          incorrectText: selectionText || remainder,
          correctedText: selectionText ? "" : remainder,
        });
        setMediaFiles([]);
        setLogFile(null);
        setAttachError(null);
        if (selectionText) {
          toast.message("Selected text prefilled into Incorrect response.");
        }
        return true;
      }

      return false;
    },
    [captureSelection, setAttachError, setMediaFiles, setLogFile, setFeedbackDialogState, setCorrectionDialogState],
  );

  const onSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const rawText = (input || interimVoice || "").trim();
    if (!rawText && mediaFiles.length === 0 && !logFile) {
      return;
    }

    if (rawText && handleSlashCommand(rawText)) {
      setInput("");
      setInterimVoice("");
      return;
    }

    // Pre-flight rate limit check for Gemini models
    try {
      if (provider === "google") {
        const modelForCheck: 'gemini-2.5-flash' | 'gemini-2.5-pro' = model.includes("pro")
          ? "gemini-2.5-pro"
          : "gemini-2.5-flash";
        const check = await rateLimitApi.checkRateLimit(modelForCheck);
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

    const text = rawText;
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
        latestCreatedSessionRef.current = createdId;
        hasRenamedRef.current = false;
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('chat-session-updated', {
              detail: {
                sessionId: String(createdId),
                agentType: desiredAgent,
              },
            }),
          );
          window.dispatchEvent(new Event('chat-sessions:refresh'));
        }
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
            useServerMemory: memoryEnabled,
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

  // Hide beams when any content (history or live messages) exists; show when empty/new chat
  useEffect(() => {
    if (hasContent) {
      setShowBeams(false);
    } else {
      setShowBeams(true);
    }
  }, [hasContent, sessionId]);


  return (
    <div className="relative min-h-svh">
      {showBeams && (
        <div className="absolute inset-0 z-0 pointer-events-none">
          <BackgroundBeamsWithCollision className="h-full from-transparent to-transparent dark:from-transparent dark:to-transparent">
            <div />
          </BackgroundBeamsWithCollision>
        </div>
      )}
      {/* Main content - centered container */}
      <div className="relative z-10 flex flex-col min-h-svh">
        {/* Header */}
        <header className="sticky top-0 z-50 h-14 backdrop-blur-lg border-b border-border/40 bg-[hsl(var(--brand-surface)/0.95)]">
          <div className="w-full h-full px-4">
            <div className="flex h-full items-center justify-start gap-3 sm:gap-4">
              <div className="flex items-center gap-2" aria-label="Primary agent model">
                <span className="text-xs text-muted-foreground">Primary</span>
                <Select value={primaryModel} onValueChange={(m) => {
                  setPrimaryModel(m);
                  const p = providerForModel(m);
                  setPrimaryProvider(p);
                  if (activeAgent === 'primary' && !logFile) {
                    setProvider(p);
                    setModel(m);
                  }
                }}>
                  <SelectTrigger className="h-8 w-48" aria-label="Primary model selector">
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {(primaryModels.length ? primaryModels : [primaryModel]).map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2" aria-label="Log analysis model">
                <span className="text-xs text-muted-foreground">Log Analysis</span>
                <Select value={logModel} onValueChange={(m) => {
                  setLogModel(m);
                  const p = providerForModel(m);
                  setLogProvider(p);
                  if (activeAgent === 'log_analysis') {
                    setProvider(p);
                    setModel(m);
                  }
                }}>
                  <SelectTrigger className="h-8 w-48" aria-label="Log analysis model selector">
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {(logModels.length ? logModels : [logModel]).map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {interruptsEnabled && (
                <Button size="sm" variant="default" onClick={handleStartSupervisedRun} aria-label="Start supervised run" disabled={interruptLoading}>
                  Start supervised run
                </Button>
              )}

              <APIKeyStatusBadge
                className="bg-muted text-foreground/70 border-border/40 hover:scale-100 active:scale-100 cursor-default text-sm py-1"
              />

              <FeedMeButton />
              <SettingsButtonV2 />
            </div>
          </div>
        </header>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-4 py-8">
            {/* Live Streaming Overlay (full-bleed) */}
            {(isOverlayActive || (overlayText && overlayText.trim().length > 0)) && (
              <StreamingOverlay
                text={overlayText}
                timelineSteps={liveTimelineSteps}
                agentType={overlayAgent}
                reducedMotion={reducedMotion}
                dripDelayMs={overlayDripMs}
              />
            )}
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
                  const fullMeta = m.metadata;
                  const assistantMetadata = normalizeAssistantMetadata(fullMeta ?? undefined);
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

                  const rawHistoryDataParts =
                    isRecord(fullMeta) && Array.isArray(fullMeta['dataParts'])
                      ? (fullMeta['dataParts'] as unknown[])
                      : [];
                  const dataParts = rawHistoryDataParts
                    .map(toChatDataPart)
                    .filter((part): part is ChatDataPart => part !== null);
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
                          {!enableMultiStepLoader && timelineSteps.length > 0 && (
                            <WorkingTimeline steps={timelineSteps} variant="final" />
                          )}
                          <AssistantMessage
                            content={m.content}
                            metadata={assistantMetadata}
                            isLogAnalysis={isLogHistory}
                          />
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
                  const meta = normalizeAssistantMetadata(m.metadata);
                  const dataParts = getDataParts(m);
                  const followupsFromParts = (() => {
                    const fp = dataParts.find((part) => part.type === 'data-followups');
                    const arr = (fp && (fp as any).data) as unknown;
                    return Array.isArray(arr) && arr.every((x) => typeof x === 'string') ? (arr as string[]) : undefined;
                  })();
                  const metaEnhanced = followupsFromParts && followupsFromParts.length > 0
                    ? ({ ...meta, followUpQuestions: followupsFromParts } as typeof meta)
                    : meta;
                  const logHints = Boolean(
                    m.agentType === 'log_analysis' ||
                      meta?.logMetadata ||
                      meta?.errorSnippets ||
                      meta?.rootCause ||
                      meta?.analysisResults ||
                      (isStreamingMessage && activeAgent === 'log_analysis')
                  );
                  const agentTypeForTimeline = logHints ? 'log_analysis' : 'primary';
                  const computedSteps = computeTimeline({
                    dataParts,
                    metadata: metaEnhanced,
                    content: contentText,
                    agentType: agentTypeForTimeline,
                    isStreaming: m.role === 'assistant' ? isStreamingMessage : false,
                  });
                  const stepsToRender = (m.role === 'assistant' && isStreamingMessage)
                    ? (liveTimelineSteps.length > 0 ? liveTimelineSteps : computedSteps)
                    : computedSteps;

                  const isLastAssistant = m.role === 'assistant' && isLast;
                  const hideAssistant = isLastAssistant && isOverlayActive;

                  return (
                    <div
                      key={m.id ?? idx}
                      className={`flex gap-4 animate-in slide-in-from-bottom-2 fade-in duration-300 ${
                        m.role === "user" ? "justify-end" : "justify-center"
                      }`}
                      style={{ animationDelay: `${idx * 50}ms` }}
                    >
                      {m.role === "assistant" && !hideAssistant ? (
                        enableMultiStepLoader && isStreamingMessage ? (
                          (() => {
                            const gridCols = "md:grid-cols-[320px_minmax(0,1fr)]";
                            const LoaderPanel = () => {
                              const loaderSteps = (liveTimelineSteps.length > 0 ? liveTimelineSteps : stepsToRender)
                              const states = loaderSteps.map(s => ({ text: s.title }))
                              let activeIndex = 0
                              if (loaderSteps.length > 0) {
                                const lastInProgress = [...loaderSteps].map((s, i) => ({ s, i })).reverse().find(x => x.s.status === 'in_progress')
                                const lastCompleted = [...loaderSteps].map((s, i) => ({ s, i })).reverse().find(x => x.s.status === 'completed')
                                activeIndex = lastInProgress?.i ?? lastCompleted?.i ?? 0
                              }
                              return (
                                <div className="hidden md:block self-start">
                                  <MultiStepLoader
                                    variant="inline"
                                    className=""
                                    loading={true}
                                    loadingStates={states}
                                    activeIndex={activeIndex}
                                    duration={1200}
                                    loop={true}
                                  />
                                </div>
                              )
                            }
                            return (
                              <div className={`grid grid-cols-1 ${gridCols} gap-4 w-full`}>
                                <LoaderPanel />
                                <div className="w-full max-w-3xl space-y-2">
                                  {/* Hide WorkingTimeline while loader is active to avoid duplication */}
                                  <AssistantMessage
                                    content={contentText}
                                    metadata={metaEnhanced}
                                    isLogAnalysis={logHints}
                                    showActions={false}
                                  />
                                </div>
                              </div>
                            )
                          })()
                        ) : (
                          <div className="w-full max-w-3xl mx-auto space-y-2">
                            {!enableMultiStepLoader && stepsToRender.length > 0 && (
                              <WorkingTimeline
                                steps={stepsToRender}
                                variant={isStreamingMessage ? 'live' : 'final'}
                              />
                            )}
                            <AssistantMessage
                              content={contentText}
                              metadata={metaEnhanced}
                              isLogAnalysis={logHints}
                              showActions={false}
                            />
                          </div>
                        )
                      ) : m.role === 'assistant' && hideAssistant ? null : (
                        <div className="max-w-[85%] rounded-2xl px-5 py-3 bg-primary/10 dark:bg-primary/20 text-foreground border border-primary/20">
                          <div className="space-y-2">
                            <div className="text-[15px] leading-relaxed whitespace-pre-wrap">
                              {contentText}
                            </div>
                            {(() => {
                              const fileParts = getFileParts(m).filter(
                                (fp) => !(typeof fp.mediaType === 'string' && fp.mediaType.startsWith('text/')),
                              );
                              return fileParts.length > 0 ? (
                                <div className="flex flex-wrap gap-2 pt-1">
                                  {fileParts.map((fp, i) => (
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

              </div>
            )}

            {/* Tool decision card removed */}

            {/* Error message */}
            {error && (
              <div className="mt-4 p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive">
                <p className="text-sm">
                  {error instanceof Error ? error.message : String(error)}
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
                memoryEnabled={memoryEnabled}
                onToggleMemory={setMemoryEnabled}
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
      <FeedbackDialog
        open={feedbackDialogState.open}
        initialFeedback={feedbackDialogState.feedbackText}
        selectedText={feedbackDialogState.selectedText}
        metadata={typeof window !== 'undefined' ? (window as any).__gk_feedback_metadata__ : undefined}
        sessionId={sessionId}
        agent={activeAgent}
        model={model}
        onClose={() =>
          setFeedbackDialogState({
            open: false,
            feedbackText: "",
            selectedText: "",
          })
        }
      />
      <CorrectionDialog
        open={correctionDialogState.open}
        initialIncorrect={correctionDialogState.incorrectText}
        initialCorrected={correctionDialogState.correctedText}
        initialExplanation={typeof window !== 'undefined' ? ( ( (window as any).__gk_correction_meta__?.explanation ) || '' ) : ''}
        metadata={typeof window !== 'undefined' ? ( (window as any).__gk_correction_meta__?.metadata ) : undefined}
        sessionId={sessionId}
        agent={activeAgent}
        model={model}
        onClose={() =>
          setCorrectionDialogState({
            open: false,
            incorrectText: "",
            correctedText: "",
          })
        }
      />
      <InterruptOverlay
        open={interruptOpen}
        threadId={interruptThreadId}
        interrupts={pendingInterrupts}
        loading={interruptLoading}
        onDecision={handleInterruptDecision}
        onClose={() => setInterruptOpen(false)}
      />
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
  const [activeTab, setActiveTab] = useState<LeftTab>('primary');
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  const [rightPanelTop, setRightPanelTop] = useState<number>(96);
  const [rightPanelLeft, setRightPanelLeft] = useState<number | undefined>(undefined);
  const rightAutoCloseTimerRef = useRef<number | null>(null);

  const handleSelectSession = (id?: string) => {
    setSessionId(id || '');
    setViewKey((prev: number) => prev + 1);
  };

  const activeSessionId = sessionId || undefined;
  
  const openRightSidebar = useCallback((top?: number, left?: number) => {
    if (typeof top === 'number' && !Number.isNaN(top)) {
      setRightPanelTop(Math.max(64, Math.round(top)));
    }
    if (typeof left === 'number' && !Number.isNaN(left)) {
      setRightPanelLeft(Math.max(0, Math.round(left)));
    }
    setIsRightSidebarOpen(true);
    if (rightAutoCloseTimerRef.current) {
      window.clearTimeout(rightAutoCloseTimerRef.current);
    }
    rightAutoCloseTimerRef.current = window.setTimeout(() => {
      setIsRightSidebarOpen(false);
      rightAutoCloseTimerRef.current = null;
    }, 3000);
  }, []);

  useEffect(() => {
    if (!isRightSidebarOpen) return;

    const cancelTimer = () => {
      if (rightAutoCloseTimerRef.current) {
        window.clearTimeout(rightAutoCloseTimerRef.current);
        rightAutoCloseTimerRef.current = null;
      }
    };

    const onDocMouseDown = (e: MouseEvent) => {
      const panel = document.getElementById('right-context-sidebar');
      if (panel && !panel.contains(e.target as Node)) {
        setIsRightSidebarOpen(false);
        cancelTimer();
      }
    };

    document.addEventListener('mousedown', onDocMouseDown);
    const panel = document.getElementById('right-context-sidebar');
    if (panel) {
      panel.addEventListener('mouseenter', cancelTimer);
      panel.addEventListener('focusin', cancelTimer);
      panel.addEventListener('mousedown', cancelTimer);
    }
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      if (panel) {
        panel.removeEventListener('mouseenter', cancelTimer);
        panel.removeEventListener('focusin', cancelTimer);
        panel.removeEventListener('mousedown', cancelTimer);
      }
    };
  }, [isRightSidebarOpen]);

  const handleNewChat = useCallback(async () => {
    try {
      const desiredAgent: 'primary' | 'log_analysis' = activeTab === 'log' ? 'log_analysis' : 'primary';
      const session = await sessionsAPI.create(desiredAgent);
      const createdId = String(session.id);
      setSessionId(createdId);
      setViewKey((prev: number) => prev + 1);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('chat-session-updated', {
            detail: { sessionId: createdId, agentType: desiredAgent },
          }),
        );
        window.dispatchEvent(new Event('chat-sessions:refresh'));
      }
    } catch (e) {
      console.error('Failed to create new chat session:', e);
    }
  }, [activeTab]);

  return (
    <SidebarProvider defaultOpen={true}>
      <AppSidebarLeft
        activeTab={activeTab}
        onChangeTab={setActiveTab}
        onOpenRightSidebar={openRightSidebar}
        onNewChat={handleNewChat}
      />
      <RightContextSidebar 
        activeTab={activeTab} 
        sessionId={activeSessionId} 
        onSelectSession={handleSelectSession}
        isOpen={isRightSidebarOpen}
        top={rightPanelTop}
        left={rightPanelLeft}
      />
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
