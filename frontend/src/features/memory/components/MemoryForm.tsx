'use client';

import React, { useMemo, useState, useCallback, useRef } from 'react';
import type { User } from '@supabase/supabase-js';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  X,
  Save,
  AlertCircle,
  Bold,
  Italic,
  List,
  ListOrdered,
  Code,
  ChevronDown,
  Link2,
  FileText,
  Zap,
  Eye,
} from 'lucide-react';
import { useAddMemory, useUpdateMemory } from '../hooks';
import type { Memory, SourceType } from '../types';
import { SourceBadge } from './SourceBadge';
import { useAuth } from '@/shared/contexts/AuthContext';

interface MemoryFormProps {
  onClose: () => void;
  onSuccess?: () => void;
  memory?: Memory;
}

// Spring animation config
const springConfig = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 30,
};

const isPlainMetadata = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const getUserDisplayName = (user: User | null): string | null => {
  if (!user) return null;

  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const fullName = typeof meta.full_name === 'string' ? meta.full_name.trim() : '';
  const name = typeof meta.name === 'string' ? meta.name.trim() : '';

  if (fullName) return fullName;
  if (name) return name;

  const email = user.email?.trim();
  if (email) return email.split('@')[0] || email;

  return user.id || null;
};

export function MemoryForm({ onClose, onSuccess, memory }: MemoryFormProps) {
  const isEditMode = Boolean(memory);
  const { user } = useAuth();
  const [content, setContent] = useState(memory?.content ?? '');
  const [sourceType, setSourceType] = useState<SourceType>(
    memory?.source_type ?? 'manual'
  );
  const [metadata, setMetadata] = useState(
    memory?.metadata && Object.keys(memory.metadata).length > 0
      ? JSON.stringify(memory.metadata, null, 2)
      : ''
  );
  const [error, setError] = useState<string | null>(null);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [metadataExpanded, setMetadataExpanded] = useState(false);
  const [previewEnabled, setPreviewEnabled] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const addMemory = useAddMemory();
  const updateMemory = useUpdateMemory();
  const isSaving = isEditMode ? updateMemory.isPending : addMemory.isPending;
  const editorName = useMemo(() => getUserDisplayName(user), [user]);

  // Insert formatting at cursor
  const insertFormat = useCallback((prefix: string, suffix: string = '') => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = content.substring(start, end);
    const before = content.substring(0, start);
    const after = content.substring(end);

    const newContent = before + prefix + selectedText + suffix + after;
    setContent(newContent);

    // Focus and set cursor position
    setTimeout(() => {
      textarea.focus();
      const newCursorPos = start + prefix.length + selectedText.length + suffix.length;
      textarea.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  }, [content]);

  const handleBold = () => insertFormat('**', '**');
  const handleItalic = () => insertFormat('_', '_');
  const handleCode = () => insertFormat('`', '`');
  const handleBulletList = () => insertFormat('\n- ');
  const handleNumberedList = () => insertFormat('\n1. ');
  const handleLink = () => insertFormat('[', '](url)');

  const handlePrettifyMetadata = useCallback(() => {
    const trimmed = metadata.trim();
    if (!trimmed) {
      setMetadata('');
      setMetadataError(null);
      return;
    }

    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setMetadataExpanded(true);
        setMetadataError('Metadata must be a JSON object');
        return;
      }
      setMetadata(JSON.stringify(parsed, null, 2));
      setMetadataError(null);
    } catch {
      setMetadataExpanded(true);
      setMetadataError('Invalid JSON');
    }
  }, [metadata]);

  const handleClearMetadata = useCallback(() => {
    setMetadata('');
    setMetadataError(null);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setMetadataError(null);

      if (!content.trim()) {
        setError('Content is required');
        return;
      }

      try {
        let parsedMetadata: Record<string, unknown> = {};
        if (metadata.trim()) {
          try {
            const parsed: unknown = JSON.parse(metadata);
            // Validate that parsed result is an object
            if (!isPlainMetadata(parsed)) {
              setMetadataExpanded(true);
              setMetadataError('Metadata must be a JSON object');
              setError('Metadata must be a JSON object');
              return;
            }
            parsedMetadata = parsed;
          } catch {
            setMetadataExpanded(true);
            setMetadataError('Invalid JSON');
            setError('Invalid JSON in metadata field');
            return;
          }
        }

        const metadataWithEditor =
          isEditMode && editorName
            ? { ...(isPlainMetadata(parsedMetadata) ? parsedMetadata : {}), edited_by: editorName }
            : parsedMetadata;

        if (isEditMode && memory) {
          await updateMemory.mutateAsync({
            memoryId: memory.id,
            request: {
              content: content.trim(),
              metadata: metadataWithEditor,
            },
          });
        } else {
          await addMemory.mutateAsync({
            content: content.trim(),
            source_type: sourceType,
            metadata: parsedMetadata,
          });
        }

        onSuccess?.();
        onClose();
      } catch (err: unknown) {
        const defaultMessage = isEditMode ? 'Failed to update memory' : 'Failed to add memory';
        setError(err instanceof Error ? err.message : defaultMessage);
      }
    },
    [content, sourceType, metadata, addMemory, updateMemory, isEditMode, memory, editorName, onSuccess, onClose]
  );

  const metadataKeyCount = useMemo(() => {
    const trimmed = metadata.trim();
    if (!trimmed) return 0;
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (!isPlainMetadata(parsed)) {
        return 0;
      }
      return Object.keys(parsed as Record<string, unknown>).length;
    } catch {
      return 0;
    }
  }, [metadata]);

  return (
    <motion.div
      className="add-memory-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="add-memory-modal"
        initial={{ opacity: 0, scale: 0.95, y: 30 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 30 }}
        transition={springConfig}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Accent gradient bar */}
        <div className="add-memory-accent" />

        {/* Header */}
        <div className="add-memory-header">
          <div className="add-memory-header-content">
            <h2 className="add-memory-title">{isEditMode ? 'Edit Memory' : 'New Memory'}</h2>
            <p className="add-memory-subtitle">
              {isEditMode ? 'Refine knowledge for the agent' : 'Add knowledge to the graph'}
            </p>
          </div>
          <motion.button
            className="add-memory-close"
            onClick={onClose}
            whileHover={{ scale: 1.1, rotate: 90 }}
            whileTap={{ scale: 0.9 }}
          >
            <X size={18} />
          </motion.button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="add-memory-form">
          {/* Error message */}
          <AnimatePresence>
            {error && (
              <motion.div
                className="add-memory-error"
                initial={{ opacity: 0, y: -10, height: 0 }}
                animate={{ opacity: 1, y: 0, height: 'auto' }}
                exit={{ opacity: 0, y: -10, height: 0 }}
              >
                <AlertCircle size={16} />
                <span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Full-width content editor */}
          <div
            className={`add-memory-editor-section ${
              !isEditMode && previewEnabled ? 'with-preview' : ''
            }`}
          >
            {/* Formatting toolbar */}
            <div className="add-memory-toolbar">
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleBold}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Bold"
              >
                <Bold size={14} />
              </motion.button>
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleItalic}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Italic"
              >
                <Italic size={14} />
              </motion.button>
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleCode}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Code"
              >
                <Code size={14} />
              </motion.button>
              <div className="add-memory-tool-divider" />
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleBulletList}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Bullet List"
              >
                <List size={14} />
              </motion.button>
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleNumberedList}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Numbered List"
              >
                <ListOrdered size={14} />
              </motion.button>
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleLink}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Link"
              >
                <Link2 size={14} />
              </motion.button>
              <div className="add-memory-toolbar-spacer" />
              {!isEditMode && (
                <motion.button
                  type="button"
                  className={`add-memory-tool-btn ${previewEnabled ? 'active' : ''}`}
                  onClick={() => setPreviewEnabled((prev) => !prev)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.95 }}
                  title={previewEnabled ? 'Hide preview' : 'Show preview'}
                >
                  <Eye size={14} />
                </motion.button>
              )}
              <span className="add-memory-char-count">{content.length} chars</span>
            </div>

            <div className="add-memory-editor-split">
              <textarea
                ref={textareaRef}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Enter the memory content...&#10;&#10;Example: To resolve sync issues with Gmail, clear the OAuth cache by going to Settings > Accounts > Gmail > Reconnect."
                className="add-memory-textarea add-memory-textarea-main"
                autoFocus
              />

              {!isEditMode && previewEnabled && (
                <div className="add-memory-preview">
                  {content.trim() ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                  ) : (
                    <div className="add-memory-preview-empty">
                      <p>Start typing to see a preview of your markdown content.</p>
                      <p className="memory-empty-hint">
                        Preview renders markdown (lists, code, links) to make memories easier to read.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Collapsible Metadata Panel */}
          <AnimatePresence>
            {metadataExpanded && (
              <motion.div
                className="add-memory-meta-panel"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="add-memory-meta-panel-inner">
                  <div className="add-memory-meta-toolbar">
                    <button
                      type="button"
                      className="add-memory-meta-btn"
                      onClick={handlePrettifyMetadata}
                    >
                      Prettify
                    </button>
                    <button
                      type="button"
                      className="add-memory-meta-btn"
                      onClick={handleClearMetadata}
                    >
                      Clear
                    </button>
                  </div>
                  <textarea
                    value={metadata}
                    onChange={(e) => {
                      setMetadata(e.target.value);
                      setMetadataError(null);
                    }}
                    placeholder='{"ticket_id": "12345", "source": "zendesk"}'
                    className="add-memory-textarea add-memory-code add-memory-metadata-textarea"
                    rows={3}
                  />
                  {metadataError && (
                    <div className="add-memory-field-error">
                      <AlertCircle size={14} />
                      <span>{metadataError}</span>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Compact Footer */}
          <div className="add-memory-footer">
            {/* Source selection (inline) */}
            <div className="add-memory-footer-source">
              {isEditMode ? (
                <SourceBadge sourceType={sourceType} />
              ) : (
                <div className="add-memory-source-toggle">
                  <button
                    type="button"
                    className={`add-memory-source-pill ${sourceType === 'manual' ? 'active' : ''}`}
                    onClick={() => setSourceType('manual')}
                  >
                    <FileText size={14} />
                    Manual
                  </button>
                  <button
                    type="button"
                    className={`add-memory-source-pill ${sourceType === 'auto_extracted' ? 'active' : ''}`}
                    onClick={() => setSourceType('auto_extracted')}
                  >
                    <Zap size={14} />
                    Auto
                  </button>
                </div>
              )}
            </div>

            {/* Collapsible Metadata */}
            <button
              type="button"
              className={`add-memory-meta-toggle ${metadataExpanded ? 'expanded' : ''} ${metadataKeyCount > 0 ? 'has-data' : ''}`}
              onClick={() => setMetadataExpanded(!metadataExpanded)}
            >
              <Code size={14} />
              <span>Metadata{metadataKeyCount > 0 ? ` (${metadataKeyCount})` : ''}</span>
              <ChevronDown size={14} className="add-memory-meta-chevron" />
            </button>

            {/* Actions */}
            <div className="add-memory-actions">
              <motion.button
                type="button"
                onClick={onClose}
                className="add-memory-btn add-memory-btn-secondary"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Cancel
              </motion.button>
              <motion.button
                type="submit"
                className="add-memory-btn add-memory-btn-primary"
                disabled={isSaving || !content.trim()}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {isSaving ? (
                  <>
                    <motion.div
                      className="add-memory-spinner"
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Save size={16} />
                    <span>{isEditMode ? 'Update Memory' : 'Save Memory'}</span>
                  </>
                )}
              </motion.button>
            </div>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
