"use client";

import React from "react";
import { AssistantMessageProps, Markdown } from "@copilotkit/react-ui";
import { ReasoningPanel } from "@/features/chat/components/ReasoningPanel";
import { useCopilotSuggestionsContext } from "./CopilotSuggestionsContext";
import type { Suggestion } from "@/features/chat/hooks/useCopilotSuggestions";

/**
 * Custom Assistant Message Component for Phase 3 + Phase 4 CopilotKit Integration
 *
 * Integrates ReasoningPanel to display thinking traces and reasoning metadata
 * from the multi-agent system (Primary, Log Analysis, Research agents).
 *
 * Phase 4: Re-enabled suggestion chips with smart click handling:
 * - Standard click: Inserts text into input (no send)
 * - Cmd/Ctrl+Enter: Inserts and sends immediately
 *
 * Props provided by CopilotKit:
 * - message: The message object with content
 * - isLoading: Whether the message is still being generated
 * - isGenerating: Whether the agent is actively generating
 * - rawData: Raw message data including metadata
 * - subComponent: Optional sub-component for generative UI
 */
export function CustomAssistantMessage(props: AssistantMessageProps) {
  const { message, isLoading, isGenerating, rawData, subComponent } = props;
  const {
    suggestions: contextSuggestions,
    onSuggestionSelected,
  } = useCopilotSuggestionsContext();

  // Extract metadata for reasoning traces
  const metadata = rawData?.metadata || (rawData as any)?.messageMetadata || {};

  // Extract thinking trace from various possible locations
  const thinkingTrace =
    metadata.thinking_trace ||
    metadata.thinkingTrace ||
    metadata.preface?.structured?.thinking_trace;

  // Extract latest thought for preview
  const latestThought =
    metadata.latest_thought ||
    metadata.preface?.latest_thought;

  // Extract suggestions for follow-up questions
  const fallbackMetadataSuggestions = Array.isArray(metadata.suggestions)
    ? (metadata.suggestions as string[])
    : Array.isArray(metadata.messageMetadata?.suggestions)
    ? (metadata.messageMetadata.suggestions as string[])
    : [];

  const displaySuggestions: Suggestion[] =
    contextSuggestions.length > 0
      ? contextSuggestions
      : fallbackMetadataSuggestions.map((suggestion, idx) => ({
          id: `metadata-${idx}`,
          text: suggestion,
          source: "backend" as const,
          priority: 3,
        }));

  // If subComponent provided (for generative UI), render it directly
  if (subComponent) {
    return (
      <div className="flex flex-col gap-2">
        {subComponent}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Main message content - use CopilotKit's Markdown renderer */}
      {message?.content && (
        <div className="text-[15px] whitespace-pre-wrap leading-relaxed">
          <Markdown content={message.content} />
        </div>
      )}

      {/* Loading indicator */}
      {isLoading && (
        <div className="text-xs text-muted-foreground italic">
          Generating response...
        </div>
      )}

      {/* Phase 4: Suggestion chips (re-enabled with smart click handling) */}
      {!isLoading && displaySuggestions.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {displaySuggestions.slice(0, 3).map((suggestion) => (
            <button
              key={suggestion.id}
              type="button"
              className="text-xs rounded-full px-3 py-1 border bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer"
              title="Click to insert; Cmd/Ctrl+Click to send immediately"
              onClick={(event) => {
                onSuggestionSelected?.(suggestion, {
                  sendImmediately: event.metaKey || event.ctrlKey,
                });
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  onSuggestionSelected?.(suggestion, {
                    sendImmediately: event.metaKey || event.ctrlKey,
                  });
                }
              }}
              disabled={!onSuggestionSelected}
            >
              {suggestion.text}
            </button>
          ))}
        </div>
      )}

      {/* Reasoning Panel - show thinking traces from agents */}
      {(thinkingTrace || latestThought) && (
        <ReasoningPanel
          trace={thinkingTrace}
          latestThought={latestThought}
          isStreaming={isGenerating || isLoading}
        />
      )}
    </div>
  );
}
