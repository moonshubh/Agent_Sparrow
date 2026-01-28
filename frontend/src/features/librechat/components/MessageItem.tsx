'use client';

import React, { memo, useState, useCallback, useEffect, useRef } from 'react';
import dynamic from 'next/dynamic';
import type { Message } from '@/services/ag-ui/client';
import { useAgent } from '@/features/librechat/AgentContext';
import { ThinkingPanel } from './ThinkingPanel';
import { ResearchProgress } from './ResearchProgress';
import { ToolIndicator } from './ToolIndicator';
import { Copy, Check, RefreshCw, Pencil } from 'lucide-react';
import { AttachmentPreviewList } from '@/features/librechat/components/AttachmentPreview';
import { EnhancedMarkdown } from '@/features/librechat/components/EnhancedMarkdown';
import { FeedbackPopover } from './FeedbackPopover';
import { LogAnalysisNotesDropdown } from './log-analysis-notes-dropdown';
import { extractJsonObjects, stripInternalSearchPayloads } from '@/features/librechat/utils';

const TipTapEditor = dynamic(
  () => import('./tiptap/TipTapEditor').then((mod) => mod.TipTapEditor),
  { ssr: false }
);

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  sessionId?: string;
  onEditMessage?: (messageId: string, content: string) => void;
  onRegenerate?: () => void;
}

const LONG_MESSAGE_THRESHOLD = 500;
const THINK_BLOCK_REGEX = /:::\s*(?:thinking|think|analysis|reasoning)\s*([\s\S]*?)\s*:::/gi;
const THINK_TAG_REGEX = /<\s*(?:thinking|think|analysis|reasoning)\s*>\s*([\s\S]*?)\s*<\/\s*(?:thinking|think|analysis|reasoning)\s*>/gi;
const THINK_FENCE_REGEX = /```(?:thinking|think|analysis|reasoning)\s*([\s\S]*?)```/gi;
const THINK_ORPHAN_START_REGEX = /:::\s*(?:thinking|think|analysis|reasoning)\s*/i;
const THINK_ORPHAN_CLOSE_REGEX = /(?:^|\n)\s*:::\s*(?=\n|$)/g;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

function extractThinking(
  content: string
): { thinking: string | null; mainContent: string; hadThinking: boolean } {
  THINK_BLOCK_REGEX.lastIndex = 0;
  THINK_TAG_REGEX.lastIndex = 0;
  THINK_FENCE_REGEX.lastIndex = 0;
  const blocks = [
    ...content.matchAll(THINK_BLOCK_REGEX),
    ...content.matchAll(THINK_TAG_REGEX),
    ...content.matchAll(THINK_FENCE_REGEX),
  ];

  const thinkingParts = blocks
    .map((match) => match[1]?.trim())
    .filter(Boolean);

  let mainContent = content
    .replace(THINK_BLOCK_REGEX, '')
    .replace(THINK_TAG_REGEX, '')
    .replace(THINK_FENCE_REGEX, '');

  const orphanMatch = mainContent.match(THINK_ORPHAN_START_REGEX);
  if (orphanMatch?.index !== undefined) {
    const startIndex = orphanMatch.index;
    const before = mainContent.slice(0, startIndex);
    const after = mainContent.slice(startIndex + orphanMatch[0].length);
    if (after.trim()) {
      thinkingParts.push(after.trim());
    }
    mainContent = before;
  }

  const hadThinking = thinkingParts.length > 0 || mainContent !== content;

  if (hadThinking) {
    mainContent = mainContent.replace(THINK_ORPHAN_CLOSE_REGEX, '\n').trim();
  }

  return {
    thinking: thinkingParts.length > 0 ? thinkingParts.join('\n\n') : null,
    mainContent,
    hadThinking,
  };
}

type ParsedLogDiagnoserNote = {
  file_name?: string;
  internal_notes?: string;
  confidence?: number;
  evidence?: string[];
  recommended_actions?: string[];
  open_questions?: string[];
};

const looksLikeLogDiagnoserPayload = (text: string): boolean => {
  const sample = text.slice(0, 20000);
  return sample.includes('"customer_ready"') && sample.includes('"internal_notes"') && sample.includes('"file_name"');
};

