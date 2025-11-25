/**
 * Type-Safe AG-UI Event Handlers
 *
 * This module provides typed handlers for AG-UI custom events.
 * Each handler validates incoming data and updates the appropriate state.
 */

import type {
  AgentThinkingTraceEvent,
  AgentTimelineUpdateEvent,
  ToolEvidenceUpdateEvent,
  AgentTodosUpdateEvent,
  TraceStep,
  TimelineOperation,
  TodoItem,
} from '@/services/ag-ui/event-types';
import {
  validateThinkingTrace,
  validateTimelineUpdate,
  validateToolEvidence,
  validateTodosUpdate,
  validateGenuiState,
} from '@/services/ag-ui/validators';

// -----------------------------------------------------------------------------
// Handler Context
// -----------------------------------------------------------------------------

/**
 * Context providing state setters for event handlers.
 */
export interface EventHandlerContext {
  /** Update the full thinking trace */
  setThinkingTrace: (trace: TraceStep[]) => void;
  /** Append a step to the thinking trace */
  appendTraceStep: (step: TraceStep) => void;
  /** Update the timeline operations */
  setTimelineOperations: (operations: TimelineOperation[]) => void;
  /** Set the current operation ID */
  setCurrentOperationId: (id: string | null) => void;
  /** Add or update tool evidence */
  setToolEvidence: (toolCallId: string, evidence: ToolEvidenceUpdateEvent) => void;
  /** Update the todo list */
  setTodos: (todos: TodoItem[]) => void;
  /** Update GenUI state */
  setGenuiState: (state: Record<string, unknown>) => void;
  /** Get current thinking trace */
  getThinkingTrace: () => TraceStep[];
}

// -----------------------------------------------------------------------------
// Individual Event Handlers
// -----------------------------------------------------------------------------

/**
 * Handle `agent_thinking_trace` events.
 *
 * These events can either:
 * 1. Send the full trace (on first event or reconnection)
 * 2. Send just the latest step (for incremental updates)
 */
export function handleThinkingTrace(
  data: unknown,
  ctx: EventHandlerContext
): void {
  const validated = validateThinkingTrace(data);
  if (!validated) return;

  if (validated.thinkingTrace && validated.thinkingTrace.length > 0) {
    // Full trace sync - replace existing
    ctx.setThinkingTrace(validated.thinkingTrace);
  } else if (validated.latestStep) {
    // Incremental update - append or update existing
    const currentTrace = ctx.getThinkingTrace();
    const existingIndex = currentTrace.findIndex(
      (step) => step.id === validated.latestStep!.id
    );

    if (existingIndex >= 0) {
      // Update existing step
      const updatedTrace = [...currentTrace];
      updatedTrace[existingIndex] = validated.latestStep;
      ctx.setThinkingTrace(updatedTrace);
    } else {
      // Append new step
      ctx.appendTraceStep(validated.latestStep);
    }
  }
}

/**
 * Handle `agent_timeline_update` events.
 *
 * Updates the timeline operations shown in the reasoning panel.
 */
export function handleTimelineUpdate(
  data: unknown,
  ctx: EventHandlerContext
): void {
  const validated = validateTimelineUpdate(data);
  if (!validated) return;

  ctx.setTimelineOperations(validated.operations);
  ctx.setCurrentOperationId(validated.currentOperationId ?? null);
}

/**
 * Handle `tool_evidence_update` events.
 *
 * Updates tool output evidence for display in the reasoning panel.
 */
export function handleToolEvidence(
  data: unknown,
  ctx: EventHandlerContext
): void {
  const validated = validateToolEvidence(data);
  if (!validated) return;

  ctx.setToolEvidence(validated.toolCallId, validated);
}

/**
 * Handle `agent_todos_update` events.
 *
 * Updates the todo list displayed to the user.
 */
export function handleTodosUpdate(
  data: unknown,
  ctx: EventHandlerContext
): void {
  const validated = validateTodosUpdate(data);
  if (!validated) return;

  ctx.setTodos(validated.todos);
}

