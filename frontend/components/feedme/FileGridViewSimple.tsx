/**
 * FileGridView - Simplified Version
 * Grid layout for displaying conversations with basic functionality
 */

'use client'

import React, { useEffect } from 'react'
import { FileText, Clock, User, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { useConversations, useActions } from '@/lib/stores/feedme-store'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { formatDistanceToNow } from 'date-fns'

interface FileGridViewProps {
  onConversationSelect?: (conversationId: number) => void
  className?: string
}

const StatusIcon = ({ status }: { status: string }) => {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case 'processing':
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
    case 'failed':
      return <AlertCircle className="h-4 w-4 text-red-500" />
    default:
      return <Clock className="h-4 w-4 text-yellow-500" />
  }
}

export function FileGridView({ onConversationSelect, className }: FileGridViewProps) {
  const { items: conversations, isLoading } = useConversations()
  const actions = useActions()

  useEffect(() => {
    // Load conversations on mount
    actions.loadConversations()
  }, [actions])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading conversations...</span>
      </div>
    )
  }

  if (conversations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <FileText className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="text-lg font-medium">No conversations yet</h3>
        <p className="text-muted-foreground">Upload your first transcript to get started</p>
        <Button className="mt-4" onClick={() => actions.setActiveTab('upload')}>
          Upload Transcript
        </Button>
      </div>
    )
  }

  return (
    <ScrollArea className={className}>
      <div className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {conversations.map((conversation) => (
            <Card 
              key={conversation.id} 
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => onConversationSelect?.(conversation.id)}
            >
              <CardHeader className="pb-3">
                <CardTitle className="text-sm line-clamp-2 h-10">
                  {conversation.title}
                </CardTitle>
                <div className="flex items-center gap-2">
                  <StatusIcon status={conversation.processing_status} />
                  <Badge variant="secondary" className="text-xs">
                    {conversation.processing_status}
                  </Badge>
                </div>
              </CardHeader>
              
              <CardContent className="pt-0">
                <div className="space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    <span>{conversation.total_examples} examples</span>
                  </div>
                  
                  <div className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>
                      {conversation.created_at && 
                        formatDistanceToNow(new Date(conversation.created_at), { addSuffix: true })
                      }
                    </span>
                  </div>
                  
                  {conversation.metadata?.uploaded_by && (
                    <div className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      <span>{conversation.metadata.uploaded_by}</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </ScrollArea>
  )
}