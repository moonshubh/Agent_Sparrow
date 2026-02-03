'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { resolveMemoryAssetUrl } from '@/features/memory/lib/memoryAssetResolver';
import { parseMemoryImageSrc, withSizeFragment } from '@/features/memory/lib/memoryImageSizing';

type ResizeHandle =
  | 'top-left'
  | 'top'
  | 'top-right'
  | 'right'
  | 'bottom-right'
  | 'bottom'
  | 'bottom-left'
  | 'left';

type DragState = {
  startX: number;
  startY: number;
  startWidth: number;
  startHeight: number;
  maxWidth: number;
  handle: ResizeHandle;
};

const MIN_WIDTH = 120;
const MIN_HEIGHT = 80;

const clamp = (value: number, min: number, max?: number) => {
  if (!Number.isFinite(value)) return min;
  if (max !== undefined) {
    return Math.min(Math.max(value, min), max);
  }
  return Math.max(value, min);
};

export function MemoryImageView({ node, editor, selected, updateAttributes }: NodeViewProps) {
  const src = node.attrs.src || '';
  const alt = node.attrs.alt || '';
  const { baseSrc, width: initialWidth, height: initialHeight } = useMemo(
    () => parseMemoryImageSrc(src),
    [src]
  );

  const [resolvedSrc, setResolvedSrc] = useState<string | null>(null);
  const [hasError, setHasError] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [size, setSize] = useState<{ width?: number; height?: number }>({
    width: initialWidth,
    height: initialHeight,
  });

  const sizeRef = useRef(size);
  const dragRef = useRef<DragState | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    sizeRef.current = size;
  }, [size]);

  useEffect(() => {
    setSize({ width: initialWidth, height: initialHeight });
  }, [initialWidth, initialHeight]);

  useEffect(() => {
    let active = true;
    let revoke: (() => void) | undefined;
    setHasError(false);
    setResolvedSrc(null);

    const run = async () => {
      try {
        const resolved = await resolveMemoryAssetUrl(baseSrc);
        if (!active || !resolved) return;
        revoke = resolved.revoke;
        setResolvedSrc(resolved.src);
      } catch (error) {
        if (!active) return;
        setHasError(true);
      }
    };

    if (baseSrc) {
      void run();
    } else {
      setHasError(true);
    }

    return () => {
      active = false;
      if (revoke) revoke();
    };
  }, [baseSrc]);

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>, handle: ResizeHandle) => {
      if (!editor?.isEditable) return;
      event.preventDefault();
      event.stopPropagation();

      const image = imageRef.current;
      const frame = frameRef.current;
      if (!image || !frame) return;

      const rect = image.getBoundingClientRect();
      const frameRect = frame.getBoundingClientRect();
      dragRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        startWidth: rect.width,
        startHeight: rect.height,
        maxWidth: Math.max(frameRect.width, MIN_WIDTH),
        handle,
      };

      setIsResizing(true);
      const startingSize = { width: rect.width, height: rect.height };
      sizeRef.current = startingSize;
      setSize(startingSize);

      const handleMove = (moveEvent: PointerEvent) => {
        if (!dragRef.current) return;
        moveEvent.preventDefault();
        const { startX, startY, startWidth, startHeight, maxWidth, handle } =
          dragRef.current;
        const dx = moveEvent.clientX - startX;
        const dy = moveEvent.clientY - startY;

        const affectsWidth = handle.includes('right') || handle.includes('left');
        const affectsHeight = handle.includes('bottom') || handle.includes('top');
        const widthDelta = affectsWidth ? (handle.includes('right') ? dx : -dx) : 0;
        const heightDelta = affectsHeight ? (handle.includes('bottom') ? dy : -dy) : 0;

        const nextWidth = affectsWidth
          ? clamp(startWidth + widthDelta, MIN_WIDTH, maxWidth)
          : startWidth;
        const nextHeight = affectsHeight
          ? clamp(startHeight + heightDelta, MIN_HEIGHT)
          : startHeight;

        const nextSize = { width: nextWidth, height: nextHeight };
        sizeRef.current = nextSize;
        setSize(nextSize);
      };

      const handleUp = () => {
        window.removeEventListener('pointermove', handleMove);
        window.removeEventListener('pointerup', handleUp);
        setIsResizing(false);

        const { width, height } = sizeRef.current;
        if (!width || !height) return;
        updateAttributes({ src: withSizeFragment(baseSrc, width, height) });
      };

      window.addEventListener('pointermove', handleMove);
      window.addEventListener('pointerup', handleUp);
    },
    [baseSrc, editor, updateAttributes]
  );

  const showHandles = Boolean(selected && editor?.isEditable && resolvedSrc && !hasError);

  return (
    <NodeViewWrapper
      className={`memory-image-node${showHandles ? ' is-selected' : ''}${isResizing ? ' is-resizing' : ''}`}
    >
      {resolvedSrc && !hasError ? (
        <div className="memory-image-frame" ref={frameRef}>
          <div className="memory-image-wrapper">
            <img
              ref={imageRef}
              src={resolvedSrc}
              alt={alt}
              draggable={false}
              style={{
                width: size.width ? `${size.width}px` : undefined,
                height: size.height ? `${size.height}px` : undefined,
              }}
            />
            {showHandles && (
              <>
                <div
                  className="memory-image-handle handle-top-left"
                  onPointerDown={(event) => handlePointerDown(event, 'top-left')}
                />
                <div
                  className="memory-image-handle handle-top"
                  onPointerDown={(event) => handlePointerDown(event, 'top')}
                />
                <div
                  className="memory-image-handle handle-top-right"
                  onPointerDown={(event) => handlePointerDown(event, 'top-right')}
                />
                <div
                  className="memory-image-handle handle-right"
                  onPointerDown={(event) => handlePointerDown(event, 'right')}
                />
                <div
                  className="memory-image-handle handle-bottom-left"
                  onPointerDown={(event) => handlePointerDown(event, 'bottom-left')}
                />
                <div
                  className="memory-image-handle handle-bottom"
                  onPointerDown={(event) => handlePointerDown(event, 'bottom')}
                />
                <div
                  className="memory-image-handle handle-bottom-right"
                  onPointerDown={(event) => handlePointerDown(event, 'bottom-right')}
                />
                <div
                  className="memory-image-handle handle-left"
                  onPointerDown={(event) => handlePointerDown(event, 'left')}
                />
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="memory-image-fallback">
          <span>Image unavailable</span>
          {alt ? <small>{alt}</small> : null}
        </div>
      )}
    </NodeViewWrapper>
  );
}
