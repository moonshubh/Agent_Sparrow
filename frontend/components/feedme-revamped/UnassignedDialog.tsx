"use client"

import React, { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { CheckCircle2, Clock, Loader2, FileText, X } from 'lucide-react'
import { feedMeApi } from '@/lib/feedme-api'
import { useRouter } from 'next/navigation'
import type { ProcessingStageValue } from '@/lib/stores/realtime-store'

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
  const router = useRouter()

  const fetchUnassignedConversations = async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch conversations with no folder assignment (folder_id = null)
      const response = await feedMeApi.listConversations(1, 100, undefined, undefined, undefined, null)

      // Filter for unassigned conversations (null or undefined folder_id)
      const unassigned = response.conversations.filter(conv =>
        !conv.metadata?.folder_id || conv.metadata?.folder_id === null
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

  // Fetch conversations when dialog opens with smart polling
  useEffect(() => {
    if (!isOpen) return

    let intervalId: NodeJS.Timeout | null = null
    let mounted = true

    const fetchWithErrorHandling = async () => {
      if (!mounted) return
      try {
        await fetchUnassignedConversations()
      } catch (err) {
        console.error('Failed to fetch unassigned conversations:', err)
      }
    }

    // Initial fetch
    fetchWithErrorHandling()

    // Only poll if there are processing conversations
    const setupPolling = () => {
      // Check if we have any processing conversations
      const hasProcessing = conversations.some(
        conv => conv.processing_status === 'processing' || conv.processing_status === 'pending'
      )

      if (hasProcessing && mounted) {
        intervalId = setInterval(fetchWithErrorHandling, 5000)
      }
    }

    // Set up polling after initial data loads
    const timeout = setTimeout(setupPolling, 1000)

    return () => {
      mounted = false
      if (intervalId) clearInterval(intervalId)
      clearTimeout(timeout)
    }
  }, [isOpen, conversations])

  const getStatusIcon = (status: string, progress?: number) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case 'processing':
        return (
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
            {progress !== undefined && (
              <span className="text-xs text-muted-foreground">{progress}%</span>
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

  const handleConversationClick = (conversationId: number) => {
    // Navigate to the conversation detail page
    router.push(`/feedme/conversation/${conversationId}`)
    onClose()
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // Render progress bar for processing conversations
  const renderProgressBar = (progress: number) => {
    return (
      <div className="w-full bg-secondary/30 rounded-full h-1.5 mt-2">
        <div
          className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>
    )
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[900px] w-[900px] p-0 overflow-hidden">
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
            <div className="grid grid-cols-2 gap-4 overflow-x-auto">
              {conversations.map(conv => (
                <div
                  key={conv.id}
                  className="group relative rounded-lg border bg-card/50 hover:bg-card transition-all cursor-pointer p-4 min-w-[350px]"
                  onClick={() => handleConversationClick(conv.id)}
                >
                  <div className="flex flex-col h-full">
                    {/* Header with icon and title */}
                    <div className="flex items-start gap-3 mb-3">
                      <FileText className="h-5 w-5 text-muted-foreground flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-sm line-clamp-2">
                          {conv.title || `Conversation ${conv.id}`}
                        </h4>
                        <p className="text-xs text-muted-foreground mt-1">
                          {formatDate(conv.created_at)}
                        </p>
                      </div>
                    </div>

                    {/* Status section */}
                    <div className="flex items-center justify-between mt-auto">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(conv.processing_status, conv.progress_percentage)}
                        {conv.processing_status === 'completed' && (
                          <span className="text-xs text-green-600 font-medium">Processed</span>
                        )}
                        {conv.processing_status === 'processing' && (
                          <span className="text-xs text-blue-600 font-medium">
                            {conv.status_message || 'Processing'}
                          </span>
                        )}
                        {conv.processing_status === 'pending' && (
                          <span className="text-xs text-yellow-600 font-medium">
                            {conv.status_message || 'Pending'}
                          </span>
                        )}
                        {conv.processing_status === 'failed' && (
                          <span className="text-xs text-red-600 font-medium">
                            {conv.status_message || 'Failed'}
                          </span>
                        )}
                        {conv.processing_status === 'cancelled' && (
                          <span className="text-xs text-muted-foreground font-medium">
                            {conv.status_message || 'Cancelled'}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Progress bar for processing conversations */}
                    {conv.processing_status === 'processing' && conv.progress_percentage !== undefined && (
                      <div className="mt-3">
                        {renderProgressBar(conv.progress_percentage)}
                      </div>
                    )}

                    {/* Show extraction method if available */}
                    {conv.processing_method && conv.processing_status === 'completed' && (
                      <div className="mt-3 pt-3 border-t">
                        <span className="text-xs text-muted-foreground">
                          Method: {conv.processing_method === 'pdf_ai' ? 'AI Vision' : 'Text Extraction'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </DialogContent>
    </Dialog>
  )
}
