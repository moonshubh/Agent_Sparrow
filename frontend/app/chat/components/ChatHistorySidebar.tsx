"use client"

import React, { useCallback, useEffect, useState } from "react"
import Image from "next/image"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  SidebarTrigger,
  SidebarRail,
} from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { GradientButton } from "@/components/ui/gradient-button"
import { Input } from "@/components/ui/input"
import { Plus, MessageSquare, FolderGit2, MoreHorizontal } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipProvider,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog"
import { sessionsAPI, type ChatSession } from "@/lib/api/sessions"

type Props = {
  sessionId?: string
  onSelect: (sessionId: string | undefined) => void
}

type SessionUpdatedDetail = {
  sessionId: string
  title?: string
  metadata?: Record<string, any>
  agentType?: string
}

export function ChatHistorySidebar({ sessionId, onSelect }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState<string>("")
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [renameTimer, setRenameTimer] = useState<NodeJS.Timeout | null>(null)

  const refreshSessions = useCallback(
    async (
      {
        silent = false,
        aborted,
      }: { silent?: boolean; aborted?: () => boolean } = {}
    ) => {
      const isAborted = () => (aborted ? aborted() : false)

      if (!silent) {
        setLoading(true)
        setError(null)
      }

      try {
        const items = await sessionsAPI.list(10, 0)
        if (isAborted()) return
        setSessions(items.slice(0, 10))
      } catch (refreshError: any) {
        if (isAborted()) return
        if (silent) {
          console.error('Failed to refresh chat sessions', refreshError)
        } else {
          setError(refreshError?.message || 'Failed to load sessions')
        }
      } finally {
        if (!silent && !isAborted()) {
          setLoading(false)
        }
      }
    },
    []
  )

  useEffect(() => {
    let cancelled = false
    refreshSessions({ silent: false, aborted: () => cancelled })
    return () => {
      cancelled = true
    }
  }, [refreshSessions])

  const onCreate = async () => {
    try {
      const s = await sessionsAPI.create("primary")
      setSessions(prev => [s, ...prev].slice(0, 10))
      onSelect(String(s.id))
    } catch (e) {
      console.error("Failed to create session", e)
    }
  }

  // Debounced auto-save for rename
  useEffect(() => {
    if (!editingId) return
    if (renameTimer) clearTimeout(renameTimer)
    const t = setTimeout(async () => {
      const title = editingTitle.trim()
      try {
        const updated = await sessionsAPI.rename(editingId, title || "Untitled")
        setSessions(prev => prev.map(s => (String(s.id) === editingId ? updated : s)))
      } catch (e) {
        console.error('Failed to rename session', e)
      }
    }, 500)
    setRenameTimer(t)
    return () => clearTimeout(t)
  }, [editingId, editingTitle])

  useEffect(() => {
    const handleSessionUpdated = (event: Event) => {
      const detail = (event as CustomEvent<SessionUpdatedDetail>).detail
      if (!detail?.sessionId) return

      const nowIso = new Date().toISOString()

      setSessions((prev) => {
        const updated = prev.map((s) => {
          if (String(s.id) !== detail.sessionId) return s
          return {
            ...s,
            title: detail.title ?? s.title,
            metadata: detail.metadata ?? s.metadata,
            agent_type: (detail.agentType as ChatSession['agent_type']) ?? s.agent_type,
            updated_at: nowIso,
            last_message_at: nowIso,
          }
        })

        return updated.sort((a, b) => {
          const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0
          const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0
          return bTime - aTime
        })
      })
    }

    const handleRefreshRequest = () => {
      refreshSessions({ silent: true })
    }

    window.addEventListener('chat-session-updated', handleSessionUpdated as EventListener)
    window.addEventListener('chat-sessions:refresh', handleRefreshRequest)

    return () => {
      window.removeEventListener('chat-session-updated', handleSessionUpdated as EventListener)
      window.removeEventListener('chat-sessions:refresh', handleRefreshRequest)
    }
  }, [refreshSessions])

  return (
    <Sidebar collapsible="offcanvas" variant="sidebar" side="left" className="border-r h-full">
      <SidebarHeader className="px-3 py-3 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Image src="/agent-sparrow-logo.png" alt="Mailbird" width={22} height={22} className="rounded" />
            <span className="text-sm font-medium group-data-[collapsible=icon]:hidden">Mailbird</span>
          </div>
          {/* Top collapse icon removed by request */}
        </div>
      </SidebarHeader>

      <SidebarContent className="flex-1 px-2 py-2">
        <div className="px-1 pb-2">
          <GradientButton
            size="sm"
            className="w-full justify-center gap-2 text-white"
            onClick={onCreate}
            data-testid="new-chat-button"
          >
            <Plus className="h-4 w-4" /> New Chat
          </GradientButton>
        </div>

        <SidebarSeparator />

        <SidebarGroup>
          <div className="px-2 py-2 text-[11px] uppercase tracking-wider text-muted-foreground/80">Recent</div>
          <SidebarGroupContent>
            <SidebarMenu>
              {loading && (
                <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>
              )}
              {error && (
                <div className="px-3 py-2 text-xs text-destructive">{error}</div>
              )}
              {!loading && sessions.length === 0 && (
                <div className="px-3 py-2 text-xs text-muted-foreground">No conversations yet</div>
              )}
              {sessions.map((s) => {
                // Extract metadata for log analysis sessions
                const isLogAnalysis = s.agent_type === "log_analysis"
                const logMetadata = isLogAnalysis && s.metadata ? s.metadata : null
                const errorCount = logMetadata?.error_count
                const label = s.title?.trim() || (isLogAnalysis
                  ? `Log Analysis${errorCount ? ` - ${errorCount} errors` : ''}`
                  : "Conversation")
                const sessionKey = String(s.id)
                const isActive = sessionKey === sessionId
                return (
                  <SidebarMenuItem key={s.id} className="group/menu-item relative">
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      data-testid={`chat-session-${sessionKey}`}
                      onClick={(e: any) => {
                        e.preventDefault()
                        onSelect(sessionKey)
                      }}
                    >
                      <a href="#" className="gap-2 pr-12">
                        {isLogAnalysis ? (
                          <FolderGit2 className={`h-4 w-4 ${errorCount > 0 ? 'text-orange-500' : ''}`} />
                        ) : (
                          <MessageSquare className="h-4 w-4" />
                        )}
                        {editingId === sessionKey ? (
                          <Input
                            autoFocus
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Escape') setEditingId(null)
                              if (e.key === 'Enter') setEditingId(null)
                            }}
                            onBlur={() => setEditingId(null)}
                            className="h-7 text-sm px-2 py-1"
                          />
                        ) : (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="truncate text-sm max-w-[160px] inline-block align-middle">
                                  {label}
                                </span>
                              </TooltipTrigger>
                              <TooltipContent side="right">
                                <div className="text-xs space-y-1">
                                  <div>{label}</div>
                                  {isLogAnalysis && logMetadata && (
                                    <>
                                      {errorCount !== undefined && (
                                        <div className="text-orange-500">Errors: {errorCount}</div>
                                      )}
                                      {logMetadata.warning_count !== undefined && (
                                        <div className="text-yellow-500">Warnings: {logMetadata.warning_count}</div>
                                      )}
                                      {logMetadata.health_status && (
                                        <div>Status: {logMetadata.health_status}</div>
                                      )}
                                    </>
                                  )}
                                </div>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </a>
                    </SidebarMenuButton>

                    {/* Overflow menu */}
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="absolute right-2 top-1/2 h-6 w-6 -translate-y-1/2 opacity-0 group-hover/menu-item:opacity-100 transition-opacity"
                          title="More actions"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">Actions</span>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" side="right">
                        <DropdownMenuItem
                          onClick={() => {
                            setEditingId(sessionKey)
                            setEditingTitle(label)
                          }}
                        >
                          Rename
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setConfirmDeleteId(sessionKey)}
                        >
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      {/* Confirm delete dialog */}
      <AlertDialog open={!!confirmDeleteId} onOpenChange={(open) => !open && setConfirmDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The conversation will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:opacity-90"
              onClick={async () => {
                const id = confirmDeleteId!
                try {
                  await sessionsAPI.remove(id)
                  setSessions(prev => prev.filter(s => String(s.id) !== String(id)))
                  if (sessionId === String(id)) onSelect(undefined)
                } catch (e) {
                  console.error('Failed to delete session', e)
                } finally {
                  setConfirmDeleteId(null)
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* Bottom-right collapse/expand control */}
      <SidebarFooter className="border-t">
        <div className="w-full flex items-center justify-end">
          <SidebarTrigger className="h-8 w-8" />
        </div>
      </SidebarFooter>
      {/* Rail to re-open when collapsed */}
      <SidebarRail />
    </Sidebar>
  )
}
