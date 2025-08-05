"use client"

import React, { useState, useRef, useEffect, useCallback } from 'react'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import {
  MessageCircle,
  FileSearch,
  Search,
  Bot,
  Loader2,
  Trash2,
  Settings
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUnifiedChat, UnifiedMessage } from '@/hooks/useUnifiedChat'
import { useChatHistory } from '@/hooks/useChatHistory'
import { toast } from 'sonner'
import MessageBubble from './MessageBubble'
import InputSystem from './InputSystem'
import VirtualizedMessageList from './VirtualizedMessageList'
import SystemStatusMessage from './SystemStatusMessage'
import { Header } from '@/components/layout/Header'
import { Welcome } from '@/components/home/Welcome'
import { ChatSidebar } from './ChatSidebar'
import { RateLimitWarning } from '@/components/rate-limiting'
import { UserPanel } from '@/components/layout/UserPanel'
import { useAuth } from '@/hooks/useAuth'

interface AgentStatusProps {
  currentAgent: "primary" | "log_analyst" | "researcher" | null
  isProcessing: boolean
  confidence?: number
}

function AgentStatus({ currentAgent, isProcessing, confidence }: AgentStatusProps) {
  if (!currentAgent && !isProcessing) return null
  
  const getAgentInfo = () => {
    switch (currentAgent) {
      case 'primary':
        return { icon: MessageCircle, label: 'Primary Support', color: 'bg-blue-500', textColor: 'text-blue-400' }
      case 'log_analyst':
        return { icon: FileSearch, label: 'Log Analysis', color: 'bg-orange-500', textColor: 'text-orange-400' }
      case 'researcher':
        return { icon: Search, label: 'Research Agent', color: 'bg-mb-blue-500', textColor: 'text-mb-blue-400' }
      default:
        return { icon: Bot, label: 'Processing', color: 'bg-green-500', textColor: 'text-green-400' }
    }
  }
  
  const { icon: Icon, label, color, textColor } = getAgentInfo()
  
  return (
    <div className="flex items-center gap-2 text-sm">
      <div className={cn(
        "w-2 h-2 rounded-full transition-all",
        color,
        isProcessing && "animate-pulse"
      )} />
      <Icon className={cn("w-4 h-4", textColor)} />
      <span className="text-chat-metadata font-medium">{label}</span>
      {confidence && confidence > 0.8 && (
        <Badge variant="outline" className="text-xs h-5">
          {Math.round(confidence * 100)}%
        </Badge>
      )}
      {isProcessing && <Loader2 className="w-3 h-3 animate-spin text-chat-metadata" />}
    </div>
  )
}

function LoadingIndicator({ agentType }: { agentType?: "primary" | "log_analyst" | "researcher" }) {
  const getLoadingMessage = () => {
    switch (agentType) {
      case 'log_analyst':
        return 'Analyzing log files...'
      case 'researcher':
        return 'Researching your query...'
      default:
        return 'Thinking...'
    }
  }
  
  return (
    <div className="flex justify-center mb-4">
      <div className="flex items-center gap-3 text-sm text-chat-metadata bg-background/50 backdrop-blur-sm rounded-full px-4 py-2 border border-border/30">
        <Image 
          src="/agent-thinking.webp"
          alt="Agent thinking"
          width={32}
          height={32}
          className="animate-pulse"
        />
        <span>{getLoadingMessage()}</span>
      </div>
    </div>
  )
}

