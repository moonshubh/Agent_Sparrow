/**
 * Unified Text Canvas for FeedMe System
 * Replaces fragmented Q&A sections with a single editable text area
 *
 * Features:
 * - Display extracted text in a unified canvas
 * - Edit text with real-time preview
 * - Processing method indicators (PDF OCR, manual entry, etc.)
 * - Confidence scoring and quality indicators
 * - Approval workflow integration
 * - Text statistics and metadata
 */

"use client";

import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
} from "react";
import { withErrorBoundary } from "@/features/feedme/components/ErrorBoundary";
import { Card, CardContent } from "@/shared/ui/card";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Toggle } from "@/shared/ui/toggle";
import { ToggleGroup, ToggleGroupItem } from "@/shared/ui/toggle-group";
import {
  Edit3,
  X,
  FileText,
  Bold,
  Italic,
  Underline,
  Code,
  List,
  ListOrdered,
  CheckCircle2,
  Bot,
  User,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import CharacterCount from "@tiptap/extension-character-count";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import UnderlineExtension from "@tiptap/extension-underline";
import { uploadImageToSupabase } from "@/services/storage/storage";
import type { Editor } from "@tiptap/core";
import type {
  ProcessingStageValue,
  ProcessingStatusValue,
} from "@/features/feedme/services/feedme-api";

const isLikelyHtml = (text: string): boolean =>
  /<\s*(p|br|ul|ol|li|h[1-6]|strong|em|a|img|code|pre)\b/i.test(text);

const escapeHtml = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const styleNamesInHtml = (html: string): string => {
  let output = html;

  output = output.replace(
    /(<strong>)?Mailbird Support:?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)(<\/strong>)?/g,
    '<code class="agent-name bg-blue-100 text-blue-900 px-1 py-0.5 rounded text-sm font-semibold">Mailbird Support: $2</code>',
  );

  output = output.replace(
    /(<strong>)([A-Z][a-z]+\s+[A-Z][a-z]+)(\s+[A-Z][a-z]+ \d+, \d{4} at \d+:\d+)(<\/strong>)/g,
    '<code class="agent-name bg-blue-100 text-blue-900 px-1 py-0.5 rounded text-sm font-semibold">$2</code>$3',
  );

  output = output.replace(
    /^(<p>)?(<strong>)?([A-Z][a-z]+\s+[A-Z][a-z]+)(?!\s*:?\s*Mailbird)(\s+[A-Z][a-z]+ \d+, \d{4} at \d+:\d+)/gm,
    '$1<code class="customer-name bg-amber-100 text-amber-900 px-1 py-0.5 rounded text-sm font-semibold">$3</code>$4',
  );

  return output;
};

const formatMetricLabel = (key: string): string =>
  key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

// Types
interface ProcessingMetadata {
  processing_method: "pdf_ai" | "pdf_ocr" | "manual_text" | "text_paste";
  extraction_confidence?: number;
  processing_time_ms?: number;
  quality_metrics?: Record<string, number>;
  extraction_method?: string;
  warnings?: string[];
}

interface TextStatistics {
  character_count: number;
  word_count: number;
  line_count: number;
  paragraph_count: number;
  estimated_read_time_minutes: number;
}

interface CanvasMetadata extends Record<string, unknown> {
  ticket_id?: string | number | null;
  processing_tracker?: {
    progress?: number;
    stage?: ProcessingStageValue | ProcessingStatusValue;
    message?: string;
  };
  content_format?: string;
}

type ApprovalAction = "approve" | "reject" | "edit_and_approve";

interface ApprovalActionPayload {
  edited_text?: string;
}

interface UnifiedTextCanvasProps {
  conversationId: number;
  title: string;
  ticketId?: string | null;
  extractedText: string;
  metadata?: CanvasMetadata | null;
  processingMetadata: ProcessingMetadata;
  approvalStatus: "pending" | "approved" | "rejected";
  approvedBy?: string;
  approvedAt?: string;
  pdfCleaned?: boolean;
  pdfCleanedAt?: string;
  originalPdfSize?: number;
  folderId?: number | null;
  onTextUpdate?: (text: string) => Promise<void>;
  onApprovalAction?: (
    action: ApprovalAction,
    data?: ApprovalActionPayload,
  ) => Promise<void>;
  readOnly?: boolean;
  showApprovalControls?: boolean;
  fullPageMode?: boolean;
  showProcessingSummary?: boolean;
}

