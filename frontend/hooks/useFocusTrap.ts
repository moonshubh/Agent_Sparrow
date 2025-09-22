import { useEffect, useRef, useCallback } from 'react'

interface UseFocusTrapOptions {
  enabled?: boolean
  returnFocus?: boolean
  initialFocus?: string
  fallbackFocus?: string
}

export function useFocusTrap(
  containerRef: React.RefObject<HTMLElement>,
  options: UseFocusTrapOptions = {}
) {
  const {
    enabled = true,
    returnFocus = true,
    initialFocus,
    fallbackFocus,
  } = options

  const previousActiveElement = useRef<Element | null>(null)

  const getFocusableElements = useCallback((): HTMLElement[] => {
    if (!containerRef.current) return []

    const selector = [
      'a[href]',
      'button:not([disabled])',
      'textarea:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ')

    return Array.from(containerRef.current.querySelectorAll<HTMLElement>(selector))
      .filter(el => el.offsetParent !== null) // Filter out hidden elements
  }, [containerRef])

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!enabled || event.key !== 'Tab') return

    const focusableElements = getFocusableElements()
    if (focusableElements.length === 0) return

    const firstElement = focusableElements[0]
    const lastElement = focusableElements[focusableElements.length - 1]
    const activeElement = document.activeElement

    if (event.shiftKey) {
      // Shift+Tab
      if (activeElement === firstElement || !containerRef.current?.contains(activeElement)) {
        event.preventDefault()
        lastElement.focus()
      }
    } else {
      // Tab
      if (activeElement === lastElement || !containerRef.current?.contains(activeElement)) {
        event.preventDefault()
        firstElement.focus()
      }
    }
  }, [enabled, getFocusableElements, containerRef])

  useEffect(() => {
    if (!enabled || !containerRef.current) return

    // Store current focus
    previousActiveElement.current = document.activeElement

    // Set initial focus
    const setInitialFocus = () => {
      let elementToFocus: HTMLElement | null = null

      if (initialFocus) {
        elementToFocus = containerRef.current?.querySelector<HTMLElement>(initialFocus) ?? null
      }

      if (!elementToFocus && fallbackFocus) {
        elementToFocus = containerRef.current?.querySelector<HTMLElement>(fallbackFocus) ?? null
      }

      if (!elementToFocus) {
        const focusableElements = getFocusableElements()
        elementToFocus = focusableElements[0] ?? null
      }

      if (elementToFocus) {
        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(() => {
          elementToFocus?.focus()
        })
      }
    }

    setInitialFocus()

    // Add event listener
    document.addEventListener('keydown', handleKeyDown)

    // Cleanup
    return () => {
      document.removeEventListener('keydown', handleKeyDown)

      // Return focus
      if (returnFocus && previousActiveElement.current instanceof HTMLElement) {
        previousActiveElement.current.focus()
      }
    }
  }, [enabled, containerRef, initialFocus, fallbackFocus, handleKeyDown, getFocusableElements, returnFocus])

  return {
    getFocusableElements,
  }
}