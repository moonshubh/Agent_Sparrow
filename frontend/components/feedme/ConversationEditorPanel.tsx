/**
 * ConversationEditorPanel
 * Fetches the selected conversation and renders the UnifiedTextCanvas
 */

'use client'

import React, { useEffect, useState } from 'react'
import { useUIPanels, useUIActions } from '@/lib/stores/ui-store'
import { feedMeApi } from '@/lib/feedme-api'
// Outer page scroll handles content; no inner scroll area needed
import { Loader2 } from 'lucide-react'
import {
  SidebarProvider,
  SidebarInset,
} from '@/components/ui/sidebar'
import ConversationInfoSidebar from './ConversationInfoSidebar'
import { UnifiedTextCanvas } from './UnifiedTextCanvas'

interface ConversationRecord {
  id: number
  title: string
  extracted_text?: string | null
  processing_method?: string
  extraction_confidence?: number | null
  processing_time_ms?: number | null
  quality_metrics?: Record<string, number> | null
  extraction_method?: string | null
  warnings?: string[] | null
  approval_status: 'pending' | 'approved' | 'rejected' | 'processed' | 'published'
  approved_by?: string | null
  approved_at?: string | null
  metadata?: Record<string, any> | null
  folder_id?: number | null
}

export function ConversationEditorPanel() {
  const { selectedConversationId } = useUIPanels()
  const ui = useUIActions()
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [conversation, setConversation] = useState<ConversationRecord | null>(null)

  useEffect(() => {
    const load = async () => {
      if (!selectedConversationId) return
      setLoading(true)
      setError(null)
      try {
        const data = await feedMeApi.getConversation(selectedConversationId)
        setConversation(data as unknown as ConversationRecord)
      } catch (e: any) {
        console.warn('Editor: service unreachable; skipping conversation fetch')
        setError(e?.message || 'Failed to load conversation')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [selectedConversationId])

  if (!selectedConversationId) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground">
        <div className="text-center">
          <p className="text-lg font-medium">Select a conversation</p>
          <p className="text-sm mt-1">Choose a conversation from the list to view and edit its content</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        Loading conversation...
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 text-red-600">{error}</div>
    )
  }

  if (!conversation) return null

  const procMeta = {
    processing_method: (conversation.processing_method as any) || 'pdf_ocr',
    extraction_confidence: conversation.extraction_confidence ?? undefined,
    processing_time_ms: conversation.processing_time_ms ?? undefined,
    quality_metrics: conversation.quality_metrics ?? undefined,
    extraction_method: conversation.extraction_method ?? undefined,
    warnings: conversation.warnings ?? undefined,
  }

  return (
    <SidebarProvider defaultOpen>
      <ConversationInfoSidebar
        side="right"
        conversationId={conversation.id}
        title={conversation.title}
        processingMethod={conversation.processing_method as any}
        extractionConfidence={conversation.extraction_confidence ?? null}
        approvalStatus={conversation.approval_status as any}
        extractedText={conversation.extracted_text || ''}
        folderId={conversation.folder_id ?? null}
        onTitleChange={(t) => setConversation(c => c ? { ...c, title: t } : c)}
      />
      
      <SidebarInset className="h-svh overflow-hidden">
        <div className="h-full overflow-auto p-4">
          <UnifiedTextCanvas
                conversationId={conversation.id}
                title={conversation.title}
                extractedText={conversation.extracted_text || ''}
                metadata={conversation.metadata || null}
                processingMetadata={procMeta as any}
                approvalStatus={(conversation.approval_status as any) || 'pending'}
                approvedBy={conversation.approved_by || undefined}
                approvedAt={conversation.approved_at || undefined}
                folderId={conversation.folder_id ?? null}
                readOnly={false}
                showApprovalControls={conversation.approval_status === 'pending'}
          />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default ConversationEditorPanel
