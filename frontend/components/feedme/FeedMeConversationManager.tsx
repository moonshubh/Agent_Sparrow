/**
 * Updated FeedMe Conversation Manager
 * Main interface for managing conversations with unified text canvas
 * 
 * Updated Features:
 * - Unified text canvas display (replaces Q&A sections)
 * - PDF OCR and manual text processing
 * - Human approval workflow integration
 * - Processing method indicators
 * - Enhanced search and filtering
 */

'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useDebounce } from 'use-debounce'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  Plus, 
  Search, 
  Filter, 
  Edit3, 
  Clock, 
  User, 
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  Trash2,
  Folder,
  Settings,
  Move,
  Bot,
  Sparkles,
  Eye,
  X
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import UnifiedTextCanvas from './UnifiedTextCanvas'

// Updated types for unified text workflow
interface ConversationData {
  id: number
  title: string
  extracted_text?: string
  raw_transcript?: string
  processing_method: 'pdf_ocr' | 'manual_text' | 'text_paste'
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  approval_status: 'pending' | 'approved' | 'rejected'
  extraction_confidence?: number
  processing_time_ms?: number
  quality_metrics?: Record<string, number>
  extraction_method?: string
  warnings?: string[]
  approved_by?: string
  approved_at?: string
  created_at: string
  updated_at: string
  uploaded_by?: string
}

interface ConversationCardProps {
  conversation: ConversationData
  onView: (conversation: ConversationData) => void
  onDelete: (conversation: ConversationData) => void
  onRefresh: () => void
}

