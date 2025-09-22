/**
 * Virtual List Component
 * High-performance virtualized list for rendering large datasets
 */

'use client'

import React, { useRef, useEffect, useState, useCallback, useMemo, CSSProperties } from 'react'
import { useDebounce } from '@/hooks/use-debounce'
import { UI_CONFIG, FEATURE_FLAGS } from '@/lib/config/constants'
import { logger } from '@/lib/logging/logger'

// Virtual list configuration
export interface VirtualListConfig {
  itemHeight?: number | ((index: number) => number)  // Fixed or dynamic height
  overscan?: number                                   // Items to render outside viewport
  scrollDebounce?: number                            // Debounce scroll events
  threshold?: number                                  // Min items before virtualization
  estimatedItemHeight?: number                       // For dynamic heights
  getItemKey?: (index: number) => string | number    // Custom key generator
  onScroll?: (event: React.UIEvent<HTMLDivElement>) => void
  onItemsRendered?: (startIndex: number, endIndex: number) => void
  className?: string
  style?: CSSProperties
  role?: string
  ariaLabel?: string
  testId?: string
}

export interface VirtualListProps<T> extends VirtualListConfig {
  items: T[]
  renderItem: (item: T, index: number) => React.ReactNode
  emptyMessage?: string | React.ReactNode
  loadingMessage?: string | React.ReactNode
  isLoading?: boolean
}

// Item metadata for dynamic heights
interface ItemMetadata {
  height: number
  offset: number
}

