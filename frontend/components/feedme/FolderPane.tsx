/**
 * FolderPane Component
 * 
 * Persistent folder navigation panel with:
 * - Folder tree view with hierarchy
 * - Search functionality
 * - "Create Folder" button
 * - Collapsible folder hierarchy
 * - Selection state management
 */

'use client'

import React, { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  Plus, 
  Loader2
} from 'lucide-react'
import { FolderIcon } from '@/components/ui/FolderIcon'
import { cn } from '@/lib/utils'
import { FolderTreeView } from './FolderTreeViewSimple'
import { FolderSearch } from './FolderSearch'
import { useFolders, useFoldersActions } from '@/lib/stores/folders-store'

interface FolderPaneProps {
  selectedFolderId: number | null
  onFolderSelect: (folderId: number | null) => void
  onFolderCreate: () => void
  className?: string
}

export function FolderPane({ 
  selectedFolderId, 
  onFolderSelect, 
  onFolderCreate,
  className 
}: FolderPaneProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const { isLoading, folderTree } = useFolders()
  const foldersActions = useFoldersActions()

  // Filter folders based on search query
  const filteredFolders = useMemo(() => {
    if (!searchQuery.trim()) return folderTree
    
    const query = searchQuery.toLowerCase()
    return folderTree.filter(folder => 
      folder.name.toLowerCase().includes(query) ||
      folder.description?.toLowerCase().includes(query)
    )
  }, [folderTree, searchQuery])

  const handleSearch = (value: string) => {
    setSearchQuery(value)
  }

  const handleClearSearch = () => {
    setSearchQuery('')
  }

  return (
    <div className={cn("feedme-folder-pane flex flex-col h-full bg-sidebar-background", className)}>
      {/* Header */}
      <div className="folder-pane-header p-3 border-b bg-card/30">
        <div className="space-y-3">
          {/* Search Icon/Input */}
          <FolderSearch
            value={searchQuery}
            onChange={handleSearch}
            onClear={handleClearSearch}
          />

          {/* Create Folder Button */}
          <Button 
            onClick={onFolderCreate}
            size="sm"
            className="w-full bg-accent hover:bg-mb-blue-300/90 text-accent-foreground"
            data-testid="create-folder-button"
          >
            <Plus className="h-4 w-4 mr-2" />
            Create Folder
          </Button>
        </div>
      </div>

      {/* Folder Tree */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full folder-tree-container">
          <div className="p-2">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-accent" />
                <span className="ml-2 text-sm text-muted-foreground">Loading folders...</span>
              </div>
            ) : filteredFolders.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <FolderIcon size={32} isOpen={true} color="#95a5a6" alt="No folders" className="mb-2 opacity-50" />
                <p className="text-sm text-muted-foreground">
                  {searchQuery ? 'No folders match your search' : 'No folders yet'}
                </p>
                {!searchQuery && (
                  <Button
                    variant="link"
                    size="sm"
                    onClick={onFolderCreate}
                    className="mt-2 text-accent"
                  >
                    Create your first folder
                  </Button>
                )}
              </div>
            ) : (
              <FolderTreeView
                selectedFolderId={selectedFolderId}
                onFolderSelect={onFolderSelect}
                persistentSelection={true}
                showConversationCounts={true}
                expanded={true}
                className="space-y-1"
              />
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Footer Info */}
      {!isLoading && filteredFolders.length > 0 && (
        <div className="border-t p-2 bg-card/20">
          <p className="text-xs text-muted-foreground text-center">
            {searchQuery 
              ? `${filteredFolders.length} of ${folderTree.length} folders shown`
              : `${folderTree.length} folder${folderTree.length !== 1 ? 's' : ''} total`
            }
          </p>
        </div>
      )}
    </div>
  )
}