/**
 * Chat Session API Client
 * Handles persistent chat storage via backend API
 */

import { UnifiedMessage } from '@/hooks/useUnifiedChat'
import { getSession } from '@/lib/supabase'

// API Base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || ''

// Types matching backend schemas
export type AgentType = 'primary' | 'log_analysis' | 'research'
export type MessageType = 'user' | 'assistant' | 'system'

export interface ChatSession {
  id: number
  user_id: string
  title: string
  agent_type: AgentType
  created_at: string
  last_message_at: string
  updated_at: string
  is_active: boolean
  message_count: number
  metadata: Record<string, any>
}

export interface ChatMessage {
  id: number
  session_id: number
  content: string
  message_type: MessageType
  agent_type?: AgentType
  created_at: string
  metadata: Record<string, any>
}

export interface SessionWithMessages extends ChatSession {
  messages: ChatMessage[]
}

export interface CreateSessionRequest {
  title: string
  agent_type: AgentType
  metadata?: Record<string, any>
  is_active?: boolean
}

export interface UpdateSessionRequest {
  title?: string
  is_active?: boolean
  metadata?: Record<string, any>
}

export interface CreateMessageRequest {
  content: string
  message_type: MessageType
  agent_type?: AgentType
  metadata?: Record<string, any>
}

export interface SessionListResponse {
  sessions: ChatSession[]
  total_count: number
  page: number
  page_size: number
  has_next: boolean
  has_previous: boolean
}

// API Client Class
export class ChatAPI {
  private baseUrl: string
  private authToken: string | null = null

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || `${API_BASE_URL}/api/v1`
  }

  // Set authentication token (for future use)
  setAuthToken(token: string) {
    this.authToken = token
  }

  // Helper to generate user ID (for now, use a simple browser fingerprint)
  private getUserId(): string {
    // In a real app, this would come from authentication
    // For now, generate a stable browser-based ID
    let userId = localStorage.getItem('mb-sparrow-user-id')
    if (!userId) {
      userId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
      localStorage.setItem('mb-sparrow-user-id', userId)
    }
    return userId
  }

  // Helper for API requests
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    // Try to get the current session token
    try {
      const session = await getSession()
      if (session?.access_token) {
        headers['Authorization'] = `Bearer ${session.access_token}`
      } else if (this.authToken) {
        headers['Authorization'] = `Bearer ${this.authToken}`
      }
    } catch (error) {
      console.debug('Failed to get session for auth header:', error)
      // Continue without auth header
    }

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`API Error ${response.status}: ${errorText}`)
    }

    return response.json()
  }

  // Session Management
  async createSession(request: CreateSessionRequest): Promise<ChatSession> {
    const sessionData = {
      ...request,
      // Backend expects the authenticated user ID, but for now we'll use anonymous
    }

    return this.request<ChatSession>('/chat-sessions', {
      method: 'POST',
      body: JSON.stringify(sessionData),
    })
  }

  async listSessions(
    agentType?: AgentType,
    isActive?: boolean,
    page = 1,
    pageSize = 20
  ): Promise<SessionListResponse> {
    const params = new URLSearchParams()
    if (agentType) params.append('agent_type', agentType)
    if (isActive !== undefined) params.append('is_active', isActive.toString())
    params.append('page', page.toString())
    params.append('page_size', pageSize.toString())

    return this.request<SessionListResponse>(`/chat-sessions?${params}`)
  }

  async getSession(sessionId: number, includeMessages = true): Promise<SessionWithMessages> {
    const params = includeMessages ? '?include_messages=true' : '?include_messages=false'
    return this.request<SessionWithMessages>(`/chat-sessions/${sessionId}${params}`)
  }

  async updateSession(sessionId: number, updates: UpdateSessionRequest): Promise<ChatSession> {
    return this.request<ChatSession>(`/chat-sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }

  async deleteSession(sessionId: number): Promise<void> {
    await this.request(`/chat-sessions/${sessionId}`, {
      method: 'DELETE',
    })
  }

  // Message Management
  async addMessage(sessionId: number, message: CreateMessageRequest): Promise<ChatMessage> {
    return this.request<ChatMessage>(`/chat-sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify(message),
    })
  }

  // Utility functions to convert between frontend and backend formats
  static sessionToFrontend(session: ChatSession): import('@/hooks/useChatHistory').ChatSession {
    return {
      id: session.id.toString(),
      title: session.title,
      agentType: session.agent_type,
      createdAt: new Date(session.created_at),
      lastMessageAt: new Date(session.last_message_at),
      messages: [], // Will be populated separately
      preview: undefined, // Could extract from metadata
    }
  }

  static messageToFrontend(message: ChatMessage): UnifiedMessage {
    return {
      id: message.id.toString(),
      type: message.message_type === 'assistant' ? 'agent' : message.message_type,
      content: message.content,
      timestamp: new Date(message.created_at),
      agentType: message.agent_type,
      metadata: message.metadata,
    }
  }

  static messageToBackend(message: UnifiedMessage, sessionId: number): CreateMessageRequest {
    // Map agent types to valid backend values
    let mappedAgentType = message.agentType
    if (mappedAgentType === 'log_analyst') {
      mappedAgentType = 'log_analysis'
    } else if (mappedAgentType === 'researcher') {
      mappedAgentType = 'research'
    }
    
    return {
      content: message.content,
      message_type: message.type === 'agent' ? 'assistant' : message.type,
      agent_type: mappedAgentType,
      metadata: message.metadata || {},
    }
  }

  // Batch operations for sync
  async syncSession(
    sessionId: number,
    messages: UnifiedMessage[]
  ): Promise<{ synced: number; total: number }> {
    // For now, we'll add messages one by one
    // In the future, we could implement a bulk sync endpoint
    let synced = 0
    
    for (const message of messages) {
      try {
        const backendMessage = ChatAPI.messageToBackend(message, sessionId)
        await this.addMessage(sessionId, backendMessage)
        synced++
      } catch (error) {
        console.warn('Failed to sync message:', message.id, error)
      }
    }

    return { synced, total: messages.length }
  }
}

// Default instance
export const chatAPI = new ChatAPI()

// Helper to check if chat persistence is available
export async function isChatPersistenceAvailable(): Promise<boolean> {
  try {
    await chatAPI.listSessions(undefined, undefined, 1, 1)
    return true
  } catch {
    return false
  }
}