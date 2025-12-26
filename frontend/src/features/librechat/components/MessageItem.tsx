'use client';

import React, { useEffect, useRef, memo, useState, useCallback } from 'react';
import type { Message } from '@/services/ag-ui/client';
import { useAgent } from '@/features/librechat/AgentContext';
import { ThinkingPanel } from './ThinkingPanel';
import { ToolIndicator } from './ToolIndicator';
import { Copy, Check, RefreshCw, Pencil, X } from 'lucide-react';
import { AttachmentPreviewList } from '@/features/librechat/components/AttachmentPreview';
import { EnhancedMarkdown } from '@/features/librechat/components/EnhancedMarkdown';

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  onEditMessage?: (messageId: string, content: string) => void;
}

const LONG_MESSAGE_THRESHOLD = 500;
const THINK_BLOCK_REGEX = /:::(?:thinking|think)\s*([\s\S]*?):::/gi;
const THINK_TAG_REGEX = /<(?:thinking|think)>\s*([\s\S]*?)<\/(?:thinking|think)>/gi;

function extractThinking(content: string): { thinking: string | null; mainContent: string } {
  THINK_BLOCK_REGEX.lastIndex = 0;
  THINK_TAG_REGEX.lastIndex = 0;
  const blocks = [
    ...content.matchAll(THINK_BLOCK_REGEX),
    ...content.matchAll(THINK_TAG_REGEX),
  ];
  if (blocks.length > 0) {
    const thinking = blocks
      .map((match) => match[1]?.trim())
      .filter(Boolean)
      .join('\n\n');
    const mainContent = content
      .replace(THINK_BLOCK_REGEX, '')
      .replace(THINK_TAG_REGEX, '')
      .trim();
    return { thinking: thinking || null, mainContent };
  }
  return { thinking: null, mainContent: content };
}

const MessageAvatar = memo(function MessageAvatar({ role }: { role: 'user' | 'assistant' }) {
  if (role === 'user') {
    return (
      <div className="lc-avatar user" aria-hidden="true">
        <span>U</span>
      </div>
    );
  }
  return (
    <div className="lc-avatar assistant" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
      </svg>
    </div>
  );
});

interface MessageActionsProps {
  content: string;
  onRegenerate?: () => void;
  onEdit?: () => void;
}

const MessageActions = memo(function MessageActions({ content, onRegenerate, onEdit }: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      if (!navigator.clipboard) {
        const textArea = document.createElement('textarea');
        textArea.value = content;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        return;
      }

      await navigator.clipboard.writeText(content);
      setCopied(true);
      setCopyError(false);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
      setCopyError(true);
      setTimeout(() => setCopyError(false), 2000);
    }
  }, [content]);

  return (
    <div className="lc-message-actions" role="group" aria-label="Message actions">
      {onEdit && (
        <button className="lc-action-btn" onClick={onEdit} aria-label="Edit response">
          <Pencil size={14} />
        </button>
      )}
      <button
        className="lc-action-btn"
        onClick={handleCopy}
        aria-label={copied ? 'Copied!' : copyError ? 'Copy failed' : 'Copy message'}
      >
        {copied ? <Check size={14} style={{ color: 'var(--lc-accent)' }} /> : <Copy size={14} />}
      </button>
      {onRegenerate && (
        <button className="lc-action-btn" onClick={onRegenerate} aria-label="Regenerate response">
          <RefreshCw size={14} />
        </button>
      )}
    </div>
  );
});

function StreamingIndicator() {
  return (
    <span className="lc-streaming">
      <span className="lc-streaming-dot" />
      <span className="lc-streaming-dot" />
      <span className="lc-streaming-dot" />
      <span style={{ marginLeft: '8px', color: 'var(--lc-text-tertiary)', fontSize: '13px' }}>
        Processing...
      </span>
    </span>
  );
}

