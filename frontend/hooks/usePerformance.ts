"use client"

import { useCallback, useEffect, useRef, useState, useMemo } from 'react'

/**
 * Debounce hook that delays execution of a function until after delay milliseconds
 * have elapsed since the last time the debounced function was invoked.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}

/**
 * Debounced callback hook that returns a memoized version of the callback
 * that only changes if one of the dependencies has changed and delays execution.
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number,
  deps: React.DependencyList
): T {
  const timeoutRef = useRef<NodeJS.Timeout>()
  const callbackRef = useRef<T>(callback)

  // Update callback ref when callback changes
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return useCallback(
    ((...args: Parameters<T>) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }

      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args)
      }, delay)
    }) as T,
    [delay, ...deps]
  )
}

/**
 * Throttle hook that limits the rate at which a function can fire.
 * Fixed to prevent race conditions and ensure consistent behavior.
 */
export function useThrottle<T>(value: T, interval: number): T {
  const [throttledValue, setThrottledValue] = useState<T>(value)
  const lastExecuted = useRef<number>(0)
  const timeoutRef = useRef<NodeJS.Timeout | null>(null)
  const latestValueRef = useRef<T>(value)

  useEffect(() => {
    latestValueRef.current = value
    const now = Date.now()
    
    // Clear any existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    
    if (now >= lastExecuted.current + interval) {
      // Can execute immediately
      lastExecuted.current = now
      setThrottledValue(value)
    } else {
      // Schedule execution after remaining interval
      const remainingTime = lastExecuted.current + interval - now
      timeoutRef.current = setTimeout(() => {
        lastExecuted.current = Date.now()
        setThrottledValue(latestValueRef.current)
        timeoutRef.current = null
      }, remainingTime)
    }
    
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }
  }, [value, interval])

  return throttledValue
}

/**
 * Performance monitoring hook for measuring render times and detecting performance issues.
 * Fixed to avoid render mutations and consolidate timing logic.
 */
export function usePerformanceMonitor(componentName: string, logThreshold: number = 16) {
  const [renderStats, setRenderStats] = useState({ renderCount: 0, slowRenderCount: 0 })
  const renderStartTime = useRef<number>(0)
  const renderCount = useRef<number>(0)
  const slowRenderCount = useRef<number>(0)

  useEffect(() => {
    // Measure render time after render completes
    const renderEndTime = performance.now()
    const renderTime = renderEndTime - renderStartTime.current
    
    // Update counters
    renderCount.current += 1
    
    if (renderTime > logThreshold) {
      slowRenderCount.current += 1
      console.warn(
        `🐌 Slow render detected in ${componentName}:`,
        `${renderTime.toFixed(2)}ms`,
        `(${slowRenderCount.current}/${renderCount.current} slow renders)`
      )
    }

    if (process.env.NODE_ENV === 'development' && renderCount.current % 100 === 0) {
      console.log(
        `📊 ${componentName} performance:`,
        `${renderCount.current} renders,`,
        `${slowRenderCount.current} slow (>${logThreshold}ms)`
      )
    }
    
    // Update state to trigger re-render with latest stats
    setRenderStats({
      renderCount: renderCount.current,
      slowRenderCount: slowRenderCount.current
    })
    
    // Set start time for next render
    renderStartTime.current = performance.now()
  })

  return renderStats
}

/**
 * Intersection Observer hook for implementing lazy loading and visibility detection.
 * Fixed to memoize options and prevent unnecessary observer recreations.
 */
export function useIntersectionObserver(
  options: IntersectionObserverInit = {},
  triggerOnce: boolean = true
) {
  const [isIntersecting, setIsIntersecting] = useState(false)
  const [hasIntersected, setHasIntersected] = useState(false)
  const targetRef = useRef<HTMLElement | null>(null)
  
  // Memoize the merged options to prevent unnecessary observer recreations
  const mergedOptions = useMemo(() => ({
    threshold: 0.1,
    rootMargin: '10px',
    ...options
  }), [options.root, options.rootMargin, options.threshold])

  useEffect(() => {
    const target = targetRef.current
    if (!target) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        const isIntersectingNow = entry.isIntersecting
        setIsIntersecting(isIntersectingNow)

        if (isIntersectingNow) {
          setHasIntersected(true)
          if (triggerOnce) {
            observer.unobserve(target)
          }
        }
      },
      mergedOptions
    )

    observer.observe(target)

    return () => {
      observer.unobserve(target)
    }
  }, [mergedOptions, triggerOnce])

  return {
    targetRef,
    isIntersecting,
    hasIntersected
  }
}

/**
 * RequestAnimationFrame hook for smooth animations.
 */
