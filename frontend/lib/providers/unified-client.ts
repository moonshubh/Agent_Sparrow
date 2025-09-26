import type { UIMessage } from 'ai'
import { resolve } from '@ai-sdk/provider-utils'
import { getApiBaseUrl } from '@/lib/utils/environment'
import { FilteringChatTransport } from '@/lib/providers/filtering-transport'
import { DefaultChatTransport } from 'ai'

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

export function createBackendChatTransport({
  provider,
  model,
  sessionId,
  getAuthToken,
  endpoint,
}: UnifiedTransportOptions) {
  const apiBaseUrl = getApiBaseUrl()
  const resolvedEndpoint = endpoint ?? (apiBaseUrl ? `${apiBaseUrl}/v2/agent/chat/stream` : '/api/v1/v2/agent/chat/stream')

  const headersResolvable = async () => {
    const token = (await getAuthToken?.()) ?? null
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  const baseBody = () => ({ provider, model, session_id: sessionId })

  const enableClientFilter = process.env.NEXT_PUBLIC_CLIENT_FILTER === 'true'

  const TransportCtor = enableClientFilter ? FilteringChatTransport<UIMessage> : DefaultChatTransport<UIMessage>

  return new (TransportCtor as any)({
    api: resolvedEndpoint,
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

      return {
        api: api ?? resolvedEndpoint,
        credentials,
        headers: resolvedHeaders,
        body: {
          message: currentMessage,
          messages: history,
          provider: (resolvedBody?.provider as string | undefined) ?? provider,
          model: (resolvedBody?.model as string | undefined) ?? model,
          session_id: (resolvedBody?.session_id as string | undefined) ?? sessionId,
        },
      }
    },
  })
}
