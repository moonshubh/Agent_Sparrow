'use client';

import React from 'react';
import type { Message } from '@ag-ui/core';
import { ReasoningPanel } from '@/features/chat/components/ReasoningPanel';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/shared/lib/utils';

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
}

function MessageItem({ message, isLast, isStreaming }: MessageItemProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  // Skip system messages in UI
  if (isSystem) return null;

  // Extract metadata for reasoning traces
  const metadata = (message as any).metadata || {};
  const thinkingTrace = metadata.thinking_trace || metadata.thinkingTrace;
  const latestThought = metadata.latest_thought;

  // Format message content
  const content = typeof message.content === 'string'
    ? message.content
    : JSON.stringify(message.content, null, 2);

  return (
    <div
      className={cn(
        'flex',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div
        className={cn(
          'max-w-[70%] rounded-lg px-4 py-3',
          isUser
            ? 'bg-slate-700 text-white'
            : 'bg-white border border-gray-200 text-slate-800'
        )}
      >
        {/* Message role indicator */}
        <div className={cn(
          'text-xs font-medium mb-2',
          isUser ? 'text-slate-300' : 'text-slate-500'
        )}>
          {isUser ? 'You' : 'Assistant'}
        </div>

        {/* Message content with markdown rendering */}
        <div className={cn(
          'prose prose-sm max-w-none',
          isUser && 'prose-invert'
        )}>
          <ReactMarkdown
            components={{
              code({ node, inline, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                return !inline && match ? (
                  <SyntaxHighlighter
                    {...props}
                    style={vscDarkPlus}
                    language={match[1]}
                    PreTag="div"
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                ) : (
                  <code
                    {...props}
                    className={cn(
                      className,
                      'bg-gray-100 px-1 py-0.5 rounded text-sm',
                      isUser && 'bg-slate-600'
                    )}
                  >
                    {children}
                  </code>
                );
              },
            }}
          >
            {content}
          </ReactMarkdown>
        </div>

        {/* Streaming indicator */}
        {isLast && isStreaming && !isUser && (
          <div className="flex items-center gap-2 mt-3 text-xs text-slate-500">
            <div className="flex gap-1">
              <span className="animate-bounce animation-delay-0">●</span>
              <span className="animate-bounce animation-delay-200">●</span>
              <span className="animate-bounce animation-delay-400">●</span>
            </div>
            <span>Generating response...</span>
          </div>
        )}
      </div>

      {/* Reasoning Panel (for assistant messages) */}
      {!isUser && (thinkingTrace || latestThought) && (
        <div className="ml-4">
          <ReasoningPanel
            trace={thinkingTrace}
            latestThought={latestThought}
            isStreaming={isLast && isStreaming}
          />
        </div>
      )}
    </div>
  );
}

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
}

export function MessageList({ messages, isStreaming }: MessageListProps) {
  // Filter out system messages and empty messages
  const visibleMessages = messages.filter(
    m => m.role !== 'system' && m.content !== ''
  );

  if (visibleMessages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center py-12">
        <div className="text-4xl mb-4">👋</div>
        <h2 className="text-xl font-semibold text-slate-700 mb-2">
          Welcome to Agent Sparrow
        </h2>
        <p className="text-slate-500 max-w-md">
          Start a conversation by typing a message below. I&apos;m here to help with your questions and tasks.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {visibleMessages.map((message, idx) => (
        <MessageItem
          key={message.id ?? idx}
          message={message}
          isLast={idx === visibleMessages.length - 1}
          isStreaming={isStreaming}
        />
      ))}
    </div>
  );
}

// Add animation delay styles
if (typeof window !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes bounce {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-4px); }
    }
    .animation-delay-0 { animation-delay: 0ms; }
    .animation-delay-200 { animation-delay: 200ms; }
    .animation-delay-400 { animation-delay: 400ms; }
  `;
  document.head.appendChild(style);
}