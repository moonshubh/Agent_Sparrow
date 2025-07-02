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

import React, { useState, useEffect, useRef } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog'
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
  type FeedMeFolder,
  type FolderCreate,
  type FolderUpdate,
  type AssignFolderRequest
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
    description: ''
  })
  
  // Assignment state
  const [isAssigning, setIsAssigning] = useState(false)
  const [selectedFolderForAssignment, setSelectedFolderForAssignment] = useState<number | null>(null)
  
  // Active tab
  const [activeTab, setActiveTab] = useState<'browse' | 'create' | 'assign'>('browse')

  const nameInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (activeTab === 'create' && editingFolder) {
      // Timeout to allow tab content to render before focusing
      setTimeout(() => nameInputRef.current?.focus(), 50)
    }
  }, [activeTab, editingFolder])

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
    setIsLoading(true)
    setApiError(null)
    try {
      const response = await listFolders()
      setFolders(response.folders)
    } catch (error) {
      console.error('Failed to load folders:', error)
      setApiError('Failed to load folders. Please check the connection and try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCreateFolder = async () => {
    if (!formData.name.trim()) {
      setApiError('Folder name is required.');
      return;
    }

    setIsCreating(true);
    setApiError(null);

    try {
      const folderName = formData.name;
      await createFolder(formData);
      
      toast({
        title: 'Folder Created',
        description: `"${folderName}" has been successfully created.`,
      });
      
      // Reset form and switch tab before reloading data
      setFormData({ name: '', color: PRESET_COLORS[0].value, description: '' });
      setActiveTab('browse');
      
      // Refresh the folder list from the server to ensure consistency
      await loadFolders();

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
      setApiError(errorMessage);
      toast({
        title: 'Error Creating Folder',
        description: errorMessage,
        variant: 'destructive',
      });
    } finally {
      setIsCreating(false);
    }
  };

  const handleEditFolder = async () => {
    if (!editingFolder) return
    
    setApiError(null)
    setIsCreating(true) // Reuse creating state for loading indicator
    
    try {
      await updateFolder(editingFolder.id, formData)
      toast({
        title: 'Folder Updated',
        description: `Folder "${formData.name}" was successfully updated.`,
      })
      await loadFolders()
      cancelEdit()
    } catch (error) {
      console.error('Failed to update folder:', error)
      setApiError('Failed to update folder. Please try again.')
    } finally {
      setIsCreating(false)
    }
  }

  const handleDeleteFolder = async (folder: FeedMeFolder, moveToFolderId?: number) => {
    setApiError(null)
    setIsLoading(true)
    
    try {
      await deleteFolder(folder.id, moveToFolderId)
      toast({
        title: 'Folder Deleted',
        description: `Folder "${folder.name}" was successfully deleted.`,
      })
      await loadFolders()
      setDeleteConfirmFolder(null)
    } catch (error) {
      console.error('Failed to delete folder:', error)
      setApiError('Failed to delete folder. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleAssignToFolder = async (folderId: number | null) => {
    if (selectedConversations.length === 0) {
      toast({
        title: 'No Conversations Selected',
        description: 'Please select conversations to assign.',
        variant: 'destructive',
      })
      return
    }

    setApiError(null)
    setIsAssigning(true)
    setSelectedFolderForAssignment(folderId)

    try {
      const request: AssignFolderRequest = {
        folder_id: folderId,
        conversation_ids: selectedConversations,
      }
      await assignConversationsToFolder(request)
      toast({
        title: 'Conversations Assigned',
        description: `${selectedConversations.length} conversations have been assigned.`,
      })
      if (onConversationsUpdated) {
        onConversationsUpdated()
      }
      onClose()
    } catch (error) {
      console.error('Failed to assign conversations:', error)
      setApiError('Failed to assign conversations. Please try again.')
    } finally {
      setIsAssigning(false)
      setSelectedFolderForAssignment(null)
    }
  }
  
  const startEditFolder = (folder: FeedMeFolder) => {
    setEditingFolder(folder)
    setFormData({
      name: folder.name,
      color: folder.color,
      description: folder.description || ''
    })
    setActiveTab('create') // Reuse create tab for editing
  }

  const cancelEdit = () => {
    setEditingFolder(null)
    setFormData({
      name: '',
      color: PRESET_COLORS[0].value,
      description: ''
    })
    setActiveTab('browse')
  }
  
  const renderContent = () => {
    if (isLoading && folders.length === 0) {
      return (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          <span className="ml-3 text-gray-500">Loading folders...</span>
        </div>
      )
    }

    if (apiError) {
      return (
        <Alert variant="destructive" className="my-4">
          <AlertDescription>{apiError}</AlertDescription>
        </Alert>
      )
    }

    return null
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Folder Management</DialogTitle>
          <DialogDescription>
            Organize your conversations with colored folders for better management and navigation.
          </DialogDescription>
        </DialogHeader>

        {renderContent() || (
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="flex-grow flex flex-col">
            <TabsList>
              <TabsTrigger value="browse">
                <Folder className="h-4 w-4 mr-2" />
                Browse Folders ({folders.length})
              </TabsTrigger>
              <TabsTrigger value="create">
                <FolderPlus className="h-4 w-4 mr-2" />
                {editingFolder ? 'Edit Folder' : 'Create New Folder'}
              </TabsTrigger>
              {selectedConversations.length > 0 && (
                <TabsTrigger value="assign">
                  <Move className="h-4 w-4 mr-2" />
                  Assign to Folder
                </TabsTrigger>
              )}
            </TabsList>

            {/* Browse Folders Tab */}
            <TabsContent value="browse" className="flex-grow overflow-y-auto p-1">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {folders.map((folder) => (
                  <Card key={folder.id} className="flex flex-col">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full" style={{ backgroundColor: folder.color }} />
                        <span className="flex-1 truncate">{folder.name}</span>
                      </CardTitle>
                      <CardDescription>{folder.description || 'No description'}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex-grow flex items-end justify-between">
                      <Badge variant="secondary">{folder.conversation_count} items</Badge>
                      <div className="flex gap-2">
                        <Button variant="ghost" size="icon" onClick={() => startEditFolder(folder)}>
                          <Edit3 className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="text-red-500 hover:text-red-600" onClick={() => setDeleteConfirmFolder(folder)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {folders.length === 0 && (
                <div className="flex items-center justify-center h-64">
                  <div className="text-center">
                    <Folder className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                    <h3 className="text-lg font-medium mb-2">No folders yet</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Create your first folder to organize conversations
                    </p>
                    <Button onClick={() => setActiveTab('create')}>
                      <FolderPlus className="h-4 w-4 mr-2" />
                      Create Folder
                    </Button>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* Create/Edit Folder Tab */}
            <TabsContent value="create" className="flex-grow overflow-y-auto p-1">
              <div className="max-w-md mx-auto">
                <h3 className="text-lg font-medium mb-4">
                  {editingFolder ? 'Edit Folder Details' : 'Create a New Folder'}
                </h3>
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (editingFolder) {
                      void handleEditFolder()
                    } else {
                      void handleCreateFolder()
                    }
                  }}
                >
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="folder-name">Folder Name</Label>
                      <Input
                        id="folder-name"
                        ref={nameInputRef}
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g., 'High Priority Tickets'"
                      />
                    </div>
                    <div>
                      <Label htmlFor="folder-description">Description</Label>
                      <Textarea
                        id="folder-description"
                        value={formData.description || ''}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        placeholder="A brief description of what this folder is for"
                      />
                    </div>
                    <div>
                      <Label>Folder Color</Label>
                      <div className="grid grid-cols-3 gap-2 mt-2">
                        {PRESET_COLORS.map((color) => (
                          <button
                            type="button"
                            key={color.value}
                            className={cn(
                              'p-2 rounded-md border-2 flex items-center gap-2 hover:bg-gray-50',
                              formData.color === color.value ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
                            )}
                            onClick={() => setFormData({ ...formData, color: color.value })}
                          >
                            <div className="w-5 h-5 rounded-full" style={{ backgroundColor: color.value }} />
                            <span className="text-sm">{color.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button type="submit" disabled={isCreating || !formData.name.trim()}>
                        {isCreating ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        ) : editingFolder ? (
                          <Check className="h-4 w-4 mr-2" />
                        ) : (
                          <FolderPlus className="h-4 w-4 mr-2" />
                        )}
                        {editingFolder ? 'Save Changes' : 'Create Folder'}
                      </Button>
                      {editingFolder && (
                        <Button variant="outline" type="button" onClick={cancelEdit}>
                          <X className="h-4 w-4 mr-2" />
                          Cancel
                        </Button>
                      )}
                    </div>
                  </div>
                </form>
              </div>
            </TabsContent>

            {/* Assign to Folder Tab */}
            {selectedConversations.length > 0 && (
              <TabsContent value="assign" className="flex-grow overflow-y-auto p-1">
                <div className="max-w-md mx-auto">
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
        )}

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