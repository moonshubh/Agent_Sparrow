"use client";

import React, { useEffect, useRef, memo, useCallback } from "react";
import type { Message } from "@/services/ag-ui/client";
import { MessageItem } from "./MessageItem";
import { useAgent } from "../AgentContext";
import { sessionsAPI } from "@/services/api/endpoints/sessions";
import type { AttachmentInput } from "@/services/ag-ui/types";
import type {
  ToolEvidenceUpdateEvent,
  TraceStep,
  TodoItem,
} from "@/services/ag-ui/event-types";
import type { SubagentRun } from "@/features/librechat/AgentContext";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  sessionId?: string;
}

const EMPTY_ATTACHMENTS: AttachmentInput[] = [];
const EMPTY_ACTIVE_TOOLS: string[] = [];
const EMPTY_THINKING_TRACE: TraceStep[] = [];
const EMPTY_TODOS: TodoItem[] = [];
const EMPTY_TOOL_EVIDENCE: Record<string, ToolEvidenceUpdateEvent> = {};
const EMPTY_SUBAGENT_ACTIVITY: Map<string, SubagentRun> = new Map();

function stableMessageKey(message: Message, index: number): string {
  if (message.id) return message.id;
  if (process.env.NODE_ENV !== "production") {
    console.warn(
      "[LibreChat] Message missing id; falling back to content hash",
      message,
    );
  }
  const content =
    typeof message.content === "string"
      ? message.content
      : JSON.stringify(message.content ?? "");
  const base = `${message.role}|${message.name || ""}|${message.tool_call_id || ""}|${content}|${index}`;
  let hash = 0;
  for (let i = 0; i < base.length; i += 1) {
    hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
  }
  return `msg-${hash.toString(16)}`;
}

export const MessageList = memo(function MessageList({
  messages,
  isStreaming,
  sessionId,
}: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(messages.length);
  const {
    updateMessageContent,
    regenerateLastResponse,
    resolvePersistedMessageId,
    messageAttachments,
    thinkingTrace,
    activeTraceStepId,
    activeTools,
    todos,
    toolEvidence,
    subagentActivity,
    researchProgress,
    researchStatus,
    isResearching,
  } = useAgent();

  // Handle message edit - updates context immediately and persists to API
  const handleEditMessage = useCallback(
    async (messageId: string, content: string) => {
      // Update in context immediately for responsive UI
      updateMessageContent(messageId, content);

      // Persist to backend if we have a session
      if (sessionId) {
        try {
          const persistedId = resolvePersistedMessageId(messageId);
          if (!persistedId) {
            console.debug(
              "[MessageList] Skipping persist for non-persisted message",
              messageId,
            );
            return;
          }
          await sessionsAPI.updateMessage(sessionId, persistedId, content);
        } catch (error) {
          console.error("[MessageList] Failed to persist message edit:", error);
          // Note: We could add a toast notification here in the future
        }
      }
    },
    [resolvePersistedMessageId, sessionId, updateMessageContent],
  );

  // Auto-scroll only when message count changes (not on every content update)
  useEffect(() => {
    const lengthChanged = messages.length !== prevLengthRef.current;
    prevLengthRef.current = messages.length;

    if (lengthChanged) {
      // Use instant scroll during streaming for better UX, smooth otherwise
      messagesEndRef.current?.scrollIntoView({
        behavior: isStreaming ? "auto" : "smooth",
      });
    }
  }, [messages.length, isStreaming]);

  return (
    <div
      className="lc-messages"
      role="log"
      aria-label="Chat messages"
      aria-live="polite"
    >
      <div className="lc-messages-inner">
        {messages.map((message, index) => {
          const isLast = index === messages.length - 1;
          const isLastAssistant = isLast && message.role === "assistant";
          const attachments =
            messageAttachments[message.id] ?? EMPTY_ATTACHMENTS;
          return (
            <MessageItem
              key={stableMessageKey(message, index)}
              message={message}
              isLast={isLast}
              isStreaming={isStreaming}
              sessionId={sessionId}
              attachments={attachments}
              thinkingTrace={isLast ? thinkingTrace : EMPTY_THINKING_TRACE}
              activeTraceStepId={isLast ? activeTraceStepId : undefined}
              activeTools={isLast ? activeTools : EMPTY_ACTIVE_TOOLS}
              todos={isLast ? todos : EMPTY_TODOS}
              toolEvidence={isLast ? toolEvidence : EMPTY_TOOL_EVIDENCE}
              subagentActivity={
                isLast ? subagentActivity : EMPTY_SUBAGENT_ACTIVITY
              }
              researchProgress={isLast ? researchProgress : 0}
              researchStatus={isLast ? researchStatus : "idle"}
              isResearching={isLast ? isResearching : false}
              onEditMessage={handleEditMessage}
              onRegenerate={
                isLastAssistant && !isStreaming
                  ? regenerateLastResponse
                  : undefined
              }
            />
          );
        })}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>
    </div>
  );
});

export default MessageList;
