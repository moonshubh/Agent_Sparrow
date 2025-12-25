'use client';

import React, { useCallback, useState, useRef, ChangeEvent } from 'react';
import { useAgent } from '@/features/librechat/AgentContext';
import { Sparkles, ArrowUp, Command, PenTool, MessageSquare, Zap, Paperclip } from 'lucide-react';
import type { AttachmentInput } from '@/services/ag-ui/types';
import { AttachmentPreviewList } from '@/features/librechat/components/AttachmentPreview';
import { LayoutTextFlip } from '@/components/ui/layout-text-flip';
import { motion } from 'motion/react';

interface LandingProps {
  onStarterClick?: (prompt: string) => void;
}

interface AgentState {
  model?: string;
  [key: string]: unknown;
}

const ACTION_PILLS = [
  { icon: Zap, label: 'Skills', action: 'skills' },
  { icon: PenTool, label: 'Rephrase', action: 'rephrase' },
  { icon: MessageSquare, label: 'Reply', action: 'reply' },
  { icon: Command, label: 'Prompt', action: 'prompt' },
];

export function Landing({ onStarterClick }: LandingProps) {
  const { agent, sendMessage } = useAgent();
  const [inputValue, setInputValue] = useState('');
  const [attachments, setAttachments] = useState<AttachmentInput[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newAttachments: AttachmentInput[] = [];
    const errors: string[] = [];

    for (const file of Array.from(files)) {
      const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
      if (file.size > MAX_FILE_SIZE) {
        errors.push(`${file.name} exceeds 10MB limit`);
        continue;
      }

      try {
        const reader = new FileReader();
        const dataUrl = await new Promise<string>((resolve, reject) => {
          reader.onload = () => {
            if (typeof reader.result === 'string') resolve(reader.result);
            else reject(new Error('Failed to read file'));
          };
          reader.onerror = () => reject(new Error('Read error'));
          reader.readAsDataURL(file);
        });

        newAttachments.push({
          name: file.name,
          mime_type: inferMimeType(file),
          data_url: dataUrl,
          size: file.size,
        });
      } catch (err) {
        console.error('File read error:', err);
      }
    }

    if (newAttachments.length > 0) {
      setAttachments((prev) => [...prev, ...newAttachments]);
    }
  }, [inferMimeType]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  }, [handleFileSelect]);

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

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (inputValue.trim() || attachments.length > 0) {
        sendMessage(inputValue.trim(), attachments);
        setInputValue('');
        setAttachments([]);
      }
    }
  }, [inputValue, attachments, sendMessage]);

  const handleSubmit = useCallback(() => {
    if (inputValue.trim() || attachments.length > 0) {
      sendMessage(inputValue.trim(), attachments);
      setInputValue('');
      setAttachments([]);
    }
  }, [inputValue, attachments, sendMessage]);

  // Force display of 3.0 Flash for landing page visual consistency
  const modelName = 'Gemini 3.0 Flash';

  return (
    <div className="lc-landing">
      {/* Centered Content Container */}
      <div className="lc-landing-content">
        {/* Logo */}
        <div className="lc-landing-logo">
          <img src="/Sparrow_logo.png" alt="Agent Sparrow" />
        </div>

        <div>
          <motion.div className="relative mx-4 mt-4 mb-8 flex max-w-full flex-col items-center justify-center gap-3 text-center sm:mx-0 sm:flex-row sm:flex-wrap">
            <LayoutTextFlip
              text="What can I help you with?"
              words={["Log files", "Images", "General questions", "Technical questions", "Writing articles"]}
            />
          </motion.div>
        </div>

        <div className="lc-hero-search-container">
          <div
            className={`lc-hero-input-wrapper ${isDragOver ? 'drag-over' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {/* Attachment Preview Section */}
            {attachments.length > 0 && (
              <div className="px-3 pt-3">
                <AttachmentPreviewList
                  attachments={attachments}
                  onRemove={removeAttachment}
                  variant="input"
                />
              </div>
            )}

            <div className="flex items-center w-full">
              {/* Attachment Button */}
              <button
                className="lc-action-btn ml-2"
                onClick={openFilePicker}
                aria-label="Attach file"
                type="button"
              >
                <Paperclip size={18} />
              </button>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.pdf,.txt,.log,.md,.json,.csv,text/plain"
                onChange={(e) => {
                  handleFileSelect(e.target.files);
                  e.target.value = '';
                }}
                style={{ display: 'none' }}
              />

              <input
                type="text"
                className="lc-hero-input flex-1"
                placeholder="Ask anything..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
              />
              <div className="lc-hero-input-actions mr-1">
                <button
                  className="lc-hero-submit-btn"
                  onClick={handleSubmit}
                  disabled={!inputValue.trim() && attachments.length === 0}
                >
                  <ArrowUp size={16} />
                </button>
              </div>
            </div>
          </div>

          {/* Action Pills */}
          <div className="lc-hero-pills">
            {ACTION_PILLS.map((pill) => {
              const Icon = pill.icon;
              return (
                <button
                  key={pill.label}
                  className="lc-hero-pill"
                  onClick={() => {
                    // Placeholder for future actions
                  }}
                >
                  <Icon size={12} />
                  <span>{pill.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Landing;