export default function UnifiedChatInterface() {
  const { user, isAuthenticated, logout } = useAuth()
  const { state, sendMessage, clearConversation, retryLastMessage, loadSessionMessages } = useUnifiedChat()
  const {
    sessions,
    currentSessionId,
    currentSession,
    isPersistenceAvailable,
    isLoading: isSessionsLoading,
    createSession,
    selectSession,
    updateSession,
    deleteSession,
    renameSession,
    addMessageToSession
  } = useChatHistory()
  
  const [inputValue, setInputValue] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [isClient, setIsClient] = useState(false)
  const [windowHeight, setWindowHeight] = useState(600) // Default height for SSR
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [logAnalysisState, setLogAnalysisState] = useState<{
    isActive: boolean
    fileName?: string
    fileSize?: string
    lines?: number
    startedAt?: Date
  }>({ isActive: false })
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const lastProcessedMessageId = useRef<string | null>(null)
  
  // Handle client-side rendering and window dimensions
  useEffect(() => {
    setIsClient(true)
    setWindowHeight(window.innerHeight)
    
    const handleResize = () => {
      setWindowHeight(window.innerHeight)
    }
    
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])
  
  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages])

  // Monitor log analysis state
  useEffect(() => {
    const isLogAnalysisActive = state.currentAgent === 'log_analyst' && state.isProcessing && state.context.isAnalyzing
    
    if (isLogAnalysisActive && !logAnalysisState.isActive) {
      // Log analysis just started - extract file info from recent messages
      const recentFileMessage = state.messages
        .slice(-5) // Look at last 5 messages
        .find(msg => msg.content.includes('📁 Processing') && msg.agentType === 'log_analyst')
        
      if (recentFileMessage) {
        // Extract file info from the message content: "📁 Processing filename.log (123KB, 456 lines)"
        const match = recentFileMessage.content.match(/📁 Processing (.+?) \((\d+(?:\.\d+)?KB), (\d+) lines\)/)
        if (match) {
          const [, fileName, fileSize, linesStr] = match
          setLogAnalysisState({
            isActive: true,
            fileName,
            fileSize,
            lines: parseInt(linesStr, 10),
            startedAt: new Date()
          })
        }
      } else {
        // Fallback if we can't extract file info
        setLogAnalysisState({
          isActive: true,
          startedAt: new Date()
        })
      }
    } else if (!isLogAnalysisActive && logAnalysisState.isActive) {
      // Log analysis finished
      setLogAnalysisState({ isActive: false })
    }
  }, [state.currentAgent, state.isProcessing, state.context.isAnalyzing, state.messages, logAnalysisState.isActive])
  
  // Helper to map currentAgent to session agentType
  const mapAgentToSessionType = (agent: string | null): 'primary' | 'log_analysis' | 'research' => {
    if (agent === 'log_analyst') return 'log_analysis'
    if (agent === 'researcher') return 'research'
    if (agent === 'primary_agent') return 'primary'
    return 'primary'
  }

  const handleSendMessage = async (content: string, messageFiles?: File[]) => {
    if (!content.trim() && (!messageFiles || messageFiles.length === 0)) return
    if (state.isProcessing) return
    
    try {
      // Create a new session if needed
      let sessionId = currentSessionId
      if (!sessionId) {
        // Determine agent type based on file upload or content
        let agentType: 'primary' | 'log_analysis' | 'research' = 'primary'
        if (messageFiles && messageFiles.length > 0) {
          agentType = 'log_analysis'
        } else {
          const contentLower = content.toLowerCase()
          if (contentLower.includes('research') || contentLower.includes('find information')) {
            agentType = 'research'
          }
        }
        sessionId = await createSession(agentType, content)
      }
      
      await sendMessage(content, messageFiles)
      
      // Session message syncing is handled by the useEffect below
      // Update session title if this is the first user message
      if (sessionId) {
        const userMessages = state.messages.filter(m => m.type === 'user')
        if (userMessages.length === 0) { // No user messages yet, this will be the first
          updateSessionTitle(sessionId, content)
        }
      }
    } catch (error) {
      console.error('Failed to send message:', error)
      toast.error('Failed to send message. Please try again.')
    }
  }
  
  const handleMessageRate = (messageId: string, rating: 'up' | 'down') => {
    // TODO: Implement message rating API call
    console.log('Rating message:', messageId, rating)
  }
  
  // Chat history handlers
  const handleNewChat = async (agentType: 'primary' | 'log_analysis' | 'research') => {
    clearConversation()
    const sessionId = await createSession(agentType)
    selectSession(sessionId)
  }
  
  const handleSelectSession = (sessionId: string) => {
    const session = sessions.find(s => s.id === sessionId)
    if (session) {
      // Don't clear conversation, just load the session messages directly
      selectSession(sessionId)
      
      // Load session messages into the chat state
      loadSessionMessages(session.messages || [], session.agentType)
    }
  }
  
  
  const handleDeleteSession = (sessionId: string) => {
    deleteSession(sessionId)
    if (currentSessionId === sessionId) {
      clearConversation()
    }
  }
  

  // Handle title updates when user sends first message
  const updateSessionTitle = useCallback((sessionId: string, messageContent: string) => {
    const currentSession = sessions.find(s => s.id === sessionId)
    if (currentSession && (currentSession.title.startsWith('New ') || currentSession.title === 'New Chat' || currentSession.title === 'New Analysis')) {
      const newTitle = generateSessionTitle(messageContent)
      if (newTitle !== currentSession.title) {
        renameSession(sessionId, newTitle)
      }
    }
  }, [sessions, renameSession])

  // Sync new messages to history (controlled to prevent infinite loops)
  useEffect(() => {
    const syncMessage = async () => {
      if (currentSessionId && state.messages.length > 1) {
        const lastMessage = state.messages[state.messages.length - 1]
        
        // Only process if this is a new message we haven't seen before
        if (lastMessage.id !== lastProcessedMessageId.current && lastMessage.id !== 'welcome') {
          lastProcessedMessageId.current = lastMessage.id
          
          // Update session's agent type based on actual agent response if needed
          const currentSession = sessions.find(s => s.id === currentSessionId)
          if (currentSession && lastMessage.agentType && lastMessage.type === 'agent') {
            const mappedType = mapAgentToSessionType(lastMessage.agentType)
            if (currentSession.agentType !== mappedType) {
              // Update session to correct agent type
              updateSession(currentSessionId, { agentType: mappedType })
            }
          }
          
          await addMessageToSession(currentSessionId, lastMessage)
        }
      }
    }

    syncMessage().catch(error => {
      console.error('Failed to sync message to session:', error)
    })
  }, [state.messages.length, currentSessionId, addMessageToSession, sessions, updateSession]) // Added dependencies
  
  // Helper function to generate a title from the first message
  const generateSessionTitle = (message: string): string => {
    const cleaned = message.replace(/[#*`_~\[\]]/g, '').trim()
    const truncated = cleaned.length > 40 ? cleaned.slice(0, 37) + '...' : cleaned
    return truncated || 'New Chat'
  }
  
  const hasMessages = state.messages.length > 1 // More than just welcome message
  
  return (
    <div 
      className="h-screen flex flex-col bg-chat-background"
      role="main"
      aria-label="Mailbird Support Chat Interface"
    >
      {/* Header */}
      <Header />
      
      {/* Main Content Area with Sidebar */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat Sidebar */}
        <ChatSidebar
          sessions={sessions}
          currentSessionId={currentSessionId || undefined}
          isCollapsed={isSidebarCollapsed}
          isLoading={isSessionsLoading}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          onRenameSession={renameSession}
        />
        
        {/* Chat Area */}
        <div className="flex-1 flex flex-col relative">
          {/* Welcome Hero (shown when no messages exist) */}
          {!hasMessages && (
            <div className="flex-1 flex items-center justify-center">
              <Welcome hasMessages={hasMessages} />
            </div>
          )}

          {/* Messages Area */}
          {hasMessages && (
            <div className="flex-1 overflow-hidden">
              <div className="h-full relative">
                {/* Agent Status Bar */}
                {(state.isProcessing || state.currentAgent) && (
                  <div className="flex-shrink-0 border-b border-border/50 bg-background/80 backdrop-blur-sm">
                    <div className="w-full max-w-4xl mx-auto px-4 md:px-6 lg:px-8 py-2">
                      <div className="flex items-center justify-between">
                        <AgentStatus 
                          currentAgent={state.currentAgent} 
                          isProcessing={state.isProcessing}
                          confidence={state.routingConfidence}
                        />
                        
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={clearConversation}
                            className="text-chat-metadata hover:text-foreground"
                          >
                            <Trash2 className="w-4 h-4 mr-2" />
                            Clear
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-chat-metadata hover:text-foreground"
                          >
                            <Settings className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Rate Limit Warning */}
                <div className="flex-shrink-0">
                  <div className="w-full max-w-4xl mx-auto px-4 md:px-6 lg:px-8 py-2">
                    <RateLimitWarning 
                      warningThreshold={0.7}
                      criticalThreshold={0.85}
                      autoCheck={true}
                      checkInterval={10000}
                      dismissible={true}
                    />
                  </div>
                </div>

                {/* Use virtualized list for large conversations */}
                {isClient && state.messages.length > 50 ? (
                  <VirtualizedMessageList
                    messages={state.messages.slice(1)} // Skip welcome message
                    onRetry={retryLastMessage}
                    onRate={handleMessageRate}
                    containerHeight={windowHeight - 280}
                  />
                ) : (
                  <ScrollArea ref={scrollAreaRef} className="h-full">
                    <div className="w-full max-w-4xl mx-auto px-4 md:px-6 lg:px-8 py-6 space-y-6 pb-24">
                      {/* Messages */}
                      {state.messages.slice(1).map((message) => ( // Skip welcome message
                        <MessageBubble
                          key={message.id}
                          id={message.id}
                          type={message.type}
                          content={message.content}
                          timestamp={message.timestamp}
                          agentType={message.agentType}
                          metadata={message.metadata}
                          streaming={message.streaming}
                          onRetry={message.type === 'agent' ? retryLastMessage : undefined}
                          onRate={(rating) => handleMessageRate(message.id, rating)}
                        />
                      ))}
                      
                      {/* SystemStatusMessage for active log analysis */}
                      {logAnalysisState.isActive && logAnalysisState.startedAt && (
                        <SystemStatusMessage
                          phase="analyzing"
                          filesize={logAnalysisState.fileName ? `"${logAnalysisState.fileName}" (${logAnalysisState.fileSize})` : logAnalysisState.fileSize}
                          lines={logAnalysisState.lines}
                          startedAt={logAnalysisState.startedAt}
                        />
                      )}
                      
                      <div ref={messagesEndRef} />
                    </div>
                  </ScrollArea>
                )}
                
                {/* Loading Indicator - Fixed position */}
                {state.isProcessing && (
                  <div className="absolute bottom-24 left-0 right-0 p-4 bg-gradient-to-t from-chat-background to-transparent">
                    <div className="w-full max-w-4xl mx-auto">
                      <LoadingIndicator agentType={state.currentAgent || undefined} />
                    </div>
                  </div>
                )}
                
                {/* Error Display - Fixed position */}
                {state.error && (
                  <div className="absolute bottom-24 left-0 right-0 p-4 bg-gradient-to-t from-chat-background to-transparent">
                    <div className="w-full max-w-4xl mx-auto">
                      <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-destructive">
                          <div className="w-4 h-4 rounded-full bg-destructive/20 flex items-center justify-center">
                            <span className="text-xs">!</span>
                          </div>
                          <span className="text-sm font-medium">Error</span>
                        </div>
                        <p className="text-sm text-destructive/80 mt-1">{state.error}</p>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={retryLastMessage}
                          className="mt-3 text-destructive border-destructive/20 hover:bg-destructive/10"
                        >
                          Try Again
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Fixed Input Area at Bottom Center */}
          <div className="absolute bottom-0 left-0 right-0 bg-background/80 backdrop-blur-sm">
            <div className="w-full max-w-4xl mx-auto px-4 md:px-6 lg:px-8 py-4">
              <InputSystem
                value={inputValue}
                onChange={setInputValue}
                onSubmit={handleSendMessage}
                files={files}
                onFilesChange={setFiles}
                isLoading={state.isProcessing}
                placeholder={
                  files.length > 0 
                    ? "Describe the issue or ask questions about the uploaded files..."
                    : hasMessages
                    ? "Ask a follow-up question..."
                    : "Ask anything about Mailbird..."
                }
                disabled={false}
                isWelcomeMode={!hasMessages}
              />
            </div>
          </div>
        </div>
      </div>
      
      {/* Live region for screen readers */}
      <div 
        aria-live="polite" 
        aria-atomic="true" 
        className="sr-only"
        role="status"
      >
        {state.isProcessing && "Assistant is thinking..."}
        {state.error && `Error: ${state.error}`}
      </div>
      
      {/* User Panel */}
      <UserPanel
        user={user}
        isAuthenticated={isAuthenticated}
        onLogout={logout}
      />
    </div>
  )
}