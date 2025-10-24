"use client"

import React, { useCallback, useEffect, useMemo, useState } from "react"
import {
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/shared/ui/sidebar"
import { Button } from "@/shared/ui/button"
import { Check, FileText, MessageSquare, Trash2, Wrench } from "lucide-react"
import type { LeftTab } from "./AppSidebarLeft"
import { sessionsAPI, type ChatSession } from "@/services/api/endpoints/sessions"
import { useGlobalKnowledgeObservability } from "@/features/global-knowledge/hooks/useGlobalKnowledgeObservability"
import { toast } from "sonner"

type Props = {
  activeTab: LeftTab
  sessionId?: string
  onSelectSession: (id?: string) => void
  isOpen?: boolean
  top?: number
  left?: number
}

export function RightContextSidebar({ activeTab, sessionId, onSelectSession, isOpen = true, top = 96, left }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [hoveredItem, setHoveredItem] = useState<string | null>(null)
  const [deletingItem, setDeletingItem] = useState<string | null>(null)
  const { queue, isQueueLoading, queueError, promoteFeedback, promoteCorrection, removeQueueItem } = useGlobalKnowledgeObservability()
  const memoryUiEnabled = process.env.NEXT_PUBLIC_ENABLE_MEMORY !== 'false'

  const fetchSessions = useCallback(async () => {
    try {
      const items = await sessionsAPI.list(20, 0)
      setSessions(items)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (activeTab === 'primary' || activeTab === 'log') {
      fetchSessions().catch(() => undefined)
    }
    return () => { cancelled = true }
  }, [activeTab, fetchSessions])

  // Keep sessions in sync with chat updates
  useEffect(() => {
    const onRefresh = () => { void fetchSessions() }
    const onUpdated = () => { void fetchSessions() }
    window.addEventListener('chat-sessions:refresh', onRefresh)
    window.addEventListener('chat-session-updated', onUpdated as EventListener)
    return () => {
      window.removeEventListener('chat-sessions:refresh', onRefresh)
      window.removeEventListener('chat-session-updated', onUpdated as EventListener)
    }
  }, [fetchSessions])

  const visibleSessions = useMemo(() => {
    if (activeTab === 'primary') return sessions.filter(s => s.agent_type === 'primary')
    if (activeTab === 'log') return sessions.filter(s => s.agent_type === 'log_analysis')
    return []
  }, [sessions, activeTab])

  const feedbacks = useMemo(() => queue.filter(q => q.kind === 'feedback'), [queue])
  const corrects = useMemo(() => queue.filter(q => q.kind === 'correction'), [queue])

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    setDeletingItem(sessionId)
    try {
      await sessionsAPI.remove(sessionId)
      toast.success('Session deleted')
      await fetchSessions()
    } catch (error) {
      toast.error('Failed to delete session')
    } finally {
      setDeletingItem(null)
    }
  }, [fetchSessions])

  const handleDeleteQueueItem = useCallback(async (itemId: number, kind: 'feedback' | 'correction') => {
    const key = `${kind}-${itemId}`
    setDeletingItem(key)
    try {
      await removeQueueItem(itemId, kind)
      toast.success(`${kind === 'feedback' ? 'Feedback' : 'Correction'} deleted`)
    } catch (error) {
      toast.error(`Failed to delete ${kind === 'feedback' ? 'feedback' : 'correction'}`)
    } finally {
      setDeletingItem(null)
    }
  }, [removeQueueItem])

  if (!isOpen) return null

  const clampedTop = Math.max(64, Math.round(top))
  const defaultLeft = 260 // fallback if not provided (approx sidebar width)
  const clampedLeft = Math.max(0, Math.round((left ?? defaultLeft) + 8))
  const panelStyle: React.CSSProperties = {
    top: `${clampedTop}px`,
    height: `calc(100vh - ${clampedTop + 16}px)`,
    left: `${clampedLeft}px`,
  }

  return (
    <div
      id="right-context-sidebar"
      className="fixed z-50 w-80 max-w-[22rem] rounded-lg border bg-sidebar text-sidebar-foreground shadow-xl flex flex-col"
      style={panelStyle}
    >
          <SidebarHeader className="px-4 py-3 border-b sticky top-0 bg-sidebar">
            <h3 className="font-medium">
              {activeTab === "primary" && "Primary Agent • Chats"}
              {activeTab === "log" && "Log Analysis • Chats"}
              {activeTab === "feedbacks" && "Feedbacks • Added"}
              {activeTab === "corrects" && "Corrects • List"}
            </h3>
          </SidebarHeader>

          <SidebarContent className="flex-1 overflow-y-auto">
            {(activeTab === 'primary' || activeTab === 'log') ? (
              <SidebarGroup>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {visibleSessions.map((s) => {
                      const itemId = String(s.id)
                      const isHovered = hoveredItem === itemId
                      const isDeleting = deletingItem === itemId
                      return (
                        <SidebarMenuItem 
                          key={s.id}
                          onMouseEnter={() => setHoveredItem(itemId)}
                          onMouseLeave={() => setHoveredItem(null)}
                          className="relative group"
                        >
                          <SidebarMenuButton 
                            className="gap-2 pr-10" 
                            onClick={() => onSelectSession(itemId)}
                            disabled={isDeleting}
                          >
                            <MessageSquare className="h-4 w-4" />
                            <span className="truncate">{s.title || 'Conversation'}</span>
                          </SidebarMenuButton>
                          {isHovered && !isDeleting && (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6 hover:bg-destructive/10 hover:text-destructive"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteSession(itemId)
                              }}
                              title="Delete session"
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          )}
                        </SidebarMenuItem>
                      )
                    })}
                    {visibleSessions.length === 0 && (
                      <div className="px-3 py-2 text-xs text-muted-foreground">No conversations</div>
                    )}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            ) : (
              <SidebarGroup>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {(activeTab === 'feedbacks' ? feedbacks : corrects).map((item) => {
                      const itemKey = `${item.kind}-${item.id}`
                      const isHovered = hoveredItem === itemKey
                      const isDeleting = deletingItem === itemKey
                      return (
                        <SidebarMenuItem 
                          key={itemKey}
                          onMouseEnter={() => setHoveredItem(itemKey)}
                          onMouseLeave={() => setHoveredItem(null)}
                          className="relative group"
                        >
                          <SidebarMenuButton
                            className="gap-2 pr-24"
                            disabled={isDeleting}
                            onClick={(e) => {
                              e.preventDefault()
                              try {
                                const md = (item.metadata || {}) as Record<string, unknown>
                                if (item.kind === 'feedback') {
                                  const selected = typeof md['selected_text'] === 'string' ? (md['selected_text'] as string)
                                    : (typeof md['selectedText'] === 'string' ? (md['selectedText'] as string) : '')
                                  window.dispatchEvent(
                                    new CustomEvent('chat:open-feedback-dialog', {
                                      detail: {
                                        feedbackText: item.raw_text || '',
                                        selectedText: selected || undefined,
                                        metadata: md,
                                      },
                                    })
                                  )
                                } else {
                                  const pair = (md['normalized_pair'] as Record<string, unknown> | undefined) || undefined
                                  const incorrect = pair && typeof pair['incorrect'] === 'string' ? (pair['incorrect'] as string) : (item.raw_text || '')
                                  const corrected = pair && typeof pair['corrected'] === 'string' ? (pair['corrected'] as string) : ''
                                  const explanation = typeof md['explanation'] === 'string' ? (md['explanation'] as string) : ''
                                  window.dispatchEvent(
                                    new CustomEvent('chat:open-correction-dialog', {
                                      detail: {
                                        incorrectText: incorrect,
                                        correctedText: corrected,
                                        explanation,
                                        metadata: md,
                                      },
                                    })
                                  )
                                }
                              } catch {}
                            }}
                          >
                            {activeTab === 'feedbacks' ? <FileText className="h-4 w-4" /> : <Wrench className="h-4 w-4" />}
                            <span className="truncate">{item.summary}</span>
                          </SidebarMenuButton>
                          {(isHovered || isDeleting) && (
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-6 w-6 hover:bg-green-500/10 hover:text-green-600"
                                disabled={isDeleting}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  const action = activeTab === 'feedbacks' ? promoteFeedback(item.id) : promoteCorrection(item.id)
                                  void action.then((res) => {
                                    if (res?.success) {
                                      if (memoryUiEnabled) {
                                        toast.success('Promoted to Memory and Knowledge Base')
                                      } else {
                                        toast.success(activeTab === 'feedbacks' ? 'Promoted to feedback store' : 'Promoted to knowledge base')
                                      }
                                    } else if (res) {
                                      toast.error(res.message || 'Promotion failed')
                                    }
                                  })
                                }}
                                title={memoryUiEnabled ? 'Promote to Memory' : (activeTab === 'feedbacks' ? 'Promote to feedback store' : 'Promote to knowledge base')}
                              >
                                <Check className="h-3 w-3" />
                              </Button>
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-6 w-6 hover:bg-destructive/10 hover:text-destructive"
                                disabled={isDeleting}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleDeleteQueueItem(item.id, activeTab === 'feedbacks' ? 'feedback' : 'correction')
                                }}
                                title={activeTab === 'feedbacks' ? 'Delete feedback' : 'Delete correction'}
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            </div>
                          )}
                        </SidebarMenuItem>
                      )
                    })}
                    {isQueueLoading && <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>}
                    {queueError && <div className="px-3 py-2 text-xs text-destructive">{queueError}</div>}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}
          </SidebarContent>
    </div>
  )
}

export default RightContextSidebar
