/**
 * FeedMe Folder Management Component
 * Provides folder creation, editing, and organization for conversations
 * 
 * Features:
 * - Colored folder organization with preset colors
 * - Folder creation with custom names and colors
 * - Conversation assignment to folders
 * - Folder editing and deletion
 * - Visual folder browser with conversation counts
 */

'use client'

import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Textarea } from '../ui/textarea'
import { Badge } from '../ui/badge'
import { Alert, AlertDescription } from '../ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { 
  Folder, 
  FolderPlus, 
  Edit3, 
  Trash2, 
  Move, 
  Loader2, 
  Palette, 
  Users,
  Settings,
  Check,
  X
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { toast } from '../ui/use-toast'
import {
  listFolders,
  createFolder,
  updateFolder,
  deleteFolder,
  assignConversationsToFolder,
  listFolderConversations,
  type FeedMeFolder,
  type FolderCreate,
  type FolderUpdate,
  type AssignFolderRequest,
  type UploadTranscriptResponse
} from '../../lib/feedme-api'

interface FolderManagerProps {
  isOpen: boolean
  onClose: () => void
  onFolderSelected?: (folder: FeedMeFolder | null) => void
  selectedConversations?: number[]
  onConversationsUpdated?: () => void
}

interface ColorOption {
  name: string
  value: string
  description: string
}

const PRESET_COLORS: ColorOption[] = [
  { name: 'Mailbird Blue', value: '#0095ff', description: 'Default blue' },
  { name: 'Email Red', value: '#e74c3c', description: 'Email issues' },
  { name: 'Sky Blue', value: '#3498db', description: 'Account setup' },
  { name: 'Orange', value: '#f39c12', description: 'Performance' },
  { name: 'Purple', value: '#9b59b6', description: 'Features' },
  { name: 'Amber', value: '#e67e22', description: 'Bug reports' },
  { name: 'Gray', value: '#95a5a6', description: 'General' },
  { name: 'Green', value: '#27ae60', description: 'Resolved' },
  { name: 'Pink', value: '#e91e63', description: 'Priority' },
]

