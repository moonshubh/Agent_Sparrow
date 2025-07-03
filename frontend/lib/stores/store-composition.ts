/**
 * Store Composition Utilities
 * 
 * Provides cross-store communication, event coordination, and composition
 * utilities for the modular FeedMe store architecture.
 */

import { useEffect, useCallback, useMemo } from 'react'
import { useConversationsStore } from './conversations-store'
import { useRealtimeStore } from './realtime-store'
import { useSearchStore } from './search-store'
import { useFoldersStore } from './folders-store'
import { useAnalyticsStore } from './analytics-store'
import { useUIStore } from './ui-store'

// Cross-store event types
export type StoreEvent = 
  | { type: 'conversation_updated'; payload: { id: number; updates: any } }
  | { type: 'conversation_deleted'; payload: { id: number } }
  | { type: 'conversation_uploaded'; payload: { conversation: any } }
  | { type: 'processing_started'; payload: { conversationId: number } }
  | { type: 'processing_completed'; payload: { conversationId: number; result: any } }
  | { type: 'folder_created'; payload: { folder: any } }
  | { type: 'folder_updated'; payload: { id: number; updates: any } }
  | { type: 'folder_deleted'; payload: { id: number } }
  | { type: 'search_performed'; payload: { query: string; results: number } }
  | { type: 'websocket_connected'; payload: {} }
  | { type: 'websocket_disconnected'; payload: {} }

// Event bus for cross-store communication
class StoreEventBus {
  private listeners = new Map<string, Array<(event: StoreEvent) => void>>()
  
  subscribe(eventType: string, callback: (event: StoreEvent) => void) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, [])
    }
    this.listeners.get(eventType)!.push(callback)
    
    // Return unsubscribe function
    return () => {
      const callbacks = this.listeners.get(eventType)
      if (callbacks) {
        const index = callbacks.indexOf(callback)
        if (index > -1) {
          callbacks.splice(index, 1)
        }
      }
    }
  }
  
  emit(event: StoreEvent) {
    const callbacks = this.listeners.get(event.type)
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(event)
        } catch (error) {
          console.error(`Error in store event handler for ${event.type}:`, error)
        }
      })
    }
  }
  
  clear() {
    this.listeners.clear()
  }
}

export const storeEventBus = new StoreEventBus()

// Cross-store synchronization hooks
export function useStoreSync() {
  const conversationsActions = useConversationsStore(state => state.actions)
  const realtimeActions = useRealtimeStore(state => state.actions)
  const searchActions = useSearchStore(state => state.actions)
  const foldersActions = useFoldersStore(state => state.actions)
  const analyticsActions = useAnalyticsStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  
  useEffect(() => {
    // Sync processing updates from realtime to conversations
    const unsubscribeProcessing = storeEventBus.subscribe('processing_completed', (event) => {
      if (event.type === 'processing_completed') {
        conversationsActions.updateConversation(event.payload.conversationId, {
          processing_status: 'completed',
          last_updated: new Date().toISOString(),
          ...event.payload.result
        })
        
        // Record analytics
        analyticsActions.recordUserAction('processing_completed', {
          conversation_id: event.payload.conversationId
        })
      }
    })
    
    // Sync folder changes to conversations
    const unsubscribeFolderUpdates = storeEventBus.subscribe('folder_updated', (event) => {
      if (event.type === 'folder_updated') {
        // Refresh conversations that might be affected
        conversationsActions.refreshConversations()
      }
    })
    
    // Sync search events to analytics
    const unsubscribeSearch = storeEventBus.subscribe('search_performed', (event) => {
      if (event.type === 'search_performed') {
        analyticsActions.recordUserAction('search_performed', {
          query: event.payload.query,
          results_count: event.payload.results
        })
      }
    })
    
    // Sync WebSocket connection status to UI
    const unsubscribeWsConnect = storeEventBus.subscribe('websocket_connected', () => {
      uiActions.hideBanner('websocket-disconnected')
      uiActions.showToast({
        type: 'success',
        title: 'Connected',
        message: 'Real-time updates enabled',
        duration: 3000
      })
    })
    
    const unsubscribeWsDisconnect = storeEventBus.subscribe('websocket_disconnected', () => {
      uiActions.showBanner({
        type: 'warning',
        message: 'Real-time updates disconnected. Attempting to reconnect...',
        dismissible: false,
        persistent: true
      })
    })
    
    return () => {
      unsubscribeProcessing()
      unsubscribeFolderUpdates()
      unsubscribeSearch()
      unsubscribeWsConnect()
      unsubscribeWsDisconnect()
    }
  }, [conversationsActions, analyticsActions, uiActions])
}