/**
 * Handle `genui_state_update` events.
 *
 * Updates generative UI component state.
 */
export function handleGenuiState(
  data: unknown,
  ctx: EventHandlerContext
): void {
  const validated = validateGenuiState(data);
  if (!validated) return;

  ctx.setGenuiState(validated);
}

// -----------------------------------------------------------------------------
// Event Handler Registry
// -----------------------------------------------------------------------------

/**
 * Map of event names to their handlers.
 */
export const eventHandlers = {
  agent_thinking_trace: handleThinkingTrace,
  agent_timeline_update: handleTimelineUpdate,
  tool_evidence_update: handleToolEvidence,
  agent_todos_update: handleTodosUpdate,
  genui_state_update: handleGenuiState,
} as const;

/**
 * Type of known event names.
 */
export type KnownEventName = keyof typeof eventHandlers;

/**
 * Check if an event name is known.
 */
export function isKnownEventName(name: string): name is KnownEventName {
  return name in eventHandlers;
}

/**
 * Process any custom event using the appropriate handler.
 *
 * @param eventName - The event name
 * @param data - The event data
 * @param ctx - Handler context with state setters
 * @returns true if handled, false if unknown event
 */
export function processCustomEvent(
  eventName: string,
  data: unknown,
  ctx: EventHandlerContext
): boolean {
  if (!isKnownEventName(eventName)) {
    console.warn(`[AG-UI] Unknown custom event: ${eventName}`);
    return false;
  }

  const handler = eventHandlers[eventName];
  handler(data, ctx);
  return true;
}

// -----------------------------------------------------------------------------
// React Hook Helper
// -----------------------------------------------------------------------------

/**
 * Create an event handler context from React state setters.
 *
 * Usage in a component:
 * ```tsx
 * const [thinkingTrace, setThinkingTrace] = useState<TraceStep[]>([]);
 * const [operations, setOperations] = useState<TimelineOperation[]>([]);
 * // ... other state
 *
 * const ctx = createEventHandlerContext({
 *   setThinkingTrace,
 *   setOperations,
 *   // ...
 * });
 *
 * // In AG-UI client callback:
 * processCustomEvent(event.name, event.value, ctx);
 * ```
 */
export interface CreateContextOptions {
  /**
   * Getter function to retrieve current thinking trace.
   * Using a getter avoids stale closure issues when state changes.
   *
   * @example
   * // In a React component:
   * const thinkingTraceRef = useRef<TraceStep[]>([]);
   * // Keep ref in sync with state
   * thinkingTraceRef.current = thinkingTrace;
   *
   * const ctx = createEventHandlerContext({
   *   getThinkingTrace: () => thinkingTraceRef.current,
   *   // ...
   * });
   */
  getThinkingTrace: () => TraceStep[];
  setThinkingTrace: React.Dispatch<React.SetStateAction<TraceStep[]>>;
  setOperations: React.Dispatch<React.SetStateAction<TimelineOperation[]>>;
  setCurrentOperationId: React.Dispatch<React.SetStateAction<string | null>>;
  setToolEvidence: React.Dispatch<
    React.SetStateAction<Record<string, ToolEvidenceUpdateEvent>>
  >;
  setTodos: React.Dispatch<React.SetStateAction<TodoItem[]>>;
  setGenuiState: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
}

export function createEventHandlerContext(
  options: CreateContextOptions
): EventHandlerContext {
  return {
    setThinkingTrace: options.setThinkingTrace,
    appendTraceStep: (step) => {
      options.setThinkingTrace((prev) => [...prev, step]);
    },
    setTimelineOperations: options.setOperations,
    setCurrentOperationId: options.setCurrentOperationId,
    setToolEvidence: (id, evidence) => {
      options.setToolEvidence((prev) => ({ ...prev, [id]: evidence }));
    },
    setTodos: options.setTodos,
    setGenuiState: options.setGenuiState,
    // Use the getter function to always get the latest thinking trace
    getThinkingTrace: options.getThinkingTrace,
  };
}
