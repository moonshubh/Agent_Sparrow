import { apiClient, type EnhancedEventSource } from '@/services/api/api-client'

export interface GlobalKnowledgeSummary {
  window_seconds: number
  total_submissions: number
  by_kind: Record<string, number>
  enhancer_success_rate?: number | null
  store_write_success_rate?: number | null
  fallback_rate?: number | null
  stage_p95_ms: Record<string, number | null>
}

export interface GlobalKnowledgeTimelineEvent {
  event_id: string
  timeline_id: string
  kind: string
  stage: string
  status: string
  created_at: string
  duration_ms?: number | null
  metadata: Record<string, unknown>
  user_id?: string | null
  submission_id?: number | null
  fallback_used?: boolean | null
  store_written?: boolean | null
}

export const GLOBAL_KNOWLEDGE_QUEUE_STATUSES = [
  'received',
  'listed',
  'accepted',
] as const

export type GlobalKnowledgeQueueStatus = typeof GLOBAL_KNOWLEDGE_QUEUE_STATUSES[number]

export interface GlobalKnowledgeQueueItem {
  id: number
  kind: string
  status: GlobalKnowledgeQueueStatus
  summary: string
  raw_text: string
  key_facts: string[]
  tags: string[]
  metadata: Record<string, unknown>
  attachments: Array<Record<string, unknown>>
  created_at: string
  user_id?: string | null
}

export interface GlobalKnowledgeQueueResponse {
  items: GlobalKnowledgeQueueItem[]
}

export interface GlobalKnowledgeEventsResponse {
  items: GlobalKnowledgeTimelineEvent[]
}

export interface GlobalKnowledgeActionResponse {
  success: boolean
  status: string
  message?: string | null
}

export interface QueueQuery {
  kind?: 'feedback' | 'correction' | 'all'
  status?: GlobalKnowledgeQueueStatus
  limit?: number
}

export interface EventsQuery {
  limit?: number
}

export interface StreamOptions {
  since?: string
  onMessage?: (payload: unknown) => void
  onError?: (error: Error) => void
  onClose?: () => void
}

const SUMMARY_ENDPOINT = '/api/v1/global-knowledge/observability/summary'
const QUEUE_ENDPOINT = '/api/v1/global-knowledge/queue'
const EVENTS_ENDPOINT = '/api/v1/global-knowledge/observability/events'
const STREAM_ENDPOINT = '/api/v1/global-knowledge/observability/stream'
const PROMOTE_CORRECTION_ENDPOINT = '/api/v1/global-knowledge/actions/add-to-kb'
const PROMOTE_FEEDBACK_ENDPOINT = '/api/v1/global-knowledge/actions/add-to-feedback'

export const globalKnowledgeApi = {
  async getSummary(windowSeconds?: number): Promise<GlobalKnowledgeSummary> {
    const query = new URLSearchParams()
    if (windowSeconds) {
      query.set('window_seconds', String(windowSeconds))
    }

    const suffix = query.size > 0 ? `?${query.toString()}` : ''
    return apiClient.get<GlobalKnowledgeSummary>(`${SUMMARY_ENDPOINT}${suffix}`)
  },

  async getQueue(params: QueueQuery = {}): Promise<GlobalKnowledgeQueueResponse> {
    const query = new URLSearchParams()
    if (params.kind && params.kind !== 'all') {
      query.set('kind', params.kind)
    }
    if (params.status) {
      query.set('status', params.status)
    }
    if (params.limit) {
      query.set('limit', String(params.limit))
    }

    const suffix = query.size > 0 ? `?${query.toString()}` : ''
    return apiClient.get<GlobalKnowledgeQueueResponse>(`${QUEUE_ENDPOINT}${suffix}`)
  },

  async getEvents(params: EventsQuery = {}): Promise<GlobalKnowledgeEventsResponse> {
    const query = new URLSearchParams()
    if (params.limit) {
      query.set('limit', String(params.limit))
    }

    const suffix = query.size > 0 ? `?${query.toString()}` : ''
    return apiClient.get<GlobalKnowledgeEventsResponse>(`${EVENTS_ENDPOINT}${suffix}`)
  },

  async streamEvents(options: StreamOptions = {}): Promise<EnhancedEventSource> {
    const query = new URLSearchParams()
    if (options.since) {
      query.set('since', options.since)
    }
    const suffix = query.size > 0 ? `?${query.toString()}` : ''
    return apiClient.stream(
      `${STREAM_ENDPOINT}${suffix}`,
      undefined,
      options.onMessage,
      { onError: options.onError, onClose: options.onClose }
    )
  },

  async promoteCorrection(correctionId: number): Promise<GlobalKnowledgeActionResponse> {
    return apiClient.post<GlobalKnowledgeActionResponse>(
      PROMOTE_CORRECTION_ENDPOINT,
      { correction_id: correctionId }
    )
  },

  async promoteFeedback(feedbackId: number): Promise<GlobalKnowledgeActionResponse> {
    return apiClient.post<GlobalKnowledgeActionResponse>(
      PROMOTE_FEEDBACK_ENDPOINT,
      { feedback_id: feedbackId }
    )
  },
}

export type GlobalKnowledgeApi = typeof globalKnowledgeApi