// Composite hooks for complex operations
export function useConversationManagement() {
  const conversationsActions = useConversationsStore(state => state.actions)
  const foldersActions = useFoldersStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  const realtimeActions = useRealtimeStore(state => state.actions)
  
  const deleteConversationWithConfirmation = useCallback(async (id: number) => {
    const confirmed = window.confirm('Are you sure you want to delete this conversation?')
    if (!confirmed) return false
    
    try {
      uiActions.setOperationLoading('delete-conversation', true)
      
      await conversationsActions.deleteConversation(id)
      
      // Emit event for other stores
      storeEventBus.emit({
        type: 'conversation_deleted',
        payload: { id }
      })
      
      uiActions.showToast({
        type: 'success',
        title: 'Conversation Deleted',
        message: 'The conversation has been successfully deleted.'
      })
      
      return true
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Delete Failed',
        message: error instanceof Error ? error.message : 'Failed to delete conversation'
      })
      
      return false
      
    } finally {
      uiActions.setOperationLoading('delete-conversation', false)
    }
  }, [conversationsActions, uiActions])
  
  const uploadWithProgress = useCallback(async (
    title: string,
    file?: File,
    content?: string,
    folderId?: number
  ) => {
    try {
      uiActions.setOperationLoading('upload-conversation', true)
      
      // Upload conversation
      const uploadId = await conversationsActions.uploadConversation({
        type: file ? 'file' : 'text',
        title,
        file,
        content,
        autoProcess: true
      })
      
      // Assign to folder if specified
      if (folderId) {
        // Wait for upload to complete and get conversation ID
        // This would be handled by the upload process in real implementation
      }
      
      uiActions.showToast({
        type: 'success',
        title: 'Upload Started',
        message: 'Your conversation is being processed...'
      })
      
      // Switch to conversations tab to show progress
      uiActions.setActiveTab('conversations')
      
      return uploadId
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Upload Failed',
        message: error instanceof Error ? error.message : 'Failed to upload conversation'
      })
      
      throw error
      
    } finally {
      uiActions.setOperationLoading('upload-conversation', false)
    }
  }, [conversationsActions, uiActions])
  
  return {
    deleteConversationWithConfirmation,
    uploadWithProgress
  }
}

