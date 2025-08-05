"use client"

import React, { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from '@/components/ui/context-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { 
  ChevronLeft, 
  ChevronRight,
  Plus,
  MessageCircle,
  FileSearch,
  Search,
  Trash2,
  Edit3,
  ChevronDown,
  ChevronUp,
  Bot
} from 'lucide-react'
import Image from 'next/image'

export interface ChatSession {
  id: string
  title: string
  agentType: 'primary' | 'log_analysis' | 'research'
  createdAt: Date
  lastMessageAt: Date
  preview?: string
}

interface ChatSidebarProps {
  sessions: ChatSession[]
  currentSessionId?: string
  isCollapsed: boolean
  isLoading?: boolean
  onToggleCollapse: () => void
  onNewChat: (agentType: 'primary' | 'log_analysis' | 'research') => Promise<void>
  onSelectSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
  onRenameSession: (sessionId: string, newTitle: string) => void
}

export function ChatSidebar({
  sessions,
  currentSessionId,
  isCollapsed,
  isLoading = false,
  onToggleCollapse,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onRenameSession
}: ChatSidebarProps) {
  const [primaryExpanded, setPrimaryExpanded] = useState(true)
  const [logAnalysisExpanded, setLogAnalysisExpanded] = useState(true)
  const [researchExpanded, setResearchExpanded] = useState(true)
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')

  // Sort sessions by lastMessageAt (newest first) and enforce limits
  const primarySessions = sessions
    .filter(s => s.agentType === 'primary')
    .sort((a, b) => b.lastMessageAt.getTime() - a.lastMessageAt.getTime())
    .slice(0, 5)
  
  const logAnalysisSessions = sessions
    .filter(s => s.agentType === 'log_analysis')
    .sort((a, b) => b.lastMessageAt.getTime() - a.lastMessageAt.getTime())
    .slice(0, 5)
    
  const researchSessions = sessions
    .filter(s => s.agentType === 'research')
    .sort((a, b) => b.lastMessageAt.getTime() - a.lastMessageAt.getTime())
    .slice(0, 5)

  const handleRename = useCallback((sessionId: string, currentTitle: string) => {
    setEditingSessionId(sessionId)
    setEditingTitle(currentTitle)
  }, [])

  const handleRenameSubmit = useCallback((sessionId: string) => {
    if (editingTitle.trim()) {
      onRenameSession(sessionId, editingTitle.trim())
    }
    setEditingSessionId(null)
    setEditingTitle('')
  }, [editingTitle, onRenameSession])

  const formatDate = (date: Date) => {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    
    if (days === 0) {
      return `Today at ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
    } else if (days === 1) {
      return `Yesterday at ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
    } else if (days < 7) {
      return `${days} days ago`
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }
  }

  return (
    <TooltipProvider>
      <div className={cn(
        "h-full bg-background border-r border-border flex flex-col transition-all duration-300",
        isCollapsed ? "w-16" : "w-80"
      )}>
        {/* Collapse Toggle */}
        <div className="flex items-center justify-end p-2 border-b border-border">
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleCollapse}
            className="h-8 w-8"
          >
            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </Button>
        </div>

        {/* Main Content */}
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-4">
            {/* New Chat Button */}
            <Button
              variant="default"
              className={cn(
                "w-full justify-start gap-2 bg-accent hover:bg-mb-blue-300/90",
                isCollapsed && "justify-center px-2"
              )}
              onClick={() => onNewChat('primary')}
              disabled={isLoading}
            >
              <Plus className="h-4 w-4" />
              {!isCollapsed && <span>New Chat</span>}
            </Button>

            {/* Loading indicator */}
            {isLoading && !isCollapsed && (
              <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground py-4">
                <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
                <span>Loading sessions...</span>
              </div>
            )}

            {/* Primary Agent Section */}
            <div className="space-y-2">
              <Collapsible open={primaryExpanded} onOpenChange={setPrimaryExpanded}>
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    className={cn(
                      "w-full justify-between h-9 px-2 text-sm text-muted-foreground hover:text-foreground",
                      isCollapsed && "justify-center"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Image 
                        src="/primary-agent-icon.png" 
                        alt="Primary Agent" 
                        width={24} 
                        height={24}
                        className="w-6 h-6"
                      />
                      {!isCollapsed && <span>Primary Agent</span>}
                    </div>
                    {!isCollapsed && (
                      primaryExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-1 mt-1">
                  {primarySessions.map((session) => (
                    <SessionItem
                      key={session.id}
                      session={session}
                      isActive={session.id === currentSessionId}
                      isEditing={session.id === editingSessionId}
                      editingTitle={editingTitle}
                      isCollapsed={isCollapsed}
                      onSelect={() => onSelectSession(session.id)}
                      onDelete={() => onDeleteSession(session.id)}
                      onRename={() => handleRename(session.id, session.title)}
                      onRenameSubmit={() => handleRenameSubmit(session.id)}
                      onEditingTitleChange={setEditingTitle}
                      formatDate={formatDate}
                    />
                  ))}
                </CollapsibleContent>
              </Collapsible>
            </div>

            {/* Log Analysis Section */}
            <div className="space-y-2">
              <Collapsible open={logAnalysisExpanded} onOpenChange={setLogAnalysisExpanded}>
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    className={cn(
                      "w-full justify-between h-9 px-2 text-sm text-muted-foreground hover:text-foreground",
                      isCollapsed && "justify-center"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Image 
                        src="/log-analysis-icon.png" 
                        alt="Log Analysis" 
                        width={24} 
                        height={24}
                        className="w-6 h-6"
                      />
                      {!isCollapsed && <span>Log Analysis</span>}
                    </div>
                    {!isCollapsed && (
                      logAnalysisExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-1 mt-1">
                  {logAnalysisSessions.map((session) => (
                    <SessionItem
                      key={session.id}
                      session={session}
                      isActive={session.id === currentSessionId}
                      isEditing={session.id === editingSessionId}
                      editingTitle={editingTitle}
                      isCollapsed={isCollapsed}
                      onSelect={() => onSelectSession(session.id)}
                      onDelete={() => onDeleteSession(session.id)}
                      onRename={() => handleRename(session.id, session.title)}
                      onRenameSubmit={() => handleRenameSubmit(session.id)}
                      onEditingTitleChange={setEditingTitle}
                      formatDate={formatDate}
                    />
                  ))}
                </CollapsibleContent>
              </Collapsible>
            </div>

            {/* Research Section */}
            <div className="space-y-2">
              <Collapsible open={researchExpanded} onOpenChange={setResearchExpanded}>
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    className={cn(
                      "w-full justify-between h-9 px-2 text-sm text-muted-foreground hover:text-foreground",
                      isCollapsed && "justify-center"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Image 
                        src="/research-agent-icon.png" 
                        alt="Research" 
                        width={24} 
                        height={24}
                        className="w-6 h-6"
                      />
                      {!isCollapsed && <span>Research</span>}
                    </div>
                    {!isCollapsed && (
                      researchExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-1 mt-1">
                  {researchSessions.map((session) => (
                    <SessionItem
                      key={session.id}
                      session={session}
                      isActive={session.id === currentSessionId}
                      isEditing={session.id === editingSessionId}
                      editingTitle={editingTitle}
                      isCollapsed={isCollapsed}
                      onSelect={() => onSelectSession(session.id)}
                      onDelete={() => onDeleteSession(session.id)}
                      onRename={() => handleRename(session.id, session.title)}
                      onRenameSubmit={() => handleRenameSubmit(session.id)}
                      onEditingTitleChange={setEditingTitle}
                      formatDate={formatDate}
                    />
                  ))}
                </CollapsibleContent>
              </Collapsible>
            </div>
          </div>
        </ScrollArea>
      </div>
    </TooltipProvider>
  )
}

interface SessionItemProps {
  session: ChatSession
  isActive: boolean
  isEditing: boolean
  editingTitle: string
  isCollapsed: boolean
  onSelect: () => void
  onDelete: () => void
  onRename: () => void
  onRenameSubmit: () => void
  onEditingTitleChange: (title: string) => void
  formatDate: (date: Date) => string
}

function SessionItem({
  session,
  isActive,
  isEditing,
  editingTitle,
  isCollapsed,
  onSelect,
  onDelete,
  onRename,
  onRenameSubmit,
  onEditingTitleChange,
  formatDate
}: SessionItemProps) {
  if (isCollapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={isActive ? "secondary" : "ghost"}
            size="icon"
            className="w-full h-9"
            onClick={onSelect}
          >
            <Bot className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right">
          <p className="text-xs">{formatDate(session.lastMessageAt)}</p>
        </TooltipContent>
      </Tooltip>
    )
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              className={cn(
                "w-full h-9 pl-2 pr-1 text-sm font-normal group flex items-center overflow-hidden cursor-pointer",
                "rounded-md border border-transparent hover:bg-mb-blue-300 hover:bg-mb-blue-300-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                "transition-colors",
                isActive ? "bg-secondary text-secondary-foreground" : "hover:bg-mb-blue-300",
                isActive && "bg-accent/20 text-accent border-l-2 border-accent shadow-sm"
              )}
              onClick={onSelect}
              onDoubleClick={onRename}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect()
                }
              }}
            >
              <div className="flex-1 min-w-0 mr-1 overflow-hidden">
                {isEditing ? (
                  <input
                    type="text"
                    value={editingTitle}
                    onChange={(e) => onEditingTitleChange(e.target.value)}
                    onBlur={onRenameSubmit}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        onRenameSubmit()
                      } else if (e.key === 'Escape') {
                        onEditingTitleChange(session.title)
                        onRenameSubmit()
                      }
                    }}
                    className="bg-transparent outline-none w-full text-ellipsis"
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                    onDoubleClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="block truncate w-full">{session.title}</span>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 min-w-[24px] max-w-[24px] opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-opacity flex-shrink-0"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete()
                }}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p className="text-xs">{formatDate(session.lastMessageAt)}</p>
          </TooltipContent>
        </Tooltip>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onClick={onRename}>
          <Edit3 className="h-4 w-4 mr-2" />
          Rename
        </ContextMenuItem>
        <ContextMenuItem onClick={onDelete} className="text-destructive">
          <Trash2 className="h-4 w-4 mr-2" />
          Delete
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}