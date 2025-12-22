'use client';

import React, { memo, useEffect, useRef, useState, useCallback } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, Download, FileImage, Code, Eye, AlertCircle } from 'lucide-react';
import { TransformWrapper, TransformComponent, ReactZoomPanPinchRef } from 'react-zoom-pan-pinch';
import mermaid from 'mermaid';
import { cn } from '@/shared/lib/utils';
import type { Artifact } from './types';

/**
 * Sanitize mermaid content to fix common parsing issues.
 * Models sometimes generate invalid syntax like <br/> tags.
 */
function sanitizeMermaidContent(content: string): string {
  let sanitized = content;

  // Replace <br/> and <br> tags with newlines in node labels
  sanitized = sanitized.replace(/<br\s*\/?>/gi, '\\n');

  // Remove HTML entities that might cause issues
  sanitized = sanitized.replace(/&nbsp;/g, ' ');
  sanitized = sanitized.replace(/&amp;/g, '&');
  sanitized = sanitized.replace(/&lt;/g, '<');
  sanitized = sanitized.replace(/&gt;/g, '>');

  // Fix parentheses inside node labels that cause parsing issues
  sanitized = sanitized.replace(/\[([^\]]*)\(([^)]*)\)([^\]]*)\]/g, (match, before, inner, after) => {
    return `[${before}${inner}${after}]`;
  });

  return sanitized;
}

interface MermaidPreviewProps {
  content: string;
  id: string;
  onSvgReady?: (svg: string) => void;
}

/**
 * MermaidPreview - Renders mermaid diagram with zoom/pan support
 */
