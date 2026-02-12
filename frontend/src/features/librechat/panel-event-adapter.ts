"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentCustomEvent,
  ObjectiveHintUpdateEvent,
  TodoItem,
  ToolEvidenceCard,
  TraceStep,
  TimelineOperation,
  ToolEvidenceUpdateEvent,
} from "@/services/ag-ui/event-types";

export const PANEL_PRIMARY_LANE_ID = "primary";
export const PANEL_PRIMARY_PHASE_ORDER = [
  "plan",
  "gather",
  "execute",
  "synthesize",
] as const;

export type PanelObjectivePhase = (typeof PANEL_PRIMARY_PHASE_ORDER)[number];
export type PanelObjectiveStatus =
  | "pending"
  | "running"
  | "done"
  | "error"
  | "unknown";
export type PanelObjectiveKind = "thought" | "tool" | "todo" | "error";
export type PanelLaneType = "primary" | "subagent";

export interface PanelObjective {
  id: string;
  runId: string;
  laneId: string;
  phase: PanelObjectivePhase;
  kind: PanelObjectiveKind;
  title: string;
  status: PanelObjectiveStatus;
  summary?: string;
  detail?: string;
  toolCallId?: string;
  subagentType?: string;
  startedAt: string;
  updatedAt: string;
  endedAt?: string;
  evidenceCards: ToolEvidenceCard[];
  sourceEvent: string;
}

export interface PanelLane {
  id: string;
  type: PanelLaneType;
  title: string;
  toolCallId?: string;
  subagentType?: string;
  objectiveIds: string[];
  status: PanelObjectiveStatus;
  updatedAt: string;
}

export interface PanelState {
  runId: string;
  lanes: Record<string, PanelLane>;
  laneOrder: string[];
  objectives: Record<string, PanelObjective>;
  todos: TodoItem[];
  activeLaneId: string;
  activeObjectiveId?: string;
  runStatus: PanelObjectiveStatus;
  updatedAt: string;
}

type ToolCallStartEvent = {
  name: "tool_call_start";
  value: {
    toolCallId: string;
    toolName: string;
    timestamp?: string;
    args?: unknown;
  };
};

type ToolCallResultEvent = {
  name: "tool_call_result";
  value: {
    toolCallId?: string;
    toolName?: string;
    timestamp?: string;
    result?: unknown;
    status?: "done" | "error";
  };
};

type TodosSnapshotEvent = {
  name: "todos_snapshot";
  value: {
    todos: TodoItem[];
  };
};

export type PanelAdapterEvent =
  | AgentCustomEvent
  | ToolCallStartEvent
  | ToolCallResultEvent
  | TodosSnapshotEvent;

const TERMINAL_STATUSES: ReadonlySet<PanelObjectiveStatus> = new Set([
  "done",
  "error",
  "unknown",
]);
const MAX_EVENT_KEYS = 1200;
const MAX_OBJECTIVE_SUMMARY = 900;
const MAX_OBJECTIVE_DETAIL = 1800;
const DEFAULT_BATCH_MS = 200;