export function useAnimationFrame(callback: (deltaTime: number) => void, running: boolean = true) {
  const callbackRef = useRef(callback)
  const frameRef = useRef<number>()
  const lastTimeRef = useRef<number>()

  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  useEffect(() => {
    if (!running) {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
      return
    }

    const animate = (time: number) => {
      const deltaTime = lastTimeRef.current ? time - lastTimeRef.current : 0
      lastTimeRef.current = time

      callbackRef.current(deltaTime)
      frameRef.current = requestAnimationFrame(animate)
    }

    frameRef.current = requestAnimationFrame(animate)

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
    }
  }, [running])
}

/**
 * Lazy component hook that loads components only when needed.
 */
export function useLazyComponent<T extends React.ComponentType<any>>(
  componentImporter: () => Promise<{ default: T }>,
  deps: React.DependencyList = []
) {
  const [Component, setComponent] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const loadComponent = useCallback(async () => {
    if (Component || loading) return

    try {
      setLoading(true)
      setError(null)
      const { default: LoadedComponent } = await componentImporter()
      setComponent(() => LoadedComponent)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to load component'))
    } finally {
      setLoading(false)
    }
  }, [Component, loading, componentImporter, ...deps])

  return {
    Component,
    loading,
    error,
    loadComponent
  }
}

/**
 * Optimized re-render hook that prevents unnecessary re-renders.
 * Fixed to include callback in dependency array.
 */
export function useStableCallback<T extends (...args: any[]) => any>(
  callback: T
): T {
  const callbackRef = useRef<T>(callback)

  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  return useCallback(
    ((...args: Parameters<T>) => callbackRef.current(...args)) as T,
    []
  )
}

/**
 * Memory usage monitor (development only).
 * Fixed to check performance.memory availability before accessing.
 */
export function useMemoryMonitor(componentName: string, interval: number = 5000) {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return

    const checkMemory = () => {
      // Check if performance.memory exists (non-standard API)
      if (typeof performance !== 'undefined' && 
          'memory' in performance && 
          performance.memory) {
        try {
          const memory = performance.memory
          const used = Math.round(memory.usedJSHeapSize / 1048576 * 100) / 100
          const total = Math.round(memory.totalJSHeapSize / 1048576 * 100) / 100
          const limit = Math.round(memory.jsHeapSizeLimit / 1048576 * 100) / 100

          if (used > limit * 0.8) {
            console.warn(
              `🚨 High memory usage in ${componentName}:`,
              `${used}MB / ${limit}MB (${Math.round((used / limit) * 100)}%)`
            )
          }
        } catch (error) {
          console.warn(`Failed to read memory usage for ${componentName}:`, error)
        }
      }
    }

    const intervalId = setInterval(checkMemory, interval)
    return () => clearInterval(intervalId)
  }, [componentName, interval])
}

/**
 * Efficient list virtualization helper.
 * Enhanced with edge case handling and memoization for better performance.
 */
export function useVirtualization<T>(
  items: T[],
  itemHeight: number,
  containerHeight: number,
  overscan: number = 5
) {
  const [scrollTop, setScrollTop] = useState(0)
  
  // Edge case handling
  const safeItemHeight = Math.max(1, itemHeight)
  const safeContainerHeight = Math.max(1, containerHeight)
  const safeItems = items || []
  const safeOverscan = Math.max(0, overscan)
  
  // Memoize calculations to avoid unnecessary recalculations
  const calculations = useMemo(() => {
    if (safeItems.length === 0) {
      return {
        visibleStart: 0,
        visibleEnd: 0,
        startIndex: 0,
        endIndex: 0,
        totalHeight: 0
      }
    }
    
    const visibleStart = Math.floor(scrollTop / safeItemHeight)
    const visibleEnd = Math.min(
      visibleStart + Math.ceil(safeContainerHeight / safeItemHeight),
      safeItems.length - 1
    )

    const startIndex = Math.max(0, visibleStart - safeOverscan)
    const endIndex = Math.min(safeItems.length - 1, visibleEnd + safeOverscan)
    const totalHeight = safeItems.length * safeItemHeight
    
    return {
      visibleStart,
      visibleEnd,
      startIndex,
      endIndex,
      totalHeight
    }
  }, [scrollTop, safeItemHeight, safeContainerHeight, safeItems.length, safeOverscan])
  
  const visibleItems = useMemo(() => {
    if (safeItems.length === 0 || calculations.startIndex > calculations.endIndex) {
      return []
    }
    
    return safeItems.slice(calculations.startIndex, calculations.endIndex + 1).map((item, index) => ({
      item,
      index: calculations.startIndex + index,
      offsetTop: (calculations.startIndex + index) * safeItemHeight
    }))
  }, [safeItems, calculations.startIndex, calculations.endIndex, safeItemHeight])

  return {
    visibleItems,
    totalHeight: calculations.totalHeight,
    setScrollTop,
    startIndex: calculations.startIndex,
    endIndex: calculations.endIndex
  }
}