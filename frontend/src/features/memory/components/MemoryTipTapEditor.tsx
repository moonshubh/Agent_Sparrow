"use client";

import { useEffect, useMemo, useRef } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import type { Editor } from "@tiptap/core";
import { createMemoryExtensions } from "@/features/memory/tiptap/memoryExtensions";

interface MemoryTipTapEditorProps {
  content: string;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
  keyHeadingHighlights?: string[];
  onChange?: (markdown: string) => void;
  onEditorReady?: (editor: Editor | null) => void;
  syncExternalContent?: boolean;
}

export function MemoryTipTapEditor({
  content,
  readOnly = false,
  placeholder,
  className,
  keyHeadingHighlights,
  onChange,
  onEditorReady,
  syncExternalContent = true,
}: MemoryTipTapEditorProps) {
  const lastEmittedMarkdownRef = useRef(content);
  const extensions = useMemo(
    () =>
      createMemoryExtensions({
        placeholder,
        enableImages: true,
      }),
    [placeholder],
  );

  const editor = useEditor({
    extensions,
    content,
    contentType: "markdown",
    editable: !readOnly,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: `memory-tiptap-editor${readOnly ? " memory-tiptap-editor--readonly" : ""}`,
      },
    },
    onUpdate: ({ editor }) => {
      if (readOnly || !onChange) return;
      const markdown = editor.getMarkdown();
      if (markdown === lastEmittedMarkdownRef.current) return;
      lastEmittedMarkdownRef.current = markdown;
      onChange(markdown);
    },
  });

  useEffect(() => {
    if (!syncExternalContent) return;
    lastEmittedMarkdownRef.current = content;
  }, [content, syncExternalContent]);

  useEffect(() => {
    if (!editor) return;
    onEditorReady?.(editor);
    return () => {
      onEditorReady?.(null);
    };
  }, [editor, onEditorReady]);

  useEffect(() => {
    if (!editor) return;
    if (!syncExternalContent) return;
    if (content === editor.getMarkdown()) return;
    lastEmittedMarkdownRef.current = content;
    editor.commands.setContent(content, { contentType: "markdown" });
  }, [content, editor, syncExternalContent]);

  useEffect(() => {
    if (!editor) return;

    const clearHighlights = () => {
      const root = editor.view.dom as HTMLElement | null;
      if (!root) return;
      root
        .querySelectorAll<HTMLElement>(
          ".memory-key-heading, .memory-key-label-line",
        )
        .forEach((node) =>
          node.classList.remove("memory-key-heading", "memory-key-label-line"),
        );
    };

    const normalizedHeadings = (keyHeadingHighlights ?? [])
      .map((heading) => heading.trim().toLowerCase())
      .filter(Boolean);
    if (normalizedHeadings.length === 0) {
      clearHighlights();
      return;
    }
    const headingSet = new Set(normalizedHeadings);

    const normalizeHeadingText = (value: string): string =>
      value
        .replace(/\u00A0/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase()
        .replace(/\*\*/g, "")
        .replace(/\s*[:\-|/]\s*$/, "")
        .trim();

    const isHighlightedHeading = (value: string): boolean => {
      const normalized = normalizeHeadingText(value);
      if (!normalized) return false;
      if (headingSet.has(normalized)) return true;
      return normalizedHeadings.some(
        (heading) =>
          normalized.startsWith(`${heading}:`) ||
          normalized.startsWith(`${heading} -`) ||
          normalized.startsWith(`${heading} /`) ||
          normalized.startsWith(`${heading} |`) ||
          normalized.startsWith(`${heading} `),
      );
    };
    const labelLinePatterns = normalizedHeadings.map((heading) => {
      const escapedHeading = heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return new RegExp(
        `^(?:[-*]\\s+|\\d+[.)]\\s+)?(?:\\*\\*)?${escapedHeading}(?:\\*\\*)?\\s*(?::|-|$)`,
        "i",
      );
    });

    const applyHeadingHighlights = () => {
      const root = editor.view.dom as HTMLElement | null;
      if (!root) return;

      const normalizeLine = (value: string): string =>
        value
          .replace(/\u00A0/g, " ")
          .replace(/\s+/g, " ")
          .trim();

      // Highlight markdown heading nodes (h1-h6).
      const headings = root.querySelectorAll<HTMLElement>(
        "h1, h2, h3, h4, h5, h6",
      );
      headings.forEach((headingNode) => {
        const headingText = normalizeLine(headingNode.textContent ?? "");
        if (isHighlightedHeading(headingText)) {
          headingNode.classList.add("memory-key-heading");
        } else {
          headingNode.classList.remove("memory-key-heading");
        }
      });

      // Imported playbook memories often use "Problem: ..." label lines.
      // Highlight those label paragraphs with the same visual emphasis.
      const paragraphs = root.querySelectorAll<HTMLElement>("p");
      paragraphs.forEach((paragraphNode) => {
        const paragraphText = normalizeLine(paragraphNode.textContent ?? "");
        const isKeyLabelLine = labelLinePatterns.some((pattern) =>
          pattern.test(paragraphText),
        );

        if (isKeyLabelLine) {
          paragraphNode.classList.add("memory-key-label-line");
        } else {
          paragraphNode.classList.remove("memory-key-label-line");
        }
      });
    };

    applyHeadingHighlights();
    editor.on("update", applyHeadingHighlights);

    return () => {
      editor.off("update", applyHeadingHighlights);
      clearHighlights();
    };
  }, [editor, keyHeadingHighlights]);

  if (!editor) return null;

  return (
    <div
      className={
        className
          ? `memory-tiptap-wrapper ${className}`
          : "memory-tiptap-wrapper"
      }
    >
      <EditorContent editor={editor} />
    </div>
  );
}
