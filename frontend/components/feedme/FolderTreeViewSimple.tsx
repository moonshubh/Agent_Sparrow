/**
 * FolderTreeView Component - Simplified Version
 * 
 * Hierarchical folder structure with expand/collapse functionality.
 * Simplified version that works without complex tree virtualization.
 */

'use client'

import React, { useState, useCallback } from 'react'
import { ChevronRight, ChevronDown, Folder, FolderOpen, MoreHorizontal, Plus, MessageCircle } from 'lucide-react'
import { useFolders, useFoldersActions } from '@/lib/stores/folders-store'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface FolderTreeViewProps {
  onConversationSelect?: (conversationId: number) => void
  onFolderSelect?: (folderId: number | null) => void
  expanded?: boolean
  className?: string
}

interface Folder {
  id: number
  name: string
  parent_id: number | null
  conversation_count: number
  isExpanded?: boolean
  path?: string
  description?: string
  color?: string
  created_at: string
  updated_at: string
  children?: Folder[]
}

interface FolderItemProps {
  folder: Folder
  level: number
  onSelect?: (folderId: number) => void
  onFolderSelect?: (folderId: number | null) => void
}

const FolderItem: React.FC<FolderItemProps> = ({ folder, level, onSelect, onFolderSelect }) => {
  const actions = useFoldersActions()
  const [isExpanded, setIsExpanded] = useState(folder.isExpanded || false)
  const isUnassignedFolder = folder.id === 0

  const handleToggle = useCallback(() => {
    // Don't allow toggling for unassigned folder (it doesn't have children)
    if (isUnassignedFolder) return
    
    setIsExpanded(!isExpanded)
    actions.expandFolder(folder.id, !isExpanded)
  }, [isExpanded, folder.id, actions, isUnassignedFolder])

  const handleSelect = useCallback(() => {
    onSelect?.(folder.id)
    onFolderSelect?.(folder.id) // Trigger conversation filtering
    actions.selectFolder(folder.id, true)
  }, [folder.id, onSelect, onFolderSelect, actions])

  return (
    <div className="w-full">
      <div 
        className={cn(
          "flex items-center gap-2 px-2 py-1 hover:bg-mb-blue-300/50 cursor-pointer rounded-sm",
          folder.isSelected && "bg-accent/30",
          isUnassignedFolder && "border-b border-border/40 mb-2"
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={handleSelect}
      >
        {!isUnassignedFolder && (
          <Button
            variant="ghost"
            size="sm"
            className="h-4 w-4 p-0"
            onClick={(e) => {
              e.stopPropagation()
              handleToggle()
            }}
          >
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </Button>
        )}

        {isUnassignedFolder ? (
          <MessageCircle className="h-4 w-4 text-accent ml-6" aria-label="Unassigned folder icon" />
        ) : isExpanded ? (
          <FolderOpen className="h-4 w-4 text-blue-500" />
        ) : (
          <Folder className="h-4 w-4 text-blue-500" />
        )}

        <span className={cn(
          "flex-1 text-sm truncate",
          isUnassignedFolder && "font-medium text-accent"
        )}>{folder.name}</span>

        <Badge variant="secondary" className="text-xs">
          {folder.conversation_count || 0}
        </Badge>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
              <MoreHorizontal className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => actions.createFolder("New Subfolder")}>
              <Plus className="h-4 w-4 mr-2" />
              Add Subfolder
            </DropdownMenuItem>
            <DropdownMenuItem 
              onClick={() => actions.deleteFolder(folder.id)}
              className="text-destructive"
            >
              Delete Folder
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

export function FolderTreeView({ 
  onConversationSelect, 
  onFolderSelect,
  expanded = false,
  className 
}: FolderTreeViewProps) {
  const { folders } = useFolders()
  const actions = useFoldersActions()
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')

  const folderList = folders ? Object.values(folders).sort((a, b) => a.name?.localeCompare(b.name) || 0) : []

  const handleCreateFolder = useCallback(async () => {
    if (newFolderName.trim()) {
      try {
        await actions.createFolder(newFolderName.trim())
        setIsCreateModalOpen(false)
        setNewFolderName('')
      } catch (error) {
        // Error handling is done in the store action
      }
    }
  }, [actions, newFolderName])

  const handleOpenCreateModal = useCallback(() => {
    setIsCreateModalOpen(true)
    setNewFolderName('')
  }, [])

  const handleCloseCreateModal = useCallback(() => {
    setIsCreateModalOpen(false)
    setNewFolderName('')
  }, [])

  return (
    <div className={cn("h-full flex flex-col", className)}>

      {/* Tree Content */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {/* All Conversations item */}
          <div 
            className="flex items-center gap-2 px-2 py-1 hover:bg-mb-blue-300/50 cursor-pointer rounded-sm"
            onClick={() => onFolderSelect?.(null)}
          >
            <div className="h-4 w-4" /> {/* Spacer for alignment */}
            <FolderOpen className="h-4 w-4 text-accent" />
            <span className="flex-1 text-sm font-medium">All Conversations</span>
          </div>
          
          {/* Unassigned conversations */}
          <div 
            className="flex items-center gap-2 px-2 py-1 hover:bg-mb-blue-300/50 cursor-pointer rounded-sm"
            onClick={() => onFolderSelect?.(0)}
          >
            <div className="h-4 w-4" /> {/* Spacer for alignment */}
            <Folder className="h-4 w-4 text-muted-foreground" />
            <span className="flex-1 text-sm">Unassigned</span>
          </div>
          
          {folderList.length === 0 ? (
            <div className="text-center text-muted-foreground p-4">
              <Folder className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No folders yet</p>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCreateFolder}
                className="mt-2"
              >
                <Plus className="h-4 w-4 mr-2" />
                Create Folder
              </Button>
            </div>
          ) : (
            folderList.map((folder) => (
              <FolderItem
                key={folder.id}
                folder={folder}
                level={0}
                onSelect={onConversationSelect}
                onFolderSelect={onFolderSelect}
              />
            ))
          )}
        </div>
      </ScrollArea>
      
      {/* Create Folder Modal */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Create New Folder</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="folder-name" className="text-right">
                Name
              </Label>
              <Input
                id="folder-name"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                className="col-span-3"
                placeholder="Enter folder name"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleCreateFolder()
                  }
                }}
                autoFocus
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCloseCreateModal}>
              Cancel
            </Button>
            <Button 
              onClick={handleCreateFolder}
              disabled={!newFolderName.trim()}
            >
              Create Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}