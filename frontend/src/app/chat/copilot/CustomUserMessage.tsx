"use client";

import React from "react";
import { UserMessageProps, Markdown } from "@copilotkit/react-ui";

/**
 * Custom User Message Component for Phase 3 CopilotKit Integration
 *
 * Simple wrapper around CopilotKit's Markdown renderer for user messages.
 * Can be extended for custom styling or additional features.
 *
 * Props provided by CopilotKit:
 * - message: The message object with content
 * - rawData: Raw message data
 */
export function CustomUserMessage(props: UserMessageProps) {
  const { message } = props;

  return (
    <div className="text-[15px] whitespace-pre-wrap leading-relaxed">
      {message?.content && <Markdown content={message.content} />}
    </div>
  );
}
