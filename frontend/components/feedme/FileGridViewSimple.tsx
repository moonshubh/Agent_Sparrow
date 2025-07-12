/**
 * FileGridView - Simplified Version
 * Grid layout for displaying conversations with basic functionality
 */

'use client'

import React, { useEffect, useState } from 'react'
import { FileText, Clock, User, CheckCircle2, AlertCircle, Loader2, Trash2, MoreHorizontal, Folder, Move } from 'lucide-react'
import { useConversations, useConversationsActions } from '@/lib/stores/conversations-store'
import { useUIActions } from '@/lib/stores/ui-store'
import { useFoldersStore } from '@/lib/stores/folders-store'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { 
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'

interface FileGridViewProps {
  onConversationSelect?: (conversationId: number) => void
  currentFolderId?: number | null
  onFolderSelect?: (folderId: number | null) => void
  onConversationMove?: (conversationId: number, folderId: number | null) => void
  className?: string
}

const StatusIcon = ({ status }: { status: string }) => {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-accent" />
    case 'processing':
      return <Loader2 className="h-4 w-4 text-accent animate-spin" />
    case 'failed':
      return <AlertCircle className="h-4 w-4 text-red-500" />
    default:
      return <Clock className="h-4 w-4 text-yellow-500" />
  }
}

export function FileGridView({ onConversationSelect, currentFolderId, onFolderSelect, onConversationMove, className }: FileGridViewProps) {
  const { items: conversations, isLoading } = useConversations()
  const conversationsActions = useConversationsActions()
  const uiActions = useUIActions()
  const { folders, actions: foldersActions } = useFoldersStore()
  
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [conversationToDelete, setConversationToDelete] = useState<number | null>(null)

  useEffect(() => {
    // Load conversations and folders on mount
    conversationsActions.loadConversations()
    foldersActions.loadFolders()
  }, []) // Empty dependency array - only run once on mount

  const handleConversationSelect = (conversationId: number) => {
    // Validate conversation ID before setting
    if (!conversationId || conversationId <= 0) {
      console.warn('Invalid conversation ID selected:', conversationId)
      return
    }
    
    // Check if conversation exists in current store
    const conversation = conversations.find(c => c.id === conversationId)
    if (!conversation) {
      console.warn(`Conversation ${conversationId} not found in current list`)
      
      // Show loading message but don't refresh here - let the editor handle the load
      uiActions.showToast({
        type: 'info',
        title: 'Loading Conversation',
        message: 'Loading conversation details...'
      })
    }
    
    // Always call the parent callback - let the editor handle loading/errors
    onConversationSelect?.(conversationId)
  }

  const handleDeleteClick = (e: React.MouseEvent, conversationId: number) => {
    e.stopPropagation() // Prevent card click
    setConversationToDelete(conversationId)
    setDeleteDialogOpen(true)
  }

  const handleMoveToFolder = async (conversationId: number, folderId: number | null) => {
    try {
      await conversationsActions.bulkAssignToFolder([conversationId], folderId)
      const folderName = folderId ? Object.values(folders).find(f => f.id === folderId)?.name || 'Unknown Folder' : 'Root'
      
      uiActions.showToast({
        type: 'success',
        title: 'Conversation Moved',
        message: `Conversation moved to ${folderName} successfully.`
      })
    } catch (error) {
      console.error('Failed to move conversation:', error)
      uiActions.showToast({
        type: 'error',
        title: 'Move Failed',
        message: 'Failed to move conversation. Please try again.'
      })
    }
  }

  const handleDeleteConfirm = async () => {
    if (conversationToDelete) {
      try {
        await conversationsActions.deleteConversation(conversationToDelete)
        uiActions.showToast({
          type: 'success',
          title: 'Conversation Deleted',
          message: 'The conversation has been successfully deleted.'
        })
      } catch (error) {
        console.error('Failed to delete conversation:', error)
        uiActions.showToast({
          type: 'error',
          title: 'Delete Failed',
          message: 'Failed to delete the conversation. Please try again.'
        })
      }
    }
    setDeleteDialogOpen(false)
    setConversationToDelete(null)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading conversations...</span>
      </div>
    )
  }

  // Get current folder name for display
  const currentFolder = currentFolderId ? Object.values(folders).find(f => f.id === currentFolderId) : null
  const folderDisplayName = currentFolderId === 0 ? "Unassigned" : currentFolder?.name || "All Conversations"

  if (conversations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <FileText className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="text-lg font-medium">
          {currentFolderId !== null ? `No conversations in ${folderDisplayName}` : "No conversations yet"}
        </h3>
        <p className="text-muted-foreground">
          {currentFolderId !== null 
            ? "This folder is empty. Try moving conversations here or switch to view all conversations."
            : "Upload your first transcript to get started"
          }
        </p>
        {currentFolderId !== null ? (
          <Button className="mt-4" onClick={() => onFolderSelect?.(null)}>
            View All Conversations
          </Button>
        ) : (
          <Button className="mt-4" onClick={() => uiActions.setActiveTab('upload')}>
            Upload Transcript
          </Button>
        )}
      </div>
    )
  }

  return (
    <ScrollArea className={`${className} feedme-scrollbar`}>
      <div className="p-6">
        {/* Folder navigation header */}
        {currentFolderId !== null && (
          <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onFolderSelect?.(null)}
              className="text-accent hover:bg-mb-blue-300-foreground"
            >
              All Conversations
            </Button>
            <span>/</span>
            <span className="font-medium text-foreground">{folderDisplayName}</span>
          </div>
        )}
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {conversations.map((conversation) => (
            <Card 
              key={conversation.id} 
              className="cursor-pointer hover:shadow-md hover:bg-mb-blue-300/50 focus-within:ring-2 focus-within:ring-accent/50 transition-all duration-200 relative group"
              onClick={() => handleConversationSelect(conversation.id)}
              tabIndex={0}
            >
              {/* Actions dropdown - shows on hover */}
              <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="p-1 h-8 w-8 bg-background/80 hover:bg-mb-blue-300"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    
                    {/* Move to Folder submenu */}
                    <DropdownMenuItem 
                      className="flex items-center gap-2 cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleMoveToFolder(conversation.id, null)
                      }}
                    >
                      <Folder className="h-4 w-4" />
                      Move to Root
                    </DropdownMenuItem>
                    
                    {Object.values(folders).map((folder) => (
                      <DropdownMenuItem 
                        key={folder.id}
                        className="flex items-center gap-2 cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleMoveToFolder(conversation.id, folder.id)
                        }}
                      >
                        <div className="flex items-center gap-2">
                          <div 
                            className="w-3 h-3 rounded-full border"
                            style={{ backgroundColor: folder.color }}
                          />
                          <span>Move to {folder.name}</span>
                        </div>
                      </DropdownMenuItem>
                    ))}
                    
                    <DropdownMenuSeparator />
                    <DropdownMenuItem 
                      className="flex items-center gap-2 text-destructive focus:text-destructive cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteClick(e, conversation.id)
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              <CardHeader className="pb-3">
                <CardTitle className="text-sm line-clamp-2 h-10 pr-8">
                  {conversation.title}
                </CardTitle>
                <div className="flex items-center gap-2">
                  <StatusIcon status={conversation.processing_status} />
                  <Badge 
                    variant={conversation.processing_status === 'completed' ? 'default' : 'secondary'}
                    className={cn(
                      "text-xs",
                      conversation.processing_status === 'completed' && "bg-accent text-accent-foreground"
                    )}
                  >
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

      {/* Delete confirmation dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this conversation? This action cannot be undone and will permanently remove all Q&A examples extracted from this transcript.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ScrollArea>
  )
}
