'use client';

import React, { memo, useState, useCallback, useMemo } from 'react';
import { ChevronDown, ChevronUp, Image as ImageIcon } from 'lucide-react';
import { cn } from '@/shared/lib/utils';
import { SearchImageCard } from './SearchImageCard';
import { SearchImageDialog, type SearchImage } from './SearchImageDialog';

interface SearchImageGridProps {
  /** Array of image objects from search results */
  images: SearchImage[];
  /** Maximum number of images to display initially */
  maxVisible?: number;
  /** Optional title for the image section */
  title?: string;
  /** Additional CSS classes */
  className?: string;
}

/**
 * SearchImageGrid - Dynamic responsive grid for search result images
 * 
 * Layout rules:
 * - 1 image → full-width
 * - 2 images → 2-column on desktop, stacked on mobile
 * - 3–4 images → 2-column grid
 * - 5+ images → responsive grid with auto-fit
 * 
 * Features:
 * - Expandable to show more images
 * - Click to open fullscreen dialog
 * - Responsive layout
 */
export const SearchImageGrid = memo(function SearchImageGrid({
  images,
  maxVisible = 4,
  title,
  className,
}: SearchImageGridProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedImage, setSelectedImage] = useState<SearchImage | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // Filter out invalid images
  const validImages = useMemo(() => {
    return images.filter(img => img && img.url && typeof img.url === 'string');
  }, [images]);

  // Determine which images to show
  const visibleImages = useMemo(() => {
    if (isExpanded || validImages.length <= maxVisible) {
      return validImages;
    }
    return validImages.slice(0, maxVisible);
  }, [validImages, maxVisible, isExpanded]);

  const hasMoreImages = validImages.length > maxVisible;
  const hiddenCount = validImages.length - maxVisible;

  const handleImageClick = useCallback((image: SearchImage) => {
    setSelectedImage(image);
    setIsDialogOpen(true);
  }, []);

  const handleCloseDialog = useCallback(() => {
    setIsDialogOpen(false);
    setSelectedImage(null);
  }, []);

  const toggleExpanded = useCallback(() => {
    setIsExpanded(prev => !prev);
  }, []);

  // Determine grid layout based on image count
  const getGridClasses = (count: number) => {
    if (count === 1) {
      return 'grid-cols-1';
    }
    if (count === 2) {
      return 'grid-cols-1 sm:grid-cols-2';
    }
    if (count <= 4) {
      return 'grid-cols-2';
    }
    // 5+ images: responsive auto-fit grid
    return 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4';
  };

  // Determine image size based on grid layout
  const getImageSize = (count: number, index: number): 'small' | 'medium' | 'large' => {
    if (count === 1) return 'large';
    if (count === 2) return 'medium';
    if (count <= 4) return 'medium';
    return 'small';
  };

  if (validImages.length === 0) {
    return null;
  }

  return (
    <div className={cn('space-y-2', className)}>
      {/* Title */}
      {title && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageIcon className="h-4 w-4" />
          <span>{title}</span>
          <span className="text-xs">({validImages.length})</span>
        </div>
      )}

      {/* Image grid */}
      <div className={cn(
        'grid gap-2',
        getGridClasses(visibleImages.length)
      )}>
        {visibleImages.map((image, index) => (
          <SearchImageCard
            key={`${image.url}-${index}`}
            image={image}
            onClick={handleImageClick}
            size={getImageSize(visibleImages.length, index)}
          />
        ))}
      </div>

      {/* Show more/less button */}
      {hasMoreImages && (
        <button
          onClick={toggleExpanded}
          className={cn(
            'w-full py-2 px-3 rounded-lg',
            'bg-secondary/50 hover:bg-secondary/80',
            'text-sm text-muted-foreground hover:text-foreground',
            'flex items-center justify-center gap-2',
            'transition-colors duration-200'
          )}
        >
          {isExpanded ? (
            <>
              <ChevronUp className="h-4 w-4" />
              Show less
            </>
          ) : (
            <>
              <ChevronDown className="h-4 w-4" />
              Show {hiddenCount} more image{hiddenCount !== 1 ? 's' : ''}
            </>
          )}
        </button>
      )}

      {/* Fullscreen dialog */}
      <SearchImageDialog
        image={selectedImage}
        isOpen={isDialogOpen}
        onClose={handleCloseDialog}
      />
    </div>
  );
});

export default SearchImageGrid;
