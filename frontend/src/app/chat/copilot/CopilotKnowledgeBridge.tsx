/**
 * CopilotKnowledgeBridge Component
 *
 * Phase 4: Document Integration Bridge
 *
 * Orchestrates on-demand document registration for CopilotKit:
 * - Listens for user message sends
 * - Triggers document retrieval (KB + FeedMe)
 * - Registers documents via useMakeCopilotDocumentReadable
 * - Subscribes to FeedMe Realtime updates
 * - Manages cache and deduplication
 *
 * Must be mounted INSIDE <CopilotKit> provider
 */

"use client";

import { useCallback, useEffect, useRef, useState } from 'react'
import { useCopilotChat, useMakeCopilotDocumentReadable } from '@copilotkit/react-core'
import { useCopilotDocuments, DocumentPointer } from '@/features/global-knowledge/hooks/useCopilotDocuments'

interface Props {
  sessionId?: string
  agentType: 'primary' | 'log_analysis'
  enabled: boolean
  kbEnabled: boolean
  feedmeEnabled: boolean
  onDocumentsRegistered?: (documents: DocumentPointer[]) => void
}

export function CopilotKnowledgeBridge({
  sessionId = 'default',
  agentType,
  enabled,
  kbEnabled,
  feedmeEnabled,
  onDocumentsRegistered,
}: Props) {
  const { registerForTurn, getCurrentDocuments, invalidateCache, realtimeChannel } = useCopilotDocuments()
  // Loosen type to access messages safely across CopilotKit versions
  const chat = useCopilotChat() as any

  type CopilotMessage = {
    id?: string
    messageId?: string
    role: string
    content: unknown
    createdAt?: string
  }

  // Track last query to avoid re-registration
  const lastQueryRef = useRef<string>('')
  const processedMessageIdsRef = useRef<Set<string>>(new Set())
  const [registeredDocuments, setRegisteredDocuments] = useState<DocumentPointer[]>([])

  /**
   * Register documents on user message
   * This will be called from the parent component when a message is sent
   */
  const handleUserMessage = useCallback(
    async (query: string, options?: { force?: boolean }) => {
      if (!enabled) return
      if (!query) return

      const force = options?.force ?? false

      if (!force && query === lastQueryRef.current) {
        return
      }

      lastQueryRef.current = query

      try {
        const newDocuments = await registerForTurn({
          query,
          agentType,
          sessionId,
          kbEnabled,
          feedmeEnabled,
        })

        const currentDocuments =
          getCurrentDocuments(sessionId, query) ?? newDocuments

        setRegisteredDocuments(currentDocuments)
        onDocumentsRegistered?.(currentDocuments)

        console.log(
          `[CopilotKnowledgeBridge] Registered ${currentDocuments.length} documents for query: "${query}"`
        )
      } catch (error) {
        console.error('[CopilotKnowledgeBridge] Error registering documents:', error)
      }
    },
    [
      enabled,
      agentType,
      sessionId,
      kbEnabled,
      feedmeEnabled,
      registerForTurn,
      getCurrentDocuments,
      onDocumentsRegistered,
    ]
  )

  /**
   * Watch chat messages for new user turns
   */
  useEffect(() => {
    if (!enabled || !chat?.messages) return

    const reversedMessages = [...chat.messages].reverse() as CopilotMessage[]
    const lastUserMessage = reversedMessages.find((message) => message.role === 'user')

    if (!lastUserMessage) {
      return
    }

    const messageKey =
      lastUserMessage.id ||
      lastUserMessage.messageId ||
      `${lastUserMessage.role}:${lastUserMessage.createdAt ?? ''}:${lastUserMessage.content ?? ''}`

    if (processedMessageIdsRef.current.has(messageKey)) {
      return
    }

    const extractContent = (content: unknown): string => {
      if (typeof content === 'string') {
        return content
      }

      if (Array.isArray(content)) {
        return content
          .map((part) => {
            if (typeof part === 'string') {
              return part
            }
            if (typeof part === 'object' && part !== null) {
              const maybeText = (part as { text?: string; value?: string }).text
              const maybeValue = (part as { text?: string; value?: string }).value
              return maybeText || maybeValue || ''
            }
            return ''
          })
          .join(' ')
      }

      if (typeof content === 'object' && content !== null) {
        const candidate = content as { text?: string }
        if (typeof candidate.text === 'string') {
          return candidate.text
        }
      }

      return ''
    }

    const content = extractContent(lastUserMessage.content).trim()

    if (!content) {
      processedMessageIdsRef.current.add(messageKey)
      return
    }

    processedMessageIdsRef.current.add(messageKey)
    handleUserMessage(content)
  }, [chat?.messages, enabled, handleUserMessage])

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      // Invalidate cache when component unmounts
      invalidateCache(sessionId)
    }
  }, [sessionId, invalidateCache])

  useEffect(() => {
    processedMessageIdsRef.current.clear()
    lastQueryRef.current = ''
    setRegisteredDocuments([])
    onDocumentsRegistered?.([])
  }, [sessionId, onDocumentsRegistered])

  useEffect(() => {
    if (!enabled) {
      setRegisteredDocuments([])
      onDocumentsRegistered?.([])
      return
    }

    invalidateCache(sessionId)

    if (!kbEnabled && !feedmeEnabled) {
      setRegisteredDocuments([])
      onDocumentsRegistered?.([])
      return
    }

    if (lastQueryRef.current) {
      handleUserMessage(lastQueryRef.current, { force: true })
    }
  }, [
    enabled,
    kbEnabled,
    feedmeEnabled,
    sessionId,
    handleUserMessage,
    invalidateCache,
    onDocumentsRegistered,
  ])

  // Log realtime subscription status
  useEffect(() => {
    if (realtimeChannel && enabled && feedmeEnabled) {
      console.log('[CopilotKnowledgeBridge] FeedMe Realtime subscription active')
    }
  }, [realtimeChannel, enabled, feedmeEnabled])

  // Register documents with CopilotKit
  // We render individual DocumentReadable components for each document
  return (
    <>
      {registeredDocuments.map((doc) => (
        <DocumentReadable key={doc.documentId} document={doc} />
      ))}
    </>
  )
}

/**
 * Individual document readable component
 * Each calls useMakeCopilotDocumentReadable at top level
 */
function DocumentReadable({ document }: { document: DocumentPointer }) {
  useMakeCopilotDocumentReadable({
    // Align with CopilotKit document readable API; provide id alias and cast to relax version drift
    id: (document as any).documentId ?? document.documentId,
    title: document.title,
    content: document.content,
    description: document.description,
    categories: document.categories,
  } as any)

  return null
}
