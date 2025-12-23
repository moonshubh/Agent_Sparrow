'use client';

import React, { useState, useCallback, useRef, useEffect, KeyboardEvent, ChangeEvent } from 'react';
import { useAgent } from '@/features/librechat/AgentContext';
import { ArrowUp, Square, Paperclip } from 'lucide-react';
import type { AttachmentInput } from '@/services/ag-ui/types';
import { toast } from 'sonner';
import { AttachmentPreviewList } from '@/features/librechat/components/AttachmentPreview';

interface ChatInputProps {
  isLanding?: boolean;
  initialInput?: string;
  onInitialInputUsed?: () => void;
}

export function ChatInput({ initialInput, onInitialInputUsed }: ChatInputProps) {
  const { sendMessage, isStreaming, abortRun } = useAgent();
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<AttachmentInput[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastAppliedInitialInputRef = useRef<string | null>(null);
  const readersRef = useRef<FileReader[]>([]);
  const isMountedRef = useRef(true);

  const inferMimeType = useCallback((file: globalThis.File): string => {
    if (file.type) return file.type;

    const lower = file.name.toLowerCase();
    if (lower.endsWith('.log')) return 'text/plain';
    if (lower.endsWith('.txt')) return 'text/plain';
    if (lower.endsWith('.md')) return 'text/markdown';
    if (lower.endsWith('.csv')) return 'text/csv';
    if (lower.endsWith('.json')) return 'application/json';

    return 'application/octet-stream';
  }, []);

  // Handle initial input from starters
  useEffect(() => {
    if (initialInput && initialInput !== lastAppliedInitialInputRef.current) {
      setInput(initialInput);
      lastAppliedInitialInputRef.current = initialInput;
      onInitialInputUsed?.();
      // Focus the textarea and position cursor at end
      if (textareaRef.current) {
        textareaRef.current.focus();
        // Resize textarea for content
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
      }
    }
  }, [initialInput, onInitialInputUsed]);

  // Abort any in-flight file reads on unmount to avoid leaks/state updates.
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      readersRef.current.forEach((reader) => {
        try {
          reader.abort();
        } catch {
          // ignore
        }
      });
      readersRef.current = [];
    };
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!input.trim() && attachments.length === 0) return;
    if (isStreaming) return;

    const message = input.trim();
    const currentAttachments = [...attachments];

    setInput('');
    setAttachments([]);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    await sendMessage(message, currentAttachments);
  }, [input, attachments, isStreaming, sendMessage]);

  const handleStop = useCallback(() => {
    abortRun();
  }, [abortRun]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!isStreaming) {
          handleSubmit();
        }
      }
    },
    [handleSubmit, isStreaming]
  );

  const handleInputChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);

    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  }, []);

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newAttachments: AttachmentInput[] = [];
    const errors: string[] = [];

    for (const file of Array.from(files)) {
      // Validate file size (max 10MB)
      const MAX_FILE_SIZE = 10 * 1024 * 1024;
      if (file.size > MAX_FILE_SIZE) {
        errors.push(`${file.name} exceeds 10MB limit`);
        continue;
      }

      const reader = new FileReader();
      try {
        // Read file as base64 with proper error handling
        readersRef.current.push(reader);
        const dataUrl = await new Promise<string>((resolve, reject) => {
          reader.onload = () => {
            if (typeof reader.result === 'string') {
              resolve(reader.result);
            } else {
              reject(new Error('Failed to read file as string'));
            }
          };
          reader.onerror = () => {
            reject(new Error(`Failed to read ${file.name}: ${reader.error?.message || 'Unknown error'}`));
          };
          reader.onabort = () => {
            reject(new Error(`Reading ${file.name} was aborted`));
          };
          reader.readAsDataURL(file);
        });

        newAttachments.push({
          name: file.name,
          mime_type: inferMimeType(file),
          data_url: dataUrl,
          size: file.size,
        });
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : `Failed to read ${file.name}`;
        errors.push(errorMessage);
        if (process.env.NODE_ENV !== 'production') {
          console.error('File read error:', err);
        } else {
          console.error('File read failed');
        }
      } finally {
        readersRef.current = readersRef.current.filter((r) => r !== reader);
      }
    }

    if (!isMountedRef.current) return;

    if (newAttachments.length > 0) {
      setAttachments((prev) => [...prev, ...newAttachments]);
    }

    if (errors.length > 0) {
      const [first, ...rest] = errors;
      const description = rest.length > 0 ? `${first} (+${rest.length} more)` : first;
      toast.error('Some files could not be attached', { description });
    }
  }, [inferMimeType]);

  const handleFileInputChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      handleFileSelect(e.target.files);
      e.target.value = ''; // Reset input
    },
    [handleFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      handleFileSelect(e.dataTransfer.files);
    },
    [handleFileSelect]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <div className="lc-input-container">
      <div className="lc-input-wrapper">
        {/* Attachments preview */}
        {attachments.length > 0 && (
          <div style={{ marginBottom: '8px' }} aria-label="Attached files">
            <AttachmentPreviewList
              attachments={attachments}
              onRemove={removeAttachment}
              variant="input"
            />
          </div>
        )}

        {/* Input box */}
        <div
          className={`lc-input-box ${isDragOver ? 'drag-over' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          role="group"
          aria-label="Message input area"
        >
          {/* File attachment button */}
          <button
            className="lc-action-btn"
            onClick={openFilePicker}
            aria-label="Attach file (images, PDF, text files supported)"
            type="button"
          >
            <Paperclip size={18} />
          </button>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,.pdf,.txt,.log,.md,.json,.csv,text/plain"
            onChange={handleFileInputChange}
            style={{ display: 'none' }}
            aria-hidden="true"
            tabIndex={-1}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className="lc-textarea"
            placeholder="Message Agent Sparrow..."
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isStreaming}
            aria-label="Message input"
            aria-describedby="input-footer"
          />

          {/* Send/Stop button */}
          {isStreaming ? (
            <button
              className="lc-send-btn lc-stop-btn"
              onClick={handleStop}
              aria-label="Stop generating response"
              type="button"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              className="lc-send-btn"
              onClick={handleSubmit}
              disabled={!input.trim() && attachments.length === 0}
              aria-label="Send message"
              type="button"
            >
              <ArrowUp size={18} />
            </button>
          )}
        </div>

        {/* Footer text */}
        <div id="input-footer" className="lc-input-footer">
          Agent Sparrow can make mistakes. Please verify important information.
        </div>
      </div>
    </div>
  );
}

export default ChatInput;
