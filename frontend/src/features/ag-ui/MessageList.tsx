'use client';

import React, { useMemo } from 'react';
import type { Message } from '@ag-ui/core';
import type { AgentChoice } from '@/features/ag-ui/hooks/useAgentSelection';
import type { AttachmentInput } from '@/services/ag-ui/types';
import { EnhancedReasoningPanel } from '@/features/ag-ui/reasoning/EnhancedReasoningPanel';
import { AttachmentPreviewList } from './components/AttachmentPreview';
import { EnhancedMarkdown } from './components/EnhancedMarkdown';
import { InlineThinking } from './components/InlineThinking';
import { useAgent } from './AgentContext';
import { cn } from '@/shared/lib/utils';
import { User, Clock } from 'lucide-react';

/**
 * Parse thinking content from message text.
 * Extracts :::thinking blocks and separates them from regular content.
 * 
 * Pattern: :::thinking\n{content}\n:::\n{response}
 * 
 * @param text - The full message content
 * @returns Object with thinkingContent and regularContent
 */
function parseThinkingContent(text: string | undefined | null): {
  thinkingContent: string;
  regularContent: string;
} {
  // Handle null/undefined input gracefully
  if (!text) {
    return { thinkingContent: '', regularContent: '' };
  }

  // Match :::thinking ... ::: blocks (with or without newlines)
  const thinkingMatch = text.match(/:::thinking\s*([\s\S]*?)\s*:::/);
  
  if (thinkingMatch) {
    const thinkingContent = thinkingMatch[1].trim();
    const regularContent = text.replace(/:::thinking\s*[\s\S]*?\s*:::/, '').trim();
    return { thinkingContent, regularContent };
  }
  
  return { thinkingContent: '', regularContent: text };
}

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  agentType?: AgentChoice;
  attachments?: AttachmentInput[];
  /** Message index for deterministic ID generation (Issue #4: hydration stability) */
  messageIndex: number;
}

function MessageItem({ message, isLast, isStreaming, agentType, attachments = [], messageIndex }: MessageItemProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isTool = message.role === 'tool';

  // Skip system messages in UI
  if (isSystem) return null;

  // Tool messages are now surfaced via the agentic timeline / sidebar, not inline
  if (isTool) return null;

  // Extract metadata for reasoning traces (attachments now passed as prop from context)
  const metadata = (message as any).metadata || {};
  const thinkingTrace = metadata.thinking_trace || metadata.thinkingTrace;
  const latestThought = metadata.latest_thought;

  // Format message content
  const rawContent = typeof message.content === 'string'
    ? message.content
    : JSON.stringify(message.content, null, 2);

  // Parse thinking content for assistant messages (:::thinking blocks)
  const { thinkingContent, regularContent } = useMemo(() => {
    if (isUser) {
      return { thinkingContent: '', regularContent: rawContent };
    }
    return parseThinkingContent(rawContent);
  }, [rawContent, isUser]);

  return (
    <div
      className={cn(
        'flex gap-4 mb-6 animate-in fade-in slide-in-from-bottom-2 duration-500 items-start',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* User Avatar (Only for user) - Terracotta warmth */}
      {isUser && (
        <div
          className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-academia-sm bg-gradient-to-br from-terracotta-500 to-terracotta-600"
          aria-label="User avatar"
        >
          <User className="w-4 h-4 text-cream-50" />
        </div>
      )}

      {/* Message Content */}
      <div className={cn(
        "flex flex-col max-w-[85%]",
        isUser ? "items-end" : "items-start"
      )}>
        {/* Label (Only for user) */}
        {isUser && (
          <div className="text-xs font-medium mb-1 opacity-50 text-right mr-1">
            You
          </div>
        )}

        {/* User Attachments - Display stacked thumbnails ABOVE message content */}
        {isUser && attachments.length > 0 && (
          <div className="mb-2 flex justify-end">
            <AttachmentPreviewList
              attachments={attachments}
              variant="stacked"
            />
          </div>
        )}

        <div
          className={cn(
            'text-[17px] leading-relaxed',
            isUser
              ? 'bg-chat-user-bg text-chat-user-text bubble-user px-5 py-3.5 shadow-academia-sm text-left'
              : 'bg-transparent text-foreground px-0 py-0' // Completely transparent, no padding for agent
          )}
        >
          {/* Inline Thinking - Display for assistant messages with :::thinking blocks */}
          {!isUser && thinkingContent && (
            <InlineThinking thinkingText={thinkingContent} />
          )}

          {/* Main message content with enhanced markdown */}
          <div className={cn(
            'prose max-w-none prose-invert [&>*]:text-[17px]',
            !isUser && 'prose-headings:text-foreground prose-p:text-foreground/90 prose-strong:text-foreground prose-code:text-terracotta-300'
          )}>
            <EnhancedMarkdown
              content={regularContent}
              isLatestMessage={isLast && isStreaming}
              messageId={message.id || `msg-${messageIndex}`}
            />
          </div>

          {/* Streaming indicator - Warm gold glow */}
          {isLast && isStreaming && !isUser && (
            <div className="flex items-center gap-2 mt-2 text-xs text-gold-400/90 thinking-indicator">
              <div className="flex gap-1">
                <span className="animate-bounce animation-delay-0 w-1.5 h-1.5 bg-current rounded-full"></span>
                <span className="animate-bounce animation-delay-200 w-1.5 h-1.5 bg-current rounded-full"></span>
                <span className="animate-bounce animation-delay-400 w-1.5 h-1.5 bg-current rounded-full"></span>
              </div>
              {agentType === 'log_analysis' ? (
                <span className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  Deep analysis in progress (takes longer for thorough results)
                </span>
              ) : (
                <span>Thinking...</span>
              )}
            </div>
          )}
        </div>

        {/* Reasoning Panel (for assistant messages) */}
        {!isUser && (thinkingTrace || latestThought) && (
          <div className="mt-4 w-full">
            <EnhancedReasoningPanel
              phases={[]}
              currentPhase={isStreaming ? 'responding' : undefined}
              isExpanded={true}
              statusMessage={latestThought || 'Thinking...'}
            />
          </div>
        )}
      </div>
    </div>
  );
}

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  agentType?: AgentChoice;
}

export function MessageList({ messages, isStreaming, agentType }: MessageListProps) {
  // Get attachments from context (stored separately from messages to avoid backend validation errors)
  const { messageAttachments } = useAgent();

  // Filter out system messages and empty messages
  const visibleMessages = messages.filter(
    m => m.role !== 'system' && m.content !== ''
  );

  if (visibleMessages.length === 0) {
    return null; // Handled by ChatContainer empty state
  }

  return (
    <div className="space-y-2 py-4">
      {visibleMessages.map((message, idx) => (
        <MessageItem
          key={message.id ?? idx}
          message={message}
          isLast={idx === visibleMessages.length - 1}
          isStreaming={isStreaming}
          agentType={agentType}
          attachments={message.id ? messageAttachments[message.id] : undefined}
          messageIndex={idx}
        />
      ))}
    </div>
  );
}
