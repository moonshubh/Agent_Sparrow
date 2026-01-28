'use client';

import React, { useState, useCallback, useMemo, useRef } from 'react';
import { Eye, Edit3, FileText, Image as ImageIcon, Maximize2 } from 'lucide-react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/shared/lib/utils';
import type { Artifact } from './types';
import { useArtifactStore } from './ArtifactContext';
import { useAgent } from '@/features/librechat/AgentContext';
import { sessionsAPI } from '@/services/api/endpoints/sessions';
import { TipTapEditor } from '@/features/librechat/components/tiptap/TipTapEditor';
import { serializeArtifact } from './serialization';
import { findImageByTitle, resolveArtifactImageByRef, resolveImageSrc } from './imageUtils';

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
        const src = resolveImageSrc(imageArtifact);
        if (src) {
          const altText = title || imageArtifact.title || 'Image';
          return `![${altText}](${src})`;
        }
      }

      return `\n\n> 📷 *[Image: ${title || 'Unknown'}]*\n\n`;
    };

    let updated = content.replace(artifactRegex, (match, title) => {
      const imageArtifact = findImageByTitle(artifactsById, title);
      return replaceWithImage(title, imageArtifact);
    });

    updated = updated.replace(artifactIdRegex, (match, alt, ref) => {
      const normalizedRef = String(ref || '').trim();
      const imageArtifact = resolveArtifactImageByRef(artifactsById, normalizedRef, alt || normalizedRef);

      return replaceWithImage(alt || normalizedRef, imageArtifact);
    });

    return updated;
  }, [content, artifactsById]);
}

interface ArticleEditorProps {
  artifact: Artifact;
}

interface LightboxImage {
  src: string;
  alt: string;
  pageUrl?: string;
}


/**
 * ArticleEditor - Rich article editor with markdown support
 *
 * Features:
 * - Toggle between edit and preview modes
 * - WYSIWYG editing with TipTap
 * - Live preview with rendered markdown
 * - Auto-save on blur/click-away
 * - Support for embedded images
 */
