'use client';

import React, { useMemo } from 'react';
import type { Message } from '@ag-ui/core';
import type { AgentChoice } from '@/features/ag-ui/hooks/useAgentSelection';
import type { AttachmentInput } from '@/services/ag-ui/types';
import { EnhancedReasoningPanel } from '@/features/ag-ui/reasoning/EnhancedReasoningPanel';
import { AttachmentPreviewList } from './components/AttachmentPreview';
import { EnhancedMarkdown } from './components/EnhancedMarkdown';
import { InlineThinking } from './components/InlineThinking';
import { SearchImageGrid } from './components/SearchImageGrid';
import type { SearchImage } from './components/SearchImageDialog';
import { useAgent } from './AgentContext';
import { cn } from '@/shared/lib/utils';
import { User, Clock } from 'lucide-react';

/**
 * Parse a potentially nested/wrapped output value into a usable object.
 * Handles various formats:
 * - Direct object/dict
 * - JSON string
 * - String with "content='{...}'" wrapper (from LangChain tool outputs)
 */
function parseToolOutput(output: unknown): Record<string, unknown> {
  if (!output) return {};

  // Already an object
  if (typeof output === 'object' && output !== null && !Array.isArray(output)) {
    return output as Record<string, unknown>;
  }

  // Not a string - can't parse further
  if (typeof output !== 'string') return {};

  let text = output.trim();

  // Handle "content='{...}'" wrapper format from LangChain
  // The format is: content='{"key": "value", ...}'
  // We need to extract the JSON between the quotes after content=
  const startsWithContentSingle = text.startsWith("content='");
  const startsWithContentDouble = text.startsWith('content="');

  if (process.env.NODE_ENV === 'development') {
    console.debug('[parseToolOutput] Input check:', {
      textLength: text.length,
      textStart: text.slice(0, 50),
      startsWithContentSingle,
      startsWithContentDouble,
    });
  }

  if (startsWithContentSingle || startsWithContentDouble) {
    const quoteChar = text[8]; // The quote character used
    const startPos = 9; // Position after "content='"

    // Find the JSON start (first { or [)
    const jsonStartBrace = text.indexOf('{', startPos);
    const jsonStartBracket = text.indexOf('[', startPos);
    const jsonStart = jsonStartBrace >= 0 && jsonStartBracket >= 0
      ? Math.min(jsonStartBrace, jsonStartBracket)
      : jsonStartBrace >= 0 ? jsonStartBrace : jsonStartBracket;

    if (jsonStart >= 0) {
      // Find the matching end by counting brackets
      const isArray = text[jsonStart] === '[';
      const openChar = isArray ? '[' : '{';
      const closeChar = isArray ? ']' : '}';
      let depth = 0;
      let inString = false;
      let escaped = false;
      let jsonEnd = -1;

      for (let i = jsonStart; i < text.length; i++) {
        const char = text[i];

        if (escaped) {
          escaped = false;
          continue;
        }

        if (char === '\\') {
          escaped = true;
          continue;
        }

        if (char === '"' && !escaped) {
          inString = !inString;
          continue;
        }

        if (!inString) {
          if (char === openChar) depth++;
          if (char === closeChar) {
            depth--;
            if (depth === 0) {
              jsonEnd = i;
              break;
            }
          }
        }
      }

      if (process.env.NODE_ENV === 'development') {
        console.debug('[parseToolOutput] Bracket matching result:', {
          jsonStart,
          jsonEnd,
          openChar,
          closeChar,
          foundMatch: jsonEnd > jsonStart,
        });
      }

      if (jsonEnd > jsonStart) {
        text = text.slice(jsonStart, jsonEnd + 1);
        // Unescape Python-style string escapes when wrapper used single quotes
        // LangChain/Python outputs escape both single quotes AND backslashes
        if (quoteChar === "'") {
          // First, handle escaped backslashes (\\\\) -> (\\)
          // Then handle escaped single quotes (\') -> (')
          // Note: Python str(dict) escapes ' as \' inside single-quoted strings
          text = text.replace(/\\'/g, "'");
        }
        // Handle double-escaped sequences that Python may produce
        // e.g., \\n should be \n (actual newline escape in JSON)
        // But \\\\ should stay as \\ (escaped backslash in JSON)
        // Actually, the issue is Python's repr() may escape things differently
        // Let's try a more targeted approach: replace \\x sequences with \x
        // This handles cases where Python double-escapes JSON escapes
        text = text.replace(/\\\\(["\\/bfnrtu])/g, '\\$1');

        if (process.env.NODE_ENV === 'development') {
          console.debug('[parseToolOutput] Extracted JSON preview:', text.slice(0, 200));
          // Show the exact bytes around where errors might occur
          const problematicChars = text.match(/\\[^"\\/bfnrtu]/g);
          if (problematicChars) {
            console.debug('[parseToolOutput] Potentially problematic escape sequences:', problematicChars.slice(0, 10));
          }
        }
      }
    }
  }

  // Try parsing as JSON
  if (process.env.NODE_ENV === 'development') {
    console.debug('[parseToolOutput] Pre-parse check:', {
      startsWithBrace: text.startsWith('{'),
      endsWithBrace: text.endsWith('}'),
      startsWithBracket: text.startsWith('['),
      endsWithBracket: text.endsWith(']'),
      textLength: text.length,
      textStart: text.slice(0, 50),
      textEnd: text.slice(-50),
    });
  }
  if ((text.startsWith('{') && text.endsWith('}')) ||
    (text.startsWith('[') && text.endsWith(']'))) {
    try {
      const parsed = JSON.parse(text);
      if (process.env.NODE_ENV === 'development') {
        console.debug('[parseToolOutput] JSON.parse succeeded, keys:', Object.keys(parsed));
      }
      if (typeof parsed === 'object' && parsed !== null) {
        return Array.isArray(parsed) ? { items: parsed } : parsed;
      }
    } catch (e) {
      if (process.env.NODE_ENV === 'development') {
        console.debug('[parseToolOutput] JSON.parse FAILED:', e, 'text preview:', text.slice(0, 300));
      }
      // Fall through to further attempts
    }
  }

  // Try to find JSON object in the string (handles prefix/suffix noise)
  const braceIdx = text.indexOf('{');
  const bracketIdx = text.indexOf('[');
  const startIdx = braceIdx >= 0 && bracketIdx >= 0
    ? Math.min(braceIdx, bracketIdx)
    : braceIdx >= 0 ? braceIdx : bracketIdx;

  if (startIdx >= 0) {
    // Try to find balanced JSON by bracket counting
    const isArray = text[startIdx] === '[';
    const openChar = isArray ? '[' : '{';
    const closeChar = isArray ? ']' : '}';
    let depth = 0;
    let inString = false;
    let escaped = false;
    let jsonEnd = -1;

    for (let i = startIdx; i < text.length; i++) {
      const char = text[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (char === '\\') {
        escaped = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === openChar) depth++;
        if (char === closeChar) {
          depth--;
          if (depth === 0) {
            jsonEnd = i;
            break;
          }
        }
      }
    }

    if (jsonEnd > startIdx) {
      const candidate = text.slice(startIdx, jsonEnd + 1);
      try {
        const parsed = JSON.parse(candidate);
        if (process.env.NODE_ENV === 'development') {
          console.debug('[parseToolOutput] Fallback JSON.parse succeeded, keys:', Object.keys(parsed));
        }
        if (typeof parsed === 'object' && parsed !== null) {
          return Array.isArray(parsed) ? { items: parsed } : parsed;
        }
      } catch (e) {
        if (process.env.NODE_ENV === 'development') {
          console.debug('[parseToolOutput] Fallback JSON.parse FAILED:', e, 'candidate preview:', candidate.slice(0, 300));
        }
        // Could not parse
      }
    }
  }

  if (process.env.NODE_ENV === 'development') {
    console.debug('[parseToolOutput] Returning empty object - all parsing attempts failed');
  }
  return {};
}

/**
 * Extract a single image object from various formats
 */
function extractImageObject(img: unknown, defaultAlt: string): SearchImage | null {
  if (!img) return null;

  if (typeof img === 'string' && img.startsWith('http')) {
    return { url: img, alt: defaultAlt };
  }

  if (typeof img === 'object' && img !== null) {
    const imgObj = img as Record<string, unknown>;
    const url = (imgObj.url || imgObj.src || imgObj.image || imgObj.thumbnail) as string | undefined;
    if (url && typeof url === 'string' && url.startsWith('http')) {
      return {
        url,
        alt: (imgObj.alt || imgObj.title || imgObj.description || defaultAlt) as string,
        source: imgObj.source as string | undefined,
        width: imgObj.width as number | undefined,
        height: imgObj.height as number | undefined,
      };
    }
  }

  return null;
}

/**
 * Extract images from tool evidence data
 * Looks for images in web_search, grounding_search results
 */
function extractImagesFromToolEvidence(toolEvidence: Record<string, any>): SearchImage[] {
  const images: SearchImage[] = [];
  const seenUrls = new Set<string>();

  const addImage = (img: SearchImage | null) => {
    if (img && img.url && !seenUrls.has(img.url)) {
      seenUrls.add(img.url);
      images.push(img);
    }
  };

  for (const evidence of Object.values(toolEvidence)) {
    if (!evidence) continue;

    // Check if it's a web search or grounding search result
    const toolName = (evidence.toolName || evidence.tool_name || '') as string;
    const isSearchTool = toolName.toLowerCase().includes('search') ||
      toolName.toLowerCase().includes('grounding') ||
      toolName.toLowerCase().includes('web');

    if (!isSearchTool) continue;

    // Parse the output - handle multiple wrapper formats
    const rawOutput = evidence.output ?? evidence.result ?? evidence.data ?? evidence.value;
    const parsedOutput = parseToolOutput(rawOutput);

    // Debug logging for development
    if (process.env.NODE_ENV === 'development') {
      const imageCount = Array.isArray((parsedOutput as any)?.images)
        ? (parsedOutput as any).images.length
        : 0;
      console.debug('[extractImagesFromToolEvidence] Tool:', toolName, {
        rawOutputType: typeof rawOutput,
        rawOutputPreview: typeof rawOutput === 'string' ? rawOutput.slice(0, 300) : rawOutput,
        parsedOutputKeys: Object.keys(parsedOutput),
        hasImages: imageCount > 0,
        imageCount,
        imagesPreview: Array.isArray((parsedOutput as any)?.images)
          ? (parsedOutput as any).images.slice(0, 2)
          : null,
        evidenceKeys: Object.keys(evidence),
      });
    }

    // Extract images from various possible locations
    const imageSources = [
      parsedOutput?.images,
      parsedOutput?.image_results,
      parsedOutput?.imageResults,
      evidence.metadata?.images,
      evidence.images,
    ];

    for (const imageSource of imageSources) {
      if (Array.isArray(imageSource)) {
        for (const img of imageSource) {
          addImage(extractImageObject(img, `Image from ${toolName}`));
        }
      }
    }

    // Also check results array for thumbnails/images
    const results = parsedOutput?.results;
    if (Array.isArray(results)) {
      for (const result of results) {
        if (result && typeof result === 'object') {
          const thumbnail = (result as Record<string, unknown>).thumbnail ||
            (result as Record<string, unknown>).image ||
            (result as Record<string, unknown>).img;
          if (thumbnail) {
            addImage(extractImageObject(thumbnail, (result as Record<string, unknown>).title as string || `Result image from ${toolName}`));
          }
        }
      }
    }
  }

  return images;
}

/**
 * Parse thinking content from message text.
 * Extracts :::thinking blocks and separates them from regular content.
 *
 * Pattern: :::thinking\n{content}\n:::\n{response}
 *
 * Handles edge cases:
 * - Multiple thinking blocks (extracts all, concatenates)
 * - Partial/malformed blocks (removes orphaned markers)
 * - Case variations (:::THINKING, :::Think, etc.)
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

  // Match ALL :::thinking ... ::: blocks (global flag for multiple matches)
  // FIXED: Require closing ::: markers - don't use $ fallback which captures too much during streaming
  // During streaming, if a block isn't closed yet, we wait rather than capturing everything
  const thinkingPattern = /:::(?:thinking|think)\s*([\s\S]*?)\s*:::/gi;
  const allThinkingContent: string[] = [];
  let match: RegExpExecArray | null;

  // Extract all thinking blocks
  while ((match = thinkingPattern.exec(text)) !== null) {
    const content = match[1].trim();
    if (content) {
      allThinkingContent.push(content);
    }
  }

  // Remove all thinking blocks from regular content
  let regularContent = text.replace(thinkingPattern, '');

  // Also remove orphaned/malformed thinking markers that might have leaked
  // These patterns catch partial blocks that didn't close properly
  regularContent = regularContent
    // Remove orphaned opening markers (:::thinking without closing :::)
    .replace(/:::(?:thinking|think)\s*(?!\S*:::)/gi, '')
    // Remove orphaned closing ::: at start of line (not in code blocks)
    .replace(/(?:^|\n)\s*:::\s*(?=\n|$)/g, '\n')
    // Clean up excess whitespace
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return {
    thinkingContent: allThinkingContent.join('\n\n'),
    regularContent
  };
}

/**
 * Extract a thinking fallback from message metadata when :::thinking is absent.
 * Uses latest_thought or trailing thinking_trace steps.
 */
function extractThinkingFallback(metadata: Record<string, any> = {}): string {
  const latest = metadata.latest_thought;
  if (typeof latest === 'string' && latest.trim()) return latest.trim();

  const trace = metadata.thinking_trace || metadata.thinkingTrace;
  if (Array.isArray(trace) && trace.length) {
    const tail = trace.slice(-3);
    const lines = tail
      .map((step: any) => (typeof step === 'string' ? step : step?.content))
      .filter(Boolean)
      .map((s: string) => s.trim());
    if (lines.length) return lines.join('\n');
  }
  return '';
}

// NOTE: The following functions were removed as they are no longer needed after
// the backend fix that properly separates thinking content from message content:
// - isReasoningSentence() - Heuristic pattern matching was over-filtering
// - splitIntoSemanticUnits() - Only used by separateReasoningFromAnswer
// - separateReasoningFromAnswer() - No longer called; backend handles separation
// The backend now emits thinking content via trace events only, not in messages.

/**
 * Final sanitization pass to catch any escaped thinking markers.
 * Applied after reasoning separation to ensure no thinking content leaks.
 *
 * Based on LibreChat PR #10278 patterns.
 */
function finalSanitizeThinkingMarkers(text: string): string {
  if (!text) return '';

  // FIXED: Replaced invalid lookbehind with simpler approach
  // First, protect code blocks by temporarily replacing them
  const codeBlocks: string[] = [];
  let cleaned = text.replace(/```[\s\S]*?```/g, (match) => {
    const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push(match);
    return placeholder;
  });

  // Now safely remove thinking markers (code blocks are protected)
  cleaned = cleaned
    // Remove any remaining :::thinking or :::think markers
    .replace(/:::(?:thinking|think)\s*/gi, '')
    // Remove orphaned closing ::: markers at line boundaries
    .replace(/(?:^|\n)\s*:::\s*(?=\n|$)/g, '\n')
    // Remove "Model reasoning" prefix anywhere
    .replace(/\bModel reasoning\b\s*/gi, '')
    // Clean up resulting whitespace
    .replace(/\n{3,}/g, '\n\n');

  // Restore code blocks
  codeBlocks.forEach((block, i) => {
    cleaned = cleaned.replace(`__CODE_BLOCK_${i}__`, block);
  });

  return cleaned.trim();
}

/**
 * Strip tool-planning noise (e.g., tool_calls payloads) from assistant content.
 * Uses smart reasoning classification to separate self-talk from user-facing answers.
 *
 * Based on Anthropic's extended thinking best practices:
 * - Thinking blocks should contain reasoning, planning, and intermediate thoughts
 * - Text blocks should contain only the final user-facing answer
 */
function sanitizeAssistantContentForDisplay(text: string): string {
  const original = text || '';
  let cleaned = original;

  // Strip only tool_call payload fences; keep other code (e.g., mermaid) intact.
  const toolFencePattern = /```(?:jsonc?|json5|js)?[\s\S]*?"tool_calls?"[\s\S]*?```/gi;
  cleaned = cleaned.replace(toolFencePattern, '');

  // Remove explicit tool call lines
  const toolCallPatterns = [
    /^tool call.*$/gim,
    /^calling tool.*$/gim,
    /^invoking tool.*$/gim,
    /^selected tool.*$/gim,
    /^action:\s*.*$/gim,
  ];
  toolCallPatterns.forEach((pattern) => {
    cleaned = cleaned.replace(pattern, '');
  });

  // Remove any remaining thinking block markers using the robust parser
  // This handles unclosed blocks during streaming to prevent leaks
  const { regularContent } = parseThinkingContent(cleaned);
  cleaned = regularContent;

  // NOTE: separateReasoningFromAnswer() removed - backend now properly separates
  // thinking content and no longer embeds it in messages. The heuristic-based
  // reasoning extraction was over-filtering legitimate content.

  // Apply final sanitization to catch any escaped thinking markers
  cleaned = finalSanitizeThinkingMarkers(cleaned);

  // Collapse extra whitespace
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();

  const cleanedLen = cleaned.trim().length;

  // If all content was reasoning, return empty string
  // The InlineThinking panel will handle reasoning-only responses
  if (cleanedLen === 0) {
    return '';
  }

  return cleaned;
}

// NOTE: extractReasoningForThinkingPanel() removed - backend now properly separates
// thinking content via trace events. This function was calling separateReasoningFromAnswer()
// which is also removed.

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  isStreaming: boolean;
  agentType?: AgentChoice;
  attachments?: AttachmentInput[];
  /** Message index for deterministic ID generation (Issue #4: hydration stability) */
  messageIndex: number;
  /** Images from web search results to display inline */
  searchImages?: SearchImage[];
  /** Aggregated thinking text for the entire run (from thinking trace) */
  globalThinkingText?: string;
  /** Whether this message should display the global thinking block */
  showGlobalThinking?: boolean;
}

function MessageItem({
  message,
  isLast,
  isStreaming,
  agentType,
  attachments = [],
  messageIndex,
  searchImages = [],
  globalThinkingText,
  showGlobalThinking = false,
}: MessageItemProps) {
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

  // NOTE: extractReasoningForThinkingPanel() removed - backend now properly separates
  // thinking content via trace events. Heuristic extraction was over-filtering.

  const thinkingToRender = useMemo(() => {
    if (isUser) return '';

    if (!showGlobalThinking) {
      return '';
    }

    // Collect thinking sources (simplified - backend now handles separation)
    const thinkingSources: string[] = [];

    // 1. Global thinking text from the trace (primary source)
    const globalText = globalThinkingText?.trim() || '';
    if (globalText) {
      thinkingSources.push(globalText);
    }

    // 2. Explicit :::thinking blocks from the message (fallback)
    if (thinkingContent?.trim()) {
      thinkingSources.push(thinkingContent.trim());
    }

    // 3. Fallback to metadata if no trace available
    if (thinkingSources.length === 0) {
      const fallback = extractThinkingFallback(metadata);
      if (fallback) {
        thinkingSources.push(fallback);
      }
    }

    // Combine sources (avoid duplicating if only one source)
    if (thinkingSources.length <= 1) {
      return thinkingSources[0] || '';
    }
    return thinkingSources.join('\n\n---\n\n').trim();
  }, [
    isUser,
    showGlobalThinking,
    globalThinkingText,
    thinkingContent,
    metadata,
  ]);

  const sanitizedContent = useMemo(() => {
    if (isUser) return regularContent;
    return sanitizeAssistantContentForDisplay(regularContent);
  }, [isUser, regularContent]);

  const shouldRegisterArtifacts = !(isLast && isStreaming);

  // Determine actual content to display
  const contentForDisplay = useMemo(() => {
    const trimmed = sanitizedContent.trim();
    return trimmed;
  }, [sanitizedContent]);

  // Check if this is a thinking-only message (no user-facing content)
  // In this case, show only the InlineThinking panel, no message bubble
  const hasOnlyThinking = useMemo(() => {
    return !isUser && !contentForDisplay && thinkingToRender.trim().length > 0;
  }, [isUser, contentForDisplay, thinkingToRender]);

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
            'leading-relaxed',
            isUser
              ? 'text-[16.5px] bg-chat-user-bg text-chat-user-text bubble-user px-5 py-3.5 shadow-academia-sm text-left'
              : 'text-[16.5px] bg-transparent text-foreground px-0 py-0' // Slightly larger type for assistant answers
          )}
        >
          {/* Inline Thinking - Display for assistant messages with thinking content */}
          {!isUser && thinkingToRender && (
            <InlineThinking
              thinkingText={thinkingToRender}
              isStreaming={isLast && isStreaming}
            />
          )}

          {/* Main message content with enhanced markdown - only show if there's actual content */}
          {(contentForDisplay || isUser) && (
            <div
              className={cn(
                'prose prose-sm max-w-none prose-invert',
                isUser
                  ? [
                    'text-[16.5px] leading-relaxed',
                    'prose-p:text-[16.5px] prose-li:text-[16.5px] prose-blockquote:text-[16.5px] prose-table:text-[16.5px]',
                    'prose-th:text-[16.5px] prose-td:text-[16.5px]',
                    'prose-code:text-[14px] prose-pre:text-[13px]',
                  ]
                  : [
                    'prose-headings:text-foreground prose-p:text-foreground/90 prose-strong:text-foreground prose-code:text-terracotta-300',
                    'text-[16.5px] leading-relaxed',
                    'prose-p:text-[16.5px] prose-li:text-[16.5px] prose-blockquote:text-[16.5px] prose-table:text-[16.5px]',
                    'prose-th:text-[16.5px] prose-td:text-[16.5px]',
                    'prose-code:text-[14px] prose-pre:text-[13px]',
                  ]
              )}
            >
              <EnhancedMarkdown
                content={contentForDisplay}
                isLatestMessage={isLast && isStreaming}
                messageId={message.id || `msg-${messageIndex}`}
                registerArtifacts={shouldRegisterArtifacts}
              />
            </div>
          )}

          {/* Inline search images - Show after message content for assistant messages */}
          {!isUser && searchImages.length > 0 && !isStreaming && (
            <div className="mt-4 not-prose">
              <SearchImageGrid
                images={searchImages}
                maxVisible={4}
                title="Related Images"
              />
            </div>
          )}

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
  /** Aggregated thinking text for the current run (from AgentContext.thinkingTrace) */
  thinkingText?: string;
}

export function MessageList({ messages, isStreaming, agentType, thinkingText }: MessageListProps) {
  // Get attachments and tool evidence from context
  const { messageAttachments, toolEvidence } = useAgent();

  // Extract images from tool evidence (web search results)
  const searchImages = useMemo(() => {
    return extractImagesFromToolEvidence(toolEvidence);
  }, [toolEvidence]);

  // Filter out system messages and empty messages
  const visibleMessages = messages.filter(
    m => m.role !== 'system' && m.content !== ''
  );

  if (visibleMessages.length === 0) {
    return null; // Handled by ChatContainer empty state
  }

  // Determine the index of the last assistant message so we can show a single
  // global thinking block there.
  const lastAssistantIndex = (() => {
    for (let i = visibleMessages.length - 1; i >= 0; i -= 1) {
      if (visibleMessages[i].role === 'assistant') {
        return i;
      }
    }
    return -1;
  })();

  return (
    <div className="space-y-2 py-4">
      {visibleMessages.map((message, idx) => {
        const isLastMessage = idx === visibleMessages.length - 1;
        const isAssistant = message.role === 'assistant';

        return (
          <MessageItem
            key={message.id ?? idx}
            message={message}
            isLast={isLastMessage}
            isStreaming={isStreaming}
            agentType={agentType}
            attachments={message.id ? messageAttachments[message.id] : undefined}
            messageIndex={idx}
            // Only show images on the last assistant message to avoid duplication
            searchImages={isLastMessage && isAssistant ? searchImages : undefined}
            // Show the single aggregated thinking block only on the last
            // assistant message, so the user sees one "Thoughts" section per run.
            globalThinkingText={thinkingText}
            showGlobalThinking={thinkingText !== undefined && thinkingText.trim().length > 0 && idx === lastAssistantIndex}
          />
        );
      })}
    </div>
  );
}
