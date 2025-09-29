import type { UIMessage, UIMessageChunk } from 'ai'
import { DefaultChatTransport } from 'ai'
import { resolve } from '@ai-sdk/provider-utils'
import { EventSourceParserStream } from 'eventsource-parser/stream'

import { filterUIMessageStream } from '@/lib/providers/filtering-transport'
import { getApiBaseUrl } from '@/lib/utils/environment'

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

const mapAnalysisResultsToMessageMetadata = (analysis: any) => {
  if (!analysis || typeof analysis !== 'object') return undefined

  const ingestion = analysis.ingestion_metadata ?? analysis.metadata ?? {}
  const system = analysis.system_metadata ?? {}

  const logMetadata = {
    version: system.app_version ?? system.version ?? analysis.version ?? null,
    platform: system.platform ?? analysis.platform ?? null,
    // Only map true database size if provided by the backend; do not substitute file size here
    database_size: system.database_size ?? analysis.database_size ?? null,
    account_count: system.account_count ?? ingestion.account_count ?? null,
    accounts_with_errors: system.accounts_with_errors ?? null,
    total_entries: ingestion.line_count ?? system.total_entries ?? null,
    error_count: ingestion.error_count ?? system.error_count ?? null,
    warning_count: ingestion.warning_count ?? system.warning_count ?? null,
    time_range: ingestion.time_range ?? system.time_range ?? null,
    performance_metrics: system.performance_metrics ?? analysis.performance_metrics ?? null,
    health_status: analysis.health_status ?? system.health_status ?? null,
    confidence_level: analysis.confidence_level ?? undefined,
  }

  const issues = Array.isArray(analysis.identified_issues)
    ? analysis.identified_issues
    : Array.isArray(analysis.issues)
      ? analysis.issues
      : []

  const errorSnippets = issues.length > 0
    ? issues.map((issue: any) => {
        const sevRaw = (issue?.severity ?? '').toString().toLowerCase()
        const level = sevRaw === 'critical' ? 'CRITICAL' : sevRaw === 'high' ? 'ERROR' : 'WARNING'
        return {
          timestamp: issue?.timestamp ?? issue?.first_seen ?? undefined,
          level,
          message: issue?.description ?? issue?.title ?? '',
          context: issue?.details ?? issue?.recommendation ?? undefined,
          stackTrace: issue?.stack_trace ?? undefined,
        }
      })
    : undefined

  const rootCauseSummary = Array.isArray(analysis.priority_concerns) && analysis.priority_concerns.length > 0
    ? analysis.priority_concerns[0]
    : analysis.overall_summary

  const rootCause = rootCauseSummary
    ? {
        summary: rootCauseSummary,
        confidence: analysis.confidence_level ?? undefined,
        category: analysis.analysis_method ?? 'log_analysis',
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

  const headersResolvable = async () => {
    const token = (await getAuthToken?.()) ?? null
    return token ? { Authorization: `Bearer ${token}` } : {}
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
          ...(dataPayload.useServerMemory ? { use_server_memory: true } : {}),
        },
      }
    },
  })

  return transport as any
}