export function VirtualList<T>({
  items,
  renderItem,
  itemHeight = UI_CONFIG.VIRTUALIZATION.ITEM_HEIGHT,
  overscan = UI_CONFIG.VIRTUALIZATION.OVERSCAN,
  scrollDebounce = UI_CONFIG.VIRTUALIZATION.SCROLL_DEBOUNCE,
  threshold = UI_CONFIG.VIRTUALIZATION.THRESHOLD,
  estimatedItemHeight = UI_CONFIG.VIRTUALIZATION.ITEM_HEIGHT,
  getItemKey,
  onScroll,
  onItemsRendered,
  className = '',
  style = {},
  role = 'list',
  ariaLabel = 'Virtual list',
  testId = 'virtual-list',
  emptyMessage = 'No items to display',
  loadingMessage = 'Loading...',
  isLoading = false
}: VirtualListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null)
  const scrollElementRef = useRef<HTMLDivElement>(null)
  const itemMetadataMap = useRef<Map<number, ItemMetadata>>(new Map())
  const measuredHeights = useRef<Map<number, number>>(new Map())

  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(0)
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 0 })

  // Check if virtualization is enabled and needed
  const shouldVirtualize = useMemo(() => {
    return FEATURE_FLAGS.ENABLE_VIRTUALIZATION && items.length > threshold
  }, [items.length, threshold])

  // Check if using dynamic heights
  const isDynamicHeight = typeof itemHeight === 'function'

  // Calculate item metadata for dynamic heights with O(n) complexity
  const getItemMetadata = useCallback((index: number): ItemMetadata => {
    if (!isDynamicHeight) {
      const height = itemHeight as number
      return {
        height,
        offset: index * height
      }
    }

    // Check cache first
    const cached = itemMetadataMap.current.get(index)
    if (cached) return cached

    // Build metadata from 0 to index to avoid recursion
    let offset = 0

    // Ensure all previous items are calculated first (linear pass)
    for (let i = 0; i <= index; i++) {
      if (itemMetadataMap.current.has(i)) {
        const metadata = itemMetadataMap.current.get(i)!
        offset = metadata.offset + metadata.height
        continue
      }

      // Calculate height for item i
      let height = estimatedItemHeight
      if (measuredHeights.current.has(i)) {
        height = measuredHeights.current.get(i)!
      } else if (typeof itemHeight === 'function') {
        height = itemHeight(i)
      }

      // Store metadata for item i
      const metadata = { height, offset }
      itemMetadataMap.current.set(i, metadata)

      if (i === index) {
        return metadata
      }

      offset += height
    }

    // Should never reach here, but return a default
    return { height: estimatedItemHeight, offset: 0 }
  }, [isDynamicHeight, itemHeight, estimatedItemHeight])

  // Calculate total height with O(n) complexity
  const totalHeight = useMemo(() => {
    if (!shouldVirtualize) {
      return 'auto'
    }

    if (!isDynamicHeight) {
      return items.length * (itemHeight as number)
    }

    // Get the last item's metadata to determine total height
    if (items.length === 0) return 0

    const lastItemMetadata = getItemMetadata(items.length - 1)
    return lastItemMetadata.offset + lastItemMetadata.height
  }, [items.length, itemHeight, isDynamicHeight, shouldVirtualize, getItemMetadata])

  // Calculate visible range
  const calculateVisibleRange = useCallback(() => {
    if (!shouldVirtualize || !containerRef.current) {
      return { start: 0, end: items.length }
    }

    const scrollTop = scrollElementRef.current?.scrollTop || 0
    const containerHeight = containerRef.current.clientHeight

    if (!isDynamicHeight) {
      const height = itemHeight as number
      const start = Math.max(0, Math.floor(scrollTop / height) - overscan)
      const end = Math.min(
        items.length,
        Math.ceil((scrollTop + containerHeight) / height) + overscan
      )
      return { start, end }
    }

    // For dynamic heights, find visible items by offset using binary search
    let start = 0
    let end = items.length

    // Binary search for start index
    let left = 0
    let right = items.length - 1
    const targetStart = scrollTop - overscan * estimatedItemHeight

    while (left <= right) {
      const mid = Math.floor((left + right) / 2)
      const metadata = getItemMetadata(mid)
      const itemBottom = metadata.offset + metadata.height

      if (itemBottom < targetStart) {
        left = mid + 1
      } else {
        start = mid
        right = mid - 1
      }
    }

    // Binary search for end index
    left = start
    right = items.length - 1
    const targetEnd = scrollTop + containerHeight + overscan * estimatedItemHeight

    while (left <= right) {
      const mid = Math.floor((left + right) / 2)
      const metadata = getItemMetadata(mid)

      if (metadata.offset <= targetEnd) {
        end = mid + 1
        left = mid + 1
      } else {
        right = mid - 1
      }
    }

    return { start, end }
  }, [
    shouldVirtualize,
    items.length,
    itemHeight,
    isDynamicHeight,
    overscan,
    estimatedItemHeight,
    getItemMetadata
  ])

  // Debounced scroll handler
  const debouncedScrollTop = useDebounce(scrollTop, scrollDebounce)

  // Handle scroll
  const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const target = event.currentTarget
    setScrollTop(target.scrollTop)

    if (onScroll) {
      onScroll(event)
    }
  }, [onScroll])

  // Update visible range when scroll changes
  useEffect(() => {
    const range = calculateVisibleRange()
    setVisibleRange(range)

    if (onItemsRendered && range.start !== visibleRange.start) {
      onItemsRendered(range.start, range.end)
    }
  }, [debouncedScrollTop, calculateVisibleRange, onItemsRendered])

  // Handle container resize
  useEffect(() => {
    if (!containerRef.current) return

    const resizeObserver = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })

    resizeObserver.observe(containerRef.current)
    setContainerHeight(containerRef.current.clientHeight)

    return () => {
      resizeObserver.disconnect()
    }
  }, [])

  // Measure dynamic item heights
  const measureItem = useCallback((index: number, element: HTMLElement | null) => {
    if (!element || !isDynamicHeight) return

    const height = element.getBoundingClientRect().height
    const prevHeight = measuredHeights.current.get(index)

    if (prevHeight !== height) {
      measuredHeights.current.set(index, height)
      itemMetadataMap.current.delete(index) // Clear cache for this item

      // Clear cache for subsequent items
      for (let i = index + 1; i < items.length; i++) {
        itemMetadataMap.current.delete(i)
      }

      // Force re-render if height changed significantly
      if (Math.abs((prevHeight || estimatedItemHeight) - height) > 5) {
        setVisibleRange(calculateVisibleRange())
      }
    }
  }, [isDynamicHeight, items.length, estimatedItemHeight, calculateVisibleRange])

  // Render items
  const renderItems = useMemo(() => {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center p-8">
          <div className="text-muted-foreground">{loadingMessage}</div>
        </div>
      )
    }

    if (items.length === 0) {
      return (
        <div className="flex items-center justify-center p-8">
          <div className="text-muted-foreground">{emptyMessage}</div>
        </div>
      )
    }

    if (!shouldVirtualize) {
      // Render all items without virtualization
      return items.map((item, index) => (
        <div
          key={getItemKey ? getItemKey(index) : index}
          role="listitem"
          data-index={index}
        >
          {renderItem(item, index)}
        </div>
      ))
    }

    // Virtualized rendering
    const { start, end } = visibleRange
    const visibleItems: React.ReactNode[] = []

    for (let i = start; i < end; i++) {
      const item = items[i]
      const metadata = getItemMetadata(i)
      const key = getItemKey ? getItemKey(i) : i

      visibleItems.push(
        <div
          key={key}
          ref={el => measureItem(i, el)}
          role="listitem"
          data-index={i}
          style={{
            position: 'absolute',
            top: metadata.offset,
            left: 0,
            right: 0,
            height: isDynamicHeight ? 'auto' : metadata.height,
            minHeight: isDynamicHeight ? metadata.height : undefined
          }}
        >
          {renderItem(item, i)}
        </div>
      )
    }

    return visibleItems
  }, [
    items,
    isLoading,
    loadingMessage,
    emptyMessage,
    shouldVirtualize,
    visibleRange,
    getItemKey,
    getItemMetadata,
    renderItem,
    isDynamicHeight,
    measureItem
  ])

  // Log performance metrics in development
  useEffect(() => {
    if (process.env.NODE_ENV === 'development' && shouldVirtualize) {
      logger.debug('VirtualList performance', {
        totalItems: items.length,
        renderedItems: visibleRange.end - visibleRange.start,
        startIndex: visibleRange.start,
        endIndex: visibleRange.end,
        efficiency: `${Math.round(((visibleRange.end - visibleRange.start) / items.length) * 100)}%`
      })
    }
  }, [items.length, visibleRange, shouldVirtualize])

  return (
    <div
      ref={containerRef}
      className={`relative ${className}`}
      style={{
        ...style,
        height: style.height || '100%',
        width: style.width || '100%'
      }}
      data-testid={testId}
    >
      <div
        ref={scrollElementRef}
        className="h-full w-full overflow-auto"
        onScroll={handleScroll}
        role={role}
        aria-label={ariaLabel}
        aria-rowcount={items.length}
        style={{
          position: 'relative'
        }}
      >
        <div
          style={{
            height: totalHeight,
            position: 'relative',
            width: '100%'
          }}
        >
          {renderItems}
        </div>
      </div>
    </div>
  )
}

