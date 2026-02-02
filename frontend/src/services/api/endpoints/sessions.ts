import { apiClient } from '@/services/api/api-client'

export type AgentType = 'primary' | 'log_analysis' | 'research'

export interface ChatSession {
  id: string | number
  title?: string
  agent_type?: AgentType
  created_at?: string
  updated_at?: string
  metadata?: Record<string, unknown>
}

export interface ChatSessionListResponse {
  sessions?: ChatSession[]
  items?: ChatSession[]
  total?: number
  total_count?: number
}

export interface ChatMessagePayload {
  message_type: 'user' | 'assistant' | 'system'
  agent_type?: AgentType
  content: string
  metadata?: Record<string, unknown>
  environmental_context?: Record<string, unknown>
  correlation_analysis?: Record<string, unknown>
}

export type ChatMessageRecord = {
  id: string | number
  session_id?: string | number
  message_type: 'user' | 'assistant' | 'system' | 'tool'
  agent_type?: AgentType
  content: string
  metadata?: Record<string, unknown> | null
  created_at?: string
}

interface ChatMessageListResponse {
  messages?: ChatMessageRecord[]
  items?: ChatMessageRecord[]
}

export interface ChatMessageUpdatePayload {
  content?: string
  metadata?: Record<string, unknown>
}

export const sessionsAPI = {
  async list(limit = 20, offset = 0): Promise<ChatSession[]> {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const res = await apiClient.get<ChatSessionListResponse | ChatSession[]>(`/api/v1/chat-sessions?${qs.toString()}`)

    if (!res) {
      return []
    }

    if (Array.isArray(res)) {
      return res
    }

    if (Array.isArray(res.sessions)) {
      return res.sessions
    }

    if (Array.isArray(res.items)) {
      return res.items
    }

    return []
  },

  async create(
    agent_type: AgentType = 'primary',
    title?: string,
    options?: RequestInit
  ): Promise<ChatSession> {
    const normalizedTitle = title?.trim() || 'New Chat'
    return apiClient.post<ChatSession>(
      `/api/v1/chat-sessions`,
      { agent_type, title: normalizedTitle },
      options
    )
  },

  async rename(sessionId: string | number, title: string): Promise<ChatSession> {
    return apiClient.put<ChatSession>(`/api/v1/chat-sessions/${sessionId}`, { title })
  },

  async remove(sessionId: string | number): Promise<void> {
    return apiClient.delete<void>(`/api/v1/chat-sessions/${sessionId}`)
  },

  // Messages
  async listMessages(sessionId: string | number, limit = 100, offset = 0): Promise<ChatMessageRecord[]> {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const res = await apiClient.get<ChatMessageListResponse | ChatMessageRecord[]>(
      `/api/v1/chat-sessions/${sessionId}/messages?${qs.toString()}`
    )

    if (!res) {
      return []
    }

    if (Array.isArray(res)) {
      return res
    }

    if (Array.isArray(res.messages)) {
      return res.messages
    }

    if (Array.isArray(res.items)) {
      return res.items
    }

    return []
  },

  async postMessage(
    sessionId: string | number,
    data: ChatMessagePayload,
    options?: RequestInit
  ): Promise<ChatMessageRecord> {
    return apiClient.post<ChatMessageRecord, ChatMessagePayload>(
      `/api/v1/chat-sessions/${sessionId}/messages`,
      data,
      options
    )
  },

  async updateMessage(
    sessionId: string | number,
    messageId: string | number,
    payload: string | ChatMessageUpdatePayload
  ): Promise<ChatMessageRecord> {
    const body = typeof payload === 'string' ? { content: payload } : payload
    return apiClient.put<ChatMessageRecord>(
      `/api/v1/chat-sessions/${sessionId}/messages/${messageId}`,
      body
    )
  },
}
