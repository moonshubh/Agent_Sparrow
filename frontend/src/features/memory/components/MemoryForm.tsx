"use client";

import React, { useMemo, useState, useCallback, useEffect } from "react";
import type { User } from "@supabase/supabase-js";
import { motion, AnimatePresence } from "framer-motion";
import { MemoryTipTapEditor } from "./MemoryTipTapEditor";
import {
  X,
  Save,
  AlertCircle,
  Bold,
  Italic,
  Underline,
  List,
  ListOrdered,
  Code,
  ChevronDown,
  Link2,
  FileText,
  Zap,
} from "lucide-react";
import { useAddMemory, useUpdateMemory } from "../hooks";
import type { Memory, SourceType } from "../types";
import { SourceBadge } from "./SourceBadge";
import { useAuth } from "@/shared/contexts/AuthContext";
import { normalizeLegacyMemoryContent } from "../lib/legacyMemoryFormatting";
import { normalizeMarkdownImageSizing } from "../lib/memoryImageMarkdown";
import { toast } from "sonner";
import type { Editor } from "@tiptap/core";

interface MemoryFormProps {
  onClose: () => void;
  onSuccess?: (memoryId?: string) => void;
  memory?: Memory;
}

// Spring animation config
const springConfig = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

const isPlainMetadata = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const toInitialMetadataText = (value: unknown): string => {
  if (!isPlainMetadata(value) || Object.keys(value).length === 0) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
};

const PLAYBOOK_SECTION_PATTERN =
  /^\s*(?:#{1,6}\s*)?(?:\*\*)?(problem|impact|environment)(?:\*\*)?\s*(?::|-)?\s*/im;
const PLAYBOOK_KEY_HEADINGS = ["Problem", "Impact", "Environment"];
const INLINE_MEMORY_ASSET_IMAGE_PATTERN =
  /!\[[^\]]*]\((?:memory-asset:\/\/|\/api\/v1\/memory\/assets\/)[^)]+\)/i;

const getUserDisplayName = (user: User | null): string | null => {
  if (!user) return null;

  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const fullName =
    typeof meta.full_name === "string" ? meta.full_name.trim() : "";
  const name = typeof meta.name === "string" ? meta.name.trim() : "";

  if (fullName) return fullName;
  if (name) return name;

  const email = user.email?.trim();
  if (email) return email.split("@")[0] || email;

  return user.id || null;
};

