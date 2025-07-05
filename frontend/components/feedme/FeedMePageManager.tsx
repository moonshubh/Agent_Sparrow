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
import { 
  Home, 
  Upload, 
  FolderOpen, 
  BarChart3, 
  Settings,
  Bell,
  Menu,
  X
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

// Import store hooks
import { useFeedMeStore, useActions, useRealtime, useUI } from '@/lib/stores/feedme-store'

export function FeedMePageManager() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null)

  // Store hooks
  const { activeTab } = useUI()
  const { notifications, isConnected } = useRealtime()
  const actions = useActions()

  // Initialize data and WebSocket connection
  useEffect(() => {
    // Load initial data
    actions.loadConversations()
    actions.loadFolders()
    actions.loadAnalytics()
    
    // Connect to WebSocket for real-time updates
    actions.connectWebSocket()

    // Cleanup on unmount
    return () => {
      actions.disconnectWebSocket()
    }
  }, [actions])

  const handleTabChange = (tab: string) => {
    actions.setActiveTab(tab as any)
  }

  const handleConversationSelect = (conversationId: number) => {
    setSelectedConversationId(conversationId)
  }

  const handleConversationClose = () => {
    setSelectedConversationId(null)
  }

  const unreadNotifications = notifications.filter(n => !n.read).length

  return (
    <FeedMeErrorBoundary>
      <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b bg-card px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="md:hidden"
          >
            {sidebarCollapsed ? <Menu className="h-4 w-4" /> : <X className="h-4 w-4" />}
          </Button>
          
          <div>
            <h1 className="text-2xl font-bold text-foreground">FeedMe</h1>
            <p className="text-sm text-muted-foreground">
              AI-powered customer support transcript management
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
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

          {/* Upload button */}
          <Button onClick={() => setUploadModalOpen(true)} size="sm">
            <Upload className="h-4 w-4 mr-2" />
            Upload
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className={cn(
          "border-r bg-card transition-all duration-200",
          sidebarCollapsed ? "w-0 md:w-12" : "w-80"
        )}>
          <div className="h-full flex flex-col">
            {!sidebarCollapsed && (
              <>
                {/* Search bar */}
                <div className="p-4 border-b">
                  <UnifiedSearchBar />
                </div>

                {/* Folder tree */}
                <div className="flex-1 overflow-hidden">
                  <FolderTreeView 
                    onConversationSelect={handleConversationSelect}
                  />
                </div>
              </>
            )}
          </div>
        </aside>

        {/* Main content area */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col">
            <div className="border-b px-6 py-2">
              <TabsList className="grid w-full grid-cols-4 max-w-md">
                <TabsTrigger value="conversations" className="flex items-center gap-2">
                  <Home className="h-4 w-4" />
                  Conversations
                </TabsTrigger>
                <TabsTrigger value="folders" className="flex items-center gap-2">
                  <FolderOpen className="h-4 w-4" />
                  Folders
                </TabsTrigger>
                <TabsTrigger value="analytics" className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  Analytics
                </TabsTrigger>
                <TabsTrigger value="upload" className="flex items-center gap-2">
                  <Upload className="h-4 w-4" />
                  Upload
                </TabsTrigger>
              </TabsList>
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-hidden">
              <TabsContent value="conversations" className="h-full">
                <FileGridView 
                  onConversationSelect={handleConversationSelect}
                />
              </TabsContent>

              <TabsContent value="folders" className="h-full p-6">
                <div className="grid gap-6">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-semibold">Folder Management</h2>
                    <Button 
                      onClick={() => actions.createFolder("New Folder")}
                      size="sm"
                    >
                      <FolderOpen className="h-4 w-4 mr-2" />
                      Create Folder
                    </Button>
                  </div>
                  <FolderTreeView 
                    onConversationSelect={handleConversationSelect}
                    expanded={true}
                  />
                </div>
              </TabsContent>

              <TabsContent value="analytics" className="h-full">
                <AnalyticsDashboard />
              </TabsContent>

              <TabsContent value="upload" className="h-full p-6">
                <div className="max-w-2xl mx-auto">
                  <div className="text-center mb-8">
                    <h2 className="text-2xl font-semibold mb-2">Upload Conversations</h2>
                    <p className="text-muted-foreground">
                      Upload customer support transcripts for AI-powered analysis and knowledge extraction
                    </p>
                  </div>
                  
                  <EnhancedFeedMeModal 
                    isOpen={true}
                    onClose={() => handleTabChange("conversations")}
                    mode="embedded"
                  />
                </div>
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
      </div>
    </FeedMeErrorBoundary>
  )
}