export function UnifiedTextCanvas({
  conversationId,
  extractedText,
  metadata,
  processingMetadata,
  approvalStatus,
  approvedBy,
  approvedAt,
  onTextUpdate,
  onApprovalAction,
  readOnly = false,
  showApprovalControls = false,
  fullPageMode = false,
  showProcessingSummary = true,
}: UnifiedTextCanvasProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState(extractedText);
  const [isLoading, setIsLoading] = useState(false);
  const [textStats, setTextStats] = useState<TextStatistics | null>(null);
  // Use the actual DOMPurify type from the library
  const [purify, setPurify] = useState<
    typeof import("isomorphic-dompurify").default | null
  >(null);
  const [purifyLoading, setPurifyLoading] = useState(true);

  const {
    processing_method,
    extraction_confidence,
    extraction_method,
    processing_time_ms,
    quality_metrics,
    warnings: processingWarnings = [],
  } = processingMetadata;

  const processingSummary = useMemo(() => {
    switch (processing_method) {
      case "pdf_ai":
        return {
          label: "AI Vision",
          description: "LLM vision extraction (Gemini)",
          icon: <Bot className="h-3.5 w-3.5" />,
          badgeClass: "bg-sky-100 text-sky-800 border-sky-200",
        };
      case "pdf_ocr":
        return {
          label: "PDF OCR",
          description:
            extraction_method === "ocr_fallback"
              ? "OCR with fallback heuristics"
              : "Text extracted via OCR",
          icon: <Bot className="h-3.5 w-3.5" />,
          badgeClass: "bg-blue-100 text-blue-800 border-blue-200",
        };
      case "manual_text":
        return {
          label: "Manual Entry",
          description: "Content entered manually",
          icon: <User className="h-3.5 w-3.5" />,
          badgeClass: "bg-green-100 text-green-800 border-green-200",
        };
      case "text_paste":
      default:
        return {
          label: "Text Paste",
          description: "Content pasted from another source",
          icon: <FileText className="h-3.5 w-3.5" />,
          badgeClass: "bg-purple-100 text-purple-800 border-purple-200",
        };
    }
  }, [extraction_method, processing_method]);

  const confidenceBadge = useMemo(() => {
    if (typeof extraction_confidence !== "number") return null;
    const percentage = Math.round(extraction_confidence * 100);
    if (extraction_confidence >= 0.9) {
      return (
        <Badge
          variant="outline"
          className="bg-emerald-100 text-emerald-800 border-emerald-200"
        >
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
          High confidence ({percentage}%)
        </Badge>
      );
    }
    if (extraction_confidence >= 0.7) {
      return (
        <Badge
          variant="outline"
          className="bg-amber-100 text-amber-800 border-amber-200"
        >
          <FileText className="mr-1 h-3.5 w-3.5" />
          Medium confidence ({percentage}%)
        </Badge>
      );
    }
    return (
      <Badge
        variant="outline"
        className="bg-rose-100 text-rose-800 border-rose-200"
      >
        <FileText className="mr-1 h-3.5 w-3.5" />
        Low confidence ({percentage}%)
      </Badge>
    );
  }, [extraction_confidence]);

  const warnings = useMemo(
    () =>
      processingWarnings.filter(
        (warning): warning is string =>
          typeof warning === "string" && warning.trim().length > 0,
      ),
    [processingWarnings],
  );

  const metricBadges = useMemo(() => {
    const metrics: Array<{ key: string; label: string; value: string }> = [];

    if (
      typeof processing_time_ms === "number" &&
      Number.isFinite(processing_time_ms)
    ) {
      const seconds = processing_time_ms / 1000;
      const value =
        seconds >= 1
          ? `${seconds.toFixed(1)}s`
          : `${Math.max(seconds, 0).toFixed(2)}s`;
      metrics.push({ key: "processing_time", label: "Processing Time", value });
    }

    Object.entries(quality_metrics ?? {})
      .filter(
        (entry): entry is [string, number] =>
          typeof entry[1] === "number" && Number.isFinite(entry[1]),
      )
      .forEach(([key, value]) => {
        let display = value.toString();
        if (value >= 0 && value <= 1) {
          display = `${Math.round(value * 100)}%`;
        } else if (Math.abs(value) >= 1000) {
          display = Math.trunc(value).toLocaleString();
        }

        metrics.push({ key, label: formatMetricLabel(key), value: display });
      });

    return metrics;
  }, [processing_time_ms, quality_metrics]);

  // Load DOMPurify on client side
  useEffect(() => {
    if (typeof window !== "undefined") {
      import("isomorphic-dompurify")
        .then((module) => {
          // Access the default export which is the actual DOMPurify instance
          setPurify(() => module.default);
          setPurifyLoading(false);
        })
        .catch((err) => {
          console.error("Failed to load DOMPurify:", err);
          setPurifyLoading(false);
        });
    }
  }, []);

  const markdownToHtml = useCallback(
    (md: string): string => {
      if (!md) return "";
      // Code blocks ```
      let html = md.replace(
        /```([\s\S]*?)```/g,
        (_m, code) => `<pre><code>${escapeHtml(code.trim())}</code></pre>`,
      );
      // Inline code `code`
      html = html.replace(
        /`([^`]+)`/g,
        (_m, code) => `<code>${escapeHtml(code)}</code>`,
      );
      // Headings #, ##, ### (limit to h1-h3 for readability)
      html = html.replace(/^(#{1,3})\s+(.+)$/gm, (_m, hashes, text) => {
        const level = Math.min(hashes.length, 3);
        return `<h${level}>${text.trim()}</h${level}>`;
      });
      // Bold **text**
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      // Underline __text__
      html = html.replace(/__([^_]+)__/g, "<u>$1</u>");
      // Italic _text_ or *text*
      html = html.replace(/(^|\W)_(.+?)_(?=\W|$)/g, "$1<em>$2</em>");
      html = html.replace(/(^|\W)\*(.+?)\*(?=\W|$)/g, "$1<em>$2</em>");
      // Links [text](url)
      html = html.replace(
        /\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
      );
      // Lists: group consecutive - or * lines
      html = html.replace(
        /(?:^|\n)([\t ]*[-*] .+(?:\n[\t ]*[-*] .+)*)/g,
        (m) => {
          const items = m
            .trim()
            .split(/\n/)
            .map((l) => l.replace(/^[-*]\s+/, "").trim());
          return `\n<ul>${items.map((it) => `<li>${it}</li>`).join("")}</ul>`;
        },
      );
      // Ordered lists: 1. 2. ...
      html = html.replace(
        /(?:^|\n)([\t ]*\d+\. .+(?:\n[\t ]*\d+\. .+)*)/g,
        (m) => {
          const items = m
            .trim()
            .split(/\n/)
            .map((l) => l.replace(/^\d+\.\s+/, "").trim());
          return `\n<ol>${items.map((it) => `<li>${it}</li>`).join("")}</ol>`;
        },
      );
      // Paragraphs: split on blank lines
      const blocks = html
        .split(/\n\n+/)
        .map((b) => b.trim())
        .filter(Boolean)
        .map((b) => {
          if (/^<\/?(h\d|ul|ol|li|pre|blockquote|p|img|code)/i.test(b))
            return b;
          return `<p>${b.replace(/\n/g, "<br />")}</p>`;
        });

      // Apply name styling after all other conversions
      const finalHtml = styleNamesInHtml(blocks.join("\n"));

      // Sanitize HTML to prevent XSS if DOMPurify is available
      if (purify) {
        return purify.sanitize(finalHtml, {
          ALLOWED_TAGS: [
            "p",
            "br",
            "strong",
            "em",
            "u",
            "a",
            "ul",
            "ol",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "code",
            "pre",
            "blockquote",
            "img",
          ],
          ALLOWED_ATTR: ["href", "target", "rel", "src", "alt", "class"],
          ALLOWED_URI_REGEXP:
            /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|cid|xmpp|data):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
        });
      }
      return finalHtml;
    },
    [purify],
  );

  const htmlToMarkdown = useCallback((html: string): string => {
    if (!html) return "";
    let md = html;
    // Normalize line breaks
    md = md.replace(/<br\s*\/?>(\s*)/gi, "\n");
    // Code blocks
    md = md.replace(
      /<pre[^>]*>\s*<code[^>]*>([\s\S]*?)<\/code>\s*<\/pre>/gi,
      (_m, code) => `\n\n\
\`\`\`\n${code}\n\`\`\`\n\n`,
    );
    // Inline code
    md = md.replace(
      /<code[^>]*>([\s\S]*?)<\/code>/gi,
      (_m, code) => "`" + code + "`",
    );
    // Headings
    md = md.replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, "# $1\n\n");
    md = md.replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, "## $1\n\n");
    md = md.replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, "### $1\n\n");
    // Strong/Emphasis/Underline
    md = md.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, "**$1**");
    md = md.replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, "**$1**");
    md = md.replace(/<u[^>]*>([\s\S]*?)<\/u>/gi, "__$1__");
    md = md.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, "*$1*");
    md = md.replace(/<i[^>]*>([\s\S]*?)<\/i>/gi, "*$1*");
    // Links
    md = md.replace(
      /<a[^>]*href=["'](https?:[^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi,
      "[$2]($1)",
    );
    // Images
    md = md.replace(
      /<img[^>]*src=["'](https?:[^"']+)["'][^>]*alt=["']([^"']*)["'][^>]*\/?>(?:<\/img>)?/gi,
      "![$2]($1)",
    );
    md = md.replace(
      /<img[^>]*src=["'](https?:[^"']+)["'][^>]*\/?>(?:<\/img>)?/gi,
      "![]($1)",
    );
    // Lists
    md = md.replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, (_m, inner) => {
      const items = inner.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, "- $1\n");
      return `\n${items}\n`;
    });
    md = md.replace(
      /<ol[^>]*>([\s\S]*?)<\/ol>/gi,
      (_m: string, inner: string) => {
        let i = 0;
        return `\n${inner.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_m2: string, it: string) => `${++i}. ${it}\n`)}\n`;
      },
    );
    // Paragraphs
    md = md.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, "$1\n\n");
    // Blockquotes
    md = md.replace(
      /<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi,
      (_m: string, inr: string) =>
        inr
          .split(/\n/)
          .map((l: string) => `> ${l}`)
          .join("\n") + "\n\n",
    );
    // Remove remaining tags
    md = md.replace(/<[^>]+>/g, "");
    // Normalize spacing
    return md
      .split("\n")
      .map((l) => l.trimEnd())
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }, []);

  const htmlToPlain = useCallback(
    (html: string): string => {
      if (!purify) return html.replace(/<[^>]*>/g, ""); // Fallback to simple tag stripping
      return purify.sanitize(html, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
    },
    [purify],
  );

  // Sanitize config for rendering - NEVER render unsanitized HTML
  const sanitizeHtml = useCallback(
    (html: string) => {
      if (!purify) {
        // If DOMPurify isn't loaded, strip all HTML tags as a fallback
        return html.replace(/<[^>]*>/g, "");
      }
      return purify.sanitize(html, {
        ALLOWED_TAGS: [
          "p",
          "br",
          "strong",
          "em",
          "u",
          "a",
          "ul",
          "ol",
          "li",
          "code",
          "pre",
          "blockquote",
          "h1",
          "h2",
          "h3",
          "img",
        ],
        ALLOWED_ATTR: ["href", "target", "rel", "src", "alt", "class"],
        ALLOW_DATA_ATTR: false,
        FORBID_TAGS: ["style", "script", "iframe", "object", "embed", "link"],
      });
    },
    [purify],
  );

  // Handle auto-save - defined early for editor dependency
  const [isSaving, setIsSaving] = useState(false);
  const saveAbortControllerRef = useRef<AbortController | null>(null);

  const handleAutoSave = useCallback(
    async (html: string) => {
      const markdown = htmlToMarkdown(html);
      if (markdown === extractedText) return;

      // Cancel any pending save request
      if (saveAbortControllerRef.current) {
        saveAbortControllerRef.current.abort();
      }

      // Create new abort controller for this save
      const abortController = new AbortController();
      saveAbortControllerRef.current = abortController;

      setIsSaving(true);
      try {
        if (onTextUpdate) {
          await onTextUpdate(markdown);
        } else {
          await fetch(`/api/v1/feedme/conversations/${conversationId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              extracted_text: markdown,
              metadata: { ...(metadata || {}), content_format: "markdown" },
            }),
            signal: abortController.signal,
          });
        }
      } catch (error) {
        // Ignore abort errors
        if (error instanceof Error && error.name !== "AbortError") {
          console.error("Failed to auto-save text:", error);
        }
      } finally {
        // Only update saving state if this request wasn't aborted
        if (!abortController.signal.aborted) {
          setIsSaving(false);
        }
      }
    },
    [extractedText, htmlToMarkdown, onTextUpdate, conversationId, metadata],
  );

  // Initialize Tiptap editor (stores HTML)
  const handleEditorUpdate = useCallback(({ editor }: { editor: Editor }) => {
    const html = editor.getHTML();
    setEditedText(html);
  }, []);

  const editor = useEditor({
    editable: !readOnly,
    immediatelyRender: false, // Prevent SSR hydration mismatch in Next.js
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Placeholder.configure({ placeholder: "Edit extracted content here…" }),
      CharacterCount.configure({ limit: 500000 }),
      Link.configure({ openOnClick: true, autolink: true }),
      Image.configure({ inline: false, allowBase64: false }),
      UnderlineExtension,
    ],
    content: "<p></p>",
    onUpdate: handleEditorUpdate,
  });

  // Paste/drop images: upload to Supabase storage and insert by URL
  useEffect(() => {
    if (!editor) return;
    const view = editor.view;
    const handlePaste = async (event: ClipboardEvent) => {
      const items = event.clipboardData?.items;
      if (!items) return;

      for (const item of items) {
        if (item.kind !== "file") continue;
        const file = item.getAsFile();
        if (!file || !file.type.startsWith("image/")) continue;

        event.preventDefault();
        try {
          const url = await uploadImageToSupabase(file, conversationId);
          editor.chain().focus().setImage({ src: url }).run();
        } catch (uploadError) {
          console.error("Image upload failed", uploadError);
        }
      }
    };

    const handleDrop = async (event: DragEvent) => {
      if (!event.dataTransfer) return;
      const files = Array.from(event.dataTransfer.files ?? []);
      const image = files.find((file) => file.type.startsWith("image/"));
      if (!image) return;

      event.preventDefault();
      try {
        const url = await uploadImageToSupabase(image, conversationId);
        editor.chain().focus().setImage({ src: url }).run();
      } catch (uploadError) {
        console.error("Image upload failed", uploadError);
      }
    };

    view.dom.addEventListener("paste", handlePaste);
    view.dom.addEventListener("drop", handleDrop);
    return () => {
      view.dom.removeEventListener("paste", handlePaste);
      view.dom.removeEventListener("drop", handleDrop);
    };
  }, [editor, conversationId]);

  // Calculate text statistics
  const calculateTextStats = useCallback((text: string): TextStatistics => {
    const lines = text.split("\n");
    const paragraphs = text.split("\n\n").filter((p) => p.trim().length > 0);
    const words = text
      .trim()
      .split(/\s+/)
      .filter((w) => w.length > 0);

    return {
      character_count: text.length,
      word_count: words.length,
      line_count: lines.length,
      paragraph_count: paragraphs.length,
      estimated_read_time_minutes: Math.max(1, Math.ceil(words.length / 200)),
    };
  }, []);

  // Update text statistics when text changes (compute from plain text)
  useEffect(() => {
    if (!extractedText) {
      setTextStats(null);
      return;
    }
    const html = isLikelyHtml(extractedText)
      ? extractedText
      : markdownToHtml(extractedText);
    const plain = htmlToPlain(html);
    setTextStats(calculateTextStats(plain));
  }, [extractedText, calculateTextStats, htmlToPlain, markdownToHtml]);

  // Initialize/refresh editor content preserving formatting
  useEffect(() => {
    if (!editor) return;
    const html = isLikelyHtml(extractedText)
      ? extractedText
      : markdownToHtml(extractedText);
    setEditedText(html);
    editor.commands.setContent(html || "<p></p>");
  }, [extractedText, editor, markdownToHtml]);

  // Folder selection is handled in the sidebar; nothing to load here

  // Handle clicking outside to exit edit mode
  useEffect(() => {
    if (!isEditing) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const editorElement = document.querySelector(".ProseMirror");
      const toolbarElement = document.querySelector('[data-toolbar="true"]');

      if (
        editorElement &&
        !editorElement.contains(target) &&
        toolbarElement &&
        !toolbarElement.contains(target)
      ) {
        setIsEditing(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isEditing]);

  // Handle auto-save with proper cleanup
  useEffect(() => {
    if (!isEditing || !editedText) return;

    const timeoutId = setTimeout(() => {
      void handleAutoSave(editedText);
    }, 2000); // Auto-save after 2 seconds of no activity

    return () => {
      clearTimeout(timeoutId);
    };
  }, [editedText, isEditing, handleAutoSave]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      // Cleanup any pending saves on unmount
      if (saveAbortControllerRef.current) {
        saveAbortControllerRef.current.abort();
      }
    };
  }, []);

  // Handle approval actions
  const handleApprovalAction = async (action: ApprovalAction) => {
    if (!onApprovalAction) return;

    setIsLoading(true);
    try {
      const payload: ApprovalActionPayload | undefined =
        action === "edit_and_approve" ? { edited_text: editedText } : undefined;
      await onApprovalAction(action, payload);
      if (action === "edit_and_approve") {
        setIsEditing(false);
      }
    } catch (error) {
      console.error("Failed to process approval action:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // Listen for external edit toggles from sidebar
  useEffect(() => {
    const onToggle = (event: Event) => {
      const detail = (
        event as CustomEvent<{
          conversationId: number;
          action: "start" | "stop";
        }>
      ).detail;
      if (!detail) return;
      if (detail.conversationId === conversationId) {
        setIsEditing(detail.action === "start");
      }
    };
    document.addEventListener("feedme:toggle-edit", onToggle);
    return () => document.removeEventListener("feedme:toggle-edit", onToggle);
  }, [conversationId]);

  // Get processing method display info
  return (
    <Card className="border-0 shadow-none bg-transparent h-full">
      <CardContent className="flex h-full flex-col gap-4 p-0">
        {showProcessingSummary && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border/60 bg-muted/10 px-4 py-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn(
                  "inline-flex items-center gap-1 border",
                  processingSummary.badgeClass,
                )}
              >
                {processingSummary.icon}
                {processingSummary.label}
              </Badge>
              <span>{processingSummary.description}</span>
            </div>
            {confidenceBadge}
          </div>
        )}

        {textStats && (
          <div className="flex flex-wrap gap-4 rounded-md border border-border/40 bg-card/50 px-3 py-2 text-xs text-muted-foreground">
            <span>{textStats.word_count.toLocaleString()} words</span>
            <span>{textStats.paragraph_count.toLocaleString()} paragraphs</span>
            <span>
              ~{textStats.estimated_read_time_minutes.toLocaleString()} min read
            </span>
          </div>
        )}

        {metricBadges.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 text-xs">
            {metricBadges.map(({ key, label, value }) => (
              <Badge
                key={key}
                variant="secondary"
                className="bg-card text-foreground border-border/60 font-normal"
              >
                <span className="font-semibold">{label}</span>
                <span className="ml-1 text-muted-foreground/80">{value}</span>
              </Badge>
            ))}
          </div>
        )}

        {warnings.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
            <p className="font-medium">Warnings</p>
            <ul className="mt-1 list-disc pl-5">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex-1">
          {isEditing ? (
            <div
              className={cn(
                "relative flex h-full flex-col",
                fullPageMode ? "p-4" : "p-3",
              )}
            >
              <div
                className="flex flex-wrap items-center justify-between gap-2 pb-3 pr-12"
                data-toolbar="true"
              >
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1">
                    <Toggle
                      size="sm"
                      aria-label="Toggle bold"
                      pressed={!!editor?.isActive("bold")}
                      onPressedChange={() =>
                        editor?.chain().focus().toggleBold().run()
                      }
                    >
                      <Bold className="h-4 w-4" />
                    </Toggle>
                    <Toggle
                      size="sm"
                      aria-label="Toggle italic"
                      pressed={!!editor?.isActive("italic")}
                      onPressedChange={() =>
                        editor?.chain().focus().toggleItalic().run()
                      }
                    >
                      <Italic className="h-4 w-4" />
                    </Toggle>
                    <Toggle
                      size="sm"
                      aria-label="Toggle underline"
                      pressed={!!editor?.isActive("underline")}
                      onPressedChange={() => {
                        if (editor?.isActive("underline")) {
                          editor?.chain().focus().unsetMark("underline").run();
                        } else {
                          editor?.chain().focus().setMark("underline").run();
                        }
                      }}
                    >
                      <Underline className="h-4 w-4" />
                    </Toggle>
                    <Toggle
                      size="sm"
                      aria-label="Toggle code"
                      pressed={!!editor?.isActive("code")}
                      onPressedChange={() =>
                        editor?.chain().focus().toggleCode().run()
                      }
                    >
                      <Code className="h-4 w-4" />
                    </Toggle>
                  </div>
                  <ToggleGroup
                    type="single"
                    size="sm"
                    aria-label="List type"
                    value={
                      editor?.isActive("orderedList")
                        ? "ol"
                        : editor?.isActive("bulletList")
                          ? "ul"
                          : undefined
                    }
                    onValueChange={(val) => {
                      if (!editor) return;
                      if (val === "ul") {
                        editor.chain().focus().toggleBulletList().run();
                      } else if (val === "ol") {
                        editor.chain().focus().toggleOrderedList().run();
                      } else {
                        if (editor.isActive("orderedList"))
                          editor.chain().focus().toggleOrderedList().run();
                        if (editor.isActive("bulletList"))
                          editor.chain().focus().toggleBulletList().run();
                      }
                    }}
                  >
                    <ToggleGroupItem value="ul" aria-label="Bulleted list">
                      <List className="h-4 w-4" />
                    </ToggleGroupItem>
                    <ToggleGroupItem value="ol" aria-label="Numbered list">
                      <ListOrdered className="h-4 w-4" />
                    </ToggleGroupItem>
                  </ToggleGroup>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {isSaving ? (
                    <>
                      <div className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
                      Saving...
                    </>
                  ) : (
                    "Auto-saving enabled"
                  )}
                </div>
              </div>
              <div
                className={cn(
                  "font-sans text-foreground rounded-md border border-border/40 bg-[hsl(var(--brand-surface)/0.95)]",
                  fullPageMode
                    ? "max-h-[calc(78vh-56px)] overflow-y-auto p-4 pb-12"
                    : "max-h-[360px] overflow-y-auto p-3 pb-8",
                )}
              >
                <EditorContent
                  editor={editor}
                  className={cn(
                    "prose max-w-none leading-7 text-sm dark:prose-invert",
                    "prose-p:my-3 prose-li:my-1 prose-ul:my-3 prose-ol:my-3",
                    "prose-headings:mt-6 prose-headings:mb-3",
                    "[&_code.agent-name]:bg-blue-100 [&_code.agent-name]:text-blue-900 [&_code.agent-name]:px-1 [&_code.agent-name]:py-0.5 [&_code.agent-name]:rounded [&_code.agent-name]:text-sm [&_code.agent-name]:font-semibold",
                    "[&_code.customer-name]:bg-amber-100 [&_code.customer-name]:text-amber-900 [&_code.customer-name]:px-1 [&_code.customer-name]:py-0.5 [&_code.customer-name]:rounded [&_code.customer-name]:text-sm [&_code.customer-name]:font-semibold",
                  )}
                />
              </div>
              <div className="absolute bottom-4 right-4 rounded bg-background px-2 py-1 text-xs text-muted-foreground shadow">
                {editedText.length.toLocaleString()} characters
              </div>
            </div>
          ) : purifyLoading ? (
            <div
              className={cn(
                "flex items-center justify-center rounded-md border border-border/40 bg-[hsl(var(--brand-surface)/0.95)]",
                fullPageMode ? "min-h-[calc(82vh)]" : "min-h-[380px]",
              )}
            >
              <div className="text-center space-y-2">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
                <p className="text-sm text-muted-foreground">
                  Loading content viewer...
                </p>
              </div>
            </div>
          ) : (
            <div
              className={cn(
                "prose max-w-none font-sans text-sm leading-relaxed dark:prose-invert rounded-md border border-border/40 text-foreground bg-[hsl(var(--brand-surface)/0.95)]",
                fullPageMode
                  ? "max-h-[calc(82vh)] overflow-y-auto p-6 pb-12"
                  : "max-h-[380px] overflow-y-auto p-4 pb-8",
                "[&_code.agent-name]:bg-blue-100 [&_code.agent-name]:text-blue-900 [&_code.agent-name]:px-1 [&_code.agent-name]:py-0.5 [&_code.agent-name]:rounded [&_code.agent-name]:text-sm [&_code.agent-name]:font-semibold [&_code.agent-name]:not-italic",
                "[&_code.customer-name]:bg-amber-100 [&_code.customer-name]:text-amber-900 [&_code.customer-name]:px-1 [&_code.customer-name]:py-0.5 [&_code.customer-name]:rounded [&_code.customer-name]:text-sm [&_code.customer-name]:font-semibold [&_code.customer-name]:not-italic",
              )}
              dangerouslySetInnerHTML={{
                __html: sanitizeHtml(
                  isLikelyHtml(extractedText)
                    ? styleNamesInHtml(extractedText)
                    : markdownToHtml(extractedText),
                ),
              }}
            />
          )}
        </div>

        {showApprovalControls && approvalStatus === "pending" && (
          <div className="rounded-lg border border-border/60 bg-muted/20 px-4 py-3">
            <p className="text-xs text-muted-foreground mb-3">
              Review and decide whether this conversation should be added to the
              knowledge base.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                onClick={() => handleApprovalAction("approve")}
                disabled={isLoading}
                className="text-green-700 border-green-300 hover:bg-green-50"
              >
                <CheckCircle2 className="h-4 w-4 mr-1" />
                Approve
              </Button>
              <Button
                variant="outline"
                onClick={() => handleApprovalAction("reject")}
                disabled={isLoading}
                className="text-red-700 border-red-300 hover:bg-red-50"
              >
                <X className="h-4 w-4 mr-1" />
                Reject
              </Button>
              {isEditing && (
                <Button
                  onClick={() => handleApprovalAction("edit_and_approve")}
                  disabled={isLoading || editedText === extractedText}
                  className="text-blue-700 bg-blue-50 border-blue-300 hover:bg-blue-100"
                >
                  <Edit3 className="h-4 w-4 mr-1" />
                  Edit & Approve
                </Button>
              )}
            </div>
          </div>
        )}

        {approvalStatus === "approved" && approvedBy && (
          <div className="rounded-lg border border-border/60 bg-muted/10 px-4 py-3 text-sm text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <span>Approved by {approvedBy}</span>
              {approvedAt && (
                <span>
                  •{" "}
                  {formatDistanceToNow(new Date(approvedAt), {
                    addSuffix: true,
                  })}
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Export the component wrapped with error boundary
export default withErrorBoundary(UnifiedTextCanvas);
