import { supabase } from './supabase'

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
  metadata?: any
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

interface ApiKeyStatus {
  total_keys: number
  active_keys: number
  inactive_keys: number
  key_types: string[]
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
interface EnhancedEventSource {
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

  async request<T = any>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { skipAuth = false, customContentType, headers = {}, ...restOptions } = options

    const authHeaders = skipAuth ? {} : await this.getAuthHeaders(customContentType)

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...restOptions,
      headers: {
        ...authHeaders,
        ...headers
      }
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => null)
      throw new Error(
        errorData?.detail || errorData?.message || `HTTP error! status: ${response.status}`
      )
    }

    // Enhanced response type handling
    const contentType = response.headers.get('content-type')
    if (!contentType) {
      // No content type - check if response has content
      const text = await response.text()
      return (text ? text : {}) as T
    }

    if (contentType.includes('application/json')) {
      return response.json()
    } else if (contentType.includes('text/plain') || contentType.includes('text/html')) {
      return response.text() as T
    } else {
      // For other content types, return the response as-is
      const text = await response.text()
      return (text || {}) as T
    }
  }

  // Convenience methods with explicit return types
  async get<T = any>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  async post<T = any>(
    endpoint: string,
    data?: any,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined
    })
  }

  async put<T = any>(
    endpoint: string,
    data?: any,
    options?: RequestOptions
  ): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined
    })
  }

  async delete<T = any>(endpoint: string, options?: RequestOptions): Promise<T> {
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
  async stream(
    endpoint: string,
    data?: any,
    onMessage?: (data: any) => void,
    options?: StreamOptions
  ): Promise<EnhancedEventSource> {
    const { onError, onClose, skipAuth = false, customContentType, ...restOptions } = options || {}
    
    // Get secure stream token instead of exposing auth token in URL
    const streamToken = skipAuth ? null : await this.getStreamToken()
    const authHeaders = skipAuth ? {} : await this.getAuthHeaders(customContentType)
    
    const headers = new Headers({
      ...authHeaders,
      ...restOptions.headers
    })

    // If we have data, we need to use POST with fetch streaming
    if (data) {
      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
      let isClosed = false
      
      try {
        const requestBody: any = { ...data }
        if (streamToken) {
          requestBody._stream_token = streamToken
        }

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
          method: 'POST',
          headers,
          body: JSON.stringify(requestBody)
        })

        if (!response.ok) {
          const errorText = await response.text().catch(() => 'Unknown error')
          throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
        }

        reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body available')
        }

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
                const { done, value } = await reader!.read()
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
                      const parsed = JSON.parse(data)
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
            const parsed = JSON.parse(event.data)
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

  updateProfile: (data: { full_name?: string; metadata?: any }): Promise<User> =>
    apiClient.put<User>('/api/v1/auth/me', data)
}

export const apiKeyAPI = {
  list: (): Promise<ApiKey[]> => apiClient.get<ApiKey[]>('/api/v1/api-keys/'),

  create: (data: { api_key_type: string; api_key: string; key_name?: string }): Promise<ApiKey> =>
    apiClient.post<ApiKey>('/api/v1/api-keys/', data),

  delete: (apiKeyType: string): Promise<void> =>
    apiClient.delete<void>(`/api/v1/api-keys/${apiKeyType}`),

  getStatus: (): Promise<ApiKeyStatus> => apiClient.get<ApiKeyStatus>('/api/v1/api-keys/status')
}

export const agentAPI = {
  chat: (
    message: string, 
    onMessage: (data: any) => void,
    onError?: (error: Error) => void,
    onClose?: () => void
  ): Promise<EnhancedEventSource> =>
    apiClient.stream('/api/v1/v2/agent/chat/stream', { message }, onMessage, { onError, onClose }),

  analyzeLogs: (content: string): Promise<any> =>
    apiClient.post('/api/v1/agent/logs', { content }),

  research: (query: string): Promise<any> =>
    apiClient.post('/api/v1/agent/research', { query })
}