"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { toast } from "sonner"
import { getApiUrl } from "@/lib/utils/environment"

// Types for unified chat system
export interface UnifiedMessage {
  id: string
  type: "user" | "agent" | "system"
  content: string
  timestamp: Date | string // Support both Date objects and string timestamps (from JSON deserialization)
  agentType?: "primary" | "primary_agent" | "log_analyst" | "researcher"
  streaming?: boolean
  metadata?: {
    confidence?: number
    sources?: any[]
    analysisResults?: any
    routingReason?: string
    researchSteps?: any[]
    isError?: boolean
    errorType?: string
    followUpQuestions?: string[] // Array of follow-up questions
    followUpQuestionsUsed?: number // Track how many have been used in this session
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
  loadSessionMessages: (messages: UnifiedMessage[], agentType?: 'primary' | 'log_analysis' | 'research') => void
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
  // Use environment-aware API URL
  const apiBaseUrl = getApiUrl()
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
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        console.error('❌ Backend connectivity test failed:', errorMessage)
        console.log('🔍 Checking if API_URL is set correctly:', {
          apiBaseUrl,
          NODE_ENV: process.env.NODE_ENV,
          NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
          hostname: typeof window !== 'undefined' ? window.location.hostname : 'N/A'
        })
        
        // If in production and backend is not reachable, show a warning
        if (process.env.NODE_ENV === 'production' && typeof window !== 'undefined') {
          console.warn('⚠️ Backend API is not reachable. Please ensure the backend server is running.')
        }
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

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    const suggestedAgent = detectQueryType(content, files)

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
        await handleLogAnalysis(content, files[0], abortController)
      } else if (suggestedAgent === 'researcher') {
        await handleResearchQuery(content, abortController)
      } else {
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
  
  const handleUnifiedChat = async (content: string, suggestedAgent: string, abortController: AbortController) => {
    try {
      console.log('🚀 Making API call to:', `${apiBaseUrl}/api/v1/agent/unified/stream`)
      console.log('📤 Request payload:', { 
        message: content,
        agent_type: suggestedAgent === "primary" ? null : suggestedAgent
      })
      
      // Prepare message history for the API
      const messageHistory = state.messages
        .filter(m => m.type !== 'system') // Exclude system messages
        .map(m => ({
          type: m.type,
          role: m.type === 'agent' ? 'assistant' : m.type,
          content: m.content
        }))
      
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/unified/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: content,
          agent_type: suggestedAgent === "primary" ? null : suggestedAgent,
          messages: messageHistory
        }),
        signal: abortController.signal
      })
      
      console.log('📡 Response status:', response.status, response.statusText)
      console.log('📡 Response headers:', Object.fromEntries(response.headers.entries()))
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('❌ API Error Response:', errorText)
        
        // Try to parse the error as JSON to get more details
        let errorMessage = `HTTP ${response.status}: ${errorText}`
        try {
          const errorData = JSON.parse(errorText)
          
          // Check if it's a rate limit error
          if (response.status === 429 || errorData.error === 'rate_limit_exceeded') {
            const limits = errorData.limits || {}
            const model = errorData.model || 'unknown'
            const retryAfter = errorData.retry_after
            
            // Create a user-friendly rate limit message
            errorMessage = `⚠️ Rate limit exceeded for ${model} model.\n\n`
            
            if (limits.rpd_remaining !== undefined) {
              errorMessage += `📊 Daily limit: ${limits.rpd_used || 0}/${limits.rpd_limit || 0} requests used\n`
              errorMessage += `⏰ Daily limit resets: ${limits.reset_time_rpd ? new Date(limits.reset_time_rpd).toLocaleTimeString() : 'unknown'}\n`
            }
            
            if (limits.rpm_remaining !== undefined) {
              errorMessage += `📈 Minute limit: ${limits.rpm_used || 0}/${limits.rpm_limit || 0} requests used\n`
              errorMessage += `⏱️ Minute limit resets: ${limits.reset_time_rpm ? new Date(limits.reset_time_rpm).toLocaleTimeString() : 'in 1 minute'}\n`
            }
            
            if (retryAfter) {
              errorMessage += `\n🔄 Please try again in ${retryAfter} seconds.`
            } else {
              errorMessage += `\n🔄 Please try again later.`
            }
            
            // Add the error message as a system message
            const rateLimitMessage: UnifiedMessage = {
              id: generateUniqueId('rate-limit'),
              type: "system",
              content: errorMessage,
              timestamp: new Date(),
              agentType: "primary",
              metadata: { isError: true, errorType: 'rate_limit' }
            }
            
            setState(prev => ({ 
              ...prev, 
              messages: [...prev.messages, rateLimitMessage],
              isProcessing: false
            }))
            
            return // Exit early for rate limit errors
          }
          
          // Use the error message from the API if available
          if (errorData.detail) {
            errorMessage = errorData.detail
          } else if (errorData.message) {
            errorMessage = errorData.message
          }
        } catch (e) {
          // If JSON parsing fails, use the original error text
          console.debug('Failed to parse error response as JSON:', e)
        }
        
        throw new Error(errorMessage)
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
            } else if (event.role === 'error' && event.content) {
              // Handle error messages (e.g., API key missing)
              const errorMessage: UnifiedMessage = {
                id: generateUniqueId('error'),
                type: "agent",
                content: event.content,
                timestamp: new Date(),
                agentType: "primary",
                metadata: { isError: true }
              }
              
              setState(prev => ({ 
                ...prev, 
                messages: [...prev.messages, errorMessage],
                isProcessing: false
              }))
            } else if (event.role === 'assistant' && event.content) {
              accumulatedContent += event.content

              // Always de-duplicate by messageId before pushing the updated chunk. This
              // guarantees that even if React StrictMode or rapid successive chunks
              // invoke this updater before the previous state has been applied, the
              // final state will only contain ONE message with this `messageId`.
              setState(prev => {
                const newMessage: UnifiedMessage = {
                  id: messageId,
                  type: "agent",
                  content: accumulatedContent,
                  timestamp: new Date(),
                  agentType: event.agent_type || "primary",
                  streaming: true,
                  metadata: event.sources ? { sources: event.sources } : undefined
                }

                const newMessages = [
                  // filter out any stale duplicates for this id
                  ...prev.messages.filter(m => m.id !== messageId),
                  newMessage,
                ]

                return { ...prev, messages: newMessages }
              })
            } else if (event.role === 'metadata' && event.metadata) {
              // Handle metadata event with follow-up questions
              setState(prev => {
                // Find the last agent message and update its metadata
                const lastAgentMessageIndex = prev.messages.findLastIndex(m => m.type === 'agent' && m.id === messageId)
                
                // Add null-safety check and logging
                if (lastAgentMessageIndex >= 0 && prev.messages[lastAgentMessageIndex]) {
                  const updatedMessages = [...prev.messages]
                  updatedMessages[lastAgentMessageIndex] = {
                    ...updatedMessages[lastAgentMessageIndex],
                    metadata: {
                      ...updatedMessages[lastAgentMessageIndex].metadata,
                      ...event.metadata
                    }
                  }
                  console.log(`✅ Updated metadata for message ${messageId} at index ${lastAgentMessageIndex}`)
                  return { ...prev, messages: updatedMessages }
                } else {
                  // Log warning when message is not found
                  console.warn(
                    `⚠️ Could not find agent message with ID ${messageId} to update metadata. ` +
                    `Total messages: ${prev.messages.length}, Last agent message index: ${lastAgentMessageIndex}`
                  )
                }
                return prev
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
    // Generate a single, stable ID for the entire research stream
    const messageId = generateUniqueId('agent');
    let accumulatedContent = '';
    const steps: any[] = [];

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/research/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: content }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const jsonStrs = chunk.split('\n\n').filter(s => s.startsWith('data: ')).map(s => s.slice(6));

        for (const jsonStr of jsonStrs) {
          if (jsonStr === '[DONE]') {
            setState(prev => ({
              ...prev,
              isProcessing: false,
              messages: prev.messages.map(msg =>
                msg.id === messageId ? { ...msg, streaming: false } : msg
              )
            }));
            return;
          }

          try {
            const event = JSON.parse(jsonStr);

            if (event.type === 'step') {
              steps.push(event.data);
              // Update the streaming message with the latest step
              accumulatedContent = `*Researching: ${event.data.description}*`;

              setState(prev => {
                const newMessage: UnifiedMessage = {
                  id: messageId,
                  type: "agent",
                  content: accumulatedContent,
                  timestamp: new Date(),
                  agentType: "researcher",
                  streaming: true,
                   metadata: {
                    researchSteps: steps
                  }
                };
                // Replace or add the message
                const newMessages = [
                  ...prev.messages.filter(m => m.id !== messageId),
                  newMessage
                ];
                return { ...prev, messages: newMessages };
              });
            } else if (event.type === 'final_answer') {
              const finalMessage: UnifiedMessage = {
                id: messageId,
                type: "agent",
                content: event.data.final_answer,
                timestamp: new Date(),
                agentType: "researcher",
                streaming: false, // Stream is complete
                metadata: {
                  sources: event.data.citations || [],
                  researchSteps: steps
                }
              };

              // Replace the streaming message with the final version
              setState(prev => ({
                ...prev,
                messages: [
                  ...prev.messages.filter(m => m.id !== messageId),
                  finalMessage
                ],
                isProcessing: false
              }));
              return;
            }
          } catch (e) {
            console.warn('⚠️ Failed to parse JSON chunk:', jsonStr, e);
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
      context: {
        hasFiles: uniqueMessages.some(msg => msg.metadata?.analysisResults || msg.type === 'user'),
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