'use client'

import React, { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import UnifiedTextCanvas from '@/components/feedme/UnifiedTextCanvas'
import { feedMeApi } from '@/lib/feedme-api'

interface ConversationData {
  id: number
  title: string
  extracted_text?: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  processing_method?: string
  metadata?: {
    folder_id?: number | null
    ai_comment?: string
    content_format?: string
  }
}

export default function ConversationDetailPage() {
  const params = useParams()
  const router = useRouter()
  const conversationId = params?.id ? parseInt(params.id as string) : null

  const [conversation, setConversation] = useState<ConversationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!conversationId) {
      setError('Invalid conversation ID')
      setLoading(false)
      return
    }

    fetchConversation()
  }, [conversationId])

  const fetchConversation = async () => {
    if (!conversationId) return

    try {
      setLoading(true)
      setError(null)

      // Fetch conversation details
      const response = await feedMeApi.getConversationById(conversationId)
      setConversation(response)
    } catch (err) {
      console.error('Failed to fetch conversation:', err)
      setError('Failed to load conversation')
    } finally {
      setLoading(false)
    }
  }

  const handleBack = () => {
    router.back()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !conversation) {
    return (
      <div className="container max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          <h2 className="text-xl font-semibold mb-2">Error Loading Conversation</h2>
          <p className="text-muted-foreground mb-4">
            {error || 'Conversation not found'}
          </p>
          <Button onClick={handleBack} variant="outline">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Go Back
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="container max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <Button
          onClick={handleBack}
          variant="ghost"
          size="sm"
          className="mb-4"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>

        <h1 className="text-2xl font-bold">
          {conversation.title || `Conversation ${conversation.id}`}
        </h1>

        {conversation.processing_method && (
          <p className="text-sm text-muted-foreground mt-1">
            Processed via: {conversation.processing_method === 'pdf_ai' ? 'AI Vision' : 'Text Extraction'}
          </p>
        )}
      </div>

      {conversation.processing_status === 'completed' ? (
        <UnifiedTextCanvas
          conversationId={conversation.id}
          title={conversation.title || `Conversation ${conversation.id}`}
          ticketId={null}
          extractedText={conversation.extracted_text || ''}
          metadata={conversation.metadata}
          processingMetadata={{
            processing_method: conversation.processing_method === 'pdf_ai' ? 'pdf_ocr' : 'text_paste',
            extraction_confidence: 0.95,
          }}
          approvalStatus="approved"
          pdfCleaned={true}
          folderId={conversation.metadata?.folder_id}
          onTextUpdate={async (text) => {
            try {
              await feedMeApi.updateConversation(conversation.id, {
                extracted_text: text,
              })
              // Refresh conversation data
              await fetchConversation()
            } catch (error) {
              console.error('Failed to save conversation:', error)
              throw error
            }
          }}
          readOnly={false}
          showApprovalControls={false}
          fullPageMode={false}
        />
      ) : conversation.processing_status === 'processing' ? (
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500 mb-4" />
          <p className="text-muted-foreground">Processing conversation...</p>
        </div>
      ) : conversation.processing_status === 'failed' ? (
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <AlertCircle className="h-8 w-8 text-red-500 mb-4" />
          <p className="text-muted-foreground">Failed to process conversation</p>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <p className="text-muted-foreground">Conversation is pending processing</p>
        </div>
      )}
    </div>
  )
}