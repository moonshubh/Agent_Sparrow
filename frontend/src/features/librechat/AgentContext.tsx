'use client';

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import type { Message, RunAgentInput } from '@/services/ag-ui/client';
import type { DocumentPointer, AttachmentInput, InterruptPayload } from '@/services/ag-ui/types';
import {
  isAgentCustomEvent,
  type TimelineOperation,
  type TraceStep,
  type TodoItem,
  type ToolEvidenceCard,
  type ToolEvidenceUpdateEvent,
} from '@/services/ag-ui/event-types';
import { sessionsAPI, type AgentType as PersistedAgentType } from '@/services/api/endpoints/sessions';
import { getGlobalArtifactStore } from './artifacts';
import type { Artifact } from './artifacts/types';
import { formatLogAnalysisResult } from './formatters/logFormatter';
import {
  stripCodeFence,
  extractTodosFromPayload,
  formatIfStructuredLog,
} from './utils';

/**
 * Serializable artifact data for persistence in message metadata.
 * Excludes runtime fields like lastUpdateTime and messageId (which will be set on restore).
 */
export interface SerializedArtifact {
  id: string;
  type: Artifact['type'];
  title: string;
  content: string;
  language?: string;
  identifier?: string;
  index?: number;
  // Image artifact fields
  imageData?: string;
  mimeType?: string;
  altText?: string;
  aspectRatio?: string;
  resolution?: string;
}

/**
 * Abstract agent interface for CopilotKit compatibility.
 * This replaces the @ag-ui/client AbstractAgent type.
 */
export interface AbstractAgent {
  messages: Message[];
  state: Record<string, unknown>;
  addMessage: (message: Message) => void;
  setState: (state: Record<string, unknown>) => void;
  runAgent: (input: Partial<RunAgentInput>, handlers: AgentEventHandlers) => Promise<void>;
  abortRun: () => void;
}

/**
 * Event handlers for agent streaming
 */
export interface AgentEventHandlers {
  signal?: AbortSignal;
  onTextMessageContentEvent?: (params: { event: unknown; textMessageBuffer?: string }) => void;
  onMessagesChanged?: (params: { messages: Message[] }) => void;
  onCustomEvent?: (params: { event: unknown }) => unknown | Promise<unknown>;
  onStateChanged?: (params: { state: unknown }) => void;
  onToolCallStartEvent?: (params: { event: unknown }) => void;
  onToolCallResultEvent?: (params: { event: unknown }) => void;
  onRunFailed?: (params: { error: unknown }) => void;
}

interface AgentContextValue {
  agent: AbstractAgent | null;
  sessionId?: string;
  messages: Message[];
  isStreaming: boolean;
  error: Error | null;
  sendMessage: (content: string, attachments?: AttachmentInput[]) => Promise<void>;
  abortRun: () => void;
  registerDocuments: (documents: DocumentPointer[]) => void;
  interrupt: InterruptPayload | null;
  resolveInterrupt: (value: string) => void;
  activeTools: string[];
  timelineOperations: TimelineOperation[];
  currentOperationId?: string;
  toolEvidence: Record<string, ToolEvidenceUpdateEvent>;
  todos: TodoItem[];
  thinkingTrace: TraceStep[];
  activeTraceStepId?: string;
  setActiveTraceStep: (stepId?: string) => void;
  isTraceCollapsed: boolean;
  setTraceCollapsed: (collapsed: boolean) => void;
  resolvedModel?: string;
  resolvedTaskType?: string;
  messageAttachments: Record<string, AttachmentInput[]>;
  updateMessageContent: (messageId: string, content: string) => void;
  updateMessageMetadata: (messageId: string, metadata: Record<string, unknown>) => void;
  resolvePersistedMessageId: (messageId: string | number) => string | number | null;
  regenerateLastResponse: () => Promise<void>;
}

const AgentContext = createContext<AgentContextValue | null>(null);

interface AgentProviderProps {
  children: React.ReactNode;
  agent: AbstractAgent;
  sessionId?: string;
}

// Utility functions moved to ./utils

const MARKDOWN_DATA_URI_PATTERN = /!\[[^\]]*\]\(data:image\/[^)]+\)/gi;

