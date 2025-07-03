/**
 * FeedMe State Management Store
 * 
 * Zustand store for managing complex FeedMe UI state, real-time updates,
 * and WebSocket connections for Phase 3 enhanced functionality.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import { 
  listConversations, 
  listFolders, 
  getApprovalWorkflowStats,
  type UploadTranscriptResponse,
  type FeedMeFolder,
  type ApprovalWorkflowStats,
  type ConversationListResponse,
  type FolderListResponse
} from '@/lib/feedme-api'
import { feedMeAuth, autoLogin } from '@/lib/auth/feedme-auth'

// Types
export interface Conversation extends UploadTranscriptResponse {
  folder_id?: number
  last_updated?: string
  quality_score?: number
}

export interface Folder extends FeedMeFolder {
  isExpanded?: boolean
  isSelected?: boolean
}

export interface SearchState {
  query: string
  filters: SearchFilters
  results: SearchResult[]
  totalResults: number
  isSearching: boolean
  searchHistory: string[]
  savedSearches: SavedSearch[]
}

export interface SearchFilters {
  dateRange: 'all' | 'today' | 'week' | 'month' | 'year'
  folders: number[]
  tags: string[]
  confidence: [number, number]
  platforms: string[]
  status: string[]
  qualityScore: [number, number]
}

export interface SearchResult {
  id: number
  title: string
  snippet: string
  score: number
  conversation_id: number
  type: 'conversation' | 'example'
}

export interface SavedSearch {
  id: string
  name: string
  query: string
  filters: SearchFilters
  created_at: string
}

export interface ProcessingUpdate {
  conversation_id: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  message?: string
  examples_extracted?: number
}

export interface RealtimeState {
  isConnected: boolean
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
  lastUpdate: string | null
  processingUpdates: Record<number, ProcessingUpdate>
  notifications: Notification[]
  websocket: WebSocket | null
}

export interface Notification {
  id: string
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  timestamp: string
  read: boolean
  actions?: NotificationAction[]
}

export interface NotificationAction {
  label: string
  action: () => void
  variant?: 'default' | 'destructive'
}

export interface AnalyticsState {
  workflowStats: ApprovalWorkflowStats | null
  performanceMetrics: PerformanceMetrics | null
  usageStats: UsageStats | null
  lastUpdated: string | null
  isLoading: boolean
}

export interface PerformanceMetrics {
  upload_success_rate: number
  avg_processing_time: number
  search_response_time: number
  system_health: number
  active_users: number
}

export interface UsageStats {
  total_conversations: number
  total_examples: number
  searches_today: number
  most_active_folders: Array<{ folder_id: number; activity_count: number }>
  trending_tags: string[]
}

export interface UIState {
  activeTab: 'conversations' | 'folders' | 'analytics' | 'upload'
  selectedConversations: number[]
  selectedFolders: number[]
  isMultiSelectMode: boolean
  viewMode: 'grid' | 'list' | 'table'
  sidebarCollapsed: boolean
  activeModal: string | null
  bulkActionMode: boolean
}

// Main Store Interface
export interface FeedMeStore {
  // Data State
  conversations: Record<number, Conversation>
  folders: Record<number, Folder>
  conversationsList: {
    items: Conversation[]
    totalCount: number
    currentPage: number
    pageSize: number
    hasNext: boolean
    isLoading: boolean
    lastUpdated: string | null
  }
  
  // Feature States
  search: SearchState
  realtime: RealtimeState
  analytics: AnalyticsState
  ui: UIState
  
  // Actions
  actions: {
    // Conversation Management
    loadConversations: (page?: number, pageSize?: number, search?: string) => Promise<void>
    refreshConversations: () => Promise<void>
    updateConversation: (id: number, updates: Partial<Conversation>) => void
    removeConversation: (id: number) => void
    selectConversation: (id: number, selected: boolean) => void
    selectAllConversations: (selected: boolean) => void
    
    // Folder Management
    loadFolders: () => Promise<void>
    updateFolder: (id: number, updates: Partial<Folder>) => void
    toggleFolderExpanded: (id: number) => void
    selectFolder: (id: number, selected: boolean) => void
    
    // Search Operations
    performSearch: (query: string, filters?: Partial<SearchFilters>) => Promise<void>
    updateSearchFilters: (filters: Partial<SearchFilters>) => void
    saveSearch: (name: string) => void
    loadSavedSearch: (searchId: string) => void
    clearSearch: () => void
    addToSearchHistory: (query: string) => void
    
    // Real-time Operations
    connectWebSocket: (conversationId?: number) => void
    disconnectWebSocket: () => void
    handleProcessingUpdate: (update: ProcessingUpdate) => void
    addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => void
    markNotificationRead: (id: string) => void
    clearNotifications: () => void
    
    // Analytics Operations
    loadAnalytics: () => Promise<void>
    refreshAnalytics: () => Promise<void>
    
    // UI Operations
    setActiveTab: (tab: UIState['activeTab']) => void
    setViewMode: (mode: UIState['viewMode']) => void
    toggleSidebar: () => void
    openModal: (modalId: string) => void
    closeModal: () => void
    enableBulkActions: () => void
    disableBulkActions: () => void
  }
}

// Default states
const defaultSearchFilters: SearchFilters = {
  dateRange: 'all',
  folders: [],
  tags: [],
  confidence: [0.7, 1.0],
  platforms: [],
  status: [],
  qualityScore: [0.0, 1.0]
}

const defaultSearchState: SearchState = {
  query: '',
  filters: defaultSearchFilters,
  results: [],
  totalResults: 0,
  isSearching: false,
  searchHistory: [],
  savedSearches: []
}

const defaultRealtimeState: RealtimeState = {
  isConnected: false,
  connectionStatus: 'disconnected',
  lastUpdate: null,
  processingUpdates: {},
  notifications: [],
  websocket: null
}

const defaultAnalyticsState: AnalyticsState = {
  workflowStats: null,
  performanceMetrics: null,
  usageStats: null,
  lastUpdated: null,
  isLoading: false
}

const defaultUIState: UIState = {
  activeTab: 'conversations',
  selectedConversations: [],
  selectedFolders: [],
  isMultiSelectMode: false,
  viewMode: 'list',
  sidebarCollapsed: false,
  activeModal: null,
  bulkActionMode: false
}

// Utility functions
const generateId = (): string => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

const createNotification = (
  notification: Omit<Notification, 'id' | 'timestamp'>
): Notification => ({
  ...notification,
  id: generateId(),
  timestamp: new Date().toISOString(),
  read: false
})

// Store Implementation
export const useFeedMeStore = create<FeedMeStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial State
      conversations: {},
      folders: {},
      conversationsList: {
        items: [],
        totalCount: 0,
        currentPage: 1,
        pageSize: 20,
        hasNext: false,
        isLoading: false,
        lastUpdated: null
      },
      search: defaultSearchState,
      realtime: defaultRealtimeState,
      analytics: defaultAnalyticsState,
      ui: defaultUIState,

      // Actions Implementation
      actions: {
        // Conversation Management
        loadConversations: async (page = 1, pageSize = 20, search = '') => {
          set((state) => ({
            conversationsList: {
              ...state.conversationsList,
              isLoading: true
            }
          }))

          try {
            const response: ConversationListResponse = await listConversations(
              page,
              pageSize,
              search
            )

            // Update conversations map
            const conversationsMap = { ...get().conversations }
            response.conversations.forEach(conv => {
              conversationsMap[conv.id] = conv as Conversation
            })

            set((state) => ({
              conversations: conversationsMap,
              conversationsList: {
                ...state.conversationsList,
                items: response.conversations as Conversation[],
                totalCount: response.total_count,
                currentPage: response.page,
                pageSize: response.page_size,
                hasNext: response.has_next,
                isLoading: false,
                lastUpdated: new Date().toISOString()
              }
            }))
          } catch (error) {
            console.error('Failed to load conversations:', error)
            set((state) => ({
              conversationsList: {
                ...state.conversationsList,
                isLoading: false
              }
            }))
            
            get().actions.addNotification({
              type: 'error',
              title: 'Loading Failed',
              message: 'Failed to load conversations. Please try again.'
            })
          }
        },

        refreshConversations: async () => {
          const { currentPage, pageSize } = get().conversationsList
          const { query } = get().search
          await get().actions.loadConversations(currentPage, pageSize, query)
        },

        updateConversation: (id: number, updates: Partial<Conversation>) => {
          set((state) => ({
            conversations: {
              ...state.conversations,
              [id]: {
                ...state.conversations[id],
                ...updates
              }
            },
            conversationsList: {
              ...state.conversationsList,
              items: state.conversationsList.items.map(conv =>
                conv.id === id ? { ...conv, ...updates } : conv
              )
            }
          }))
        },

        removeConversation: (id: number) => {
          set((state) => {
            const { [id]: removed, ...remainingConversations } = state.conversations
            return {
              conversations: remainingConversations,
              conversationsList: {
                ...state.conversationsList,
                items: state.conversationsList.items.filter(conv => conv.id !== id),
                totalCount: state.conversationsList.totalCount - 1
              },
              ui: {
                ...state.ui,
                selectedConversations: state.ui.selectedConversations.filter(cId => cId !== id)
              }
            }
          })
        },

        selectConversation: (id: number, selected: boolean) => {
          set((state) => ({
            ui: {
              ...state.ui,
              selectedConversations: selected
                ? [...state.ui.selectedConversations.filter(cId => cId !== id), id]
                : state.ui.selectedConversations.filter(cId => cId !== id)
            }
          }))
        },

        selectAllConversations: (selected: boolean) => {
          set((state) => ({
            ui: {
              ...state.ui,
              selectedConversations: selected
                ? state.conversationsList.items.map(conv => conv.id)
                : []
            }
          }))
        },

        // Folder Management
        loadFolders: async () => {
          try {
            const response: FolderListResponse = await listFolders()
            const foldersMap: Record<number, Folder> = {}
            
            response.folders.forEach(folder => {
              foldersMap[folder.id] = {
                ...folder,
                isExpanded: false,
                isSelected: false
              }
            })

            set({ folders: foldersMap })
          } catch (error) {
            console.error('Failed to load folders:', error)
            get().actions.addNotification({
              type: 'error',
              title: 'Loading Failed',
              message: 'Failed to load folders. Please try again.'
            })
          }
        },

        updateFolder: (id: number, updates: Partial<Folder>) => {
          set((state) => ({
            folders: {
              ...state.folders,
              [id]: {
                ...state.folders[id],
                ...updates
              }
            }
          }))
        },

        toggleFolderExpanded: (id: number) => {
          set((state) => ({
            folders: {
              ...state.folders,
              [id]: {
                ...state.folders[id],
                isExpanded: !state.folders[id]?.isExpanded
              }
            }
          }))
        },

        selectFolder: (id: number, selected: boolean) => {
          set((state) => ({
            ui: {
              ...state.ui,
              selectedFolders: selected
                ? [...state.ui.selectedFolders.filter(fId => fId !== id), id]
                : state.ui.selectedFolders.filter(fId => fId !== id)
            },
            folders: {
              ...state.folders,
              [id]: {
                ...state.folders[id],
                isSelected: selected
              }
            }
          }))
        },

        // Search Operations
        performSearch: async (query: string, filters?: Partial<SearchFilters>) => {
          set((state) => ({
            search: {
              ...state.search,
              query,
              filters: filters ? { ...state.search.filters, ...filters } : state.search.filters,
              isSearching: true
            }
          }))

          try {
            // Implement search API call here when backend is ready
            // For now, simulate search
            await new Promise(resolve => setTimeout(resolve, 500))
            
            get().actions.addToSearchHistory(query)
            
            set((state) => ({
              search: {
                ...state.search,
                isSearching: false,
                results: [], // Will be populated with actual search results
                totalResults: 0
              }
            }))
          } catch (error) {
            console.error('Search failed:', error)
            set((state) => ({
              search: {
                ...state.search,
                isSearching: false
              }
            }))
          }
        },

        updateSearchFilters: (filters: Partial<SearchFilters>) => {
          set((state) => ({
            search: {
              ...state.search,
              filters: {
                ...state.search.filters,
                ...filters
              }
            }
          }))
        },

        saveSearch: (name: string) => {
          const { query, filters } = get().search
          const savedSearch: SavedSearch = {
            id: generateId(),
            name,
            query,
            filters,
            created_at: new Date().toISOString()
          }

          set((state) => ({
            search: {
              ...state.search,
              savedSearches: [...state.search.savedSearches, savedSearch]
            }
          }))
        },

        loadSavedSearch: (searchId: string) => {
          const savedSearch = get().search.savedSearches.find(s => s.id === searchId)
          if (savedSearch) {
            set((state) => ({
              search: {
                ...state.search,
                query: savedSearch.query,
                filters: savedSearch.filters
              }
            }))
            get().actions.performSearch(savedSearch.query, savedSearch.filters)
          }
        },

        clearSearch: () => {
          set((state) => ({
            search: {
              ...state.search,
              query: '',
              filters: defaultSearchFilters,
              results: [],
              totalResults: 0
            }
          }))
        },

        addToSearchHistory: (query: string) => {
          if (!query.trim()) return
          
          set((state) => ({
            search: {
              ...state.search,
              searchHistory: [
                query,
                ...state.search.searchHistory.filter(h => h !== query)
              ].slice(0, 10) // Keep last 10 searches
            }
          }))
        },

        // Real-time Operations
        connectWebSocket: (conversationId?: number) => {
          // Determine the appropriate WebSocket endpoint
          // Determine WebSocket protocol based on current page protocol
          const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
          const host = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/^https?:\/\//, '') || 'localhost:8000'
          
          let wsUrl: string
          if (conversationId) {
            // Connect to conversation-specific processing updates
            wsUrl = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${host}/ws/feedme/processing/${conversationId}`
          } else {
            // Connect to global updates
            wsUrl = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${host}/ws/feedme/global`
          }
          
          // Ensure user is authenticated before connecting
          if (!feedMeAuth.isAuthenticated()) {
            console.log('FeedMe: Auto-login for WebSocket connection')
            autoLogin()
          }
          
          // Get authenticated WebSocket URL
          wsUrl = feedMeAuth.getWebSocketUrl(wsUrl)
          
          try {
            const ws = new WebSocket(wsUrl)
            
            ws.onopen = () => {
              set((state) => ({
                realtime: {
                  ...state.realtime,
                  isConnected: true,
                  connectionStatus: 'connected',
                  websocket: ws
                }
              }))
              
              get().actions.addNotification({
                type: 'success',
                title: 'Connected',
                message: 'Real-time updates are now active'
              })
              
              // Start heartbeat to keep connection alive
              const heartbeatInterval = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                  ws.send(JSON.stringify({ type: 'ping' }))
                } else {
                  clearInterval(heartbeatInterval)
                }
              }, 30000) // Send ping every 30 seconds
            }

            ws.onmessage = (event) => {
              try {
                const data = JSON.parse(event.data)
                
                // Handle different message types from backend
                switch (data.type) {
                  case 'processing_update':
                    get().actions.handleProcessingUpdate({
                      conversation_id: data.conversation_id,
                      status: data.status,
                      progress: data.progress || 0,
                      message: data.message,
                      examples_extracted: data.examples_extracted
                    })
                    break
                    
                  case 'notification':
                    get().actions.addNotification({
                      type: data.level || 'info',
                      title: data.title,
                      message: data.message
                    })
                    break
                    
                  case 'pong':
                    // Handle heartbeat response
                    console.debug('WebSocket heartbeat received')
                    break
                    
                  case 'error':
                    console.error('WebSocket error message:', data.error)
                    get().actions.addNotification({
                      type: 'error',
                      title: 'Connection Error',
                      message: data.error || 'Unknown WebSocket error'
                    })
                    break
                    
                  case 'approval_update':
                    // Handle approval workflow updates
                    console.log('Approval update received:', data)
                    break
                    
                  default:
                    console.warn('Unknown WebSocket message type:', data.type)
                }
                
                set((state) => ({
                  realtime: {
                    ...state.realtime,
                    lastUpdate: new Date().toISOString()
                  }
                }))
              } catch (error) {
                console.error('Failed to parse WebSocket message:', error)
              }
            }

            ws.onclose = () => {
              set((state) => ({
                realtime: {
                  ...state.realtime,
                  isConnected: false,
                  connectionStatus: 'disconnected',
                  websocket: null
                }
              }))
            }

            ws.onerror = () => {
              set((state) => ({
                realtime: {
                  ...state.realtime,
                  isConnected: false,
                  connectionStatus: 'error',
                  websocket: null
                }
              }))
              
              get().actions.addNotification({
                type: 'error',
                title: 'Connection Error',
                message: 'Failed to connect to real-time updates'
              })
            }
          } catch (error) {
            console.error('Failed to create WebSocket connection:', error)
          }
        },

        disconnectWebSocket: () => {
          const { websocket } = get().realtime
          if (websocket) {
            websocket.close()
          }
          
          set((state) => ({
            realtime: {
              ...state.realtime,
              isConnected: false,
              connectionStatus: 'disconnected',
              websocket: null
            }
          }))
        },

        handleProcessingUpdate: (update: ProcessingUpdate) => {
          set((state) => ({
            realtime: {
              ...state.realtime,
              processingUpdates: {
                ...state.realtime.processingUpdates,
                [update.conversation_id]: update
              }
            }
          }))

          // Update conversation if it exists
          if (get().conversations[update.conversation_id]) {
            get().actions.updateConversation(update.conversation_id, {
              processing_status: update.status
            })
          }

          // Add notification for completion
          if (update.status === 'completed') {
            get().actions.addNotification({
              type: 'success',
              title: 'Processing Complete',
              message: `Conversation processed successfully. ${update.examples_extracted || 0} examples extracted.`
            })
          } else if (update.status === 'failed') {
            get().actions.addNotification({
              type: 'error',
              title: 'Processing Failed',
              message: update.message || 'Conversation processing failed'
            })
          }
        },

        addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => {
          const newNotification = createNotification(notification)
          
          set((state) => ({
            realtime: {
              ...state.realtime,
              notifications: [newNotification, ...state.realtime.notifications]
            }
          }))

          // Auto-remove non-error notifications after 5 seconds
          if (notification.type !== 'error') {
            setTimeout(() => {
              get().actions.markNotificationRead(newNotification.id)
            }, 5000)
          }
        },

        markNotificationRead: (id: string) => {
          set((state) => ({
            realtime: {
              ...state.realtime,
              notifications: state.realtime.notifications.map(n =>
                n.id === id ? { ...n, read: true } : n
              )
            }
          }))
        },

        clearNotifications: () => {
          set((state) => ({
            realtime: {
              ...state.realtime,
              notifications: []
            }
          }))
        },

        // Analytics Operations
        loadAnalytics: async () => {
          set((state) => ({
            analytics: {
              ...state.analytics,
              isLoading: true
            }
          }))

          try {
            const workflowStats = await getApprovalWorkflowStats()
            
            set((state) => ({
              analytics: {
                ...state.analytics,
                workflowStats,
                lastUpdated: new Date().toISOString(),
                isLoading: false
              }
            }))
          } catch (error) {
            console.error('Failed to load analytics:', error)
            set((state) => ({
              analytics: {
                ...state.analytics,
                isLoading: false
              }
            }))
          }
        },

        refreshAnalytics: async () => {
          await get().actions.loadAnalytics()
        },

        // UI Operations
        setActiveTab: (tab: UIState['activeTab']) => {
          set((state) => ({
            ui: {
              ...state.ui,
              activeTab: tab
            }
          }))
        },

        setViewMode: (mode: UIState['viewMode']) => {
          set((state) => ({
            ui: {
              ...state.ui,
              viewMode: mode
            }
          }))
        },

        toggleSidebar: () => {
          set((state) => ({
            ui: {
              ...state.ui,
              sidebarCollapsed: !state.ui.sidebarCollapsed
            }
          }))
        },

        openModal: (modalId: string) => {
          set((state) => ({
            ui: {
              ...state.ui,
              activeModal: modalId
            }
          }))
        },

        closeModal: () => {
          set((state) => ({
            ui: {
              ...state.ui,
              activeModal: null
            }
          }))
        },

        enableBulkActions: () => {
          set((state) => ({
            ui: {
              ...state.ui,
              bulkActionMode: true,
              isMultiSelectMode: true
            }
          }))
        },

        disableBulkActions: () => {
          set((state) => ({
            ui: {
              ...state.ui,
              bulkActionMode: false,
              isMultiSelectMode: false,
              selectedConversations: [],
              selectedFolders: []
            }
          }))
        }
      }
    })),
    {
      name: 'feedme-store',
      partialize: (state) => ({
        // Persist only non-sensitive UI preferences
        ui: {
          viewMode: state.ui.viewMode,
          sidebarCollapsed: state.ui.sidebarCollapsed
        },
        search: {
          searchHistory: state.search.searchHistory,
          savedSearches: state.search.savedSearches
        }
      })
    }
  )
)

// Selectors for optimal performance
export const useConversations = () => useFeedMeStore(state => state.conversationsList)
export const useFolders = () => useFeedMeStore(state => state.folders)
export const useSearch = () => useFeedMeStore(state => state.search)
export const useRealtime = () => useFeedMeStore(state => state.realtime)
export const useAnalytics = () => useFeedMeStore(state => state.analytics)
export const useUI = () => useFeedMeStore(state => state.ui)
export const useActions = () => useFeedMeStore(state => state.actions)

// Hook for WebSocket connection management (to be imported separately)
// Note: Import React in the component that uses this hook
// export const useWebSocketConnection = () => {
//   const { isConnected, connectionStatus } = useRealtime()
//   const { connectWebSocket, disconnectWebSocket } = useActions()
//   
//   React.useEffect(() => {
//     // Auto-connect on mount
//     if (!isConnected && connectionStatus === 'disconnected') {
//       connectWebSocket()
//     }
//     
//     // Cleanup on unmount
//     return () => {
//       if (isConnected) {
//         disconnectWebSocket()
//       }
//     }
//   }, [])
//   
//   return { isConnected, connectionStatus, connectWebSocket, disconnectWebSocket }
// }