export function MemoryForm({ onClose, onSuccess, memory }: MemoryFormProps) {
  const isEditMode = Boolean(memory);
  const { user } = useAuth();
  const initialContent = useMemo(
    () => normalizeLegacyMemoryContent(memory?.content ?? ""),
    [memory?.content],
  );
  const [content, setContent] = useState(initialContent);
  const [sourceType, setSourceType] = useState<SourceType>(
    memory?.source_type ?? "manual",
  );
  const [metadata, setMetadata] = useState(() =>
    toInitialMetadataText(memory?.metadata),
  );
  const [error, setError] = useState<string | null>(null);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [metadataExpanded, setMetadataExpanded] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);

  useEffect(() => {
    setContent(initialContent);
  }, [initialContent]);

  const addMemory = useAddMemory();
  const updateMemory = useUpdateMemory();
  const isSaving = isEditMode ? updateMemory.isPending : addMemory.isPending;
  const editorName = useMemo(() => getUserDisplayName(user), [user]);
  const editorEmail = useMemo(
    () => (user?.email ? user.email.toLowerCase() : null),
    [user],
  );
  const isMbPlaybookImportedMemory = useMemo(() => {
    if (memory?.metadata && isPlainMetadata(memory.metadata)) {
      const source = String(memory.metadata.source ?? "").toLowerCase();
      if (source === "zendesk_mb_playbook") return true;
      const tags = Array.isArray(memory.metadata.tags)
        ? memory.metadata.tags.map((tag) => String(tag).toLowerCase())
        : [];
      if (tags.includes("mb_playbook")) return true;
    }

    // Fallback for imported memories where metadata may be partially edited.
    return PLAYBOOK_SECTION_PATTERN.test(initialContent);
  }, [initialContent, memory?.metadata]);
  const hasInlineMemoryAssetImages = useMemo(
    () => INLINE_MEMORY_ASSET_IMAGE_PATTERN.test(initialContent),
    [initialContent],
  );
  const [usePlainTextSafeMode, setUsePlainTextSafeMode] = useState(
    () => isEditMode && hasInlineMemoryAssetImages,
  );

  const handleBold = useCallback(() => {
    editor?.chain().focus().toggleBold().run();
  }, [editor]);
  const handleItalic = useCallback(() => {
    editor?.chain().focus().toggleItalic().run();
  }, [editor]);
  const handleUnderline = useCallback(() => {
    editor?.chain().focus().toggleUnderline().run();
  }, [editor]);
  const handleCode = useCallback(() => {
    editor?.chain().focus().toggleCodeBlock().run();
  }, [editor]);
  const handleBulletList = useCallback(() => {
    editor?.chain().focus().toggleBulletList().run();
  }, [editor]);
  const handleNumberedList = useCallback(() => {
    editor?.chain().focus().toggleOrderedList().run();
  }, [editor]);
  const handleLink = useCallback(() => {
    const previousUrl = editor?.getAttributes("link").href || "";
    const url = window.prompt("Enter URL", previousUrl);
    if (url === null) return;
    if (!url) {
      editor?.chain().focus().unsetLink().run();
      return;
    }
    editor?.chain().focus().setLink({ href: url }).run();
  }, [editor]);

  const handlePrettifyMetadata = useCallback(() => {
    const trimmed = metadata.trim();
    if (!trimmed) {
      setMetadata("");
      setMetadataError(null);
      return;
    }

    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (
        typeof parsed !== "object" ||
        parsed === null ||
        Array.isArray(parsed)
      ) {
        setMetadataExpanded(true);
        setMetadataError("Metadata must be a JSON object");
        return;
      }
      setMetadata(JSON.stringify(parsed, null, 2));
      setMetadataError(null);
    } catch {
      setMetadataExpanded(true);
      setMetadataError("Invalid JSON");
    }
  }, [metadata]);

  const handleClearMetadata = useCallback(() => {
    setMetadata("");
    setMetadataError(null);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setMetadataError(null);

      const editorContent = editor?.getMarkdown() ?? content;
      const normalizedImageContent = normalizeMarkdownImageSizing(editorContent, {
        editorDoc: editor?.getJSON() ?? null,
        fallbackMarkdown: memory?.content,
      });
      const trimmedContent = normalizedImageContent.trim();

      if (!trimmedContent) {
        setError("Content is required");
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
              setMetadataError("Metadata must be a JSON object");
              setError("Metadata must be a JSON object");
              return;
            }
            parsedMetadata = parsed;
          } catch {
            setMetadataExpanded(true);
            setMetadataError("Invalid JSON");
            setError("Invalid JSON in metadata field");
            return;
          }
        }

        const metadataBase = isPlainMetadata(parsedMetadata) ? parsedMetadata : {};
        const editorIdentity = editorName || editorEmail || user?.id || null;
        const metadataWithEditor =
          isEditMode && editorIdentity
            ? {
                ...metadataBase,
                edited_by: editorIdentity,
                edited_by_email: editorEmail || undefined,
                edited_by_name: editorName || editorEmail || undefined,
                updated_by_email: editorEmail || undefined,
                updated_by: editorIdentity,
              }
            : parsedMetadata;

        if (isEditMode && memory) {
          const updated = await updateMemory.mutateAsync({
            memoryId: memory.id,
            request: {
              content: trimmedContent,
              metadata: metadataWithEditor,
            },
          });
          toast.success("Memory updated");
          onSuccess?.(updated?.id || memory.id);
        } else {
          const created = await addMemory.mutateAsync({
            content: trimmedContent,
            source_type: sourceType,
            metadata: parsedMetadata,
          });
          toast.success("Memory saved");
          onSuccess?.(created?.id);
        }
        onClose();
      } catch (err: unknown) {
        const defaultMessage = isEditMode
          ? "Failed to update memory"
          : "Failed to add memory";
        setError(err instanceof Error ? err.message : defaultMessage);
      }
    },
    [
      content,
      sourceType,
      metadata,
      editor,
      addMemory,
      updateMemory,
      isEditMode,
      memory,
      editorName,
      editorEmail,
      user?.id,
      onSuccess,
      onClose,
    ],
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
            <h2 className="add-memory-title">
              {isEditMode ? "Edit Memory" : "New Memory"}
            </h2>
            <p className="add-memory-subtitle">
              {isEditMode
                ? "Refine knowledge for the agent"
                : "Add knowledge to the graph"}
            </p>
          </div>
          <div className="add-memory-header-right">
            <div className="add-memory-toolbar add-memory-toolbar--header">
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
                onClick={handleUnderline}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Underline"
              >
                <Underline size={14} />
              </motion.button>
              <motion.button
                type="button"
                className="add-memory-tool-btn"
                onClick={handleCode}
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                title="Code Block"
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
              <div className="add-memory-tool-divider" />
              <span className="add-memory-char-count">
                {content.length} chars
              </span>
              {isEditMode && hasInlineMemoryAssetImages ? (
                <button
                  type="button"
                  className="add-memory-meta-btn"
                  onClick={() =>
                    setUsePlainTextSafeMode((enabled) => !enabled)
                  }
                  title={
                    usePlainTextSafeMode
                      ? "Enable rich image editor"
                      : "Switch to safe markdown mode"
                  }
                >
                  {usePlainTextSafeMode ? "Load Rich Editor" : "Safe Mode"}
                </button>
              ) : null}
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
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="add-memory-form">
          <div className="add-memory-body">
            {/* Error message */}
            <AnimatePresence>
              {error && (
                <motion.div
                  className="add-memory-error"
                  initial={{ opacity: 0, y: -10, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: "auto" }}
                  exit={{ opacity: 0, y: -10, height: 0 }}
                >
                  <AlertCircle size={16} />
                  <span>{error}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Full-width content editor */}
            <div className="add-memory-editor-section">
              <div className="add-memory-editor-split">
                {usePlainTextSafeMode ? (
                  <div className="add-memory-safe-editor">
                    <div className="add-memory-readonly">
                      <span>
                        Safe mode avoids rich image rendering for this imported
                        memory to prevent UI freezes.
                      </span>
                      <span className="add-memory-readonly-hint">
                        Markdown source view
                      </span>
                    </div>
                    <textarea
                      value={content}
                      onChange={(event) => setContent(event.target.value)}
                      className="add-memory-textarea add-memory-code"
                      rows={14}
                      placeholder="Enter memory markdown..."
                    />
                  </div>
                ) : (
                  <div className="add-memory-tiptap">
                    <MemoryTipTapEditor
                      content={content}
                      onChange={setContent}
                      onEditorReady={setEditor}
                      syncExternalContent={false}
                      className={
                        isMbPlaybookImportedMemory
                          ? "memory-edit-mb-playbook"
                          : undefined
                      }
                      keyHeadingHighlights={PLAYBOOK_KEY_HEADINGS}
                      placeholder="Enter the memory content... Example: To resolve sync issues with Gmail, clear the OAuth cache by going to Settings > Accounts > Gmail > Reconnect."
                    />
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
                  animate={{ height: "auto", opacity: 1 }}
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
          </div>

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
                    className={`add-memory-source-pill ${sourceType === "manual" ? "active" : ""}`}
                    onClick={() => setSourceType("manual")}
                  >
                    <FileText size={14} />
                    Manual
                  </button>
                  <button
                    type="button"
                    className={`add-memory-source-pill ${sourceType === "auto_extracted" ? "active" : ""}`}
                    onClick={() => setSourceType("auto_extracted")}
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
              className={`add-memory-meta-toggle ${metadataExpanded ? "expanded" : ""} ${metadataKeyCount > 0 ? "has-data" : ""}`}
              onClick={() => setMetadataExpanded(!metadataExpanded)}
            >
              <Code size={14} />
              <span>
                Metadata{metadataKeyCount > 0 ? ` (${metadataKeyCount})` : ""}
              </span>
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
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        ease: "linear",
                      }}
                    />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Save size={16} />
                    <span>{isEditMode ? "Update Memory" : "Save Memory"}</span>
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
