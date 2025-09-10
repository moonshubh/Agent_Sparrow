/**
 * FeedMe Page Manager
 * Full-page version of the FeedMe interface with advanced enterprise features
 * 
 * Features:
 * - Unified search bar with smart autocomplete
 * - Folder tree view with hierarchical organization
 * - File grid view with virtual scrolling
 * - Conversation editor with AI assistance
 * - Analytics dashboard
 * - Real-time updates via WebSocket
 */

'use client'

import React, { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { 
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

// Import the FeedMe components
import { FileGridView } from './FileGridViewSimple'
import { AnalyticsDashboard } from './AnalyticsDashboardSimple'
import { EnhancedFeedMeModal } from './EnhancedFeedMeModal'
import ConversationEditorPanel from './ConversationEditorPanel'
import { FeedMeErrorBoundary } from './ErrorBoundary'

// Import new two-panel components
import { SecondaryFolderPanel } from './SecondaryFolderPanel'

// Import modular store hooks
import { useConversations } from '@/lib/stores/conversations-store'
import { useRealtime } from '@/lib/stores/realtime-store'
import { useFolders, useFoldersActions, useFolderModals } from '@/lib/stores/folders-store'
import { useUIPanels, useUIResponsive, useUIActions } from '@/lib/stores/ui-store'
import { useStoreInitialization } from '@/lib/stores/store-composition'

// Import custom hooks for extracted functionality
import { useFeedMeModals } from '@/hooks/useFeedMeModals'
import { useFeedMeNavigation } from '@/hooks/useFeedMeNavigation'

export function FeedMePageManager() {
  // Extract functionality into custom hooks
  const {
    uploadModalOpen,
    folderFormData,
    openUploadModal,
    closeUploadModal,
    openFolderCreateModal,
    updateFolderForm,
    handleCreateFolder,
  } = useFeedMeModals()

  const {
    handleTabChange,
    handleConversationSelect,
    handleConversationClose,
    handleFolderSelect,
    handleConversationMove,
  } = useFeedMeNavigation()

  // Store hooks - only what's needed for rendering
  const { rightPanel, selectedConversationId } = useUIPanels()
  const uiActions = useUIActions()
  const { isMobile } = useUIResponsive()
  const conversations = useConversations()
  const { notifications } = useRealtime()
  const folders = useFolders()
  const foldersActions = useFoldersActions()
  const folderModals = useFolderModals()

  // Auto-initialize all stores with cross-store synchronization
  useStoreInitialization()
  
  // Additional page-specific initialization
  useEffect(() => {
    console.log('FeedMe Page Manager ready')
  }, [])

  const unreadNotifications = notifications.filter(n => !n.read).length

  return (
    <FeedMeErrorBoundary>
      <div className="h-screen flex bg-background overflow-hidden">
        {/* Sidebar removed in new layout; navigation is now in top-right header */}

        {/* Secondary Folder Panel */}
        <SecondaryFolderPanel
          selectedFolderId={conversations.currentFolderId === undefined ? null : conversations.currentFolderId}
          onFolderSelect={handleFolderSelect}
          onFolderCreate={openFolderCreateModal}
        />

        {/* Main Content */}
        <main className="flex-1 overflow-hidden flex flex-col transition-all duration-300">
          {/* Top bar handled in page.tsx; keep content clean */}

          {/* Content Area */}
          <div className="flex-1 overflow-hidden">
            {rightPanel === 'conversations' && (
              <FileGridView 
                onConversationSelect={handleConversationSelect}
                currentFolderId={conversations.currentFolderId ?? null}
                onFolderSelect={handleFolderSelect}
                onConversationMove={handleConversationMove}
              />
            )}

            {rightPanel === 'editor' && (
              <div className="w-full">
                {selectedConversationId ? (
                  <ConversationEditorPanel />
                ) : (
                  <div className="flex-1 flex items-center justify-center text-muted-foreground">
                    <div className="text-center">
                      <p className="text-lg font-medium">Select a conversation</p>
                      <p className="text-sm mt-1">Choose a conversation from the list to view and edit its content</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {rightPanel === 'analytics' && (
              <AnalyticsDashboard />
            )}
            
            {/* Legacy modal editor removed in unified canvas flow */}
          </div>
        </main>


      {/* Upload Modal */}
      <EnhancedFeedMeModal 
        isOpen={uploadModalOpen}
        onClose={closeUploadModal}
      />
      
      {/* Create Folder Modal */}
      <Dialog open={folderModals.createModalOpen} onOpenChange={() => foldersActions.closeModals()}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Create New Folder</DialogTitle>
            <DialogDescription>
              Create a new folder to organize your conversations.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="folder-name" className="text-right">
                Name
              </Label>
              <Input
                id="folder-name"
                value={folderFormData.name}
                onChange={(e) => updateFolderForm({ name: e.target.value })}
                placeholder="Folder name"
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="folder-color" className="text-right">
                Color
              </Label>
              <Input
                id="folder-color"
                type="color"
                value={folderFormData.color}
                onChange={(e) => updateFolderForm({ color: e.target.value })}
                className="col-span-3 h-10"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="folder-description" className="text-right">
                Description
              </Label>
              <Textarea
                id="folder-description"
                value={folderFormData.description}
                onChange={(e) => updateFolderForm({ description: e.target.value })}
                placeholder="Optional description"
                className="col-span-3"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => foldersActions.closeModals()}>
              Cancel
            </Button>
            <Button onClick={handleCreateFolder} disabled={!folderFormData.name.trim()}>
              Create Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
      {/* Edit Folder Modal */}
      <Dialog open={folderModals.editModalOpen} onOpenChange={() => foldersActions.closeModals()}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Edit Folder</DialogTitle>
            <DialogDescription>
              Update the folder details.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="edit-folder-name" className="text-right">
                Name
              </Label>
              <Input
                id="edit-folder-name"
                value={folderFormData.name}
                onChange={(e) => updateFolderForm({ name: e.target.value })}
                placeholder="Folder name"
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="edit-folder-color" className="text-right">
                Color
              </Label>
              <Input
                id="edit-folder-color"
                type="color"
                value={folderFormData.color}
                onChange={(e) => updateFolderForm({ color: e.target.value })}
                className="col-span-3 h-10"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="edit-folder-description" className="text-right">
                Description
              </Label>
              <Textarea
                id="edit-folder-description"
                value={folderFormData.description}
                onChange={(e) => updateFolderForm({ description: e.target.value })}
                placeholder="Optional description"
                className="col-span-3"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => foldersActions.closeModals()}>
              Cancel
            </Button>
            <Button 
              onClick={async () => {
                if (folderModals.targetFolderId) {
                  await foldersActions.updateFolder(folderModals.targetFolderId, {
                    name: folderFormData.name,
                    color: folderFormData.color,
                    description: folderFormData.description
                  })
                  foldersActions.closeModals()
                }
              }} 
              disabled={!folderFormData.name.trim()}
            >
              Update Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
      {/* Delete Folder Modal */}
      <Dialog open={folderModals.deleteModalOpen} onOpenChange={() => foldersActions.closeModals()}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Delete Folder</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this folder? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground">
              All conversations in this folder will be moved to "All Conversations".
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => foldersActions.closeModals()}>
              Cancel
            </Button>
            <Button 
              variant="destructive" 
              onClick={async () => {
                if (folderModals.targetFolderId) {
                  await foldersActions.deleteFolder(folderModals.targetFolderId)
                  foldersActions.closeModals()
                }
              }}
            >
              Delete Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </div>
    </FeedMeErrorBoundary>
  )
}
