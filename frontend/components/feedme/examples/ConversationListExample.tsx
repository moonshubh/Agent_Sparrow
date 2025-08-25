/**
 * Example: Conversation List Component using Modular Stores
 * 
 * This example demonstrates best practices for using the modular stores
 * without any legacy dependencies.
 */

'use client'

import React, { useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { FileText, Clock, CheckCircle, XCircle } from 'lucide-react'

// Import specific hooks from modular stores - NO legacy imports
import { 
  useConversations,
  useConversationsActions,
  useConversationSelection
} from '@/lib/stores/conversations-store'
import { useRealtimeActions } from '@/lib/stores/realtime-store'
import { useUIActions } from '@/lib/stores/ui-store'

export function ConversationListExample() {
  // Use specific store hooks
  const conversations = useConversations()
  const { selectedIds, isMultiSelectMode } = useConversationSelection()
  const conversationActions = useConversationsActions()
  const realtimeActions = useRealtimeActions()
  const uiActions = useUIActions()

  // Initialize data on mount
  useEffect(() => {
    conversationActions.loadConversations({ page: 1, pageSize: 20 })
    realtimeActions.connect() // Auto-reconnecting WebSocket
  }, [])

  // Handle conversation selection
  const handleSelect = (id: number) => {
    if (isMultiSelectMode) {
      conversationActions.selectConversation(id, !selectedIds.has(id))
    } else {
      uiActions.openModal('conversation-detail', { conversationId: id })
    }
  }

  if (conversations.isLoading && conversations.items.length === 0) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-[250px]" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-4 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {conversations.items.map(conversation => (
        <Card 
          key={conversation.id}
          className="cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => handleSelect(conversation.id || conversation.conversation_id || 0)}
        >
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4" />
                {conversation.title}
              </CardTitle>
              <Badge variant={
                conversation.processing_status === 'completed' ? 'default' :
                conversation.processing_status === 'failed' ? 'destructive' :
                conversation.processing_status === 'processing' ? 'secondary' :
                'outline'
              }>
                {conversation.processing_status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground line-clamp-2">
              {(conversation as any).raw_transcript?.substring(0, 150) || 
               conversation.metadata?.preview?.substring(0, 150) || 
               'No preview available'}...
            </p>
            <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              {conversation.created_at ? new Date(conversation.created_at).toLocaleDateString() : 'Unknown date'}
              {conversation.total_examples && (
                <span className="ml-auto">{conversation.total_examples} examples</span>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
