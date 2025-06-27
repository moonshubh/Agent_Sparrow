"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { toast } from "sonner"

// Types for unified chat system
export interface UnifiedMessage {
  id: string
  type: "user" | "agent" | "system"
  content: string
  timestamp: Date | string // Support both Date objects and string timestamps (from JSON deserialization)
  agentType?: "primary" | "log_analyst" | "researcher"
  streaming?: boolean
  metadata?: {
    confidence?: number
    sources?: any[]
    analysisResults?: any
    routingReason?: string
  }
}

export interface UnifiedChatState {
  messages: UnifiedMessage[]
  isProcessing: boolean
  currentAgent: "primary" | "log_analyst" | "researcher" | null
  routingConfidence: number
  error: string | null
  context: {
    hasFiles: boolean
    isAnalyzing: boolean
    researchSteps: any[]
  }
}

export interface UseUnifiedChatReturn {
  state: UnifiedChatState
  sendMessage: (content: string, files?: File[]) => Promise<void>
  clearConversation: () => void
  retryLastMessage: () => Promise<void>
  loadSessionMessages: (messages: UnifiedMessage[], agentType?: 'primary' | 'log_analysis') => void
}

// Unique ID generator to prevent duplicate keys
let messageIdCounter = 0
const generateUniqueId = (prefix: string = ''): string => {
  const timestamp = Date.now()
  const counter = ++messageIdCounter
  return prefix ? `${prefix}-${timestamp}-${counter}` : `${timestamp}-${counter}`
}

/**
 * Provides a unified chat hook that routes user queries to the appropriate agent (primary, log analyst, or researcher) and manages the conversation state.
 *
 * The hook maintains chat history, handles message sending (including file uploads for log analysis), processes streaming responses, manages errors, and supports conversation reset and retry functionality. It intelligently determines the agent type based on message content and attached files, ensuring a seamless multi-agent chat experience.
 *
 * @returns An object containing the current chat state, a function to send messages (with optional files), a function to clear the conversation, and a function to retry the last user message.
 */
