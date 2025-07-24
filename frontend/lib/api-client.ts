import { supabase } from './supabase'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface RequestOptions extends RequestInit {
  skipAuth?: boolean
}

class APIClient {
  private async getAuthHeaders(): Promise<HeadersInit> {
    const session = await supabase.auth.getSession()
    const token = session.data.session?.access_token

    return {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` })
    }
  }

  async request<T = any>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { skipAuth = false, headers = {}, ...restOptions } = options

    const authHeaders = skipAuth ? {} : await this.getAuthHeaders()

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

    // Handle empty responses
    const contentType = response.headers.get('content-type')
    if (!contentType || !contentType.includes('application/json')) {
      return {} as T
    }

    return response.json()
  }

  // Convenience methods
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

  // Stream endpoint for SSE
  async stream(
    endpoint: string,
    data?: any,
    onMessage?: (data: any) => void,
    options?: RequestOptions
  ): Promise<EventSource> {
    const authHeaders = options?.skipAuth ? {} : await this.getAuthHeaders()
    const headers = new Headers({
      ...authHeaders,
      ...options?.headers
    })

    // For EventSource, we need to pass auth token as query parameter
    const token = headers.get('Authorization')?.replace('Bearer ', '')
    const url = new URL(`${API_BASE_URL}${endpoint}`)
    if (token) {
      url.searchParams.append('token', token)
    }

    // If we have data, we need to use POST with EventSource
    if (data) {
      // Since EventSource doesn't support POST directly, we'll use fetch for streaming
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(data)
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      // Simulate EventSource interface
      const eventSource = {
        close: () => reader.cancel(),
        readyState: 1 // OPEN
      } as EventSource

      // Read the stream
      const decoder = new TextDecoder()
      const processStream = async () => {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6)
              if (data === '[DONE]') continue
              
              try {
                const parsed = JSON.parse(data)
                onMessage?.(parsed)
              } catch (e) {
                console.error('Error parsing SSE data:', e)
              }
            }
          }
        }
      }

      processStream().catch(console.error)
      return eventSource
    }

    // For GET requests, use standard EventSource
    const eventSource = new EventSource(url.toString())

    if (onMessage) {
      eventSource.onmessage = (event) => {
        if (event.data === '[DONE]') return
        
        try {
          const parsed = JSON.parse(event.data)
          onMessage(parsed)
        } catch (e) {
          console.error('Error parsing SSE data:', e)
        }
      }
    }

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error)
      eventSource.close()
    }

    return eventSource
  }
}

export const apiClient = new APIClient()

// Export specific API functions
export const authAPI = {
  signOut: () => apiClient.post('/api/v1/auth/signout'),

  getMe: () => apiClient.get('/api/v1/auth/me'),

  updateProfile: (data: { full_name?: string; metadata?: any }) =>
    apiClient.put('/api/v1/auth/me', data)
}

export const apiKeyAPI = {
  list: () => apiClient.get('/api/v1/api-keys/'),

  create: (data: { api_key_type: string; api_key: string; key_name?: string }) =>
    apiClient.post('/api/v1/api-keys/', data),

  delete: (apiKeyType: string) =>
    apiClient.delete(`/api/v1/api-keys/${apiKeyType}`),

  getStatus: () => apiClient.get('/api/v1/api-keys/status')
}

export const agentAPI = {
  chat: (message: string, onMessage: (data: any) => void) =>
    apiClient.stream('/api/v1/v2/agent/chat/stream', { message }, onMessage),

  analyzeLogs: (content: string) =>
    apiClient.post('/api/v1/agent/logs', { content }),

  research: (query: string) =>
    apiClient.post('/api/v1/agent/research', { query })
}