export function useFolderManagement() {
  const foldersActions = useFoldersStore(state => state.actions)
  const conversationsActions = useConversationsStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  
  const createFolderWithValidation = useCallback(async (
    name: string,
    parentId?: number,
    description?: string
  ) => {
    if (!name.trim()) {
      uiActions.showToast({
        type: 'error',
        title: 'Invalid Name',
        message: 'Folder name cannot be empty'
      })
      return null
    }
    
    try {
      uiActions.setOperationLoading('create-folder', true)
      
      const folder = await foldersActions.createFolder({
        name: name.trim(),
        parent_id: parentId,
        description: description?.trim()
      })
      
      // Emit event
      storeEventBus.emit({
        type: 'folder_created',
        payload: { folder }
      })
      
      uiActions.showToast({
        type: 'success',
        title: 'Folder Created',
        message: `Folder "${name}" has been created successfully.`
      })
      
      return folder
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Creation Failed',
        message: error instanceof Error ? error.message : 'Failed to create folder'
      })
      
      return null
      
    } finally {
      uiActions.setOperationLoading('create-folder', false)
    }
  }, [foldersActions, uiActions])
  
  const moveConversationsToFolder = useCallback(async (
    conversationIds: number[],
    targetFolderId: number | null
  ) => {
    try {
      uiActions.setOperationLoading('move-conversations', true)
      
      await foldersActions.assignConversationsToFolder(conversationIds, targetFolderId)
      
      // Update conversations in conversations store
      conversationIds.forEach(id => {
        conversationsActions.updateConversation(id, {
          folder_id: targetFolderId || undefined
        })
      })
      
      const folderName = targetFolderId ? 'selected folder' : 'root'
      
      uiActions.showToast({
        type: 'success',
        title: 'Conversations Moved',
        message: `${conversationIds.length} conversation(s) moved to ${folderName}.`
      })
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Move Failed',
        message: error instanceof Error ? error.message : 'Failed to move conversations'
      })
      
      throw error
      
    } finally {
      uiActions.setOperationLoading('move-conversations', false)
    }
  }, [foldersActions, conversationsActions, uiActions])
  
  return {
    createFolderWithValidation,
    moveConversationsToFolder
  }
}

export function useSearchIntegration() {
  const searchActions = useSearchStore(state => state.actions)
  const conversationsActions = useConversationsStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  
  const performSearchWithAnalytics = useCallback(async (
    query: string,
    options?: Parameters<typeof searchActions.performSearch>[1]
  ) => {
    try {
      const startTime = Date.now()
      
      await searchActions.performSearch(query, options)
      
      const endTime = Date.now()
      const responseTime = endTime - startTime
      
      // Get result count from search store
      const searchState = useSearchStore.getState()
      
      // Emit analytics event
      storeEventBus.emit({
        type: 'search_performed',
        payload: {
          query,
          results: searchState.totalResults
        }
      })
      
      // Show no results message if needed
      if (searchState.totalResults === 0 && query.trim()) {
        uiActions.showToast({
          type: 'info',
          title: 'No Results',
          message: `No results found for "${query}". Try different keywords or check filters.`,
          duration: 4000
        })
      }
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Search Failed',
        message: error instanceof Error ? error.message : 'Search request failed'
      })
      
      throw error
    }
  }, [searchActions, uiActions])
  
  const searchAndNavigate = useCallback(async (query: string) => {
    // Switch to search tab
    uiActions.setActiveTab('search')
    
    // Perform search
    await performSearchWithAnalytics(query)
  }, [performSearchWithAnalytics, uiActions])
  
  return {
    performSearchWithAnalytics,
    searchAndNavigate
  }
}

// Global store state selector
export function useGlobalState() {
  const conversations = useConversationsStore(state => ({
    items: state.conversationsList.items,
    isLoading: state.conversationsList.isLoading,
    totalCount: state.conversationsList.totalCount
  }))
  
  const realtime = useRealtimeStore(state => ({
    isConnected: state.isConnected,
    connectionStatus: state.connectionStatus,
    notifications: state.notifications
  }))
  
  const search = useSearchStore(state => ({
    query: state.query,
    isSearching: state.isSearching,
    results: state.results,
    totalResults: state.totalResults
  }))
  
  const folders = useFoldersStore(state => ({
    folderTree: state.folderTree,
    isLoading: state.isLoading
  }))
  
  const analytics = useAnalyticsStore(state => ({
    workflowStats: state.workflowStats,
    isLoading: state.isLoading
  }))
  
  const ui = useUIStore(state => ({
    activeTab: state.tabs.activeTab,
    viewMode: state.view.viewMode,
    isGlobalLoading: state.loading.global,
    notifications: state.notifications
  }))
  
  return {
    conversations,
    realtime,
    search,
    folders,
    analytics,
    ui
  }
}