const toIsoTimestamp = (value: unknown): string => {
  if (typeof value !== "string" && typeof value !== "number") {
    return new Date().toISOString();
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? new Date().toISOString()
    : parsed.toISOString();
};

const toTimestampMs = (value?: string): number => {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const clampText = (value: unknown, max: number): string | undefined => {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.length > max ? `${trimmed.slice(0, max).trimEnd()}...` : trimmed;
};

const humanize = (value: string): string =>
  value
    .replace(/^subagent:/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const normalizePhase = (value: unknown): PanelObjectivePhase => {
  if (typeof value !== "string") return "execute";
  const normalized = value.trim().toLowerCase();
  if (
    normalized === "plan" ||
    normalized === "gather" ||
    normalized === "execute" ||
    normalized === "synthesize"
  ) {
    return normalized;
  }
  return "execute";
};

const normalizeStatus = (value: unknown): PanelObjectiveStatus => {
  if (
    value === "pending" ||
    value === "running" ||
    value === "done" ||
    value === "error" ||
    value === "unknown"
  ) {
    return value;
  }
  if (value === "success" || value === "completed" || value === "complete") {
    return "done";
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (normalized === "in_progress") return "running";
    if (normalized === "failed" || normalized === "fail") return "error";
  }
  return "pending";
};

const statusWeight = (status: PanelObjectiveStatus): number => {
  switch (status) {
    case "pending":
      return 1;
    case "running":
      return 2;
    case "unknown":
      return 3;
    case "done":
      return 4;
    case "error":
      return 5;
    default:
      return 0;
  }
};

const isTerminalStatus = (status: PanelObjectiveStatus): boolean =>
  TERMINAL_STATUSES.has(status);

const inferThoughtPhase = (
  step: TraceStep,
  kind: PanelObjectiveKind,
): PanelObjectivePhase => {
  const metadata =
    step.metadata && typeof step.metadata === "object" ? step.metadata : {};
  if (typeof (metadata as Record<string, unknown>).phase === "string") {
    return normalizePhase((metadata as Record<string, unknown>).phase);
  }

  const sample = step.content.toLowerCase();
  if (/plan|strategy|outline|todo/.test(sample)) return "plan";
  if (/gather|research|collect|retrieve|search|inspect/.test(sample)) {
    return "gather";
  }
  if (/synthesize|final|answer|conclusion|summary/.test(sample)) {
    return "synthesize";
  }
  if (kind === "thought") return "gather";
  return "execute";
};

const inferThoughtKind = (step: TraceStep): PanelObjectiveKind => {
  if (step.status === "error") return "error";
  if (step.type === "tool" || step.type === "action") return "tool";
  return "thought";
};

const inferThoughtStatus = (step: TraceStep): PanelObjectiveStatus => {
  if (step.status === "error") return "error";
  if (step.type === "result") return "done";
  return "running";
};

const normalizeLaneId = (laneId?: string, toolCallId?: string): string => {
  if (laneId && laneId.trim()) {
    const trimmed = laneId.trim();
    if (trimmed === PANEL_PRIMARY_LANE_ID) return PANEL_PRIMARY_LANE_ID;
    if (trimmed.startsWith("subagent:")) return trimmed;
    return `subagent:${trimmed}`;
  }
  if (toolCallId && toolCallId.trim()) {
    return `subagent:${toolCallId.trim()}`;
  }
  return PANEL_PRIMARY_LANE_ID;
};

const stableHash = (value: string): string => {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash.toString(16);
};

const hashUnknownForKey = (value: unknown): string => {
  try {
    return stableHash(JSON.stringify(value ?? null));
  } catch {
    return stableHash(String(value));
  }
};

const buildTraceStepKey = (step: TraceStep): string =>
  [
    step.id,
    step.timestamp,
    step.type,
    step.status ?? "",
    step.toolName ?? "",
    stableHash(step.content ?? ""),
    hashUnknownForKey(step.metadata ?? null),
  ].join(":");

const buildTodosKey = (todos: TodoItem[]): string => {
  const signature = todos
    .map((todo) => {
      const title = typeof todo.title === "string" ? todo.title.trim() : "";
      return `${todo.id}:${todo.status}:${stableHash(title)}:${hashUnknownForKey(todo.metadata ?? null)}`;
    })
    .join("|");
  return `${todos.length}:${stableHash(signature)}`;
};

const summarizeUnknown = (value: unknown): string => {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value
      .slice(0, 3)
      .map((item) => summarizeUnknown(item))
      .join(", ");
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const summaryCandidate =
      record.summary ??
      record.message ??
      record.error ??
      record.detail ??
      record.content ??
      record.output;
    if (summaryCandidate !== undefined) {
      return summarizeUnknown(summaryCandidate);
    }
    try {
      return JSON.stringify(record);
    } catch {
      return "[object]";
    }
  }
  return "";
};

const createPrimaryLane = (nowIso: string): PanelLane => ({
  id: PANEL_PRIMARY_LANE_ID,
  type: "primary",
  title: "Primary",
  objectiveIds: [],
  status: "pending",
  updatedAt: nowIso,
});

export const createInitialPanelState = (runId?: string): PanelState => {
  const nowIso = new Date().toISOString();
  return {
    runId: runId ?? `run-${Date.now()}`,
    lanes: {
      [PANEL_PRIMARY_LANE_ID]: createPrimaryLane(nowIso),
    },
    laneOrder: [PANEL_PRIMARY_LANE_ID],
    objectives: {},
    todos: [],
    activeLaneId: PANEL_PRIMARY_LANE_ID,
    activeObjectiveId: undefined,
    runStatus: "pending",
    updatedAt: nowIso,
  };
};

const ensureLane = (
  state: PanelState,
  laneId: string,
  options: {
    subagentType?: string;
    toolCallId?: string;
    timestamp?: string;
  },
): PanelState => {
  if (state.lanes[laneId]) return state;
  const nowIso = options.timestamp ?? new Date().toISOString();
  const title =
    laneId === PANEL_PRIMARY_LANE_ID
      ? "Primary"
      : options.subagentType
        ? humanize(options.subagentType)
        : humanize(laneId);
  const nextLane: PanelLane = {
    id: laneId,
    type: laneId === PANEL_PRIMARY_LANE_ID ? "primary" : "subagent",
    title: title || "Subagent",
    toolCallId: options.toolCallId,
    subagentType: options.subagentType,
    objectiveIds: [],
    status: "pending",
    updatedAt: nowIso,
  };
  return {
    ...state,
    lanes: {
      ...state.lanes,
      [laneId]: nextLane,
    },
    laneOrder: state.laneOrder.includes(laneId)
      ? state.laneOrder
      : [...state.laneOrder, laneId],
  };
};

const computeLaneStatus = (
  lane: PanelLane,
  objectives: Record<string, PanelObjective>,
): PanelObjectiveStatus => {
  if (!lane.objectiveIds.length) return "pending";
  const laneObjectives = lane.objectiveIds
    .map((id) => objectives[id])
    .filter((objective): objective is PanelObjective => Boolean(objective));
  if (!laneObjectives.length) return "pending";
  if (laneObjectives.some((objective) => objective.status === "error")) {
    return "error";
  }
  if (laneObjectives.some((objective) => objective.status === "running")) {
    return "running";
  }
  if (laneObjectives.some((objective) => objective.status === "pending")) {
    return "pending";
  }
  if (laneObjectives.some((objective) => objective.status === "unknown")) {
    return "unknown";
  }
  return "done";
};

const computeRunStatus = (lanes: Record<string, PanelLane>): PanelObjectiveStatus => {
  const laneStatuses = Object.values(lanes).map((lane) => lane.status);
  if (!laneStatuses.length) return "pending";
  if (laneStatuses.some((status) => status === "error")) return "error";
  if (laneStatuses.some((status) => status === "running")) return "running";
  if (laneStatuses.some((status) => status === "pending")) return "pending";
  if (laneStatuses.some((status) => status === "unknown")) return "unknown";
  return "done";
};

const recomputeStatuses = (
  state: PanelState,
  touchedLaneIds: string[],
): PanelState => {
  if (!touchedLaneIds.length) return state;
  const nextLanes = { ...state.lanes };
  const touched = new Set(touchedLaneIds);
  for (const laneId of touched) {
    const lane = nextLanes[laneId];
    if (!lane) continue;
    nextLanes[laneId] = {
      ...lane,
      status: computeLaneStatus(lane, state.objectives),
      updatedAt: state.updatedAt,
    };
  }
  return {
    ...state,
    lanes: nextLanes,
    runStatus: computeRunStatus(nextLanes),
  };
};

type ObjectivePatch = {
  id: string;
  runId: string;
  laneId: string;
  phase: PanelObjectivePhase;
  kind: PanelObjectiveKind;
  title: string;
  status: PanelObjectiveStatus;
  summary?: string;
  detail?: string;
  toolCallId?: string;
  subagentType?: string;
  startedAt?: string;
  updatedAt?: string;
  endedAt?: string;
  evidenceCards?: ToolEvidenceCard[];
  sourceEvent: string;
};

const shouldReplaceObjective = (
  existing: PanelObjective,
  incoming: PanelObjective,
): boolean => {
  const existingTerminal = isTerminalStatus(existing.status);
  const incomingTerminal = isTerminalStatus(incoming.status);
  if (existingTerminal && !incomingTerminal) {
    return false;
  }
  if (!existingTerminal && incomingTerminal) {
    return true;
  }

  const existingTs = toTimestampMs(existing.updatedAt);
  const incomingTs = toTimestampMs(incoming.updatedAt);
  if (incomingTs > existingTs) return true;
  if (incomingTs < existingTs) return false;

  return statusWeight(incoming.status) >= statusWeight(existing.status);
};

const upsertObjective = (state: PanelState, patch: ObjectivePatch): PanelState => {
  const nowIso = patch.updatedAt ?? new Date().toISOString();
  const laneId = normalizeLaneId(patch.laneId, patch.toolCallId);
  const stateWithLane = ensureLane(state, laneId, {
    subagentType: patch.subagentType,
    toolCallId: patch.toolCallId,
    timestamp: nowIso,
  });
  const existing = stateWithLane.objectives[patch.id];
  const nextObjective: PanelObjective = {
    id: patch.id,
    runId: patch.runId,
    laneId,
    phase: patch.phase,
    kind: patch.kind,
    title: patch.title || existing?.title || "Untitled objective",
    status: patch.status,
    summary: patch.summary,
    detail: patch.detail,
    toolCallId: patch.toolCallId ?? existing?.toolCallId,
    subagentType: patch.subagentType ?? existing?.subagentType,
    startedAt: patch.startedAt ?? existing?.startedAt ?? nowIso,
    updatedAt: nowIso,
    endedAt: patch.endedAt ?? existing?.endedAt,
    evidenceCards: patch.evidenceCards ?? existing?.evidenceCards ?? [],
    sourceEvent: patch.sourceEvent,
  };

  if (existing && !shouldReplaceObjective(existing, nextObjective)) {
    return stateWithLane;
  }

  const mergedObjective = existing
    ? {
        ...existing,
        ...nextObjective,
        summary: nextObjective.summary ?? existing.summary,
        detail: nextObjective.detail ?? existing.detail,
        evidenceCards:
          nextObjective.evidenceCards.length > 0
            ? nextObjective.evidenceCards
            : existing.evidenceCards,
      }
    : nextObjective;

  const prevLane = stateWithLane.lanes[laneId];
  const laneObjectiveIds = prevLane.objectiveIds.includes(patch.id)
    ? prevLane.objectiveIds
    : [...prevLane.objectiveIds, patch.id];

  const objectives = {
    ...stateWithLane.objectives,
    [patch.id]: mergedObjective,
  };

  let activeLaneId = stateWithLane.activeLaneId;
  let activeObjectiveId = stateWithLane.activeObjectiveId;
  if (mergedObjective.status === "running") {
    activeLaneId = laneId;
    activeObjectiveId = mergedObjective.id;
  }

  if (
    activeObjectiveId === mergedObjective.id &&
    isTerminalStatus(mergedObjective.status)
  ) {
    const fallbackObjective = laneObjectiveIds
      .map((objectiveId) => objectives[objectiveId])
      .find((objective) => objective?.status === "running");
    if (fallbackObjective) {
      activeObjectiveId = fallbackObjective.id;
      activeLaneId = fallbackObjective.laneId;
    } else {
      activeObjectiveId = undefined;
    }
  }

  const next: PanelState = {
    ...stateWithLane,
    objectives,
    lanes: {
      ...stateWithLane.lanes,
      [laneId]: {
        ...prevLane,
        objectiveIds: laneObjectiveIds,
        updatedAt: nowIso,
      },
    },
    activeLaneId,
    activeObjectiveId,
    updatedAt: nowIso,
  };

  return recomputeStatuses(next, [laneId]);
};

const buildTodoProgressSummary = (todos: TodoItem[]): string => {
  if (!todos.length) return "No todos";
  const done = todos.filter((todo) => todo.status === "done").length;
  return `${done}/${todos.length} completed`;
};

const findObjectiveByToolCall = (
  objectives: Record<string, PanelObjective>,
  toolCallId: string,
): PanelObjective | undefined => {
  const values = Object.values(objectives);
  return values.find((objective) => objective.toolCallId === toolCallId);
};

const mapTimelineOperation = (
  state: PanelState,
  operation: TimelineOperation,
): ObjectivePatch => {
  const metadata =
    operation.metadata && typeof operation.metadata === "object"
      ? operation.metadata
      : {};
  const metadataRecord = metadata as Record<string, unknown>;
  const toolCallId =
    typeof metadataRecord.toolCallId === "string"
      ? metadataRecord.toolCallId
      : undefined;
  const laneId = normalizeLaneId(
    typeof metadataRecord.laneId === "string" ? metadataRecord.laneId : undefined,
    toolCallId,
  );

  const phase: PanelObjectivePhase =
    operation.type === "todo"
      ? "plan"
      : operation.type === "thought"
        ? "gather"
        : operation.type === "tool"
          ? "execute"
          : "synthesize";
  const status: PanelObjectiveStatus =
    operation.status === "error"
      ? "error"
      : operation.status === "success"
        ? "done"
        : operation.status === "running"
          ? "running"
          : "pending";
  const kind: PanelObjectiveKind =
    status === "error"
      ? "error"
      : operation.type === "todo"
        ? "todo"
        : operation.type === "tool"
          ? "tool"
          : "thought";

  return {
    id: `timeline:${operation.id}`,
    runId: state.runId,
    laneId,
    phase,
    kind,
    title: operation.name || `Operation ${operation.id}`,
    status,
    summary: clampText(metadataRecord.summary, MAX_OBJECTIVE_SUMMARY),
    detail: clampText(metadataRecord.detail, MAX_OBJECTIVE_DETAIL),
    toolCallId,
    startedAt: operation.startTime ? toIsoTimestamp(operation.startTime) : undefined,
    updatedAt: operation.endTime
      ? toIsoTimestamp(operation.endTime)
      : operation.startTime
        ? toIsoTimestamp(operation.startTime)
        : undefined,
    endedAt: operation.endTime ? toIsoTimestamp(operation.endTime) : undefined,
    sourceEvent: "agent_timeline_update",
  };
};

const applyObjectiveHint = (
  state: PanelState,
  payload: ObjectiveHintUpdateEvent,
): PanelState => {
  const laneId = normalizeLaneId(payload.laneId, payload.toolCallId);
  const updatedAt = toIsoTimestamp(
    payload.endedAt ?? payload.startedAt ?? Date.now(),
  );
  const objectiveId = payload.objectiveId?.trim()
    ? payload.objectiveId.trim()
    : `hint:${payload.phase}:${stableHash(`${payload.title}:${laneId}:${updatedAt}`)}`;
  const kind: PanelObjectiveKind =
    payload.status === "error"
      ? "error"
      : payload.toolCallId
        ? "tool"
        : payload.phase === "plan"
          ? "todo"
          : "thought";
  return upsertObjective(state, {
    id: objectiveId,
    runId: payload.runId || state.runId,
    laneId,
    phase: normalizePhase(payload.phase),
    kind,
    title: payload.title || "Objective",
    status: normalizeStatus(payload.status),
    summary: clampText(payload.summary, MAX_OBJECTIVE_SUMMARY),
    toolCallId: payload.toolCallId,
    subagentType: payload.subagentType,
    startedAt: payload.startedAt ? toIsoTimestamp(payload.startedAt) : updatedAt,
    updatedAt,
    endedAt: payload.endedAt ? toIsoTimestamp(payload.endedAt) : undefined,
    sourceEvent: "objective_hint_update",
  });
};

const applyTraceStep = (state: PanelState, step: TraceStep): PanelState => {
  const kind = inferThoughtKind(step);
  const metadata =
    step.metadata && typeof step.metadata === "object" ? step.metadata : {};
  const metadataRecord = metadata as Record<string, unknown>;
  const toolCallId =
    typeof metadataRecord.toolCallId === "string"
      ? metadataRecord.toolCallId
      : typeof metadataRecord.tool_call_id === "string"
        ? metadataRecord.tool_call_id
        : undefined;
  const laneId = normalizeLaneId(
    typeof metadataRecord.laneId === "string" ? metadataRecord.laneId : undefined,
    toolCallId,
  );
  const objectiveId = `trace:${step.id}`;
  const title =
    kind === "tool"
      ? typeof step.toolName === "string" && step.toolName.trim()
        ? humanize(step.toolName)
        : "Tool call"
      : kind === "error"
        ? "Error surfaced"
        : "Thought";
  const status = inferThoughtStatus(step);
  const summary = clampText(step.content, MAX_OBJECTIVE_SUMMARY);

  return upsertObjective(state, {
    id: objectiveId,
    runId: state.runId,
    laneId,
    phase: inferThoughtPhase(step, kind),
    kind,
    title,
    status,
    summary,
    detail: clampText(step.content, MAX_OBJECTIVE_DETAIL),
    toolCallId,
    startedAt: toIsoTimestamp(step.timestamp),
    updatedAt: toIsoTimestamp(step.timestamp),
    endedAt: status === "done" || status === "error" ? toIsoTimestamp(step.timestamp) : undefined,
    sourceEvent: "agent_thinking_trace",
  });
};

const applyToolEvidence = (
  state: PanelState,
  payload: ToolEvidenceUpdateEvent,
): PanelState => {
  const existing = findObjectiveByToolCall(state.objectives, payload.toolCallId);
  const laneId = existing?.laneId ?? normalizeLaneId(undefined, payload.toolCallId);
  const status: PanelObjectiveStatus = (() => {
    if (payload.metadata?.status === "error") return "error";
    const summarySource = summarizeUnknown(payload.output ?? payload.result);
    if (/error|failed/i.test(summarySource)) return "error";
    return "done";
  })();
  const summary =
    clampText(payload.summary, MAX_OBJECTIVE_SUMMARY) ||
    clampText(summarizeUnknown(payload.output ?? payload.result), MAX_OBJECTIVE_SUMMARY);
  const nowIso = new Date().toISOString();

  return upsertObjective(state, {
    id: existing?.id ?? `tool:${payload.toolCallId}`,
    runId: state.runId,
    laneId,
    phase: "execute",
    kind: status === "error" ? "error" : "tool",
    title: humanize(payload.toolName) || "Tool",
    status,
    summary,
    detail: clampText(summarizeUnknown(payload.output ?? payload.result), MAX_OBJECTIVE_DETAIL),
    toolCallId: payload.toolCallId,
    startedAt: existing?.startedAt ?? nowIso,
    updatedAt: nowIso,
    endedAt: status === "done" || status === "error" ? nowIso : undefined,
    evidenceCards: Array.isArray(payload.cards) ? payload.cards.slice(0, 8) : undefined,
    sourceEvent: "tool_evidence_update",
  });
};

const applySubagentSpawn = (
  state: PanelState,
  payload: { toolCallId: string; subagentType: string; task: string; timestamp: string },
): PanelState => {
  const laneId = normalizeLaneId(`subagent:${payload.toolCallId}`, payload.toolCallId);
  return upsertObjective(state, {
    id: `subagent:${payload.toolCallId}:task`,
    runId: state.runId,
    laneId,
    phase: "execute",
    kind: "tool",
    title: payload.task?.trim() ? payload.task.trim() : "Subagent task",
    status: "running",
    summary: clampText(payload.task, MAX_OBJECTIVE_SUMMARY),
    subagentType: payload.subagentType,
    toolCallId: payload.toolCallId,
    startedAt: toIsoTimestamp(payload.timestamp),
    updatedAt: toIsoTimestamp(payload.timestamp),
    sourceEvent: "subagent_spawn",
  });
};

const applySubagentEnd = (
  state: PanelState,
  payload: {
    toolCallId: string;
    subagentType: string;
    status: "success" | "error";
    excerpt?: string;
    timestamp: string;
  },
): PanelState => {
  const laneId = normalizeLaneId(`subagent:${payload.toolCallId}`, payload.toolCallId);
  const summary = payload.excerpt
    ? clampText(payload.excerpt, MAX_OBJECTIVE_SUMMARY)
    : payload.status === "error"
      ? "Subagent failed"
      : "Subagent completed";
  const nowIso = toIsoTimestamp(payload.timestamp);
  return upsertObjective(state, {
    id: `subagent:${payload.toolCallId}:task`,
    runId: state.runId,
    laneId,
    phase: "execute",
    kind: payload.status === "error" ? "error" : "tool",
    title: "Subagent task",
    status: payload.status === "error" ? "error" : "done",
    summary,
    subagentType: payload.subagentType,
    toolCallId: payload.toolCallId,
    updatedAt: nowIso,
    endedAt: nowIso,
    sourceEvent: "subagent_end",
  });
};

const applySubagentDelta = (
  state: PanelState,
  payload: { toolCallId: string; subagentType?: string; delta: string; timestamp: string },
): PanelState => {
  const laneId = normalizeLaneId(`subagent:${payload.toolCallId}`, payload.toolCallId);
  const objectiveId = `subagent:${payload.toolCallId}:task`;
  const existing = state.objectives[objectiveId];
  const combined = `${existing?.detail ?? ""}${payload.delta ?? ""}`.trim();
  const detail = clampText(combined, MAX_OBJECTIVE_DETAIL);
  const summary = clampText(detail, MAX_OBJECTIVE_SUMMARY);
  return upsertObjective(state, {
    id: objectiveId,
    runId: state.runId,
    laneId,
    phase: "execute",
    kind: "tool",
    title: existing?.title ?? "Subagent task",
    status: "running",
    summary,
    detail,
    subagentType: payload.subagentType ?? existing?.subagentType,
    toolCallId: payload.toolCallId,
    startedAt: existing?.startedAt ?? toIsoTimestamp(payload.timestamp),
    updatedAt: toIsoTimestamp(payload.timestamp),
    sourceEvent: "subagent_thinking_delta",
  });
};

const applyTodos = (state: PanelState, todos: TodoItem[]): PanelState => {
  const normalizedTodos = Array.isArray(todos) ? todos : [];
  const summary = buildTodoProgressSummary(normalizedTodos);
  const status: PanelObjectiveStatus = (() => {
    if (!normalizedTodos.length) return "pending";
    const done = normalizedTodos.every((todo) => todo.status === "done");
    return done ? "done" : "running";
  })();

  const nowIso = new Date().toISOString();
  const next = upsertObjective(state, {
    id: "todo:progress",
    runId: state.runId,
    laneId: PANEL_PRIMARY_LANE_ID,
    phase: "plan",
    kind: "todo",
    title: "Todo progress",
    status,
    summary,
    detail: normalizedTodos
      .map((todo, index) => `${index + 1}. ${todo.title} (${todo.status})`)
      .join("\n"),
    updatedAt: nowIso,
    endedAt: status === "done" ? nowIso : undefined,
    sourceEvent: "agent_todos_update",
  });
  return {
    ...next,
    todos: normalizedTodos,
  };
};

export const reducePanelEvent = (
  state: PanelState,
  event: PanelAdapterEvent,
): PanelState => {
  switch (event.name) {
    case "objective_hint_update":
      return applyObjectiveHint(state, event.value);
    case "agent_thinking_trace": {
      const trace = event.value.thinkingTrace ?? [];
      if (trace.length > 0) {
        return trace.reduce((next, step) => applyTraceStep(next, step), state);
      }
      if (event.value.latestStep) {
        return applyTraceStep(state, event.value.latestStep);
      }
      return state;
    }
    case "tool_evidence_update":
      return applyToolEvidence(state, event.value);
    case "agent_todos_update":
      return applyTodos(state, event.value.todos ?? []);
    case "agent_timeline_update": {
      if (!Array.isArray(event.value.operations)) return state;
      return event.value.operations.reduce((next, operation) => {
        const patch = mapTimelineOperation(next, operation);
        return upsertObjective(next, patch);
      }, state);
    }
    case "subagent_spawn":
      return applySubagentSpawn(state, {
        toolCallId: event.value.toolCallId,
        subagentType: event.value.subagentType || "subagent",
        task: event.value.task || "",
        timestamp: event.value.timestamp,
      });
    case "subagent_end":
      return applySubagentEnd(state, {
        toolCallId: event.value.toolCallId,
        subagentType: event.value.subagentType || "subagent",
        status: event.value.status,
        excerpt: event.value.excerpt,
        timestamp: event.value.timestamp,
      });
    case "subagent_thinking_delta":
      return applySubagentDelta(state, {
        toolCallId: event.value.toolCallId,
        subagentType: event.value.subagentType,
        delta: event.value.delta,
        timestamp: event.value.timestamp,
      });
    case "tool_call_start": {
      const nowIso = toIsoTimestamp(event.value.timestamp ?? Date.now());
      return upsertObjective(state, {
        id: `tool:${event.value.toolCallId}`,
        runId: state.runId,
        laneId: PANEL_PRIMARY_LANE_ID,
        phase: "execute",
        kind: "tool",
        title: humanize(event.value.toolName) || "Tool",
        status: "running",
        summary: clampText(summarizeUnknown(event.value.args), MAX_OBJECTIVE_SUMMARY),
        detail: clampText(summarizeUnknown(event.value.args), MAX_OBJECTIVE_DETAIL),
        toolCallId: event.value.toolCallId,
        startedAt: nowIso,
        updatedAt: nowIso,
        sourceEvent: "tool_call_start",
      });
    }
    case "tool_call_result": {
      const targetObjective = event.value.toolCallId
        ? findObjectiveByToolCall(state.objectives, event.value.toolCallId)
        : undefined;
      const objectiveId =
        targetObjective?.id ??
        (event.value.toolCallId ? `tool:${event.value.toolCallId}` : undefined);
      if (!objectiveId) return state;
      const nowIso = toIsoTimestamp(event.value.timestamp ?? Date.now());
      const status = normalizeStatus(event.value.status ?? "done");
      const detail = clampText(
        summarizeUnknown(event.value.result),
        MAX_OBJECTIVE_DETAIL,
      );
      return upsertObjective(state, {
        id: objectiveId,
        runId: state.runId,
        laneId: targetObjective?.laneId ?? PANEL_PRIMARY_LANE_ID,
        phase: targetObjective?.phase ?? "execute",
        kind: status === "error" ? "error" : targetObjective?.kind ?? "tool",
        title:
          targetObjective?.title ??
          (event.value.toolName ? humanize(event.value.toolName) : "Tool"),
        status,
        summary: clampText(detail, MAX_OBJECTIVE_SUMMARY),
        detail,
        toolCallId: event.value.toolCallId ?? targetObjective?.toolCallId,
        updatedAt: nowIso,
        endedAt: nowIso,
        sourceEvent: "tool_call_result",
      });
    }
    case "todos_snapshot":
      return applyTodos(state, event.value.todos);
    default:
      return state;
  }
};

const buildEventKey = (event: PanelAdapterEvent): string => {
  switch (event.name) {
    case "objective_hint_update":
      return `objective_hint_update:${event.value.runId}:${event.value.laneId}:${event.value.objectiveId}:${event.value.status}:${event.value.startedAt ?? ""}:${event.value.endedAt ?? ""}`;
    case "agent_thinking_trace": {
      const latest = event.value.latestStep;
      if (latest) {
        return `agent_thinking_trace:${event.value.totalSteps}:${event.value.activeStepId ?? ""}:${buildTraceStepKey(
          latest,
        )}`;
      }
      if (Array.isArray(event.value.thinkingTrace) && event.value.thinkingTrace.length) {
        const tailSignature = event.value.thinkingTrace
          .slice(-3)
          .map((step) => buildTraceStepKey(step))
          .join("|");
        return `agent_thinking_trace:${event.value.totalSteps}:${event.value.activeStepId ?? ""}:${event.value.thinkingTrace.length}:${stableHash(
          tailSignature,
        )}`;
      }
      return `agent_thinking_trace:${event.value.totalSteps}:${event.value.activeStepId ?? ""}`;
    }
    case "tool_evidence_update":
      return `tool_evidence_update:${event.value.toolCallId}:${event.value.summary ?? ""}:${event.value.cards?.length ?? 0}`;
    case "agent_todos_update":
      return `agent_todos_update:${buildTodosKey(event.value.todos)}`;
    case "agent_timeline_update":
      return `agent_timeline_update:${event.value.operations
        .map((operation) => `${operation.id}:${operation.status}`)
        .join("|")}:${event.value.currentOperationId ?? ""}`;
    case "subagent_spawn":
      return `subagent_spawn:${event.value.toolCallId}:${event.value.timestamp}`;
    case "subagent_end":
      return `subagent_end:${event.value.toolCallId}:${event.value.status}:${event.value.timestamp}`;
    case "subagent_thinking_delta":
      return `subagent_thinking_delta:${event.value.toolCallId}:${event.value.timestamp}:${stableHash(
        event.value.delta,
      )}`;
    case "tool_call_start":
      return `tool_call_start:${event.value.toolCallId}:${event.value.toolName}:${event.value.timestamp ?? ""}`;
    case "tool_call_result":
      return `tool_call_result:${event.value.toolCallId ?? ""}:${event.value.timestamp ?? ""}:${event.value.status ?? ""}`;
    case "todos_snapshot":
      return `todos_snapshot:${buildTodosKey(event.value.todos)}`;
    default:
      return `${event.name}:${stableHash(JSON.stringify(event.value ?? ""))}`;
  }
};

const isThoughtCadenceEvent = (eventName: PanelAdapterEvent["name"]): boolean =>
  eventName === "agent_thinking_trace" || eventName === "subagent_thinking_delta";

interface UsePanelEventAdapterOptions {
  batchMs?: number;
}

export interface UsePanelEventAdapterResult {
  panelState: PanelState;
  resetPanelState: (runId?: string) => void;
  applyCustomEvent: (event: AgentCustomEvent) => void;
  applyToolCallStart: (params: {
    toolCallId: string;
    toolName: string;
    timestamp?: string;
    args?: unknown;
  }) => void;
  applyToolCallResult: (params: {
    toolCallId?: string;
    toolName?: string;
    timestamp?: string;
    result?: unknown;
    status?: "done" | "error";
  }) => void;
  syncTodosSnapshot: (todos: TodoItem[]) => void;
}

export function usePanelEventAdapter(
  options?: UsePanelEventAdapterOptions,
): UsePanelEventAdapterResult {
  const batchMs = options?.batchMs ?? DEFAULT_BATCH_MS;
  const [panelState, setPanelState] = useState<PanelState>(() =>
    createInitialPanelState(),
  );

  const queuedThoughtEventsRef = useRef<PanelAdapterEvent[]>([]);
  const flushTimerRef = useRef<number | null>(null);
  const seenKeysRef = useRef<Set<string>>(new Set());
  const seenKeyOrderRef = useRef<string[]>([]);

  const rememberEventKey = useCallback((key: string): boolean => {
    if (seenKeysRef.current.has(key)) {
      return false;
    }
    seenKeysRef.current.add(key);
    seenKeyOrderRef.current.push(key);
    if (seenKeyOrderRef.current.length > MAX_EVENT_KEYS) {
      const toDrop = seenKeyOrderRef.current.shift();
      if (toDrop) {
        seenKeysRef.current.delete(toDrop);
      }
    }
    return true;
  }, []);

  const flushThoughtEvents = useCallback(() => {
    if (flushTimerRef.current !== null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    if (!queuedThoughtEventsRef.current.length) return;
    const queued = queuedThoughtEventsRef.current;
    queuedThoughtEventsRef.current = [];
    setPanelState((prev) => queued.reduce((next, event) => reducePanelEvent(next, event), prev));
  }, []);

  const dispatchEvent = useCallback(
    (event: PanelAdapterEvent) => {
      const key = buildEventKey(event);
      if (!rememberEventKey(key)) return;
      if (isThoughtCadenceEvent(event.name)) {
        queuedThoughtEventsRef.current.push(event);
        if (flushTimerRef.current === null) {
          flushTimerRef.current = window.setTimeout(() => {
            flushThoughtEvents();
          }, batchMs);
        }
        return;
      }
      setPanelState((prev) => reducePanelEvent(prev, event));
    },
    [batchMs, flushThoughtEvents, rememberEventKey],
  );

  const resetPanelState = useCallback(
    (runId?: string) => {
      if (flushTimerRef.current !== null) {
        window.clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      queuedThoughtEventsRef.current = [];
      seenKeysRef.current.clear();
      seenKeyOrderRef.current = [];
      setPanelState(createInitialPanelState(runId));
    },
    [],
  );

  useEffect(() => {
    return () => {
      if (flushTimerRef.current !== null) {
        window.clearTimeout(flushTimerRef.current);
      }
    };
  }, []);

  const applyCustomEvent = useCallback(
    (event: AgentCustomEvent) => {
      dispatchEvent(event);
    },
    [dispatchEvent],
  );

  const applyToolCallStart = useCallback(
    (params: {
      toolCallId: string;
      toolName: string;
      timestamp?: string;
      args?: unknown;
    }) => {
      dispatchEvent({
        name: "tool_call_start",
        value: {
          toolCallId: params.toolCallId,
          toolName: params.toolName,
          timestamp: params.timestamp,
          args: params.args,
        },
      });
    },
    [dispatchEvent],
  );

  const applyToolCallResult = useCallback(
    (params: {
      toolCallId?: string;
      toolName?: string;
      timestamp?: string;
      result?: unknown;
      status?: "done" | "error";
    }) => {
      dispatchEvent({
        name: "tool_call_result",
        value: {
          toolCallId: params.toolCallId,
          toolName: params.toolName,
          timestamp: params.timestamp,
          result: params.result,
          status: params.status,
        },
      });
    },
    [dispatchEvent],
  );

  const syncTodosSnapshot = useCallback(
    (todos: TodoItem[]) => {
      dispatchEvent({ name: "todos_snapshot", value: { todos } });
    },
    [dispatchEvent],
  );

  return {
    panelState,
    resetPanelState,
    applyCustomEvent,
    applyToolCallStart,
    applyToolCallResult,
    syncTodosSnapshot,
  };
}
