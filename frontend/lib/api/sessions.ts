import { apiClient } from '@/lib/api-client'

export type AgentType = 'primary' | 'log_analysis' | 'research'

export interface ChatSession {
  id: string | number
  title?: string
  agent_type?: AgentType
  created_at?: string
  updated_at?: string
  metadata?: {
    error_count?: number
    warning_count?: number
    health_status?: string
    [key: string]: any
  }
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
  metadata?: Record<string, any>
  environmental_context?: Record<string, any>
  correlation_analysis?: Record<string, any>
}

export const sessionsAPI = {
  async list(limit = 20, offset = 0): Promise<ChatSession[]> {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const res = await apiClient.get<ChatSessionListResponse>(`/api/v1/chat-sessions?${qs.toString()}`)
    if (Array.isArray((res as any)?.sessions)) return (res as any).sessions as ChatSession[]
    if (Array.isArray((res as any)?.items)) return (res as any).items as ChatSession[]
    if (Array.isArray(res as any)) return res as any
    return []
  },

  async create(agent_type: AgentType = 'primary', title?: string): Promise<ChatSession> {
    const normalizedTitle = title?.trim() || 'New Chat'
    return apiClient.post<ChatSession>(`/api/v1/chat-sessions`, { agent_type, title: normalizedTitle })
  },

  async rename(sessionId: string | number, title: string): Promise<ChatSession> {
    return apiClient.put<ChatSession>(`/api/v1/chat-sessions/${sessionId}`, { title })
  },

  async remove(sessionId: string | number): Promise<void> {
    return apiClient.delete<void>(`/api/v1/chat-sessions/${sessionId}`)
  },

  // Messages
  async listMessages(sessionId: string | number, limit = 100, offset = 0): Promise<Array<{ id: string | number; message_type: 'user'|'assistant'|'system'|'tool'; content: string; created_at?: string }>> {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const res = await apiClient.get<any>(`/api/v1/chat-sessions/${sessionId}/messages?${qs.toString()}`)
    if (Array.isArray(res?.messages)) return res.messages
    if (Array.isArray(res?.items)) return res.items
    if (Array.isArray(res)) return res
    return []
  },

  async postMessage(sessionId: string | number, data: ChatMessagePayload) {
    return apiClient.post(`/api/v1/chat-sessions/${sessionId}/messages`, data)
  },
}
