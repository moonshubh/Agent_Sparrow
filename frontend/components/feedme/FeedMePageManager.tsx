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

// Import modular store hooks - NO legacy dependencies
import { useConversations, useConversationsActions } from '@/lib/stores/conversations-store'
import { useRealtime, useRealtimeActions } from '@/lib/stores/realtime-store'
import { useSearch, useSearchActions } from '@/lib/stores/search-store'
import { useFolders, useFoldersActions, useFolderModals } from '@/lib/stores/folders-store'
import { useAnalytics, useAnalyticsActions } from '@/lib/stores/analytics-store'
import { useUITabs, useUIActions } from '@/lib/stores/ui-store'
import { useStoreInitialization } from '@/lib/stores/store-composition'

export function FeedMePageManager() {
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null)
  const [currentFolderId, setCurrentFolderId] = useState<number | null>(null)
  
  // Folder modal state
  const [folderName, setFolderName] = useState('')
  const [folderDescription, setFolderDescription] = useState('')
  const [folderColor, setFolderColor] = useState('#0095ff')

  // Modular store hooks - specific subscriptions for performance
  const { activeTab } = useUITabs()
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

  const handleTabChange = (tab: string) => {
    uiActions.setActiveTab(tab as any)
  }

  const handleConversationSelect = (conversationId: number) => {
    // Validate conversation ID before setting
    if (!conversationId || conversationId <= 0) {
      console.warn('Invalid conversation ID selected:', conversationId)
      return
    }
    setSelectedConversationId(conversationId)
  }

  const handleConversationClose = () => {
    setSelectedConversationId(null)
  }

  const handleFolderSelect = (folderId: number | null) => {
    setCurrentFolderId(folderId)
    conversationsActions.setCurrentFolder(folderId)
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
      <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b bg-card px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Feed<span className="text-accent">Me</span>
          </h1>
          <p className="text-sm text-muted-foreground">
            AI-powered customer support transcript management
          </p>
        </div>

        <div className="flex items-center gap-4">
          {/* Home button to return to Agent Sparrow dashboard */}
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => window.location.href = '/'}
            className="flex items-center gap-2"
            title="Return to Agent Sparrow Dashboard"
          >
            <Home className="h-4 w-4" />
            Agent Sparrow
          </Button>

          {/* Connection status */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className={cn(
              "h-2 w-2 rounded-full",
              isConnected ? "bg-green-500" : "bg-red-500"
            )}></div>
            <span>{isConnected ? "Connected" : "Disconnected"}</span>
          </div>

          {/* Notifications */}
          <Button variant="ghost" size="sm" className="relative">
            <Bell className="h-4 w-4" />
            {unreadNotifications > 0 && (
              <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
                {unreadNotifications}
              </span>
            )}
          </Button>

          {/* Enhanced Upload button with dropdown */}
          <div className="relative">
            <Button 
              onClick={() => setUploadModalOpen(true)} 
              size="sm"
              className="bg-accent hover:bg-accent/90 text-accent-foreground"
            >
              <Upload className="h-4 w-4 mr-2" />
              Upload Transcripts
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Search and filter bar */}
        <div className="border-b px-6 py-4 bg-card">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <UnifiedSearchBar />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTabChange("folders")}
              className="flex items-center gap-2 border-accent/30 text-accent hover:bg-accent hover:text-accent-foreground"
            >
              <FolderOpen className="h-4 w-4" />
              Manage Folders
            </Button>
          </div>
        </div>

        {/* Main content area */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col">
            <div className="border-b px-6 py-2 flex justify-center">
              <TabsList className="grid grid-cols-3 max-w-md">
                <TabsTrigger value="conversations" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <Home className="h-4 w-4" />
                  Conversations
                </TabsTrigger>
                <TabsTrigger value="folders" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <FolderOpen className="h-4 w-4" />
                  Folders
                </TabsTrigger>
                <TabsTrigger value="analytics" className="flex items-center gap-2 data-[state=active]:bg-accent data-[state=active]:text-accent-foreground">
                  <BarChart3 className="h-4 w-4" />
                  Analytics
                </TabsTrigger>
              </TabsList>
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-hidden">
              <TabsContent value="conversations" className="h-full">
                <FileGridView 
                  onConversationSelect={handleConversationSelect}
                  currentFolderId={currentFolderId}
                  onFolderSelect={handleFolderSelect}
                />
              </TabsContent>

              <TabsContent value="folders" className="h-full p-6">
                <div className="grid gap-6">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-semibold">Folder Management</h2>
                    <Button 
                      onClick={() => foldersActions.openCreateModal()}
                      size="sm"
                    >
                      <FolderOpen className="h-4 w-4 mr-2" />
                      Create Folder
                    </Button>
                  </div>
                  <FolderTreeView 
                    onConversationSelect={handleConversationSelect}
                    onFolderSelect={handleFolderSelect}
                    expanded={true}
                  />
                </div>
              </TabsContent>

              <TabsContent value="analytics" className="h-full">
                <AnalyticsDashboard />
              </TabsContent>
            </div>
          </Tabs>
        </main>
      </div>

      {/* Conversation Editor Modal */}
      {selectedConversationId && (
        <ConversationEditor
          conversationId={selectedConversationId}
          isOpen={true}
          onClose={handleConversationClose}
        />
      )}

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