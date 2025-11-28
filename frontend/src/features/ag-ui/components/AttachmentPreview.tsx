'use client';

import React, { useState } from 'react';
import { cn } from '@/shared/lib/utils';
import { X, FileText, File, Image as ImageIcon } from 'lucide-react';
import type { AttachmentInput } from '@/services/ag-ui/types';

import { motion } from 'framer-motion';

interface AttachmentPreviewProps {
  attachment: AttachmentInput;
  onRemove?: () => void;
  variant?: 'input' | 'message' | 'stacked';
  className?: string;
  index?: number;
  total?: number;
}

/**
 * Determines the type of attachment based on MIME type
 */
function getAttachmentType(mimeType: string): 'image' | 'pdf' | 'text' | 'file' {
  const mime = mimeType.toLowerCase();
  if (mime.startsWith('image/')) return 'image';
  if (mime === 'application/pdf') return 'pdf';
  if (mime.startsWith('text/') || mime === 'application/json') return 'text';
  return 'file';
}

/**
 * Gets file extension from filename
 */
function getFileExtension(filename: string): string {
  const parts = filename.split('.');
  return parts.length > 1 ? parts[parts.length - 1].toUpperCase() : '';
}

/**
 * AttachmentPreview - Displays attachment thumbnails with remove functionality
 *
 * For images: Shows actual image thumbnail
 * For PDFs: Shows PDF icon with filename
 * For text/logs: Shows text file icon
 *
 * @param attachment - The attachment data
 * @param onRemove - Callback when X button is clicked (only shown if provided)
 * @param variant - 'input' for chat input bar, 'message' for sent messages, 'stacked' for stacked view
 */
export function AttachmentPreview({
  attachment,
  onRemove,
  variant = 'input',
  className,
  index = 0,
  total = 1,
}: AttachmentPreviewProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [imageError, setImageError] = useState(false);

  const type = getAttachmentType(attachment.mime_type);
  const extension = getFileExtension(attachment.name);
  const isImage = type === 'image' && !imageError;

  // Compact variant for input bar
  const isInputVariant = variant === 'input';
  const isStacked = variant === 'stacked';
  const sizeInKb = attachment.size != null ? Math.round((Number(attachment.size) || 0) / 1024) : null;

  // Stacked positioning styles
  const stackedStyle = isStacked ? {
    zIndex: total - index,
    originX: 1, // Transform origin bottom right
    originY: 1,
    rotate: index * 6, // Fan out UPWARDS (positive rotation moves left side up)
    x: -(index * 4), // Shift left to expose more
    y: -(index * 4), // Shift up to expose more
    scale: 1 - (index * 0.02), // Very slight scale down
  } : {};

  const Content = (
    <div
      className={cn(
        'relative group rounded-lg overflow-hidden transition-all duration-200',
        isInputVariant
          ? 'w-16 h-16 bg-secondary/80 border border-border hover:border-terracotta-400/50'
          : isStacked
            ? 'w-52 h-16 bg-card border border-border/50 shadow-lg flex items-center px-3' // Wide card for stack with stronger shadow
            : 'w-20 h-20 bg-secondary/60 border border-border/50',
        className
      )}
      style={isStacked ? undefined : undefined} // Style handled by motion div for stacked
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Image Thumbnail */}
      {isImage && (
        <div className={cn("relative overflow-hidden rounded-md", isStacked ? "w-10 h-10 mr-3 flex-shrink-0" : "w-full h-full")}>
          <img
            src={attachment.data_url}
            alt={attachment.name}
            className="w-full h-full object-cover opacity-90 hover:opacity-100 transition-opacity"
            onError={() => setImageError(true)}
          />
        </div>
      )}

      {/* Non-Image File Display */}
      {!isImage && (
        <div className={cn(
          "flex items-center justify-center rounded-md",
          isStacked ? "w-10 h-10 mr-3 flex-shrink-0 bg-secondary/50" : "w-full h-full flex-col p-1.5 gap-0.5"
        )}>
          {/* File Icon */}
          <div className={cn(
            'flex items-center justify-center rounded-md',
            isInputVariant ? 'w-8 h-8' : isStacked ? 'w-6 h-6' : 'w-10 h-10',
            type === 'pdf' && 'bg-red-500/20 text-red-400',
            type === 'text' && 'bg-blue-500/20 text-blue-400',
            type === 'file' && 'bg-muted text-muted-foreground'
          )}>
            {type === 'pdf' && <FileText className={isInputVariant ? 'w-4 h-4' : 'w-4 h-4'} />}
            {type === 'text' && <File className={isInputVariant ? 'w-4 h-4' : 'w-4 h-4'} />}
            {type === 'file' && <File className={isInputVariant ? 'w-4 h-4' : 'w-4 h-4'} />}
            {imageError && <ImageIcon className={isInputVariant ? 'w-4 h-4' : 'w-4 h-4'} />}
          </div>

          {/* Extension Badge (Only for non-stacked or if space permits) */}
          {!isStacked && extension && (
            <span className={cn(
              'font-mono font-semibold uppercase',
              isInputVariant ? 'text-[8px]' : 'text-[10px]',
              'text-muted-foreground'
            )}>
              {extension}
            </span>
          )}
        </div>
      )}

      {/* Stacked File Info */}
      {isStacked && (
        <div className="flex-1 min-w-0 flex flex-col justify-center">
          <p className="text-xs font-medium text-foreground truncate">{attachment.name}</p>
          <p className="text-[10px] text-muted-foreground uppercase">
            {extension} • {sizeInKb !== null ? `${sizeInKb}KB` : '-'}
          </p>
        </div>
      )}

      {/* Filename Tooltip on Hover (Not for stacked as it shows info) */}
      {!isStacked && (
        <div
          className={cn(
            'absolute bottom-0 left-0 right-0 bg-background/90 backdrop-blur-sm',
            'px-1 py-0.5 transition-all duration-200',
            isHovered ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1',
            isInputVariant ? 'text-[9px]' : 'text-[10px]'
          )}
        >
          <p className="truncate text-foreground/90 text-center">
            {attachment.name}
          </p>
        </div>
      )}

      {/* Remove Button (X) - Only shown on hover when onRemove is provided */}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className={cn(
            'absolute top-0.5 right-0.5 rounded-full',
            'bg-background/80 hover:bg-destructive text-foreground hover:text-destructive-foreground',
            'transition-all duration-200 shadow-sm',
            isInputVariant ? 'p-0.5' : 'p-1',
            isHovered ? 'opacity-100 scale-100' : 'opacity-0 scale-75'
          )}
          aria-label={`Remove ${attachment.name}`}
        >
          <X className={isInputVariant ? 'w-3 h-3' : 'w-3.5 h-3.5'} />
        </button>
      )}
    </div>
  );

  if (isStacked) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.9 }}
        animate={{ opacity: 1, ...stackedStyle }}
        transition={{ duration: 0.4, delay: index * 0.1 }}
        className="absolute bottom-0 right-0 origin-bottom-right"
      >
        {Content}
      </motion.div>
    );
  }

  return Content;
}

