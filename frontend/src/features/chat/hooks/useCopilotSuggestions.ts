/**
 * useCopilotSuggestions Hook
 *
 * Phase 4: Smart Suggestion Generation for CopilotKit
 *
 * Provides intelligent suggestion chips after assistant messages with:
 * 1. Backend-provided suggestions (from message.metadata.suggestions)
 * 2. Client-side heuristics (lightweight, no LLM)
 * 3. Doc-aware suggestions (if documents are available)
 *
 * Priority Order:
 * 1. Backend metadata (highest priority, guaranteed <250ms)
 * 2. Context heuristics based on agent_type
 * 3. Document-aware chips (max 1-2)
 *
 * UX Behavior:
 * - Render ONLY after assistant finishes streaming
 * - Max chips: 3 (configurable via NEXT_PUBLIC_SUGGESTIONS_MAX)
 * - Click: Insert text into input (NO auto-send)
 * - Cmd/Ctrl+Enter: Send immediately
 * - Latency budget: <250ms (configurable via NEXT_PUBLIC_SUGGESTIONS_LATENCY_BUDGET_MS)
 */

import { useCallback, useEffect, useState } from 'react'
import { useCopilotChat } from '@copilotkit/react-core'
import type { DocumentPointer } from '@/features/global-knowledge/hooks/useCopilotDocuments'

// ============================================================================
// Types
// ============================================================================

export interface Suggestion {
  id: string
  text: string
  source: 'backend' | 'heuristic' | 'document'
  priority: number
}

export interface SuggestionsOptions {
  agentType: 'primary' | 'log_analysis'
  availableDocuments?: DocumentPointer[]
  conversationContext?: string[]
}

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
  maxSuggestions: Number(process.env.NEXT_PUBLIC_SUGGESTIONS_MAX) || 3,
  latencyBudgetMs: Number(process.env.NEXT_PUBLIC_SUGGESTIONS_LATENCY_BUDGET_MS) || 250,
  enablePerfMarks: process.env.NEXT_PUBLIC_ENABLE_PERF_MARKS === 'true',
}

// ============================================================================
// Performance Instrumentation
// ============================================================================

const perf = {
  mark: (name: string) => {
    if (CONFIG.enablePerfMarks && typeof performance !== 'undefined') {
      performance.mark(name)
    }
  },
  measure: (name: string, startMark: string, endMark: string) => {
    if (CONFIG.enablePerfMarks && typeof performance !== 'undefined') {
      try {
        const measure = performance.measure(name, startMark, endMark)
        console.log(`[Perf] ${name}: ${measure.duration.toFixed(2)}ms`)
        return measure.duration
      } catch (e) {
        // Marks may not exist, silent fail
      }
    }
    return null
  },
}

// ============================================================================
// Backend Metadata Extraction
// ============================================================================

/**
 * Extract suggestions from message metadata
 * Supports multiple paths for backward compatibility
 */
function extractBackendSuggestions(message: any): string[] {
  if (!message) return []

  // Preferred path: message.metadata.suggestions
  if (Array.isArray(message.metadata?.suggestions)) {
    return message.metadata.suggestions
  }

  // Legacy path: message.metadata.messageMetadata.suggestions
  if (Array.isArray(message.metadata?.messageMetadata?.suggestions)) {
    return message.metadata.messageMetadata.suggestions
  }

  return []
}

// ============================================================================
// Client Heuristics
// ============================================================================

/**
 * Generate contextual suggestions based on agent type
 * Lightweight, no LLM calls
 */
function generateHeuristicSuggestions(
  agentType: 'primary' | 'log_analysis',
  context?: string[]
): string[] {
  if (agentType === 'primary') {
    return [
      'Tell me more about this',
      'What are the alternatives?',
      'Can you explain this in simpler terms?',
      'What should I do next?',
    ]
  }

  // log_analysis specific
  return [
    'Show me the timeline',
    'Find correlations in the data',
    'Identify the root cause',
    'What are the error patterns?',
    'Analyze the logs further',
  ]
}

// ============================================================================
// Document-Aware Suggestions
// ============================================================================

/**
 * Generate suggestions that reference available documents
 * Max 1-2 chips
 */
function generateDocumentSuggestions(documents: DocumentPointer[]): string[] {
  if (!documents || documents.length === 0) return []

  const suggestions: string[] = []

  // Take top 2 documents
  const topDocs = documents.slice(0, 2)

  topDocs.forEach((doc) => {
    if (doc.source === 'kb') {
      suggestions.push(`Learn more: ${doc.title}`)
    } else if (doc.source === 'feedme') {
      suggestions.push(`View similar case: ${doc.title}`)
    }
  })

  return suggestions.slice(0, 2) // Max 2 doc-aware chips
}

