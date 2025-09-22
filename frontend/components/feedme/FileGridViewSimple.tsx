/**
 * FileGridView - Simplified Version
 * Grid layout for displaying conversations with basic functionality
 */

'use client'

import React, { useEffect, useState } from 'react'
import { withErrorBoundary } from '@/components/feedme-revamped/ErrorBoundary'
import { FileText, Clock, User, CheckCircle2, AlertCircle, Loader2, Trash2, MoreHorizontal, Folder, Move, Edit2 } from 'lucide-react'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
  const [renameDialogOpen, setRenameDialogOpen] = useState(false)
  const [conversationToRename, setConversationToRename] = useState<{ id: number, title: string } | null>(null)
  const [newTitle, setNewTitle] = useState('')

  useEffect(() => {
    // Load conversations and folders on mount
    conversationsActions.loadConversations()
    foldersActions.loadFolders()
  }, []) // Empty dependency array - only run once on mount

  const handleConversationSelect = (conversation: { id?: number; title?: string }) => {
    // Type guard to ensure conversation has a valid ID
    const isValidConversationId = (id: any): id is number => {
      return typeof id === 'number' && Number.isInteger(id) && id > 0
    }

    // Validate conversation ID before processing
    if (!conversation.id || !isValidConversationId(conversation.id)) {
      console.warn('Invalid conversation ID selected:', conversation.id)
      uiActions.showToast({
        type: 'error',
        title: 'Invalid Selection',
        message: 'Please select a valid conversation'
      })
      return
    }

    // Check if conversation exists in current store
    const existingConversation = conversations.find(c => c.id === conversation.id)
    if (!existingConversation) {
      console.warn(`Conversation ${conversation.id} not found in current list`)

      // Show loading message but don't refresh here - let the editor handle the load
      uiActions.showToast({
        type: 'info',
        title: 'Loading Conversation',
        message: 'Loading conversation details...'
      })
    }

    // Always call the parent callback with validated ID
    onConversationSelect?.(conversation.id)
  }

  const handleDeleteClick = (e: React.MouseEvent, conversationId: number | undefined) => {
    e.stopPropagation() // Prevent card click
    if (typeof conversationId !== 'number' || conversationId <= 0) {
      console.warn('Invalid conversation ID for delete:', conversationId)
      uiActions.showToast({
        type: 'error',
        title: 'Invalid Selection',
        message: 'Cannot delete - invalid conversation ID'
      })
      return
    }
    setConversationToDelete(conversationId)
    setDeleteDialogOpen(true)
  }

  const handleMoveToFolder = async (conversationId: number | undefined, folderId: number | null) => {
    if (typeof conversationId !== 'number' || conversationId <= 0) {
      console.warn('Invalid conversation ID for move:', conversationId)
      uiActions.showToast({
        type: 'error',
        title: 'Invalid Selection',
        message: 'Cannot move - invalid conversation ID'
      })
      return
    }

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

  const handleRenameClick = (conversationId: number | undefined, currentTitle: string) => {
    if (typeof conversationId !== 'number' || conversationId <= 0) {
      console.warn('Invalid conversation ID for rename:', conversationId)
      uiActions.showToast({
        type: 'error',
        title: 'Invalid Selection',
        message: 'Cannot rename - invalid conversation ID'
      })
      return
    }
    setConversationToRename({ id: conversationId, title: currentTitle })
    setNewTitle(currentTitle)
    setRenameDialogOpen(true)
  }

  const handleRenameConfirm = async () => {
    if (conversationToRename && newTitle.trim()) {
      try {
        await conversationsActions.editConversation(conversationToRename.id, {
          title: newTitle.trim()
        })
        uiActions.showToast({
          type: 'success',
          title: 'Conversation Renamed',
          message: 'The conversation has been successfully renamed.'
        })
      } catch (error) {
        console.error('Failed to rename conversation:', error)
        uiActions.showToast({
          type: 'error',
          title: 'Rename Failed',
          message: 'Failed to rename the conversation. Please try again.'
        })
      }
    }
    setRenameDialogOpen(false)
    setConversationToRename(null)
    setNewTitle('')
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
  const isUnassignedFolder = currentFolderId === 0

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
        {/* Folder navigation header - don't show for unassigned conversations */}
        {currentFolderId !== null && currentFolderId !== 0 && (
          <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onFolderSelect?.(null)}
              className="text-accent hover:bg-mb-blue-300/20"
            >
              All Conversations
            </Button>
            <span>/</span>
            <span className="font-medium text-foreground">{folderDisplayName}</span>
          </div>
        )}
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {conversations.map((conversation) => {
            const tracker = (conversation.metadata as any)?.processing_tracker || {}
            const statusMessage = tracker.message as string | undefined
            const progress = typeof tracker.progress === 'number'
              ? tracker.progress
              : conversation.processing_status === 'completed'
                ? 100
                : undefined

            return (
              <Card
                key={conversation.id}
                className="cursor-pointer hover:shadow-md hover:bg-mb-blue-300/50 focus-within:ring-2 focus-within:ring-accent/50 transition-all duration-200 relative group"
                onClick={() => handleConversationSelect(conversation)}
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
                    {isUnassignedFolder ? (
                      // For unassigned conversations, only show Rename and Delete
                      <>
                        <DropdownMenuItem 
                          className="flex items-center gap-2 cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleRenameClick(conversation.id, conversation.title || '')
                          }}
                        >
                          <Edit2 className="h-4 w-4" />
                          Rename
                        </DropdownMenuItem>
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
                      </>
                    ) : (
                      // For other folders, show full menu
                      <>
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
                      </>
                    )}
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
                    {statusMessage || conversation.processing_status}
                  </Badge>
                </div>
              </CardHeader>
              
              <CardContent className="pt-0">
                <div className="space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>
                      {conversation.created_at && 
                        formatDistanceToNow(new Date(conversation.created_at), { addSuffix: true })
                      }
                    </span>
                  </div>

                  {conversation.processing_status === 'processing' && typeof progress === 'number' && (
                    <div className="pt-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[11px] uppercase tracking-wide text-emerald-600">Progress</span>
                        <span className="text-[11px] font-medium text-emerald-600">{progress}%</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-emerald-500/20 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-emerald-500 transition-all duration-300"
                          style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
                        />
                      </div>
                    </div>
                  )}
                  
                  {conversation.metadata?.uploaded_by && (
                    <div className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      <span>{conversation.metadata.uploaded_by}</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
            )
          })}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this conversation? This action cannot be undone.
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

      {/* Rename dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Conversation</DialogTitle>
            <DialogDescription>
              Enter a new name for this conversation.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="name" className="text-right">
                Name
              </Label>
              <Input
                id="name"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="col-span-3"
                placeholder="Enter conversation name"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleRenameConfirm()
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRenameDialogOpen(false)
                setConversationToRename(null)
                setNewTitle('')
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleRenameConfirm} disabled={!newTitle.trim()}>
              Rename
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ScrollArea>
  )
}

// Export the component wrapped with error boundary
export default withErrorBoundary(FileGridView)
