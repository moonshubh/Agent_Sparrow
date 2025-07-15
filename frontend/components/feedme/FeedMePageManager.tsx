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
import { UnifiedSearchBar } from './UnifiedSearchBarSimple'
import { FileGridView } from './FileGridViewSimple'
import { ConversationEditor } from './ConversationEditorSimple'
import { AnalyticsDashboard } from './AnalyticsDashboardSimple'
import { EnhancedFeedMeModal } from './EnhancedFeedMeModal'
import { FeedMeErrorBoundary } from './ErrorBoundary'

// Import new two-panel components
import { SidebarNav } from './SidebarNav'
import { SecondaryFolderPanel } from './SecondaryFolderPanel'

// Import modular store hooks
import { useConversations } from '@/lib/stores/conversations-store'
import { useRealtime } from '@/lib/stores/realtime-store'
import { useFolders, useFoldersActions, useFolderModals } from '@/lib/stores/folders-store'
import { useUIPanels, useUIResponsive } from '@/lib/stores/ui-store'
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
      <div className="h-screen flex bg-background">
        {/* Main Sidebar (Desktop Only) */}
        {!isMobile && (
          <SidebarNav
            activeTab={rightPanel === 'editor' ? 'conversations' : rightPanel}
            onTabChange={(tab) => {
              if (tab === 'conversations') uiActions.setRightPanel('conversations')
              else if (tab === 'analytics') uiActions.setRightPanel('analytics')
              else if (tab === 'folders') uiActions.setLeftPanel('folders')
            }}
            conversationCount={conversations.totalCount || 0}
            folderCount={Object.keys(folders.folders).length}
          />
        )}

        {/* Secondary Folder Panel */}
        <SecondaryFolderPanel
          selectedFolderId={conversations.currentFolderId === undefined ? null : conversations.currentFolderId}
          onFolderSelect={handleFolderSelect}
          onFolderCreate={openFolderCreateModal}
        />

        {/* Main Content */}
        <main className="flex-1 overflow-hidden flex flex-col transition-all duration-300">
          {/* Search Bar */}
          <div className="border-b px-4 py-3 bg-card/50">
            <UnifiedSearchBar />
          </div>

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
            
            {rightPanel === 'analytics' && (
              <AnalyticsDashboard />
            )}
            
            {rightPanel === 'editor' && selectedConversationId && (
              <ConversationEditor
                conversationId={selectedConversationId}
                isOpen={true}
                onClose={handleConversationClose}
              />
            )}
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
      </div>
    </FeedMeErrorBoundary>
  )
}
