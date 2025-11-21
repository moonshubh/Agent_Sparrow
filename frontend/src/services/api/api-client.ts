import { supabase } from '@/services/supabase'
import { getAuthToken as getLocalToken } from '@/services/auth/local-auth'

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

const resolveApiBaseUrl = (): string => {
  const envUrl = process.env.NEXT_PUBLIC_API_URL

  // When running in browser on https and env is missing or points to http localhost,
  // prefer same-origin to avoid mixed-content "Failed to fetch".
  if (typeof window !== 'undefined') {
    const currentOrigin = window.location.origin
    const looksLikeLocalHttp = envUrl?.startsWith('http://localhost')
    if (!envUrl || (currentOrigin.startsWith('https://') && looksLikeLocalHttp)) {
      return currentOrigin
    }
  }

  return validateApiBaseUrl(envUrl || 'http://localhost:8000')
}

const API_BASE_URL = resolveApiBaseUrl()
const TRUSTED_FALLBACK_ORIGINS = (process.env.NEXT_PUBLIC_TRUSTED_API_ORIGINS || '')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean)

const buildRequestUrl = (endpoint: string): string => {
  try {
    // Absolute endpoints pass through unchanged
    new URL(endpoint)
    return endpoint
  } catch {
    return `${API_BASE_URL}${endpoint}`
  }
}

const toOrigin = (url?: string | null): string | null => {
  if (!url) return null
  try {
    return new URL(url).origin
  } catch {
    return null
  }
}

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

/* eslint-disable @typescript-eslint/no-explicit-any */
const toTextStream = (stream: ReadableStream<Uint8Array>): ReadableStream<string> => {
  // Using "any" here to safely access cross-environment Web Streams APIs without failing type checks
  // across differing TS lib versions. Runtime behavior is guarded by feature detection.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const g: any = globalThis as any
  if (typeof g.TextDecoderStream !== 'undefined') {
    // Casts are intentional to avoid TS ReadableWritablePair type mismatch across lib versions
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (stream as any).pipeThrough(new g.TextDecoderStream()) as ReadableStream<string>
  }

  const decoder = new TextDecoder()
  const transform = new TransformStream<Uint8Array, string>({
    transform(chunk, controller) {
      controller.enqueue(decoder.decode(chunk, { stream: true }))
    },
    flush(controller) {
      controller.enqueue(decoder.decode())
    },
  })
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (stream as any).pipeThrough(transform as any) as ReadableStream<string>
}
/* eslint-enable @typescript-eslint/no-explicit-any */

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
    } catch {
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

    const targetUrl = buildRequestUrl(endpoint)
    const sameOrigin = typeof window !== 'undefined' ? window.location.origin : null
    const apiOrigin = toOrigin(API_BASE_URL)
    const trustedOrigins = new Set<string>(
      [apiOrigin, ...TRUSTED_FALLBACK_ORIGINS].filter(Boolean) as string[]
    )
    const scrubHeadersForOrigin = (targetOrigin?: string | null) => {
      if (!targetOrigin) return requestHeaders
      const sanitized = new Headers(requestHeaders)
      if (apiOrigin && targetOrigin !== apiOrigin) {
        sanitized.delete('authorization')
      }
      return sanitized
    }

    let response: Response
    try {
      response = await fetch(targetUrl, {
        ...restOptions,
        headers: requestHeaders
      })
    } catch (err) {
      // Mixed-content or bad base URL can throw TypeError; retry relative if allowed.
      const originIsTrusted = !!(sameOrigin && trustedOrigins.has(sameOrigin))
      const shouldRetrySameOrigin =
        err instanceof TypeError &&
        originIsTrusted &&
        !endpoint.startsWith('http') &&
        sameOrigin !== API_BASE_URL
      if (shouldRetrySameOrigin) {
        const fallbackHeaders = scrubHeadersForOrigin(sameOrigin)
        response = await fetch(endpoint, {
          ...restOptions,
          headers: fallbackHeaders
        })
      } else {
        throw err
      }
    }

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

  /**
   * Generic SSE/stream helper with auth support.
   * Uses fetch + ReadableStream to support headers across environments.
   */
  async stream<T = unknown>(
    endpoint: string,
    payload?: unknown,
    onMessage?: (data: T) => void,
    options: StreamOptions = {}
  ): Promise<EnhancedEventSource> {
    const controller = new AbortController()
    try {
      const headers = await this.getAuthHeaders('application/json')
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: payload ? 'POST' : 'GET',
        headers,
        body: payload ? JSON.stringify(payload) : undefined,
        signal: controller.signal,
      })

      if (!response.ok) {
        const text = await response.text().catch(() => '')
        throw new APIRequestError({ status: response.status, statusText: response.statusText, body: text })
      }

      const body = response.body
      if (!body) {
        throw new Error('Stream response has no body')
      }

      const reader = toTextStream(body).getReader()
      const pump = async () => {
        try {
          let buffer = ''
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += value || ''
            let idx: number
            while ((idx = buffer.indexOf('\n')) >= 0) {
              const line = buffer.slice(0, idx).trim()
              buffer = buffer.slice(idx + 1)
              if (!line) continue
              const dataStr = line.startsWith('data:') ? line.slice(5).trim() : line
              try {
                onMessage?.(JSON.parse(dataStr))
              } catch {
                onMessage?.(dataStr as unknown as T)
              }
            }
          }
          options.onClose?.()
        } catch (err) {
          options.onError?.(err as Error)
        }
      }
      // Start pumping asynchronously
      void pump()

      return {
        close: () => {
          try { controller.abort() } catch {}
        },
        readyState: 1,
      }
    } catch (err) {
      options.onError?.(err as Error)
      // Return a closed stub
      return {
        close: () => { try { controller.abort() } catch {} },
        readyState: 2,
      }
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
    messages?: Array<{ role: string; content: string; [key: string]: unknown }>,
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