function ConversationCard({ conversation, onView, onDelete, onRefresh }: ConversationCardProps) {
  const formatTimestamp = (timestamp: string) => {
    try {
      return formatDistanceToNow(new Date(timestamp), { addSuffix: true })
    } catch {
      return timestamp
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-50 border-green-200'
      case 'processing': return 'text-blue-600 bg-blue-50 border-blue-200'
      case 'failed': return 'text-red-600 bg-red-50 border-red-200'
      default: return 'text-yellow-600 bg-yellow-50 border-yellow-200'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle2 className="h-3 w-3" />
      case 'processing': return <Loader2 className="h-3 w-3 animate-spin" />
      case 'failed': return <AlertCircle className="h-3 w-3" />
      default: return <Clock className="h-3 w-3" />
    }
  }

  const getProcessingMethodInfo = (method: string) => {
    switch (method) {
      case 'pdf_ocr':
        return { label: 'PDF OCR', icon: <Bot className="h-3 w-3" />, color: 'bg-blue-100 text-blue-700' }
      case 'manual_text':
        return { label: 'Manual', icon: <User className="h-3 w-3" />, color: 'bg-green-100 text-green-700' }
      case 'text_paste':
        return { label: 'Paste', icon: <FileText className="h-3 w-3" />, color: 'bg-purple-100 text-purple-700' }
      default:
        return { label: 'Unknown', icon: <FileText className="h-3 w-3" />, color: 'bg-gray-100 text-gray-700' }
    }
  }

  const getApprovalStatusInfo = (status: string) => {
    switch (status) {
      case 'approved':
        return { label: 'Approved', color: 'bg-green-100 text-green-700 border-green-300' }
      case 'rejected':
        return { label: 'Rejected', color: 'bg-red-100 text-red-700 border-red-300' }
      default:
        return { label: 'Review', color: 'bg-yellow-100 text-yellow-700 border-yellow-300' }
    }
  }

  const methodInfo = getProcessingMethodInfo(conversation.processing_method)
  const approvalInfo = getApprovalStatusInfo(conversation.approval_status)

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm line-clamp-2 mb-2">
              {conversation.title}
            </CardTitle>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                {methodInfo.icon}
                <span>{methodInfo.label}</span>
              </div>
              {conversation.extraction_confidence && (
                <div className="flex items-center gap-1">
                  <Sparkles className="h-3 w-3" />
                  <span>{Math.round(conversation.extraction_confidence * 100)}%</span>
                </div>
              )}
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                <span>{formatTimestamp(conversation.created_at)}</span>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2 ml-2">
            <Badge 
              variant="outline" 
              className={cn("text-xs", getStatusColor(conversation.processing_status))}
            >
              <span className="mr-1">{getStatusIcon(conversation.processing_status)}</span>
              {conversation.processing_status}
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn("text-xs", approvalInfo.color)}>
              {approvalInfo.label}
            </Badge>
            {conversation.extracted_text && (
              <span className="text-xs text-muted-foreground">
                {conversation.extracted_text.length.toLocaleString()} chars
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            {conversation.processing_status === 'processing' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onRefresh}
                className="h-8 w-8 p-0"
                title="Refresh status"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            )}
            
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onView(conversation)}
              className="h-8 w-8 p-0"
              title="View conversation"
            >
              <Eye className="h-4 w-4" />
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(conversation)}
              className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
              title="Delete conversation"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function UpdatedConversationManager() {
  const [conversations, setConversations] = useState<ConversationData[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearchQuery] = useDebounce(searchQuery, 300)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [methodFilter, setMethodFilter] = useState<string>('all')
  const [selectedConversation, setSelectedConversation] = useState<ConversationData | null>(null)
  const [conversationToDelete, setConversationToDelete] = useState<ConversationData | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // Load conversations
  const loadConversations = useCallback(async () => {
    setIsLoading(true)
    try {
      // TODO: Replace with actual API call
      const response = await fetch('/api/v1/feedme/conversations')
      if (response.ok) {
        const data = await response.json()
        setConversations(data.conversations || [])
      }
    } catch (error) {
      console.error('Failed to load conversations:', error)
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Load conversations on mount
  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // Filter conversations
  const filteredConversations = conversations.filter(conv => {
    const matchesSearch = !debouncedSearchQuery || 
      conv.title.toLowerCase().includes(debouncedSearchQuery.toLowerCase()) ||
      (conv.extracted_text && conv.extracted_text.toLowerCase().includes(debouncedSearchQuery.toLowerCase()))
    
    const matchesStatus = statusFilter === 'all' || conv.processing_status === statusFilter
    const matchesMethod = methodFilter === 'all' || conv.processing_method === methodFilter
    
    return matchesSearch && matchesStatus && matchesMethod
  })

  // Handle viewing conversation
  const handleViewConversation = (conversation: ConversationData) => {
    setSelectedConversation(conversation)
  }

  // Handle text update
  const handleTextUpdate = async (text: string) => {
    if (!selectedConversation) return

    try {
      const response = await fetch(`/api/v1/feedme/conversations/${selectedConversation.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extracted_text: text })
      })

      if (response.ok) {
        // Update local state
        setSelectedConversation({ ...selectedConversation, extracted_text: text })
        setConversations(convs => 
          convs.map(c => c.id === selectedConversation.id ? { ...c, extracted_text: text } : c)
        )
      } else {
        throw new Error('Failed to update text')
      }
    } catch (error) {
      console.error('Failed to update text:', error)
      throw error
    }
  }

  // Handle approval action
  const handleApprovalAction = async (action: 'approve' | 'reject' | 'edit_and_approve', data?: any) => {
    if (!selectedConversation) return

    try {
      const response = await fetch(`/api/v1/feedme/approval/conversation/${selectedConversation.id}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          reviewer_id: 'current_user', // TODO: Get from auth context
          notes: `${action} via UI`,
          ...data
        })
      })

      if (response.ok) {
        const result = await response.json()
        // Update local state
        const updatedConversation = {
          ...selectedConversation,
          approval_status: action === 'reject' ? 'rejected' : 'approved',
          approved_by: 'current_user',
          approved_at: new Date().toISOString(),
          ...(data?.edited_text && { extracted_text: data.edited_text })
        }
        setSelectedConversation(updatedConversation)
        setConversations(convs => 
          convs.map(c => c.id === selectedConversation.id ? updatedConversation : c)
        )
      } else {
        throw new Error('Failed to process approval action')
      }
    } catch (error) {
      console.error('Failed to process approval action:', error)
      throw error
    }
  }

  // Handle delete conversation
  const handleDeleteConversation = async () => {
    if (!conversationToDelete) return

    setIsDeleting(true)
    try {
      const response = await fetch(`/api/v1/feedme/conversations/${conversationToDelete.id}`, {
        method: 'DELETE'
      })

      if (response.ok) {
        setConversations(convs => convs.filter(c => c.id !== conversationToDelete.id))
        setConversationToDelete(null)
        
        // Close detail view if showing deleted conversation
        if (selectedConversation?.id === conversationToDelete.id) {
          setSelectedConversation(null)
        }
      } else {
        throw new Error('Failed to delete conversation')
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error)
    } finally {
      setIsDeleting(false)
    }
  }

  // Get status counts for filter badges
  const statusCounts = conversations.reduce((acc, conv) => {
    acc[conv.processing_status] = (acc[conv.processing_status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Left panel - Conversation list */}
      <div className="w-1/3 border-r bg-muted/30 flex flex-col">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Conversations</h2>
            <Button size="sm" className="gap-2">
              <Plus className="h-4 w-4" />
              Upload
            </Button>
          </div>

          {/* Search */}
          <div className="relative mb-4">
            <Search className="h-4 w-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Filters */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium">Status:</span>
              <Button
                variant={statusFilter === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('all')}
              >
                All ({conversations.length})
              </Button>
              <Button
                variant={statusFilter === 'pending' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('pending')}
              >
                Pending ({statusCounts.pending || 0})
              </Button>
              <Button
                variant={statusFilter === 'completed' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setStatusFilter('completed')}
              >
                Completed ({statusCounts.completed || 0})
              </Button>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium">Method:</span>
              <Button
                variant={methodFilter === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setMethodFilter('all')}
              >
                All
              </Button>
              <Button
                variant={methodFilter === 'pdf_ocr' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setMethodFilter('pdf_ocr')}
              >
                PDF OCR
              </Button>
              <Button
                variant={methodFilter === 'manual_text' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setMethodFilter('manual_text')}
              >
                Manual
              </Button>
            </div>
          </div>
        </div>

        {/* Conversation list */}
        <ScrollArea className="flex-1">
          <div className="p-4 space-y-3">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : filteredConversations.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-sm">No conversations found</p>
                <p className="text-xs mt-1">
                  {debouncedSearchQuery ? 'Try adjusting your search' : 'Upload a transcript to get started'}
                </p>
              </div>
            ) : (
              filteredConversations.map((conversation) => (
                <ConversationCard
                  key={conversation.id}
                  conversation={conversation}
                  onView={handleViewConversation}
                  onDelete={setConversationToDelete}
                  onRefresh={loadConversations}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Right panel - Conversation detail */}
      <div className="flex-1 flex flex-col">
        {selectedConversation ? (
          <div className="flex-1 overflow-hidden">
            <div className="h-full flex flex-col">
              <div className="border-b p-4 flex items-center justify-between">
                <h3 className="font-semibold">Conversation Details</h3>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedConversation(null)}
                  className="h-8 w-8 p-0"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              
              <ScrollArea className="flex-1">
                <div className="p-6">
                  <UnifiedTextCanvas
                    conversationId={selectedConversation.id}
                    title={selectedConversation.title}
                    extractedText={selectedConversation.extracted_text || ''}
                    processingMetadata={{
                      processing_method: selectedConversation.processing_method,
                      extraction_confidence: selectedConversation.extraction_confidence,
                      processing_time_ms: selectedConversation.processing_time_ms,
                      quality_metrics: selectedConversation.quality_metrics,
                      extraction_method: selectedConversation.extraction_method,
                      warnings: selectedConversation.warnings
                    }}
                    approvalStatus={selectedConversation.approval_status}
                    approvedBy={selectedConversation.approved_by}
                    approvedAt={selectedConversation.approved_at}
                    onTextUpdate={handleTextUpdate}
                    onApprovalAction={handleApprovalAction}
                    readOnly={false}
                    showApprovalControls={selectedConversation.approval_status === 'pending'}
                  />
                </div>
              </ScrollArea>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">Select a conversation</p>
              <p className="text-sm mt-1">Choose a conversation from the list to view and edit its content</p>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <AlertDialog open={!!conversationToDelete} onOpenChange={() => setConversationToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{conversationToDelete?.title}"? 
              This action cannot be undone and will permanently remove the conversation and its extracted text.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConversation}
              disabled={isDeleting}
              className="bg-red-600 hover:bg-red-700"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export { FeedMeConversationManager }