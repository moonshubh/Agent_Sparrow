'use client';

import { useEffect, useMemo } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import type { Editor } from '@tiptap/core';
import { createMemoryExtensions } from '@/features/memory/tiptap/memoryExtensions';

interface MemoryTipTapEditorProps {
  content: string;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
  onChange?: (markdown: string) => void;
  onEditorReady?: (editor: Editor | null) => void;
}

export function MemoryTipTapEditor({
  content,
  readOnly = false,
  placeholder,
  className,
  onChange,
  onEditorReady,
}: MemoryTipTapEditorProps) {
  const extensions = useMemo(
    () =>
      createMemoryExtensions({
        placeholder,
        enableImages: true,
      }),
    [placeholder]
  );

  const editor = useEditor({
    extensions,
    content,
    contentType: 'markdown',
    editable: !readOnly,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: `memory-tiptap-editor${readOnly ? ' memory-tiptap-editor--readonly' : ''}`,
      },
    },
    onUpdate: ({ editor }) => {
      if (readOnly || !onChange) return;
      onChange(editor.getMarkdown());
    },
  });

  useEffect(() => {
    if (!editor) return;
    onEditorReady?.(editor);
    return () => {
      onEditorReady?.(null);
    };
  }, [editor, onEditorReady]);

  useEffect(() => {
    if (!editor) return;
    if (content === editor.getMarkdown()) return;
    editor.commands.setContent(content, { contentType: 'markdown' });
  }, [content, editor]);

  if (!editor) return null;

  return (
    <div className={className ? `memory-tiptap-wrapper ${className}` : 'memory-tiptap-wrapper'}>
      <EditorContent editor={editor} />
    </div>
  );
}

