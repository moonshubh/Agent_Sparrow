/**
 * Flawless Folder Manager Component
 * 
 * Enhanced folder management with refined create, update, delete, and move operations.
 * Features comprehensive error handling, validation, and user feedback.
 */

'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { 
  FolderPlus,
  Edit3,
  Trash2,
  Move,
  ChevronRight,
  ChevronDown,
  Folder as FolderIcon,
  FolderOpen,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  X,
  Save,
  RotateCcw,
  FileText,
  Eye,
  MoreHorizontal
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useEnhancedFoldersStore, useFolderTree, useSelectedFolders, usePendingOperations } from '@/lib/stores/enhanced-folders-store'
import type { Folder } from '@/lib/stores/enhanced-folders-store'

// Interfaces
interface FolderDialogProps {
  isOpen: boolean
  onClose: () => void
  mode: 'create' | 'edit' | 'move'
  folder?: Folder
  parentFolder?: Folder
  conversationIds?: number[]
}

interface DeleteConfirmationProps {
  isOpen: boolean
  onClose: () => void
  folder: Folder | null
  onConfirm: (moveConversationsTo?: number, force?: boolean) => void
}

// Color options for folders
const FOLDER_COLORS = [
  { value: '#0095ff', label: 'Blue', className: 'bg-blue-500' },
  { value: '#22c55e', label: 'Green', className: 'bg-green-500' },
  { value: '#f59e0b', label: 'Orange', className: 'bg-orange-500' },
  { value: '#ef4444', label: 'Red', className: 'bg-red-500' },
  { value: '#8b5cf6', label: 'Purple', className: 'bg-purple-500' },
  { value: '#06b6d4', label: 'Cyan', className: 'bg-cyan-500' },
  { value: '#84cc16', label: 'Lime', className: 'bg-lime-500' },
  { value: '#f97316', label: 'Orange', className: 'bg-orange-600' },
]