const stripMarkdownDataUriImages = (text: string): string => {
  const replaced = text.replace(MARKDOWN_DATA_URI_PATTERN, '');
  return replaced === text ? text : replaced.trim();
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const isMessageRole = (value: unknown): value is Message['role'] =>
  value === 'user' || value === 'assistant' || value === 'system' || value === 'tool';

const toIsoTimestamp = (value: unknown): string => {
  if (typeof value !== 'string' && typeof value !== 'number') {
    return new Date().toISOString();
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString();
};

const safeJsonStringify = (value: unknown): string => {
  try {
    const serialized = JSON.stringify(value);
    return typeof serialized === 'string' ? serialized : '';
  } catch {
    return '';
  }
};

const getStringFromRecord = (record: Record<string, unknown>, key: string): string | undefined => {
  const value = record[key];
  return typeof value === 'string' ? value : undefined;
};

const getAgentTypeFromState = (state: Record<string, unknown>): string | undefined =>
  getStringFromRecord(state, 'agent_type') ?? getStringFromRecord(state, 'agentType');

const isPersistedAgentType = (value: unknown): value is PersistedAgentType =>
  value === 'primary' || value === 'log_analysis' || value === 'research';

const getPersistedAgentTypeFromState = (state: Record<string, unknown>): PersistedAgentType => {
  const agentType = getAgentTypeFromState(state);
  return isPersistedAgentType(agentType) ? agentType : 'primary';
};

const normalizeTraceType = (rawType: unknown, content: string): TraceStep['type'] => {
  const value = typeof rawType === 'string' ? rawType.toLowerCase() : '';
  if (value === 'tool' || value === 'action') return 'tool';
  if (value === 'result') return 'result';
  if (value === 'warning' || value === 'error') return 'result';
  if (/failed|error/i.test(content)) return 'result';
  return 'thought';
};

const extractToolName = (raw: unknown, content: string): string | undefined => {
  const rawRecord = isRecord(raw) ? raw : null;
  const metadata = rawRecord && isRecord(rawRecord.metadata) ? rawRecord.metadata : {};

  const directCandidates: unknown[] = [
    rawRecord?.toolName,
    metadata.toolName,
    metadata.tool_name,
    metadata.name,
    rawRecord?.name,
  ];
  const direct = directCandidates.find((candidate) => typeof candidate === 'string' && candidate.trim());
  if (typeof direct === 'string') return direct.trim();

  const match = content.match(/(?:Executing|completed|failed)\s+([\w:-]+)/i);
  return match ? match[1] : undefined;
};

const extractDurationSeconds = (raw: unknown): number | undefined => {
  const rawRecord = isRecord(raw) ? raw : null;
  const metadata = rawRecord && isRecord(rawRecord.metadata) ? rawRecord.metadata : {};

  const durationMs = metadata.durationMs ?? metadata.duration_ms ?? rawRecord?.durationMs ?? rawRecord?.duration_ms;
  if (typeof durationMs === 'number' && Number.isFinite(durationMs)) {
    return durationMs / 1000;
  }
  const durationSeconds = metadata.duration ?? rawRecord?.duration;
  if (typeof durationSeconds === 'number' && Number.isFinite(durationSeconds)) {
    return durationSeconds;
  }
  return undefined;
};

const inferTraceStatus = (
  raw: unknown,
  content: string,
  type: TraceStep['type']
): TraceStep['status'] => {
  const rawRecord = isRecord(raw) ? raw : null;
  const metadata = rawRecord && isRecord(rawRecord.metadata) ? rawRecord.metadata : {};
  const metaStatus = metadata.status ?? rawRecord?.status;
  const output = metadata.output ?? metadata.result ?? metadata.data ?? metadata.value;
  const outputError = isRecord(output) ? output.error ?? output.message : undefined;
  if (metaStatus === 'error' || metadata.error || outputError || /failed|error/i.test(content)) {
    return 'error';
  }
  if (type === 'result') return 'success';
  return undefined;
};

const normalizeTraceStep = (raw: unknown): TraceStep => {
  const rawRecord = isRecord(raw) ? raw : {};
  const idValue = rawRecord.id;
  const id = idValue !== undefined && idValue !== null ? String(idValue) : crypto.randomUUID();

  const timestampValue = toIsoTimestamp(rawRecord.timestamp);

  const contentRaw = rawRecord.content;
  const contentValue =
    typeof contentRaw === 'string'
      ? contentRaw
      : safeJsonStringify(contentRaw ?? '');

  const typeValue = normalizeTraceType(rawRecord.type, contentValue);
  const toolName = extractToolName(rawRecord, contentValue);
  const duration = extractDurationSeconds(rawRecord);
  const status = inferTraceStatus(rawRecord, contentValue, typeValue);
  const metadata = isRecord(rawRecord.metadata) ? rawRecord.metadata : {};

  return {
    id,
    type: typeValue,
    timestamp: timestampValue,
    content: contentValue,
    toolName,
    duration,
    status,
    metadata,
  };
};

const mapTraceList = (rawList: unknown[]): TraceStep[] => rawList.map(normalizeTraceStep);

const hasLogAttachment = (attachments?: AttachmentInput[]): boolean => {
  if (!attachments || attachments.length === 0) return false;
  return attachments.some((att) => {
    const name = typeof att?.name === 'string' ? att.name.toLowerCase() : '';
    return name.endsWith('.log');
  });
};

const looksLikeJsonPayload = (text: string): boolean => {
  const trimmed = stripCodeFence(text).trim();
  if (!trimmed) return false;
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) return false;
  return trimmed.length > 80;
};

const estimateAttachmentSizeFromDataUrl = (dataUrl: string): number | null => {
  const commaIndex = dataUrl.indexOf(',');
  if (commaIndex === -1) return null;
  const base64 = dataUrl.slice(commaIndex + 1).trim();
  if (!base64) return null;
  return Math.floor((base64.length * 3) / 4);
};

const normalizeAttachmentForMetadata = (attachment: AttachmentInput): AttachmentInput | null => {
  const name = typeof attachment.name === 'string' ? attachment.name.trim() : '';
  const mimeType = typeof attachment.mime_type === 'string' ? attachment.mime_type.trim() : '';
  const dataUrl = typeof attachment.data_url === 'string' ? attachment.data_url.trim() : '';
  const sizeValue = attachment.size;
  const size =
    typeof sizeValue === 'number' && Number.isFinite(sizeValue)
      ? sizeValue
      : dataUrl
        ? estimateAttachmentSizeFromDataUrl(dataUrl)
        : null;

  if (!name || !mimeType || !dataUrl || !dataUrl.startsWith('data:')) {
    return null;
  }

  return {
    name,
    mime_type: mimeType,
    data_url: dataUrl,
    size: size ?? 0,
  };
};

const normalizePersistedAttachments = (attachments?: AttachmentInput[]): AttachmentInput[] => {
  if (!attachments || attachments.length === 0) return [];
  return attachments
    .map((attachment) => normalizeAttachmentForMetadata(attachment))
    .filter((attachment): attachment is AttachmentInput => Boolean(attachment));
};

const normalizeAttachmentFromMetadata = (raw: unknown): AttachmentInput | null => {
  if (!isRecord(raw)) return null;
  const name = typeof raw.name === 'string' ? raw.name.trim() : '';
  const mimeType = typeof raw.mime_type === 'string' ? raw.mime_type.trim() : '';
  const dataUrl = typeof raw.data_url === 'string' ? raw.data_url.trim() : '';
  const sizeValue = raw.size;
  const size =
    typeof sizeValue === 'number' && Number.isFinite(sizeValue)
      ? sizeValue
      : dataUrl
        ? estimateAttachmentSizeFromDataUrl(dataUrl)
        : null;

  if (!name || !mimeType || !dataUrl || !dataUrl.startsWith('data:')) {
    return null;
  }

  return {
    name,
    mime_type: mimeType,
    data_url: dataUrl,
    size: size ?? 0,
  };
};

const extractPersistedAttachments = (metadata: Record<string, unknown> | undefined): AttachmentInput[] => {
  if (!metadata) return [];
  const rawAttachments = metadata.attachments;
  if (!Array.isArray(rawAttachments)) return [];
  return rawAttachments
    .map((attachment) => normalizeAttachmentFromMetadata(attachment))
    .filter((attachment): attachment is AttachmentInput => Boolean(attachment));
};

const stripLargeMetadata = (
  metadata: Record<string, unknown>
): Record<string, unknown> | undefined => {
  if (!('attachments' in metadata) && !('artifacts' in metadata)) {
    return metadata;
  }
  const { attachments: _attachments, artifacts: _artifacts, ...rest } = metadata;
  return Object.keys(rest).length > 0 ? rest : undefined;
};

const sanitizeMessagesForRun = (currentMessages: Message[]): Message[] =>
  currentMessages.map((message) => {
    if (!isRecord(message.metadata)) return message;
    const sanitizedMetadata = stripLargeMetadata(message.metadata);
    if (sanitizedMetadata === message.metadata) return message;
    if (!sanitizedMetadata) {
      return { ...message, metadata: undefined };
    }
    return { ...message, metadata: sanitizedMetadata };
  });

const normalizeTextFromContentParts = (raw: unknown): string | null => {
  if (typeof raw === 'string') return raw;

  const isNonVisibleBlockType = (value: unknown): boolean => {
    if (!isRecord(value)) return false;
    const typeValue = value.type;
    const type = typeof typeValue === 'string' ? typeValue.toLowerCase() : '';
    return [
      'thinking',
      'reasoning',
      'thought',
      'signature',
      'thought_signature',
      'tool',
      'tool_use',
      'tool_call',
      'tool_calls',
      'function_call',
      'function',
    ].includes(type);
  };

  if (Array.isArray(raw)) {
    const text = raw
      .map((part) => {
        if (typeof part === 'string') return part;
        if (isNonVisibleBlockType(part)) return '';
        if (isRecord(part)) {
          const textValue = part.text;
          if (typeof textValue === 'string') return textValue;
          const contentValue = part.content;
          if (typeof contentValue === 'string') return contentValue;
        }
        return '';
      })
      .join('');
    return text || null;
  }
  if (isRecord(raw)) {
    if (isNonVisibleBlockType(raw)) return null;
    const textValue = raw.text;
    if (typeof textValue === 'string') return textValue;
    const contentValue = raw.content;
    if (typeof contentValue === 'string') return contentValue;
  }
  return null;
};

const stableMessageFallbackId = (params: {
  role: string;
  name: string;
  toolCallId: string;
  index: number;
}): string => {
  const base = `${params.role}|${params.name}|${params.toolCallId}|${params.index}`;
  let hash = 0;
  for (let i = 0; i < base.length; i += 1) {
    hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
  }
  if (process.env.NODE_ENV !== 'production') {
    console.warn('[AG-UI] Message missing id; using stable fallback id', params);
  }
  return `msg-${hash.toString(16)}`;
};

const getToolCallIdFromMessageRecord = (msg: Record<string, unknown>): string => {
  const direct = msg.tool_call_id;
  if (typeof direct === 'string' && direct.trim()) return direct.trim();
  const alt = msg.toolCallId;
  if (typeof alt === 'string' && alt.trim()) return alt.trim();
  return '';
};

const hasToolCallData = (msg: Record<string, unknown>): boolean => {
  const toolCalls = msg.tool_calls ?? msg.toolCalls;
  if (Array.isArray(toolCalls) && toolCalls.length > 0) return true;

  const additional = msg.additional_kwargs ?? msg.additionalKwargs;
  if (!isRecord(additional)) return false;

  return Boolean(additional.function_call || additional.tool_calls || additional.toolCalls);
};

const normalizeMessageContent = (raw: unknown): string => {
  if (typeof raw === 'string') return raw;
  const normalized = normalizeTextFromContentParts(raw);
  if (normalized) return normalized;
  const serialized = safeJsonStringify(raw);
  if (serialized) return serialized;
  return raw === undefined || raw === null ? '' : String(raw);
};

const normalizeIncomingMessage = (raw: unknown, index: number): Message | null => {
  if (!isRecord(raw)) return null;

  const roleRaw = raw.role;
  if (!isMessageRole(roleRaw)) return null;
  const role = roleRaw;

  const name = typeof raw.name === 'string' ? raw.name : undefined;
  const toolCallId = getToolCallIdFromMessageRecord(raw);
  const content = normalizeMessageContent(raw.content);

  // Remove assistant tool-call placeholder messages (no user-visible content).
  if (role === 'assistant' && hasToolCallData(raw) && !content.trim()) {
    return null;
  }

  const idRaw = raw.id;
  const id =
    typeof idRaw === 'number'
      ? String(idRaw)
      : typeof idRaw === 'string' && idRaw.trim()
        ? idRaw
        : stableMessageFallbackId({
          role: typeof raw.role === 'string' ? raw.role : 'unknown',
          name: typeof raw.name === 'string' ? raw.name : '',
          toolCallId,
          index,
        });

  const metadata = isRecord(raw.metadata) ? raw.metadata : undefined;

  return {
    id,
    role,
    content,
    name,
    tool_call_id: toolCallId || undefined,
    metadata,
  };
};

const normalizeTodoStatus = (value: unknown): TodoItem['status'] => {
  if (value === 'pending' || value === 'in_progress' || value === 'done') return value;
  if (typeof value !== 'string') return 'pending';
  const normalized = value.toLowerCase().replace(/\s+/g, '_').replace(/-+/g, '_');
  if (normalized === 'in_progress') return 'in_progress';
  if (normalized === 'done' || normalized === 'completed' || normalized === 'complete') return 'done';
  return 'pending';
};

const normalizeTodoItem = (raw: unknown): TodoItem | null => {
  if (!isRecord(raw)) return null;
  const idRaw = raw.id ?? raw.todoId ?? raw.title;
  const id =
    typeof idRaw === 'string' || typeof idRaw === 'number' ? String(idRaw) : crypto.randomUUID();
  const titleRaw = raw.title ?? raw.name ?? raw.text ?? id;
  const title = typeof titleRaw === 'string' ? titleRaw : String(titleRaw);
  const status = normalizeTodoStatus(raw.status);
  const metadata = isRecord(raw.metadata) ? raw.metadata : undefined;
  return { id, title, status, metadata };
};

const normalizeTodoItems = (raw: unknown): TodoItem[] => {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw.map(normalizeTodoItem).filter((todo): todo is TodoItem => Boolean(todo));
  }
  if (isRecord(raw) && Array.isArray(raw.todos)) {
    return raw.todos.map(normalizeTodoItem).filter((todo): todo is TodoItem => Boolean(todo));
  }
  return [];
};

