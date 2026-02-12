import { describe, expect, it } from "vitest";
import type { PanelState } from "./panel-event-adapter";
import {
  PANEL_SNAPSHOT_MAX_BYTES,
  buildEditedProvenance,
  buildGeneratedProvenance,
  buildPanelSnapshotV1,
  buildPanelVersionHistory,
  coercePanelProvenanceV1,
  seedPanelVersionsFromMetadata,
  type PanelSnapshotV1,
  type PanelSnapshotVersionV1,
} from "./panel-snapshot";

const byteLength = (value: unknown): number =>
  new TextEncoder().encode(JSON.stringify(value)).length;

const buildSnapshotFixture = (
  params: { runId: string; objectiveSuffix: string; updatedAt: string },
): PanelSnapshotV1 => ({
  schema: "panel_snapshot_v1",
  version: 1,
  captured_at: params.updatedAt,
  runId: params.runId,
  lanes: {
    primary: {
      id: "primary",
      type: "primary",
      title: "Primary",
      objectiveIds: [`objective-${params.objectiveSuffix}`],
      status: "running",
      updatedAt: params.updatedAt,
    },
  },
  laneOrder: ["primary"],
  objectives: {
    [`objective-${params.objectiveSuffix}`]: {
      id: `objective-${params.objectiveSuffix}`,
      runId: params.runId,
      laneId: "primary",
      phase: "execute",
      kind: "tool",
      title: `Objective ${params.objectiveSuffix}`,
      status: "running",
      summary: "Investigating long-running workflow state",
      detail: "Captured state from streaming tool execution",
      startedAt: params.updatedAt,
      updatedAt: params.updatedAt,
      evidenceCards: [],
      sourceEvent: "fixture",
    },
  },
  todos: [
    {
      id: `todo-${params.objectiveSuffix}`,
      title: "Validate snapshot helper behavior",
      status: "pending",
    },
  ],
  activeLaneId: "primary",
  activeObjectiveId: `objective-${params.objectiveSuffix}`,
  runStatus: "running",
  updatedAt: params.updatedAt,
});

const buildLargePanelState = (): PanelState => {
  const updatedAt = "2026-01-01T00:05:00.000Z";
  const objectiveIds = Array.from({ length: 96 }, (_, index) => `obj-${index + 1}`);

  const objectives = Object.fromEntries(
    objectiveIds.map((id, index) => [
      id,
      {
        id,
        runId: "run-heavy",
        laneId: "primary",
        phase: "execute" as const,
        kind: "tool" as const,
        title: `Objective ${index + 1} with verbose title text`,
        status: "running" as const,
        summary:
          "Detailed summary ".repeat(24) +
          `for ${id} including additional context and long descriptive text.`,
        detail:
          "Long detail block ".repeat(72) +
          `for ${id} to stress snapshot byte budget trimming behavior.`,
        toolCallId: `tool-${index + 1}`,
        startedAt: "2026-01-01T00:00:00.000Z",
        updatedAt,
        evidenceCards: Array.from({ length: 8 }, (_, evidenceIndex) => ({
          id: `${id}-evidence-${evidenceIndex + 1}`,
          title: `Evidence ${evidenceIndex + 1}`,
          snippet:
            "Snippet ".repeat(28) +
            `captured for ${id} evidence ${evidenceIndex + 1}.`,
          metadata: {
            source: "fixture",
            chunk: evidenceIndex + 1,
          },
        })),
        sourceEvent: "fixture",
      },
    ]),
  );

  return {
    runId: "run-heavy",
    lanes: {
      primary: {
        id: "primary",
        type: "primary",
        title: "Primary",
        objectiveIds,
        status: "running",
        updatedAt,
      },
    },
    laneOrder: ["primary"],
    objectives,
    todos: Array.from({ length: 32 }, (_, index) => ({
      id: `todo-${index + 1}`,
      title: "Todo item with a verbose label for snapshot pressure ".repeat(3),
      status: index % 3 === 0 ? "done" : index % 3 === 1 ? "in_progress" : "pending",
    })),
    activeLaneId: "primary",
    activeObjectiveId: objectiveIds[objectiveIds.length - 1],
    runStatus: "running",
    updatedAt,
  };
};

describe("panel-snapshot size budget", () => {
  it("caps serialized snapshots at 20KB", () => {
    const snapshot = buildPanelSnapshotV1(buildLargePanelState());
    expect(byteLength(snapshot)).toBeLessThanOrEqual(PANEL_SNAPSHOT_MAX_BYTES);
    expect(snapshot.laneOrder[0]).toBe("primary");
  });
});

