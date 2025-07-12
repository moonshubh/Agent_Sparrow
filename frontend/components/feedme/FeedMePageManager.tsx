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

import React, { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { 
  Home, 
  Upload, 
  FolderOpen, 
  BarChart3, 
  Settings,
  Bell
} from 'lucide-react'
import { cn } from '@/lib/utils'

// Import the FeedMe components
import { UnifiedSearchBar } from './UnifiedSearchBarSimple'
import { FolderTreeView } from './FolderTreeViewSimple'
import { FileGridView } from './FileGridViewSimple'
import { ConversationEditor } from './ConversationEditorSimple'
import { AnalyticsDashboard } from './AnalyticsDashboardSimple'
import { EnhancedFeedMeModal } from './EnhancedFeedMeModal'
import { FeedMeErrorBoundary } from './ErrorBoundary'

// Import new two-panel components
import { SidebarNav } from './SidebarNav'
import { SecondaryFolderPanel } from './SecondaryFolderPanel'
import { ThemeSwitch } from './ThemeSwitch'
import { MobileDrawer } from './MobileDrawer'

// Import modular store hooks - NO legacy dependencies
import { useConversations, useConversationsActions } from '@/lib/stores/conversations-store'
import { useRealtime, useRealtimeActions } from '@/lib/stores/realtime-store'
import { useSearch, useSearchActions } from '@/lib/stores/search-store'
import { useFolders, useFoldersActions, useFolderModals } from '@/lib/stores/folders-store'
import { useAnalytics, useAnalyticsActions } from '@/lib/stores/analytics-store'
import { useUITabs, useUIPanels, useUIActions, useUIResponsive } from '@/lib/stores/ui-store'
import { useStoreInitialization } from '@/lib/stores/store-composition'

export function FeedMePageManager() {
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  
  // Folder modal state
  const [folderName, setFolderName] = useState('')
  const [folderDescription, setFolderDescription] = useState('')
  const [folderColor, setFolderColor] = useState('#0095ff')

  // Modular store hooks - specific subscriptions for performance
  const { activeTab } = useUITabs()
  const { leftPanel, rightPanel, selectedConversationId, leftWidth } = useUIPanels()
  const { isMobile } = useUIResponsive()
  const uiActions = useUIActions()
  
  // Conversations store
  const conversations = useConversations()
  const conversationsActions = useConversationsActions()
  
  // Realtime store  
  const { notifications, isConnected } = useRealtime()
  const realtimeActions = useRealtimeActions()
  
  // Search store
  const search = useSearch()
  const searchActions = useSearchActions()
  
  // Folders and Analytics
  const folders = useFolders()
  const foldersActions = useFoldersActions()
  const folderModals = useFolderModals()
  const analytics = useAnalytics()
  const analyticsActions = useAnalyticsActions()

  // Auto-initialize all stores with cross-store synchronization
  useStoreInitialization()
  
  // Additional page-specific initialization
  useEffect(() => {
    console.log('FeedMe Page Manager ready')
  }, [])

  // Legacy tab change handler (maintain compatibility)
  const handleTabChange = (tab: string) => {
    uiActions.setActiveTab(tab as any)
    // Map tab changes to panel system
    if (tab === 'conversations') {
      uiActions.setRightPanel('conversations')
    } else if (tab === 'analytics') {
      uiActions.setRightPanel('analytics')
    } else if (tab === 'folders') {
      uiActions.setLeftPanel('folders')
    }
  }

  const handleConversationSelect = (conversationId: number) => {
    // Validate conversation ID before setting
    if (!conversationId || conversationId <= 0) {
      console.warn('Invalid conversation ID selected:', conversationId)
      return
    }
    uiActions.selectConversation(conversationId)
  }

  const handleConversationClose = () => {
    uiActions.selectConversation(null)
  }

  const handleFolderSelect = (folderId: number | null) => {
    conversationsActions.setCurrentFolder(folderId)
    // Switch to conversations view when folder is selected
    uiActions.setRightPanel('conversations')
  }

  const handleConversationMove = async (conversationId: number, folderId: number | null) => {
    try {
      await conversationsActions.updateConversation(conversationId, { folder_id: folderId === null ? undefined : folderId })
      // Refresh conversations list to reflect the move
      await conversationsActions.loadConversations()
    } catch (error) {
      console.error('Failed to move conversation:', error)
    }
  }


  const handleCreateFolder = async () => {
    if (!folderName.trim()) return
    
    try {
      await foldersActions.createFolder({
        name: folderName.trim(),
        color: folderColor,
        description: folderDescription.trim() || undefined
      })
      
      // Reset form
      setFolderName('')
      setFolderDescription('')
      setFolderColor('#0095ff')
      foldersActions.closeModals()
    } catch (error) {
      console.error('Failed to create folder:', error)
    }
  }

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
          onFolderCreate={() => foldersActions.openCreateModal()}
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
        onClose={() => setUploadModalOpen(false)}
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
                value={folderName}
                onChange={(e) => setFolderName(e.target.value)}
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
                value={folderColor}
                onChange={(e) => setFolderColor(e.target.value)}
                className="col-span-3 h-10"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="folder-description" className="text-right">
                Description
              </Label>
              <Textarea
                id="folder-description"
                value={folderDescription}
                onChange={(e) => setFolderDescription(e.target.value)}
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
            <Button onClick={handleCreateFolder} disabled={!folderName.trim()}>
              Create Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </div>
    </FeedMeErrorBoundary>
  )
}
