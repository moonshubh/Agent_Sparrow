import { EventSourceParserStream } from 'eventsource-parser/stream'

import { supabase } from '@/services/supabase'
import { getAuthToken as getLocalToken } from '@/services/auth/local-auth'
import { ChatMessage } from '@/shared/types/chat'

// URL validation with proper error handling
const validateApiBaseUrl = (url: string): string => {
  try {
    const parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      throw new Error('API base URL must use HTTP or HTTPS protocol')
    }
    return url
  } catch (error) {
    throw new Error(`Invalid API base URL: ${error instanceof Error ? error.message : 'Unknown error'}`)
  }
}

const API_BASE_URL = validateApiBaseUrl(
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
)

// TypeScript interfaces for better type safety
interface User {
  id: string
  email: string
  full_name?: string
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface ApiKey {
  id: string
  api_key_type: string
  key_name?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

interface ApiKeyListResponse {
  api_keys: ApiKey[]
  total_count: number
}

interface ApiKeyStatus {
  total_keys: number
  active_keys: number
  inactive_keys: number
  key_types: string[]
}

type JsonRecord = Record<string, unknown>

const isRecord = (value: unknown): value is JsonRecord => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)

const isBodyInit = (value: unknown): value is BodyInit => (
  typeof value === 'string' ||
  value instanceof Blob ||
  value instanceof FormData ||
  value instanceof URLSearchParams ||
  value instanceof ArrayBuffer ||
  ArrayBuffer.isView(value as ArrayBufferView)
)

const parseBody = (rawBody: string, contentType: string | null): unknown => {
  if (!rawBody) {
    return null
  }

  if (contentType?.includes('application/json')) {
    try {
      return JSON.parse(rawBody)
    } catch {
      return rawBody
    }
  }

  if (contentType?.includes('text/')) {
    return rawBody
  }

  return rawBody
}

const extractErrorDetail = (body: unknown): string | null => {
  if (!body) {
    return null
  }

  if (typeof body === 'string') {
    return body
  }

  if (isRecord(body)) {
    const { detail, message } = body

    if (typeof detail === 'string') {
      return detail
    }

    if (typeof message === 'string') {
      return message
    }

    if (isRecord(detail) || Array.isArray(detail)) {
      try {
        return JSON.stringify(detail)
      } catch {
        return null
      }
    }
  }

  return null
}

const serializeBody = (data: unknown): BodyInit | undefined => {
  if (data === null || data === undefined) {
    return undefined
  }

  if (isBodyInit(data)) {
    return data
  }

  return JSON.stringify(data)
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

export class APIRequestError extends Error {
  public readonly status: number
  public readonly statusText: string
  public readonly body: unknown

  constructor(params: { status: number; statusText: string; body: unknown; message?: string }) {
    const statusLine = `${params.status} ${params.statusText || ''}`.trim()
    const defaultMessage = `HTTP error: ${statusLine}`
    super(params.message ?? defaultMessage)
    this.name = 'APIRequestError'
    this.status = params.status
    this.statusText = params.statusText
    this.body = params.body
  }
}

interface RequestOptions extends RequestInit {
  skipAuth?: boolean
  customContentType?: string
}

interface StreamOptions extends RequestOptions {
  onError?: (error: Error) => void
  onClose?: () => void
}

// Enhanced EventSource interface for better typing
export interface EnhancedEventSource {
  close: () => void
  readyState: 0 | 1 | 2 // CONNECTING | OPEN | CLOSED
  addEventListener?: (type: string, listener: EventListener) => void
  removeEventListener?: (type: string, listener: EventListener) => void
}

class APIClient {
  private streamTokenUnavailable = false

  private async getAuthHeaders(customContentType?: string): Promise<HeadersInit> {
    try {
      const session = await supabase.auth.getSession()
      const supaToken = session.data.session?.access_token
      const localBypass = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true'
      const localToken = localBypass && typeof window !== 'undefined' ? getLocalToken() : null
      const token = supaToken || localToken || undefined

      return {
        'Content-Type': customContentType || 'application/json',
        ...(token && { Authorization: `Bearer ${token}` })
      }
    } catch (error) {
      console.error('Failed to retrieve session:', error)
      return {
        'Content-Type': customContentType || 'application/json'
      }
    }
  }

  async request<T = unknown>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { skipAuth = false, customContentType, headers, ...restOptions } = options

    const authHeaders = skipAuth ? undefined : await this.getAuthHeaders(customContentType)
    const requestHeaders = new Headers()

    if (authHeaders) {
      new Headers(authHeaders).forEach((value, key) => requestHeaders.set(key, value))
    }

    if (headers) {
      new Headers(headers).forEach((value, key) => requestHeaders.set(key, value))
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...restOptions,
      headers: requestHeaders
    })

    const contentType = response.headers.get('content-type')

    if (!response.ok) {
      const rawBody = await response.text()
      const parsedBody = parseBody(rawBody, contentType)
      const statusLine = `${response.status} ${response.statusText || ''}`.trim()
      const detail = extractErrorDetail(parsedBody)
      const message = detail ? `${statusLine} - ${detail}` : statusLine

      throw new APIRequestError({
        status: response.status,
        statusText: response.statusText ?? '',
        body: parsedBody,
        message: `HTTP error: ${message}`
      })
    }

    if (!contentType || response.status === 204) {
      return undefined as T
    }

    if (contentType.includes('application/json')) {
      return (await response.json()) as T
    }

    if (contentType.includes('text/plain') || contentType.includes('text/html')) {
      return (await response.text()) as unknown as T
    }

    return (await response.arrayBuffer()) as unknown as T
  }

