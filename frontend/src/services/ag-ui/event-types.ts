/**
 * AG-UI Event Types
 *
 * TypeScript types mirroring backend event_types.py exactly.
 * These types define the contract for custom events emitted by Agent Sparrow.
 */

// -----------------------------------------------------------------------------
// Thinking Trace Types
// -----------------------------------------------------------------------------

export type TraceStepType = "thought" | "action" | "result" | "tool";

/**
 * A single step in the agent's thinking trace.
 * Emitted via `agent_thinking_trace` custom events.
 */
export interface TraceStep {
  /** Unique identifier for this step */
  id: string;
  /** ISO timestamp of when this step occurred */
  timestamp: string;
  /** Type of step */
  type: TraceStepType;
  /** Human-readable content describing this step */
  content: string;
  /** Additional metadata (tool info, model info, etc.) */
  metadata: Record<string, unknown>;
  /** Optional tool name if type is tool/action */
  toolName?: string;
  /** Optional duration in seconds */
  duration?: number;
  /** Optional status of the step */
  status?: "success" | "error";
}

/**
 * Event payload for `agent_thinking_trace` custom events.
 */
export interface AgentThinkingTraceEvent {
  /** Total number of steps in the trace so far */
  totalSteps: number;
  /** Full trace if syncing all steps (usually on first event) */
  thinkingTrace?: TraceStep[];
  /** Latest step if incremental update */
  latestStep?: TraceStep;
  /** ID of the currently active step */
  activeStepId?: string;
}

// -----------------------------------------------------------------------------
// Timeline Operation Types
// -----------------------------------------------------------------------------

export type TimelineOperationType = "agent" | "tool" | "thought" | "todo";
export type TimelineOperationStatus =
  | "pending"
  | "running"
  | "success"
  | "error";

/**
 * A single operation in the agent timeline.
 * Represents agent runs, tool calls, thinking, and todo items.
 */
