import type { UIMessage, UIMessageChunk } from 'ai'
import { DefaultChatTransport } from 'ai'
import { resolve } from '@ai-sdk/provider-utils'
import { EventSourceParserStream } from 'eventsource-parser/stream'

import { filterUIMessageStream } from '@/services/api/providers/filtering-transport'
import { getApiBaseUrl } from '@/shared/lib/utils/environment'

type UnifiedTransportOptions = {
  provider: string
  model: string
  sessionId: string
  getAuthToken?: () => Promise<string | null>
  endpoint?: string
}

function extractTextFromMessage(message: UIMessage): string {
  if (!message?.parts) return ''
  return message.parts
    .filter(part => part.type === 'text')
    .map(part => part.text)
    .join('')
}

function buildHistory(messages: UIMessage[]): { role: string; content: string }[] {
  return messages
    .filter(msg => msg.role === 'user' || msg.role === 'assistant')
    .map(msg => ({
      role: msg.role,
      content: extractTextFromMessage(msg),
    }))
    .filter(entry => entry.content.length > 0)
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const asRecord = (value: unknown): Record<string, unknown> | undefined =>
  isRecord(value) ? value : undefined

const getString = (source: Record<string, unknown>, key: string): string | undefined => {
  const value = source[key]
  return typeof value === 'string' ? value : undefined
}

const getNumber = (source: Record<string, unknown>, key: string): number | undefined => {
  const value = source[key]
  if (typeof value === 'number') return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

const getArray = (value: unknown): unknown[] | undefined => (Array.isArray(value) ? value : undefined)

const generateStreamId = () => {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch (error) {
    console.warn('[UnifiedChatTransport] Falling back to pseudo-random id:', error)
  }
  return `stream-${Math.random().toString(36).slice(2)}`
}

const toTextStream = (stream: ReadableStream<Uint8Array<ArrayBufferLike>>) => {
  if (typeof TextDecoderStream !== 'undefined') {
    return stream.pipeThrough(new TextDecoderStream())
  }

  const decoder = new TextDecoder()
  return stream.pipeThrough(
    new TransformStream<Uint8Array, string>({
      transform(chunk, controller) {
        controller.enqueue(decoder.decode(chunk, { stream: true }))
      },
      flush(controller) {
        controller.enqueue(decoder.decode())
      },
    }),
  )
}

const mapAnalysisResultsToMessageMetadata = (analysis: unknown) => {
  if (!isRecord(analysis)) return undefined

  const ingestion = asRecord(analysis['ingestion_metadata']) ?? asRecord(analysis['metadata']) ?? {}
  const system = asRecord(analysis['system_metadata']) ?? {}

  const version =
    getString(system, 'app_version') ??
    getString(system, 'version') ??
    getString(analysis, 'version') ??
    null

  const platform =
    getString(system, 'platform') ??
    getString(analysis, 'platform') ??
    null

  const databaseSize =
    getNumber(system, 'database_size') ??
    getNumber(analysis, 'database_size') ??
    null

  const accountCount =
    getNumber(system, 'account_count') ??
    getNumber(ingestion, 'account_count') ??
    null

  const accountsWithErrors = getNumber(system, 'accounts_with_errors') ?? null

  const totalEntries =
    getNumber(ingestion, 'line_count') ??
    getNumber(system, 'total_entries') ??
    null

  const errorCount =
    getNumber(ingestion, 'error_count') ??
    getNumber(system, 'error_count') ??
    null

  const warningCount =
    getNumber(ingestion, 'warning_count') ??
    getNumber(system, 'warning_count') ??
    null

  const timeRange =
    getString(ingestion, 'time_range') ??
    getString(system, 'time_range') ??
    null

  const performanceMetrics = asRecord(system['performance_metrics']) ?? asRecord(analysis['performance_metrics']) ?? null

  const healthStatus = getString(analysis, 'health_status') ?? getString(system, 'health_status') ?? null

  const confidenceLevel =
    getNumber(analysis, 'confidence_level') ??
    getNumber(system, 'confidence_level') ??
    undefined

  const logMetadata = {
    version,
    platform,
    // Only map true database size if provided by the backend; do not substitute file size here
    database_size: databaseSize,
    account_count: accountCount,
    accounts_with_errors: accountsWithErrors,
    total_entries: totalEntries,
    error_count: errorCount,
    warning_count: warningCount,
    time_range: timeRange,
    performance_metrics: performanceMetrics,
    health_status: healthStatus,
    confidence_level: confidenceLevel,
  }

  const issuesSource = getArray(analysis['identified_issues']) ?? getArray(analysis['issues']) ?? []
  const issueRecords = issuesSource.filter(isRecord)

  const errorSnippets = issueRecords.length
    ? issueRecords.map(issue => {
        const severityRaw = getString(issue, 'severity') ?? ''
        const normalizedSeverity = severityRaw.toLowerCase()
        const level = normalizedSeverity === 'critical'
          ? 'CRITICAL'
          : normalizedSeverity === 'high'
            ? 'ERROR'
            : 'WARNING'

        const timestamp =
          getString(issue, 'timestamp') ??
          getString(issue, 'first_seen') ??
          undefined
        const message =
          getString(issue, 'description') ??
          getString(issue, 'title') ??
          ''
        const context =
          getString(issue, 'details') ??
          getString(issue, 'recommendation') ??
          undefined
        const stackTrace = getString(issue, 'stack_trace') ?? undefined

        return {
          timestamp,
          level,
          message,
          context,
          stackTrace,
        }
      })
    : undefined

  const priorityConcerns = getArray(analysis['priority_concerns'])
  const firstConcern = priorityConcerns?.find(item => typeof item === 'string') as string | undefined
  const overallSummary = getString(analysis, 'overall_summary') ?? undefined

  const rootCauseSummary = firstConcern ?? overallSummary

  const rootCause = rootCauseSummary
    ? {
        summary: rootCauseSummary,
        confidence: confidenceLevel,
        category: getString(analysis, 'analysis_method') ?? 'log_analysis',
      }
    : undefined

  return {
    logMetadata,
    ...(errorSnippets ? { errorSnippets } : {}),
    ...(rootCause ? { rootCause } : {}),
    analysisResults: analysis,
  }
}

const createUnifiedResponseStream = (
  stream: ReadableStream<Uint8Array<ArrayBufferLike>>,
): ReadableStream<UIMessageChunk> => {
  const messageId = generateStreamId()
  let started = false
  let finished = false

  return toTextStream(stream)
    .pipeThrough(new EventSourceParserStream())
    .pipeThrough(
      new TransformStream<{ data: string | undefined }, UIMessageChunk>({
        transform(chunk, controller) {
          const { data } = chunk
          if (!data) return

          if (data === '[DONE]') {
            if (started && !finished) {
              controller.enqueue({ type: 'text-end', id: messageId } as UIMessageChunk)
              finished = true
            }
            return
          }

          let payload: any
          try {
            payload = JSON.parse(data)
          } catch (error) {
            console.warn('[UnifiedChatTransport] Unable to parse SSE chunk', error)
            return
          }

          // Map generic step/result events (Stage-2 for log analysis)
          const payloadType = typeof payload?.type === 'string' ? payload.type : undefined;

          if (payloadType && (payloadType === 'reasoning' || payloadType.startsWith('reasoning-'))) {
            const dataChunk = {
              type: `data-${payloadType}` as UIMessageChunk['type'],
              data: { type: payloadType, data: payload },
            } as UIMessageChunk
            controller.enqueue(dataChunk)
            return;
          }

          if (payloadType === 'step' && payload?.data) {
            if (!started) {
              started = true
              controller.enqueue({ type: 'text-start', id: messageId } as UIMessageChunk)
            }
            const dataChunk = {
              type: 'data-timeline-step' as UIMessageChunk['type'],
              data: payload.data,
            } as UIMessageChunk
            controller.enqueue(dataChunk)
            return
          }

          if (payload?.type === 'result' && payload?.data?.analysis) {
            const mapped = mapAnalysisResultsToMessageMetadata(payload.data.analysis)
            controller.enqueue({
              type: 'message-metadata',
              messageMetadata: mapped ?? payload.data.analysis,
            } as UIMessageChunk)
            return
          }

          if (payload === 'done' || payload?.type === 'done') {
            if (started && !finished) {
              controller.enqueue({ type: 'text-end', id: messageId } as UIMessageChunk)
              finished = true
            }
            return
          }

          if (payload?.role === 'error') {
            const errorText = typeof payload?.content === 'string'
              ? payload.content
              : 'Log analysis failed while processing the stream.'
            controller.enqueue({ type: 'error', errorText } as UIMessageChunk)
            finished = true
            return
          }

          if (payload?.role !== 'assistant') {
            // Ignore router/system notifications for now; UI focuses on final response
            return
          }

          if (!started) {
            started = true
            controller.enqueue({ type: 'text-start', id: messageId } as UIMessageChunk)
          }

          const delta = typeof payload.content === 'string' ? payload.content : ''
          if (delta) {
            controller.enqueue({ type: 'text-delta', id: messageId, delta } as UIMessageChunk)
          }

          if (payload.analysis_results) {
            const mappedMetadata = mapAnalysisResultsToMessageMetadata(payload.analysis_results)
            controller.enqueue({
              type: 'message-metadata',
              messageMetadata: mappedMetadata ?? payload.analysis_results,
            } as UIMessageChunk)
          }
        },
        flush(controller) {
          if (started && !finished) {
            controller.enqueue({ type: 'text-end', id: messageId } as UIMessageChunk)
          }
        },
      }),
    )
}

class UnifiedAwareTransport<UI_MESSAGE extends UIMessage> extends DefaultChatTransport<UI_MESSAGE> {
  private useUnifiedStream = false

  setUseUnifiedStream(value: boolean) {
    this.useUnifiedStream = value
  }

  protected processResponseStream(
    stream: ReadableStream<Uint8Array<ArrayBufferLike>>,
  ): ReadableStream<UIMessageChunk> {
    if (this.useUnifiedStream) {
      return filterUIMessageStream(createUnifiedResponseStream(stream))
    }

    return filterUIMessageStream(super.processResponseStream(stream))
  }
}

export function createBackendChatTransport({
  provider,
  model,
  sessionId,
  getAuthToken,
  endpoint,
}: UnifiedTransportOptions) {
  const apiBaseUrl = getApiBaseUrl()
  const chatEndpoint = endpoint ?? (apiBaseUrl ? `${apiBaseUrl}/v2/agent/chat/stream` : '/api/v1/v2/agent/chat/stream')
  const unifiedEndpoint = apiBaseUrl ? `${apiBaseUrl}/agent/unified/stream` : '/api/v1/agent/unified/stream'

  const headersResolvable: () => Promise<Record<string, string>> = async () => {
    const headers: Record<string, string> = {}
    const token = (await getAuthToken?.()) ?? null
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    return headers
  }

  const baseBody = () => ({ provider, model, session_id: sessionId })

  const transport = new UnifiedAwareTransport<UIMessage>({
    api: chatEndpoint,
    credentials: 'include',
    headers: headersResolvable,
    body: baseBody,
    prepareSendMessagesRequest: async ({
      messages,
      body,
      headers,
      credentials,
      api,
    }) => {
      const conversation = buildHistory(messages)
      const lastUserIndex = [...conversation].reverse().findIndex(msg => msg.role === 'user')
      const absoluteIndex = lastUserIndex === -1 ? -1 : conversation.length - 1 - lastUserIndex

      const currentMessage = absoluteIndex >= 0 ? conversation[absoluteIndex].content : ''
      const history = absoluteIndex >= 0 ? conversation.slice(0, absoluteIndex) : conversation

      const resolvedBody = (await resolve(body)) as Record<string, unknown> | undefined
      const resolvedHeaders = (await resolve(headers)) as Record<string, string> | undefined

      // Extract log-specific data from body
      const dataPayload = (resolvedBody?.data as Record<string, any>) ?? {}
      const isLogAnalysis = Boolean(dataPayload.isLogAnalysis && dataPayload.attachedLogText)
      const attachedLogText = dataPayload.attachedLogText
      const logMetadata = dataPayload.logMetadata
      // Web search flags (manual pill)
      const forceWebSearch = Boolean(dataPayload.forceWebSearch)
      const webSearchMaxResults = getNumber(dataPayload, 'webSearchMaxResults')
      const webSearchProfile = getString(dataPayload, 'webSearchProfile')

      const targetEndpoint = isLogAnalysis ? unifiedEndpoint : chatEndpoint

      transport.setUseUnifiedStream(isLogAnalysis)

      return {
        api: targetEndpoint,
        credentials,
        headers: resolvedHeaders,
        body: {
          message: currentMessage,
          messages: history,
          provider: (resolvedBody?.provider as string | undefined) ?? provider,
          model: (resolvedBody?.model as string | undefined) ?? model,
          session_id: (resolvedBody?.session_id as string | undefined) ?? sessionId,
          ...(isLogAnalysis ? {
            agent_type: 'log_analysis',
            log_content: attachedLogText,
            log_metadata: logMetadata,
            trace_id: (resolvedBody?.session_id as string | undefined) ?? sessionId,
          } : {}),
          ...(forceWebSearch ? { force_websearch: true } : {}),
          ...(webSearchMaxResults ? { websearch_max_results: webSearchMaxResults } : {}),
          ...(webSearchProfile ? { websearch_profile: webSearchProfile } : {}),
          ...(dataPayload.useServerMemory ? { use_server_memory: true } : {}),
        },
      }
    },
  })

  return transport as any
}