export function useUnifiedChat(): UseUnifiedChatReturn {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || ""
  const abortControllerRef = useRef<AbortController | null>(null)
  
  // Test backend connectivity on initialization
  useEffect(() => {
    const testConnection = async () => {
      try {
        console.log('🔌 Testing backend connectivity to:', apiBaseUrl)
        const response = await fetch(`${apiBaseUrl}/health`, { 
          method: 'GET',
          signal: AbortSignal.timeout(5000) // 5 second timeout
        })
        if (response.ok) {
          console.log('✅ Backend is reachable')
        } else {
          console.warn('⚠️ Backend responded with status:', response.status)
        }
      } catch (error) {
        console.error('❌ Backend connectivity test failed:', error)
        console.log('🔍 Checking if API_BASE_URL is set correctly:', {
          apiBaseUrl,
          NODE_ENV: process.env.NODE_ENV,
          NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL
        })
      }
    }
    
    if (apiBaseUrl) {
      testConnection().catch(error => {
        // Silently handle connection test errors to prevent unhandled promise rejections
        console.debug('Backend connectivity test failed (expected during development):', error.message)
      })
    }
  }, [apiBaseUrl])
  
  const [state, setState] = useState<UnifiedChatState>({
    messages: [
      {
        id: "welcome",
        type: "system",
        content: "Hello! I'm your Mailbird support assistant. I can help with general questions, analyze log files, or research complex topics. How can I assist you today?",
        timestamp: new Date(),
        agentType: "primary"
      }
    ],
    isProcessing: false,
    currentAgent: null,
    routingConfidence: 0,
    error: null,
    context: {
      hasFiles: false,
      isAnalyzing: false,
      researchSteps: []
    }
  })

  /**
   * Determine the agent route for a user query.
   *
   * Detection priority is:
   * 1. Uploaded files -> always log analyst
   * 2. Explicit log analysis keywords
   * 3. Research intent keywords
   * 4. Default to primary agent
   */
  const detectQueryType = (content: string, files?: File[]): "primary" | "log_analyst" | "researcher" => {
    // Only classify as log_analyst when files are actually uploaded
    if (files && files.length > 0) {
      return "log_analyst"
    }
    
    // Check for explicit research indicators (more specific keywords)
    const researchKeywords = [
      "research", "find information about", "latest news", "compare products", 
      "what's new in", "investigate", "gather sources", "multiple sources",
      "comprehensive overview", "detailed research"
    ]
    
    // Only check for explicit log analysis requests (no files = text-only questions)
    const explicitLogKeywords = [
      "analyze this log", "parse log file", "debug this log", "log analysis",
      "examine log entries", "review log output", "check log errors"
    ]
    
    const contentLower = content.toLowerCase()
    
    // Check for explicit log analysis requests (only when very specific)
    if (explicitLogKeywords.some(keyword => contentLower.includes(keyword))) {
      return "log_analyst"
    }
    
    // Check for research indicators (be more specific)
    if (researchKeywords.some(keyword => contentLower.includes(keyword))) {
      return "researcher"
    }
    
    // Default to primary agent for all regular support questions
    // Let the backend router handle the actual classification
    return "primary"
  }

  const sendMessage = useCallback(async (content: string, files?: File[]) => {
    if (!content.trim() && (!files || files.length === 0)) return
    
    // Cancel any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    
    const abortController = new AbortController()
    abortControllerRef.current = abortController
    
    // Detect the appropriate agent
    const suggestedAgent = detectQueryType(content, files)
    
    // Add user message
    const userMessage: UnifiedMessage = {
      id: generateUniqueId('user'),
      type: "user",
      content: content,
      timestamp: new Date()
    }
    
    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage],
      isProcessing: true,
      currentAgent: suggestedAgent,
      error: null,
      context: {
        ...prev.context,
        hasFiles: Boolean(files && files.length > 0),
        isAnalyzing: suggestedAgent === "log_analyst"
      }
    }))
    
    try {
      if (suggestedAgent === "log_analyst" && files && files.length > 0) {
        // Handle log analysis with file upload
        await handleLogAnalysis(content, files[0], abortController)
      } else {
        // Handle all other queries through unified endpoint
        await handleUnifiedChat(content, suggestedAgent, abortController)
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error('💥 Chat error details:', {
          message: error.message,
          stack: error.stack,
          name: error.name,
          suggestedAgent,
          apiBaseUrl,
          contentLength: content.length
        })
        setState(prev => ({
          ...prev,
          isProcessing: false,
          error: error.message || 'Something went wrong. Please try again.'
        }))
        toast.error('Message failed to send')
      }
    }
  }, [apiBaseUrl])
  
  const handleUnifiedChat = async (content: string, suggestedAgent: string, abortController: AbortController) => {
    try {
      console.log('🚀 Making API call to:', `${apiBaseUrl}/api/v1/agent/unified/stream`)
      console.log('📤 Request payload:', { 
        message: content,
        agent_type: suggestedAgent === "primary" ? null : suggestedAgent
      })
      
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/unified/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: content,
          agent_type: suggestedAgent === "primary" ? null : suggestedAgent
        }),
        signal: abortController.signal
      })
      
      console.log('📡 Response status:', response.status, response.statusText)
      console.log('📡 Response headers:', Object.fromEntries(response.headers.entries()))
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('❌ API Error Response:', errorText)
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }
      
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')
      
      const decoder = new TextDecoder()
      let accumulatedContent = ""
      let messageId = generateUniqueId('agent')
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n').filter(line => line.startsWith('data:'))
        
        for (const line of lines) {
          const jsonStr = line.replace('data:', '').trim()
          if (jsonStr === '[DONE]') {
            setState(prev => ({
              ...prev, 
              isProcessing: false,
              messages: prev.messages.map(msg => 
                msg.id === messageId ? { ...msg, streaming: false } : msg
              )
            }))
            return
          }
          
          try {
            const event = JSON.parse(jsonStr)
            
            if (event.role === 'system' && event.content) {
              // Filter out [DONE] tokens that come as system messages
              if (event.content === '[DONE]') {
                setState(prev => ({
                  ...prev, 
                  isProcessing: false,
                  messages: prev.messages.map(msg => 
                    msg.id === messageId ? { ...msg, streaming: false } : msg
                  )
                }))
                return
              }
              
              // Handle system messages (routing notifications)
              const systemMessage: UnifiedMessage = {
                id: generateUniqueId('system'),
                type: "system",
                content: event.content,
                timestamp: new Date(),
                agentType: event.agent_type
              }
              
              setState(prev => ({ 
                ...prev, 
                messages: [...prev.messages, systemMessage],
                currentAgent: event.agent_type || prev.currentAgent
              }))
            } else if (event.role === 'assistant' && event.content) {
              accumulatedContent += event.content
              
              setState(prev => {
                const existingMessageIndex = prev.messages.findIndex(m => m.id === messageId)
                const newMessage: UnifiedMessage = {
                  id: messageId,
                  type: "agent",
                  content: accumulatedContent,
                  timestamp: new Date(),
                  agentType: event.agent_type || "primary",
                  streaming: true,
                  metadata: event.sources ? { sources: event.sources } : undefined
                }
                
                if (existingMessageIndex >= 0) {
                  const newMessages = [...prev.messages]
                  newMessages[existingMessageIndex] = newMessage
                  return { ...prev, messages: newMessages }
                } else {
                  return { ...prev, messages: [...prev.messages, newMessage] }
                }
              })
            }
          } catch (e) {
            console.warn('⚠️ Failed to parse JSON chunk:', jsonStr, e)
          }
        }
      }
    } finally {
      setState(prev => ({
        ...prev, 
        isProcessing: false,
        messages: prev.messages.map(msg => 
          msg.streaming ? { ...msg, streaming: false } : msg
        )
      }))
    }
  }
  
  const handleLogAnalysis = async (content: string, file: File, abortController: AbortController) => {
    try {
      // Add progress message
      const progressMessage: UnifiedMessage = {
        id: generateUniqueId('progress'),
        type: "system",
        content: "🔍 Analyzing log file... This may take several minutes for large files.",
        timestamp: new Date(),
        agentType: "log_analyst"
      }
      
      setState(prev => ({
        ...prev,
        messages: [...prev.messages, progressMessage]
      }))
      
      // Read file content
      const fileContent = await file.text()
      
      // Add file size info
      const sizeInfo: UnifiedMessage = {
        id: generateUniqueId('size'),
        type: "system", 
        content: `📁 Processing ${file.name} (${Math.round(file.size / 1024)}KB, ${fileContent.split('\n').length} lines)`,
        timestamp: new Date(),
        agentType: "log_analyst"
      }
      
      setState(prev => ({
        ...prev,
        messages: [...prev.messages, sizeInfo]
      }))
      
      // Create timeout for very long requests (10 minutes)
      const timeoutId = setTimeout(() => {
        abortController.abort()
      }, 600000) // 10 minutes
      
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/agent/logs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: fileContent }),
          signal: abortController.signal
        })
        
        clearTimeout(timeoutId)
        
        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(`Analysis failed (${response.status}): ${errorText}`)
        }
        
        const result = await response.json()
        
        // Debug: Log the analysis results
        console.log('Log Analysis Results:', result)
        console.log('Issues found:', result.identified_issues?.length || 0)
        console.log('Solutions found:', result.proposed_solutions?.length || 0)
        
        const analysisMessage: UnifiedMessage = {
          id: generateUniqueId('analysis'),
          type: "agent",
          content: `✅ Log analysis complete! ${result.overall_summary}`,
          timestamp: new Date(),
          agentType: "log_analyst",
          metadata: {
            analysisResults: result
          }
        }
        
        setState(prev => ({
          ...prev,
          messages: [...prev.messages, analysisMessage],
          isProcessing: false,
          context: {
            ...prev.context,
            isAnalyzing: false
          }
        }))
      } catch (fetchError: any) {
        clearTimeout(timeoutId)
        throw fetchError
      }
      
    } catch (error: any) {
      // Handle timeouts and other errors gracefully
      if (error.name === 'AbortError') {
        const timeoutMessage: UnifiedMessage = {
          id: generateUniqueId('timeout'),
          type: "system",
          content: "⚠️ Analysis timed out after 10 minutes. Try with a smaller log file or contact support.",
          timestamp: new Date(),
          agentType: "log_analyst"
        }
        
        setState(prev => ({
          ...prev,
          messages: [...prev.messages, timeoutMessage],
          isProcessing: false,
          context: {
            ...prev.context,
            isAnalyzing: false
          }
        }))
      } else {
        throw error
      }
    }
  }
  
  const handleResearchQuery = async (content: string, abortController: AbortController) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/research/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: content }),
        signal: abortController.signal
      })
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')
      
      const decoder = new TextDecoder()
      const steps: any[] = []
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n').filter(line => line.startsWith('data:'))
        
        for (const line of lines) {
          const jsonStr = line.replace('data:', '').trim()
          
          try {
            const event = JSON.parse(jsonStr)
            
            if (event.type === 'step') {
              steps.push(event.data)
              setState(prev => ({
                ...prev,
                context: {
                  ...prev.context,
                  researchSteps: [...steps]
                }
              }))
            } else if (event.type === 'message') {
              const researchMessage: UnifiedMessage = {
                id: generateUniqueId('research'),
                type: "agent",
                content: event.data.content,
                timestamp: new Date(),
                agentType: "researcher",
                metadata: {
                  sources: event.data.citations || []
                }
              }
              
              setState(prev => ({
                ...prev,
                messages: [...prev.messages, researchMessage],
                isProcessing: false
              }))
              return
            }
          } catch (e) {
            console.warn('⚠️ Failed to parse JSON chunk:', jsonStr, e)
          }
        }
      }
    } finally {
      setState(prev => ({ ...prev, isProcessing: false }))
    }
  }
  
  const clearConversation = useCallback(() => {
    setState({
      messages: [
        {
          id: "welcome",
          type: "system",
          content: "Hello! I'm your Mailbird support assistant. How can I help you today?",
          timestamp: new Date(),
          agentType: "primary"
        }
      ],
      isProcessing: false,
      currentAgent: null,
      routingConfidence: 0,
      error: null,
      context: {
        hasFiles: false,
        isAnalyzing: false,
        researchSteps: []
      }
    })
  }, [])
  
  const retryLastMessage = useCallback(async () => {
    try {
      const lastUserMessage = state.messages
        .filter(m => m.type === "user")
        .pop()
      
      if (lastUserMessage) {
        await sendMessage(lastUserMessage.content)
      }
    } catch (error) {
      console.error('Failed to retry message:', error)
      // The sendMessage function already handles errors, so this is just a safety net
    }
  }, [state.messages, sendMessage])
  
  const loadSessionMessages = useCallback((messages: UnifiedMessage[], agentType?: 'primary' | 'log_analysis') => {
    const welcomeMessage: UnifiedMessage = {
      id: "welcome",
      type: "system",
      content: "Hello! I'm your Mailbird support assistant. How can I help you today?",
      timestamp: new Date(),
      agentType: "primary"
    }
    
    setState({
      messages: [welcomeMessage, ...messages],
      isProcessing: false,
      currentAgent: agentType === 'log_analysis' ? 'log_analyst' : 'primary',
      routingConfidence: 0,
      error: null,
      context: {
        hasFiles: messages.some(msg => msg.metadata?.analysisResults || msg.type === 'user'),
        isAnalyzing: false,
        researchSteps: []
      }
    })
  }, [])
  
  return {
    state,
    sendMessage,
    clearConversation,
    retryLastMessage,
    loadSessionMessages
  }
}