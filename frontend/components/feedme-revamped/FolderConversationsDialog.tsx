"use client"

import React, { useEffect, useState, useRef, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { CheckCircle2, Clock, Loader2, FileText, X, RefreshCw, Trash2, AlertCircle, ArrowLeft } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { feedMeApi } from '@/lib/feedme-api'
import { useRouter } from 'next/navigation'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { useUIStore } from '@/lib/stores/ui-store'
import { formatDistanceToNow } from 'date-fns'
import { cn } from '@/lib/utils'
import type { ProcessingStageValue } from '@/lib/stores/realtime-store'
import { DialogErrorBoundary } from './DialogErrorBoundary'

// Constants
const MAX_CONVERSATIONS_PER_PAGE = 100

interface Props {
  isOpen: boolean
  onClose: () => void
  folderId: number
  folderName: string
  folderColor?: string
}

interface ConversationItem {
  id: number
  title: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  progress_percentage?: number
  processing_stage?: ProcessingStageValue
  status_message?: string
  created_at: string
  updated_at?: string
  extracted_text?: string
  processing_method?: string
  metadata?: Record<string, unknown>
  folder_id: number | null
}

const FolderConversationsDialog = React.memo(function FolderConversationsDialog({ isOpen, onClose, folderId, folderName, folderColor = '#6b7280' }: Props) {
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [originalTitle, setOriginalTitle] = useState('')
  const [isRenaming, setIsRenaming] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ConversationItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [hasFetchedData, setHasFetchedData] = useState(false)
  const router = useRouter()
  const showToast = useUIStore(state => state.actions.showToast)
  const renameInputRef = useRef<HTMLInputElement | null>(null)

  const fetchFolderConversations = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch conversations for this specific folder
      const response = await feedMeApi.listConversations(1, MAX_CONVERSATIONS_PER_PAGE, undefined, undefined, undefined, folderId)

      // API already filters by folderId, no need for client-side filtering
      interface ProcessingTracker {
        progress?: number
        stage?: ProcessingStageValue
        message?: string
      }

      const enriched = response.conversations.map(conv => {
        const metadata = conv.metadata as { processing_tracker?: ProcessingTracker } | undefined
        const tracker = metadata?.processing_tracker || {}
        const progress = typeof tracker.progress === 'number'
          ? tracker.progress
          : conv.processing_status === 'completed'
            ? 100
            : conv.processing_status === 'failed'
              ? 100
              : undefined
        const stage = tracker.stage
        const statusMessage = tracker.message
        return {
          ...conv,
          progress_percentage: progress,
          processing_stage: stage,
          status_message: statusMessage || undefined,
        } as ConversationItem
      })

      setConversations(enriched)
    } catch (err) {
      console.error('Failed to fetch folder conversations:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to load conversations'
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }, [folderId])

  // Fetch conversations when dialog opens
  useEffect(() => {
    if (!isOpen || !folderId) {
      setHasFetchedData(false)
      return
    }

    // Only fetch if we haven't fetched for this dialog session
    if (!hasFetchedData) {
      fetchFolderConversations()
      setHasFetchedData(true)
    }
  }, [isOpen, folderId, fetchFolderConversations, hasFetchedData])

  // Focus rename input when editing starts
  useEffect(() => {
    if (editingId && renameInputRef.current) {
      requestAnimationFrame(() => {
        renameInputRef.current?.focus()
        renameInputRef.current?.select()
      })
    }
  }, [editingId])

  const handleOpenConversation = useCallback((conversationId: number) => {
    router.push(`/feedme-revamped/conversation/${conversationId}`)
    onClose()
  }, [router, onClose])

  const startRename = useCallback((conv: ConversationItem) => {
    setEditingId(conv.id)
    setTitleDraft(conv.title)
    setOriginalTitle(conv.title)
  }, [])

  const cancelRename = useCallback(() => {
    setEditingId(null)
    setTitleDraft('')
    setOriginalTitle('')
  }, [])

  const commitRename = useCallback(async () => {
    if (editingId === null || isRenaming) return

    const conv = conversations.find(c => c.id === editingId)
    if (!conv) {
      cancelRename()
      return
    }

    const trimmed = titleDraft.trim()
    if (!trimmed || trimmed === originalTitle) {
      cancelRename()
      return
    }

    setIsRenaming(true)
    try {
      await feedMeApi.updateConversation(editingId, { title: trimmed })
      setConversations(prev => prev.map(c => c.id === editingId ? { ...c, title: trimmed } : c))
      showToast({
        title: 'Conversation renamed',
        description: `Updated to "${trimmed}"`,
        duration: 3000,
      })
      cancelRename()
    } catch (error) {
      console.error('Failed to rename conversation:', error)
      showToast({
        title: 'Rename failed',
        description: 'Could not rename the conversation. Please try again.',
        duration: 4000,
      })
      setTitleDraft(originalTitle)
    } finally {
      setIsRenaming(false)
    }
  }, [editingId, titleDraft, originalTitle, isRenaming, conversations, cancelRename, showToast])

  const handleDelete = useCallback((conv: ConversationItem) => {
    setDeleteTarget(conv)
  }, [])

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return

    setIsDeleting(true)
    try {
      await feedMeApi.deleteConversation(deleteTarget.id)
      setConversations(prev => prev.filter(c => c.id !== deleteTarget.id))
      showToast({
        title: 'Conversation deleted',
        description: `"${deleteTarget.title}" has been removed`,
        duration: 3000,
      })
    } catch (error) {
      console.error('Failed to delete conversation:', error)
      showToast({
        title: 'Delete failed',
        description: 'Could not delete the conversation. Please try again.',
        duration: 4000,
      })
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }, [deleteTarget, showToast])

  const getStatusIcon = useCallback((status: ConversationItem['processing_status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-600" />
      case 'processing':
        return <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
      case 'failed':
        return <X className="h-4 w-4 text-red-600" />
      case 'pending':
      default:
        return <Clock className="h-4 w-4 text-amber-600" />
    }
  }, [])

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="max-w-[900px] w-[900px] p-0 overflow-hidden">
          <DialogErrorBoundary fallbackTitle="Failed to load folder conversations" onReset={fetchFolderConversations}>
          <DialogHeader className="flex flex-row items-center justify-between px-6 pt-6 pb-3 space-y-0">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={onClose}
                aria-label="Go back to folders"
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div
                className="h-3 w-3 rounded-full"
                style={{ backgroundColor: folderColor }}
              />
              <DialogTitle className="font-semibold">
                {folderName}
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  ({conversations.length} conversation{conversations.length !== 1 ? 's' : ''})
                </span>
              </DialogTitle>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchFolderConversations}
              disabled={loading}
              aria-label="Refresh conversations"
            >
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
              <span className="ml-2">Refresh</span>
            </Button>
          </DialogHeader>

          <Separator />

          <ScrollArea className="h-[500px]">
            <div className="p-6">
              {loading && conversations.length === 0 && (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}

              {error && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 text-destructive" />
                    <p className="text-sm text-destructive">{error}</p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={fetchFolderConversations}
                  >
                    Try Again
                  </Button>
                </div>
              )}

              {!loading && !error && conversations.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <FileText className="h-12 w-12 text-muted-foreground/30 mb-4" />
                  <p className="text-sm text-muted-foreground">No conversations in this folder yet.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Assign conversations from the Unassigned view or Canvas sidebar.
                  </p>
                </div>
              )}

              {!loading && conversations.length > 0 && (
                <ul className="space-y-2">
                  {conversations.map(conv => {
                    const isEditing = editingId === conv.id
                    const createdRelative = formatDistanceToNow(new Date(conv.created_at), { addSuffix: true })

                    return (
                      <li
                        key={conv.id}
                        className="group relative flex items-center gap-3 rounded-lg border border-border/40 bg-background/70 p-4 transition hover:border-border hover:bg-accent/5"
                        role="article"
                        aria-label={`Conversation: ${conv.title}`}
                      >
                        <div className="flex-shrink-0">
                          {getStatusIcon(conv.processing_status)}
                        </div>

                        <div className="flex-1 min-w-0">
                          {isEditing ? (
                            <Input
                              ref={renameInputRef}
                              value={titleDraft}
                              onChange={e => setTitleDraft(e.target.value)}
                              onBlur={commitRename}
                              onKeyDown={e => {
                                if (e.key === 'Enter') {
                                  e.preventDefault()
                                  void commitRename()
                                } else if (e.key === 'Escape') {
                                  e.preventDefault()
                                  cancelRename()
                                }
                              }}
                              className="h-7 text-sm"
                              disabled={isRenaming}
                              aria-label="Edit conversation title"
                            />
                          ) : (
                            <div
                              className="cursor-pointer"
                              onClick={() => handleOpenConversation(conv.id)}
                              onDoubleClick={() => startRename(conv)}
                            >
                              <h4 className="text-sm font-medium truncate hover:text-primary transition-colors">
                                {conv.title || `Conversation ${conv.id}`}
                              </h4>
                            </div>
                          )}

                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-xs text-muted-foreground">
                              Created {createdRelative}
                            </span>
                            {conv.processing_method && (
                              <span className="text-xs text-muted-foreground">
                                • {conv.processing_method.replace(/_/g, ' ')}
                              </span>
                            )}
                            {conv.progress_percentage !== undefined && conv.processing_status === 'processing' && (
                              <span className="text-xs text-blue-600">
                                • {conv.progress_percentage}%
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDelete(conv)
                            }}
                            aria-label={`Delete conversation ${conv.title}`}
                          >
                            <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                          </Button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </ScrollArea>
          </DialogErrorBoundary>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.title}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
})

export default FolderConversationsDialog