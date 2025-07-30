"use client"

import { useCallback, useEffect, useRef, useState } from 'react'

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
 */
export function useThrottle<T>(value: T, interval: number): T {
  const [throttledValue, setThrottledValue] = useState<T>(value)
  const lastExecuted = useRef<number>(Date.now())

  useEffect(() => {
    if (Date.now() >= lastExecuted.current + interval) {
      lastExecuted.current = Date.now()
      setThrottledValue(value)
    } else {
      const timerId = setTimeout(() => {
        lastExecuted.current = Date.now()
        setThrottledValue(value)
      }, interval)

      return () => clearTimeout(timerId)
    }
  }, [value, interval])

  return throttledValue
}

/**
 * Performance monitoring hook for measuring render times and detecting performance issues.
 */
export function usePerformanceMonitor(componentName: string, logThreshold: number = 16) {
  const renderStartTime = useRef<number>(0)
  const renderCount = useRef<number>(0)
  const slowRenderCount = useRef<number>(0)

  useEffect(() => {
    renderStartTime.current = performance.now()
    renderCount.current += 1
  })

  useEffect(() => {
    const renderTime = performance.now() - renderStartTime.current
    
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
  })

  return {
    renderCount: renderCount.current,
    slowRenderCount: slowRenderCount.current
  }
}

/**
 * Intersection Observer hook for implementing lazy loading and visibility detection.
 */
export function useIntersectionObserver(
  options: IntersectionObserverInit = {},
  triggerOnce: boolean = true
) {
  const [isIntersecting, setIsIntersecting] = useState(false)
  const [hasIntersected, setHasIntersected] = useState(false)
  const targetRef = useRef<HTMLElement | null>(null)

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
      {
        threshold: 0.1,
        rootMargin: '10px',
        ...options
      }
    )

    observer.observe(target)

    return () => {
      observer.unobserve(target)
    }
  }, [options.root, options.rootMargin, options.threshold, triggerOnce])

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
 */
export function useStableCallback<T extends (...args: any[]) => any>(
  callback: T
): T {
  const callbackRef = useRef<T>(callback)

  useEffect(() => {
    callbackRef.current = callback
  })

  return useCallback(
    ((...args: Parameters<T>) => callbackRef.current(...args)) as T,
    []
  )
}

/**
 * Memory usage monitor (development only).
 */
export function useMemoryMonitor(componentName: string, interval: number = 5000) {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'development') return

    const checkMemory = () => {
      if ('memory' in performance) {
        const memory = (performance as any).memory
        const used = Math.round(memory.usedJSHeapSize / 1048576 * 100) / 100
        const total = Math.round(memory.totalJSHeapSize / 1048576 * 100) / 100
        const limit = Math.round(memory.jsHeapSizeLimit / 1048576 * 100) / 100

        if (used > limit * 0.8) {
          console.warn(
            `🚨 High memory usage in ${componentName}:`,
            `${used}MB / ${limit}MB (${Math.round((used / limit) * 100)}%)`
          )
        }
      }
    }

    const intervalId = setInterval(checkMemory, interval)
    return () => clearInterval(intervalId)
  }, [componentName, interval])
}

/**
 * Efficient list virtualization helper.
 */
export function useVirtualization<T>(
  items: T[],
  itemHeight: number,
  containerHeight: number,
  overscan: number = 5
) {
  const [scrollTop, setScrollTop] = useState(0)

  const visibleStart = Math.floor(scrollTop / itemHeight)
  const visibleEnd = Math.min(
    visibleStart + Math.ceil(containerHeight / itemHeight),
    items.length - 1
  )

  const startIndex = Math.max(0, visibleStart - overscan)
  const endIndex = Math.min(items.length - 1, visibleEnd + overscan)

  const visibleItems = items.slice(startIndex, endIndex + 1).map((item, index) => ({
    item,
    index: startIndex + index,
    offsetTop: (startIndex + index) * itemHeight
  }))

  const totalHeight = items.length * itemHeight

  return {
    visibleItems,
    totalHeight,
    setScrollTop,
    startIndex,
    endIndex
  }
}