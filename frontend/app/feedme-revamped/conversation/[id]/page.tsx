'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Loader2, AlertCircle, RefreshCcw, CheckCircle2, Clock, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import UnifiedTextCanvas from '@/components/feedme-revamped/UnifiedTextCanvas'
import ConversationSidebar from '@/components/feedme-revamped/ConversationSidebar'
import { ErrorBoundary } from '@/components/feedme-revamped/ErrorBoundary'
import PlatformTagSelector from '@/components/feedme-revamped/PlatformTagSelector'
import { feedMeApi } from '@/lib/feedme-api'
import { useUIStore } from '@/lib/stores/ui-store'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { ConversationDetail, PlatformTag } from '@/types/feedme'

export default function FeedMeConversationPage() {
  const params = useParams()
  const router = useRouter()
  const conversationId = params?.id ? Number(params.id) : null

  const showToast = useUIStore(state => state.actions.showToast)

  const [conversation, setConversation] = useState<ConversationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingFolder, setSavingFolder] = useState(false)
  const [savingNote, setSavingNote] = useState(false)
  const [markingReady, setMarkingReady] = useState(false)

  const aiNote = useMemo(() => conversation?.metadata?.ai_note as string | undefined, [conversation?.metadata])
  const uploadedRelative = useMemo(() => conversation?.created_at ? formatDistanceToNow(new Date(conversation.created_at), { addSuffix: true }) : null, [conversation?.created_at])
  const updatedRelative = useMemo(() => conversation?.updated_at ? formatDistanceToNow(new Date(conversation.updated_at), { addSuffix: true }) : null, [conversation?.updated_at])

  // Not passed to memoized children - no need for useCallback
  const fetchConversation = async () => {
    if (!conversationId) return
    try {
      setLoading(true)
      const detail = await feedMeApi.getConversationById(conversationId)

      // Runtime validation of API response
      if (!detail || typeof detail !== 'object') {
        throw new Error('Invalid conversation data received')
      }
      if (!('id' in detail) || !('title' in detail)) {
        throw new Error('Conversation data missing required fields')
      }

      setConversation(detail as ConversationDetail)
    } catch (error) {
      console.error('Failed to fetch conversation', error)
      showToast({
        type: 'info',
        title: 'Unable to load conversation',
        message: error instanceof Error ? error.message : 'Please try again later',
        duration: 5000
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!conversationId) return
    fetchConversation().catch(() => {})
  }, [conversationId])

  // Simple navigation - no need for useCallback
  const handleBack = () => router.push('/feedme-revamped')

  // Passed to UnifiedTextCanvas but it's not memoized - keep useCallback
  const handleTextUpdate = useCallback(async (text: string) => {
    if (!conversation) return
    try {
      await feedMeApi.updateConversation(conversation.id, { extracted_text: text })
      showToast({ type: 'success', title: 'Canvas saved', message: 'Draft updated successfully', duration: 3000 })
      await fetchConversation()
    } catch (error) {
      console.error('Failed to update text', error)
      showToast({
        type: 'error',
        title: 'Failed to save changes',
        message: error instanceof Error ? error.message : 'Please try again',
        duration: 5000
      })
      throw error // Re-throw to let the UnifiedTextCanvas know the save failed
    }
  }, [conversation, showToast])

  const handleFolderChange = useCallback(async (folderId: number | null) => {
    if (!conversation) return
    try {
      setSavingFolder(true)
      // Directly assign to folder
      await feedMeApi.assignConversationsToFolderSupabase(folderId, [conversation.id])
      setConversation(prev => prev ? {
        ...prev,
        folder_id: folderId
      } : prev)
      showToast({
        type: 'success',
        title: 'Folder updated',
        message: folderId ? 'Conversation moved to folder.' : 'Conversation unassigned.',
        duration: 3000
      })
    } catch (error) {
      console.error('Failed to update folder', error)
      showToast({ type: 'error', title: 'Failed to update folder', message: 'Please try again.', duration: 5000 })
      throw error
    } finally {
      setSavingFolder(false)
    }
  }, [conversation, showToast])

  const handleSaveAiNote = useCallback(async (note: string) => {
    if (!conversation) return
    try {
      setSavingNote(true)
      const metadata = { ...(conversation.metadata || {}), ai_note: note }
      await feedMeApi.updateConversation(conversation.id, { metadata })
      setConversation(prev => prev ? { ...prev, metadata } : prev)
      showToast({ type: 'success', title: 'Note saved', message: 'AI note updated.', duration: 3000 })
    } finally {
      setSavingNote(false)
    }
  }, [conversation, showToast])

  const handleMarkReady = useCallback(async () => {
    if (!conversation) return

    // Check if folder is assigned
    if (!conversation.folder_id) {
      showToast({ type: 'warning', title: 'Assign folder first', message: 'Select a folder before marking ready.', duration: 4000 })
      return
    }

    try {
      setMarkingReady(true)

      // Update metadata: mark as ready for knowledge base
      const metadata = {
        ...(conversation.metadata || {}),
        review_status: 'ready',
        approval_status: 'approved'
      }
      await feedMeApi.updateConversation(conversation.id, { metadata })

      showToast({
        type: 'success',
        title: 'Conversation marked ready',
        message: 'Conversation flagged for knowledge base.',
        duration: 4000
      })
      await fetchConversation()
    } catch (error) {
      console.error('Failed to mark ready', error)
      showToast({ type: 'error', title: 'Failed to update conversation', message: 'Please try again.', duration: 5000 })
    } finally {
      setMarkingReady(false)
    }
  }, [conversation, showToast, fetchConversation])

  const handleTagUpdate = useCallback(async (tags: string[]) => {
    if (!conversation) return

    try {
      const metadata = {
        ...(conversation.metadata || {}),
        tags: tags // Single source of truth - no redundant platform_tag
      }

      await feedMeApi.updateConversation(conversation.id, { metadata })
      setConversation(prev => prev ? { ...prev, metadata } : prev)

      // Extract platform tag for toast message (with correct casing)
      const platformTag = tags.find(t => t.toLowerCase() === 'windows' || t.toLowerCase() === 'macos')
      const displayTag = platformTag ? (platformTag.toLowerCase() === 'macos' ? 'macOS' : 'Windows') : null

      showToast({
        type: 'success',
        title: 'Tags updated',
        message: displayTag
          ? `Platform tag set to ${displayTag}`
          : 'Platform tag cleared',
        duration: 3000
      })
    } catch (error) {
      console.error('Failed to update tags', error)
      showToast({
        type: 'error',
        title: 'Failed to update tags',
        message: error instanceof Error ? error.message : 'Please try again',
        duration: 5000
      })
      throw error
    }
  }, [conversation, showToast])

  if (!conversationId) {
    return (
      <div className="flex h-screen items-center justify-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="ml-3 text-lg">Invalid conversation id.</p>
      </div>
    )
  }

  if (loading && !conversation) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="flex h-screen flex-col items-center justify-center space-y-3">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-sm text-muted-foreground">Conversation not found.</p>
        <Button variant="outline" onClick={handleBack}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back
        </Button>
      </div>
    )
  }

  const canEdit = conversation.processing_status === 'completed'

  // Simple event dispatch - no need for useCallback
  const triggerEdit = () => {
    if (!canEdit || !conversation) return
    document.dispatchEvent(new CustomEvent('feedme:toggle-edit', {
      detail: { conversationId: conversation.id, action: 'start' as const }
    }))
  }

  const statusIcon = conversation.processing_status === 'completed'
    ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    : conversation.processing_status === 'processing'
      ? <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
      : conversation.processing_status === 'failed'
        ? <AlertCircle className="h-4 w-4 text-rose-500" />
        : conversation.processing_status === 'pending'
          ? <Clock className="h-4 w-4 text-amber-500" />
          : <Clock className="h-4 w-4 text-muted-foreground" />

  return (
    <ErrorBoundary>
      <div className="flex h-screen flex-col bg-background">
        <header className="border-b border-border/60 bg-card">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="sm" onClick={handleBack}>
                  <ArrowLeft className="mr-2 h-4 w-4" /> Back
                </Button>
                <div className="space-y-1">
                  <h1 className="text-xl font-semibold leading-tight">{conversation.title || `Conversation ${conversation.id}`}</h1>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1 text-emerald-600">
                      {statusIcon}
                      {conversation.processing_status === 'processing' && conversation.metadata?.processing_tracker?.message ? conversation.metadata.processing_tracker.message : null}
                    </span>
                    {conversation.processing_method && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700">
                        {conversation.processing_method === 'pdf_ai' ? 'AI Vision' : conversation.processing_method.replace(/_/g, ' ')}
                      </span>
                    )}
                    <span className="text-muted-foreground">Conversation #{conversation.id}</span>
                    {uploadedRelative && <span>Uploaded {uploadedRelative}</span>}
                    {updatedRelative && <span>Updated {updatedRelative}</span>}
                    {conversation.uploaded_by && <span>Uploader: {conversation.uploaded_by}</span>}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {canEdit && (
                <PlatformTagSelector
                  conversationId={conversation.id}
                  currentTags={conversation.metadata?.tags || []}
                  onTagUpdate={handleTagUpdate}
                  disabled={conversation.processing_status !== 'completed'}
                />
              )}
              <Button variant="outline" size="sm" onClick={() => fetchConversation()}>
                <RefreshCcw className="mr-2 h-4 w-4" /> Refresh
              </Button>
            </div>
          </div>
          </div>
        </header>

        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="mx-auto grid h-full w-full max-w-6xl grid-cols-1 gap-8 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_360px]">
          <main className="relative min-h-0 overflow-hidden rounded-lg border border-border/60 bg-card shadow-sm">
            {canEdit && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="icon"
                      variant="outline"
                      className="absolute right-4 top-4 z-20 h-8 w-8 rounded-full"
                      onClick={(event) => { event.stopPropagation(); triggerEdit() }}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Edit Canvas</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}

            <div className="h-full overflow-hidden">
              {canEdit ? (
                <UnifiedTextCanvas
                  conversationId={conversation.id}
                  title={conversation.title}
                  ticketId={conversation.metadata?.ticket_id}
                  extractedText={conversation.extracted_text || ''}
                  metadata={conversation.metadata}
                  processingMetadata={{
                    processing_method: (conversation.processing_method || 'pdf_ai') as 'pdf_ocr' | 'manual_text' | 'text_paste',
                    extraction_confidence: conversation.metadata?.extraction_confidence,
                  }}
                  approvalStatus={conversation.approval_status || 'pending'}
                  folderId={conversation.folder_id ?? null}
                  onTextUpdate={handleTextUpdate}
                  readOnly={false}
                  showApprovalControls={false}
                  fullPageMode
                />
              ) : (
                <div className="flex h-full flex-col items-center justify-center space-y-3 text-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    This conversation is still processing. You can edit once processing completes.
                  </p>
                </div>
              )}
            </div>
          </main>

          <aside className={cn('hidden min-h-0 lg:flex')}>
            <ConversationSidebar
              folderId={conversation.folder_id}
              aiNote={aiNote}
              onFolderChange={handleFolderChange}
              onSaveNote={handleSaveAiNote}
              onRegenerateNote={undefined}
              onMarkReady={handleMarkReady}
              isSavingFolder={savingFolder}
              isSavingNote={savingNote}
              isMarkingReady={markingReady}
            />
          </aside>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