const parseLogDiagnoserPayload = (
  text: string,
  metadata?: Record<string, unknown>
): { answer: string; notes: Record<string, ParsedLogDiagnoserNote> } | null => {
  if (!looksLikeLogDiagnoserPayload(text)) return null;

  const candidates = extractJsonObjects(text);
  if (!candidates.length) return null;

  const parsed = candidates
    .map((raw) => {
      try {
        const obj = JSON.parse(raw);
        return obj && typeof obj === 'object' ? (obj as Record<string, unknown>) : null;
      } catch {
        return null;
      }
    })
    .filter((obj): obj is Record<string, unknown> => Boolean(obj));

  const notes: Record<string, ParsedLogDiagnoserNote> = {};
  const recommendedActions: string[] = [];
  const customerReadyBlocks: Array<{
    fileName?: string;
    content: string;
    summary?: string;
  }> = [];

  parsed.forEach((obj, idx) => {
    const fileName = typeof obj.file_name === 'string' ? obj.file_name : '';
    const key = fileName || `log-${idx + 1}`;

    const evidence = Array.isArray(obj.evidence) ? obj.evidence.filter((v): v is string => typeof v === 'string') : undefined;
    const actions = Array.isArray(obj.recommended_actions)
      ? obj.recommended_actions.filter((v): v is string => typeof v === 'string')
      : undefined;
    const questions = Array.isArray(obj.open_questions)
      ? obj.open_questions.filter((v): v is string => typeof v === 'string')
      : undefined;

    const customerReady =
      typeof obj.customer_ready === 'string' && obj.customer_ready.trim()
        ? obj.customer_ready.trim()
        : '';
    const summaryRaw =
      typeof obj.overall_summary === 'string'
        ? obj.overall_summary
        : typeof obj.summary === 'string'
          ? obj.summary
          : '';
    const summary = summaryRaw.trim();

    if (actions?.length) {
      actions.forEach((action) => {
        if (!recommendedActions.includes(action)) recommendedActions.push(action);
      });
    }

    const confidenceRaw = obj.confidence;
    const confidence = typeof confidenceRaw === 'number' && Number.isFinite(confidenceRaw) ? confidenceRaw : undefined;

    notes[key] = {
      file_name: fileName || undefined,
      internal_notes: typeof obj.internal_notes === 'string' ? obj.internal_notes : undefined,
      confidence,
      evidence,
      recommended_actions: actions,
      open_questions: questions,
    };

    if (customerReady) {
      customerReadyBlocks.push({
        fileName: fileName || undefined,
        content: customerReady,
        summary: summary || (evidence?.[0] ?? undefined),
      });
    }
  });

  const artifactTitle = (() => {
    const artifacts = metadata?.artifacts;
    if (!Array.isArray(artifacts) || artifacts.length === 0) return null;
    const first = artifacts[0];
    if (!isRecord(first)) return null;
    const title = first.title;
    return typeof title === 'string' && title.trim() ? title.trim() : null;
  })();

  if (customerReadyBlocks.length > 0) {
    const primary = customerReadyBlocks[0];
    let answer = primary.content;
    if (customerReadyBlocks.length > 1) {
      const extraLines: string[] = [];
      extraLines.push('', '## Additional Files');
      customerReadyBlocks.slice(1).forEach((block, index) => {
        const label = block.fileName || `Log file ${index + 2}`;
        const detail = block.summary || 'Additional log analyzed.';
        extraLines.push(`- **${label}:** ${detail}`);
      });
      answer = `${answer}\n${extraLines.join('\n')}`;
    }
    return { answer, notes };
  }

  const lines: string[] = [];
  lines.push('Thanks for the log file. Here is a focused summary and next steps.');
  lines.push('', '## The Diagnosis');
  lines.push(`- Reviewed ${parsed.length} attached log file${parsed.length === 1 ? '' : 's'}.`);
  if (artifactTitle) {
    lines.push(`- Created artifact: ${artifactTitle}.`);
  }

  if (recommendedActions.length) {
    lines.push('', '## How to Fix It');
    recommendedActions.slice(0, 12).forEach((action, index) => {
      lines.push(`${index + 1}. ${action}`);
    });
  } else {
    lines.push('', '## Next Steps');
    lines.push('Open Technical details for per-file diagnostics.');
  }

  return { answer: lines.join('\n'), notes };
};

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
  messageId: string;
  sessionId?: string;
  onRegenerate?: () => void;
  onEdit?: () => void;
}

