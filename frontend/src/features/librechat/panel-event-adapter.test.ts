import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createInitialPanelState,
  reducePanelEvent,
  usePanelEventAdapter,
} from "./panel-event-adapter";
import type { AgentCustomEvent, TraceStep } from "@/services/ag-ui/event-types";

const BASE_TS = "2026-01-01T00:00:00.000Z";

const traceStep = (params: {
  id: string;
  content: string;
  timestamp: string;
}): TraceStep => ({
  id: params.id,
  type: "thought",
  content: params.content,
  timestamp: params.timestamp,
  metadata: {},
});

describe("panel-event-adapter reducer", () => {
  it("keeps terminal unknown objective when a stale running patch arrives", () => {
    let state = createInitialPanelState("run-unknown");

    state = reducePanelEvent(state, {
      name: "objective_hint_update",
      value: {
        runId: "run-unknown",
        laneId: "primary",
        objectiveId: "objective-1",
        phase: "execute",
        title: "Investigate timeout handling",
        status: "unknown",
        summary: "Tool timeout status was not emitted",
        startedAt: "2026-01-01T00:00:02.000Z",
        endedAt: "2026-01-01T00:00:02.000Z",
      },
    });

    state = reducePanelEvent(state, {
      name: "objective_hint_update",
      value: {
        runId: "run-unknown",
        laneId: "primary",
        objectiveId: "objective-1",
        phase: "execute",
        title: "Investigate timeout handling",
        status: "running",
        summary: "Older status update",
        startedAt: BASE_TS,
      },
    });

    expect(state.objectives["objective-1"]?.status).toBe("unknown");
    expect(state.objectives["objective-1"]?.summary).toBe(
      "Tool timeout status was not emitted",
    );
  });

  it("ignores stale terminal tool results when a newer result already exists", () => {
    let state = createInitialPanelState("run-stale-result");

    state = reducePanelEvent(state, {
      name: "tool_call_start",
      value: {
        toolCallId: "call-1",
        toolName: "web_search",
        timestamp: "2026-01-01T00:00:00.000Z",
        args: { query: "status page" },
      },
    });

    state = reducePanelEvent(state, {
      name: "tool_call_result",
      value: {
        toolCallId: "call-1",
        toolName: "web_search",
        timestamp: "2026-01-01T00:00:02.000Z",
        status: "done",
        result: "newer success",
      },
    });

    state = reducePanelEvent(state, {
      name: "tool_call_result",
      value: {
        toolCallId: "call-1",
        toolName: "web_search",
        timestamp: "2026-01-01T00:00:01.000Z",
        status: "error",
        result: "older failed payload",
      },
    });

    const objective = state.objectives["tool:call-1"];
    expect(objective?.status).toBe("done");
    expect(objective?.detail).toContain("newer success");
  });

  it("allows unknown fallback objectives to recover when newer backend updates arrive", () => {
    let state = createInitialPanelState("run-recover-unknown");

    state = reducePanelEvent(state, {
      name: "objective_hint_update",
      value: {
        runId: "run-recover-unknown",
        laneId: "primary",
        objectiveId: "objective-recover",
        phase: "execute",
        title: "Recover from stale state",
        status: "unknown",
        summary: "No completion event received before timeout.",
        startedAt: "2026-01-01T00:00:10.000Z",
      },
    });

    state = reducePanelEvent(state, {
      name: "objective_hint_update",
      value: {
        runId: "run-recover-unknown",
        laneId: "primary",
        objectiveId: "objective-recover",
        phase: "execute",
        title: "Recover from stale state",
        status: "running",
        summary: "Backend resumed and emitted fresh status.",
        startedAt: "2026-01-01T00:00:20.000Z",
      },
    });

    expect(state.objectives["objective-recover"]?.status).toBe("running");
    expect(state.objectives["objective-recover"]?.summary).toBe(
      "Backend resumed and emitted fresh status.",
    );
  });
});

describe("usePanelEventAdapter cadence batching", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("flushes thought cadence events only after batch timeout and dedupes repeats", async () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => usePanelEventAdapter({ batchMs: 40 }));

    const repeatedTraceEvent: AgentCustomEvent = {
      name: "agent_thinking_trace",
      value: {
        totalSteps: 1,
        latestStep: traceStep({
          id: "step-1",
          content: "Plan investigation checklist",
          timestamp: BASE_TS,
        }),
        activeStepId: "step-1",
      },
    };

    act(() => {
      result.current.applyCustomEvent(repeatedTraceEvent);
      result.current.applyCustomEvent(repeatedTraceEvent);
    });

    expect(Object.keys(result.current.panelState.objectives)).toHaveLength(0);

    act(() => {
      vi.advanceTimersByTime(39);
    });
    expect(Object.keys(result.current.panelState.objectives)).toHaveLength(0);

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(Object.keys(result.current.panelState.objectives)).toHaveLength(1);
    expect(result.current.panelState.objectives["trace:step-1"]?.status).toBe(
      "running",
    );
  });

  it("marks stale running objectives as unknown after timeout window", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(BASE_TS));

    const { result } = renderHook(() => usePanelEventAdapter({ batchMs: 40 }));

    act(() => {
      result.current.applyToolCallStart({
        toolCallId: "stale-tool-1",
        toolName: "web_search",
        timestamp: BASE_TS,
      });
    });

    expect(
      result.current.panelState.objectives["tool:stale-tool-1"]?.status,
    ).toBe("running");

    act(() => {
      vi.setSystemTime(new Date("2026-01-01T00:00:35.000Z"));
      vi.advanceTimersByTime(2500);
    });

    const objective = result.current.panelState.objectives["tool:stale-tool-1"];
    expect(objective?.status).toBe("unknown");
    expect(result.current.panelState.runStatus).toBe("unknown");
  });

  it("forces unresolved objectives to unknown when marking run incomplete", () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => usePanelEventAdapter({ batchMs: 40 }));

    act(() => {
      result.current.applyToolCallStart({
        toolCallId: "incomplete-tool",
        toolName: "write_todos",
        timestamp: BASE_TS,
      });
      result.current.syncTodosSnapshot([
        { id: "todo-1", title: "Open todo", status: "in_progress" },
      ]);
    });

    act(() => {
      result.current.markRunIncomplete("Connection lost before completion.");
    });

    expect(result.current.panelState.runStatus).toBe("unknown");
    expect(
      result.current.panelState.objectives["tool:incomplete-tool"]?.status,
    ).toBe("unknown");
  });
});