  // Convenience methods with explicit return types
  async get<T = unknown>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  async post<TResponse = unknown, TPayload = unknown>(
    endpoint: string,
    data?: TPayload,
    options?: RequestOptions
  ): Promise<TResponse> {
    return this.request<TResponse>(endpoint, {
      ...options,
      method: 'POST',
      body: serializeBody(data)
    })
  }

  async put<TResponse = unknown, TPayload = unknown>(
    endpoint: string,
    data?: TPayload,
    options?: RequestOptions
  ): Promise<TResponse> {
    return this.request<TResponse>(endpoint, {
      ...options,
      method: 'PUT',
      body: serializeBody(data)
    })
  }

  async delete<T = unknown>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }

  // Secure token exchange endpoint for SSE
  private async getStreamToken(): Promise<string | null> {
    // In-memory short-circuit
    if (this.streamTokenUnavailable) {
      return null
    }

    // Persisted flag (survives HMR / reloads in dev)
    try {
      if (typeof window !== 'undefined') {
        const cached = window.sessionStorage.getItem('streamTokenUnavailable')
          || window.localStorage.getItem('streamTokenUnavailable')
        if (cached === '1') {
          this.streamTokenUnavailable = true
          return null
        }
      }
    } catch {
      // ignore storage access errors
    }

    try {
      const response = await this.post<{ stream_token: string }>(
        '/api/v1/auth/stream-token',
        {},
        { skipAuth: false }
      )
      return response.stream_token
    } catch (error) {
      if (error instanceof APIRequestError && error.status === 404) {
        this.streamTokenUnavailable = true
        try {
          if (typeof window !== 'undefined') {
            window.sessionStorage.setItem('streamTokenUnavailable', '1')
            window.localStorage.setItem('streamTokenUnavailable', '1')
          }
        } catch {}
        if (process.env.NODE_ENV === 'development') {
          // One-time notice; subsequent calls are short-circuited
          // eslint-disable-next-line no-console
          console.debug('Stream token endpoint unavailable (404); falling back to session auth.')
        }
      } else if (process.env.NODE_ENV === 'development') {
        // eslint-disable-next-line no-console
        console.debug('Failed to get stream token, using session auth fallback:', error)
      }
      return null
    }
  }

  // Enhanced secure streaming endpoint for SSE
  async stream<TMessage = unknown>(
    endpoint: string,
    data?: Record<string, unknown>,
    onMessage?: (data: TMessage) => void,
    options?: StreamOptions
  ): Promise<EnhancedEventSource> {
    const { onError, onClose, skipAuth = false, customContentType, ...restOptions } = options || {}
    
    // Get secure stream token instead of exposing auth token in URL
    const streamToken = skipAuth ? null : await this.getStreamToken()
    const authHeaders = skipAuth ? undefined : await this.getAuthHeaders(customContentType)

    const headers = new Headers()
    if (authHeaders) {
      new Headers(authHeaders).forEach((value, key) => headers.set(key, value))
    }
    if (restOptions.headers) {
      new Headers(restOptions.headers).forEach((value, key) => headers.set(key, value))
    }

    // If we have data, we need to use POST with fetch streaming
    if (data) {
      let reader: ReadableStreamDefaultReader<{ data: string | undefined; event?: string }> | null = null
      let isClosed = false

      const stopReader = () => {
        reader?.cancel().catch(() => undefined)
      }

      try {
        const requestBody: Record<string, unknown> = { ...data }
        if (streamToken) {
          requestBody._stream_token = streamToken
        }

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
          method: 'POST',
          headers,
          body: JSON.stringify(requestBody),
        })

        if (!response.ok) {
          const rawBody = await response.text().catch(() => '')
          const parsedBody = parseBody(rawBody, response.headers.get('content-type'))
          const statusLine = `${response.status} ${response.statusText || ''}`.trim()
          const detail = extractErrorDetail(parsedBody)
          const message = detail ? `${statusLine} - ${detail}` : statusLine
          throw new APIRequestError({
            status: response.status,
            statusText: response.statusText ?? '',
            body: parsedBody,
            message: `HTTP error: ${message}`,
          })
        }

        const body = response.body
        if (!body) {
          throw new Error('No response body available')
        }

        const eventStream = toTextStream(body as ReadableStream<Uint8Array>).pipeThrough(new EventSourceParserStream())
        reader = eventStream.getReader()

        const enhancedEventSource: EnhancedEventSource = {
          close: () => {
            if (!isClosed) {
              isClosed = true
              enhancedEventSource.readyState = 2
              stopReader()
              onClose?.()
            }
          },
          readyState: 1,
        }

        const processStream = async (): Promise<void> => {
          try {
            while (!isClosed && reader) {
              const { value, done } = await reader.read()
              if (done) {
                enhancedEventSource.close()
                break
              }

              if (!value || typeof value.data !== 'string') {
                continue
              }

              const payload = value.data
              if (payload === '[DONE]') {
                enhancedEventSource.close()
                break
              }

              try {
                const parsed = JSON.parse(payload) as TMessage
                onMessage?.(parsed)
              } catch (parseError) {
                const errorMessage = parseError instanceof Error ? parseError.message : 'Unknown parse error'
                onError?.(new Error(`Failed to parse SSE data: ${errorMessage}`))
              }
            }
          } catch (streamError) {
            if (!isClosed) {
              const errorMessage = streamError instanceof Error ? streamError.message : 'Stream processing failed'
              onError?.(new Error(`Stream processing failed: ${errorMessage}`))
              enhancedEventSource.close()
            }
          }
        }

        processStream().catch((error) => {
          if (!isClosed) {
            const errorMessage = error instanceof Error ? error.message : 'Unhandled stream error'
            onError?.(new Error(`Unhandled stream error: ${errorMessage}`))
            enhancedEventSource.close()
          }
        })

        return enhancedEventSource
      } catch (error) {
        stopReader()
        throw error instanceof Error ? error : new Error('Stream initialization failed')
      }
    }

    // For GET requests, use standard EventSource with secure token handling
    let eventSource: EventSource
    let isClosed = false
    
    try {
      const url = new URL(`${API_BASE_URL}${endpoint}`)
      
      // Use secure token if available, otherwise rely on session-based auth on server
      if (streamToken) {
        url.searchParams.append('stream_token', streamToken)
      }

      eventSource = new EventSource(url.toString())

      const enhancedEventSource: EnhancedEventSource = {
        close: () => {
          if (!isClosed) {
            isClosed = true
            eventSource.close()
            enhancedEventSource.readyState = 2
            onClose?.()
          }
        },
        readyState: eventSource.readyState as 0 | 1 | 2
      }

      if (onMessage) {
        eventSource.onmessage = (event) => {
          if (event.data === '[DONE]') {
            enhancedEventSource.close()
            return
          }
          
          try {
            const parsed = JSON.parse(event.data) as TMessage
            onMessage(parsed)
          } catch (e) {
            const message = e instanceof Error ? e.message : 'Failed to parse SSE payload'
            onError?.(new Error(`Failed to parse SSE data: ${message}`))
          }
        }
      }

      eventSource.onerror = () => {
        if (!isClosed) {
          const streamError = new Error('EventSource connection error')
          onError?.(streamError)
          enhancedEventSource.close()
        }
      }

      eventSource.onopen = () => {
        enhancedEventSource.readyState = 1 // OPEN
      }

      return enhancedEventSource
    } catch (error) {
      throw error instanceof Error ? error : new Error('EventSource initialization failed')
    }
  }
}

