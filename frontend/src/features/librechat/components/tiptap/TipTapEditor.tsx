'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import type { Editor } from '@tiptap/core';
import { createExtensions, type ExtensionOptions } from './extensions';

export interface TipTapEditorProps {
  initialContent: string;
  onSave?: (markdown: string) => Promise<void> | void;
  onExit?: () => void;
  onCancel?: () => void;
  autoSave?: boolean;
  autoSaveDelay?: number;
  enableMath?: boolean;
  enableTables?: boolean;
  enableTaskList?: boolean;
  enableImages?: boolean;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export function TipTapEditor({
  initialContent,
  onSave,
  onExit,
  onCancel,
  autoSave = true,
  autoSaveDelay = 350,
  enableMath = true,
  enableTables = true,
  enableTaskList = true,
  enableImages = true,
  readOnly = false,
  placeholder,
  className,
}: TipTapEditorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedRef = useRef(initialContent);
  const isSavingRef = useRef(false);

  const [status, setStatus] = useState<SaveStatus>('idle');

  const extensionOptions: ExtensionOptions = useMemo(
    () => ({
      placeholder,
      enableMath,
      enableTables,
      enableTaskList,
      enableImages,
    }),
    [placeholder, enableMath, enableTables, enableTaskList, enableImages]
  );

  const extensions = useMemo(() => createExtensions(extensionOptions), [extensionOptions]);

  const markSaved = useCallback(() => {
    setStatus('saved');
    if (statusTimeoutRef.current) {
      clearTimeout(statusTimeoutRef.current);
    }
    statusTimeoutRef.current = setTimeout(() => setStatus('idle'), 1500);
  }, []);

  const runSave = useCallback(async (editor: Editor): Promise<boolean> => {
    if (readOnly || !onSave) return true;
    if (isSavingRef.current) return false;
    const markdown = editor.getMarkdown();
    if (markdown === lastSavedRef.current) return true;

    isSavingRef.current = true;
    setStatus('saving');

    try {
      await onSave(markdown);
      lastSavedRef.current = markdown;
      markSaved();
      return true;
    } catch (error: unknown) {
      if (error instanceof Error) {
        console.error('[TipTapEditor] Failed to save content', error.message, error.stack);
      } else {
        console.error('[TipTapEditor] Failed to save content', String(error));
      }
      setStatus('error');
      return false;
    } finally {
      isSavingRef.current = false;
    }
  }, [markSaved, onSave, readOnly]);

  const scheduleSave = useCallback((editor: Editor) => {
    if (!autoSave || readOnly || !onSave) return;
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      void runSave(editor);
    }, autoSaveDelay);
  }, [autoSave, autoSaveDelay, onSave, readOnly, runSave]);

  const editor = useEditor({
    extensions,
    content: initialContent,
    contentType: 'markdown',
    editable: !readOnly,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: 'lc-tiptap-editor',
      },
    },
    onCreate: ({ editor }) => {
      lastSavedRef.current = editor.getMarkdown();
    },
    onUpdate: ({ editor }) => {
      scheduleSave(editor);
    },
  });

  useEffect(() => {
    if (!editor) return;
    if (initialContent === lastSavedRef.current) return;
    editor.commands.setContent(initialContent, { contentType: 'markdown' });
    lastSavedRef.current = initialContent;
    setStatus('idle');
  }, [editor, initialContent]);

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      if (statusTimeoutRef.current) {
        clearTimeout(statusTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!editor || !autoSave || readOnly || !onSave) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target;
      if (!target || !(target instanceof Node) || !containerRef.current) return;
      if (containerRef.current.contains(target)) return;

      void runSave(editor).then((didSave) => {
        if (didSave) {
          onExit?.();
        }
      });
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [autoSave, editor, onExit, onSave, readOnly, runSave]);

  const handleKeyDownCapture = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      if (onCancel) {
        onCancel();
        return;
      }
      onExit?.();
    }
  }, [onCancel, onExit]);

  if (!editor) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className={className ? `lc-tiptap-wrapper ${className}` : 'lc-tiptap-wrapper'}
      onKeyDownCapture={handleKeyDownCapture}
    >
      <EditorContent editor={editor} />
      {!readOnly && status !== 'idle' && (
        <div
          className={
            status === 'error'
              ? 'lc-tiptap-status lc-tiptap-status-error'
              : 'lc-tiptap-status'
          }
          role="status"
          aria-live="polite"
        >
          {status === 'saving' && 'Saving...'}
          {status === 'saved' && 'Saved'}
          {status === 'error' && 'Save failed'}
        </div>
      )}
    </div>
  );
}

export default TipTapEditor;
