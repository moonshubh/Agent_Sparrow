'use client';

import React from 'react';
import type { Message } from '@ag-ui/core';
import type { AgentChoice } from '@/features/ag-ui/hooks/useAgentSelection';
import { EnhancedReasoningPanel } from '@/features/ag-ui/reasoning/EnhancedReasoningPanel';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/shared/lib/utils';
import { User, Clock } from 'lucide-react';

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  agentType?: AgentChoice;
}

function MessageItem({ message, isLast, isStreaming, agentType }: MessageItemProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isTool = message.role === 'tool';

  // Skip system messages in UI
  if (isSystem) return null;

  // Tool messages are now surfaced via the agentic timeline / sidebar, not inline
  if (isTool) return null;

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
        'flex gap-4 mb-6 animate-in fade-in slide-in-from-bottom-2 duration-500',
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

        <div
          className={cn(
            'text-academia-base leading-relaxed',
            isUser
              ? 'bg-chat-user-bg text-chat-user-text bubble-user px-5 py-3.5 shadow-academia-sm'
              : 'bg-transparent text-foreground px-0 py-0' // Completely transparent, no padding for agent
          )}
        >
          <div className={cn(
            'prose prose-sm max-w-none prose-invert',
            !isUser && 'prose-headings:text-foreground prose-p:text-foreground/90 prose-strong:text-foreground prose-code:text-terracotta-300'
          )}>
            <ReactMarkdown
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '');
                  return !inline && match ? (
                    <div className="rounded-organic overflow-hidden my-4 border border-border shadow-academia-sm">
                      <div className="bg-secondary px-4 py-2 text-xs text-muted-foreground border-b border-border flex justify-between font-mono">
                        <span>{match[1]}</span>
                      </div>
                      <SyntaxHighlighter
                        {...props}
                        style={vscDarkPlus}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ margin: 0, borderRadius: 0, background: 'hsl(var(--code-block-bg))' }}
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    </div>
                  ) : (
                    <code
                      {...props}
                      className={cn(
                        className,
                        'bg-secondary px-1.5 py-0.5 rounded-organic-sm text-xs font-mono text-terracotta-300',
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
        />
      ))}
    </div>
  );
}
