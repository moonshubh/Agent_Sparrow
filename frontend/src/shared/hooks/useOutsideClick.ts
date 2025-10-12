/**
 * useOutsideClick Hook
 * 
 * Detects clicks outside of a target element for menu and modal closing behavior.
 * Apple/Google-level interaction polish with proper event handling.
 */

import { useEffect, useRef, RefObject } from 'react'

interface UseOutsideClickOptions {
  enabled?: boolean
  excludeElements?: RefObject<HTMLElement>[]
  onClickOutside: (event: MouseEvent | TouchEvent) => void
}

export function useOutsideClick<T extends HTMLElement = HTMLDivElement>(
  options: UseOutsideClickOptions
): RefObject<T | null> {
  const ref = useRef<T | null>(null)
  const { enabled = true, excludeElements = [], onClickOutside } = options

  useEffect(() => {
    if (!enabled) return

    const handleClickOutside = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node

      // Check if click is inside the main element
      if (ref.current && ref.current.contains(target)) {
        return
      }

      // Check if click is inside any excluded elements
      const isInExcludedElement = excludeElements.some(excludeRef => 
        excludeRef.current && excludeRef.current.contains(target)
      )

      if (isInExcludedElement) {
        return
      }

      // Click is outside - trigger callback
      onClickOutside(event)
    }

    // Delay adding listeners to avoid immediate triggering
    const timeoutId = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside)
      document.addEventListener('touchstart', handleClickOutside)
    }, 0)

    return () => {
      clearTimeout(timeoutId)
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [enabled, excludeElements, onClickOutside])

  return ref
}

// Simplified version for basic use cases
export function useSimpleOutsideClick<T extends HTMLElement = HTMLDivElement>(
  onClickOutside: () => void,
  enabled = true
): RefObject<T | null> {
  return useOutsideClick<T>({
    enabled,
    onClickOutside
  })
}