const normalizeToolEvidenceCard = (raw: unknown): ToolEvidenceCard | null => {
  if (!isRecord(raw)) return null;
  const idRaw = raw.id;
  const id = typeof idRaw === 'string' || typeof idRaw === 'number' ? String(idRaw) : undefined;
  const type = typeof raw.type === 'string' ? raw.type : undefined;
  const title = typeof raw.title === 'string' ? raw.title : undefined;
  const snippet = typeof raw.snippet === 'string' ? raw.snippet : undefined;
  const url = typeof raw.url === 'string' ? raw.url : undefined;
  const status = typeof raw.status === 'string' ? raw.status : undefined;
  const timestamp = typeof raw.timestamp === 'string' ? raw.timestamp : undefined;
  const metadata = isRecord(raw.metadata) ? raw.metadata : undefined;

  return {
    id,
    type,
    title,
    snippet,
    url,
    fullContent: raw.fullContent,
    status,
    timestamp,
    metadata,
  };
};

const normalizeToolEvidenceCards = (raw: unknown): ToolEvidenceCard[] | undefined => {
  if (!Array.isArray(raw)) return undefined;
  const cards = raw
    .map(normalizeToolEvidenceCard)
    .filter((card): card is ToolEvidenceCard => Boolean(card));
  return cards.length ? cards : undefined;
};

