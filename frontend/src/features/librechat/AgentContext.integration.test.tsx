import React, { useEffect } from "react";
import { act, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Message, RunAgentInput } from "@/services/ag-ui/client";
import {
  AgentProvider,
  useAgent,
  type AbstractAgent,
  type AgentEventHandlers,
} from "./AgentContext";

vi.mock("./artifacts", () => ({
  getGlobalArtifactStore: () => null,
}));

vi.mock("@/services/api/endpoints/sessions", () => ({
  sessionsAPI: {
    postMessage: vi.fn(async () => ({ id: "persisted-message-id" })),
    updateMessage: vi.fn(async () => ({ id: "persisted-message-id" })),
    listMessages: vi.fn(async () => []),
  },
}));

type RunCall = {
  input: Partial<RunAgentInput>;
  handlers: AgentEventHandlers;
  resolve: () => void;
  reject: (error: Error) => void;
  settled: boolean;
};

const createAbortError = (): Error => {
  try {
    return new DOMException("Aborted", "AbortError");
  } catch {
    const error = new Error("Aborted");
    error.name = "AbortError";
    return error;
  }
};

class MockAgent implements AbstractAgent {
  public messages: Message[] = [];
  public state: Record<string, unknown> = {
    provider: "google",
    model: "gemini-test-model",
  };
  public readonly runCalls: RunCall[] = [];
  public readonly addedMessages: Message[] = [];
  public readonly addMessage = vi.fn((message: Message) => {
    this.messages = [...this.messages, message];
    this.addedMessages.push(message);
  });
  public readonly setState = vi.fn((state: Record<string, unknown>) => {
    this.state = state;
  });
  public readonly runAgent = vi.fn(
    (
      input: Partial<RunAgentInput>,
      handlers: AgentEventHandlers,
    ): Promise<void> => {
      return new Promise((resolve, reject) => {
        const runCall: RunCall = {
          input,
          handlers,
          resolve: () => {
            if (runCall.settled) return;
            runCall.settled = true;
            resolve();
          },
          reject: (error: Error) => {
            if (runCall.settled) return;
            runCall.settled = true;
            reject(error);
          },
          settled: false,
        };
        this.runCalls.push(runCall);

        if (handlers.signal) {
          if (handlers.signal.aborted) {
            runCall.reject(createAbortError());
            return;
          }
          handlers.signal.addEventListener(
            "abort",
            () => runCall.reject(createAbortError()),
            { once: true },
          );
        }
      });
    },
  );
  public readonly abortRun = vi.fn(() => {
    for (let index = this.runCalls.length - 1; index >= 0; index -= 1) {
      const runCall = this.runCalls[index];
      if (!runCall?.settled) {
        runCall.reject(createAbortError());
        break;
      }
    }
  });
}

type AgentContextSnapshot = ReturnType<typeof useAgent>;

const AgentProbe = (props: {
  onUpdate: (snapshot: AgentContextSnapshot) => void;
}) => {
  const context = useAgent();
  useEffect(() => {
    props.onUpdate(context);
  });
  return null;
};

const setupAgentProvider = (agent: MockAgent) => {
  let snapshot: AgentContextSnapshot | null = null;
  render(
    <AgentProvider agent={agent}>
      <AgentProbe
        onUpdate={(nextSnapshot) => {
          snapshot = nextSnapshot;
        }}
      />
    </AgentProvider>,
  );

  const getSnapshot = (): AgentContextSnapshot => {
    if (!snapshot) {
      throw new Error("Agent context snapshot not available yet");
    }
    return snapshot;
  };

  return { getSnapshot };
};

const unresolvedObjectiveEvent = {
  name: "objective_hint_update",
  value: {
    runId: "run-context",
    laneId: "primary",
    objectiveId: "objective-open",
    phase: "execute",
    title: "Investigate timeout retry logic",
    status: "running",
    summary: "Pending timeout retries and retry backoff checks",
    startedAt: "2026-01-01T00:00:00.000Z",
  },
} as const;

