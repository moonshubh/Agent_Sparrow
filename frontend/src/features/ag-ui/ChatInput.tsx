'use client';

import React, { useState, useRef, KeyboardEvent } from 'react';
import { Button } from '@/shared/ui/button';
import { Textarea } from '@/shared/ui/textarea';
import { cn } from '@/shared/lib/utils';
import { SendHorizontalIcon, Square, Paperclip, X, Mic, Plus, Sparkles, RefreshCw } from 'lucide-react';
import type { AttachmentInput } from '@/services/ag-ui/types';
import { createBinaryContent } from '@/services/ag-ui/types';
import type { AgentChoice } from '@/features/chat/hooks/useAgentSelection';

interface ChatInputProps {
  onSend: (message: string) => void;
  onAbort: () => void;
  disabled: boolean;
  attachments: AttachmentInput[];
  onAttachmentsChange: (attachments: AttachmentInput[]) => void;
  sessionId: string;
  agentType?: AgentChoice;
  variant?: 'default' | 'centered';
}

export function ChatInput({
  onSend,
  onAbort,
  disabled,
  attachments,
  onAttachmentsChange,
  sessionId,
  agentType,
  variant = 'default',
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isLogAgent = agentType === 'log_analysis';

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
      const normalizedType = file.type || 'application/octet-stream';

      // Validate file size (10MB limit)
      if (file.size > 10 * 1024 * 1024) {
        console.warn(`File ${file.name} is too large (max 10MB)`);
        continue;
      }

      try {
        const binaryContent = await createBinaryContent(file);
        newAttachments.push({
          name: file.name,
          mime_type: normalizedType,
          data_url: `data:${normalizedType};base64,${binaryContent.data}`,
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

  const isCentered = variant === 'centered';

  return (
    <div
      className={cn(
        'transition-all duration-500 ease-in-out w-full',
        isCentered ? 'max-w-2xl mx-auto' : 'border-t bg-[hsl(220,15%,10%)] p-4',
        isDragOver && 'bg-blue-500/10 border-blue-500/50'
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
              className="flex items-center gap-2 bg-white/10 backdrop-blur-md rounded-lg px-3 py-2 border border-white/10"
            >
              <Paperclip className="w-4 h-4 text-gray-300" />
              <span className="text-sm text-gray-200 max-w-[200px] truncate">
                {attachment.name}
              </span>
              <span className="text-xs text-gray-400">
                ({(attachment.size / 1024).toFixed(1)}KB)
              </span>
              <button
                type="button"
                onClick={() => removeAttachment(index)}
                className="ml-1 text-gray-400 hover:text-white"
                aria-label={`Remove attachment ${index + 1}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input Container */}
      <div className={cn(
        "relative flex flex-col gap-4",
        isCentered ? "" : "max-w-4xl mx-auto"
      )}>

        {/* Main Input Bar */}
        <div className={cn(
          "flex items-center gap-2 p-2 transition-all duration-300",
          isCentered
            ? "bg-[hsl(220,15%,16%)]/80 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl min-h-[64px]"
            : "bg-[hsl(220,15%,14%)] border border-white/5 rounded-xl"
        )}>
          {/* File upload button */}
          <Button
            type="button"
            variant="ghost"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            className={cn(
              "text-gray-400 hover:text-white hover:bg-white/5 transition-colors",
              isCentered ? "rounded-xl px-3 h-10 gap-2 bg-white/5" : "h-10 w-10 p-0 rounded-lg"
            )}
            aria-label="Attach file"
          >
            {isCentered ? (
              <>
                <Plus className="w-4 h-4" />
                <span className="text-sm font-medium">Add files</span>
              </>
            ) : (
              <Paperclip className="w-5 h-5" />
            )}
          </Button>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="sr-only"
            onChange={(e) => handleFileSelect(e.target.files)}
            accept="text/plain,.log,.txt,.md,.csv,.json,application/pdf,image/*"
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
                : isCentered ? 'Ask anything...' : 'Type a message...'
            }
            disabled={disabled}
            className={cn(
              'flex-1 bg-transparent border-0 focus:ring-0 text-gray-100 placeholder:text-gray-500 resize-none py-3',
              isCentered ? 'text-lg' : 'text-base',
              'min-h-[44px] max-h-[200px]'
            )}
            rows={1}
          />

          {/* Right Actions */}
          <div className="flex items-center gap-1 pr-1">
            {isCentered && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled
                title="Voice input coming soon"
                className="text-gray-400 hover:text-white hover:bg-white/5 rounded-full h-10 w-10"
                aria-disabled="true"
              >
                <Mic className="w-5 h-5" />
              </Button>
            )}

            {/* Send/Stop button */}
            {disabled ? (
              <Button
                type="button"
                onClick={onAbort}
                variant="destructive"
                size="icon"
                className={cn(
                  "transition-all",
                  isCentered ? "rounded-full h-10 w-10" : "rounded-lg h-10 w-10"
                )}
                aria-label="Abort generation"
              >
                <Square className="w-4 h-4" />
              </Button>
            ) : (
              <Button
                type="button"
                onClick={handleSend}
                disabled={!input.trim()}
                className={cn(
                  "transition-all bg-white/10 hover:bg-white/20 text-white border border-white/5",
                  isCentered ? "rounded-full h-10 w-10 p-0" : "rounded-lg h-10 w-10 p-0"
                )}
                aria-label="Send message"
              >
                <SendHorizontalIcon className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Action Pills (Centered Mode Only) */}
        {isCentered && (
          <div className="flex items-center justify-center gap-2 animate-in fade-in slide-in-from-bottom-4 duration-700 delay-100">
            <Button
              variant="outline"
              disabled
              aria-disabled="true"
              title="Skills shortcuts coming soon"
              className="rounded-full bg-white/5 border-white/10 hover:bg-white/10 text-gray-300 text-xs h-8 gap-2"
            >
              <Sparkles className="w-3 h-3" />
              Skills
            </Button>
            <Button
              variant="outline"
              disabled
              aria-disabled="true"
              title="Rephrase option coming soon"
              className="rounded-full bg-white/5 border-white/10 hover:bg-white/10 text-gray-300 text-xs h-8 gap-2"
            >
              <RefreshCw className="w-3 h-3" />
              Rephrase
            </Button>
          </div>
        )}

        {/* Drag and drop indicator */}
        {isDragOver && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-blue-500/20 backdrop-blur-sm rounded-2xl border-2 border-dashed border-blue-400">
            <p className="text-blue-200 font-medium">Drop files here to attach</p>
          </div>
        )}

        {isLogAgent && (
          <p className="text-center text-xs text-amber-500/80">
            {attachments.length > 0
              ? 'Attached logs will be analyzed automatically.'
              : 'Attach log files for diagnosis.'}
          </p>
        )}
      </div>
    </div>
  );
}
