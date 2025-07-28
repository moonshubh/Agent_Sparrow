import { useState, useEffect, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { UnifiedMessage } from './useUnifiedChat'
import { chatAPI, ChatAPI, isChatPersistenceAvailable } from '@/lib/api/chat'

export interface ChatSession {
  id: string
  title: string
  agentType: 'primary' | 'log_analysis' | 'research'  // Added research type
  createdAt: Date
  lastMessageAt: Date
  messages: UnifiedMessage[]
  preview?: string
}

interface ChatHistoryState {
  sessions: ChatSession[]
  currentSessionId: string | null
  isPersistenceAvailable: boolean
  isLoading: boolean
}

const STORAGE_KEY = 'mb-sparrow-chat-history'
const MAX_SESSIONS_PER_AGENT = 5

export function useChatHistory() {
  const [state, setState] = useState<ChatHistoryState>({
    sessions: [],
    currentSessionId: null,
    isPersistenceAvailable: false,
    isLoading: true
  })

  // Load sessions on mount - try API first, fallback to localStorage
  useEffect(() => {
    const loadSessions = async () => {
      try {
        // Check if API persistence is available
        const persistenceAvailable = await isChatPersistenceAvailable()
        
        if (persistenceAvailable) {
          // Load from API
          const response = await chatAPI.listSessions(undefined, undefined, 1, 100)
          const sessions = response.sessions.map(ChatAPI.sessionToFrontend)
          
          // Load messages for each session
          // Load messages for each session with session-specific filtering
          const sessionsWithMessages = await Promise.all(
            sessions.map(async (session) => {
              try {
                // Handle both numeric and UUID string session IDs
                let sessionIdForAPI: number | null = null
                if (typeof session.id === 'string') {
                  const numericId = parseInt(session.id)
                  if (!isNaN(numericId)) {
                    sessionIdForAPI = numericId
                  }
                } else if (typeof session.id === 'number') {
                  sessionIdForAPI = session.id
                }
                
                // Only attempt to load messages if we have a valid numeric ID
                if (sessionIdForAPI !== null) {
                  const sessionWithMessages = await chatAPI.getSession(sessionIdForAPI)
                  // Ensure messages are properly filtered by session
                  const filteredMessages = sessionWithMessages.messages
                    .filter(msg => msg.session_id === sessionIdForAPI)
                    .map(ChatAPI.messageToFrontend)
                  return {
                    ...session,
                    messages: filteredMessages
                  }
                } else {
                  // For UUID sessions, just return with empty messages
                  return {
                    ...session,
                    messages: []
                  }
                }
              } catch (error) {
                console.warn('Failed to load messages for session', session.id, error)
                return {
                  ...session,
                  messages: []  // Empty messages on error to prevent contamination
                }
              }
            })
          )
          
          setState(prev => ({
            ...prev,
            sessions: sessionsWithMessages,
            isPersistenceAvailable: true,
            isLoading: false
          }))
        } else {
          // Fallback to localStorage
          const stored = localStorage.getItem(STORAGE_KEY)
          if (stored) {
            try {
              const parsed = JSON.parse(stored)
              const sessions = parsed.sessions.map((session: any) => ({
                ...session,
                createdAt: new Date(session.createdAt),
                lastMessageAt: new Date(session.lastMessageAt)
              }))
              setState(prev => ({
                ...prev,
                sessions,
                currentSessionId: parsed.currentSessionId,
                isPersistenceAvailable: false,
                isLoading: false
              }))
            } catch (error) {
              console.error('Failed to parse chat history:', error)
              setState(prev => ({ ...prev, isLoading: false }))
            }
          } else {
            setState(prev => ({ ...prev, isLoading: false }))
          }
        }
      } catch (error) {
        console.error('Failed to load chat sessions:', error)
        // Fallback to localStorage
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            const sessions = parsed.sessions.map((session: any) => ({
              ...session,
              createdAt: new Date(session.createdAt),
              lastMessageAt: new Date(session.lastMessageAt)
            }))
            setState(prev => ({
              ...prev,
              sessions,
              currentSessionId: parsed.currentSessionId,
              isPersistenceAvailable: false,
              isLoading: false
            }))
          } catch (parseError) {
            console.error('Failed to parse chat history:', parseError)
            setState(prev => ({ ...prev, isLoading: false }))
          }
        } else {
          setState(prev => ({ ...prev, isLoading: false }))
        }
      }
    }

    loadSessions()
  }, [])

  // Save to localStorage whenever state changes (only if API persistence is not available)
  useEffect(() => {
    if (!state.isPersistenceAvailable && !state.isLoading) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        sessions: state.sessions,
        currentSessionId: state.currentSessionId
      }))
    }
  }, [state.sessions, state.currentSessionId, state.isPersistenceAvailable, state.isLoading])

  const createSession = useCallback(async (agentType: 'primary' | 'log_analysis' | 'research', initialMessage?: string) => {
    const title = initialMessage ? generateTitle(initialMessage) : `New ${agentType === 'primary' ? 'Chat' : agentType === 'research' ? 'Research' : 'Analysis'}`
    
    if (state.isPersistenceAvailable) {
      try {
        // Create session via API
        const backendSession = await chatAPI.createSession({
          title,
          agent_type: agentType,
          metadata: { preview: initialMessage },
          is_active: true
        })
        
        const newSession = ChatAPI.sessionToFrontend(backendSession)
        newSession.messages = []
        newSession.preview = initialMessage

        setState(prev => ({
          ...prev,
          sessions: [newSession, ...prev.sessions],
          currentSessionId: newSession.id
        }))

        return newSession.id
      } catch (error) {
        console.error('Failed to create session via API, falling back to local:', error)
        // Fall through to local creation
      }
    }

    // Local session creation (fallback or when API unavailable)
    const newSession: ChatSession = {
      id: uuidv4(),
      title,
      agentType,
      createdAt: new Date(),
      lastMessageAt: new Date(),
      messages: [],
      preview: initialMessage
    }

    setState(prev => {
      // Get sessions for this agent type
      const agentSessions = prev.sessions.filter(s => s.agentType === agentType)
      const otherSessions = prev.sessions.filter(s => s.agentType !== agentType)

      // Sort existing sessions by lastMessageAt (newest first)
      agentSessions.sort((a, b) => b.lastMessageAt.getTime() - a.lastMessageAt.getTime())

      // Add new session at the beginning and enforce limit
      let updatedAgentSessions = [newSession, ...agentSessions]
      if (updatedAgentSessions.length > MAX_SESSIONS_PER_AGENT) {
        updatedAgentSessions = updatedAgentSessions.slice(0, MAX_SESSIONS_PER_AGENT)
        console.log(`Removed ${updatedAgentSessions.length - MAX_SESSIONS_PER_AGENT} old ${agentType} sessions due to limit`)
      }

      // Sort all sessions by lastMessageAt for consistent display
      const allSessions = [...otherSessions, ...updatedAgentSessions]
      allSessions.sort((a, b) => b.lastMessageAt.getTime() - a.lastMessageAt.getTime())

      return {
        ...prev,
        sessions: allSessions,
        currentSessionId: newSession.id
      }
    })

    return newSession.id
  }, [state.isPersistenceAvailable])

  const selectSession = useCallback((sessionId: string) => {
    // Clear state to prevent bleed between sessions
    setState(prev => ({
      sessions: prev.sessions,  // Keep sessions list
      currentSessionId: sessionId,
      isPersistenceAvailable: prev.isPersistenceAvailable,
      isLoading: false  // Ensure loading is false
    }))
  }, [])

  const updateSession = useCallback((sessionId: string, updates: Partial<ChatSession>) => {
    setState(prev => ({
      ...prev,
      sessions: prev.sessions.map(session =>
        session.id === sessionId
          ? { ...session, ...updates, lastMessageAt: new Date() }
          : session
      )
    }))
  }, [])

  const deleteSession = useCallback((sessionId: string) => {
    setState(prev => {
      const newSessions = prev.sessions.filter(s => s.id !== sessionId)
      const newCurrentId = prev.currentSessionId === sessionId
        ? (newSessions.length > 0 ? newSessions[0].id : null)
        : prev.currentSessionId

      return {
        sessions: newSessions,
        currentSessionId: newCurrentId
      }
    })
  }, [])

  const renameSession = useCallback((sessionId: string, newTitle: string) => {
    setState(prev => ({
      ...prev,
      sessions: prev.sessions.map(session =>
        session.id === sessionId
          ? { ...session, title: newTitle }
          : session
      )
    }))
  }, [])

  const addMessageToSession = useCallback(async (sessionId: string, message: UnifiedMessage) => {
    // Update local state immediately for responsive UI
    setState(prev => ({
      ...prev,
      sessions: prev.sessions.map(session =>
        session.id === sessionId
          ? {
              ...session,
              messages: [...session.messages, message],
              lastMessageAt: new Date(),
              preview: message.type === 'user' ? message.content.slice(0, 100) : session.preview
            }
          : session
      )
    }))

    // Sync with API if available
    if (state.isPersistenceAvailable) {
      try {
        const sessionIdNumber = parseInt(sessionId)
        if (!isNaN(sessionIdNumber)) {
          const backendMessage = ChatAPI.messageToBackend(message, sessionIdNumber)
          await chatAPI.addMessage(sessionIdNumber, backendMessage)
        }
      } catch (error) {
        console.warn('Failed to sync message to API:', error)
        // Message is already added to local state, so we can continue
      }
    }
  }, [state.isPersistenceAvailable])

  const getCurrentSession = useCallback(() => {
    return state.sessions.find(s => s.id === state.currentSessionId)
  }, [state.sessions, state.currentSessionId])

  return {
    sessions: state.sessions,
    currentSessionId: state.currentSessionId,
    currentSession: getCurrentSession(),
    isPersistenceAvailable: state.isPersistenceAvailable,
    isLoading: state.isLoading,
    createSession,
    selectSession,
    updateSession,
    deleteSession,
    renameSession,
    addMessageToSession
  }
}

// Helper function to generate a title from the initial message
function generateTitle(message: string): string {
  // Remove any markdown or special formatting
  const cleaned = message.replace(/[#*`_~\[\]]/g, '').trim()
  
  // Take first 50 characters
  const truncated = cleaned.length > 50 ? cleaned.slice(0, 47) + '...' : cleaned
  
  // If it's a question, use it as is
  if (truncated.includes('?')) {
    return truncated.split('?')[0] + '?'
  }
  
  // Otherwise, use the first sentence or phrase
  const firstSentence = truncated.split(/[.!]/)[0]
  return firstSentence || 'New Chat'
}