const normalizeToolEvidenceUpdateEvent = (raw: unknown): ToolEvidenceUpdateEvent | null => {
  if (!isRecord(raw)) return null;
  const toolCallIdRaw = raw.toolCallId;
  const toolNameRaw = raw.toolName;
  if (
    (typeof toolCallIdRaw !== 'string' && typeof toolCallIdRaw !== 'number') ||
    typeof toolNameRaw !== 'string'
  ) {
    return null;
  }
  const toolCallId = String(toolCallIdRaw);
  const toolName = toolNameRaw;
  const output = raw.output ?? raw.result ?? raw.data ?? raw.value ?? null;
  const args = typeof raw.args === 'string' || isRecord(raw.args) ? raw.args : undefined;
  const summary = typeof raw.summary === 'string' ? raw.summary : undefined;
  const cards = normalizeToolEvidenceCards(raw.cards);
  const metadata = isRecord(raw.metadata) ? raw.metadata : undefined;

  return {
    toolCallId,
    toolName,
    output,
    result: raw.result,
    data: raw.data,
    value: raw.value,
    args,
    summary,
    cards,
    metadata,
  };
};

const findLastIndex = <T,>(items: readonly T[], predicate: (item: T) => boolean): number => {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (predicate(items[i])) return i;
  }
  return -1;
};

const inferLogAnalysisFromMessages = (messages: Message[]): string | null => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    const formatted = formatLogAnalysisResult(msg.content);
    if (formatted) {
      return formatted;
    }
  }
  return null;
};

const hydrateMessagesForSession = (
  incomingMessages: Message[]
): { sanitizedMessages: Message[]; attachmentsByMessage: Record<string, AttachmentInput[]> } => {
  const attachmentsByMessage: Record<string, AttachmentInput[]> = {};

  const sanitizedMessages = incomingMessages.map((message) => {
    if (!isRecord(message.metadata)) return message;

    if (message.role === 'user') {
      const attachments = extractPersistedAttachments(message.metadata);
      if (attachments.length > 0) {
        attachmentsByMessage[message.id] = attachments;
      }
    }

    const sanitizedMetadata = stripLargeMetadata(message.metadata);
    if (sanitizedMetadata === message.metadata) return message;
    if (!sanitizedMetadata) {
      return { ...message, metadata: undefined };
    }
    return { ...message, metadata: sanitizedMetadata };
  });

  return { sanitizedMessages, attachmentsByMessage };
};

