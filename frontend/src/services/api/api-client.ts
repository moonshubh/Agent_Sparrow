import { supabase } from '@/services/supabase'
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
  private async getAuthHeaders(customContentType?: string): Promise<HeadersInit> {
    try {
      const session = await supabase.auth.getSession()
      const token = session.data.session?.access_token

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
    try {
      const response = await this.post<{ stream_token: string }>(
        '/api/v1/auth/stream-token',
        {},
        { skipAuth: false }
      )
      return response.stream_token
    } catch (error) {
      console.warn('Failed to get stream token, falling back to session auth:', error)
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
      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
      let isClosed = false
      
      try {
        const requestBody: Record<string, unknown> = { ...data }
        if (streamToken) {
          requestBody._stream_token = streamToken
        }

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
          method: 'POST',
          headers,
          body: JSON.stringify(requestBody)
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
            message: `HTTP error: ${message}`
          })
        }

        reader = response.body?.getReader() ?? null
        if (!reader) {
          throw new Error('No response body available')
        }

        const streamReader = reader

        // Enhanced EventSource simulation with proper state management
        const eventSource: EnhancedEventSource = {
          close: () => {
            if (!isClosed) {
              isClosed = true
              reader?.cancel().catch(console.error)
              onClose?.()
            }
          },
          readyState: 1 // OPEN
        }

        // Enhanced stream processing with better error handling
        const decoder = new TextDecoder()
        let buffer = ''

        const processStream = async (): Promise<void> => {
          try {
            while (!isClosed) {
              try {
                const { done, value } = await streamReader.read()
                if (done) {
                  eventSource.readyState = 2 // CLOSED
                  onClose?.()
                  break
                }

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() || '' // Keep incomplete line in buffer

                for (const line of lines) {
                  if (!line.trim()) continue
                  
                  // Enhanced SSE parsing supporting multiple event types
                  if (line.startsWith('data: ')) {
                    const data = line.slice(6)
                    if (data === '[DONE]') {
                      eventSource.readyState = 2 // CLOSED
                      onClose?.()
                      return
                    }
                    
                    try {
                      const parsed = JSON.parse(data) as TMessage
                      onMessage?.(parsed)
                    } catch (parseError) {
                      const errorMessage = parseError instanceof Error ? parseError.message : 'Unknown parse error'
                      console.error('Error parsing SSE data:', errorMessage, 'Raw data:', data)
                      onError?.(new Error(`Failed to parse SSE data: ${errorMessage}`))
                    }
                  } else if (line.startsWith('event: ')) {
                    // Support for event types beyond 'data'
                    const eventType = line.slice(7)
                    console.log('SSE event type:', eventType)
                  } else if (line.startsWith('id: ')) {
                    // Support for event IDs
                    const eventId = line.slice(4)
                    console.log('SSE event ID:', eventId)
                  } else if (line.startsWith('retry: ')) {
                    // Support for retry intervals
                    const retryMs = parseInt(line.slice(7), 10)
                    console.log('SSE retry interval:', retryMs)
                  }
                }
              } catch (readError) {
                // Handle specific read errors
                if (!isClosed) {
                  const errorMessage = readError instanceof Error ? readError.message : 'Stream read failed'
                  console.error('Stream read error:', errorMessage)
                  
                  // Only close and error if it's not a normal stream end
                  if (!errorMessage.includes('aborted') && !errorMessage.includes('cancelled')) {
                    eventSource.readyState = 2 // CLOSED
                    onError?.(new Error(`Stream read failed: ${errorMessage}`))
                    eventSource.close()
                    break
                  }
                }
              }
            }
          } catch (streamError) {
            // Handle overall stream processing errors
            if (!isClosed) {
              eventSource.readyState = 2 // CLOSED
              const errorMessage = streamError instanceof Error ? streamError.message : 'Stream processing failed'
              console.error('Stream processing error:', errorMessage)
              onError?.(new Error(`Stream processing failed: ${errorMessage}`))
              eventSource.close()
            }
          }
        }

        // Start stream processing with unified error handling (non-blocking)
        processStream().catch((error) => {
          try {
            if (!isClosed) {
              const errorMessage = error instanceof Error ? error.message : 'Unhandled stream error'
              console.error('Unhandled stream error:', errorMessage)
              onError?.(new Error(`Unhandled stream error: ${errorMessage}`))
              eventSource.close()
            }
          } catch (handlerError) {
            // Final fallback for error handler failures
            console.error('Error in stream error handler:', handlerError)
          }
        })
        
        return eventSource
      } catch (error) {
        // Ensure proper cleanup on initialization error
        if (reader) {
          try {
            await reader.cancel()
          } catch (cancelError) {
            console.error('Error canceling reader:', cancelError)
          }
        }
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
            console.error('Error parsing SSE data:', e, 'Raw data:', event.data)
            onError?.(new Error(`Failed to parse SSE data: ${e}`))
          }
        }
      }

      eventSource.onerror = (error) => {
        if (!isClosed) {
          console.error('EventSource error:', error)
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
