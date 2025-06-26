/**
 * FeedMe Conversation Manager
 * Main interface for viewing, editing, and managing FeedMe conversations
 * 
 * Features:
 * - Conversation list with search and filters
 * - Upload new conversations
 * - Edit existing conversations with version control
 * - Processing status tracking
 * - Responsive design with tabs
 */

'use client'

import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
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
  RefreshCw
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import {
  listConversations,
  type UploadTranscriptResponse,
  type ConversationListResponse
} from '@/lib/feedme-api'
import { FeedMeModal } from './FeedMeModal'
import { EditConversationModal } from './EditConversationModal'

interface FeedMeConversationManagerProps {
  isOpen: boolean
  onClose: () => void
}

interface ConversationCardProps {
  conversation: UploadTranscriptResponse
  onEdit: (conversation: UploadTranscriptResponse) => void
  onRefresh: () => void
}

function ConversationCard({ conversation, onEdit, onRefresh }: ConversationCardProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-600 bg-green-50 border-green-200'
      case 'processing':
        return 'text-blue-600 bg-blue-50 border-blue-200'
      case 'failed':
        return 'text-red-600 bg-red-50 border-red-200'
      default:
        return 'text-yellow-600 bg-yellow-50 border-yellow-200'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4" />
      case 'processing':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'failed':
        return <AlertCircle className="h-4 w-4" />
      default:
        return <Clock className="h-4 w-4" />
    }
  }

  const formatTimestamp = (dateString: string) => {
    try {
      const date = new Date(dateString)
      return formatDistanceToNow(date, { addSuffix: true })
    } catch {
      return 'Unknown'
    }
  }

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm line-clamp-2 mb-2">
              {conversation.title}
            </CardTitle>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <FileText className="h-3 w-3" />
                <span>{conversation.total_examples} examples</span>
              </div>
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
          <div className="text-xs text-muted-foreground">
            ID: {conversation.id}
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
              variant="outline"
              size="sm"
              onClick={() => onEdit(conversation)}
              className="flex items-center gap-2"
              disabled={conversation.processing_status === 'processing'}
            >
              <Edit3 className="h-4 w-4" />
              Edit
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function FeedMeConversationManager({ isOpen, onClose }: FeedMeConversationManagerProps) {
  // State management
  const [activeTab, setActiveTab] = useState<'conversations' | 'upload'>('conversations')
  const [conversations, setConversations] = useState<UploadTranscriptResponse[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  
  // Modal states
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [selectedConversation, setSelectedConversation] = useState<UploadTranscriptResponse | null>(null)

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const pageSize = 10

  // Load conversations
  useEffect(() => {
    if (isOpen && activeTab === 'conversations') {
      loadConversations()
    }
  }, [isOpen, activeTab, currentPage, statusFilter])

  const loadConversations = async () => {
    try {
      setIsLoading(true)
      setError(null)
      
      const response: ConversationListResponse = await listConversations(
        currentPage,
        pageSize,
        statusFilter === 'all' ? undefined : statusFilter
      )
      
      setConversations(response.conversations)
      setTotalCount(response.total_count)
    } catch (error) {
      console.error('Failed to load conversations:', error)
      setError(error instanceof Error ? error.message : 'Failed to load conversations')
    } finally {
      setIsLoading(false)
    }
  }

  // Filter conversations by search query
  const filteredConversations = conversations.filter(conversation =>
    conversation.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Handle edit conversation
  const handleEditConversation = (conversation: UploadTranscriptResponse) => {
    setSelectedConversation(conversation)
    setIsEditModalOpen(true)
  }

  // Handle conversation updated
  const handleConversationUpdated = (updatedConversation: UploadTranscriptResponse) => {
    setConversations(prev => 
      prev.map(conv => 
        conv.id === updatedConversation.id ? updatedConversation : conv
      )
    )
  }

  // Refresh conversations when upload modal closes
  useEffect(() => {
    if (!isUploadModalOpen && isOpen && activeTab === 'conversations') {
      // Refresh conversations list after upload
      loadConversations()
    }
  }, [isUploadModalOpen, isOpen, activeTab])

  // Handle close
  const handleClose = () => {
    setActiveTab('conversations')
    setSearchQuery('')
    setStatusFilter('all')
    setCurrentPage(1)
    onClose()
  }

  return (
    <>
      <Dialog open={isOpen} onOpenChange={handleClose}>
        <DialogContent className="max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              FeedMe Conversation Manager
              {totalCount > 0 && (
                <Badge variant="secondary" className="ml-2">
                  {totalCount} conversations
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="flex-1 flex flex-col overflow-hidden">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="conversations" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Conversations ({totalCount})
              </TabsTrigger>
              <TabsTrigger value="upload" className="flex items-center gap-2">
                <Plus className="h-4 w-4" />
                Upload New
              </TabsTrigger>
            </TabsList>

            {/* Conversations Tab */}
            <TabsContent value="conversations" className="flex-1 flex flex-col overflow-hidden mt-4">
              {/* Search and Filters */}
              <div className="flex items-center gap-4 mb-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search conversations..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>
                
                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-muted-foreground" />
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="px-3 py-1 border rounded-md text-sm"
                  >
                    <option value="all">All Status</option>
                    <option value="completed">Completed</option>
                    <option value="processing">Processing</option>
                    <option value="failed">Failed</option>
                    <option value="pending">Pending</option>
                  </select>
                </div>

                <Button
                  variant="outline"
                  onClick={loadConversations}
                  disabled={isLoading}
                  className="flex items-center gap-2"
                >
                  <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
                  Refresh
                </Button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-hidden">
                {error ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="text-center">
                      <AlertCircle className="h-8 w-8 mx-auto mb-2 text-red-500" />
                      <p className="text-sm text-red-600 mb-4">{error}</p>
                      <Button variant="outline" onClick={loadConversations}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Retry
                      </Button>
                    </div>
                  </div>
                ) : isLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="text-center">
                      <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2 text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">Loading conversations...</p>
                    </div>
                  </div>
                ) : filteredConversations.length === 0 ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="text-center">
                      <FileText className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                      <p className="text-lg font-medium mb-2">No conversations found</p>
                      <p className="text-sm text-muted-foreground mb-4">
                        {searchQuery ? 'Try adjusting your search query' : 'Upload your first conversation to get started'}
                      </p>
                      {!searchQuery && (
                        <Button onClick={() => setActiveTab('upload')}>
                          <Plus className="h-4 w-4 mr-2" />
                          Upload Conversation
                        </Button>
                      )}
                    </div>
                  </div>
                ) : (
                  <ScrollArea className="h-[400px]">
                    <div className="space-y-4 pr-4">
                      {filteredConversations.map((conversation) => (
                        <ConversationCard
                          key={conversation.id}
                          conversation={conversation}
                          onEdit={handleEditConversation}
                          onRefresh={loadConversations}
                        />
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </div>

              {/* Pagination */}
              {totalCount > pageSize && (
                <div className="flex items-center justify-between pt-4 border-t">
                  <p className="text-sm text-muted-foreground">
                    Showing {Math.min((currentPage - 1) * pageSize + 1, totalCount)} to{' '}
                    {Math.min(currentPage * pageSize, totalCount)} of {totalCount} conversations
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage(prev => prev + 1)}
                      disabled={currentPage * pageSize >= totalCount}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* Upload Tab */}
            <TabsContent value="upload" className="flex-1 overflow-hidden mt-4">
              <div className="h-full flex items-center justify-center">
                <div className="text-center max-w-md">
                  <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                  <h3 className="text-lg font-semibold mb-2">Upload New Conversation</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Upload customer support transcripts to extract Q&A examples for the knowledge base.
                  </p>
                  <Button 
                    onClick={() => setIsUploadModalOpen(true)}
                    className="flex items-center gap-2"
                  >
                    <Plus className="h-4 w-4" />
                    Upload Transcript
                  </Button>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {/* Upload Modal */}
      <FeedMeModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
      />

      {/* Edit Modal */}
      {selectedConversation && (
        <EditConversationModal
          isOpen={isEditModalOpen}
          onClose={() => {
            setIsEditModalOpen(false)
            setSelectedConversation(null)
          }}
          conversation={selectedConversation}
          onConversationUpdated={handleConversationUpdated}
        />
      )}
    </>
  )
}