describe("AgentContext integration", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("ingests events into panel/todo/tool evidence state and propagates web mode", async () => {
    const agent = new MockAgent();
    const { getSnapshot } = setupAgentProvider(agent);

    await waitFor(() => {
      expect(getSnapshot().webSearchMode).toBe("off");
    });

    act(() => {
      getSnapshot().setWebSearchMode("on");
    });

    let sendPromise: Promise<void> | null = null;
    act(() => {
      sendPromise = getSnapshot().sendMessage("Build the todo checklist");
    });

    await waitFor(() => {
      expect(agent.runCalls).toHaveLength(1);
    });

    const firstRun = agent.runCalls[0];
    await act(async () => {
      firstRun.handlers.onToolCallStartEvent?.({
        event: {
          toolCallId: "tool-1",
          toolCallName: "write_todos",
          timestamp: "2026-01-01T00:00:00.000Z",
          args: { goal: "tests" },
        },
      });

      await firstRun.handlers.onCustomEvent?.({
        event: {
          name: "tool_evidence_update",
          value: {
            toolCallId: "tool-1",
            toolName: "write_todos",
            summary: "Built todos",
            output: {
              todos: [{ id: "todo-1", title: "Draft tests", status: "pending" }],
            },
          },
        },
      });

      await firstRun.handlers.onCustomEvent?.({
        event: {
          name: "agent_todos_update",
          value: {
            todos: [
              { id: "todo-1", title: "Draft tests", status: "in_progress" },
            ],
          },
        },
      });

      firstRun.handlers.onToolCallResultEvent?.({
        event: {
          toolCallId: "tool-1",
          toolCallName: "write_todos",
          timestamp: "2026-01-01T00:00:01.000Z",
          result: {
            todos: [{ id: "todo-1", title: "Draft tests", status: "done" }],
          },
        },
      });

      firstRun.handlers.onMessagesChanged?.({
        messages: [
          {
            id: "server-user-1",
            role: "user",
            content: "Build the todo checklist",
            metadata: { web_search_mode: "on" },
          },
          {
            id: "assistant-1",
            role: "assistant",
            content: "Todo checklist complete.",
          },
        ],
      });

      firstRun.resolve();
      await sendPromise;
    });

    expect(firstRun.input.forwardedProps?.web_search_mode).toBe("on");
    expect(firstRun.input.forwardedProps?.force_websearch).toBe(true);
    expect(agent.addedMessages[0]?.metadata?.web_search_mode).toBe("on");

    await waitFor(() => {
      const snapshot = getSnapshot();
      expect(snapshot.todos[0]?.title).toBe("Draft tests");
      expect(snapshot.toolEvidence["tool-1"]?.summary).toBe("Built todos");
      expect(
        Object.values(snapshot.panelState.objectives).some(
          (objective) => objective.toolCallId === "tool-1",
        ),
      ).toBe(true);
    });
  });

  it("queues related follow-up prompts with overlap context during streaming", async () => {
    const agent = new MockAgent();
    const { getSnapshot } = setupAgentProvider(agent);

    let firstSendPromise: Promise<void> | null = null;
    act(() => {
      firstSendPromise = getSnapshot().sendMessage("Start long running run");
    });

    await waitFor(() => {
      expect(agent.runCalls).toHaveLength(1);
    });
    const run1 = agent.runCalls[0];

    await act(async () => {
      await run1.handlers.onCustomEvent?.({ event: unresolvedObjectiveEvent });
    });

    act(() => {
      void getSnapshot().sendMessage("continue timeout retry logic now");
    });

    await waitFor(() => {
      expect(agent.abortRun).toHaveBeenCalledTimes(1);
      expect(agent.runCalls).toHaveLength(2);
    });

    const run2 = agent.runCalls[1];
    expect(run2.input.forwardedProps?.overlap_objective_context).toContain(
      "Investigate timeout retry logic",
    );
    expect(getSnapshot().pendingPromptSteering).toBeNull();

    act(() => {
      run2.resolve();
    });
    await firstSendPromise;
    await waitFor(() => {
      expect(getSnapshot().isStreaming).toBe(false);
    });
  });

  it("uses explicit unrelated prompt path without overlap context", async () => {
    const agent = new MockAgent();
    const { getSnapshot } = setupAgentProvider(agent);

    let firstSendPromise: Promise<void> | null = null;
    act(() => {
      firstSendPromise = getSnapshot().sendMessage("Start long running run");
    });

    await waitFor(() => {
      expect(agent.runCalls).toHaveLength(1);
    });
    const run1 = agent.runCalls[0];

    await act(async () => {
      await run1.handlers.onCustomEvent?.({ event: unresolvedObjectiveEvent });
    });

    act(() => {
      void getSnapshot().sendMessage("different topic: summarize deployment");
    });

    await waitFor(() => {
      expect(agent.abortRun).toHaveBeenCalledTimes(1);
      expect(agent.runCalls).toHaveLength(2);
    });

    const run2 = agent.runCalls[1];
    expect(run2.input.forwardedProps?.overlap_objective_context).toBeUndefined();

    act(() => {
      run2.resolve();
    });
    await firstSendPromise;
    await waitFor(() => {
      expect(getSnapshot().isStreaming).toBe(false);
    });
  });

  it("opens uncertain prompt steering and auto-resolves to new topic after timeout", async () => {
    vi.useFakeTimers();
    const agent = new MockAgent();
    const { getSnapshot } = setupAgentProvider(agent);

    let firstSendPromise: Promise<void> | null = null;
    act(() => {
      firstSendPromise = getSnapshot().sendMessage("Start long running run");
    });

    expect(agent.runCalls).toHaveLength(1);
    const run1 = agent.runCalls[0];

    await act(async () => {
      await run1.handlers.onCustomEvent?.({ event: unresolvedObjectiveEvent });
    });

    act(() => {
      void getSnapshot().sendMessage("Need timeout dashboard metrics");
    });

    await act(async () => {
      await Promise.resolve();
    });
    expect(getSnapshot().pendingPromptSteering).not.toBeNull();
    expect(agent.abortRun).toHaveBeenCalledTimes(0);

    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
      vi.runOnlyPendingTimers();
      await Promise.resolve();
    });

    expect(agent.abortRun).toHaveBeenCalledTimes(1);
    expect(agent.runCalls).toHaveLength(2);

    const run2 = agent.runCalls[1];
    expect(run2.input.forwardedProps?.overlap_objective_context).toBeUndefined();
    expect(getSnapshot().pendingPromptSteering).toBeNull();

    await act(async () => {
      run2.resolve();
      await Promise.resolve();
    });
    await firstSendPromise;
    expect(getSnapshot().isStreaming).toBe(false);
  });

  it(
    "retries disconnect failures and marks stream as incomplete when retries exhaust",
    async () => {
      vi.useFakeTimers();
      const agent = new MockAgent();
      const { getSnapshot } = setupAgentProvider(agent);

      let sendPromise: Promise<void> | null = null;
      act(() => {
        sendPromise = getSnapshot().sendMessage("Run a long reliability check");
      });

      expect(agent.runCalls).toHaveLength(1);

      const run1 = agent.runCalls[0];
      await act(async () => {
        await run1.handlers.onCustomEvent?.({ event: unresolvedObjectiveEvent });
      });

      act(() => {
        run1.reject(new TypeError("Failed to fetch"));
      });
      await act(async () => {
        await Promise.resolve();
      });

      expect(getSnapshot().streamRecovery.isRetrying).toBe(true);
      expect(getSnapshot().streamRecovery.attemptsUsed).toBe(1);

      await act(async () => {
        vi.advanceTimersByTime(2500);
        await Promise.resolve();
      });
      expect(agent.runCalls).toHaveLength(2);

      act(() => {
        agent.runCalls[1].reject(new TypeError("Network request failed"));
      });
      await act(async () => {
        await Promise.resolve();
      });

      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });
      expect(agent.runCalls).toHaveLength(3);

      act(() => {
        agent.runCalls[2].reject(new TypeError("Connection reset"));
      });
      await act(async () => {
        await Promise.resolve();
      });

      await act(async () => {
        vi.advanceTimersByTime(7500);
        await Promise.resolve();
      });
      expect(agent.runCalls).toHaveLength(4);

      act(() => {
        agent.runCalls[3].reject(new TypeError("Failed to fetch"));
      });
      await act(async () => {
        await Promise.resolve();
      });

      await act(async () => {
        await vi.runOnlyPendingTimersAsync();
        await Promise.resolve();
      });

      await expect(sendPromise).resolves.toBeUndefined();

      const snapshot = getSnapshot();
      expect(snapshot.streamRecovery.exhausted).toBe(true);
      expect(snapshot.streamRecovery.incomplete).toBe(true);
      expect(snapshot.panelState.runStatus).toBe("unknown");
      expect(snapshot.error?.message).toContain("Partial output");
    },
    20_000,
  );
});
