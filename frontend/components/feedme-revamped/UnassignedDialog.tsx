"use client"

import React, { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { CheckCircle2, Clock, Loader2, FileText, X, Maximize2, Trash2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { feedMeApi } from '@/lib/feedme-api'
import { useRouter } from 'next/navigation'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { useUIStore } from '@/lib/stores/ui-store'
import type { ProcessingStageValue } from '@/lib/stores/realtime-store'
import { DialogErrorBoundary } from './DialogErrorBoundary'

// Static constants - defined outside component to prevent recreation
const COLOR_PALETTE = ['#22d3ee', '#f97316', '#38bdf8', '#d946ef', '#4ade80', '#facc15', '#fb7185', '#a855f7', '#2dd4bf', '#f472b6'] as const

type Props = {
  isOpen: boolean
  onClose: () => void
}

type ConversationItem = {
  id: number
  title: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  progress_percentage?: number
  processing_stage?: ProcessingStageValue
  status_message?: string
  created_at: string
  extracted_text?: string
  processing_method?: string
}

export default function UnassignedDialog({ isOpen, onClose }: Props) {
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [originalTitle, setOriginalTitle] = useState('')
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ConversationItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const router = useRouter()
  const showToast = useUIStore(state => state.actions.showToast)

  const fetchUnassignedConversations = async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch conversations with no folder assignment (folder_id = null)
      const response = await feedMeApi.listConversations(1, 100, undefined, undefined, undefined, null)

      // Filter for unassigned conversations (null or undefined folder_id)
      const unassigned = response.conversations.filter((conv: any) =>
        conv.folder_id === null || conv.folder_id === undefined
      )

      const enriched = (unassigned as ConversationItem[]).map(conv => {
        const tracker = (conv as any)?.metadata?.processing_tracker || {}
        const progress = typeof tracker.progress === 'number'
          ? tracker.progress
          : conv.processing_status === 'completed'
            ? 100
            : conv.processing_status === 'failed'
              ? 100
              : undefined
        const stage = tracker.stage as ConversationItem['processing_stage']
        const statusMessage = tracker.message as string | undefined
        return {
          ...conv,
          progress_percentage: progress,
          processing_stage: stage,
          status_message: statusMessage || undefined,
        }
      })

      setConversations(enriched)
    } catch (err) {
      console.error('Failed to fetch unassigned conversations:', err)
      setError('Failed to load unassigned conversations')
    } finally {
      setLoading(false)
    }
  }

  // Simplified polling - one interval, one abort controller, clean cleanup
  useEffect(() => {
    if (!isOpen) return

    const abortController = new AbortController()
    let intervalId: NodeJS.Timeout | null = null

    const fetchConversations = async () => {
      try {
        const response = await feedMeApi.listConversations(1, 100, undefined, undefined, undefined, null)

        if (abortController.signal.aborted) return

        // Filter for unassigned conversations
        const unassigned = response.conversations.filter((conv: any) =>
          conv.folder_id === null || conv.folder_id === undefined
        )

        const enriched = unassigned.map(conv => {
          const tracker = (conv as any)?.metadata?.processing_tracker || {}
          const progress = typeof tracker.progress === 'number'
            ? tracker.progress
            : conv.processing_status === 'completed' || conv.processing_status === 'failed'
              ? 100
              : undefined
          const stage = tracker.stage as ConversationItem['processing_stage']
          const statusMessage = tracker.message as string | undefined
          return {
            ...conv,
            progress_percentage: progress,
            processing_stage: stage,
            status_message: statusMessage || undefined,
          } as ConversationItem
        })

        setConversations(enriched)

        // Check if we need to continue polling
        const needsPolling = enriched.some(
          conv => conv.processing_status === 'processing' || conv.processing_status === 'pending'
        )

        // Set up or clear polling
        if (needsPolling && !intervalId) {
          intervalId = setInterval(fetchConversations, 5000)
        } else if (!needsPolling && intervalId) {
          clearInterval(intervalId)
          intervalId = null
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        console.error('Failed to fetch unassigned conversations:', err)
        setError('Failed to load unassigned conversations')
      }
    }

    // Initial fetch
    fetchConversations()

    // Cleanup
    return () => {
      abortController.abort()
      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  }, [isOpen])

  const getStatusIcon = (status: string, progress?: number) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case 'processing':
        return (
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-green-500" />
            {progress !== undefined && (
              <span className="text-xs text-green-500 font-medium">{progress}%</span>
            )}
          </div>
        )
      case 'pending':
        return <Clock className="h-4 w-4 text-yellow-500" />
      case 'failed':
        return <X className="h-4 w-4 text-red-500" />
      case 'cancelled':
        return <FileText className="h-4 w-4 text-muted-foreground" />
      default:
        return <FileText className="h-4 w-4 text-muted-foreground" />
    }
  }

  const handleConversationClick = useCallback((conversationId: number) => {
    router.push(`/feedme-revamped/conversation/${conversationId}`)
    onClose()
  }, [router, onClose])

  const startEditingTitle = useCallback((conversation: ConversationItem) => {
    setEditingId(conversation.id)
    setTitleDraft(conversation.title || `Conversation ${conversation.id}`)
    setOriginalTitle(conversation.title || '')
  }, [])

  const resetEditing = useCallback(() => {
    setEditingId(null)
    setTitleDraft('')
    setOriginalTitle('')
    setRenamingId(null)
  }, [])

  const commitTitleChange = useCallback(async (conversation: ConversationItem) => {
    if (!editingId) return
    const trimmed = titleDraft.trim()
    if (!trimmed || trimmed === originalTitle) {
      resetEditing()
      return
    }
    setRenamingId(conversation.id)
    try {
      await feedMeApi.updateConversation(conversation.id, { title: trimmed })
      setConversations(prev => prev.map(item => item.id === conversation.id ? { ...item, title: trimmed } : item))
      showToast({ type: 'success', title: 'Title updated', message: 'Conversation name saved.', duration: 3000 })
    } catch (error) {
      console.error('Failed to rename conversation', error)
      showToast({ type: 'error', title: 'Rename failed', message: 'Please try again.', duration: 4000 })
      setTitleDraft(originalTitle)
    } finally {
      resetEditing()
    }
  }, [editingId, titleDraft, originalTitle, resetEditing, showToast])

  const handleDeleteConversation = useCallback(async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await feedMeApi.deleteConversation(deleteTarget.id)
      setConversations(prev => prev.filter(conv => conv.id !== deleteTarget.id))
      showToast({ type: 'success', title: 'Conversation deleted', message: 'The conversation has been removed.', duration: 4000 })
    } catch (error) {
      console.error('Failed to delete conversation', error)
      showToast({ type: 'error', title: 'Delete failed', message: 'Please try again.', duration: 5000 })
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }, [deleteTarget, showToast])

  const formatDate = useCallback((dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }, [])

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[900px] w-[900px] p-0 overflow-hidden">
        <DialogErrorBoundary fallbackTitle="Failed to load unassigned conversations" onReset={fetchUnassignedConversations}>
        <DialogHeader className="px-6 pt-6 pb-3">
          <DialogTitle>Unassigned</DialogTitle>
        </DialogHeader>
        <Separator />

        <section className="p-6 max-h-[600px] overflow-auto">
          {loading && conversations.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-sm text-muted-foreground">{error}</p>
              <Button variant="outline" size="sm" onClick={fetchUnassignedConversations} className="mt-4">
                Retry
              </Button>
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">No unassigned conversations</p>
              <p className="text-xs text-muted-foreground mt-2">
                Uploaded PDFs will appear here until assigned to a folder
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 overflow-x-auto">
              {conversations.map((conv, index) => {
                const iconColor = COLOR_PALETTE[index % COLOR_PALETTE.length]
                const isEditing = editingId === conv.id
                const isRenaming = renamingId === conv.id
                return (
                <div
                  key={conv.id}
                  className="group relative rounded-lg border bg-card/50 hover:bg-card transition-all cursor-pointer p-4"
                  onClick={() => handleConversationClick(conv.id)}
                >
                  <button
                    onClick={(event) => { event.stopPropagation(); setDeleteTarget(conv) }}
                    className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-background/90 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive z-10"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>

                  <div className="flex flex-col h-full pr-10">
                    {/* Header with icon and title */}
                    <div className="flex items-start gap-3 mb-3">
                      <FileText className="h-5 w-5 flex-shrink-0 mt-0.5" style={{ color: iconColor }} />
                      <div className="flex-1 min-w-0">
                        {isEditing ? (
                          <Input
                            value={titleDraft}
                            onChange={event => setTitleDraft(event.target.value)}
                            onClick={event => event.stopPropagation()}
                            onBlur={() => commitTitleChange(conv)}
                            onKeyDown={event => {
                              if (event.key === 'Enter') {
                                event.preventDefault()
                                commitTitleChange(conv).catch(() => {})
                              } else if (event.key === 'Escape') {
                                event.preventDefault()
                                resetEditing()
                              }
                            }}
                            disabled={isRenaming}
                            autoFocus
                            className="h-8 text-sm"
                          />
                        ) : (
                          <h4
                            className="font-medium text-sm line-clamp-2"
                            onDoubleClick={(event) => { event.stopPropagation(); startEditingTitle(conv) }}
                          >
                            {conv.title || `Conversation ${conv.id}`}
                          </h4>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">
                          {formatDate(conv.created_at)}
                        </p>
                      </div>
                    </div>

                    {/* Status section */}
                    <div className="flex items-center justify-between mt-auto">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        {getStatusIcon(conv.processing_status, conv.progress_percentage)}
                        {conv.processing_status === 'processing' && conv.status_message && (
                          <span className="text-xs text-muted-foreground">
                            {conv.status_message}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Progress bar for processing conversations */}
                    {conv.processing_status === 'processing' && conv.progress_percentage !== undefined && (
                      <div className="mt-3">
                        <div className="w-full bg-emerald-600/20 rounded-full h-1.5">
                          <div
                            className="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
                            style={{ width: `${Math.min(Math.max(conv.progress_percentage, 0), 100)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {conv.status_message && conv.processing_status !== 'processing' && (
                      <p className="mt-2 text-[11px] text-muted-foreground">{conv.status_message}</p>
                    )}

                    <button
                      className="absolute bottom-2 right-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-background/90 text-muted-foreground opacity-0 shadow-sm transition-opacity group-hover:opacity-100 hover:bg-accent hover:text-accent-foreground z-10"
                      onClick={(event) => { event.stopPropagation(); handleConversationClick(conv.id) }}
                      aria-label="Open conversation"
                    >
                      <Maximize2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              )})}
            </div>
          )}
        </section>
        </DialogErrorBoundary>
      </DialogContent>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && !isDeleting && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The conversation and its processed data will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting} onClick={() => setDeleteTarget(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteConversation} disabled={isDeleting} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  )
}
