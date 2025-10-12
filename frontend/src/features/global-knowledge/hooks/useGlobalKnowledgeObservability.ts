import { useCallback, useEffect, useRef, useState } from 'react'

import {
  globalKnowledgeApi,
  type GlobalKnowledgeActionResponse,
  type GlobalKnowledgeQueueItem,
  type GlobalKnowledgeQueueStatus,
  type GlobalKnowledgeSummary,
  type GlobalKnowledgeTimelineEvent,
} from '@/features/global-knowledge/services/global-knowledge-api'
import { sortEventsDescending, upsertTimelineEvent } from '@/features/global-knowledge/services/global-knowledge-events'
import { usePolling } from '@/shared/hooks/usePolling'

const MAX_TIMELINE_EVENTS = 150

const toErrorMessage = (error: unknown): string =>
  error instanceof Error ? error.message : String(error ?? 'Unknown error')

export type QueueKind = 'all' | 'feedback' | 'correction'

export interface GlobalKnowledgeObservabilityState {
  summary: GlobalKnowledgeSummary | null
  queue: GlobalKnowledgeQueueItem[]
  events: GlobalKnowledgeTimelineEvent[]
  isSummaryLoading: boolean
  isQueueLoading: boolean
  isEventsLoading: boolean
  summaryError: string | null
  queueError: string | null
  eventsError: string | null
  streamError: string | null
  isStreamConnected: boolean
  queueFilter: {
    kind: QueueKind
    status: GlobalKnowledgeQueueStatus
  }
  refreshSummary: () => Promise<void>
  refreshQueue: () => Promise<void>
  refreshEvents: () => Promise<void>
  setQueueFilter: (next: Partial<{ kind: QueueKind; status: GlobalKnowledgeQueueStatus }>) => void
  promoteCorrection: (correctionId: number) => Promise<GlobalKnowledgeActionResponse>
  promoteFeedback: (feedbackId: number) => Promise<GlobalKnowledgeActionResponse>
}

const INITIAL_QUEUE_FILTER: GlobalKnowledgeObservabilityState['queueFilter'] = {
  kind: 'all',
  status: 'received',
}

