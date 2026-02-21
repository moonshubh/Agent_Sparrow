import type { Message } from "@/services/ag-ui/client";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

export interface CollapseAssistantsResult {
  messages: Message[];
  deduped: boolean;
  droppedCount: number;
}

export const shouldCollapseAssistantMessages = (
  agentType: string | undefined,
): boolean => agentType !== "log_analysis";

/**
 * Collapse assistant duplicates for the current run window.
 *
 * Keeps only the final assistant message after the run's user boundary and
 * merges metadata from dropped assistant candidates into the retained message.
 */
export function collapseAssistantMessagesForRun(
  messages: Message[],
  runUserIndex: number,
): CollapseAssistantsResult {
  if (runUserIndex < 0 || runUserIndex >= messages.length - 1) {
    return { messages, deduped: false, droppedCount: 0 };
  }

  const assistantIndices: number[] = [];
  for (let i = runUserIndex + 1; i < messages.length; i += 1) {
    if (messages[i]?.role === "assistant") {
      assistantIndices.push(i);
    }
  }

  if (assistantIndices.length <= 1) {
    return { messages, deduped: false, droppedCount: 0 };
  }

  const keepIndex = assistantIndices[assistantIndices.length - 1];
  const droppedCount = assistantIndices.length - 1;
  const keepMessage = messages[keepIndex];

  const mergedMetadata: Record<string, unknown> = {};
  for (const idx of assistantIndices) {
    const metadata = messages[idx]?.metadata;
    if (isRecord(metadata)) {
      Object.assign(mergedMetadata, metadata);
    }
  }

  const lastNonEmptyAssistantContent = (() => {
    for (let i = assistantIndices.length - 1; i >= 0; i -= 1) {
      const candidate = messages[assistantIndices[i]]?.content;
      if (isNonEmptyString(candidate)) return candidate;
    }
    return keepMessage.content;
  })();

  const mergedCreatedAt =
    keepMessage.created_at ||
    assistantIndices
      .map((idx) => messages[idx]?.created_at)
      .find((value): value is string => typeof value === "string");

  const updatedKeep: Message = {
    ...keepMessage,
    content: lastNonEmptyAssistantContent,
    metadata: Object.keys(mergedMetadata).length
      ? mergedMetadata
      : keepMessage.metadata,
    created_at: mergedCreatedAt,
  };

  const nextMessages: Message[] = [];
  for (let i = 0; i < messages.length; i += 1) {
    if (!assistantIndices.includes(i)) {
      nextMessages.push(messages[i]);
      continue;
    }
    if (i === keepIndex) {
      nextMessages.push(updatedKeep);
    }
  }

  return {
    messages: nextMessages,
    deduped: true,
    droppedCount,
  };
}
