"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { toast } from "sonner"
import { streamChat } from "@/lib/sse"

// Types for unified chat system
export interface UnifiedMessage {
  id: string
  type: "user" | "agent" | "system"
  content: string
  timestamp: Date | string // Support both Date objects and string timestamps (from JSON deserialization)
  agentType?: "primary" | "log_analyst" | "researcher"
  streaming?: boolean
  thoughtSteps?: Array<{
    step: string
    content: string
    confidence?: number
  }>
  metadata?: {
    confidence?: number
    sources?: any[]
    analysisResults?: any
    routingReason?: string
    researchSteps?: any[]
  }
}

export interface UnifiedChatState {
  messages: UnifiedMessage[]
  isProcessing: boolean
  currentAgent: "primary" | "log_analyst" | "researcher" | null
  routingConfidence: number
  error: string | null
  currentSessionId: string | null
  context: {
    hasFiles: boolean
    isAnalyzing: boolean
    researchSteps: any[]
  }
}

export interface UseUnifiedChatReturn {
  state: UnifiedChatState
  /**
   * Send a message to the chat with optional file attachments, session ID, and model selection.
   * @param content - The message content
   * @param files - Optional file attachments (for log analysis)
   * @param sessionId - Optional session ID. Expected format: numeric string (e.g., "123") or null/undefined
   * @param model - Optional model selection for primary agent (e.g., 'google/gemini-2.5-flash')
   */
  sendMessage: (content: string, files?: File[], sessionId?: string, model?: string) => Promise<void>
  clearConversation: () => void
  retryLastMessage: () => Promise<void>
  loadSessionMessages: (messages: UnifiedMessage[], agentType?: 'primary' | 'log_analysis' | 'research') => void
  setCurrentSessionId: (sessionId: string | null) => void
}

// Unique ID generator to prevent duplicate keys
let messageIdCounter = 0
const generateUniqueId = (prefix: string = ''): string => {
  const timestamp = Date.now()
  const counter = ++messageIdCounter
  return prefix ? `${prefix}-${timestamp}-${counter}` : `${timestamp}-${counter}`
}