const MessageActions = memo(function MessageActions({ content, messageId, sessionId, onRegenerate, onEdit }: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup timeout on unmount to prevent memory leak
  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async () => {
    // Clear any existing timeout
    if (copyTimeoutRef.current) {
      clearTimeout(copyTimeoutRef.current);
    }

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
        copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
        return;
      }

      await navigator.clipboard.writeText(content);
      setCopied(true);
      setCopyError(false);
      copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
      setCopyError(true);
      copyTimeoutRef.current = setTimeout(() => setCopyError(false), 2000);
    }
  }, [content]);

  return (
    <div className="lc-message-actions" role="group" aria-label="Message actions">
      <FeedbackPopover messageId={messageId} sessionId={sessionId} />
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
  sessionId,
  onEditMessage,
  onRegenerate,
}: MessageItemProps) {
  const {
    thinkingTrace,
    activeTraceStepId,
    activeTools,
    messageAttachments,
    todos,
    toolEvidence,
    researchProgress,
    researchStatus,
    isResearching,
  } = useAgent();
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isUserExpanded, setIsUserExpanded] = useState(false);

  const attachments = messageAttachments[message.id] || [];
  const metadata = isRecord(message.metadata) ? message.metadata : undefined;
  const isUserMessage = message.role === 'user';
  const isToolMessage = message.role === 'tool';

  const rawContent = typeof message.content === 'string' ? message.content : '';
  const attachmentsOnly =
    metadata?.attachments_only === true ||
    (!rawContent.trim() && attachments.length > 0);
  const attachmentLabel = attachments.length === 1 ? 'Attachment' : `${attachments.length} attachments`;
  const logAnalysisNotes = metadata?.logAnalysisNotes ?? metadata?.log_analysis_notes;

  // Content comes directly from message (updated by context)
  const baseContent = attachmentsOnly && attachments.length > 0 ? attachmentLabel : rawContent;
  const displayContent = isUserMessage ? baseContent : stripInternalSearchPayloads(baseContent);
  const { thinking, mainContent, hadThinking } = extractThinking(displayContent);
  const showStreaming = isLast && isStreaming && !isUserMessage && !mainContent;
  const shouldRegisterArtifacts = !(isLast && isStreaming);
  const showThinking = !isUserMessage && (thinking || (isLast && thinkingTrace.length > 0));
  const showResearchProgress = isLast && !isUserMessage && (isResearching || researchStatus !== 'idle');
  const showToolIndicator = isLast && !isUserMessage && activeTools.length > 0;
  const roleName = isUserMessage ? 'You' : 'Agent Sparrow';

  const derivedLogPayload = !isUserMessage ? parseLogDiagnoserPayload(rawContent, metadata) : null;
  const looksLikeLogPayload = !isUserMessage && looksLikeLogDiagnoserPayload(rawContent);
  const artifactTitle = (() => {
    const artifacts = metadata?.artifacts;
    if (!Array.isArray(artifacts) || artifacts.length === 0) return null;
    const first = artifacts[0];
    if (!isRecord(first)) return null;
    const title = first.title;
    return typeof title === 'string' && title.trim() ? title.trim() : null;
  })();
  const fallbackNotes = (() => {
    if (!looksLikeLogPayload) return null;
    if (logAnalysisNotes || derivedLogPayload?.notes) return null;
    const payload = rawContent.trim();
    if (!payload) return null;
    return {
      raw_payload: {
        file_name: 'Raw log analysis payload',
        internal_notes: payload,
      },
    } satisfies Record<string, ParsedLogDiagnoserNote>;
  })();
  const markdownContent = (() => {
    if (derivedLogPayload) return derivedLogPayload.answer;
    if (looksLikeLogPayload) {
      return artifactTitle
        ? `Created artifact: ${artifactTitle}.`
        : 'Log analysis complete. Open Technical details for per-file diagnostics.';
    }
    return hadThinking ? mainContent : displayContent;
  })();
  const notesForDropdown = logAnalysisNotes ?? derivedLogPayload?.notes ?? fallbackNotes;

  const isLongUserMessage = isUserMessage && displayContent.length > LONG_MESSAGE_THRESHOLD;
  const userDisplayContent = isLongUserMessage && !isUserExpanded
    ? `${displayContent.slice(0, LONG_MESSAGE_THRESHOLD).trimEnd()}...`
    : displayContent;

  const handleStartEdit = useCallback(() => {
    setEditContent(mainContent || displayContent);
    setIsEditing(true);
  }, [mainContent, displayContent]);

  const handleSaveEdit = useCallback(async (markdown: string) => {
    const trimmed = markdown.trim();
    if (onEditMessage && trimmed) {
      await onEditMessage(message.id, trimmed);
    }
  }, [onEditMessage, message.id]);

  const handleExitEdit = useCallback(() => {
    setIsEditing(false);
    setEditContent('');
  }, []);

  const toggleUserExpanded = useCallback(() => {
    setIsUserExpanded((prev) => !prev);
  }, []);

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
            {showResearchProgress && (
              <ResearchProgress
                progress={researchProgress}
                status={researchStatus}
                visible={showResearchProgress}
                attached
              />
            )}
          </div>
        )}

        {!showThinking && showResearchProgress && (
          <ResearchProgress
            progress={researchProgress}
            status={researchStatus}
            visible={showResearchProgress}
          />
        )}

        {showToolIndicator && <ToolIndicator tools={activeTools} />}

        {!isUserMessage && (
          <div
            className="lc-message-body"
            onDoubleClick={!isStreaming && onEditMessage ? handleStartEdit : undefined}
          >
            {isEditing ? (
              <TipTapEditor
                initialContent={editContent}
                onSave={handleSaveEdit}
                onExit={handleExitEdit}
                onCancel={handleExitEdit}
                autoSave
                enableMath
                enableTables
                enableTaskList
                enableImages
                placeholder="Edit message..."
              />
            ) : showStreaming ? (
              <StreamingIndicator />
            ) : (
              <>
                <EnhancedMarkdown
                  content={markdownContent}
                  isLatestMessage={isLast && isStreaming}
                  messageId={message.id}
                  registerArtifacts={shouldRegisterArtifacts}
                  variant="librechat"
                />
                {notesForDropdown ? <LogAnalysisNotesDropdown notes={notesForDropdown} /> : null}
              </>
            )}
          </div>
        )}

        {!isUserMessage && mainContent && !isStreaming && !isEditing && (
          <MessageActions
            content={mainContent}
            messageId={message.id}
            sessionId={sessionId}
            onEdit={onEditMessage ? handleStartEdit : undefined}
            onRegenerate={onRegenerate}
          />
        )}
      </div>
    </article>
  );
});

export default MessageItem;
