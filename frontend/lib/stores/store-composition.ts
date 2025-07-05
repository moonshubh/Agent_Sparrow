/**
 * Store Composition Utilities
 * 
 * Provides cross-store communication, event coordination, and composition
 * utilities for the modular FeedMe store architecture.
 */

import { useEffect, useCallback, useMemo } from 'react'
import { useConversationsStore, type Conversation } from './conversations-store'
import { useRealtimeStore } from './realtime-store'
import { useSearchStore } from './search-store'
import { useFoldersStore, type Folder } from './folders-store'
import { useAnalyticsStore } from './analytics-store'
import { useUIStore } from './ui-store'

// Strongly typed event payload interfaces
export interface ConversationUpdatedPayload {
  id: number
  updates: Partial<Conversation>
}

export interface ConversationDeletedPayload {
  id: number
}

export interface ConversationUploadedPayload {
  conversation: Conversation
}

export interface ProcessingStartedPayload {
  conversationId: number
}

export interface ProcessingCompletedPayload {
  conversationId: number
  result: {
    processing_status: 'completed' | 'failed'
    extracted_examples?: number
    processing_time_ms?: number
    ai_confidence?: number
    error_message?: string
  }
}

export interface FolderCreatedPayload {
  folder: Folder
}

export interface FolderUpdatedPayload {
  id: number
  updates: Partial<Folder>
}

export interface FolderDeletedPayload {
  id: number
}

export interface SearchPerformedPayload {
  query: string
  results: number
}

export interface WebSocketConnectedPayload {}

export interface WebSocketDisconnectedPayload {}

// Cross-store event types with proper typing
export type StoreEvent = 
  | { type: 'conversation_updated'; payload: ConversationUpdatedPayload }
  | { type: 'conversation_deleted'; payload: ConversationDeletedPayload }
  | { type: 'conversation_uploaded'; payload: ConversationUploadedPayload }
  | { type: 'processing_started'; payload: ProcessingStartedPayload }
  | { type: 'processing_completed'; payload: ProcessingCompletedPayload }
  | { type: 'folder_created'; payload: FolderCreatedPayload }
  | { type: 'folder_updated'; payload: FolderUpdatedPayload }
  | { type: 'folder_deleted'; payload: FolderDeletedPayload }
  | { type: 'search_performed'; payload: SearchPerformedPayload }
  | { type: 'websocket_connected'; payload: WebSocketConnectedPayload }
  | { type: 'websocket_disconnected'; payload: WebSocketDisconnectedPayload }

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
  }, [conversationsActions, analyticsActions, uiActions, searchActions, foldersActions, realtimeActions])
}

// Composite hooks for complex operations
export function useConversationManagement() {
  const conversationsActions = useConversationsStore(state => state.actions)
  const foldersActions = useFoldersStore(state => state.actions)
  const uiActions = useUIStore(state => state.actions)
  const realtimeActions = useRealtimeStore(state => state.actions)
  
  const deleteConversationWithConfirmation = useCallback(async (id: number) => {
    // Use modal confirmation instead of window.confirm
    return new Promise<boolean>((resolve) => {
      uiActions.openModal('deleteConfirmation', {
        title: 'Delete Conversation',
        message: 'Are you sure you want to delete this conversation? This action cannot be undone.',
        confirmText: 'Delete',
        cancelText: 'Cancel',
        confirmVariant: 'destructive',
        onConfirm: async () => {
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
            
            uiActions.closeModal()
            resolve(true)
            
          } catch (error) {
            uiActions.showToast({
              type: 'error',
              title: 'Delete Failed',
              message: error instanceof Error ? error.message : 'Failed to delete conversation'
            })
            
            resolve(false)
            
          } finally {
            uiActions.setOperationLoading('delete-conversation', false)
          }
        },
        onCancel: () => {
          uiActions.closeModal()
          resolve(false)
        }
      })
    })
    
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
        try {
          // Set up event listener to handle folder assignment after upload completes
          const unsubscribe = storeEventBus.subscribe('conversation_uploaded', (event) => {
            if (event.type === 'conversation_uploaded' && event.payload.conversation.id) {
              // Assign the uploaded conversation to the specified folder
              foldersActions.assignConversationsToFolder(
                [event.payload.conversation.id],
                folderId
              ).then(() => {
                // Update the conversation to reflect folder assignment
                conversationsActions.updateConversation(event.payload.conversation.id, {
                  folder_id: folderId
                })
                
                uiActions.showToast({
                  type: 'success',
                  title: 'Conversation Assigned',
                  message: 'The conversation has been assigned to the selected folder.'
                })
              }).catch((error) => {
                uiActions.showToast({
                  type: 'warning',
                  title: 'Folder Assignment Failed',
                  message: 'The conversation was uploaded but could not be assigned to the folder.'
                })
              }).finally(() => {
                unsubscribe()
              })
            }
          })
          
          // Clean up listener after a reasonable timeout
          setTimeout(() => {
            unsubscribe()
          }, 30000) // 30 second timeout
          
        } catch (error) {
          console.warn('Failed to set up folder assignment listener:', error)
        }
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
  }, [conversationsActions, foldersActions, uiActions])
  
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
      
      // Emit analytics event with response time
      storeEventBus.emit({
        type: 'search_performed',
        payload: {
          query,
          results: searchState.totalResults,
          responseTime
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
    
    // Use modal confirmation instead of window.confirm
    return new Promise<void>((resolve) => {
      uiActions.openModal('bulkDeleteConfirmation', {
        title: 'Delete Conversations',
        message: `Are you sure you want to delete ${selectedConversationIds.length} conversation(s)? This action cannot be undone.`,
        confirmText: 'Delete All',
        cancelText: 'Cancel',
        confirmVariant: 'destructive',
        onConfirm: async () => {
          try {
            uiActions.setOperationLoading('bulk-delete', true)
            
            await conversationsActions.deleteMultipleConversations(selectedConversationIds)
            
            uiActions.clearBulkSelection()
            uiActions.showToast({
              type: 'success',
              title: 'Conversations Deleted',
              message: `Successfully deleted ${selectedConversationIds.length} conversation(s).`
            })
            
            uiActions.closeModal()
            resolve()
            
          } catch (error) {
            uiActions.showToast({
              type: 'error',
              title: 'Bulk Delete Failed',
              message: error instanceof Error ? error.message : 'Failed to delete conversations'
            })
            resolve()
          } finally {
            uiActions.setOperationLoading('bulk-delete', false)
          }
        },
        onCancel: () => {
          uiActions.closeModal()
          resolve()
        }
      })
    })
    
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