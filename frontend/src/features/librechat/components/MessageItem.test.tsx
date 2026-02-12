import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Message } from "@/services/ag-ui/client";
import type { PanelSnapshotV1 } from "@/features/librechat/panel-snapshot";

vi.mock("next/dynamic", () => ({
  default: () => {
    const Stub = () => null;
    return Stub;
  },
}));

vi.mock("./ThinkingPanel", () => ({
  ThinkingPanel: () => <div data-testid="thinking-panel" />,
}));

vi.mock("@/features/librechat/components/AttachmentPreview", () => ({
  AttachmentPreviewList: () => null,
}));

vi.mock("@/features/librechat/components/EnhancedMarkdown", () => ({
  EnhancedMarkdown: (props: { content: string }) => <div>{props.content}</div>,
}));

vi.mock("./FeedbackPopover", () => ({
  FeedbackPopover: () => null,
}));

vi.mock("./log-analysis-notes-dropdown", () => ({
  LogAnalysisNotesDropdown: () => null,
}));

import { MessageItem } from "./MessageItem";

const buildSnapshot = (params: {
  runId: string;
  objectiveId: string;
  updatedAt: string;
}): PanelSnapshotV1 => ({
  schema: "panel_snapshot_v1",
  version: 1,
  captured_at: params.updatedAt,
  runId: params.runId,
  lanes: {
    primary: {
      id: "primary",
      type: "primary",
      title: "Primary",
      objectiveIds: [params.objectiveId],
      status: "running",
      updatedAt: params.updatedAt,
    },
  },
  laneOrder: ["primary"],
  objectives: {
    [params.objectiveId]: {
      id: params.objectiveId,
      runId: params.runId,
      laneId: "primary",
      phase: "execute",
      kind: "tool",
      title: "Collect evidence",
      status: "running",
      summary: "Running analysis",
      detail: "Gathering details for the report",
      startedAt: params.updatedAt,
      updatedAt: params.updatedAt,
      evidenceCards: [],
      sourceEvent: "fixture",
    },
  },
  todos: [],
  activeLaneId: "primary",
  activeObjectiveId: params.objectiveId,
  runStatus: "running",
  updatedAt: params.updatedAt,
});

describe("MessageItem panel metadata smoke checks", () => {
  it("shows edited provenance badge, allows version switching, and fires regenerate", () => {
    const onRegenerate = vi.fn();
    const versionOneSnapshot = buildSnapshot({
      runId: "run-v1",
      objectiveId: "objective-v1",
      updatedAt: "2026-01-01T00:00:00.000Z",
    });
    const versionTwoSnapshot = buildSnapshot({
      runId: "run-v2",
      objectiveId: "objective-v2",
      updatedAt: "2026-01-01T00:02:00.000Z",
    });

    const assistantMessage: Message = {
      id: "assistant-message-1",
      role: "assistant",
      content: "Latest assistant response.",
      metadata: {
        panel_snapshot_v1: versionTwoSnapshot,
        panel_versions_v1: [
          {
            id: "version-1",
            label: "Version 1",
            created_at: "2026-01-01T00:00:00.000Z",
            snapshot: versionOneSnapshot,
          },
          {
            id: "version-2",
            label: "Version 2",
            created_at: "2026-01-01T00:02:00.000Z",
            snapshot: versionTwoSnapshot,
          },
        ],
        panel_provenance_v1: {
          source: "assistant_run",
          generated_at: "2026-01-01T00:02:00.000Z",
          edited: true,
          edited_at: "2026-01-01T00:03:00.000Z",
          edit_count: 1,
          version_count: 2,
          latest_version_id: "version-2",
        },
      },
    };

    render(
      <MessageItem
        message={assistantMessage}
        isLast={false}
        isStreaming={false}
        onRegenerate={onRegenerate}
      />,
    );

    expect(screen.getByText("Edited")).toBeInTheDocument();

    const versionSelect = screen.getByTitle("Reasoning snapshot version");
    expect(versionSelect).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Version 1" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Version 2" })).toBeInTheDocument();

    fireEvent.change(versionSelect, { target: { value: "version-1" } });
    expect((versionSelect as HTMLSelectElement).value).toBe("version-1");

    fireEvent.click(screen.getByLabelText("Regenerate response"));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });
});
