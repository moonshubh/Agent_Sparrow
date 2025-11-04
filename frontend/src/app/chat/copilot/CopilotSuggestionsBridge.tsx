/**
 * CopilotSuggestionsBridge Component
 *
 * Phase 4: Suggestion Generation Bridge
 *
 * Manages intelligent suggestion chips after assistant messages:
 * - Listens for end-of-streaming events
 * - Generates suggestions via useCopilotSuggestions hook
 * - Exposes suggestion state for parent component rendering
 * - Handles chip click behavior (insert text, optional send)
 *
 * Must be mounted INSIDE <CopilotKit> provider
 */

"use client";

import { useCallback, useEffect } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'
import { useCopilotSuggestions, Suggestion } from '@/features/chat/hooks/useCopilotSuggestions'
import type { DocumentPointer } from '@/features/global-knowledge/hooks/useCopilotDocuments'

interface Props {
  agentType: 'primary' | 'log_analysis'
  enabled: boolean
  availableDocuments?: DocumentPointer[]
  onSuggestionsChange?: (payload: {
    suggestions: Suggestion[]
    isGenerating: boolean
    handleClick: (suggestion: Suggestion, options?: { sendImmediately?: boolean }) => void
    clear: () => void
  }) => void
}

export function CopilotSuggestionsBridge({
  agentType,
  enabled,
  availableDocuments,
  onSuggestionsChange,
}: Props) {
  const { suggestions, isGenerating, handleSuggestionClick, clearSuggestions } = useCopilotSuggestions({
    agentType,
    availableDocuments,
  })

  /**
   * Handle keyboard events for power-user send
   */
  const handleChipClick = useCallback(
    (suggestion: Suggestion, event?: MouseEvent | KeyboardEvent) => {
      if (!enabled) return

      const metaKey = event && 'metaKey' in event ? event.metaKey || event.ctrlKey || false : false
      const isKeyboardEvent = !!event && 'key' in event
      const key = isKeyboardEvent ? (event as KeyboardEvent).key : undefined

      const sendImmediately = isKeyboardEvent
        ? metaKey && key === 'Enter'
        : metaKey

      if (event) {
        event.preventDefault()
        event.stopPropagation()
      }

      handleSuggestionClick(suggestion, sendImmediately)
    },
    [enabled, handleSuggestionClick]
  )

  useEffect(() => {
    onSuggestionsChange?.({
      suggestions: enabled ? suggestions : [],
      isGenerating: enabled ? isGenerating : false,
      handleClick: handleChipClick,
      clear: clearSuggestions,
    })
  }, [
    enabled,
    suggestions,
    isGenerating,
    handleChipClick,
    clearSuggestions,
    onSuggestionsChange,
  ])

  // This is a bridge component, no visual output
  // Suggestions are rendered by CustomAssistantMessage
  return null
}