// Helper function to parse session ID with validation
const parseSessionId = (sessionId?: string): number | null => {
  if (!sessionId) return null
  const numericSessionId = parseInt(sessionId, 10)
  return !isNaN(numericSessionId) ? numericSessionId : null
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
    currentSessionId: null,
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

  /**
   * Sends a message to the unified chat system with optional file attachments, session ID, and model selection.
   * @param content - The message content to send
   * @param files - Optional file attachments (primarily for log analysis)
   * @param sessionId - Optional session ID. Expected format: numeric string (e.g., "123") or null/undefined
   * @param model - Optional model selection for primary agent
   */
  const sendMessage = useCallback(async (content: string, files?: File[], sessionId?: string, model?: string) => {
    if (!content.trim() && (!files || files.length === 0)) return

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    const suggestedAgent = detectQueryType(content, files)
    
    // Update current session ID if provided
    if (sessionId) {
      setState(prev => ({ ...prev, currentSessionId: sessionId }))
    }

    const userMessage: UnifiedMessage = {
      id: generateUniqueId('user'),
      type: 'user',
      content: content,
      timestamp: new Date(),
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
        isAnalyzing: suggestedAgent === 'log_analyst',
      },
    }))

    try {
      if (suggestedAgent === 'log_analyst' && files && files.length > 0) {
        await handleLogAnalysis(content, files[0], abortController, sessionId, model)
      } else if (suggestedAgent === 'researcher') {
        await handleResearchQuery(content, abortController, sessionId, model)
      } else {
        // Use streaming for primary agent
        await handleStreamingChat(content, abortController, sessionId, model)
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        console.error('💥 Chat error details:', {
          message: error.message,
          stack: error.stack,
          name: error.name,
          suggestedAgent,
          apiBaseUrl,
          contentLength: content.length,
        })
        setState(prev => ({
          ...prev,
          isProcessing: false,
          error: error.message || 'Something went wrong. Please try again.',
        }))
        toast.error('Message failed to send')
      }
    }
  }, [apiBaseUrl])
  
  const handleStreamingChat = async (content: string, abortController: AbortController, sessionId?: string, model?: string) => {
    try {
      console.log('🚀 Starting SSE streaming to:', `/api/v1/agent/chat/stream`)
      
      // Add thinking message
      const thinkingMessage: UnifiedMessage = {
        id: generateUniqueId('thinking'),
        type: 'agent',
        content: 'Analyzing your request...',
        timestamp: new Date(),
        agentType: 'primary',
        metadata: {
          messageType: 'thinking'
        }
      }
      
      setState(prev => ({
        ...prev,
        messages: [...prev.messages, thinkingMessage]
      }))
      
      let assistantContent = ''
      let reasoningUI = null
      const DEFAULT_MODEL = 'gemini-2.5-flash'
      let modelEffective = model || DEFAULT_MODEL
      let budget = null
      
      const cleanup = await streamChat(
        `/api/v1/agent/chat/stream`,
        {
          message: content,
          model: model
        },
        {
          onThinking: (data) => {
            console.log('💭 Thinking:', data)
          },
          onToken: (token) => {
            assistantContent += token
            
            // Update the thinking message with streaming content
            setState(prev => ({
              ...prev,
              messages: prev.messages.map(msg => 
                msg.id === thinkingMessage.id 
                  ? { ...msg, content: assistantContent, streaming: true }
                  : msg
              )
            }))
          },
          onFinal: (data) => {
            console.log('✅ Final data:', data)
            
            // Extract data from final event
            reasoningUI = data.reasoning_ui
            modelEffective = data.model_effective
            budget = data.budget
            
            // Replace thinking message with final message
            const finalMessage: UnifiedMessage = {
              id: generateUniqueId('assistant'),
              type: 'agent',
              content: data.final_response_markdown || assistantContent,
              timestamp: new Date(),
              agentType: 'primary',
              streaming: false,
              metadata: {
                messageType: 'final',
                reasoningUI,
                confidence: reasoningUI?.confidence
              }
            }
            
            setState(prev => ({
              ...prev,
              messages: prev.messages.map(msg => 
                msg.id === thinkingMessage.id ? finalMessage : msg
              ),
              isProcessing: false,
              currentAgent: null
            }))
            
            // Show budget warning if needed
            if (budget?.headroom === 'Low' || budget?.headroom === 'Exhausted') {
              toast.warning(`Model budget is ${budget.headroom.toLowerCase()}`)
            }
          },
          onError: (error) => {
            console.error('❌ Streaming error:', error)
            setState(prev => ({
              ...prev,
              messages: prev.messages.filter(msg => msg.id !== thinkingMessage.id),
              isProcessing: false,
              error: error.message
            }))
            toast.error('Failed to get response')
          }
        }
      )
      
      // Store cleanup function with proper AbortController interface
      const customAbortController: AbortController = {
        signal: abortController.signal,
        abort: () => {
          cleanup()
          abortController.abort()
        }
      }
      abortControllerRef.current = customAbortController
      
    } catch (error: any) {
      console.error('💥 Streaming error:', error)
      setState(prev => ({
        ...prev,
        isProcessing: false,
        error: error.message
      }))
      toast.error('Failed to connect to streaming endpoint')
    }
  }
  
  const handleUnifiedChat = async (content: string, suggestedAgent: string, abortController: AbortController, sessionId?: string, model?: string) => {
    try {
      console.log('🚀 Making API call to:', `${apiBaseUrl}/agent`)
      // Parse and validate session ID
      const parsedSessionId = parseSessionId(sessionId)
      
      const payload = { 
        query: content,
        log_content: null,
        session_id: parsedSessionId,
        model: model
      }
      console.log('📤 Request payload:', payload)
      
      const response = await fetch(`${apiBaseUrl}/agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: abortController.signal
      })
      
      console.log('📡 Response status:', response.status, response.statusText)
      console.log('📡 Response headers:', Object.fromEntries(response.headers.entries()))
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('❌ API Error Response:', errorText)
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }
      
      const result = await response.json()
      console.log('📡 Response data:', result)
      
      // Extract the response data from final_state
      const finalState = result.final_state
      let agentResponse = ""
      let thoughtSteps: Array<{step: string, content: string, confidence?: number}> = []
      let agentType = "primary"
      
      // Handle multiple messages from backend (thinking + final response)
      const responseMessages: UnifiedMessage[] = []
      
      if (finalState.messages && finalState.messages.length > 0) {
        finalState.messages.forEach((message: any, index: number) => {
          if (message.type === 'ai' || message.type === 'assistant') {
            // Check if this is a thinking message
            const isThinking = message.additional_kwargs?.message_type === 'thinking'
            
            if (isThinking) {
              // Create thinking message
              const thinkingMessage: UnifiedMessage = {
                id: generateUniqueId('thinking'),
                type: "agent",
                content: message.content,
                timestamp: new Date(),
                agentType: "primary",
                thoughtSteps: message.additional_kwargs?.thought_steps?.map((step: any) => ({
                  step: step.step,
                  content: step.content,
                  confidence: step.confidence
                })) || [],
                metadata: {
                  messageType: 'thinking',
                  reasoningSummary: message.additional_kwargs?.reasoning_summary,
                  overallConfidence: message.additional_kwargs?.overall_confidence,
                  routingReason: "Agent thinking process"
                }
              }
              responseMessages.push(thinkingMessage)
            } else {
              // This is the final response message
              agentResponse = message.content
              
              // Determine agent type from response
              if (finalState.destination) {
                switch (finalState.destination) {
                  case 'log_analysis':
                    agentType = 'log_analyst'
                    break
                  case 'research':
                    agentType = 'researcher'
                    break
                  default:
                    agentType = 'primary'
                }
              }
              
              // Create the final response message
              const finalMessage: UnifiedMessage = {
                id: generateUniqueId('agent'),
                type: "agent",
                content: agentResponse || "I apologize, but I couldn't generate a proper response. Please try again.",
                timestamp: new Date(),
                agentType: agentType as "primary" | "log_analyst" | "researcher",
                metadata: {
                  messageType: 'final',
                  sources: finalState.sources || [],
                  routingReason: finalState.routing_reason || `Processed by ${agentType} agent`
                }
              }
              responseMessages.push(finalMessage)
            }
          }
        })
      }
      
      // If no messages were processed, create a fallback message
      if (responseMessages.length === 0) {
        const fallbackMessage: UnifiedMessage = {
          id: generateUniqueId('agent'),
          type: "agent",
          content: "I apologize, but I couldn't generate a proper response. Please try again.",
          timestamp: new Date(),
          agentType: "primary",
          metadata: {
            messageType: 'final',
            routingReason: "Fallback response"
          }
        }
        responseMessages.push(fallbackMessage)
      }
      
      setState(prev => ({
        ...prev,
        messages: [...prev.messages, ...responseMessages],
        isProcessing: false,
        currentAgent: agentType as "primary" | "log_analyst" | "researcher"
      }))
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
  
  const handleLogAnalysis = async (content: string, file: File, abortController: AbortController, sessionId?: string, model?: string) => {
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
        // Parse and validate session ID
        const parsedSessionId = parseSessionId(sessionId)
        
        const response = await fetch(`${apiBaseUrl}/agent`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            query: content,
            log_content: fileContent,
            session_id: parsedSessionId,
            model: model
          }),
          signal: abortController.signal
        })
        
        clearTimeout(timeoutId)
        
        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(`Analysis failed (${response.status}): ${errorText}`)
        }
        
        const result = await response.json()
        const finalState = result.final_state
        
        // Debug: Log the analysis results
        console.log('Log Analysis Results:', result)
        
        // Extract response content and analysis data
        let analysisContent = ""
        let analysisResults = null
        let thoughtSteps: Array<{step: string, content: string, confidence?: number}> = []
        
        if (finalState.messages && finalState.messages.length > 0) {
          const lastMessage = finalState.messages[finalState.messages.length - 1]
          if (lastMessage.type === 'ai' || lastMessage.type === 'assistant') {
            analysisContent = lastMessage.content
          }
        }
        
        // Extract analysis results from metadata or state
        if (finalState.analysis_results) {
          analysisResults = finalState.analysis_results
        }
        
        // Extract thought steps if available
        if (finalState.thought_steps && Array.isArray(finalState.thought_steps)) {
          thoughtSteps = finalState.thought_steps
        }
        
        const analysisMessage: UnifiedMessage = {
          id: generateUniqueId('analysis'),
          type: "agent",
          content: analysisContent || `✅ Log analysis complete!`,
          timestamp: new Date(),
          agentType: "log_analyst",
          thoughtSteps: thoughtSteps.length > 0 ? thoughtSteps : undefined,
          metadata: {
            analysisResults: analysisResults,
            sources: finalState.sources || []
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

const handleResearchQuery = async (content: string, abortController: AbortController, sessionId?: string, model?: string) => {
    // Generate a single, stable ID for the entire research stream
    const messageId = generateUniqueId('agent');
    let accumulatedContent = '';
    const steps: any[] = [];

    try {
      // Parse and validate session ID
      const parsedSessionId = parseSessionId(sessionId)
      
      const response = await fetch(`${apiBaseUrl}/agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: content,
          log_content: null,
          session_id: parsedSessionId,
          model: model
        }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json()
      const finalState = result.final_state
      
      // Extract response content and research data
      let researchContent = ""
      let thoughtSteps: Array<{step: string, content: string, confidence?: number}> = []
      
      if (finalState.messages && finalState.messages.length > 0) {
        const lastMessage = finalState.messages[finalState.messages.length - 1]
        if (lastMessage.type === 'ai' || lastMessage.type === 'assistant') {
          researchContent = lastMessage.content
        }
      }
      
      // Extract thought steps if available
      if (finalState.thought_steps && Array.isArray(finalState.thought_steps)) {
        thoughtSteps = finalState.thought_steps
      }
      
      const finalMessage: UnifiedMessage = {
        id: messageId,
        type: "agent",
        content: researchContent || "Research completed, but no results found.",
        timestamp: new Date(),
        agentType: "researcher",
        thoughtSteps: thoughtSteps.length > 0 ? thoughtSteps : undefined,
        metadata: {
          sources: finalState.sources || [],
          researchSteps: finalState.research_steps || []
        }
      };

      setState(prev => ({
        ...prev,
        messages: [
          ...prev.messages.filter(m => m.id !== messageId),
          finalMessage
        ],
        isProcessing: false
      }));
    } finally {
      setState(prev => ({
        ...prev,
        isProcessing: false,
        messages: prev.messages.map(msg =>
          msg.streaming ? { ...msg, streaming: false } : msg
        )
      }));
    }
  };

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
      currentSessionId: null,
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
  
  const loadSessionMessages = useCallback((messages: UnifiedMessage[], agentType?: 'primary' | 'log_analysis' | 'research') => {
    const welcomeMessage: UnifiedMessage = {
      id: "welcome",
      type: "system",
      content: "Hello! I'm your Mailbird support assistant. How can I help you today?",
      timestamp: new Date(),
      agentType: "primary"
    }

    // De-duplicate messages from the session to prevent React key errors.
    // We keep the LAST occurrence of any duplicate ID, as it's the most likely to be up-to-date.
    const seenIds = new Set<string>();
    const uniqueMessages = messages.slice().reverse().filter(msg => {
      if (seenIds.has(msg.id)) {
        console.warn(`Duplicate message ID found and removed from session load: ${msg.id}`);
        return false;
      }
      seenIds.add(msg.id);
      return true;
    }).reverse();
    
    // Map session agentType to currentAgent state
    let currentAgent: "primary" | "log_analyst" | "researcher" | null = null
    if (agentType === 'log_analysis') {
      currentAgent = 'log_analyst'
    } else if (agentType === 'research') {
      currentAgent = 'researcher'
    } else if (agentType === 'primary') {
      currentAgent = 'primary'
    }
    
    setState({
      messages: [welcomeMessage, ...uniqueMessages],
      isProcessing: false,
      currentAgent,
      routingConfidence: 0,
      error: null,
      currentSessionId: null,
      context: {
        hasFiles: uniqueMessages.some(msg => msg.metadata?.analysisResults || msg.type === 'user'),
        isAnalyzing: false,
        researchSteps: []
      }
    })
  }, [])
  
  const setCurrentSessionId = useCallback((sessionId: string | null) => {
    setState(prev => ({ ...prev, currentSessionId: sessionId }))
  }, [])
  
  return {
    state,
    sendMessage,
    clearConversation,
    retryLastMessage,
    loadSessionMessages,
    setCurrentSessionId
  }
}