const MermaidPreview = memo(function MermaidPreview({ content, id, onSvgReady }: MermaidPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const transformRef = useRef<ReactZoomPanPinchRef>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const renderDiagram = async () => {
      if (!content) {
        setError('No diagram content provided');
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        // Generate unique ID for this render
        const rendererId = `mermaid-editor-${id}-${Date.now()}`;

        // Sanitize content
        const sanitizedContent = sanitizeMermaidContent(content);

        // Render the diagram
        const { svg: renderedSvg } = await mermaid.render(rendererId, sanitizedContent);

        if (!cancelled) {
          setSvg(renderedSvg);
          setIsLoading(false);
          onSvgReady?.(renderedSvg);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Mermaid render error:', err);
          setError(err instanceof Error ? err.message : 'Failed to render diagram');
          setIsLoading(false);
        }
      }
    };

    // Debounce rendering to avoid too many renders while typing
    const timeoutId = setTimeout(renderDiagram, 300);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [content, id, onSvgReady]);

  const handleReset = useCallback(() => {
    if (transformRef.current) {
      transformRef.current.resetTransform();
    }
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground bg-secondary/30">
        <div className="flex items-center gap-2">
          <div className="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full" />
          <span className="text-sm">Rendering...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 h-full flex flex-col items-center justify-center bg-red-500/5">
        <AlertCircle className="h-8 w-8 text-red-400 mb-2" />
        <p className="text-red-400 font-medium text-sm">Render Error</p>
        <p className="text-red-300 text-xs mt-1 text-center max-w-xs">{error}</p>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full bg-[#1a1816]">
      <TransformWrapper
        ref={transformRef}
        initialScale={1}
        minScale={0.1}
        maxScale={4}
        limitToBounds={false}
        centerOnInit={true}
        wheel={{ step: 0.1 }}
        panning={{ velocityDisabled: true }}
      >
        {({ zoomIn, zoomOut }) => (
          <>
            <TransformComponent
              wrapperStyle={{ width: '100%', height: '100%', overflow: 'hidden' }}
              contentStyle={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <div
                ref={containerRef}
                className="mermaid-preview p-8"
                dangerouslySetInnerHTML={{ __html: svg }}
              />
            </TransformComponent>
            
            {/* Zoom controls */}
            <div className="absolute bottom-3 right-3 flex items-center gap-1 bg-card/90 backdrop-blur-sm rounded-lg p-1 border border-border shadow-lg">
              <button
                onClick={() => zoomIn(0.2)}
                className="p-1.5 rounded hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
                title="Zoom in"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <button
                onClick={() => zoomOut(0.2)}
                className="p-1.5 rounded hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
                title="Zoom out"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <div className="w-px h-4 bg-border mx-0.5" />
              <button
                onClick={handleReset}
                className="p-1.5 rounded hover:bg-secondary transition-colors text-muted-foreground hover:text-foreground"
                title="Reset view"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            </div>
          </>
        )}
      </TransformWrapper>
    </div>
  );
});

interface MermaidEditorProps {
  artifact: Artifact;
  onContentChange?: (content: string) => void;
}

/**
 * MermaidEditor - Split view editor for mermaid diagrams
 * 
 * Features:
 * - Left panel: Text editor for mermaid source
 * - Right panel: Live preview with zoom/pan
 * - Export to SVG and PNG
 */
export const MermaidEditor = memo(function MermaidEditor({ artifact, onContentChange }: MermaidEditorProps) {
  const [editedContent, setEditedContent] = useState(artifact.content);
  const [currentSvg, setCurrentSvg] = useState<string>('');
  const [viewMode, setViewMode] = useState<'split' | 'code' | 'preview'>('split');
  const [isExporting, setIsExporting] = useState(false);

  // Update content when artifact changes
  useEffect(() => {
    setEditedContent(artifact.content);
  }, [artifact.content]);

  const handleContentChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newContent = e.target.value;
    setEditedContent(newContent);
    onContentChange?.(newContent);
  }, [onContentChange]);

  const handleSvgReady = useCallback((svg: string) => {
    setCurrentSvg(svg);
  }, []);

  /**
   * Export diagram as SVG file
   */
  const handleExportSvg = useCallback(async () => {
    if (!currentSvg) return;
    
    setIsExporting(true);
    try {
      // Create blob with proper SVG headers
      const svgBlob = new Blob([currentSvg], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      
      // Create download link
      const link = document.createElement('a');
      link.href = url;
      link.download = `${artifact.title.replace(/\s+/g, '_')}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export SVG:', err);
    } finally {
      setIsExporting(false);
    }
  }, [currentSvg, artifact.title]);

  /**
   * Export diagram as PNG file
   */
  const handleExportPng = useCallback(async () => {
    if (!currentSvg) return;
    
    setIsExporting(true);
    try {
      // Create an image from the SVG
      const svgBlob = new Blob([currentSvg], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      
      const img = new Image();
      img.onload = () => {
        // Create canvas with proper dimensions
        const canvas = document.createElement('canvas');
        const scale = 2; // Higher resolution
        canvas.width = img.width * scale;
        canvas.height = img.height * scale;
        
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          URL.revokeObjectURL(url);
          setIsExporting(false);
          return;
        }
        
        // Fill background
        ctx.fillStyle = '#1a1816';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Draw image scaled
        ctx.scale(scale, scale);
        ctx.drawImage(img, 0, 0);
        
        // Export as PNG
        canvas.toBlob((blob) => {
          if (blob) {
            const pngUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = pngUrl;
            link.download = `${artifact.title.replace(/\s+/g, '_')}.png`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(pngUrl);
          }
          URL.revokeObjectURL(url);
          setIsExporting(false);
        }, 'image/png');
      };
      
      img.onerror = () => {
        URL.revokeObjectURL(url);
        setIsExporting(false);
        console.error('Failed to load SVG for PNG export');
      };
      
      img.src = url;
    } catch (err) {
      console.error('Failed to export PNG:', err);
      setIsExporting(false);
    }
  }, [currentSvg, artifact.title]);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-secondary/30">
        {/* View mode toggle */}
        <div className="flex items-center bg-secondary rounded-lg p-0.5">
          <button
            onClick={() => setViewMode('code')}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1',
              viewMode === 'code'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
            title="Code only"
          >
            <Code className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Code</span>
          </button>
          <button
            onClick={() => setViewMode('split')}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors',
              viewMode === 'split'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
            title="Split view"
          >
            <span>Split</span>
          </button>
          <button
            onClick={() => setViewMode('preview')}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1',
              viewMode === 'preview'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
            title="Preview only"
          >
            <Eye className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Preview</span>
          </button>
        </div>

        {/* Export buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={handleExportSvg}
            disabled={!currentSvg || isExporting}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1',
              'bg-secondary text-muted-foreground hover:text-foreground hover:bg-secondary/80',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            title="Export as SVG"
          >
            <Download className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">SVG</span>
          </button>
          <button
            onClick={handleExportPng}
            disabled={!currentSvg || isExporting}
            className={cn(
              'px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1',
              'bg-secondary text-muted-foreground hover:text-foreground hover:bg-secondary/80',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            title="Export as PNG"
          >
            <FileImage className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">PNG</span>
          </button>
        </div>
      </div>

      {/* Editor content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Code editor panel */}
        {(viewMode === 'code' || viewMode === 'split') && (
          <div className={cn(
            'flex flex-col border-r border-border',
            viewMode === 'split' ? 'w-1/2' : 'w-full'
          )}>
            <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-secondary/50 border-b border-border">
              Mermaid Source
            </div>
            <textarea
              value={editedContent}
              onChange={handleContentChange}
              className={cn(
                'flex-1 p-4 font-mono text-sm resize-none',
                'bg-[hsl(var(--code-block-bg))] text-foreground',
                'focus:outline-none focus:ring-2 focus:ring-primary/20',
                'placeholder:text-muted-foreground/50'
              )}
              placeholder="Enter mermaid diagram code..."
              spellCheck={false}
            />
          </div>
        )}

        {/* Preview panel */}
        {(viewMode === 'preview' || viewMode === 'split') && (
          <div className={cn(
            'flex flex-col',
            viewMode === 'split' ? 'w-1/2' : 'w-full'
          )}>
            <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-secondary/50 border-b border-border">
              Preview
            </div>
            <div className="flex-1 overflow-hidden">
              <MermaidPreview
                content={editedContent}
                id={artifact.id}
                onSvgReady={handleSvgReady}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

export default MermaidEditor;