export function AgentProvider({
  children,
  agent,
  sessionId,
}: AgentProviderProps) {
  const [messages, setMessages] = useState<Message[]>(agent.messages || []);
  const messagesRef = useRef<Message[]>(agent.messages || []);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [interrupt, setInterrupt] = useState<InterruptPayload | null>(null);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const [timelineOperations, setTimelineOperations] = useState<TimelineOperation[]>([]);
  const [currentOperationId, setCurrentOperationId] = useState<string | undefined>(undefined);
  const [toolEvidence, setToolEvidence] = useState<Record<string, ToolEvidenceUpdateEvent>>({});
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [thinkingTrace, setThinkingTrace] = useState<TraceStep[]>([]);
  const [activeTraceStepId, setActiveTraceStepId] = useState<string | undefined>(undefined);
  const [isTraceCollapsed, setTraceCollapsed] = useState(true);
  const [resolvedModel, setResolvedModel] = useState<string | undefined>(undefined);
  const [resolvedTaskType, setResolvedTaskType] = useState<string | undefined>(undefined);
  const [messageAttachments, setMessageAttachments] = useState<Record<string, AttachmentInput[]>>({});
  const interruptResolverRef = useRef<((value: string) => void) | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const toolNameByIdRef = useRef<Record<string, string>>({});
  const assistantPersistedRef = useRef(false);
  const lastPersistedAssistantIdBySessionRef = useRef<Record<string, string>>({});
  const lastRunUserMessageIdRef = useRef<string | null>(null);
  const persistedMessageIdRef = useRef<Record<string, string>>({});
  // Track artifacts created during the current run for persistence
  const pendingArtifactsRef = useRef<SerializedArtifact[]>([]);
  const sendMessage = useCallback(async (content: string, attachments?: AttachmentInput[]) => {
    if (!agent || isStreaming) return;

    setIsStreaming(true);
    setError(null);
    // Reset per-run UI state
    setTimelineOperations([]);
    setCurrentOperationId(undefined);
    setToolEvidence({});
    setTodos([]);
    setThinkingTrace([]);
    setActiveTraceStepId(undefined);
    toolNameByIdRef.current = {};
    assistantPersistedRef.current = false;
    lastRunUserMessageIdRef.current = null;
    pendingArtifactsRef.current = [];

    try {
      // Create abort controller for this request
      abortControllerRef.current = new AbortController();
      try {
        const sanitizedMessages = sanitizeMessagesForRun(messagesRef.current);
        agent.messages = sanitizedMessages;
      } catch {
        // ignore
      }

      const trimmedContent = content.trim();
      const persistableAttachments = normalizePersistedAttachments(attachments);
      const hasPersistableAttachments = persistableAttachments.length > 0;

      // Add user message to local state immediately (without metadata to avoid backend validation errors)
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
      };
      lastRunUserMessageIdRef.current = userMessage.id;

      // Store attachments separately by message ID for UI display
      if (attachments && attachments.length > 0) {
        setMessageAttachments((prev) => ({
          ...prev,
          [userMessage.id]: attachments,
        }));
      }

      setMessages((prev) => {
        const next = [...prev, userMessage];
        messagesRef.current = next;
        return next;
      });

      // Add user message to agent's message list
      agent.addMessage(userMessage);

      // Persist user message to backend database (best-effort)
      if (sessionId && (trimmedContent || hasPersistableAttachments)) {
        const metadata: Record<string, unknown> = {};
        if (hasPersistableAttachments) {
          metadata.attachments = persistableAttachments;
        }
        if (!trimmedContent && hasPersistableAttachments) {
          metadata.attachments_only = true;
        }
        const contentToPersist = trimmedContent
          || (hasPersistableAttachments
            ? `Uploaded ${persistableAttachments.length} attachment${persistableAttachments.length === 1 ? '' : 's'}.`
            : content);

        // Fire-and-forget but with error logging - user experience is not blocked
        sessionsAPI.postMessage(sessionId, {
          message_type: 'user',
          content: contentToPersist,
          metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
        }).then((record) => {
          if (record?.id !== undefined && record?.id !== null) {
            persistedMessageIdRef.current[userMessage.id] = String(record.id);
          }
        }).catch((err) => {
          console.error('[Persistence] Failed to persist user message:', err);
        });
      }

      const shouldForceLogAnalysis = hasLogAttachment(attachments);
      if (shouldForceLogAnalysis) {
        agent.setState({
          ...agent.state,
          agent_type: 'log_analysis',
        });
      }

      // Update agent state with attachments if provided
      if (attachments && attachments.length > 0) {
        agent.setState({
          ...agent.state,
          attachments,
        });
      }

        // No need for placeholder - streaming will handle assistant messages

      // Build forwardedProps to influence backend orchestration
      const stateProvider = getStringFromRecord(agent.state, 'provider');
      const stateModel = getStringFromRecord(agent.state, 'model');
      const stateAgentType = getAgentTypeFromState(agent.state);
      const forwardedProps: Record<string, unknown> = {
        // Prefer richer answers by default
        force_websearch: true,
        // Pass through provider/model to avoid backend defaulting to Gemini
        provider: stateProvider || 'google',
        model: stateModel || 'gemini-3-flash-preview',
        agent_type: hasLogAttachment(attachments) ? 'log_analysis' : stateAgentType,
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
      };

      // Run agent with streaming updates
      await agent.runAgent(
        {
          forwardedProps,
        },
        {
            signal: abortControllerRef.current.signal,

            // Handle streaming text content
            onTextMessageContentEvent: ({ event, textMessageBuffer }: { event: unknown; textMessageBuffer?: string }) => {
              const agentType = getAgentTypeFromState(agent.state);
              const delta = isRecord(event) && typeof event.delta === 'string' ? event.delta : '';
              let buffer = typeof textMessageBuffer === 'string' ? textMessageBuffer : delta;
              if (!buffer) {
                return;
              }

            // CRITICAL: Strip markdown images with data URIs - safety filter
            // Pattern: ![alt text](data:image/...)
            // Images are already displayed as artifacts, so this is just garbage in chat.
            const cleaned = stripMarkdownDataUriImages(buffer);
            if (cleaned !== buffer) {
              if (!cleaned) return;
              buffer = cleaned;
            }

              if (agentType === 'log_analysis') {
                const formatted = formatIfStructuredLog(buffer);
                if (formatted) {
                  buffer = formatted;
                } else if (looksLikeJsonPayload(buffer)) {
                  buffer = '';
                }
              }
                setMessages((prev) => {
                  const lastMsg = prev[prev.length - 1];
                  const next: Message[] = (() => {
                    if (lastMsg && lastMsg.role === 'assistant') {
                      return [...prev.slice(0, -1), { ...lastMsg, content: buffer }];
                    }

                    const assistantMessage: Message = {
                      id: crypto.randomUUID(),
                      role: 'assistant',
                      content: buffer,
                    };
                    return [...prev, assistantMessage];
                  })();

                  messagesRef.current = next;
                  return next;
                });
            },

            // Handle complete message updates
            onMessagesChanged: ({ messages: agentMessages }: { messages: unknown[] }) => {
              // Log summary only to avoid RangeError with large content
              console.debug('[AG-UI] onMessagesChanged received:', agentMessages.length, 'messages');

              let messagesWithIds = agentMessages
                .map((msg, idx) => normalizeIncomingMessage(msg, idx))
                .filter((msg): msg is Message => Boolean(msg));

              // CRITICAL: Strip markdown data URIs from all assistant messages.
              messagesWithIds = messagesWithIds.map((msg) => {
                if (msg.role !== 'assistant') return msg;
                const cleaned = stripMarkdownDataUriImages(msg.content);
                if (cleaned === msg.content) return msg;
                return { ...msg, content: cleaned };
              });

              try {
                agent.messages = messagesWithIds;
              } catch {
                // ignore
              }

              // If running log analysis (explicitly or inferred) and the stream ended with a tool result, surface a readable assistant reply.
              const explicitAgentType = getAgentTypeFromState(agent.state);
              const inferredLogAnalysis =
                explicitAgentType === 'log_analysis'
                  ? null
                  : inferLogAnalysisFromMessages(messagesWithIds);
              const isLogAnalysis = explicitAgentType === 'log_analysis' || Boolean(inferredLogAnalysis);

              // If we inferred log analysis while in auto mode, tag the agent state so downstream formatting stays consistent.
              if (!explicitAgentType && inferredLogAnalysis) {
                agent.setState({
                  ...agent.state,
                  agent_type: 'log_analysis',
                });
              }

              if (isLogAnalysis) {
                const lastToolFormatted = (() => {
                  for (let i = messagesWithIds.length - 1; i >= 0; i -= 1) {
                    const msg = messagesWithIds[i];
                    if (msg.role !== 'tool') continue;
                    const formatted =
                      inferredLogAnalysis ||
                      formatLogAnalysisResult(msg.content) ||
                      formatIfStructuredLog(msg.content);
                    if (formatted) return formatted;
                  }
                  return null;
                })();

                if (lastToolFormatted) {
                  const lastAssistantIdx = findLastIndex(messagesWithIds, (m) => m.role === 'assistant');

                  if (lastAssistantIdx >= 0) {
                    const existing = messagesWithIds[lastAssistantIdx];
                    const existingText = existing.content.trim();
                    if (!existingText || looksLikeJsonPayload(existingText)) {
                      const next = [...messagesWithIds];
                      next[lastAssistantIdx] = {
                        ...existing,
                        content: lastToolFormatted,
                        metadata: { ...(existing.metadata ?? {}), structured_log: false },
                      };
                      messagesWithIds = next;
                    }
                  } else {
                    messagesWithIds = [
                      ...messagesWithIds,
                      {
                        id: crypto.randomUUID(),
                        role: 'assistant',
                        content: lastToolFormatted,
                      },
                    ];
                  }
                }
              }

              // Format or hide raw structured-log dumps for log-analysis runs
              if (isLogAnalysis) {
                messagesWithIds = messagesWithIds.map((msg) => {
                  if (msg.role !== 'assistant') return msg;
                  const formatted = formatIfStructuredLog(msg.content);
                  if (!formatted) return msg;
                  return {
                    ...msg,
                    content: formatted,
                    metadata: { ...(msg.metadata ?? {}), structured_log: true },
                  };
                });

                const hasReadableAssistant = messagesWithIds.some(
                  (msg) => msg.role === 'assistant' && msg.metadata?.structured_log !== true,
                );
                if (hasReadableAssistant) {
                  messagesWithIds = messagesWithIds.filter(
                    (msg) => !(msg.role === 'assistant' && msg.metadata?.structured_log === true),
                  );
                }
              }

              if (messagesWithIds.length > 0) {
                const last = messagesWithIds[messagesWithIds.length - 1];
                console.debug('[AG-UI] onMessagesChanged last message:', {
                  role: last.role,
                  preview: last.content.slice(0, 120),
                });
              }

              // Preserve/derive an assistant reply for log analysis when the backend sends only tool/user messages.
              let nextMessages = messagesWithIds;
              if (isLogAnalysis) {
                const hasAssistant = nextMessages.some((m) => m.role === 'assistant');
                if (!hasAssistant) {
                  // Prefer a formatted tool payload from the latest tool message
                  const formattedFromTool = (() => {
                    for (let i = nextMessages.length - 1; i >= 0; i -= 1) {
                      const msg = nextMessages[i];
                      if (msg.role !== 'tool') continue;
                      const formatted =
                        formatLogAnalysisResult(msg.content) ||
                        formatIfStructuredLog(msg.content);
                      if (formatted) return formatted;
                    }
                    return null;
                  })();

                  if (formattedFromTool) {
                    nextMessages = [
                      ...nextMessages,
                      {
                        id: crypto.randomUUID(),
                        role: 'assistant',
                        content: formattedFromTool,
                      },
                    ];
                  } else {
                    // Fall back to the last assistant we already showed (e.g., from streaming buffer)
                    const lastAssistantIdx = findLastIndex(messagesRef.current, (m) => m.role === 'assistant');
                    if (lastAssistantIdx >= 0) {
                      nextMessages = [...nextMessages, messagesRef.current[lastAssistantIdx]];
                    }
                  }
                }
              }

              const uiLastMessage = messagesRef.current[messagesRef.current.length - 1];
              const uiLastAssistant =
                uiLastMessage && uiLastMessage.role === 'assistant' && uiLastMessage.content.trim()
                  ? uiLastMessage
                  : null;

              if (uiLastAssistant) {
                const uiText = uiLastAssistant.content;
                const uiTrimmed = uiText.trim();
                if (uiTrimmed && !looksLikeJsonPayload(uiTrimmed)) {
                  const lastAssistantIdx = findLastIndex(nextMessages, (m) => m.role === 'assistant');

                  if (lastAssistantIdx >= 0) {
                    const snapText = nextMessages[lastAssistantIdx]?.content ?? '';
                    const snapTrimmed = snapText.trim();
                    if (!snapTrimmed || (uiTrimmed.length > snapTrimmed.length && uiTrimmed.startsWith(snapTrimmed))) {
                      const next = [...nextMessages];
                      next[lastAssistantIdx] = {
                        ...next[lastAssistantIdx],
                        content: uiText,
                      };
                      nextMessages = next;
                    }
                  } else {
                    nextMessages = [
                      ...nextMessages,
                      {
                        ...uiLastAssistant,
                        content: uiText,
                      },
                    ];
                  }
                }
              }

              try {
                agent.messages = nextMessages;
              } catch {
                // ignore
              }

              // CRITICAL: Update messagesRef synchronously before setMessages
              // This ensures the finally block sees the latest messages.
              messagesRef.current = nextMessages;

              // Note: Persistence moved to finally block to ensure all artifacts are collected
              // before persisting (custom events like article_artifact arrive after onMessagesChanged)
              setMessages(nextMessages);
            },

            // Handle custom events (interrupts, timeline updates, tool evidence)
            onCustomEvent: ({ event }: { event: unknown }) => {
              if (!isRecord(event) || typeof event.name !== 'string') return undefined;

              const payloadValue =
                'value' in event
                  ? event.value
                  : 'data' in event
                    ? event.data
                    : undefined;

              if (event.name === 'interrupt' || event.name === 'human_input_required') {
                if (isRecord(payloadValue)) {
                  setInterrupt(payloadValue as InterruptPayload);
                }

                // Return a promise that will be resolved by user action
                return new Promise<string>((resolve) => {
                  interruptResolverRef.current = resolve;
                });
              }

              const maybeAgentEvent: unknown = { name: event.name, value: payloadValue };
              if (isAgentCustomEvent(maybeAgentEvent)) {
                if (maybeAgentEvent.name === 'agent_timeline_update') {
                  const operations = Array.isArray(maybeAgentEvent.value.operations)
                    ? maybeAgentEvent.value.operations
                    : [];
                  setTimelineOperations(operations);
                  if (typeof maybeAgentEvent.value.currentOperationId === 'string') {
                    setCurrentOperationId(maybeAgentEvent.value.currentOperationId);
                  }

                  // Fallback: extract todos from timeline operations (type === 'todo')
                  const timelineTodos = operations
                    .filter((op) => op.type === 'todo')
                    .map((op) => (isRecord(op.metadata) ? op.metadata.todo : undefined))
                    .map(normalizeTodoItem)
                    .filter((todo): todo is TodoItem => Boolean(todo));
                  if (timelineTodos.length) {
                    setTodos(timelineTodos);
                  }
                } else if (maybeAgentEvent.name === 'tool_evidence_update') {
                  const normalizedEvidence = normalizeToolEvidenceUpdateEvent(maybeAgentEvent.value);
                  if (!normalizedEvidence) return undefined;

                  setToolEvidence((prev) => ({
                    ...prev,
                    [normalizedEvidence.toolCallId]: normalizedEvidence,
                  }));

                  if (normalizedEvidence.toolName === 'write_todos') {
                    const extracted = extractTodosFromPayload(
                      normalizedEvidence.output ??
                        normalizedEvidence.result ??
                        normalizedEvidence.data ??
                        normalizedEvidence.value,
                    );
                    const nextTodos = normalizeTodoItems(extracted);
                    if (nextTodos.length) {
                      setTodos(nextTodos);
                    }
                  }
                } else if (maybeAgentEvent.name === 'agent_thinking_trace') {
                  const value = maybeAgentEvent.value;
                  console.debug('[AG-UI] Thinking trace update:', value);
                  setThinkingTrace((prev) => {
                    if (Array.isArray(value.thinkingTrace)) {
                      return mapTraceList(value.thinkingTrace);
                    }
                    if (value.latestStep) {
                      const latest = normalizeTraceStep(value.latestStep);
                      const next = [...prev];
                      const idx = next.findIndex((step) => step.id === latest.id);
                      if (idx >= 0) {
                        next[idx] = latest;
                        return next;
                      }
                      next.push(latest);
                      return next;
                    }
                    return prev;
                  });
                  if (typeof value.activeStepId === 'string') {
                    setActiveTraceStepId(value.activeStepId);
                  } else if (value.latestStep?.id) {
                    setActiveTraceStepId(String(value.latestStep.id));
                  }
                } else if (maybeAgentEvent.name === 'agent_todos_update') {
                  const nextTodos = normalizeTodoItems(maybeAgentEvent.value.todos);
                  console.debug('[AG-UI] Todos update:', nextTodos.length, 'items');
                  setTodos(nextTodos);
                } else if (maybeAgentEvent.name === 'image_artifact') {
                  const payload = maybeAgentEvent.value;
                  // Log summary only (avoid logging large base64 imageData)
                  console.debug('[AG-UI] Image artifact event:', payload?.title, 'imageData length:', payload?.imageData?.length);
                  if (payload?.imageData) {
                    const store = getGlobalArtifactStore();
                    if (store) {
                      const state = store.getState();
                      state.addArtifact({
                        id: payload.id,
                        type: 'image',
                        title: payload.title || 'Generated Image',
                        content: payload.content || '',
                        messageId: payload.messageId,
                        imageData: payload.imageData,
                        mimeType: payload.mimeType || 'image/png',
                        altText: payload.altText,
                        aspectRatio: payload.aspectRatio,
                        resolution: payload.resolution,
                      });
                      state.setCurrentArtifact(payload.id);
                      state.setArtifactsVisible(true);
                    }
                    // Track for persistence (exclude messageId - will be set on restore)
                    pendingArtifactsRef.current.push({
                      id: payload.id,
                      type: 'image',
                      title: payload.title || 'Generated Image',
                      content: payload.content || '',
                      imageData: payload.imageData,
                      mimeType: payload.mimeType || 'image/png',
                      altText: payload.altText,
                      aspectRatio: payload.aspectRatio,
                      resolution: payload.resolution,
                    });
                  }
                }
                return undefined;
              }

              // Custom (non-AG-UI) events
              if (event.name === 'article_artifact' && isRecord(payloadValue)) {
                const id = payloadValue.id;
                const content = payloadValue.content;
                if (typeof id === 'string' && typeof content === 'string') {
                  const title = typeof payloadValue.title === 'string' ? payloadValue.title : 'Article';
                  const messageId = typeof payloadValue.messageId === 'string' ? payloadValue.messageId : '';
                  console.debug('[AG-UI] Article artifact event:', title, 'length:', content.length);

                  const store = getGlobalArtifactStore();
                  if (store) {
                    const state = store.getState();
                    state.addArtifact({
                      id,
                      type: 'article',
                      title,
                      content,
                      messageId,
                    });
                    state.setCurrentArtifact(id);
                    state.setArtifactsVisible(true);
                  }

                  // Track for persistence (exclude messageId - will be set on restore)
                  pendingArtifactsRef.current.push({
                    id,
                    type: 'article',
                    title,
                    content,
                  });
                }
              }

              return undefined;
            },

            // Handle state changes (for debugging)
            onStateChanged: ({ state }: { state: unknown }) => {
              // Log summary only to avoid RangeError with large state objects
              const keys = isRecord(state) ? Object.keys(state).join(', ') : '';
              console.debug('[AG-UI] State changed:', keys);
              try {
                const meta = (() => {
                  if (!isRecord(state)) return null;
                  const config = state.config;
                  if (!isRecord(config)) return null;
                  const configurable = config.configurable;
                  if (!isRecord(configurable)) return null;
                  const metadata = configurable.metadata;
                  if (!isRecord(metadata)) return null;
                  return metadata;
                })();
                if (meta && typeof meta.resolved_model === 'string') {
                  setResolvedModel(meta.resolved_model);
                }
                if (meta && typeof meta.resolved_task_type === 'string') {
                  setResolvedTaskType(meta.resolved_task_type);
                }
              } catch (err) {
                console.debug('[AG-UI] meta parse failed:', err);
              }
            },

            // Handle tool calls (for debugging + UI visibility)
            onToolCallStartEvent: ({ event }: { event: unknown }) => {
              const toolCallId =
                isRecord(event) && typeof event.toolCallId === 'string'
                  ? event.toolCallId
                  : isRecord(event) && typeof event.tool_call_id === 'string'
                    ? event.tool_call_id
                    : crypto.randomUUID();
              const toolCallName =
                isRecord(event) && typeof event.toolCallName === 'string'
                  ? event.toolCallName
                  : isRecord(event) && typeof event.tool_call_name === 'string'
                    ? event.tool_call_name
                    : toolCallId;

              console.debug('[AG-UI] Tool call started:', toolCallName, toolCallId);
              toolNameByIdRef.current[toolCallId] = toolCallName;
              setActiveTools((prev) => (prev.includes(toolCallName) ? prev : [...prev, toolCallName]));
            },

            onToolCallResultEvent: ({ event }: { event: unknown }) => {
              const id =
                isRecord(event) && typeof event.toolCallId === 'string'
                  ? event.toolCallId
                  : isRecord(event) && typeof event.tool_call_id === 'string'
                    ? event.tool_call_id
                    : undefined;
              const name =
                (id ? toolNameByIdRef.current[id] : undefined) ||
                (isRecord(event) && typeof event.toolCallName === 'string' ? event.toolCallName : undefined) ||
                (isRecord(event) && typeof event.tool_call_name === 'string' ? event.tool_call_name : undefined);

              console.debug('[AG-UI] Tool call result:', id);

              // Try to extract todos from the result payload even if it arrives as a JSON string
              const output = isRecord(event)
                ? (event.result ?? event.output ?? event.data ?? {})
                : {};
              const extracted = extractTodosFromPayload(output);
              if (name === 'write_todos') {
                const nextTodos = normalizeTodoItems(extracted);
                if (nextTodos.length) setTodos(nextTodos);
              }

                if (name) {
                  if (id) {
                    delete toolNameByIdRef.current[id];
                  }
                  setActiveTools((prev) => prev.filter((n) => n !== name));
                }
              },

            // Handle errors
            onRunFailed: ({ error: runError }: { error: unknown }) => {
              console.error('[AG-UI] Run failed:', runError);
              setError(runError instanceof Error ? runError : new Error('Agent run failed'));
            },
          },
        );

      // Clear attachments after sending
      if (attachments && attachments.length > 0) {
        agent.state = {
          ...agent.state,
          attachments: [],
        };
      }

    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        console.error('[AG-UI] Error sending message:', err);
        setError(err);
      }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
        setActiveTools([]);

        // Persist final assistant message after run completes so all artifacts/custom events are captured.
        if (sessionId && !assistantPersistedRef.current) {
          const sessionKey = String(sessionId);
          const currentMessages = messagesRef.current;

          // Only persist an assistant message if it happened AFTER the user message in this run.
          const runUserMessageId = lastRunUserMessageIdRef.current;
          const runUserIndex = runUserMessageId
            ? findLastIndex(currentMessages, (msg) => msg.id === runUserMessageId)
            : -1;

          const candidateIndex = findLastIndex(
            currentMessages,
            (msg) => msg.role === 'assistant' && msg.content.trim().length > 0,
          );

          // Early exit conditions - use nested if instead of return to avoid masking exceptions
          const shouldPersist = runUserIndex >= 0 && candidateIndex > runUserIndex;

          // Only continue with persistence if conditions are met
          if (shouldPersist && candidateIndex >= 0) {
            const candidate = currentMessages[candidateIndex];

            const lastPersistedId = lastPersistedAssistantIdBySessionRef.current[sessionKey];
            const lastPersistedIndex = lastPersistedId
              ? findLastIndex(currentMessages, (msg) => msg.id === lastPersistedId)
              : -1;

            // Only persist if we've advanced beyond the last successfully persisted assistant message.
            if (candidateIndex > lastPersistedIndex) {
              const artifacts = pendingArtifactsRef.current.length > 0
                ? pendingArtifactsRef.current
                : undefined;
              const mergedMetadata = artifacts
                ? { ...(candidate.metadata ?? {}), artifacts }
                : candidate.metadata;
              const metadataToPersist =
                mergedMetadata && Object.keys(mergedMetadata).length ? mergedMetadata : undefined;

              assistantPersistedRef.current = true;
              const agentType = getPersistedAgentTypeFromState(agent.state);

              console.debug(
                '[Persistence] Persisting assistant message',
                { id: candidate.id, artifacts: artifacts?.length || 0 },
              );

            sessionsAPI.postMessage(sessionId, {
              message_type: 'assistant',
              content: candidate.content,
              agent_type: agentType,
              metadata: metadataToPersist,
            }).then((record) => {
              if (record?.id !== undefined && record?.id !== null) {
                persistedMessageIdRef.current[candidate.id] = String(record.id);
              }
              const latestMessages = messagesRef.current;
              const currentLastId = lastPersistedAssistantIdBySessionRef.current[sessionKey];
              const currentLastIndex = currentLastId
                ? findLastIndex(latestMessages, (msg) => msg.id === currentLastId)
                : -1;
                const candidateIndexNow = findLastIndex(latestMessages, (msg) => msg.id === candidate.id);

                if (candidateIndexNow >= 0 && candidateIndexNow > currentLastIndex) {
                  lastPersistedAssistantIdBySessionRef.current[sessionKey] = candidate.id;
                } else if (candidateIndexNow < 0 && currentLastIndex < 0) {
                  lastPersistedAssistantIdBySessionRef.current[sessionKey] = candidate.id;
                }

                console.debug('[Persistence] Assistant message persisted successfully');
              }).catch((err) => {
                console.error('[Persistence] Failed to persist assistant message:', err);
                assistantPersistedRef.current = false;
              });
            }
          }
        }
      }
    }, [agent, isStreaming, sessionId]);

  const abortRun = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
    if (agent) {
      agent.abortRun();
    }
    setActiveTools([]);
  }, [agent]);

  const registerDocuments = useCallback((documents: DocumentPointer[]) => {
    if (!agent) return;

    // Store documents in agent state for next run
    agent.state = {
      ...agent.state,
      available_documents: documents,
    };

    console.debug('[AG-UI] Registered documents:', documents.length);
  }, [agent]);

  const resolveInterrupt = useCallback((value: string) => {
    if (interruptResolverRef.current) {
      interruptResolverRef.current(value);
      interruptResolverRef.current = null;
      setInterrupt(null);
    }
  }, []);

  const setActiveTraceStep = useCallback((stepId?: string) => {
    setActiveTraceStepId(stepId);
  }, []);

  const setTraceCollapsedState = useCallback((collapsed: boolean) => {
    setTraceCollapsed(collapsed);
  }, []);

  // Update a message's content in local state (for edit persistence)
  const updateMessageContent = useCallback((messageId: string, content: string) => {
    setMessages(prev => prev.map(msg =>
      msg.id === messageId
        ? { ...msg, content }
        : msg
    ));
    // Also update ref to keep in sync
    messagesRef.current = messagesRef.current.map(msg =>
      msg.id === messageId ? { ...msg, content } : msg
    );
  }, []);

  const updateMessageMetadata = useCallback((messageId: string, metadata: Record<string, unknown>) => {
    setMessages(prev => prev.map(msg =>
      msg.id === messageId
        ? { ...msg, metadata: { ...(msg.metadata ?? {}), ...metadata } }
        : msg
    ));
    messagesRef.current = messagesRef.current.map(msg =>
      msg.id === messageId
        ? { ...msg, metadata: { ...(msg.metadata ?? {}), ...metadata } }
        : msg
    );
  }, []);

  const resolvePersistedMessageId = useCallback((messageId: string | number) => {
    if (typeof messageId === 'number' && Number.isFinite(messageId)) {
      return messageId;
    }
    if (typeof messageId !== 'string') return null;
    const trimmed = messageId.trim();
    if (!trimmed) return null;
    if (/^\d+$/.test(trimmed)) return trimmed;
    const mapped = persistedMessageIdRef.current[trimmed];
    return mapped ?? null;
  }, []);

  // Regenerate the last assistant response
  const regenerateLastResponse = useCallback(async () => {
    if (!agent || isStreaming) return;

    // Find the last user message index
    const lastUserMsgIndex = findLastIndex(
      messagesRef.current,
      (msg) => msg.role === 'user'
    );

    if (lastUserMsgIndex === -1) return;

    const lastUserMessage = messagesRef.current[lastUserMsgIndex];
    const userContent = typeof lastUserMessage.content === 'string'
      ? lastUserMessage.content
      : '';

    if (!userContent.trim()) return;

    // Get any attachments for that message
    const attachments = messageAttachments[lastUserMessage.id] || [];

    // Truncate messages to only include messages up to (and including) the user message
    const truncatedMessages = messagesRef.current.slice(0, lastUserMsgIndex + 1);
    setMessages(truncatedMessages);
    messagesRef.current = truncatedMessages;

    // Re-send the user message
    await sendMessage(userContent, attachments);
  }, [agent, isStreaming, messageAttachments, sendMessage]);

  // Initialize with agent's existing messages on mount or session switch
  useEffect(() => {
    if (!agent || !agent.messages) return;
    const { sanitizedMessages, attachmentsByMessage } = hydrateMessagesForSession(agent.messages);
    try {
      agent.messages = sanitizedMessages;
    } catch {
      // ignore
    }
    setMessages(sanitizedMessages);
    messagesRef.current = sanitizedMessages;
    setMessageAttachments(attachmentsByMessage);
  }, [agent]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  return (
    <AgentContext.Provider
      value={{
        agent,
        sessionId,
        messages,
        isStreaming,
        error,
        sendMessage,
        abortRun,
        registerDocuments,
        interrupt,
        resolveInterrupt,
        activeTools,
        timelineOperations,
        currentOperationId,
        toolEvidence,
        todos,
        thinkingTrace,
        activeTraceStepId,
        setActiveTraceStep,
        isTraceCollapsed,
        setTraceCollapsed: setTraceCollapsedState,
        resolvedModel,
        resolvedTaskType,
        messageAttachments,
        updateMessageContent,
        updateMessageMetadata,
        resolvePersistedMessageId,
        regenerateLastResponse,
      }}
    >
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgent must be used within AgentProvider');
  }
  return context;
}