export function FolderManager({
  isOpen,
  onClose,
  onFolderSelected,
  selectedConversations = [],
  onConversationsUpdated
}: FolderManagerProps) {
  // State management
  const [folders, setFolders] = useState<FeedMeFolder[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  
  // Form states
  const [isCreating, setIsCreating] = useState(false)
  const [editingFolder, setEditingFolder] = useState<FeedMeFolder | null>(null)
  const [deleteConfirmFolder, setDeleteConfirmFolder] = useState<FeedMeFolder | null>(null)
  
  // Create/Edit form data
  const [formData, setFormData] = useState<FolderCreate>({
    name: '',
    color: PRESET_COLORS[0].value,
    description: '',
    created_by: 'user@example.com'
  })
  
  // Assignment state
  const [isAssigning, setIsAssigning] = useState(false)
  const [selectedFolderForAssignment, setSelectedFolderForAssignment] = useState<number | null>(null)
  
  // Active tab
  const [activeTab, setActiveTab] = useState<'browse' | 'create' | 'assign'>('browse')

  // Load folders on mount
  useEffect(() => {
    if (isOpen) {
      loadFolders()
      // Set default tab based on props
      if (selectedConversations.length > 0) {
        setActiveTab('assign')
      } else {
        setActiveTab('browse')
      }
    }
  }, [isOpen, selectedConversations])

  const loadFolders = async () => {
    setApiError(null)
    try {
      setIsLoading(true)
      const response = await listFolders()
      setFolders(response.folders)
    } catch (error) {
      console.error('Failed to load folders:', error)
      setApiError(error instanceof Error ? error.message : 'Failed to load folders')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateFolder = async () => {
    if (!formData.name.trim()) {
      toast({
        title: 'Error',
        description: 'Folder name is required',
        variant: 'destructive'
      })
      return
    }

    setApiError(null)
    try {
      setIsCreating(true)
      const newFolder = await createFolder(formData)
      setFolders(prev => [...prev, newFolder])
      
      // Reset form
      setFormData({
        name: '',
        color: PRESET_COLORS[0].value,
        description: '',
        created_by: 'user@example.com'
      })
      
      toast({
        title: 'Success',
        description: `Folder "${newFolder.name}" created successfully`
      })
      
      setActiveTab('browse')
    } catch (error) {
      console.error('Failed to create folder:', error)
      setApiError(error instanceof Error ? error.message : 'Failed to create folder')
    } finally {
      setIsCreating(false)
    }
  }

  const handleEditFolder = async () => {
    if (!editingFolder || !formData.name.trim()) return

    setApiError(null)
    try {
      setIsCreating(true)
      const updateData: FolderUpdate = {
        name: formData.name,
        color: formData.color,
        description: formData.description
      }
      
      const updatedFolder = await updateFolder(editingFolder.id, updateData)
      setFolders(prev => prev.map(f => f.id === editingFolder.id ? updatedFolder : f))
      
      setEditingFolder(null)
      setFormData({
        name: '',
        color: PRESET_COLORS[0].value,
        description: '',
        created_by: 'user@example.com'
      })
      
      toast({
        title: 'Success',
        description: `Folder "${updatedFolder.name}" updated successfully`
      })
    } catch (error) {
      console.error('Failed to update folder:', error)
      setApiError(error instanceof Error ? error.message : 'Failed to update folder')
    } finally {
      setIsCreating(false)
    }
  }

  const handleDeleteFolder = async (folder: FeedMeFolder, moveToFolderId?: number) => {
    setApiError(null)
    try {
      setIsLoading(true)
      await deleteFolder(folder.id, moveToFolderId)
      setFolders(prev => prev.filter(f => f.id !== folder.id))
      
      setDeleteConfirmFolder(null)
      
      toast({
        title: 'Success',
        description: `Folder "${folder.name}" deleted successfully`
      })
    } catch (error) {
      console.error('Failed to delete folder:', error)
      setApiError(error instanceof Error ? error.message : 'Failed to delete folder')
    } finally {
      setIsLoading(false)
    }
  }

  const handleAssignToFolder = async (folderId: number | null) => {
    if (selectedConversations.length === 0) return

    setApiError(null)
    try {
      setIsAssigning(true)
      const assignRequest: AssignFolderRequest = {
        folder_id: folderId,
        conversation_ids: selectedConversations
      }
      
      const response = await assignConversationsToFolder(assignRequest)
      
      toast({
        title: 'Success',
        description: response.message
      })
      
      // Refresh folders to update conversation counts
      await loadFolders()
      
      // Notify parent component
      if (onConversationsUpdated) {
        onConversationsUpdated()
      }
      
      onClose()
    } catch (error) {
      console.error('Failed to assign conversations:', error)
      setApiError(error instanceof Error ? error.message : 'Failed to assign conversations')
    } finally {
      setIsAssigning(false)
    }
  }

  const startEditFolder = (folder: FeedMeFolder) => {
    setEditingFolder(folder)
    setFormData({
      name: folder.name,
      color: folder.color,
      description: folder.description || '',
      created_by: folder.created_by || 'user@example.com'
    })
    setActiveTab('create')
  }

  const cancelEdit = () => {
    setEditingFolder(null)
    setFormData({
      name: '',
      color: PRESET_COLORS[0].value,
      description: '',
      created_by: 'user@example.com'
    })
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Folder className="h-5 w-5" />
            Folder Management
            {selectedConversations.length > 0 && (
              <Badge variant="secondary">
                {selectedConversations.length} conversations selected
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            Organize your conversations with colored folders for better management and navigation.
          </DialogDescription>
        </DialogHeader>

        {apiError && (
          <Alert variant="destructive" className="my-4">
            <AlertDescription>{apiError}</AlertDescription>
          </Alert>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="browse" className="flex items-center gap-2">
              <Folder className="h-4 w-4" />
              Browse Folders
              {folders.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {folders.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="create" className="flex items-center gap-2">
              <FolderPlus className="h-4 w-4" />
              {editingFolder ? 'Edit Folder' : 'Create Folder'}
            </TabsTrigger>
            {selectedConversations.length > 0 && (
              <TabsTrigger value="assign" className="flex items-center gap-2">
                <Move className="h-4 w-4" />
                Assign to Folder
              </TabsTrigger>
            )}
          </TabsList>

          {/* Browse Folders Tab */}
          <TabsContent value="browse" className="flex-1 overflow-auto mt-4">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin" />
                <span className="ml-2">Loading folders...</span>
              </div>
            ) : folders.length === 0 ? (
              <div className="text-center py-8">
                <Folder className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium mb-2">No folders yet</h3>
                <p className="text-muted-foreground mb-4">
                  Create your first folder to organize conversations
                </p>
                <Button onClick={() => setActiveTab('create')}>
                  <FolderPlus className="h-4 w-4 mr-2" />
                  Create Folder
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {folders.map((folder) => (
                  <Card key={folder.id} className="hover:shadow-md transition-shadow">
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div 
                            className="w-4 h-4 rounded-full border border-gray-300"
                            style={{ backgroundColor: folder.color }}
                          />
                          <CardTitle className="text-base">{folder.name}</CardTitle>
                        </div>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => startEditFolder(folder)}
                          >
                            <Edit3 className="h-3 w-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteConfirmFolder(folder)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      {folder.description && (
                        <CardDescription className="text-xs">
                          {folder.description}
                        </CardDescription>
                      )}
                    </CardHeader>
                    <CardContent className="pt-0">
                      <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-1 text-muted-foreground">
                          <Users className="h-3 w-3" />
                          {folder.conversation_count} conversations
                        </div>
                        {onFolderSelected && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onFolderSelected(folder)}
                          >
                            View
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Create/Edit Folder Tab */}
          <TabsContent value="create" className="flex-1 overflow-auto mt-4">
            <div className="space-y-6 max-w-md mx-auto">
              <div>
                <Label htmlFor="folder-name">Folder Name</Label>
                <Input
                  id="folder-name"
                  value={formData.name}
                  onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Enter folder name..."
                  className="mt-1"
                />
              </div>

              <div>
                <Label>Folder Color</Label>
                <div className="grid grid-cols-3 gap-2 mt-2">
                  {PRESET_COLORS.map((color) => (
                    <button
                      key={color.value}
                      type="button"
                      className={cn(
                        "flex items-center gap-2 p-2 rounded-md border text-left text-sm hover:bg-gray-50 transition-colors",
                        formData.color === color.value && "ring-2 ring-accent"
                      )}
                      onClick={() => setFormData(prev => ({ ...prev, color: color.value }))}
                    >
                      <div 
                        className="w-4 h-4 rounded-full border border-gray-300"
                        style={{ backgroundColor: color.value }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="font-medium truncate">{color.name}</div>
                        <div className="text-xs text-muted-foreground truncate">{color.description}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <Label htmlFor="folder-description">Description (Optional)</Label>
                <Textarea
                  id="folder-description"
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Brief description of this folder's purpose..."
                  className="mt-1"
                  rows={3}
                />
              </div>

              <div className="flex gap-2">
                {editingFolder ? (
                  <>
                    <Button 
                      onClick={handleEditFolder} 
                      disabled={isCreating || !formData.name.trim()}
                      className="flex-1"
                    >
                      {isCreating ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Check className="h-4 w-4 mr-2" />
                      )}
                      Update Folder
                    </Button>
                    <Button variant="outline" onClick={cancelEdit}>
                      <X className="h-4 w-4 mr-2" />
                      Cancel
                    </Button>
                  </>
                ) : (
                  <Button 
                    onClick={handleCreateFolder} 
                    disabled={isCreating || !formData.name.trim()}
                    className="flex-1"
                  >
                    {isCreating ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <FolderPlus className="h-4 w-4 mr-2" />
                    )}
                    Create Folder
                  </Button>
                )}
              </div>
            </div>
          </TabsContent>

          {/* Assign Conversations Tab */}
          {selectedConversations.length > 0 && (
            <TabsContent value="assign" className="flex-1 overflow-auto mt-4">
              <div className="space-y-4 max-w-md mx-auto">
                <div className="text-center">
                  <h3 className="text-lg font-medium mb-2">
                    Assign {selectedConversations.length} conversations
                  </h3>
                  <p className="text-muted-foreground mb-4">
                    Choose a folder to organize these conversations
                  </p>
                </div>

                <div className="space-y-2">
                  {/* Option to remove from folders */}
                  <button
                    className="w-full flex items-center gap-3 p-3 rounded-md border hover:bg-gray-50 transition-colors text-left"
                    onClick={() => handleAssignToFolder(null)}
                    disabled={isAssigning}
                  >
                    <div className="w-4 h-4 rounded-full border border-gray-300 bg-gray-100" />
                    <div className="flex-1">
                      <div className="font-medium">No Folder</div>
                      <div className="text-sm text-muted-foreground">Remove from all folders</div>
                    </div>
                  </button>

                  {/* Folder options */}
                  {folders.map((folder) => (
                    <button
                      key={folder.id}
                      className="w-full flex items-center gap-3 p-3 rounded-md border hover:bg-gray-50 transition-colors text-left"
                      onClick={() => handleAssignToFolder(folder.id)}
                      disabled={isAssigning}
                    >
                      <div 
                        className="w-4 h-4 rounded-full border border-gray-300"
                        style={{ backgroundColor: folder.color }}
                      />
                      <div className="flex-1">
                        <div className="font-medium">{folder.name}</div>
                        <div className="text-sm text-muted-foreground">
                          {folder.conversation_count} conversations
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                {isAssigning && (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Assigning conversations...
                  </div>
                )}
              </div>
            </TabsContent>
          )}
        </Tabs>

        {/* Delete Confirmation Dialog */}
        {deleteConfirmFolder && (
          <Dialog open={!!deleteConfirmFolder} onOpenChange={() => setDeleteConfirmFolder(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete Folder</DialogTitle>
                <DialogDescription>
                  Are you sure you want to delete "{deleteConfirmFolder.name}"? 
                  {deleteConfirmFolder.conversation_count > 0 && (
                    <span className="block mt-2 text-amber-600">
                      This folder contains {deleteConfirmFolder.conversation_count} conversations.
                      They will be moved to "No Folder".
                    </span>
                  )}
                </DialogDescription>
              </DialogHeader>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setDeleteConfirmFolder(null)}>
                  Cancel
                </Button>
                <Button 
                  variant="destructive" 
                  onClick={() => handleDeleteFolder(deleteConfirmFolder)}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-2" />
                  )}
                  Delete Folder
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </DialogContent>
    </Dialog>
  )
}