export interface TimelineOperation {
  /** Unique identifier for this operation */
  id: string;
  /** Type of operation */
  type: TimelineOperationType;
  /** Human-readable name */
  name: string;
  /** Current status */
  status: TimelineOperationStatus;
  /** Parent operation ID (for nesting) */
  parent?: string;
  /** Child operation IDs */
  children: string[];
  /** ISO timestamp when operation started */
  startTime?: string;
  /** ISO timestamp when operation ended */
  endTime?: string;
  /** Duration in milliseconds */
  duration?: number;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Event payload for `agent_timeline_update` custom events.
 */
export interface AgentTimelineUpdateEvent {
  /** All operations in the timeline */
  operations: TimelineOperation[];
  /** ID of the currently active operation */
  currentOperationId?: string;
}

// -----------------------------------------------------------------------------
// Tool Evidence Types
// -----------------------------------------------------------------------------

export interface ToolEvidenceCard {
  id?: string;
  type?: string;
  title?: string;
  snippet?: string;
  url?: string;
  fullContent?: unknown;
  status?: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Event payload for `tool_evidence_update` custom events.
 * Provides detailed tool output for display in the reasoning panel.
 */
export interface ToolEvidenceUpdateEvent {
  /** Tool call identifier (matches tool_calls in AIMessage) */
  toolCallId: string;
  /** Name of the tool */
  toolName: string;
  /** Raw output from the tool */
  output: unknown;
  /** Alternative field names for output (backend compatibility) */
  result?: unknown;
  data?: unknown;
  value?: unknown;
  /** Tool input arguments */
  args?: string | Record<string, unknown>;
  /** Human-readable summary of the output */
  summary?: string;
  /** Pre-built evidence cards from the backend (optional) */
  cards?: ToolEvidenceCard[];
  /** Additional metadata from the tool call (optional) */
  metadata?: Record<string, unknown>;
}

// -----------------------------------------------------------------------------
// Todo Types
// -----------------------------------------------------------------------------

export type TodoStatus = "pending" | "in_progress" | "done";

/**
 * A single todo item created by the agent.
 */
export interface TodoItem {
  /** Unique identifier */
  id: string;
  /** Todo title/description */
  title: string;
  /** Current status */
  status: TodoStatus;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Event payload for `agent_todos_update` custom events.
 */
export interface AgentTodosUpdateEvent {
  /** All current todo items */
  todos: TodoItem[];
}

// -----------------------------------------------------------------------------
// GenUI State Types
// -----------------------------------------------------------------------------

/**
 * Event payload for `genui_state_update` custom events.
 * Contains arbitrary state for generative UI components.
 */
export interface GenuiStateUpdateEvent {
  [key: string]: unknown;
}

/**
 * Event payload for `image_artifact` custom events.
 * Contains image data for frontend artifact display.
 */
export interface ImageArtifactEvent {
  id: string;
  type: "image";
  title: string;
  content: string;
  messageId: string;
  /** Preferred (Phase V): retrievable image URL (no base64 payloads). */
  imageUrl?: string;
  /** Legacy (pre-Phase V): base64 image payload. */
  imageData?: string;
  mimeType: string;
  altText?: string;
  aspectRatio?: string;
  resolution?: string;
  /** Optional source page URL for web-sourced images. */
  pageUrl?: string;
}

/**
 * Event payload for `article_artifact` custom events.
 * Contains article markdown for frontend artifact display.
 */
export interface ArticleArtifactEvent {
  id: string;
  type: "article";
  title: string;
  content: string;
  messageId: string;
  images?: Array<{
    url?: string;
    alt?: string;
    pageUrl?: string;
    page_url?: string;
  }>;
}

// -----------------------------------------------------------------------------
// Subagent Types
// -----------------------------------------------------------------------------

export interface SubagentSpawnEvent {
  subagentType: string;
  toolCallId: string;
  parentAgentId?: string;
  task: string;
  timestamp: string;
}

export interface SubagentEndEvent {
  subagentType: string;
  toolCallId: string;
  status: "success" | "error";
  reportPath: string;
  excerpt: string;
  timestamp: string;
}

export interface SubagentThinkingDeltaEvent {
  toolCallId: string;
  delta: string;
  timestamp: string;
  subagentType?: string;
}

// -----------------------------------------------------------------------------
// Union Type for All Custom Events
// -----------------------------------------------------------------------------

/**
 * Union type representing all possible custom event payloads.
 * Use this for type-safe event handling.
 */
export type AgentCustomEvent =
  | { name: "agent_thinking_trace"; value: AgentThinkingTraceEvent }
  | { name: "agent_timeline_update"; value: AgentTimelineUpdateEvent }
  | { name: "tool_evidence_update"; value: ToolEvidenceUpdateEvent }
  | { name: "agent_todos_update"; value: AgentTodosUpdateEvent }
  | { name: "genui_state_update"; value: GenuiStateUpdateEvent }
  | { name: "image_artifact"; value: ImageArtifactEvent }
  | { name: "article_artifact"; value: ArticleArtifactEvent }
  | { name: "subagent_spawn"; value: SubagentSpawnEvent }
  | { name: "subagent_end"; value: SubagentEndEvent }
  | { name: "subagent_thinking_delta"; value: SubagentThinkingDeltaEvent };

/**
 * Known AG-UI custom event names as const tuple for compile-time type derivation.
 */
export const KNOWN_EVENT_NAMES = [
  "agent_thinking_trace",
  "agent_timeline_update",
  "tool_evidence_update",
  "agent_todos_update",
  "genui_state_update",
  "image_artifact",
  "article_artifact",
  "subagent_spawn",
  "subagent_end",
  "subagent_thinking_delta",
] as const;

/**
 * Type derived from KNOWN_EVENT_NAMES for compile-time safety.
 */
export type KnownEventName = (typeof KNOWN_EVENT_NAMES)[number];

/**
 * Type guard to check if an event is a known AG-UI custom event.
 *
 * Performs shallow validation of the event structure:
 * - Checks that event is a non-null object
 * - Validates that event.name is a known event name string
 * - Validates that event.value exists and is an object
 *
 * @remarks For full validation of event.value shape, use the Zod validators
 * from validators.ts after this guard passes.
 */
export function isAgentCustomEvent(event: unknown): event is AgentCustomEvent {
  if (!event || typeof event !== "object") return false;
  const e = event as Record<string, unknown>;

  // Validate event.name is a known event name
  if (typeof e.name !== "string") return false;
  if (!(KNOWN_EVENT_NAMES as readonly string[]).includes(e.name)) return false;

  // Shallow validation: event.value must be present and be an object
  // Full validation of value shape should be done via Zod validators
  if (!("value" in e) || e.value === null || typeof e.value !== "object") {
    return false;
  }

  return true;
}

/**
 * Extract the event name from a custom event.
 */
export function getEventName(
  event: AgentCustomEvent,
): AgentCustomEvent["name"] {
  return event.name;
}

// -----------------------------------------------------------------------------
// Type Utilities
// -----------------------------------------------------------------------------

/**
 * Extract the value type for a specific event name.
 */
export type EventValueType<T extends AgentCustomEvent["name"]> = Extract<
  AgentCustomEvent,
  { name: T }
>["value"];

/**
 * Helper to create a typed event payload.
 */
export function createEvent<T extends AgentCustomEvent["name"]>(
  name: T,
  value: EventValueType<T>,
): Extract<AgentCustomEvent, { name: T }> {
  return { name, value } as Extract<AgentCustomEvent, { name: T }>;
}