// ============================================================================
// Suggestion Prioritization
// ============================================================================

/**
 * Combine and prioritize suggestions from all sources
 */
function prioritizeSuggestions(
  backend: string[],
  heuristic: string[],
  docAware: string[]
): Suggestion[] {
  const suggestions: Suggestion[] = []
  let id = 0
  const seen = new Set<string>()

  const addSuggestion = (text: string, source: Suggestion['source'], priority: number) => {
    const normalized = text.trim().toLowerCase()
    if (!text || seen.has(normalized)) {
      return
    }
    seen.add(normalized)
    suggestions.push({
      id: `${source}-${id++}`,
      text,
      source,
      priority,
    })
  }

  // Priority 1: Backend (highest)
  backend.forEach((text) => addSuggestion(text, 'backend', 3))

  // Priority 2: Heuristics
  heuristic.forEach((text) => addSuggestion(text, 'heuristic', 2))

  // Priority 3: Document-aware (lowest)
  docAware.forEach((text) => addSuggestion(text, 'document', 1))

  // Sort by priority (highest first)
  suggestions.sort((a, b) => b.priority - a.priority)

  // Take max configured count
  return suggestions.slice(0, CONFIG.maxSuggestions)
}

// ============================================================================
// Main Hook
// ============================================================================

export function useCopilotSuggestions(options: SuggestionsOptions) {
  const { agentType, availableDocuments, conversationContext } = options
  // Loosen type to support optional helpers like setInput/submitMessage across versions
  const chat = useCopilotChat() as any

  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [isGenerating, setIsGenerating] = useState(false)

  /**
   * Generate suggestions for the last assistant message
   */
  const generateSuggestions = useCallback(
    (lastMessage: any) => {
      perf.mark('suggestions-start')
      setIsGenerating(true)

      try {
        // 1. Extract backend suggestions
        const backendSuggestions = extractBackendSuggestions(lastMessage)

        // 2. Generate heuristic suggestions
        const heuristicSuggestions = generateHeuristicSuggestions(agentType, conversationContext)

        // 3. Generate document-aware suggestions
        const docSuggestions = generateDocumentSuggestions(availableDocuments || [])

        // 4. Prioritize and combine
        const prioritized = prioritizeSuggestions(
          backendSuggestions,
          heuristicSuggestions,
          docSuggestions
        )

        setSuggestions(prioritized)

        perf.mark('suggestions-end')
        const duration = perf.measure('suggestions-duration', 'suggestions-start', 'suggestions-end')

        if (duration && duration > CONFIG.latencyBudgetMs) {
          console.warn(
            `[useCopilotSuggestions] Generation took ${duration.toFixed(2)}ms, exceeds budget of ${CONFIG.latencyBudgetMs}ms`
          )
        }
      } catch (error) {
        console.error('[useCopilotSuggestions] Error generating suggestions:', error)
        setSuggestions([])
      } finally {
        setIsGenerating(false)
      }
    },
    [agentType, availableDocuments, conversationContext]
  )

  /**
   * Handle suggestion click: insert into input
   */
  const handleSuggestionClick = useCallback(
    (suggestion: Suggestion, sendImmediately: boolean = false) => {
      if (!chat) return

      // Insert text into input
      chat.setInput(suggestion.text)

      // If sendImmediately (Cmd/Ctrl+Enter), submit the message
      if (sendImmediately && typeof chat.submitMessage === 'function') {
        chat.submitMessage()
      }
    },
    [chat]
  )

  /**
   * Monitor last message for streaming completion
   * Fix: Added all dependencies to prevent stale closures
   */
  useEffect(() => {
    if (!chat) return

    const messages = chat.messages
    const isStreaming = chat.isLoading

    if (!messages || messages.length === 0) {
      setSuggestions([])
      return
    }

    const lastMessage = messages[messages.length - 1]

    // Only generate for assistant messages
    if (lastMessage.role !== 'assistant') {
      setSuggestions([])
      return
    }

    // Skip tool-result or status-only messages
    const content = lastMessage.content || ''
    if (content.includes('[Tool Result]') || content.includes('[Status]')) {
      setSuggestions([])
      return
    }

    // Check if streaming is complete
    if (!isStreaming) {
      // Assistant finished streaming, generate suggestions
      generateSuggestions(lastMessage)
    } else {
      // Still streaming, clear suggestions to avoid jitter
      setSuggestions([])
    }
  }, [chat, chat?.messages, chat?.isLoading, generateSuggestions])

  return {
    suggestions,
    isGenerating,
    handleSuggestionClick,
    clearSuggestions: useCallback(() => setSuggestions([]), []),
  }
}

// Export types
// Note: SuggestionsOptions interface is already exported above