// Hook for infinite scrolling with virtual list
export function useInfiniteVirtualList<T>(
  loadMore: () => Promise<T[]>,
  options: {
    initialItems?: T[]
    threshold?: number
    hasMore?: boolean
  } = {}
) {
  const [items, setItems] = useState<T[]>(options.initialItems || [])
  const [isLoading, setIsLoading] = useState(false)
  const [hasMore, setHasMore] = useState(options.hasMore ?? true)
  const [error, setError] = useState<Error | null>(null)

  const loadMoreItems = useCallback(async () => {
    if (isLoading || !hasMore) return

    setIsLoading(true)
    setError(null)

    try {
      const newItems = await loadMore()

      if (newItems.length === 0) {
        setHasMore(false)
      } else {
        setItems(prev => [...prev, ...newItems])
      }
    } catch (err) {
      setError(err as Error)
      logger.error('Failed to load more items', { error: err })
    } finally {
      setIsLoading(false)
    }
  }, [isLoading, hasMore, loadMore])

  const handleItemsRendered = useCallback((startIndex: number, endIndex: number) => {
    const threshold = options.threshold || 5

    if (endIndex >= items.length - threshold && hasMore && !isLoading) {
      loadMoreItems()
    }
  }, [items.length, hasMore, isLoading, loadMoreItems, options.threshold])

  return {
    items,
    isLoading,
    hasMore,
    error,
    loadMoreItems,
    handleItemsRendered,
    reset: () => {
      setItems(options.initialItems || [])
      setHasMore(true)
      setError(null)
    }
  }
}

// Export default
export default VirtualList