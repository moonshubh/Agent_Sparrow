"use client";

import type { ToolEvidenceCard, TodoItem } from "@/services/ag-ui/event-types";
import type {
  PanelObjectiveKind,
  PanelObjectivePhase,
  PanelObjectiveStatus,
  PanelState,
} from "./panel-event-adapter";
import { PANEL_PRIMARY_LANE_ID } from "./panel-event-adapter";

export const PANEL_SNAPSHOT_MAX_BYTES = 20 * 1024;
export const PANEL_VERSION_HISTORY_LIMIT = 4;
const PANEL_SNAPSHOT_SCHEMA = "panel_snapshot_v1";
const PANEL_SNAPSHOT_VERSION = 1;

type SnapshotBudget = {
  maxObjectives: number;
  summaryChars: number;
  detailChars: number;
  maxEvidencePerObjective: number;
  evidenceSnippetChars: number;
  maxTodos: number;
};

const SNAPSHOT_BUDGETS: readonly SnapshotBudget[] = [
  {
    maxObjectives: 64,
    summaryChars: 240,
    detailChars: 420,
    maxEvidencePerObjective: 3,
    evidenceSnippetChars: 140,
    maxTodos: 30,
  },
  {
    maxObjectives: 48,
    summaryChars: 220,
    detailChars: 300,
    maxEvidencePerObjective: 2,
    evidenceSnippetChars: 120,
    maxTodos: 20,
  },
  {
    maxObjectives: 36,
    summaryChars: 180,
    detailChars: 220,
    maxEvidencePerObjective: 1,
    evidenceSnippetChars: 90,
    maxTodos: 12,
  },
  {
    maxObjectives: 24,
    summaryChars: 140,
    detailChars: 0,
    maxEvidencePerObjective: 0,
    evidenceSnippetChars: 0,
    maxTodos: 8,
  },
  {
    maxObjectives: 14,
    summaryChars: 110,
    detailChars: 0,
    maxEvidencePerObjective: 0,
    evidenceSnippetChars: 0,
    maxTodos: 4,
  },
];

const OBJECTIVE_PHASES: readonly PanelObjectivePhase[] = [
  "plan",
  "gather",
  "execute",
  "synthesize",
];
const OBJECTIVE_STATUSES: readonly PanelObjectiveStatus[] = [
  "pending",
  "running",
  "done",
  "error",
  "unknown",
];
const OBJECTIVE_KINDS: readonly PanelObjectiveKind[] = [
  "thought",
  "tool",
  "todo",
  "error",
];

