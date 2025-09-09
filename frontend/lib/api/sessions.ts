import { apiClient } from '@/lib/api-client'

export type AgentType = 'primary' | 'log_analysis' | 'research'

export interface ChatSession {
  id: string
  title?: string
  agent_type?: AgentType
  created_at?: string
  updated_at?: string
}

export interface ChatSessionListResponse {
  items?: ChatSession[]
  total?: number
}

export const sessionsAPI = {
  async list(limit = 20, offset = 0): Promise<ChatSession[]> {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const res = await apiClient.get<ChatSessionListResponse>(`/api/v1/chat-sessions?${qs.toString()}`)
    if (Array.isArray((res as any)?.items)) return (res as any).items as ChatSession[]
    if (Array.isArray(res as any)) return res as any
    return []
  },

  async create(agent_type: AgentType = 'primary', title?: string): Promise<ChatSession> {
    return apiClient.post<ChatSession>(`/api/v1/chat-sessions`, { agent_type, ...(title ? { title } : {}) })
  },

  async rename(sessionId: string, title: string): Promise<ChatSession> {
    return apiClient.put<ChatSession>(`/api/v1/chat-sessions/${sessionId}`, { title })
  },

  async remove(sessionId: string): Promise<void> {
    return apiClient.delete<void>(`/api/v1/chat-sessions/${sessionId}`)
  },

  // Messages
  async listMessages(sessionId: string, limit = 100, offset = 0): Promise<Array<{ id: string; message_type: 'user'|'assistant'|'system'|'tool'; content: string; created_at?: string }>> {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    const res = await apiClient.get<any>(`/api/v1/chat-sessions/${sessionId}/messages?${qs.toString()}`)
    if (Array.isArray(res?.items)) return res.items
    if (Array.isArray(res)) return res
    return []
  },
}
