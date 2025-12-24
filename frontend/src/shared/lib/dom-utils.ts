/**
 * Safe DOM utilities
 */

export function safeQuerySelector<T extends Element>(
  selector: string,
  parent: Document | Element = document
): T | null {
  try {
    return parent.querySelector<T>(selector)
  } catch (error) {
    console.warn(`Failed to query selector: ${selector}`, error)
    return null
  }
}

export function safeAddEventListener(
  element: Element | Window | Document | null,
  event: string,
  handler: EventListener,
  options?: AddEventListenerOptions
): () => void {
  if (!element) {
    return () => {} // No-op cleanup
  }

  try {
    element.addEventListener(event, handler, options)
    return () => element.removeEventListener(event, handler, options)
  } catch (error) {
    console.warn(`Failed to add event listener: ${event}`, error)
    return () => {}
  }
}

export function safeFocus(element: HTMLElement | null): void {
  if (!element) return

  try {
    // Use requestAnimationFrame to ensure element is ready
    requestAnimationFrame(() => {
      if (document.contains(element)) {
        element.focus()
      }
    })
  } catch (error) {
    console.warn('Failed to focus element', error)
  }
}

export function safeScrollIntoView(
  element: Element | null,
  options?: ScrollIntoViewOptions
): void {
  if (!element) return

  try {
    if (document.contains(element)) {
      element.scrollIntoView(options ?? { behavior: 'smooth', block: 'center' })
    }
  } catch (error) {
    console.warn('Failed to scroll element into view', error)
  }
}