export function ArticleEditor({ artifact }: ArticleEditorProps) {
  const { addArtifact, getArtifact, getArtifactsByMessage } = useArtifactStore();
  const { sessionId, updateMessageMetadata, resolvePersistedMessageId } = useAgent();
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(() => artifact.content);
  const lastSavedRef = useRef(artifact.content);

  // Transform content with inline artifacts for preview
  const processedContent = useInlineArtifacts(content);

  const persistArtifacts = useCallback(async (messageId: string) => {
    if (!sessionId || !messageId) return;
    const artifacts = getArtifactsByMessage(messageId).filter((item) =>
      item.type === 'article' || item.type === 'kb-article' || item.type === 'image'
    );
    if (!artifacts.length) return;
    const serialized = artifacts
      .map(serializeArtifact)
      .filter((item) => item.type !== 'image' || Boolean(item.imageUrl || item.imageData));

    const persistedId = resolvePersistedMessageId(messageId);
    if (!persistedId) return;

    await sessionsAPI.updateMessage(sessionId, persistedId, {
      metadata: { artifacts: serialized },
    });
    updateMessageMetadata(messageId, { artifacts: serialized });
  }, [getArtifactsByMessage, resolvePersistedMessageId, sessionId, updateMessageMetadata]);

  const handleSave = useCallback(async (markdown: string) => {
    if (markdown === lastSavedRef.current) return;

    const previousContent = lastSavedRef.current;
    const previousArtifact = getArtifact(artifact.id);

    setContent(markdown);
    addArtifact({
      ...artifact,
      content: markdown,
      lastUpdateTime: Date.now(),
    });

    try {
      await persistArtifacts(artifact.messageId);
      lastSavedRef.current = markdown;
    } catch (error) {
      setContent(previousContent);
      if (previousArtifact) {
        addArtifact(previousArtifact);
      }
      console.error('[ArticleEditor] Failed to persist artifact edits', error);
      throw error;
    }
  }, [addArtifact, artifact, getArtifact, persistArtifacts]);

  const handleExitEditing = useCallback(() => {
    setIsEditing(false);
  }, []);

  // State for image lightbox
  const [lightboxImage, setLightboxImage] = useState<LightboxImage | null>(null);

  // Track failed images
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set());

  const resolveHttpUrl = useCallback((value?: string) => {
    if (!value) return undefined;
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    try {
      const url = new URL(trimmed);
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        return url.toString();
      }
      return undefined;
    } catch {
      return undefined;
    }
  }, []);

  // Custom markdown components for preview
  const markdownComponents = useMemo((): Partial<Components> => ({
    // Style images with proper sizing and click-to-zoom
    img: ({
      node: _node,
      src,
      alt,
      title,
      className,
      ...props
    }: React.ImgHTMLAttributes<HTMLImageElement> & { node?: unknown }) => {
      const srcString = typeof src === 'string' ? src : undefined;
      const caption = typeof alt === 'string' ? alt : '';
      const displayAlt = caption || 'Article image';
      const isBase64 = srcString?.startsWith('data:') ?? false;
      const pageUrl = resolveHttpUrl(typeof title === 'string' ? title : undefined);
      const hasFailed = Boolean(srcString && failedImages.has(srcString));
      const isMissing = !srcString;
      const shouldShowCaption = caption && caption !== 'Article image';

      const handleImageError = () => {
        if (srcString) {
          setFailedImages((prev) => new Set(prev).add(srcString));
        }
      };

      if (isMissing || hasFailed) {
        return (
          <span className="block my-6 mx-auto max-w-full">
            <span className="block relative rounded-xl border border-border/50 bg-secondary/30 p-8 text-center">
              <ImageIcon className="h-12 w-12 mx-auto mb-3 text-muted-foreground/50" />
              <span className="block text-sm text-muted-foreground">
                {isMissing ? 'Image unavailable' : 'Image failed to load'}
              </span>
              {shouldShowCaption && (
                <span className="block text-xs text-muted-foreground/70 mt-1 italic">
                  {caption}
                </span>
              )}
            </span>
          </span>
        );
      }

      const openLightbox = () => {
        setLightboxImage({ src: srcString, alt: displayAlt, pageUrl });
      };

      return (
        <span className="block my-6 mx-auto max-w-full">
          <span
            className="block relative group cursor-pointer"
            onClick={openLightbox}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openLightbox();
              }
            }}
          >
            <img
              src={srcString}
              alt={displayAlt}
              className={cn(
                'w-full h-auto rounded-xl shadow-lg',
                'border border-border/50',
                'transition-all duration-200 group-hover:shadow-xl',
                isBase64 && 'bg-secondary/20',
                className
              )}
              loading="lazy"
              onError={handleImageError}
              {...props}
            />
            <span className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/20 rounded-xl">
              <span className="bg-background/90 backdrop-blur-sm px-3 py-1.5 rounded-lg text-xs font-medium text-foreground inline-flex items-center gap-1.5">
                <Maximize2 className="h-3.5 w-3.5" />
                Click to enlarge
              </span>
            </span>
          </span>
          {shouldShowCaption && (
            <span className="block text-center text-sm text-muted-foreground mt-2 italic">
              {caption}
            </span>
          )}
        </span>
      );
    },
    // Style headings
    h1: ({
      node: _node,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLHeadingElement> & { node?: unknown }) => (
      <h1
        {...props}
        className={cn(
          'text-2xl font-bold mt-6 mb-3 text-foreground border-b border-border pb-2',
          className
        )}
      >
        {children}
      </h1>
    ),
    h2: ({
      node: _node,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLHeadingElement> & { node?: unknown }) => (
      <h2
        {...props}
        className={cn('text-xl font-semibold mt-5 mb-2 text-foreground', className)}
      >
        {children}
      </h2>
    ),
    h3: ({
      node: _node,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLHeadingElement> & { node?: unknown }) => (
      <h3
        {...props}
        className={cn('text-lg font-medium mt-4 mb-2 text-foreground', className)}
      >
        {children}
      </h3>
    ),
    // Style paragraphs
    p: ({
      node: _node,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLParagraphElement> & { node?: unknown }) => (
      <p
        {...props}
        className={cn('my-3 text-foreground/90 leading-relaxed', className)}
      >
        {children}
      </p>
    ),
    // Style blockquotes
    blockquote: ({
      node: _node,
      children,
      className,
      ...props
    }: React.BlockquoteHTMLAttributes<HTMLQuoteElement> & { node?: unknown }) => (
      <blockquote
        {...props}
        className={cn(
          'border-l-4 border-terracotta-400 pl-4 my-4 italic text-muted-foreground bg-secondary/30 py-2 rounded-r',
          className
        )}
      >
        {children}
      </blockquote>
    ),
    // Style lists
    ul: ({
      node: _node,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLUListElement> & { node?: unknown }) => (
      <ul
        {...props}
        className={cn('list-disc list-inside my-3 space-y-1 text-foreground/90', className)}
      >
        {children}
      </ul>
    ),
    ol: ({
      node: _node,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLOListElement> & { node?: unknown }) => (
      <ol
        {...props}
        className={cn(
          'list-decimal list-inside my-3 space-y-1 text-foreground/90',
          className
        )}
      >
        {children}
      </ol>
    ),
    // Style code
    code: ({
      node: _node,
      inline,
      children,
      className,
      ...props
    }: React.HTMLAttributes<HTMLElement> & { inline?: boolean; node?: unknown }) => {
      const isInlineCode = inline ?? !String(className ?? '').includes('language-');
      return isInlineCode ? (
        <code
          {...props}
          className={cn(
            'px-1.5 py-0.5 rounded bg-secondary text-terracotta-300 text-sm font-mono',
            className
          )}
        >
          {children}
        </code>
      ) : (
        <code
          {...props}
          className={cn(
            'block p-3 rounded-lg bg-secondary text-sm font-mono overflow-x-auto',
            className
          )}
        >
          {children}
        </code>
      );
    },
    // Style links
    a: ({
      node: _node,
      href,
      children,
      className,
      ...props
    }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { node?: unknown }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        {...props}
        className={cn(
          'text-terracotta-400 hover:text-terracotta-300 underline underline-offset-2',
          className
        )}
      >
        {children}
      </a>
    ),
  }), [failedImages, resolveHttpUrl]);

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

        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {isEditing ? (
          <TipTapEditor
            initialContent={content}
            onSave={handleSave}
            onExit={handleExitEditing}
            onCancel={handleExitEditing}
            placeholder={
              artifact.type === 'kb-article'
                ? 'Write your knowledge base article...'
                : 'Write your article...'
            }
            className="lc-article-editor"
          />
        ) : (
          /* Preview mode - Rendered markdown with inline artifacts */
          <div
            className="p-6 max-w-3xl mx-auto overflow-auto"
            onDoubleClick={() => setIsEditing(true)}
          >
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
          <div
            className="relative max-w-[90vw] max-h-[90vh]"
            onClick={(event) => event.stopPropagation()}
          >
            <img
              src={lightboxImage.src}
              alt={lightboxImage.alt}
              className="max-w-full max-h-[90vh] rounded-xl shadow-2xl object-contain"
            />
            {lightboxImage.alt && lightboxImage.alt !== 'Article image' && (
              <p className="text-center text-white/80 mt-3 text-sm">{lightboxImage.alt}</p>
            )}
            <div className="flex items-center justify-center gap-4 mt-3 text-sm">
              <a
                href={lightboxImage.src}
                target="_blank"
                rel="noopener noreferrer"
                className="text-white/80 hover:text-white underline underline-offset-4"
              >
                Open image
              </a>
              {lightboxImage.pageUrl && (
                <a
                  href={lightboxImage.pageUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white/80 hover:text-white underline underline-offset-4"
                >
                  Open source page
                </a>
              )}
            </div>
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