export const apiClient = new APIClient()

// Export specific API functions with proper typing
export const authAPI = {
  signOut: (): Promise<void> => apiClient.post('/api/v1/auth/signout'),

  getMe: (): Promise<User> => apiClient.get<User>('/api/v1/auth/me'),

  updateProfile: (data: { full_name?: string; metadata?: Record<string, unknown> }): Promise<User> =>
    apiClient.put<User>('/api/v1/auth/me', data)
}

export const apiKeyAPI = {
  list: (): Promise<ApiKeyListResponse> => apiClient.get<ApiKeyListResponse>('/api/v1/api-keys/'),

  create: (data: { api_key_type: string; api_key: string; key_name?: string }): Promise<ApiKey> =>
    apiClient.post<ApiKey>('/api/v1/api-keys/', data),

  delete: (apiKeyType: string): Promise<void> =>
    apiClient.delete<void>(`/api/v1/api-keys/${apiKeyType}`),

  getStatus: (): Promise<ApiKeyStatus> => apiClient.get<ApiKeyStatus>('/api/v1/api-keys/status')
}

export const agentAPI = {
  /**
   * Sends a chat message to the agent API with streaming response
   * @param message - The message to send to the agent
   * @param onMessage - Callback function for handling streaming messages
   * @param onError - Optional callback for handling errors
   * @param onClose - Optional callback when the stream closes
   * @param messages - Optional array of previous message objects in the conversation history
   * @param sessionId - Optional string representing the session identifier for maintaining context
   * @returns Promise resolving to an EnhancedEventSource for managing the stream
   */
  chat: <TMessage = unknown>(
    message: string, 
    onMessage: (data: TMessage) => void,
    onError?: (error: Error) => void,
    onClose?: () => void,
    messages?: ChatMessage[],
    sessionId?: string
  ): Promise<EnhancedEventSource> =>
    apiClient.stream<TMessage>(
      '/api/v1/v2/agent/chat/stream',
      { message, messages, session_id: sessionId },
      onMessage,
      { onError, onClose }
    ),

  analyzeLogs: (content: string): Promise<unknown> =>
    apiClient.post('/api/v1/agent/logs', { content }),

  research: (query: string): Promise<unknown> =>
    apiClient.post('/api/v1/agent/research', { query })
}
