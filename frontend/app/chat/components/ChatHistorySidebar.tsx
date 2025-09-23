"use client"

import React, { useEffect, useMemo, useState } from "react"
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

export function ChatHistorySidebar({ sessionId, onSelect }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState<string>("")
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [renameTimer, setRenameTimer] = useState<NodeJS.Timeout | null>(null)

  useEffect(() => {
    let mounted = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        // Load the most recent 10 sessions
        const items = await sessionsAPI.list(10, 0)
        if (!mounted) return
        setSessions(items.slice(0, 10))
      } catch (e: any) {
        if (!mounted) return
        setError(e?.message || "Failed to load sessions")
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [])

  const onCreate = async () => {
    try {
      const s = await sessionsAPI.create("primary")
      setSessions(prev => [s, ...prev].slice(0, 10))
      onSelect(s.id)
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
        setSessions(prev => prev.map(s => (s.id === editingId ? updated : s)))
      } catch (e) {
        console.error('Failed to rename session', e)
      }
    }, 500)
    setRenameTimer(t)
    return () => clearTimeout(t)
  }, [editingId, editingTitle])

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
          <Button size="sm" className="w-full justify-center gap-2" onClick={onCreate}>
            <Plus className="h-4 w-4" /> New Chat
          </Button>
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
                const label = s.title?.trim() || (s.agent_type === "log_analysis" ? "Log analysis session" : "Conversation")
                const isActive = s.id === sessionId
                return (
                  <SidebarMenuItem key={s.id} className="group/menu-item">
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      onClick={(e: any) => {
                        e.preventDefault()
                        onSelect(s.id)
                      }}
                    >
                      <a href="#" className="gap-2 pr-8">
                        {s.agent_type === "log_analysis" ? (
                          <FolderGit2 className="h-4 w-4" />
                        ) : (
                          <MessageSquare className="h-4 w-4" />
                        )}
                        {editingId === s.id ? (
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
                                <span className="text-xs">{label}</span>
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
                          className="absolute right-1 h-6 w-6 opacity-0 group-hover/menu-item:opacity-100 transition-opacity"
                          title="More actions"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                          <span className="sr-only">Actions</span>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" side="right">
                        <DropdownMenuItem
                          onClick={() => {
                            setEditingId(s.id)
                            setEditingTitle(label)
                          }}
                        >
                          Rename
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setConfirmDeleteId(s.id)}
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
                  setSessions(prev => prev.filter(s => s.id !== id))
                  if (sessionId === id) onSelect(undefined)
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