// Bulk operations across stores
export function useBulkOperations() {
  const conversationsActions = useConversationsStore(state => state.actions)
  const foldersActions = useFoldersStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  const ui = useUIStore(state => state.bulkActions)
  
  const selectedConversationIds = useMemo(() => {
    return Array.from(ui.selectedItems).filter(id => typeof id === 'number') as number[]
  }, [ui.selectedItems])
  
  const bulkDeleteConversations = useCallback(async () => {
    if (selectedConversationIds.length === 0) return
    
    const confirmed = window.confirm(
      `Are you sure you want to delete ${selectedConversationIds.length} conversation(s)?`
    )
    
    if (!confirmed) return
    
    try {
      uiActions.setOperationLoading('bulk-delete', true)
      
      await conversationsActions.deleteMultipleConversations(selectedConversationIds)
      
      uiActions.clearBulkSelection()
      uiActions.showToast({
        type: 'success',
        title: 'Conversations Deleted',
        message: `Successfully deleted ${selectedConversationIds.length} conversation(s).`
      })
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Bulk Delete Failed',
        message: error instanceof Error ? error.message : 'Failed to delete conversations'
      })
    } finally {
      uiActions.setOperationLoading('bulk-delete', false)
    }
  }, [selectedConversationIds, conversationsActions, uiActions])
  
  const bulkMoveToFolder = useCallback(async (folderId: number | null) => {
    if (selectedConversationIds.length === 0) return
    
    try {
      uiActions.setOperationLoading('bulk-move', true)
      
      await foldersActions.assignConversationsToFolder(selectedConversationIds, folderId)
      
      // Update conversations
      selectedConversationIds.forEach(id => {
        conversationsActions.updateConversation(id, {
          folder_id: folderId || undefined
        })
      })
      
      uiActions.clearBulkSelection()
      
      const folderName = folderId ? 'selected folder' : 'root'
      uiActions.showToast({
        type: 'success',
        title: 'Conversations Moved',
        message: `Successfully moved ${selectedConversationIds.length} conversation(s) to ${folderName}.`
      })
      
    } catch (error) {
      uiActions.showToast({
        type: 'error',
        title: 'Bulk Move Failed',
        message: error instanceof Error ? error.message : 'Failed to move conversations'
      })
    } finally {
      uiActions.setOperationLoading('bulk-move', false)
    }
  }, [selectedConversationIds, foldersActions, conversationsActions, uiActions])
  
  return {
    selectedConversationIds,
    bulkDeleteConversations,
    bulkMoveToFolder
  }
}

// Store initialization and cleanup
export function useStoreInitialization() {
  const conversationsActions = useConversationsStore(state => state.actions)
  const foldersActions = useFoldersStore(state => state.actions)
  const realtimeActions = useRealtimeStore(state => state.actions)
  const analyticsActions = useAnalyticsStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  
  // Initialize stores on mount
  useEffect(() => {
    const initialize = async () => {
      try {
        uiActions.setGlobalLoading(true)
        
        // Load initial data in parallel
        await Promise.allSettled([
          foldersActions.loadFolders(),
          conversationsActions.loadConversations({ page: 1 }),
          analyticsActions.loadWorkflowStats()
        ])
        
        // Connect to WebSocket for real-time updates
        await realtimeActions.connect()
        
      } catch (error) {
        console.error('Store initialization failed:', error)
        
        uiActions.showToast({
          type: 'error',
          title: 'Initialization Failed',
          message: 'Some features may not work properly. Please refresh the page.'
        })
      } finally {
        uiActions.setGlobalLoading(false)
      }
    }
    
    initialize()
    
    // Cleanup on unmount
    return () => {
      realtimeActions.cleanup()
      storeEventBus.clear()
    }
  }, [])
  
  // Setup cross-store synchronization
  useStoreSync()
}

// All hooks are already exported above