export const MessageItem = memo(function MessageItem({
  message,
  isLast,
  isStreaming,
  onEditMessage,
}: MessageItemProps) {
  const { thinkingTrace, activeTraceStepId, activeTools, messageAttachments, todos, toolEvidence } = useAgent();
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const [isUserExpanded, setIsUserExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Content comes directly from message (updated by context)
  const displayContent = typeof message.content === 'string' ? message.content : '';
  const { thinking, mainContent } = extractThinking(displayContent);

  const attachments = messageAttachments[message.id] || [];

  const isUserMessage = message.role === 'user';
  const isToolMessage = message.role === 'tool';
  const showStreaming = isLast && isStreaming && !isUserMessage && !mainContent;
  const shouldRegisterArtifacts = !(isLast && isStreaming);
  const showThinking = !isUserMessage && (thinking || (isLast && thinkingTrace.length > 0));
  const showToolIndicator = isLast && !isUserMessage && activeTools.length > 0;
  const roleName = isUserMessage ? 'You' : 'Agent Sparrow';
  const isMac = typeof navigator !== 'undefined' && navigator.platform.includes('Mac');

  const isLongUserMessage = isUserMessage && displayContent.length > LONG_MESSAGE_THRESHOLD;
  const userDisplayContent = isLongUserMessage && !isUserExpanded
    ? `${displayContent.slice(0, LONG_MESSAGE_THRESHOLD).trimEnd()}...`
    : displayContent;

  const handleStartEdit = useCallback(() => {
    setEditValue(mainContent || displayContent);
    setIsEditing(true);
  }, [mainContent, displayContent]);

  const handleCancelEdit = useCallback(() => {
    setIsEditing(false);
    setEditValue('');
  }, []);

  const handleSaveEdit = useCallback(() => {
    if (onEditMessage && editValue.trim()) {
      onEditMessage(message.id, editValue.trim());
    }
    setIsEditing(false);
    setEditValue('');
  }, [onEditMessage, message.id, editValue]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      handleCancelEdit();
    } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleSaveEdit();
    }
  }, [handleCancelEdit, handleSaveEdit]);

  const toggleUserExpanded = useCallback(() => {
    setIsUserExpanded((prev) => !prev);
  }, []);

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 400) + 'px';
    }
  }, [isEditing]);

  if (isToolMessage) {
    return null;
  }

  return (
    <article
      className={`lc-message-canvas ${message.role}`}
      aria-label={`Message from ${roleName}`}
    >
      <div className="lc-message-canvas-inner">
        <div className="lc-message-header">
          {isUserMessage ? (
            <div className="lc-user-bubble">
              <p className="lc-user-bubble-text">{userDisplayContent}</p>
              {isLongUserMessage && (
                <button
                  type="button"
                  className="lc-user-bubble-toggle"
                  onClick={toggleUserExpanded}
                  aria-expanded={isUserExpanded}
                >
                  {isUserExpanded ? 'Show Less' : 'Read More'}
                </button>
              )}
            </div>
          ) : (
            <div className="lc-agent-meta">
              <MessageAvatar role="assistant" />
              <span className="lc-agent-name">Agent Sparrow</span>
            </div>
          )}
        </div>

        {isUserMessage && attachments.length > 0 && (
          <div className="lc-user-attachments" aria-label="Attached files">
            <AttachmentPreviewList attachments={attachments} variant="stacked" />
          </div>
        )}

        {showThinking && (
          <div className="lc-thinking-wrapper">
            <ThinkingPanel
              thinking={thinking}
              traceSteps={isLast ? thinkingTrace : undefined}
              todos={isLast ? todos : undefined}
              toolEvidence={isLast ? toolEvidence : undefined}
              activeStepId={isLast ? activeTraceStepId : undefined}
              isStreaming={isLast && isStreaming}
            />
          </div>
        )}

        {showToolIndicator && <ToolIndicator tools={activeTools} />}

        {!isUserMessage && (
          <div className="lc-message-body">
            {isEditing ? (
              <div className="lc-edit-container">
                <textarea
                  ref={textareaRef}
                  className="lc-edit-textarea"
                  value={editValue}
                  onChange={(e) => {
                    setEditValue(e.target.value);
                    e.target.style.height = 'auto';
                    e.target.style.height = Math.min(e.target.scrollHeight, 400) + 'px';
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="Edit message..."
                  aria-label="Edit message content"
                />
                <div className="lc-edit-actions">
                  <button
                    className="lc-edit-btn lc-edit-btn-cancel"
                    onClick={handleCancelEdit}
                    aria-label="Cancel editing"
                  >
                    <X size={14} />
                    <span>Cancel</span>
                  </button>
                  <button
                    className="lc-edit-btn lc-edit-btn-save"
                    onClick={handleSaveEdit}
                    aria-label="Save changes"
                  >
                    <Check size={14} />
                    <span>Save</span>
                  </button>
                </div>
                <div className="lc-edit-hint">
                  Press Escape to cancel, {isMac ? 'Cmd' : 'Ctrl'}+Enter to save
                </div>
              </div>
            ) : showStreaming ? (
              <StreamingIndicator />
            ) : (
              <EnhancedMarkdown
                content={mainContent || displayContent}
                isLatestMessage={isLast && isStreaming}
                messageId={message.id}
                registerArtifacts={shouldRegisterArtifacts}
                variant="librechat"
              />
            )}
          </div>
        )}

        {!isUserMessage && mainContent && !isStreaming && !isEditing && (
          <MessageActions
            content={mainContent}
            onEdit={onEditMessage ? handleStartEdit : undefined}
          />
        )}
      </div>
    </article>
  );
});

export default MessageItem;
