'use client';

import React, { useEffect, useRef, memo, useCallback } from 'react';
import type { Message } from '@/services/ag-ui/client';
import { MessageItem } from './MessageItem';
import { useAgent } from '../AgentContext';
import { sessionsAPI } from '@/services/api/endpoints/sessions';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  sessionId?: string;
}

function stableMessageKey(message: Message, index: number): string {
  if (message.id) return message.id;
  if (process.env.NODE_ENV !== 'production') {
    console.warn('[LibreChat] Message missing id; falling back to content hash', message);
  }
  const content = typeof message.content === 'string' ? message.content : JSON.stringify(message.content ?? '');
  const base = `${message.role}|${message.name || ''}|${message.tool_call_id || ''}|${content}|${index}`;
  let hash = 0;
  for (let i = 0; i < base.length; i += 1) {
    hash = (hash * 31 + base.charCodeAt(i)) >>> 0;
  }
  return `msg-${hash.toString(16)}`;
}

export const MessageList = memo(function MessageList({ messages, isStreaming, sessionId }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(messages.length);
  const { updateMessageContent, regenerateLastResponse } = useAgent();

  // Handle message edit - updates context immediately and persists to API
  const handleEditMessage = useCallback(async (messageId: string, content: string) => {
    // Update in context immediately for responsive UI
    updateMessageContent(messageId, content);

    // Persist to backend if we have a session
    if (sessionId) {
      try {
        await sessionsAPI.updateMessage(sessionId, messageId, content);
      } catch (error) {
        console.error('[MessageList] Failed to persist message edit:', error);
        // Note: We could add a toast notification here in the future
      }
    }
  }, [sessionId, updateMessageContent]);

  // Auto-scroll only when message count changes (not on every content update)
  useEffect(() => {
    const lengthChanged = messages.length !== prevLengthRef.current;
    prevLengthRef.current = messages.length;

    if (lengthChanged) {
      // Use instant scroll during streaming for better UX, smooth otherwise
      messagesEndRef.current?.scrollIntoView({
        behavior: isStreaming ? 'auto' : 'smooth',
      });
    }
  }, [messages.length, isStreaming]);

  return (
    <div className="lc-messages" role="log" aria-label="Chat messages" aria-live="polite">
      <div className="lc-messages-inner">
        {messages.map((message, index) => {
          const isLast = index === messages.length - 1;
          const isLastAssistant = isLast && message.role === 'assistant';
          return (
            <MessageItem
              key={stableMessageKey(message, index)}
              message={message}
              isLast={isLast}
              isStreaming={isStreaming}
              sessionId={sessionId}
              onEditMessage={handleEditMessage}
              onRegenerate={isLastAssistant && !isStreaming ? regenerateLastResponse : undefined}
            />
          );
        })}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>
    </div>
  );
});

export default MessageList;