interface AttachmentPreviewListProps {
  attachments: AttachmentInput[];
  onRemove?: (index: number) => void;
  variant?: 'input' | 'message' | 'stacked';
  className?: string;
}

/**
 * AttachmentPreviewList - Displays a row of attachment previews
 */
export function AttachmentPreviewList({
  attachments,
  onRemove,
  variant = 'input',
  className,
}: AttachmentPreviewListProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!attachments || attachments.length === 0) return null;

  if (variant === 'stacked') {
    // If expanded, show as a grid/list
    if (isExpanded) {
      return (
        <div className={cn('flex flex-col items-end mb-2', className)}>
          <button
            type="button"
            onClick={() => setIsExpanded(false)}
            className="text-[10px] font-medium text-muted-foreground hover:text-foreground mb-2 flex items-center gap-1 transition-colors uppercase tracking-wider"
          >
            Collapse <span className="text-[8px]">↘</span>
          </button>
          <div className="flex flex-wrap gap-2 justify-end max-w-md">
            {attachments.map((attachment, index) => (
              <AttachmentPreview
                key={`${attachment.name}-${index}`}
                attachment={attachment}
                onRemove={onRemove ? () => onRemove(index) : undefined}
                variant="message" // Use message variant for expanded view
              />
            ))}
          </div>
        </div>
      );
    }

    // Stacked View - Show up to 5 items
    const visibleAttachments = attachments.slice(0, 5);
    const hasMore = attachments.length > 1;

    // Calculate dynamic spacing based on number of items to avoid overlap with "See All"
    // We estimate the height at the button's position (approx 70px from right)
    // Formula: (n-1) * 11 + 4px buffer. 
    // This accounts for vertical offset (4px/item) and rotation height at 70px width.
    const buttonMargin = Math.max(0, (visibleAttachments.length - 1) * 11 + 4);

    return (
      <div className={cn('relative w-64 mb-2 flex flex-col items-end', className)}>
        {/* See All Link */}
        {hasMore && (
          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            className="text-[10px] font-medium text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors uppercase tracking-wider z-10"
            style={{ marginBottom: `${buttonMargin}px` }}
          >
            See All <span className="text-[8px]">↗</span>
          </button>
        )}

        {/* Stack Container */}
        <div className="relative w-52 h-16">
          {visibleAttachments.map((attachment, index) => (
            <AttachmentPreview
              key={`${attachment.name}-${index}`}
              attachment={attachment}
              onRemove={onRemove ? () => onRemove(index) : undefined}
              variant={variant}
              index={index}
              total={visibleAttachments.length}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {attachments.map((attachment, index) => (
        <AttachmentPreview
          key={`${attachment.name}-${index}`}
          attachment={attachment}
          onRemove={onRemove ? () => onRemove(index) : undefined}
          variant={variant}
        />
      ))}
    </div>
  );
}
