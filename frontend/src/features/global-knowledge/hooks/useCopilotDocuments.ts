/**
 * useCopilotDocuments Hook
 *
 * Phase 4: Document Integration for CopilotKit
 *
 * Provides on-demand document pointer registration for:
 * - Mailbird Knowledge Base (via search_mailbird_knowledge_rpc)
 * - FeedMe Conversations (via direct Supabase query)
 *
 * Features:
 * - On-demand retrieval per user turn (no upfront registration)
 * - TTL-based caching per (session_id, query)
 * - Session-based deduplication
 * - Agent-biased ranking (primary: KB 60/40, log_analysis: FeedMe 60/40)
 * - Realtime updates for FeedMe status changes
 * - Performance instrumentation (gated by NEXT_PUBLIC_ENABLE_PERF_MARKS)
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { supabase } from '@/services/supabase'
import type { RealtimeChannel } from '@supabase/supabase-js'

// ============================================================================
// Types
// ============================================================================

interface KBMetadata {
  status?: string | null
  archived?: boolean | null
  language?: string | null
  updated_at?: string | null
  description?: string | null
  categories?: string[]
}

interface KBSearchResult {
  id: string
  url: string
  title: string
  markdown: string
  metadata: KBMetadata | null
  score?: number
}

interface FeedMeDocument {
  id: number
  title: string
  extracted_text: string
  metadata: Record<string, unknown> | null
  platform?: string
  tags?: string[]
  folder_id?: number
  extraction_quality_score?: number
  created_at: string
}

interface DocumentPointer {
  documentId: string
  title: string
  content: string
  description?: string
  categories?: string[]
  source: 'kb' | 'feedme'
  score?: number
}

interface RegisterOptions {
  query: string
  agentType: 'primary' | 'log_analysis'
  sessionId?: string
  kbEnabled?: boolean
  feedmeEnabled?: boolean
}

interface CacheEntry {
  documents: DocumentPointer[]
  timestamp: number
  query: string
}

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
  topK: Number(process.env.NEXT_PUBLIC_DOCS_TOPK) || 8,
  ttlMs: Number(process.env.NEXT_PUBLIC_DOCS_TTL_MS) || 300000, // 5 minutes
  enablePerfMarks: process.env.NEXT_PUBLIC_ENABLE_PERF_MARKS === 'true',
  feedmeQualityThreshold: 0.75,
  feedmeStatuses: ['approved', 'published'] as const,
  maxContentChars: 15000,
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
      } catch {
        // Marks may not exist, silent fail
      }
    }
    return null
  },
}

// ============================================================================
// KB Search (via RPC)
// ============================================================================

async function searchMailbirdKB(
  query: string,
  topK: number = CONFIG.topK
): Promise<KBSearchResult[]> {
  perf.mark('kb-search-start')

  try {
    const { data, error } = await supabase.rpc('search_mailbird_knowledge_rpc', {
      query_text: query,
      top_k: topK,
      min_score: 0.0,
    })

    perf.mark('kb-search-end')
    perf.measure('kb-search-duration', 'kb-search-start', 'kb-search-end')

    if (error) {
      console.error('[useCopilotDocuments] KB search RPC error:', error)
      return []
    }

    // Apply filters (best-effort, column-dependent)
    const rawResults = (data ?? []) as KBSearchResult[]
    const filtered = rawResults.filter((doc) => {
      // Filter by status if exists
      if (doc.metadata?.status && doc.metadata.status !== 'published') {
        return false
      }

      // Filter out archived if exists
      if (doc.metadata?.archived === true) {
        return false
      }

      return true
    })

    // Boost English and recent docs (soft preference)
    const boosted = filtered.map((doc) => {
      let boost = 1.0

      // Language boost
      if (doc.metadata?.language === 'en') {
        boost *= 1.1
      }

      // Recency boost (prefer ≤ 24 months)
      if (doc.metadata?.updated_at) {
        const updatedAt = new Date(doc.metadata.updated_at)
        const ageMonths = (Date.now() - updatedAt.getTime()) / (1000 * 60 * 60 * 24 * 30)
        if (ageMonths <= 24) {
          boost *= 1.05
        }
      }

      return {
        ...doc,
        score: (doc.score || 0) * boost,
      }
    })

    // Re-sort by boosted score
    boosted.sort((a, b) => (b.score || 0) - (a.score || 0))

    return boosted.slice(0, topK)
  } catch (error) {
    console.error('[useCopilotDocuments] KB search error:', error)
    return []
  }
}

// ============================================================================
// FeedMe Query
// ============================================================================

async function searchFeedMe(topK: number = CONFIG.topK): Promise<FeedMeDocument[]> {
  perf.mark('feedme-search-start')

  try {
    const { data, error } = await supabase
      .from('feedme_conversations')
      .select('id, title, extracted_text, metadata, platform, tags, folder_id, extraction_quality_score, created_at')
      .eq('processing_status', 'completed')
      .in('approval_status', Array.from(CONFIG.feedmeStatuses))
      .gte('extraction_quality_score', CONFIG.feedmeQualityThreshold)
      .order('created_at', { ascending: false })
      .limit(topK)

    perf.mark('feedme-search-end')
    perf.measure('feedme-search-duration', 'feedme-search-start', 'feedme-search-end')

    if (error) {
      console.error('[useCopilotDocuments] FeedMe query error:', error)
      return []
    }

    return data || []
  } catch (error) {
    console.error('[useCopilotDocuments] FeedMe search error:', error)
    return []
  }
}

// ============================================================================
// Document Conversion
// ============================================================================

function kbToPointer(doc: KBSearchResult): DocumentPointer {
  const content = (doc.markdown || doc.url || '').slice(0, CONFIG.maxContentChars)

  return {
    documentId: `kb-${doc.id}`,
    title: doc.title || doc.url || 'Untitled KB Article',
    content,
    description: doc.metadata?.description || `Knowledge base article: ${doc.title}`,
    categories: doc.metadata?.categories || [],
    source: 'kb',
    score: doc.score,
  }
}

function feedmeToPointer(doc: FeedMeDocument): DocumentPointer {
  const content = (doc.extracted_text || '').slice(0, CONFIG.maxContentChars)

  return {
    documentId: `feedme-${doc.id}`,
    title: doc.title || 'Untitled Conversation',
    content,
    description: `Support conversation from ${doc.platform || 'unknown platform'}`,
    categories: doc.tags || [],
    source: 'feedme',
    score: doc.extraction_quality_score,
  }
}

// ============================================================================
// Agent-Biased Ranking
// ============================================================================

function applyAgentBias(
  documents: DocumentPointer[],
  agentType: 'primary' | 'log_analysis'
): DocumentPointer[] {
  const ranked = documents.map((doc) => {
    let biasedScore = doc.score || 0.5

    if (agentType === 'primary') {
      // Primary: KB 60%, FeedMe 40%
      biasedScore *= doc.source === 'kb' ? 1.5 : 1.0
    } else {
      // Log Analysis: FeedMe 60%, KB 40%
      biasedScore *= doc.source === 'feedme' ? 1.5 : 1.0
    }

    return { ...doc, score: biasedScore }
  })

  ranked.sort((a, b) => (b.score || 0) - (a.score || 0))
  return ranked
}

// ============================================================================
// Main Hook
// ============================================================================

export function useCopilotDocuments() {
  // Cache: Map<sessionId, Map<query, CacheEntry>>
  const cacheRef = useRef<Map<string, Map<string, CacheEntry>>>(new Map())

  // Deduplication: Set<documentId> per session
  const registeredRef = useRef<Map<string, Set<string>>>(new Map())

  // Realtime subscription
  const [realtimeChannel, setRealtimeChannel] = useState<RealtimeChannel | null>(null)

  // Debounce timer for realtime updates
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)

  /**
   * Register documents for a user turn
   */
  const registerForTurn = useCallback(async (options: RegisterOptions) => {
    const {
      query,
      agentType,
      sessionId = 'default',
      kbEnabled = true,
      feedmeEnabled = true,
    } = options

    perf.mark('register-start')

    // Check cache
    const sessionCache = cacheRef.current.get(sessionId)
    const cached = sessionCache?.get(query)

    if (cached && Date.now() - cached.timestamp < CONFIG.ttlMs) {
      console.log(`[useCopilotDocuments] Cache hit for session=${sessionId}, query="${query}"`)
      perf.mark('register-end')
      perf.measure('register-duration', 'register-start', 'register-end')
      return cached.documents
    }

    // Fetch documents in parallel
    const [kbDocs, feedmeDocs] = await Promise.all([
      kbEnabled ? searchMailbirdKB(query, CONFIG.topK) : Promise.resolve([]),
      feedmeEnabled ? searchFeedMe(CONFIG.topK) : Promise.resolve([]),
    ])

    // Convert to pointers
    const kbPointers = kbDocs.map(kbToPointer)
    const feedmePointers = feedmeDocs.map(feedmeToPointer)

    // Merge and apply agent bias
    const allPointers = [...kbPointers, ...feedmePointers]
    const rankedPointers = applyAgentBias(allPointers, agentType)

    // Take top K
    const topPointers = rankedPointers.slice(0, CONFIG.topK)

    // Deduplication: filter out already registered docs for this session
    const sessionRegistered = registeredRef.current.get(sessionId) || new Set()
    const newPointers = topPointers.filter((doc) => !sessionRegistered.has(doc.documentId))

    // Update cache
    if (!cacheRef.current.has(sessionId)) {
      cacheRef.current.set(sessionId, new Map())
    }
    cacheRef.current.get(sessionId)!.set(query, {
      documents: topPointers,
      timestamp: Date.now(),
      query,
    })

    // Update registered set
    newPointers.forEach((doc) => sessionRegistered.add(doc.documentId))
    registeredRef.current.set(sessionId, sessionRegistered)

    perf.mark('register-end')
    perf.measure('register-duration', 'register-start', 'register-end')

    console.log(`[useCopilotDocuments] Registered ${newPointers.length} new documents for session=${sessionId}`)

    return newPointers
  }, [])

  /**
   * Get current documents (for external use)
   */
  const getCurrentDocuments = useCallback((sessionId: string, query: string): DocumentPointer[] | null => {
    const sessionCache = cacheRef.current.get(sessionId)
    const cached = sessionCache?.get(query)

    if (cached && Date.now() - cached.timestamp < CONFIG.ttlMs) {
      return cached.documents
    }

    return null
  }, [])

  /**
   * Invalidate cache for a session
   */
  const invalidateCache = useCallback((sessionId?: string) => {
    if (sessionId) {
      cacheRef.current.delete(sessionId)
      registeredRef.current.delete(sessionId)
    } else {
      cacheRef.current.clear()
      registeredRef.current.clear()
    }
  }, [])

  /**
   * Setup Realtime subscription for FeedMe updates
   * Fix: Properly await unsubscribe and clear state to prevent memory leaks
   */
  useEffect(() => {
    const channel = supabase
      .channel('public:feedme_conversations')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'feedme_conversations',
        },
        (payload) => {
          // Debounce: only invalidate cache after 500ms of no updates
          if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current)
          }

          debounceTimerRef.current = setTimeout(() => {
            console.log('[useCopilotDocuments] FeedMe realtime update, invalidating cache')

            // Check if the update qualifies (status change to approved/published)
            type FeedMeRealtimeRecord = {
              processing_status?: string | null
              approval_status?: string | null
              extraction_quality_score?: number | null
            }

            const newRecord = payload.new as FeedMeRealtimeRecord | null
            if (!newRecord) {
              return
            }

            const { processing_status, approval_status, extraction_quality_score } = newRecord

            const allowedStatuses: readonly string[] = CONFIG.feedmeStatuses

            if (
              processing_status === 'completed' &&
              typeof approval_status === 'string' &&
              allowedStatuses.includes(approval_status) &&
              (extraction_quality_score ?? 0) >= CONFIG.feedmeQualityThreshold
            ) {
              // Invalidate all caches to force refresh
              invalidateCache()
            }
          }, 500)
        }
      )
      .subscribe()

    setRealtimeChannel(channel)

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
      // Properly await unsubscribe and clear state
      channel.unsubscribe().then(() => {
        setRealtimeChannel(null)
      })
    }
  }, [invalidateCache])

  return {
    registerForTurn,
    getCurrentDocuments,
    invalidateCache,
    realtimeChannel,
  }
}

// Export types
export type { DocumentPointer, RegisterOptions }
