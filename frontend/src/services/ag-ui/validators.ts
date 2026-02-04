/**
 * AG-UI Event Validators
 *
 * Zod schemas for runtime validation of AG-UI custom events.
 * These validators ensure type safety at runtime when receiving events from the backend.
 */

import { z } from "zod";
import type {
  AgentThinkingTraceEvent,
  AgentTimelineUpdateEvent,
  ToolEvidenceUpdateEvent,
  AgentTodosUpdateEvent,
  SubagentSpawnEvent,
  SubagentEndEvent,
  SubagentThinkingDeltaEvent,
  TraceStep,
  TimelineOperation,
  TodoItem,
  ToolEvidenceCard,
} from "./event-types";

// -----------------------------------------------------------------------------
// Trace Step Schema
// -----------------------------------------------------------------------------

export const TraceStepSchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  type: z.enum(["thought", "action", "result"]),
  content: z.string(),
  metadata: z.record(z.string(), z.unknown()),
});

// -----------------------------------------------------------------------------
// Timeline Operation Schema
// -----------------------------------------------------------------------------

export const TimelineOperationSchema = z.object({
  id: z.string(),
  type: z.enum(["agent", "tool", "thought", "todo"]),
  name: z.string(),
  status: z.enum(["pending", "running", "success", "error"]),
  parent: z.string().optional(),
  children: z.array(z.string()),
  startTime: z.string().optional(),
  endTime: z.string().optional(),
  duration: z.number().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

// -----------------------------------------------------------------------------
// Todo Item Schema
// -----------------------------------------------------------------------------

export const TodoItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.enum(["pending", "in_progress", "done"]),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

// -----------------------------------------------------------------------------
// Event Schemas
// -----------------------------------------------------------------------------

export const AgentThinkingTraceEventSchema = z.object({
  totalSteps: z.number(),
  thinkingTrace: z.array(TraceStepSchema).optional(),
  latestStep: TraceStepSchema.optional(),
  activeStepId: z.string().optional(),
});

export const AgentTimelineUpdateEventSchema = z.object({
  operations: z.array(TimelineOperationSchema),
  currentOperationId: z.string().optional(),
});

const ToolEvidenceCardSchema: z.ZodSchema<ToolEvidenceCard> = z.object({
  id: z.string().optional(),
  type: z.string().optional(),
  title: z.string().optional(),
  snippet: z.string().optional(),
  url: z.string().optional(),
  fullContent: z.unknown().optional(),
  status: z.string().optional(),
  timestamp: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export const ToolEvidenceUpdateEventSchema = z.object({
  toolCallId: z.string(),
  toolName: z.string(),
  output: z.unknown().transform((val) => val ?? null), // Ensure output is always present
  summary: z.string().optional(),
  cards: z.array(ToolEvidenceCardSchema).optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export const AgentTodosUpdateEventSchema = z.object({
  todos: z.array(TodoItemSchema),
});

export const GenuiStateUpdateEventSchema = z.record(z.string(), z.unknown());

export const ImageArtifactEventSchema = z
  .object({
    id: z.string(),
    type: z.literal("image"),
    title: z.string(),
    content: z.string(),
    messageId: z.string(),
    imageUrl: z.string().url().optional(),
    imageData: z.string().optional(),
    mimeType: z.string(),
    altText: z.string().optional(),
    aspectRatio: z.string().optional(),
    resolution: z.string().optional(),
    pageUrl: z.string().url().optional(),
  })
  .refine((value) => Boolean(value.imageUrl || value.imageData), {
    message: "imageUrl or imageData required",
  });

export const ArticleArtifactEventSchema = z.object({
  id: z.string(),
  type: z.literal("article"),
  title: z.string(),
  content: z.string(),
  messageId: z.string(),
});

// -----------------------------------------------------------------------------
// Subagent Event Schemas
// -----------------------------------------------------------------------------

export const SubagentSpawnEventSchema: z.ZodSchema<SubagentSpawnEvent> =
  z.object({
    subagentType: z.string(),
    toolCallId: z.string(),
    parentAgentId: z.string().optional(),
    task: z.string(),
    timestamp: z.string(),
  });

export const SubagentEndEventSchema: z.ZodSchema<SubagentEndEvent> = z.object({
  subagentType: z.string(),
  toolCallId: z.string(),
  status: z.enum(["success", "error"]),
  reportPath: z.string(),
  excerpt: z.string(),
  timestamp: z.string(),
});

export const SubagentThinkingDeltaEventSchema: z.ZodSchema<SubagentThinkingDeltaEvent> =
  z.object({
    toolCallId: z.string(),
    delta: z.string(),
    timestamp: z.string(),
    subagentType: z.string().optional(),
  });

// -----------------------------------------------------------------------------
// Validation Utilities
// -----------------------------------------------------------------------------

/**
 * Validation result type
 */
export interface ValidationResult<T> {
  success: boolean;
  data?: T;
  error?: string;
  issues?: z.ZodIssue[];
}

/**
 * Validate data against a Zod schema with detailed error reporting.
 */
export function validateEvent<T>(
  schema: z.ZodSchema<T>,
  data: unknown,
): ValidationResult<T> {
  const result = schema.safeParse(data);

  if (result.success) {
    return {
      success: true,
      data: result.data,
    };
  }

  return {
    success: false,
    error: result.error.message,
    issues: result.error.issues,
  };
}

/**
 * Validate and return data or null with console warning.
 */
export function validateOrNull<T>(
  schema: z.ZodSchema<T>,
  data: unknown,
  eventName?: string,
): T | null {
  const result = validateEvent(schema, data);

  if (!result.success) {
    console.warn(
      `[AG-UI] Event validation failed${eventName ? ` for ${eventName}` : ""}:`,
      result.error,
    );
    if (result.issues) {
      console.warn("[AG-UI] Validation issues:", result.issues);
    }
    return null;
  }

  return result.data ?? null;
}

/**
 * Validate a thinking trace event.
 */
export function validateThinkingTrace(
  data: unknown,
): AgentThinkingTraceEvent | null {
  return validateOrNull(
    AgentThinkingTraceEventSchema,
    data,
    "agent_thinking_trace",
  );
}

/**
 * Validate a timeline update event.
 */
export function validateTimelineUpdate(
  data: unknown,
): AgentTimelineUpdateEvent | null {
  return validateOrNull(
    AgentTimelineUpdateEventSchema,
    data,
    "agent_timeline_update",
  );
}

/**
 * Validate a tool evidence event.
 */
export function validateToolEvidence(
  data: unknown,
): ToolEvidenceUpdateEvent | null {
  const result = validateOrNull(
    ToolEvidenceUpdateEventSchema,
    data,
    "tool_evidence_update",
  );
  if (!result) return null;
  // Ensure output is present (transform guarantees this)
  return result;
}

/**
 * Validate a todos update event.
 */
export function validateTodosUpdate(
  data: unknown,
): AgentTodosUpdateEvent | null {
  return validateOrNull(
    AgentTodosUpdateEventSchema,
    data,
    "agent_todos_update",
  );
}

/**
 * Validate a GenUI state update event.
 */
export function validateGenuiState(
  data: unknown,
): Record<string, unknown> | null {
  return validateOrNull(
    GenuiStateUpdateEventSchema,
    data,
    "genui_state_update",
  );
}

/**
 * Validate an image artifact event.
 */
export function validateImageArtifact(
  data: unknown,
): z.infer<typeof ImageArtifactEventSchema> | null {
  return validateOrNull(ImageArtifactEventSchema, data, "image_artifact");
}

/**
 * Validate an article artifact event.
 */
export function validateArticleArtifact(
  data: unknown,
): z.infer<typeof ArticleArtifactEventSchema> | null {
  return validateOrNull(ArticleArtifactEventSchema, data, "article_artifact");
}

export function validateSubagentSpawn(
  data: unknown,
): SubagentSpawnEvent | null {
  return validateOrNull(SubagentSpawnEventSchema, data, "subagent_spawn");
}

export function validateSubagentEnd(data: unknown): SubagentEndEvent | null {
  return validateOrNull(SubagentEndEventSchema, data, "subagent_end");
}

export function validateSubagentThinkingDelta(
  data: unknown,
): SubagentThinkingDeltaEvent | null {
  return validateOrNull(
    SubagentThinkingDeltaEventSchema,
    data,
    "subagent_thinking_delta",
  );
}

// -----------------------------------------------------------------------------
// Event Router
// -----------------------------------------------------------------------------

/**
 * Map of event names to their validators.
 */
export const eventValidators = {
  agent_thinking_trace: validateThinkingTrace,
  agent_timeline_update: validateTimelineUpdate,
  tool_evidence_update: validateToolEvidence,
  agent_todos_update: validateTodosUpdate,
  genui_state_update: validateGenuiState,
  image_artifact: validateImageArtifact,
  article_artifact: validateArticleArtifact,
  subagent_spawn: validateSubagentSpawn,
  subagent_end: validateSubagentEnd,
  subagent_thinking_delta: validateSubagentThinkingDelta,
} as const;

/**
 * Validate any AG-UI custom event by name.
 *
 * @param eventName - The event name to validate
 * @param data - The event data to validate
 * @returns Validated data or null if validation fails or event is unknown
 *
 * @remarks Unknown events return null to maintain consistent validation behavior.
 */
export function validateCustomEvent(
  eventName: string,
  data: unknown,
): unknown | null {
  const validator = eventValidators[eventName as keyof typeof eventValidators];
  if (!validator) {
    console.warn(
      `[AG-UI] Unknown event type '${eventName}' - discarding event`,
    );
    return null; // Return null for unknown events (consistent with validation failures)
  }
  return validator(data);
}
