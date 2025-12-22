'use client';

import React, { useEffect, useRef, memo, useState, useCallback } from 'react';
import type { Message } from '@/services/ag-ui/client';
import { MessageItem } from './MessageItem';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
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

export const MessageList = memo(function MessageList({ messages, isStreaming }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(messages.length);
  const [editedMessages, setEditedMessages] = useState<Record<string, string>>({});

  // Handle message edit
  const handleEditMessage = useCallback((messageId: string, content: string) => {
    setEditedMessages((prev) => ({
      ...prev,
      [messageId]: content,
    }));
  }, []);

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
        {messages.map((message, index) => (
          <MessageItem
            key={stableMessageKey(message, index)}
            message={message}
            isLast={index === messages.length - 1}
            isStreaming={isStreaming}
            editedContent={editedMessages[message.id]}
            onEditMessage={handleEditMessage}
          />
        ))}
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>
    </div>
  );
});

export default MessageList;
