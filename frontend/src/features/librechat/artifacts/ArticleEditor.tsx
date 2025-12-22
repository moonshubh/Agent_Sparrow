'use client';

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { Eye, Edit3, Save, RotateCcw, FileText, Image as ImageIcon, Link, Bold, Italic, Heading1, Heading2, List, ListOrdered, Quote, Code, Maximize2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/shared/lib/utils';
import type { Artifact } from './types';
import { useArtifactStore } from './ArtifactContext';

/**
 * Check if content has actual text beyond just markdown images and separators.
 * Used to detect image-only articles and show appropriate UX.
 */
function hasTextContent(content: string): boolean {
  if (!content) return false;

  // Strip markdown images and separators, check if text remains
  const withoutImages = content
    .replace(/!\[.*?\]\(.*?\)/g, '')           // Remove markdown images
    .replace(/---\s*##?\s*Images?\s*/gi, '')   // Remove "--- ## Images" separators
    .replace(/#\s*Generated\s*Images?\s*/gi, '') // Remove "# Generated Images" header
    .replace(/\n{2,}/g, '\n')                  // Collapse multiple newlines
    .trim();

  return withoutImages.length > 0;
}

function normalizeImageRef(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function resolveImageMarkdown(artifact: Artifact, altText: string): string | null {
  if (artifact.imageData) {
    const mimeType = artifact.mimeType || 'image/png';
    return `![${altText}](data:${mimeType};base64,${artifact.imageData})`;
  }

  if (artifact.content) {
    return `![${altText}](${artifact.content})`;
  }

  return null;
}

function findImageByTitle(artifactsById: Record<string, Artifact>, title: string): Artifact | undefined {
  const normalizedTitle = normalizeImageRef(title);
  if (!normalizedTitle) return undefined;

  const imageArtifacts = Object.values(artifactsById).filter((a) => a.type === 'image');

  const exactMatch = imageArtifacts.find(
    (a) => normalizeImageRef(a.title || '') === normalizedTitle
  );
  if (exactMatch) return exactMatch;

  const partialMatch = imageArtifacts.find((a) => {
    const normalizedCandidate = normalizeImageRef(a.title || '');
    return normalizedCandidate.includes(normalizedTitle) || normalizedTitle.includes(normalizedCandidate);
  });
  if (partialMatch) return partialMatch;

  return imageArtifacts.find(
    (a) => (a.title || '').toLowerCase().includes(title.toLowerCase())
  );
}

/**
 * Parses ::artifact{type="image" title="..."} syntax and replaces with actual images
 * from the artifact store
 */
function useInlineArtifacts(content: string): string {
  const { artifactsById } = useArtifactStore();

  return useMemo(() => {
    if (!content) return content;

    // Match ::artifact{type="image" title="..."} or ::artifact{type='image' title='...'}
    const artifactRegex = /::artifact\{type=["']image["']\s+title=["']([^"']+)["']\}/g;
    const artifactIdRegex = /!\[([^\]]*)\]\(\s*artifact:([^)]+)\s*\)/gi;

    const replaceWithImage = (title: string, imageArtifact?: Artifact) => {
      if (imageArtifact) {
        const markdown = resolveImageMarkdown(imageArtifact, title || imageArtifact.title || 'Image');
        if (markdown) return markdown;
      }

      return `\n\n> 📷 *[Image: ${title || 'Unknown'}]*\n\n`;
    };

    let updated = content.replace(artifactRegex, (match, title) => {
      const imageArtifact = findImageByTitle(artifactsById, title);
      return replaceWithImage(title, imageArtifact);
    });

    updated = updated.replace(artifactIdRegex, (match, alt, ref) => {
      const normalizedRef = String(ref || '').trim();
      const directMatch = artifactsById[normalizedRef];
      const imageArtifact = directMatch?.type === 'image'
        ? directMatch
        : Object.values(artifactsById).find((a) =>
            a.type === 'image' &&
            (a.id.toLowerCase() === normalizedRef.toLowerCase() ||
              a.id.toLowerCase().includes(normalizedRef.toLowerCase()))
          ) || findImageByTitle(artifactsById, alt || normalizedRef);

      return replaceWithImage(alt || normalizedRef, imageArtifact);
    });

    return updated;
  }, [content, artifactsById]);
}

interface ArticleEditorProps {
  artifact: Artifact;
}

const TOOLBAR_ACTIONS = [
  { icon: Bold, label: 'Bold (Ctrl+B)', before: '**', after: '**', placeholder: 'bold text' },
  { icon: Italic, label: 'Italic (Ctrl+I)', before: '*', after: '*', placeholder: 'italic text' },
  { icon: Heading1, label: 'Heading 1', before: '\n# ', after: '\n', placeholder: 'Heading' },
  { icon: Heading2, label: 'Heading 2', before: '\n## ', after: '\n', placeholder: 'Subheading' },
  { icon: List, label: 'Bullet List', before: '\n- ', after: '\n', placeholder: 'List item' },
  { icon: ListOrdered, label: 'Numbered List', before: '\n1. ', after: '\n', placeholder: 'List item' },
  { icon: Quote, label: 'Quote', before: '\n> ', after: '\n', placeholder: 'Quote' },
  { icon: Code, label: 'Code', before: '`', after: '`', placeholder: 'code' },
  { icon: Link, label: 'Link', before: '[', after: '](url)', placeholder: 'link text' },
  { icon: ImageIcon, label: 'Image', before: '![', after: '](image-url)', placeholder: 'alt text' },
];

/**
 * Toolbar button component for the editor
 */
function ToolbarButton({
  icon: Icon,
  label,
  onClick,
  active = false,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'p-1.5 rounded hover:bg-secondary/80 transition-colors',
        active ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground'
      )}
      title={label}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

/**
 * ArticleEditor - Rich article editor with markdown support
 *
 * Features:
 * - Toggle between edit and preview modes
 * - Markdown toolbar for formatting
 * - Live preview with rendered markdown
 * - Auto-save changes to artifact store
 * - Support for embedded images
 */
export function ArticleEditor({ artifact }: ArticleEditorProps) {
  const { addArtifact } = useArtifactStore();
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(() => artifact.content);
  const [hasChanges, setHasChanges] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const originalContent = useRef(artifact.content);

  // Transform content with inline artifacts for preview
  const processedContent = useInlineArtifacts(content);

  // Handle content changes
  const handleContentChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newContent = e.target.value;
    setContent(newContent);
    setHasChanges(newContent !== originalContent.current);
  }, []);

  // Save changes to artifact store
  const handleSave = useCallback(() => {
    addArtifact({
      ...artifact,
      content,
      lastUpdateTime: Date.now(),
    });
    originalContent.current = content;
    setHasChanges(false);
  }, [addArtifact, artifact, content]);

  // Revert to original content
  const handleRevert = useCallback(() => {
    setContent(originalContent.current);
    setHasChanges(false);
  }, []);

  // Insert markdown formatting at cursor position
  const insertFormatting = useCallback((before: string, after: string = '', placeholder: string = '') => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = content.substring(start, end);
    const textToInsert = selectedText || placeholder;

    const newContent =
      content.substring(0, start) +
      before + textToInsert + after +
      content.substring(end);

    setContent(newContent);
    setHasChanges(newContent !== originalContent.current);

    // Restore focus and selection
    setTimeout(() => {
      textarea.focus();
      const newCursorPos = start + before.length + textToInsert.length;
      textarea.setSelectionRange(
        selectedText ? newCursorPos + after.length : start + before.length,
        selectedText ? newCursorPos + after.length : start + before.length + placeholder.length
      );
    }, 0);
  }, [content]);

  // Handle keyboard shortcuts
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.ctrlKey || e.metaKey) {
      switch (e.key.toLowerCase()) {
        case 'b':
          e.preventDefault();
          insertFormatting('**', '**', 'bold text');
          break;
        case 'i':
          e.preventDefault();
          insertFormatting('*', '*', 'italic text');
          break;
        case 's':
          e.preventDefault();
          handleSave();
          break;
      }
    }
  }, [insertFormatting, handleSave]);

  // State for image lightbox
  const [lightboxImage, setLightboxImage] = useState<{ src: string; alt: string } | null>(null);

  // Custom markdown components for preview
  const markdownComponents = useMemo(() => ({
    // Style images with proper sizing and click-to-zoom
    img: ({ src, alt, ...props }: any) => {
      const isBase64 = src?.startsWith('data:');
      return (
        <figure className="my-6 mx-auto max-w-full">
          <div className="relative group cursor-pointer" onClick={() => setLightboxImage({ src, alt })}>
            <img
              src={src}
              alt={alt || 'Article image'}
              className={cn(
                'w-full h-auto rounded-xl shadow-lg',
                'border border-border/50',
                'transition-all duration-200 group-hover:shadow-xl',
                isBase64 && 'bg-secondary/20' // Background for generated images
              )}
              loading="lazy"
              {...props}
            />
            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/20 rounded-xl">
              <div className="bg-background/90 backdrop-blur-sm px-3 py-1.5 rounded-lg text-xs font-medium text-foreground flex items-center gap-1.5">
                <Maximize2 className="h-3.5 w-3.5" />
                Click to enlarge
              </div>
            </div>
          </div>
          {alt && alt !== 'Article image' && (
            <figcaption className="text-center text-sm text-muted-foreground mt-2 italic">
              {alt}
            </figcaption>
          )}
        </figure>
      );
    },
    // Style headings
    h1: ({ children, ...props }: any) => (
      <h1 className="text-2xl font-bold mt-6 mb-3 text-foreground border-b border-border pb-2" {...props}>
        {children}
      </h1>
    ),
    h2: ({ children, ...props }: any) => (
      <h2 className="text-xl font-semibold mt-5 mb-2 text-foreground" {...props}>
        {children}
      </h2>
    ),
    h3: ({ children, ...props }: any) => (
      <h3 className="text-lg font-medium mt-4 mb-2 text-foreground" {...props}>
        {children}
      </h3>
    ),
    // Style paragraphs
    p: ({ children, ...props }: any) => (
      <p className="my-3 text-foreground/90 leading-relaxed" {...props}>
        {children}
      </p>
    ),
    // Style blockquotes
    blockquote: ({ children, ...props }: any) => (
      <blockquote
        className="border-l-4 border-terracotta-400 pl-4 my-4 italic text-muted-foreground bg-secondary/30 py-2 rounded-r"
        {...props}
      >
        {children}
      </blockquote>
    ),
    // Style lists
    ul: ({ children, ...props }: any) => (
      <ul className="list-disc list-inside my-3 space-y-1 text-foreground/90" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }: any) => (
      <ol className="list-decimal list-inside my-3 space-y-1 text-foreground/90" {...props}>
        {children}
      </ol>
    ),
    // Style code
    code: ({ inline, children, ...props }: any) => (
      inline ? (
        <code className="px-1.5 py-0.5 rounded bg-secondary text-terracotta-300 text-sm font-mono" {...props}>
          {children}
        </code>
      ) : (
        <code className="block p-3 rounded-lg bg-secondary text-sm font-mono overflow-x-auto" {...props}>
          {children}
        </code>
      )
    ),
    // Style links
    a: ({ href, children, ...props }: any) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-terracotta-400 hover:text-terracotta-300 underline underline-offset-2"
        {...props}
      >
        {children}
      </a>
    ),
  }), []);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-secondary/20">
        <div className="flex items-center gap-1">
          {/* Mode toggle */}
          <div className="flex items-center bg-secondary rounded-lg p-0.5 mr-3">
            <button
              onClick={() => setIsEditing(false)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors',
                !isEditing
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Eye className="h-3.5 w-3.5" />
              Preview
            </button>
            <button
              onClick={() => setIsEditing(true)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors',
                isEditing
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Edit3 className="h-3.5 w-3.5" />
              Edit
            </button>
          </div>

          {/* Formatting toolbar (only in edit mode) */}
          {isEditing && (
            <div className="flex items-center gap-0.5 border-l border-border pl-3">
              {TOOLBAR_ACTIONS.map(({ icon, label, before, after, placeholder }) => (
                <ToolbarButton
                  key={label}
                  icon={icon}
                  label={label}
                  onClick={() => insertFormatting(before, after, placeholder)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Save/Revert buttons */}
        {isEditing && hasChanges && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleRevert}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Revert
            </button>
            <button
              onClick={handleSave}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-terracotta-500 text-white hover:bg-terracotta-600 transition-colors"
            >
              <Save className="h-3.5 w-3.5" />
              Save
            </button>
          </div>
        )}

        {/* Unsaved indicator */}
        {hasChanges && (
          <span className="text-xs text-amber-400 ml-2">Unsaved changes</span>
        )}
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {isEditing ? (
          /* Edit mode - Markdown textarea */
          <textarea
            ref={textareaRef}
            value={content}
            onChange={handleContentChange}
            onKeyDown={handleKeyDown}
            className={cn(
              'w-full h-full p-4 bg-background text-foreground font-mono text-sm',
              'resize-none focus:outline-none focus:ring-0',
              'placeholder:text-muted-foreground'
            )}
            placeholder="Write your article in Markdown...

# Heading 1
## Heading 2

**Bold text** and *italic text*

- Bullet point
1. Numbered list

> Blockquote

![Image alt text](image-url)
[Link text](url)"
            spellCheck="true"
          />
        ) : (
          /* Preview mode - Rendered markdown with inline artifacts */
          <div className="p-6 max-w-3xl mx-auto overflow-auto">
            {content ? (
              <article className="prose prose-invert prose-sm max-w-none">
                {/* Show informative message for images-only articles */}
                {!hasTextContent(content) && (
                  <div className="mb-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                    <p className="text-amber-400 text-sm flex items-center gap-2 m-0">
                      <ImageIcon className="h-4 w-4 flex-shrink-0" />
                      This article contains images. Click Edit to add text content.
                    </p>
                  </div>
                )}
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents}
                >
                  {processedContent}
                </ReactMarkdown>
              </article>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
                <FileText className="h-12 w-12 mb-3 opacity-50" />
                <p className="text-sm">No content yet</p>
                <button
                  onClick={() => setIsEditing(true)}
                  className="mt-2 text-xs text-terracotta-400 hover:text-terracotta-300"
                >
                  Start writing
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Image Lightbox Modal */}
      {lightboxImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setLightboxImage(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]">
            <img
              src={lightboxImage.src}
              alt={lightboxImage.alt}
              className="max-w-full max-h-[90vh] rounded-xl shadow-2xl object-contain"
            />
            {lightboxImage.alt && lightboxImage.alt !== 'Article image' && (
              <p className="text-center text-white/80 mt-3 text-sm">{lightboxImage.alt}</p>
            )}
            <button
              onClick={() => setLightboxImage(null)}
              className="absolute -top-3 -right-3 bg-background text-foreground rounded-full p-2 shadow-lg hover:bg-secondary transition-colors"
              aria-label="Close lightbox"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ArticleEditor;