export interface PanelSnapshotObjectiveV1 {
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

export interface PanelSnapshotLaneV1 {
  id: string;
  type: "primary" | "subagent";
  title: string;
  toolCallId?: string;
  subagentType?: string;
  objectiveIds: string[];
  status: PanelObjectiveStatus;
  updatedAt: string;
}

export interface PanelSnapshotTodoV1 {
  id: string;
  title: string;
  status: TodoItem["status"];
}

export interface PanelSnapshotV1 {
  schema: "panel_snapshot_v1";
  version: 1;
  captured_at: string;
  runId: string;
  lanes: Record<string, PanelSnapshotLaneV1>;
  laneOrder: string[];
  objectives: Record<string, PanelSnapshotObjectiveV1>;
  todos: PanelSnapshotTodoV1[];
  activeLaneId: string;
  activeObjectiveId?: string;
  runStatus: PanelObjectiveStatus;
  updatedAt: string;
}

export interface PanelSnapshotVersionV1 {
  id: string;
  label: string;
  created_at: string;
  snapshot: PanelSnapshotV1;
}

export interface PanelProvenanceV1 {
  source: "assistant_run";
  generated_at: string;
  edited: boolean;
  edited_at?: string;
  edit_count: number;
  regenerated_from_message_id?: string;
  latest_version_id?: string;
  version_count: number;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const clampText = (value: unknown, max: number): string | undefined => {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (max <= 0) return undefined;
  return trimmed.length > max ? `${trimmed.slice(0, max).trimEnd()}...` : trimmed;
};

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

const jsonByteLength = (value: unknown): number => {
  const json = JSON.stringify(value);
  if (typeof TextEncoder === "undefined") {
    return json.length;
  }
  return new TextEncoder().encode(json).length;
};

const stableHash = (value: string): string => {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash.toString(16);
};

const normalizeEvidenceCards = (
  cards: unknown,
  budget: SnapshotBudget,
): ToolEvidenceCard[] => {
  if (!Array.isArray(cards) || budget.maxEvidencePerObjective <= 0) return [];
  return cards.slice(0, budget.maxEvidencePerObjective).map((raw, idx) => {
    if (!isRecord(raw)) {
      return {
        id: `evidence-${idx + 1}`,
        title: `Evidence ${idx + 1}`,
      };
    }
    return {
      id:
        typeof raw.id === "string"
          ? raw.id
          : `evidence-${idx + 1}-${stableHash(JSON.stringify(raw))}`,
      type: typeof raw.type === "string" ? raw.type : undefined,
      title: typeof raw.title === "string" ? raw.title : `Evidence ${idx + 1}`,
      snippet: clampText(raw.snippet, budget.evidenceSnippetChars),
      url: typeof raw.url === "string" ? raw.url : undefined,
      status: typeof raw.status === "string" ? raw.status : undefined,
      timestamp: typeof raw.timestamp === "string" ? raw.timestamp : undefined,
      metadata: isRecord(raw.metadata) ? raw.metadata : undefined,
    };
  });
};

const normalizeRunStatus = (value: unknown): PanelObjectiveStatus => {
  if (typeof value === "string" && OBJECTIVE_STATUSES.includes(value as PanelObjectiveStatus)) {
    return value as PanelObjectiveStatus;
  }
  return "unknown";
};

const normalizeObjectivePhase = (value: unknown): PanelObjectivePhase => {
  if (typeof value === "string" && OBJECTIVE_PHASES.includes(value as PanelObjectivePhase)) {
    return value as PanelObjectivePhase;
  }
  return "execute";
};

const normalizeObjectiveKind = (value: unknown): PanelObjectiveKind => {
  if (typeof value === "string" && OBJECTIVE_KINDS.includes(value as PanelObjectiveKind)) {
    return value as PanelObjectiveKind;
  }
  return "thought";
};

const normalizeLaneType = (value: unknown): "primary" | "subagent" => {
  return value === "subagent" ? "subagent" : "primary";
};

const normalizeTodoStatus = (value: unknown): TodoItem["status"] => {
  if (value === "pending" || value === "in_progress" || value === "done") return value;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (normalized === "complete" || normalized === "completed") return "done";
  }
  return "pending";
};

const sortObjectives = (panelState: PanelState): string[] => {
  return Object.values(panelState.objectives)
    .sort(
      (left, right) =>
        toTimestampMs(left.updatedAt || left.startedAt) -
        toTimestampMs(right.updatedAt || right.startedAt),
    )
    .map((objective) => objective.id);
};

const buildSnapshotWithBudget = (
  panelState: PanelState,
  budget: SnapshotBudget,
): PanelSnapshotV1 => {
  const capturedAt = new Date().toISOString();
  const sortedObjectiveIds = sortObjectives(panelState);
  const selectedObjectiveIds = new Set(
    sortedObjectiveIds.slice(-budget.maxObjectives),
  );
  const objectives: Record<string, PanelSnapshotObjectiveV1> = {};

  Object.entries(panelState.objectives).forEach(([objectiveId, objective]) => {
    if (!selectedObjectiveIds.has(objectiveId)) return;
    const summarySource =
      objective.summary ?? objective.detail ?? objective.title ?? "Objective";
    const summary = clampText(summarySource, budget.summaryChars);
    objectives[objectiveId] = {
      id: objective.id,
      runId: objective.runId,
      laneId: objective.laneId,
      phase: normalizeObjectivePhase(objective.phase),
      kind: normalizeObjectiveKind(objective.kind),
      title: clampText(objective.title, 120) || "Objective",
      status: normalizeRunStatus(objective.status),
      summary,
      detail:
        budget.detailChars > 0
          ? clampText(objective.detail ?? objective.summary, budget.detailChars)
          : undefined,
      toolCallId: objective.toolCallId,
      subagentType: objective.subagentType,
      startedAt: toIsoTimestamp(objective.startedAt),
      updatedAt: toIsoTimestamp(objective.updatedAt),
      endedAt: objective.endedAt ? toIsoTimestamp(objective.endedAt) : undefined,
      evidenceCards: normalizeEvidenceCards(objective.evidenceCards, budget),
      sourceEvent:
        typeof objective.sourceEvent === "string"
          ? objective.sourceEvent
          : "snapshot_v1",
    };
  });

  const lanes: Record<string, PanelSnapshotLaneV1> = {};
  const laneOrder: string[] = [];
  const selectedIds = new Set(Object.keys(objectives));
  const sourceLaneOrder = panelState.laneOrder.length
    ? panelState.laneOrder
    : [PANEL_PRIMARY_LANE_ID];

  sourceLaneOrder.forEach((laneId) => {
    const lane = panelState.lanes[laneId];
    if (!lane) return;
    const objectiveIds = lane.objectiveIds.filter((objectiveId) =>
      selectedIds.has(objectiveId),
    );
    if (!objectiveIds.length && laneId !== PANEL_PRIMARY_LANE_ID) return;
    lanes[laneId] = {
      id: lane.id,
      type: normalizeLaneType(lane.type),
      title: clampText(lane.title, 100) || "Lane",
      toolCallId: lane.toolCallId,
      subagentType: lane.subagentType,
      objectiveIds,
      status: normalizeRunStatus(lane.status),
      updatedAt: toIsoTimestamp(lane.updatedAt),
    };
    laneOrder.push(laneId);
  });

  if (!lanes[PANEL_PRIMARY_LANE_ID]) {
    lanes[PANEL_PRIMARY_LANE_ID] = {
      id: PANEL_PRIMARY_LANE_ID,
      type: "primary",
      title: "Primary",
      objectiveIds: [],
      status: normalizeRunStatus(panelState.runStatus),
      updatedAt: toIsoTimestamp(panelState.updatedAt),
    };
    laneOrder.unshift(PANEL_PRIMARY_LANE_ID);
  }

  Object.values(objectives).forEach((objective) => {
    if (lanes[objective.laneId]) return;
    lanes[objective.laneId] = {
      id: objective.laneId,
      type: objective.laneId === PANEL_PRIMARY_LANE_ID ? "primary" : "subagent",
      title: objective.subagentType || "Subagent",
      objectiveIds: [objective.id],
      status: normalizeRunStatus(objective.status),
      updatedAt: objective.updatedAt,
      toolCallId: objective.toolCallId,
      subagentType: objective.subagentType,
    };
    laneOrder.push(objective.laneId);
  });

  const todos = (panelState.todos ?? []).slice(0, budget.maxTodos).map((todo) => ({
    id: String(todo.id),
    title: clampText(todo.title, 140) || "Todo",
    status: normalizeTodoStatus(todo.status),
  }));

  const fallbackObjectiveId =
    sortedObjectiveIds
      .slice()
      .reverse()
      .find((objectiveId) => selectedIds.has(objectiveId)) || undefined;
  const activeObjectiveId =
    panelState.activeObjectiveId && selectedIds.has(panelState.activeObjectiveId)
      ? panelState.activeObjectiveId
      : fallbackObjectiveId;
  const activeLaneId =
    panelState.activeLaneId && lanes[panelState.activeLaneId]
      ? panelState.activeLaneId
      : laneOrder[0] || PANEL_PRIMARY_LANE_ID;

  return {
    schema: PANEL_SNAPSHOT_SCHEMA,
    version: PANEL_SNAPSHOT_VERSION,
    captured_at: capturedAt,
    runId: panelState.runId,
    lanes,
    laneOrder,
    objectives,
    todos,
    activeLaneId,
    activeObjectiveId,
    runStatus: normalizeRunStatus(panelState.runStatus),
    updatedAt: toIsoTimestamp(panelState.updatedAt),
  };
};

const buildMinimalSnapshot = (panelState: PanelState): PanelSnapshotV1 => {
  const minimal = buildSnapshotWithBudget(panelState, {
    maxObjectives: 8,
    summaryChars: 96,
    detailChars: 0,
    maxEvidencePerObjective: 0,
    evidenceSnippetChars: 0,
    maxTodos: 3,
  });
  return minimal;
};

export const buildPanelSnapshotV1 = (panelState: PanelState): PanelSnapshotV1 => {
  for (const budget of SNAPSHOT_BUDGETS) {
    const snapshot = buildSnapshotWithBudget(panelState, budget);
    if (jsonByteLength(snapshot) <= PANEL_SNAPSHOT_MAX_BYTES) {
      return snapshot;
    }
  }
  return buildMinimalSnapshot(panelState);
};

const normalizeSnapshotLane = (
  laneId: string,
  raw: unknown,
): PanelSnapshotLaneV1 | null => {
  if (!isRecord(raw)) return null;
  const objectiveIds = Array.isArray(raw.objectiveIds)
    ? raw.objectiveIds
        .map((value) => (typeof value === "string" ? value : String(value)))
        .filter(Boolean)
    : [];
  return {
    id: typeof raw.id === "string" && raw.id ? raw.id : laneId,
    type: normalizeLaneType(raw.type),
    title: clampText(raw.title, 100) || "Lane",
    toolCallId: typeof raw.toolCallId === "string" ? raw.toolCallId : undefined,
    subagentType:
      typeof raw.subagentType === "string" ? raw.subagentType : undefined,
    objectiveIds,
    status: normalizeRunStatus(raw.status),
    updatedAt: toIsoTimestamp(raw.updatedAt),
  };
};

const normalizeSnapshotObjective = (
  objectiveId: string,
  raw: unknown,
): PanelSnapshotObjectiveV1 | null => {
  if (!isRecord(raw)) return null;
  const evidenceCards: ToolEvidenceCard[] = Array.isArray(raw.evidenceCards)
    ? raw.evidenceCards.reduce<ToolEvidenceCard[]>((acc, card) => {
        if (!isRecord(card)) return acc;
        acc.push({
          id: typeof card.id === "string" ? card.id : undefined,
          type: typeof card.type === "string" ? card.type : undefined,
          title: typeof card.title === "string" ? card.title : "Evidence",
          snippet: typeof card.snippet === "string" ? card.snippet : undefined,
          url: typeof card.url === "string" ? card.url : undefined,
          status: typeof card.status === "string" ? card.status : undefined,
          timestamp:
            typeof card.timestamp === "string" ? card.timestamp : undefined,
          metadata: isRecord(card.metadata) ? card.metadata : undefined,
        });
        return acc;
      }, [])
    : [];
  return {
    id: typeof raw.id === "string" && raw.id ? raw.id : objectiveId,
    runId: typeof raw.runId === "string" && raw.runId ? raw.runId : "run",
    laneId:
      typeof raw.laneId === "string" && raw.laneId
        ? raw.laneId
        : PANEL_PRIMARY_LANE_ID,
    phase: normalizeObjectivePhase(raw.phase),
    kind: normalizeObjectiveKind(raw.kind),
    title: clampText(raw.title, 120) || "Objective",
    status: normalizeRunStatus(raw.status),
    summary: clampText(raw.summary, 320),
    detail: clampText(raw.detail, 520),
    toolCallId: typeof raw.toolCallId === "string" ? raw.toolCallId : undefined,
    subagentType:
      typeof raw.subagentType === "string" ? raw.subagentType : undefined,
    startedAt: toIsoTimestamp(raw.startedAt),
    updatedAt: toIsoTimestamp(raw.updatedAt),
    endedAt: raw.endedAt ? toIsoTimestamp(raw.endedAt) : undefined,
    evidenceCards,
    sourceEvent:
      typeof raw.sourceEvent === "string" ? raw.sourceEvent : "snapshot_v1",
  };
};

export const coercePanelSnapshotV1 = (raw: unknown): PanelSnapshotV1 | null => {
  if (!isRecord(raw)) return null;
  if (raw.schema !== PANEL_SNAPSHOT_SCHEMA) return null;
  if (raw.version !== PANEL_SNAPSHOT_VERSION) return null;
  if (typeof raw.runId !== "string" || !raw.runId.trim()) return null;

  const rawLanes = isRecord(raw.lanes) ? raw.lanes : {};
  const lanes: Record<string, PanelSnapshotLaneV1> = {};
  Object.entries(rawLanes).forEach(([laneId, laneValue]) => {
    const normalized = normalizeSnapshotLane(laneId, laneValue);
    if (normalized) lanes[laneId] = normalized;
  });

  const rawObjectives = isRecord(raw.objectives) ? raw.objectives : {};
  const objectives: Record<string, PanelSnapshotObjectiveV1> = {};
  Object.entries(rawObjectives).forEach(([objectiveId, objectiveValue]) => {
    const normalized = normalizeSnapshotObjective(objectiveId, objectiveValue);
    if (normalized) objectives[objectiveId] = normalized;
  });

  const laneOrder = Array.isArray(raw.laneOrder)
    ? raw.laneOrder
        .map((laneId) => (typeof laneId === "string" ? laneId : String(laneId)))
        .filter((laneId) => laneId && Boolean(lanes[laneId]))
    : [];
  if (!laneOrder.includes(PANEL_PRIMARY_LANE_ID) && lanes[PANEL_PRIMARY_LANE_ID]) {
    laneOrder.unshift(PANEL_PRIMARY_LANE_ID);
  }

  const todos = Array.isArray(raw.todos)
    ? raw.todos
        .map((todo) =>
          isRecord(todo)
            ? {
                id:
                  typeof todo.id === "string" || typeof todo.id === "number"
                    ? String(todo.id)
                    : "",
                title: clampText(todo.title, 140) || "Todo",
                status: normalizeTodoStatus(todo.status),
              }
            : null,
        )
        .filter((todo): todo is PanelSnapshotTodoV1 => Boolean(todo && todo.id))
    : [];

  const activeLaneId =
    typeof raw.activeLaneId === "string" && lanes[raw.activeLaneId]
      ? raw.activeLaneId
      : laneOrder[0] || PANEL_PRIMARY_LANE_ID;
  const activeObjectiveId =
    typeof raw.activeObjectiveId === "string" && objectives[raw.activeObjectiveId]
      ? raw.activeObjectiveId
      : undefined;

  return {
    schema: PANEL_SNAPSHOT_SCHEMA,
    version: PANEL_SNAPSHOT_VERSION,
    captured_at: toIsoTimestamp(raw.captured_at),
    runId: raw.runId,
    lanes:
      Object.keys(lanes).length > 0
        ? lanes
        : {
            [PANEL_PRIMARY_LANE_ID]: {
              id: PANEL_PRIMARY_LANE_ID,
              type: "primary",
              title: "Primary",
              objectiveIds: [],
              status: normalizeRunStatus(raw.runStatus),
              updatedAt: toIsoTimestamp(raw.updatedAt),
            },
          },
    laneOrder:
      laneOrder.length > 0
        ? laneOrder
        : [PANEL_PRIMARY_LANE_ID],
    objectives,
    todos,
    activeLaneId,
    activeObjectiveId,
    runStatus: normalizeRunStatus(raw.runStatus),
    updatedAt: toIsoTimestamp(raw.updatedAt),
  };
};

export const panelSnapshotToPanelState = (
  snapshot: PanelSnapshotV1,
): PanelState => {
  return {
    runId: snapshot.runId,
    lanes: snapshot.lanes,
    laneOrder: snapshot.laneOrder,
    objectives: snapshot.objectives,
    todos: snapshot.todos.map((todo) => ({
      id: todo.id,
      title: todo.title,
      status: todo.status,
    })),
    activeLaneId: snapshot.activeLaneId,
    activeObjectiveId: snapshot.activeObjectiveId,
    runStatus: snapshot.runStatus,
    updatedAt: snapshot.updatedAt,
  };
};

const snapshotVersionId = (
  snapshot: PanelSnapshotV1,
  createdAt: string,
): string => {
  return `panel-v1-${stableHash(
    `${snapshot.runId}:${snapshot.updatedAt}:${createdAt}:${Object.keys(snapshot.objectives).join(",")}`,
  )}`;
};

const normalizePanelVersion = (
  raw: unknown,
  fallbackIndex: number,
): PanelSnapshotVersionV1 | null => {
  if (!isRecord(raw)) return null;
  const snapshot = coercePanelSnapshotV1(raw.snapshot);
  if (!snapshot) return null;
  const createdAt = toIsoTimestamp(raw.created_at);
  const id =
    typeof raw.id === "string" && raw.id.trim()
      ? raw.id.trim()
      : snapshotVersionId(snapshot, createdAt);
  return {
    id,
    label:
      typeof raw.label === "string" && raw.label.trim()
        ? raw.label.trim()
        : `Version ${fallbackIndex + 1}`,
    created_at: createdAt,
    snapshot,
  };
};

const dedupeVersions = (
  versions: PanelSnapshotVersionV1[],
): PanelSnapshotVersionV1[] => {
  const seen = new Set<string>();
  const deduped: PanelSnapshotVersionV1[] = [];
  versions.forEach((version) => {
    if (seen.has(version.id)) return;
    seen.add(version.id);
    deduped.push(version);
  });
  return deduped;
};

export const coercePanelVersionsV1 = (
  raw: unknown,
): PanelSnapshotVersionV1[] => {
  if (!Array.isArray(raw)) return [];
  return dedupeVersions(
    raw
      .map((value, index) => normalizePanelVersion(value, index))
      .filter((value): value is PanelSnapshotVersionV1 => Boolean(value)),
  );
};

export const buildPanelVersionHistory = (params: {
  inherited: PanelSnapshotVersionV1[];
  currentSnapshot: PanelSnapshotV1;
  createdAt: string;
}): PanelSnapshotVersionV1[] => {
  const inherited = dedupeVersions(params.inherited);
  const currentVersion: PanelSnapshotVersionV1 = {
    id: snapshotVersionId(params.currentSnapshot, params.createdAt),
    label: `Version ${inherited.length + 1}`,
    created_at: params.createdAt,
    snapshot: params.currentSnapshot,
  };

  const combined = [...inherited, currentVersion]
    .sort(
      (left, right) =>
        toTimestampMs(left.created_at) - toTimestampMs(right.created_at),
    )
    .slice(-PANEL_VERSION_HISTORY_LIMIT)
    .map((version, index) => ({
      ...version,
      label: `Version ${index + 1}`,
    }));

  return combined;
};

export const seedPanelVersionsFromMetadata = (
  metadata?: Record<string, unknown>,
): PanelSnapshotVersionV1[] => {
  if (!metadata) return [];
  const versions = coercePanelVersionsV1(metadata.panel_versions_v1);
  const snapshot = coercePanelSnapshotV1(metadata.panel_snapshot_v1);
  if (!snapshot) return versions;

  const hasSnapshotAlready = versions.some(
    (version) => version.snapshot.runId === snapshot.runId && version.snapshot.updatedAt === snapshot.updatedAt,
  );
  if (hasSnapshotAlready) return versions;

  const createdAt = toIsoTimestamp(snapshot.captured_at || snapshot.updatedAt);
  return dedupeVersions([
    ...versions,
    {
      id: snapshotVersionId(snapshot, createdAt),
      label: `Version ${versions.length + 1}`,
      created_at: createdAt,
      snapshot,
    },
  ]);
};

export const coercePanelProvenanceV1 = (
  raw: unknown,
): PanelProvenanceV1 | null => {
  if (!isRecord(raw)) return null;
  if (raw.source !== "assistant_run") return null;
  return {
    source: "assistant_run",
    generated_at: toIsoTimestamp(raw.generated_at),
    edited: Boolean(raw.edited),
    edited_at:
      typeof raw.edited_at === "string" ? toIsoTimestamp(raw.edited_at) : undefined,
    edit_count:
      typeof raw.edit_count === "number" && Number.isFinite(raw.edit_count)
        ? Math.max(0, Math.floor(raw.edit_count))
        : 0,
    regenerated_from_message_id:
      typeof raw.regenerated_from_message_id === "string"
        ? raw.regenerated_from_message_id
        : undefined,
    latest_version_id:
      typeof raw.latest_version_id === "string" ? raw.latest_version_id : undefined,
    version_count:
      typeof raw.version_count === "number" && Number.isFinite(raw.version_count)
        ? Math.max(0, Math.floor(raw.version_count))
        : 0,
  };
};

export const buildGeneratedProvenance = (params: {
  generatedAt: string;
  versions: PanelSnapshotVersionV1[];
  regeneratedFromMessageId?: string;
}): PanelProvenanceV1 => ({
  source: "assistant_run",
  generated_at: toIsoTimestamp(params.generatedAt),
  edited: false,
  edit_count: 0,
  regenerated_from_message_id: params.regeneratedFromMessageId,
  latest_version_id: params.versions[params.versions.length - 1]?.id,
  version_count: params.versions.length,
});

export const buildEditedProvenance = (params: {
  existing?: Record<string, unknown>;
  editedAt: string;
}): PanelProvenanceV1 => {
  const existing = coercePanelProvenanceV1(params.existing);
  return {
    source: "assistant_run",
    generated_at: existing?.generated_at ?? toIsoTimestamp(params.editedAt),
    edited: true,
    edited_at: toIsoTimestamp(params.editedAt),
    edit_count: (existing?.edit_count ?? 0) + 1,
    regenerated_from_message_id: existing?.regenerated_from_message_id,
    latest_version_id: existing?.latest_version_id,
    version_count: existing?.version_count ?? 0,
  };
};