export const useGlobalKnowledgeObservability = (): GlobalKnowledgeObservabilityState => {
  const [summary, setSummary] = useState<GlobalKnowledgeSummary | null>(null)
  const [queue, setQueue] = useState<GlobalKnowledgeQueueItem[]>([])
  const [events, setEvents] = useState<GlobalKnowledgeTimelineEvent[]>([])

  const [isSummaryLoading, setIsSummaryLoading] = useState(true)
  const [isQueueLoading, setIsQueueLoading] = useState(true)
  const [isEventsLoading, setIsEventsLoading] = useState(true)

  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [queueError, setQueueError] = useState<string | null>(null)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)

  const [isStreamConnected, setIsStreamConnected] = useState(false)
  const [queueFilter, setQueueFilterState] = useState(INITIAL_QUEUE_FILTER)

  const latestEventTimestampRef = useRef<string | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const streamRef = useRef<ReturnType<typeof globalKnowledgeApi.streamEvents> | null>(null)
  const reconnectDelayRef = useRef<number>(2000)
  const summaryLoadedRef = useRef(false)
  const queueLoadedRef = useRef(false)
  const eventsLoadedRef = useRef(false)

  const refreshSummary = useCallback(async () => {
    if (!summaryLoadedRef.current) {
      setIsSummaryLoading(true)
    }
    try {
      const response = await globalKnowledgeApi.getSummary()
      setSummary(response)
      setSummaryError(null)
    } catch (error) {
      setSummaryError(toErrorMessage(error))
    } finally {
      setIsSummaryLoading(false)
      summaryLoadedRef.current = true
    }
  }, [])

  const refreshQueue = useCallback(async () => {
    if (!queueLoadedRef.current) {
      setIsQueueLoading(true)
    }
    try {
      const response = await globalKnowledgeApi.getQueue({
        kind: queueFilter.kind,
        status: queueFilter.status,
        limit: 30,
      })
      setQueue(response.items)
      setQueueError(null)
    } catch (error) {
      setQueueError(toErrorMessage(error))
    } finally {
      setIsQueueLoading(false)
      queueLoadedRef.current = true
    }
  }, [queueFilter.kind, queueFilter.status])

  const refreshEvents = useCallback(async () => {
    if (!eventsLoadedRef.current) {
      setIsEventsLoading(true)
    }
    try {
      const response = await globalKnowledgeApi.getEvents({ limit: MAX_TIMELINE_EVENTS })
      const sorted = sortEventsDescending(response.items)
      setEvents(sorted)
      latestEventTimestampRef.current = sorted[0]?.created_at ?? null
      setEventsError(null)
    } catch (error) {
      setEventsError(toErrorMessage(error))
    } finally {
      setIsEventsLoading(false)
      eventsLoadedRef.current = true
    }
  }, [])

  const handleStreamMessage = useCallback((payload: unknown) => {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return
    }

    const record = payload as { type?: string; data?: GlobalKnowledgeTimelineEvent }
    if (record.type !== 'timeline-step' || !record.data) {
      return
    }

    const eventData = record.data

    setEvents(prev => {
      const next = upsertTimelineEvent(prev, eventData, MAX_TIMELINE_EVENTS)
      latestEventTimestampRef.current = next[0]?.created_at ?? latestEventTimestampRef.current
      return next
    })
  }, [])

  const refreshStream = useCallback(async () => {
    const enqueueReconnect = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }

      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 20000)
        void refreshStream()
      }, reconnectDelayRef.current)
    }

    if (streamRef.current) {
      streamRef.current
        .then(source => source.close())
        .catch(() => undefined)
      streamRef.current = null
    }

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    setIsStreamConnected(false)

    try {
      streamRef.current = globalKnowledgeApi.streamEvents({
        since: latestEventTimestampRef.current ?? undefined,
        onMessage: handleStreamMessage,
        onError: error => {
          setStreamError(toErrorMessage(error))
          setIsStreamConnected(false)
          enqueueReconnect()
        },
        onClose: () => {
          setIsStreamConnected(false)
          enqueueReconnect()
        },
      })

      await streamRef.current
      reconnectDelayRef.current = 2000
      setStreamError(null)
      setIsStreamConnected(true)
    } catch (error) {
      setStreamError(toErrorMessage(error))
      setIsStreamConnected(false)
      enqueueReconnect()
    }
  }, [handleStreamMessage])

  usePolling({ enabled: true, interval: 30000, onPoll: refreshSummary })
  usePolling({ enabled: true, interval: 45000, onPoll: refreshQueue })

  useEffect(() => {
    void refreshSummary()
  }, [refreshSummary])

  useEffect(() => {
    void refreshQueue()
  }, [refreshQueue])

  useEffect(() => {
    void refreshEvents()
  }, [refreshEvents])

  useEffect(() => {
    reconnectDelayRef.current = 2000
    void refreshStream()

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }

      reconnectTimerRef.current = null

      if (streamRef.current) {
        streamRef.current
          .then(source => source.close())
          .catch(() => undefined)
        streamRef.current = null
      }
    }
  }, [refreshStream])

  const setQueueFilter = useCallback((next: Partial<{ kind: QueueKind; status: GlobalKnowledgeQueueStatus }>) => {
    setQueueFilterState(prev => ({
      kind: next.kind ?? prev.kind,
      status: next.status ?? prev.status,
    }))
  }, [])

  const promoteCorrection = useCallback(async (correctionId: number) => {
    const response = await globalKnowledgeApi.promoteCorrection(correctionId)
    if (response.success === true) {
      setQueue(prev => prev.filter(item => item.kind !== 'correction' || item.id !== correctionId))
    }
    return response
  }, [])

  const promoteFeedback = useCallback(async (feedbackId: number) => {
    const response = await globalKnowledgeApi.promoteFeedback(feedbackId)
    if (response.success === true) {
      setQueue(prev => prev.filter(item => item.kind !== 'feedback' || item.id !== feedbackId))
    }
    return response
  }, [])

  return {
    summary,
    queue,
    events,
    isSummaryLoading,
    isQueueLoading,
    isEventsLoading,
    summaryError,
    queueError,
    eventsError,
    streamError,
    isStreamConnected,
    queueFilter,
    refreshSummary,
    refreshQueue,
    refreshEvents,
    setQueueFilter,
    promoteCorrection,
    promoteFeedback,
  }
}

export type UseGlobalKnowledgeObservability = ReturnType<typeof useGlobalKnowledgeObservability>