describe("panel version/provenance helpers", () => {
  it("builds bounded version history and relabels in chronological order", () => {
    const inherited: PanelSnapshotVersionV1[] = [
      {
        id: "v1",
        label: "Version 1",
        created_at: "2026-01-01T00:00:00.000Z",
        snapshot: buildSnapshotFixture({
          runId: "run-a",
          objectiveSuffix: "a",
          updatedAt: "2026-01-01T00:00:00.000Z",
        }),
      },
      {
        id: "v2",
        label: "Version 2",
        created_at: "2026-01-01T00:01:00.000Z",
        snapshot: buildSnapshotFixture({
          runId: "run-b",
          objectiveSuffix: "b",
          updatedAt: "2026-01-01T00:01:00.000Z",
        }),
      },
      {
        id: "v3",
        label: "Version 3",
        created_at: "2026-01-01T00:02:00.000Z",
        snapshot: buildSnapshotFixture({
          runId: "run-c",
          objectiveSuffix: "c",
          updatedAt: "2026-01-01T00:02:00.000Z",
        }),
      },
      {
        id: "v4",
        label: "Version 4",
        created_at: "2026-01-01T00:03:00.000Z",
        snapshot: buildSnapshotFixture({
          runId: "run-d",
          objectiveSuffix: "d",
          updatedAt: "2026-01-01T00:03:00.000Z",
        }),
      },
    ];

    const history = buildPanelVersionHistory({
      inherited,
      currentSnapshot: buildSnapshotFixture({
        runId: "run-e",
        objectiveSuffix: "e",
        updatedAt: "2026-01-01T00:04:00.000Z",
      }),
      createdAt: "2026-01-01T00:04:00.000Z",
    });

    expect(history).toHaveLength(4);
    expect(history.map((entry) => entry.label)).toEqual([
      "Version 1",
      "Version 2",
      "Version 3",
      "Version 4",
    ]);
    expect(history[history.length - 1]?.snapshot.runId).toBe("run-e");
  });

  it("seeds versions from metadata snapshot when it is missing from version list", () => {
    const metadataSnapshot = buildSnapshotFixture({
      runId: "run-metadata",
      objectiveSuffix: "metadata",
      updatedAt: "2026-01-01T00:10:00.000Z",
    });
    const seeded = seedPanelVersionsFromMetadata({
      panel_versions_v1: [
        {
          id: "v-base",
          label: "Version 1",
          created_at: "2026-01-01T00:09:00.000Z",
          snapshot: buildSnapshotFixture({
            runId: "run-base",
            objectiveSuffix: "base",
            updatedAt: "2026-01-01T00:09:00.000Z",
          }),
        },
      ],
      panel_snapshot_v1: metadataSnapshot,
    });

    expect(seeded).toHaveLength(2);
    expect(
      seeded.some(
        (version) =>
          version.snapshot.runId === "run-metadata" &&
          version.snapshot.updatedAt === "2026-01-01T00:10:00.000Z",
      ),
    ).toBe(true);
  });

  it("preserves regenerate linkage and increments edited provenance", () => {
    const versions: PanelSnapshotVersionV1[] = [
      {
        id: "version-1",
        label: "Version 1",
        created_at: "2026-01-01T00:00:00.000Z",
        snapshot: buildSnapshotFixture({
          runId: "run-prov",
          objectiveSuffix: "prov",
          updatedAt: "2026-01-01T00:00:00.000Z",
        }),
      },
      {
        id: "version-2",
        label: "Version 2",
        created_at: "2026-01-01T00:05:00.000Z",
        snapshot: buildSnapshotFixture({
          runId: "run-prov-2",
          objectiveSuffix: "prov2",
          updatedAt: "2026-01-01T00:05:00.000Z",
        }),
      },
    ];

    const generated = buildGeneratedProvenance({
      generatedAt: "2026-01-01T00:06:00.000Z",
      versions,
      regeneratedFromMessageId: "assistant-msg-123",
    });
    const edited = buildEditedProvenance({
      existing: generated as unknown as Record<string, unknown>,
      editedAt: "2026-01-01T00:07:00.000Z",
    });
    const normalizedEdited = coercePanelProvenanceV1(edited);

    expect(generated.latest_version_id).toBe("version-2");
    expect(generated.regenerated_from_message_id).toBe("assistant-msg-123");
    expect(generated.version_count).toBe(2);

    expect(normalizedEdited?.edited).toBe(true);
    expect(normalizedEdited?.edit_count).toBe(1);
    expect(normalizedEdited?.regenerated_from_message_id).toBe(
      "assistant-msg-123",
    );
    expect(normalizedEdited?.latest_version_id).toBe("version-2");
    expect(normalizedEdited?.version_count).toBe(2);
  });
});
