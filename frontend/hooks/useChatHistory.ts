import { useState, useEffect, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { UnifiedMessage } from './useUnifiedChat'

export interface ChatSession {
  id: string
  title: string
  agentType: 'primary' | 'log_analysis'
  createdAt: Date
  lastMessageAt: Date
  messages: UnifiedMessage[]
  preview?: string
}

interface ChatHistoryState {
  sessions: ChatSession[]
  currentSessionId: string | null
}

const STORAGE_KEY = 'mb-sparrow-chat-history'
const MAX_SESSIONS_PER_AGENT = 5

export function useChatHistory() {
  const [state, setState] = useState<ChatHistoryState>({
    sessions: [],
    currentSessionId: null
  })

  // Load from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        // Convert date strings back to Date objects
        const sessions = parsed.sessions.map((session: any) => ({
          ...session,
          createdAt: new Date(session.createdAt),
          lastMessageAt: new Date(session.lastMessageAt)
        }))
        setState({
          sessions,
          currentSessionId: parsed.currentSessionId
        })
      } catch (error) {
        console.error('Failed to parse chat history:', error)
      }
    }
  }, [])

  // Save to localStorage whenever state changes
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  }, [state])

  const createSession = useCallback((agentType: 'primary' | 'log_analysis', initialMessage?: string) => {
    const newSession: ChatSession = {
      id: uuidv4(),
      title: initialMessage ? generateTitle(initialMessage) : `New ${agentType === 'primary' ? 'Chat' : 'Analysis'}`,
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
        sessions: allSessions,
        currentSessionId: newSession.id
      }
    })

    return newSession.id
  }, [])

  const selectSession = useCallback((sessionId: string) => {
    setState(prev => ({
      ...prev,
      currentSessionId: sessionId
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

  const addMessageToSession = useCallback((sessionId: string, message: UnifiedMessage) => {
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
  }, [])

  const getCurrentSession = useCallback(() => {
    return state.sessions.find(s => s.id === state.currentSessionId)
  }, [state.sessions, state.currentSessionId])

  return {
    sessions: state.sessions,
    currentSessionId: state.currentSessionId,
    currentSession: getCurrentSession(),
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