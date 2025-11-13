'use client';

import React, { useState, useRef, KeyboardEvent } from 'react';
import { Button } from '@/shared/ui/button';
import { Textarea } from '@/shared/ui/textarea';
import { cn } from '@/shared/lib/utils';
import { SendHorizontalIcon, Square, Paperclip, X } from 'lucide-react';
import type { AttachmentInput } from '@/services/ag-ui/types';
import { createBinaryContent } from '@/services/ag-ui/types';

interface ChatInputProps {
  onSend: (message: string) => void;
  onAbort: () => void;
  disabled: boolean;
  attachments: AttachmentInput[];
  onAttachmentsChange: (attachments: AttachmentInput[]) => void;
  sessionId: string;
}

export function ChatInput({
  onSend,
  onAbort,
  disabled,
  attachments,
  onAttachmentsChange,
  sessionId,
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSend(input.trim());
      setInput('');

      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }

      // Clear attachments after sending
      onAttachmentsChange([]);

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newAttachments: AttachmentInput[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];

      // Validate file size (10MB limit)
      if (file.size > 10 * 1024 * 1024) {
        console.warn(`File ${file.name} is too large (max 10MB)`);
        continue;
      }

      try {
        const binaryContent = await createBinaryContent(file);
        newAttachments.push({
          name: file.name,
          mimeType: file.type,
          dataUrl: `data:${file.type};base64,${binaryContent.data}`,
          size: file.size,
        });
      } catch (error) {
        console.error('Error processing file:', error);
      }
    }

    onAttachmentsChange([...attachments, ...newAttachments]);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    await handleFileSelect(e.dataTransfer.files);
  };

  const removeAttachment = (index: number) => {
    onAttachmentsChange(attachments.filter((_, i) => i !== index));
  };

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);

    // Auto-resize
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200
      )}px`;
    }
  };

  return (
    <div
      className={cn(
        'border-t bg-white p-4',
        isDragOver && 'bg-blue-50 border-blue-300'
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {attachments.map((attachment, index) => (
            <div
              key={index}
              className="flex items-center gap-2 bg-gray-100 rounded-lg px-3 py-2"
            >
              <Paperclip className="w-4 h-4 text-gray-500" />
              <span className="text-sm text-gray-700 max-w-[200px] truncate">
                {attachment.name}
              </span>
              <span className="text-xs text-gray-500">
                ({(attachment.size / 1024).toFixed(1)}KB)
              </span>
              <button
                type="button"
                onClick={() => removeAttachment(index)}
                className="ml-1 text-gray-400 hover:text-gray-600"
                aria-label={`Remove attachment ${index + 1}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-2">
          {/* File upload button */}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            className="mb-1"
            aria-label="Attach file"
          >
            <Paperclip className="w-5 h-5" />
          </Button>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleFileSelect(e.target.files)}
            accept="image/*,application/pdf,.txt,.md,.csv,.json"
          />

          {/* Message input */}
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled
                ? 'Generating response...'
                : 'Type a message... (Enter to send, Shift+Enter for new line)'
            }
            disabled={disabled}
            className={cn(
              'flex-1 min-h-[44px] max-h-[200px] resize-none',
              'focus:ring-2 focus:ring-blue-500'
            )}
            rows={1}
          />

          {/* Send/Stop button */}
          {disabled ? (
            <Button
              type="button"
              onClick={onAbort}
              variant="destructive"
              size="icon"
              className="mb-1"
              aria-label="Abort generation"
            >
              <Square className="w-4 h-4" />
            </Button>
          ) : (
            <Button
              type="button"
              onClick={handleSend}
              disabled={!input.trim()}
              size="icon"
              className="mb-1"
              aria-label="Send message"
            >
              <SendHorizontalIcon className="w-4 h-4" />
            </Button>
          )}
        </div>

        {/* Drag and drop indicator */}
        {isDragOver && (
          <div className="mt-2 p-4 border-2 border-dashed border-blue-400 rounded-lg bg-blue-50 text-center">
            <p className="text-blue-600">Drop files here to attach</p>
          </div>
        )}

        {/* Character count */}
        {input.length > 0 && (
          <div className="mt-1 text-xs text-gray-500 text-right">
            {input.length} characters
          </div>
        )}
      </div>
    </div>
  );
}