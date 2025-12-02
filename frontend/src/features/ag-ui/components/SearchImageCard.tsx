'use client';

import React, { memo, useState, useCallback } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import type { SearchImage } from './SearchImageDialog';

interface SearchImageCardProps {
  image: SearchImage;
  onClick?: (image: SearchImage) => void;
  className?: string;
  /** Size variant for different grid layouts */
  size?: 'small' | 'medium' | 'large';
}

/**
 * SearchImageCard - Individual image card with lazy loading
 * 
 * Features:
 * - Lazy loading with loading state
 * - Error handling with fallback
 * - Hover effects
 * - Click to open dialog
 * - Source link on hover
 */
export const SearchImageCard = memo(function SearchImageCard({
  image,
  onClick,
  className,
  size = 'medium',
}: SearchImageCardProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleLoad = useCallback(() => {
    setIsLoading(false);
    setHasError(false);
  }, []);

  const handleError = useCallback(() => {
    setIsLoading(false);
    setHasError(true);
  }, []);

  const handleClick = useCallback(() => {
    if (!hasError && onClick) {
      onClick(image);
    }
  }, [hasError, onClick, image]);

  const sizeClasses = {
    small: 'h-24 sm:h-28',
    medium: 'h-32 sm:h-40',
    large: 'h-48 sm:h-56',
  };

  return (
    <div
      className={cn(
        'relative rounded-lg overflow-hidden bg-secondary/50 border border-border',
        'transition-all duration-200 ease-out',
        'cursor-pointer group',
        sizeClasses[size],
        isHovered && 'ring-2 ring-primary/50 shadow-lg',
        hasError && 'opacity-60 cursor-not-allowed',
        className
      )}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsHovered(true)}
      onBlur={() => setIsHovered(false)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleClick();
        }
      }}
      tabIndex={hasError ? -1 : 0}
      role="button"
      aria-disabled={hasError}
    >
      {/* Loading skeleton */}
      {isLoading && !hasError && (
        <div className="absolute inset-0 flex items-center justify-center bg-secondary/80">
          <div className="animate-pulse flex flex-col items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-muted-foreground/20" />
            <div className="w-16 h-2 rounded bg-muted-foreground/20" />
          </div>
        </div>
      )}

      {/* Error state */}
      {hasError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-secondary/80 p-2">
          <p className="text-xs text-muted-foreground text-center">
            Image unavailable
          </p>
          {image.source && (
            <a
              href={image.source}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:underline mt-1 flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3" />
              View source
            </a>
          )}
        </div>
      )}

      {/* Image */}
      <img
        src={image.url}
        alt={image.alt || 'Search result'}
        className={cn(
          'w-full h-full object-cover transition-transform duration-300',
          isHovered && 'scale-105',
          (isLoading || hasError) && 'opacity-0'
        )}
        loading="lazy"
        onLoad={handleLoad}
        onError={handleError}
        draggable={false}
      />

      {/* Hover overlay */}
      <div
        className={cn(
          'absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent',
          'opacity-0 transition-opacity duration-200',
          isHovered && !hasError && 'opacity-100'
        )}
      >
        {/* Source info */}
        {image.source && image.source.startsWith('http') && (
          <div className="absolute bottom-0 left-0 right-0 p-2">
            <p className="text-xs text-white/80 truncate">
              {(() => {
                try {
                  return new URL(image.source).hostname;
                } catch {
                  return image.source;
                }
              })()}
            </p>
          </div>
        )}

        {/* Click hint */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs text-white/90 bg-black/40 px-2 py-1 rounded">
            Click to view
          </span>
        </div>
      </div>

      {/* Alt text tooltip on hover */}
      {image.alt && isHovered && !hasError && (
        <div className="absolute top-2 left-2 right-2 pointer-events-none">
          <p className="text-xs text-white bg-black/60 px-2 py-1 rounded truncate">
            {image.alt}
          </p>
        </div>
      )}
    </div>
  );
});

export default SearchImageCard;
