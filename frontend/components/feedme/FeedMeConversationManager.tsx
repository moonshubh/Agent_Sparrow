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
  Move
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import {
  listConversations,
  deleteConversation,
  listFolders,
  type UploadTranscriptResponse,
  type ConversationListResponse,
  type DeleteConversationResponse,
  type FeedMeFolder
} from '@/lib/feedme-api'
import { EnhancedFeedMeModal } from './EnhancedFeedMeModal'

interface FeedMeConversationManagerProps {
  isOpen: boolean
  onClose: () => void
}

interface ConversationCardProps {
  conversation: UploadTranscriptResponse
  onEdit: (conversation: UploadTranscriptResponse) => void
  onDelete: (conversation: UploadTranscriptResponse) => void
  onRefresh: () => void
}

function ConversationCard({ conversation, onEdit, onDelete, onRefresh }: ConversationCardProps) {
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
            
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDelete(conversation)}
              className="flex items-center gap-2 text-red-600 hover:text-red-700 hover:bg-red-50"
              disabled={conversation.processing_status === 'processing'}
              title="Delete conversation"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function FeedMeConversationManager({ isOpen, onClose }: FeedMeConversationManagerProps) {
  type TabValue = 'view' | 'upload' | 'folders'
  const [activeTab, setActiveTab] = useState<TabValue>('view')
  const [conversations, setConversations] = useState<UploadTranscriptResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [selectedConversation, setSelectedConversation] = useState<UploadTranscriptResponse | null>(null)
  
  // Delete confirmation state
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [conversationToDelete, setConversationToDelete] = useState<UploadTranscriptResponse | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // Folder management state
  const [folders, setFolders] = useState<FeedMeFolder[]>([])
  const [selectedConversations, setSelectedConversations] = useState<number[]>([])
  const [selectedFolderId, setSelectedFolderId] = useState<number | null>(null)

  // Search and pagination state
  const [searchTerm, setSearchTerm] = useState('')
  const [debouncedSearchQuery] = useDebounce(searchTerm, 300)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [totalCount, setTotalCount] = useState(0)
  const isInitialMount = useRef(true)

  // Reset page to 1 when search query changes, except on initial mount
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }

    // To prevent an extra re-render, only reset if not already on page 1
    if (currentPage !== 1) {
      setCurrentPage(1)
    }
  }, [debouncedSearchQuery])

  // Load folders from API
  const loadFolders = useCallback(async () => {
    try {
      const response = await listFolders()
      setFolders(response.folders)
    } catch (err) {
      console.error('Failed to load folders:', err)
      // If folders fail to load, set an empty array to prevent UI issues
      setFolders([])
      // Show error to user
      if (err instanceof Error) {
        const errorMessage = err.message.includes('unavailable') 
          ? 'FeedMe service is temporarily unavailable. Please try again later.'
          : 'Failed to load folders. Please check your connection and try again.'
        
        setError(errorMessage)
        // Clear error after 5 seconds
        setTimeout(() => setError(null), 5000)
      }
    }
  }, [])

  // Load conversations from API
  const loadConversations = useCallback(async () => {
    if (!isOpen) return
    setIsLoading(true)
    setError(null)
    try {
      const response = await listConversations(currentPage, pageSize, debouncedSearchQuery)
      setConversations(response.conversations)
      setTotalCount(response.total_count)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations')
      setConversations([])
      setTotalCount(0)
    } finally {
      setIsLoading(false)
    }
  }, [isOpen, currentPage, pageSize, debouncedSearchQuery])

  useEffect(() => {
    if (isOpen) {
      loadFolders()
      loadConversations()
    }
  }, [isOpen, loadFolders, loadConversations])

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

  // Handle delete conversation
  const handleDeleteConversation = (conversation: UploadTranscriptResponse) => {
    setConversationToDelete(conversation)
    setIsDeleteDialogOpen(true)
  }

  // Confirm delete conversation
  const confirmDeleteConversation = async () => {
    if (!conversationToDelete) return

    setIsDeleting(true)
    try {
      await deleteConversation(conversationToDelete.id)
      
      // Remove from local state
      setConversations(prev => 
        prev.filter(conv => conv.id !== conversationToDelete.id)
      )
      
      // Update total count
      setTotalCount(prev => Math.max(0, prev - 1))
      
      setIsDeleteDialogOpen(false)
      setConversationToDelete(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete conversation')
    } finally {
      setIsDeleting(false)
    }
  }

  // Cancel delete
  const cancelDelete = () => {
    setIsDeleteDialogOpen(false)
    setConversationToDelete(null)
  }

  // Refresh conversations when upload modal closes
  useEffect(() => {
    if (!isUploadModalOpen && isOpen) {
      // Refresh conversations list after upload
      loadConversations()
    }
  }, [isUploadModalOpen, isOpen, loadConversations])

  // Handle close
  const handleClose = () => {
    setActiveTab('view')
    setSearchTerm('')
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
            </DialogTitle>
            <DialogDescription>
              View, search, and manage your FeedMe conversations. You can also upload new transcripts for processing.
            </DialogDescription>
            {totalCount > 0 && (
              <Badge variant="secondary" className="ml-2">
                {totalCount} conversations
              </Badge>
            )}
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as TabValue)} className="flex-1 flex flex-col overflow-hidden">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="view" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Conversations ({totalCount})
              </TabsTrigger>
              <TabsTrigger value="folders" className="flex items-center gap-2">
                <Folder className="h-4 w-4" />
                Folders ({folders.length})
              </TabsTrigger>
              <TabsTrigger value="upload" className="flex items-center gap-2">
                <Plus className="h-4 w-4" />
                Upload New
              </TabsTrigger>
            </TabsList>

            {/* Conversations Tab */}
            <TabsContent value="view" className="flex-1 flex flex-col overflow-hidden mt-4">
              {/* Search and Filters */}
              <div className="flex items-center gap-4 mb-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search conversations..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                  />
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
                ) : conversations.length === 0 ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="text-center">
                      <p className="text-lg font-medium mb-2">No conversations found</p>
                      <p className="text-sm text-muted-foreground mb-4">
                        {debouncedSearchQuery ? 'Try adjusting your search query' : 'Upload your first conversation to get started'}
                      </p>
                      {!debouncedSearchQuery && !isLoading && (
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
                      {conversations.map((conversation) => (
                        <ConversationCard
                          key={conversation.id}
                          conversation={conversation}
                          onEdit={handleEditConversation}
                          onDelete={handleDeleteConversation}
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

            {/* Folders Tab */}
            <TabsContent value="folders" className="flex-1 overflow-hidden mt-4">
              <div className="h-full flex flex-col">
                {/* Folder Management Header */}
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold">Folder Organization</h3>
                    <p className="text-sm text-muted-foreground">
                      Organize conversations with colored folders for better management
                    </p>
                  </div>
                  <Button 
                    onClick={() => setIsUploadModalOpen(true)}
                    className="flex items-center gap-2"
                  >
                    <Settings className="h-4 w-4" />
                    Manage Folders
                  </Button>
                </div>

                {/* Folder Grid */}
                <div className="flex-1 overflow-auto">
                  {folders.length === 0 ? (
                    <div className="flex items-center justify-center h-64">
                      <div className="text-center">
                        <Folder className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                        <h3 className="text-lg font-medium mb-2">No folders yet</h3>
                        <p className="text-sm text-muted-foreground mb-4">
                          Create your first folder to organize conversations
                        </p>
                        <Button onClick={() => setIsUploadModalOpen(true)}>
                          <Plus className="h-4 w-4 mr-2" />
                          Upload Transcript
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {folders.map((folder) => (
                        <Card key={folder.id} className="hover:shadow-md transition-shadow cursor-pointer">
                          <CardHeader className="pb-2">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <div 
                                  className="w-4 h-4 rounded-full border border-gray-300"
                                  style={{ backgroundColor: folder.color }}
                                />
                                <CardTitle className="text-base">{folder.name}</CardTitle>
                              </div>
                              <Badge variant="secondary" className="text-xs">
                                {folder.conversation_count}
                              </Badge>
                            </div>
                            {folder.description && (
                              <p className="text-xs text-muted-foreground mt-1">
                                {folder.description}
                              </p>
                            )}
                          </CardHeader>
                          <CardContent className="pt-0">
                            <div className="flex items-center justify-between text-sm">
                              <div className="flex items-center gap-1 text-muted-foreground">
                                <FileText className="h-3 w-3" />
                                {folder.conversation_count} conversations
                              </div>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setSelectedFolderId(folder.id)
                                  setActiveTab('view')
                                }}
                              >
                                View
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </div>
              </div>
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
                    className="flex items-center gap-2 mx-auto bg-accent hover:bg-accent/90 text-accent-foreground"
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
      <EnhancedFeedMeModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
      />



      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{conversationToDelete?.title}"? 
              This will permanently remove the conversation and all associated examples ({conversationToDelete?.total_examples} examples).
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={cancelDelete} disabled={isDeleting}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction 
              onClick={confirmDeleteConversation}
              disabled={isDeleting}
              className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}