// Folder Dialog Component
function FolderDialog({ isOpen, onClose, mode, folder, parentFolder, conversationIds }: FolderDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('#0095ff')
  const [parentId, setParentId] = useState<number | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  
  const { folders, actions } = useEnhancedFoldersStore()
  const folderTree = useFolderTree()
  
  // Initialize form
  useEffect(() => {
    if (isOpen) {
      if (mode === 'edit' && folder) {
        setName(folder.name)
        setDescription(folder.description || '')
        setColor(folder.color || '#0095ff')
        setParentId(folder.parent_id)
      } else if (mode === 'create') {
        setName('')
        setDescription('')
        setColor('#0095ff')
        setParentId(parentFolder?.id || null)
      } else if (mode === 'move' && folder) {
        setName(folder.name)
        setDescription(folder.description || '')
        setColor(folder.color || '#0095ff')
        setParentId(folder.parent_id)
      }
      setValidationErrors([])
    }
  }, [isOpen, mode, folder, parentFolder])
  
  // Validation
  const validateForm = useCallback(() => {
    const errors: string[] = []
    
    if (mode === 'create' || mode === 'edit') {
      const nameErrors = actions.validateFolderName(name, parentId)
      errors.push(...nameErrors.map(e => e.message))
    }
    
    if (mode === 'move' && folder) {
      const moveErrors = actions.validateFolderMove(folder.id, parentId)
      errors.push(...moveErrors.map(e => e.message))
    }
    
    setValidationErrors(errors)
    return errors.length === 0
  }, [name, parentId, mode, folder, actions])
  
  // Handle submit
  const handleSubmit = async () => {
    if (!validateForm()) return
    
    setIsSubmitting(true)
    try {
      if (mode === 'create') {
        await actions.createFolder({
          name: name.trim(),
          description: description.trim() || undefined,
          color,
          parent_id: parentId,
          created_by: 'current_user' // TODO: Get from auth context
        })
      } else if (mode === 'edit' && folder) {
        await actions.updateFolder(folder.id, {
          name: name.trim(),
          description: description.trim() || undefined,
          color,
          parent_id: parentId
        })
      } else if (mode === 'move' && folder) {
        await actions.updateFolder(folder.id, {
          parent_id: parentId
        })
      }
      
      onClose()
    } catch (error) {
      console.error(`Failed to ${mode} folder:`, error)
      setValidationErrors([error instanceof Error ? error.message : `Failed to ${mode} folder`])
    } finally {
      setIsSubmitting(false)
    }
  }
  
  // Render folder tree for parent selection
  const renderFolderOption = (folder: Folder, level: number = 0): React.ReactNode => {
    const isDisabled = mode === 'move' && folder.id === folder?.id // Can't move to self
    const hasChildren = folder.children && folder.children.length > 0
    
    return (
      <div key={folder.id}>
        <button
          type="button"
          onClick={() => setParentId(folder.id)}
          disabled={isDisabled}
          className={cn(
            "w-full text-left px-3 py-2 rounded-lg transition-colors",
            "hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed",
            parentId === folder.id && "bg-accent text-accent-foreground",
            isDisabled && "opacity-50 cursor-not-allowed"
          )}
          style={{ paddingLeft: `${12 + level * 20}px` }}
        >
          <div className="flex items-center gap-2">
            {hasChildren ? <FolderOpen className="h-4 w-4" /> : <FolderIcon className="h-4 w-4" />}
            <span className="flex-1">{folder.name}</span>
            {folder.conversation_count && folder.conversation_count > 0 && (
              <Badge variant="outline" className="text-xs">
                {folder.conversation_count}
              </Badge>
            )}
          </div>
        </button>
        
        {hasChildren && folder.children?.map(child => renderFolderOption(child, level + 1))}
      </div>
    )
  }
  
  const getDialogTitle = () => {
    switch (mode) {
      case 'create': return 'Create New Folder'
      case 'edit': return 'Edit Folder'
      case 'move': return 'Move Folder'
      default: return 'Folder'
    }
  }
  
  const getSubmitButtonText = () => {
    if (isSubmitting) {
      return (
        <>
          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          {mode === 'create' ? 'Creating...' : mode === 'edit' ? 'Updating...' : 'Moving...'}
        </>
      )
    }
    return mode === 'create' ? 'Create Folder' : mode === 'edit' ? 'Update Folder' : 'Move Folder'
  }
  
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{getDialogTitle()}</DialogTitle>
          <DialogDescription>
            {mode === 'create' && 'Create a new folder to organize your conversations.'}
            {mode === 'edit' && 'Update the folder name, description, and color.'}
            {mode === 'move' && 'Choose a new parent folder for this folder.'}
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          {/* Validation Errors */}
          {validationErrors.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-red-800">Please fix the following errors:</p>
                  <ul className="text-sm text-red-700 mt-1 space-y-1">
                    {validationErrors.map((error, index) => (
                      <li key={index}>• {error}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
          
          {/* Name Field */}
          {(mode === 'create' || mode === 'edit') && (
            <div className="space-y-2">
              <Label htmlFor="folder-name">Folder Name</Label>
              <Input
                id="folder-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter folder name..."
                maxLength={100}
                disabled={isSubmitting}
              />
              <p className="text-xs text-muted-foreground">
                {name.length}/100 characters
              </p>
            </div>
          )}
          
          {/* Description Field */}
          {(mode === 'create' || mode === 'edit') && (
            <div className="space-y-2">
              <Label htmlFor="folder-description">Description (Optional)</Label>
              <Textarea
                id="folder-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Enter folder description..."
                rows={2}
                maxLength={255}
                disabled={isSubmitting}
              />
            </div>
          )}
          
          {/* Color Selection */}
          {(mode === 'create' || mode === 'edit') && (
            <div className="space-y-2">
              <Label>Folder Color</Label>
              <div className="flex gap-2 flex-wrap">
                {FOLDER_COLORS.map((colorOption) => (
                  <button
                    key={colorOption.value}
                    type="button"
                    onClick={() => setColor(colorOption.value)}
                    disabled={isSubmitting}
                    className={cn(
                      "w-8 h-8 rounded-lg border-2 transition-all",
                      color === colorOption.value 
                        ? "border-foreground scale-110" 
                        : "border-muted hover:border-muted-foreground",
                      colorOption.className
                    )}
                    title={colorOption.label}
                  />
                ))}
              </div>
            </div>
          )}
          
          {/* Parent Folder Selection */}
          <div className="space-y-2">
            <Label>Parent Folder</Label>
            <div className="border rounded-lg max-h-48 overflow-hidden">
              <ScrollArea className="h-full max-h-48">
                <div className="p-2 space-y-1">
                  {/* Root option */}
                  <button
                    type="button"
                    onClick={() => setParentId(null)}
                    className={cn(
                      "w-full text-left px-3 py-2 rounded-lg transition-colors",
                      "hover:bg-muted",
                      parentId === null && "bg-accent text-accent-foreground"
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <FolderIcon className="h-4 w-4" />
                      <span className="flex-1">Root Folder</span>
                    </div>
                  </button>
                  
                  <Separator className="my-2" />
                  
                  {/* Existing folders */}
                  {folderTree.map(folder => renderFolderOption(folder))}
                </div>
              </ScrollArea>
            </div>
          </div>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting || validationErrors.length > 0}>
            {getSubmitButtonText()}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Delete Confirmation Dialog
function DeleteConfirmationDialog({ isOpen, onClose, folder, onConfirm }: DeleteConfirmationProps) {
  const [moveConversationsTo, setMoveConversationsTo] = useState<number | null>(null)
  const [force, setForce] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  
  const folderTree = useFolderTree()
  const hasConversations = folder && folder.conversation_count && folder.conversation_count > 0
  const hasSubfolders = folder && Object.values(useEnhancedFoldersStore.getState().folders).some(f => f.parent_id === folder.id)
  
  const handleConfirm = async () => {
    setIsDeleting(true)
    try {
      await onConfirm(moveConversationsTo || undefined, force)
      onClose()
    } catch (error) {
      console.error('Delete failed:', error)
    } finally {
      setIsDeleting(false)
    }
  }
  
  const renderFolderOption = (folder: Folder, level: number = 0): React.ReactNode => {
    return (
      <div key={folder.id}>
        <button
          type="button"
          onClick={() => setMoveConversationsTo(folder.id)}
          className={cn(
            "w-full text-left px-3 py-2 rounded-lg transition-colors",
            "hover:bg-muted",
            moveConversationsTo === folder.id && "bg-accent text-accent-foreground"
          )}
          style={{ paddingLeft: `${12 + level * 20}px` }}
        >
          <div className="flex items-center gap-2">
            <FolderIcon className="h-4 w-4" />
            <span className="flex-1">{folder.name}</span>
            {folder.conversation_count && folder.conversation_count > 0 && (
              <Badge variant="outline" className="text-xs">
                {folder.conversation_count}
              </Badge>
            )}
          </div>
        </button>
        
        {folder.children?.map(child => renderFolderOption(child, level + 1))}
      </div>
    )
  }
  
  return (
    <AlertDialog open={isOpen} onOpenChange={onClose}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-red-600" />
            Delete Folder
          </AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete the folder "{folder?.name}"?
          </AlertDialogDescription>
        </AlertDialogHeader>
        
        <div className="space-y-4">
          {/* Warning about subfolders */}
          {hasSubfolders && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-yellow-800">This folder contains subfolders</p>
                  <p className="text-sm text-yellow-700 mt-1">
                    All subfolders will also be deleted. Consider moving them first.
                  </p>
                </div>
              </div>
            </div>
          )}
          
          {/* Conversation handling */}
          {hasConversations && (
            <div className="space-y-3">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="flex items-start gap-2">
                  <FileText className="h-4 w-4 text-blue-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-blue-800">
                      This folder contains {folder.conversation_count} conversation(s)
                    </p>
                    <p className="text-sm text-blue-700 mt-1">
                      Choose where to move them, or they will be moved to the root folder.
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="space-y-2">
                <Label>Move conversations to:</Label>
                <div className="border rounded-lg max-h-32 overflow-hidden">
                  <ScrollArea className="h-full max-h-32">
                    <div className="p-2 space-y-1">
                      {/* Root option */}
                      <button
                        type="button"
                        onClick={() => setMoveConversationsTo(null)}
                        className={cn(
                          "w-full text-left px-3 py-2 rounded-lg transition-colors",
                          "hover:bg-muted",
                          moveConversationsTo === null && "bg-accent text-accent-foreground"
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <FolderIcon className="h-4 w-4" />
                          <span className="flex-1">Root Folder</span>
                        </div>
                      </button>
                      
                      <Separator className="my-2" />
                      
                      {/* Other folders */}
                      {folderTree
                        .filter(f => f.id !== folder?.id) // Exclude the folder being deleted
                        .map(folder => renderFolderOption(folder))}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </div>
          )}
          
          {/* Force delete option */}
          {(hasSubfolders || hasConversations) && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={force}
                  onChange={(e) => setForce(e.target.checked)}
                  className="mt-1"
                />
                <div>
                  <p className="text-sm font-medium text-red-800">Force delete</p>
                  <p className="text-sm text-red-700 mt-1">
                    Delete folder and all contents permanently. This action cannot be undone.
                  </p>
                </div>
              </label>
            </div>
          )}
        </div>
        
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isDeleting}
            className="bg-red-600 hover:bg-red-700"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Deleting...
              </>
            ) : (
              'Delete Folder'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

// Main Folder Manager Component
export default function FlawlessFolderManager() {
  const [dialogState, setDialogState] = useState<{
    isOpen: boolean
    mode: 'create' | 'edit' | 'move'
    folder?: Folder
    parentFolder?: Folder
    conversationIds?: number[]
  }>({ isOpen: false, mode: 'create' })
  
  const [deleteState, setDeleteState] = useState<{
    isOpen: boolean
    folder: Folder | null
  }>({ isOpen: false, folder: null })
  
  const { folders, isLoading, actions } = useEnhancedFoldersStore()
  const folderTree = useFolderTree()
  const selectedFolders = useSelectedFolders()
  const pendingOperations = usePendingOperations()
  
  // Load folders on mount
  useEffect(() => {
    actions.loadFolders()
  }, [actions])
  
  // Handle create folder
  const handleCreateFolder = (parentFolder?: Folder) => {
    setDialogState({
      isOpen: true,
      mode: 'create',
      parentFolder
    })
  }
  
  // Handle edit folder
  const handleEditFolder = (folder: Folder) => {
    setDialogState({
      isOpen: true,
      mode: 'edit',
      folder
    })
  }
  
  // Handle move folder
  const handleMoveFolder = (folder: Folder) => {
    setDialogState({
      isOpen: true,
      mode: 'move',
      folder
    })
  }
  
  // Handle delete folder
  const handleDeleteFolder = (folder: Folder) => {
    setDeleteState({
      isOpen: true,
      folder
    })
  }
  
  // Handle delete confirmation
  const handleDeleteConfirm = async (moveConversationsTo?: number, force?: boolean) => {
    if (!deleteState.folder) return
    
    await actions.deleteFolder(deleteState.folder.id, {
      moveConversationsTo,
      force
    })
  }
  
  // Render folder tree item
  const renderFolderItem = (folder: Folder, level: number = 0): React.ReactNode => {
    const hasChildren = folder.children && folder.children.length > 0
    const isExpanded = folder.isExpanded
    const isSelected = folder.isSelected
    const isLoading = folder.isLoading
    const hasError = folder.hasError
    
    return (
      <div key={folder.id} className="select-none">
        <div
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg transition-all",
            "hover:bg-muted cursor-pointer group",
            isSelected && "bg-accent text-accent-foreground",
            hasError && "bg-red-50 border border-red-200",
            isLoading && "opacity-60"
          )}
          style={{ paddingLeft: `${12 + level * 20}px` }}
          onClick={() => actions.selectFolder(folder.id)}
        >
          {/* Expand/Collapse Button */}
          {hasChildren && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                actions.toggleFolder(folder.id)
              }}
              className="h-4 w-4 flex items-center justify-center hover:bg-muted-foreground/20 rounded"
            >
              {isExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </button>
          )}
          
          {/* Folder Icon */}
          <div
            className="h-4 w-4 rounded flex-shrink-0"
            style={{ backgroundColor: folder.color || '#0095ff' }}
          >
            {isExpanded && hasChildren ? (
              <FolderOpen className="h-4 w-4 text-white" />
            ) : (
              <FolderIcon className="h-4 w-4 text-white" />
            )}
          </div>
          
          {/* Folder Name */}
          <span className="flex-1 truncate">{folder.name}</span>
          
          {/* Loading Indicator */}
          {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
          
          {/* Error Indicator */}
          {hasError && (
            <span title={folder.errorMessage}>
              <AlertTriangle className="h-4 w-4 text-red-600" />
            </span>
          )}
          
          {/* Conversation Count */}
          {folder.conversation_count && folder.conversation_count > 0 && (
            <Badge variant="outline" className="text-xs">
              {folder.conversation_count}
            </Badge>
          )}
          
          {/* Action Buttons */}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                handleCreateFolder(folder)
              }}
              className="h-6 w-6 p-0"
              title="Create subfolder"
            >
              <FolderPlus className="h-3 w-3" />
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                handleEditFolder(folder)
              }}
              className="h-6 w-6 p-0"
              title="Edit folder"
            >
              <Edit3 className="h-3 w-3" />
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                handleMoveFolder(folder)
              }}
              className="h-6 w-6 p-0"
              title="Move folder"
            >
              <Move className="h-3 w-3" />
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                handleDeleteFolder(folder)
              }}
              className="h-6 w-6 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
              title="Delete folder"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>
        
        {/* Children */}
        {isExpanded && hasChildren && (
          <div className="ml-2">
            {folder.children?.map(child => renderFolderItem(child, level + 1))}
          </div>
        )}
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FolderIcon className="h-5 w-5" />
                Folder Management
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Organize your conversations with folders
              </p>
            </div>
            
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => actions.refreshFolders()}
                disabled={isLoading}
              >
                <RotateCcw className={cn("h-4 w-4 mr-1", isLoading && "animate-spin")} />
                Refresh
              </Button>
              
              <Button
                size="sm"
                onClick={() => handleCreateFolder()}
                className="gap-2"
              >
                <FolderPlus className="h-4 w-4" />
                New Folder
              </Button>
            </div>
          </div>
        </CardHeader>
        
        <CardContent>
          {/* Pending Operations */}
          {pendingOperations.length > 0 && (
            <div className="mb-4 space-y-2">
              {pendingOperations.map(op => (
                <div key={op.id} className="flex items-center gap-2 text-sm">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span className="capitalize">{op.type}ing folder...</span>
                  {op.status === 'error' && (
                    <span className="text-red-600">Failed: {op.errorMessage}</span>
                  )}
                </div>
              ))}
            </div>
          )}
          
          {/* Selected Folders Info */}
          {selectedFolders.length > 0 && (
            <div className="mb-4 p-3 bg-accent/50 rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {selectedFolders.length} folder(s) selected
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => actions.deselectAllFolders()}
                >
                  Clear Selection
                </Button>
              </div>
            </div>
          )}
          
          {/* Folder Tree */}
          <ScrollArea className="h-[400px]">
            <div className="space-y-1">
              {isLoading && folderTree.length === 0 ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin mr-2" />
                  Loading folders...
                </div>
              ) : folderTree.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <FolderIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="text-sm">No folders yet</p>
                  <p className="text-xs mt-1">Create your first folder to get started</p>
                </div>
              ) : (
                folderTree.map(folder => renderFolderItem(folder))
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
      
      {/* Folder Dialog */}
      <FolderDialog
        isOpen={dialogState.isOpen}
        onClose={() => setDialogState({ isOpen: false, mode: 'create' })}
        mode={dialogState.mode}
        folder={dialogState.folder}
        parentFolder={dialogState.parentFolder}
        conversationIds={dialogState.conversationIds}
      />
      
      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteState.isOpen}
        onClose={() => setDeleteState({ isOpen: false, folder: null })}
        folder={deleteState.folder}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  )
}