'use client';

import React, { memo, useState, useEffect, useCallback, useRef } from 'react';
import { X, Download, RotateCcw, ZoomIn, ZoomOut, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/shared/lib/utils';

export interface SearchImage {
  url: string;
  alt?: string;
  source?: string;
  width?: number;
  height?: number;
}

interface SearchImageDialogProps {
  image: SearchImage | null;
  isOpen: boolean;
  onClose: () => void;
}

/**
 * SearchImageDialog - Fullscreen modal for viewing search result images
 * 
 * Features:
 * - Fullscreen overlay with backdrop blur
 * - Zoom/pan support via mouse wheel and drag
 * - Download button
 * - Source link
 * - Close on ESC or backdrop click
 */
export const SearchImageDialog = memo(function SearchImageDialog({
  image,
  isOpen,
  onClose,
}: SearchImageDialogProps) {
  const [zoom, setZoom] = useState(1);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset state when dialog opens/closes
  useEffect(() => {
    if (isOpen) {
      setZoom(1);
      setPanX(0);
      setPanY(0);
      setIsLoading(true);
      setLoadError(false);
    }
  }, [isOpen, image?.url]);

  // Close on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const resetZoom = useCallback(() => {
    setZoom(1);
    setPanX(0);
    setPanY(0);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Calculate zoom factor
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.min(Math.max(zoom * zoomFactor, 0.5), 5);

    if (newZoom === zoom) return;

    // Reset pan when zooming back to 1
    if (newZoom <= 1) {
      setZoom(1);
      setPanX(0);
      setPanY(0);
      return;
    }

    // Calculate new pan position to zoom towards mouse cursor
    const containerCenterX = rect.width / 2;
    const containerCenterY = rect.height / 2;
    const zoomRatio = newZoom / zoom;
    const deltaX = (mouseX - containerCenterX - panX) * (zoomRatio - 1);
    const deltaY = (mouseY - containerCenterY - panY) * (zoomRatio - 1);

    setZoom(newZoom);
    setPanX(panX - deltaX);
    setPanY(panY - deltaY);
  }, [zoom, panX, panY]);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (zoom <= 1) return;
    e.preventDefault();
    setIsDragging(true);
    setDragStart({
      x: e.clientX - panX,
      y: e.clientY - panY,
    });
  }, [zoom, panX, panY]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging || zoom <= 1) return;
    setPanX(e.clientX - dragStart.x);
    setPanY(e.clientY - dragStart.y);
  }, [isDragging, dragStart, zoom]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDoubleClick = useCallback(() => {
    if (zoom > 1) {
      resetZoom();
    } else {
      setZoom(2);
    }
  }, [zoom, resetZoom]);

  const handleDownload = useCallback(async () => {
    if (!image?.url) return;

    try {
      const response = await fetch(image.url);
      if (!response.ok) throw new Error('Failed to fetch image');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      
      const link = document.createElement('a');
      link.href = url;
      const sanitizedName = (image.alt || 'search-image')
        .trim()
        .replace(/[/\\?%*:|"<>]/g, '-')
        .slice(0, 100) || 'search-image';
      link.download = `${sanitizedName}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      window.URL.revokeObjectURL(url);
    } catch (error) {
      // Fallback: open image in new tab
      window.open(image.url, '_blank');
    }
  }, [image]);

  const handleImageLoad = useCallback(() => {
    setIsLoading(false);
    setLoadError(false);
  }, []);

  const handleImageError = useCallback(() => {
    setIsLoading(false);
    setLoadError(true);
  }, []);

  const getCursor = () => {
    if (zoom <= 1) return 'default';
    return isDragging ? 'grabbing' : 'grab';
  };

  if (!image) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-[200] bg-black/90 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-[201] flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4">
              <div className="flex items-center gap-2">
                {image.source && (
                  <a
                    href={image.source}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink className="h-4 w-4" />
                    <span className="max-w-[200px] truncate">{image.source}</span>
                  </a>
                )}
              </div>

              <div className="flex items-center gap-2">
                {zoom > 1 && (
                  <button
                    onClick={resetZoom}
                    className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors text-white"
                    title="Reset zoom"
                  >
                    <RotateCcw className="h-5 w-5" />
                  </button>
                )}
                
                <button
                  onClick={() => setZoom(Math.min(zoom * 1.2, 5))}
                  className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors text-white"
                  title="Zoom in"
                >
                  <ZoomIn className="h-5 w-5" />
                </button>
                
                <button
                  onClick={() => setZoom(Math.max(zoom * 0.8, 0.5))}
                  className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors text-white"
                  title="Zoom out"
                >
                  <ZoomOut className="h-5 w-5" />
                </button>

                <button
                  onClick={handleDownload}
                  className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors text-white"
                  title="Download"
                >
                  <Download className="h-5 w-5" />
                </button>

                <button
                  onClick={onClose}
                  className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-colors text-white"
                  title="Close (Esc)"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Image container */}
            <div
              ref={containerRef}
              className="flex-1 flex items-center justify-center p-4 overflow-hidden"
              onWheel={handleWheel}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
              onDoubleClick={handleDoubleClick}
              style={{ cursor: getCursor() }}
            >
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="animate-spin h-8 w-8 border-2 border-white border-t-transparent rounded-full" />
                </div>
              )}

              {loadError ? (
                <div className="text-center text-white/60">
                  <p className="text-lg">Failed to load image</p>
                  <a
                    href={image.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary hover:underline mt-2 inline-block"
                  >
                    Open original
                  </a>
                </div>
              ) : (
                <div
                  className="transition-transform duration-100 ease-out"
                  style={{
                    transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
                    transformOrigin: 'center center',
                  }}
                >
                  <img
                    src={image.url}
                    alt={image.alt || 'Search result image'}
                    className={cn(
                      'max-h-[calc(100vh-8rem)] max-w-[calc(100vw-4rem)] object-contain',
                      'rounded-lg shadow-2xl',
                      isLoading && 'opacity-0'
                    )}
                    onLoad={handleImageLoad}
                    onError={handleImageError}
                    draggable={false}
                  />
                </div>
              )}
            </div>

            {/* Caption */}
            {image.alt && (
              <div className="p-4 text-center">
                <p className="text-sm text-white/70">{image.alt}</p>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
});

export default SearchImageDialog;
