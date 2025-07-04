/**
 * Conversations Store - CRUD Operations and Processing Workflows
 * 
 * Handles conversation management with upload workflows, processing status,
 * approval/rejection operations, and optimistic updates.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import { 
  listConversations, 
  uploadTranscriptFile,
  uploadTranscriptText,
  deleteConversation as apiDeleteConversation,
  editConversation as apiEditConversation,
  approveConversation as apiApproveConversation,
  rejectConversation as apiRejectConversation,
  reprocessConversation as apiReprocessConversation,
  type UploadTranscriptResponse,
  type ConversationListResponse,
  type ConversationEditRequest,
  type ApprovalRequest,
  type RejectionRequest
} from '@/lib/feedme-api'

// Types
export interface Conversation extends UploadTranscriptResponse {
  folder_id?: number
  last_updated?: string
  quality_score?: number
  processing_metadata?: {
    extracted_examples: number
    processing_time_ms: number
    ai_confidence: number
    platform_detected?: string
    language_detected?: string
  }
}

export interface ConversationUpload {
  id: string
  type: 'file' | 'text'
  title: string
  file?: File
  content?: string
  autoProcess: boolean
  status: 'preparing' | 'uploading' | 'processing' | 'completed' | 'failed'
  progress: number
  error?: string
  result?: UploadTranscriptResponse
}

export interface ConversationListState {
  items: Conversation[]
  totalCount: number
  currentPage: number
  pageSize: number
  hasNext: boolean
  isLoading: boolean
  lastUpdated: string | null
  searchQuery: string
  sortBy: 'created_at' | 'updated_at' | 'title' | 'quality_score'
  sortOrder: 'asc' | 'desc'
}

export interface ProcessingState {
  activeUploads: Record<string, ConversationUpload>
  processingQueue: number[]
  processingStatus: Record<number, {
    status: 'pending' | 'processing' | 'completed' | 'failed'
    progress: number
    message?: string
    started_at: string
    completed_at?: string
  }>
}

export interface SelectionState {
  selectedIds: Set<number>
  isMultiSelectMode: boolean
  lastSelectedId: number | null
}

interface ConversationsState {
  // Data State
  conversations: Record<number, Conversation>
  conversationsList: ConversationListState
  
  // Processing State
  processing: ProcessingState
  
  // Selection State
  selection: SelectionState
  
  // Cache State
  cache: {
    lastListRequest: string | null
    listCacheExpiry: number
    conversationDetails: Record<number, { data: Conversation, expiry: number }>
  }
}

interface ConversationsActions {
  // List Management
  loadConversations: (options?: {
    page?: number
    pageSize?: number
    search?: string
    sortBy?: ConversationListState['sortBy']
    sortOrder?: ConversationListState['sortOrder']
    forceRefresh?: boolean
  }) => Promise<void>
  
  refreshConversations: () => Promise<void>
  setSearchQuery: (query: string) => void
  setSorting: (sortBy: ConversationListState['sortBy'], sortOrder: ConversationListState['sortOrder']) => void
  
  // CRUD Operations
  getConversation: (id: number, forceRefresh?: boolean) => Promise<Conversation | null>
  updateConversation: (id: number, updates: Partial<Conversation>) => void
  removeConversation: (id: number) => void
  deleteConversation: (id: number) => Promise<void>
  deleteMultipleConversations: (ids: number[]) => Promise<void>
  
  // Upload Operations
  uploadConversation: (upload: Omit<ConversationUpload, 'id' | 'status' | 'progress'>) => Promise<string>
  cancelUpload: (uploadId: string) => void
  retryUpload: (uploadId: string) => Promise<void>
  clearCompletedUploads: () => void
  
  // Processing Operations
  reprocessConversation: (id: number) => Promise<void>
  reprocessMultipleConversations: (ids: number[]) => Promise<void>
  
  // Approval Workflow
  approveConversation: (id: number, request: ApprovalRequest) => Promise<void>
  rejectConversation: (id: number, request: RejectionRequest) => Promise<void>
  editConversation: (id: number, request: ConversationEditRequest) => Promise<void>
  
  // Selection Management
  selectConversation: (id: number, selected: boolean, useShift?: boolean) => void
  selectAllConversations: (selected: boolean) => void
  clearSelection: () => void
  toggleMultiSelectMode: () => void
  
  // Bulk Operations
  bulkApprove: (ids: number[], request: Omit<ApprovalRequest, 'conversation_id'>) => Promise<void>
  bulkReject: (ids: number[], request: Omit<RejectionRequest, 'conversation_id'>) => Promise<void>
  bulkAssignToFolder: (ids: number[], folderId: number | null) => Promise<void>
  
  // Cache Management
  invalidateCache: (conversationId?: number) => void
  clearCache: () => void
  
  // Utilities
  exportConversations: (ids: number[], format: 'json' | 'csv') => Promise<void>
  getConversationStats: () => {
    total: number
    approved: number
    pending: number
    rejected: number
    processing: number
  }
}

export interface ConversationsStore extends ConversationsState {
  actions: ConversationsActions
}

// Store Implementation
export const useConversationsStore = create<ConversationsStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial State
      conversations: {},
      conversationsList: {
        items: [],
        totalCount: 0,
        currentPage: 1,
        pageSize: 20,
        hasNext: false,
        isLoading: false,
        lastUpdated: null,
        searchQuery: '',
        sortBy: 'created_at',
        sortOrder: 'desc'
      },
      
      processing: {
        activeUploads: {},
        processingQueue: [],
        processingStatus: {}
      },
      
      selection: {
        selectedIds: new Set(),
        isMultiSelectMode: false,
        lastSelectedId: null
      },
      
      cache: {
        lastListRequest: null,
        listCacheExpiry: 0,
        conversationDetails: {}
      },
      
      actions: {
        // ===========================
        // List Management
        // ===========================
        
        loadConversations: async (options = {}) => {
          const state = get()
          const {
            page = 1,
            pageSize = 20,
            search = state.conversationsList.searchQuery,
            sortBy = state.conversationsList.sortBy,
            sortOrder = state.conversationsList.sortOrder,
            forceRefresh = false
          } = options
          
          // Check cache
          const cacheKey = `${page}-${pageSize}-${search}-${sortBy}-${sortOrder}`
          const now = Date.now()
          
          if (!forceRefresh && 
              state.cache.lastListRequest === cacheKey && 
              now < state.cache.listCacheExpiry) {
            console.log('Using cached conversation list')
            return
          }
          
          set(state => ({
            conversationsList: {
              ...state.conversationsList,
              isLoading: true,
              currentPage: page,
              pageSize,
              searchQuery: search,
              sortBy,
              sortOrder
            }
          }))
          
          try {
            const response: ConversationListResponse = await listConversations(
              page,
              pageSize,
              search || undefined,
              `${sortBy}:${sortOrder}`
            )
            
            // Update conversations map
            const conversationsMap = { ...get().conversations }
            response.conversations.forEach(conv => {
              conversationsMap[conv.id] = conv as Conversation
            })
            
            // Update list state
            set(state => ({
              conversations: conversationsMap,
              conversationsList: {
                ...state.conversationsList,
                items: response.conversations as Conversation[],
                totalCount: response.total_count,
                hasNext: response.has_next,
                isLoading: false,
                lastUpdated: new Date().toISOString()
              },
              cache: {
                ...state.cache,
                lastListRequest: cacheKey,
                listCacheExpiry: now + (5 * 60 * 1000) // 5 minutes
              }
            }))
            
          } catch (error) {
            console.error('Failed to load conversations:', error)
            
            set(state => ({
              conversationsList: {
                ...state.conversationsList,
                isLoading: false
              }
            }))
            
            throw error
          }
        },
        
        refreshConversations: async () => {
          const state = get()
          await state.actions.loadConversations({
            page: state.conversationsList.currentPage,
            forceRefresh: true
          })
        },
        
        setSearchQuery: (query) => {
          set(state => ({
            conversationsList: {
              ...state.conversationsList,
              searchQuery: query,
              currentPage: 1
            }
          }))
          
          // Debounce search
          const timeoutId = setTimeout(() => {
            get().actions.loadConversations({ page: 1 })
          }, 300)
          
          // Store timeout for cleanup if needed
          ;(globalThis as any).searchTimeoutId = timeoutId
        },
        
        setSorting: (sortBy, sortOrder) => {
          set(state => ({
            conversationsList: {
              ...state.conversationsList,
              sortBy,
              sortOrder,
              currentPage: 1
            }
          }))
          
          get().actions.loadConversations({ page: 1 })
        },
        
        // ===========================
        // CRUD Operations
        // ===========================
        
        getConversation: async (id, forceRefresh = false) => {
          const state = get()
          
          // Check cache first
          const cached = state.cache.conversationDetails[id]
          const now = Date.now()
          
          if (!forceRefresh && cached && now < cached.expiry) {
            return cached.data
          }
          
          // Check in-memory conversations
          if (!forceRefresh && state.conversations[id]) {
            return state.conversations[id]
          }
          
          try {
            // In a real implementation, this would be a specific API call
            // For now, we'll check if it's in the list or load the list
            if (!state.conversations[id]) {
              await state.actions.loadConversations({ forceRefresh: true })
            }
            
            const conversation = get().conversations[id]
            
            if (conversation) {
              // Update cache
              set(state => ({
                cache: {
                  ...state.cache,
                  conversationDetails: {
                    ...state.cache.conversationDetails,
                    [id]: {
                      data: conversation,
                      expiry: now + (10 * 60 * 1000) // 10 minutes
                    }
                  }
                }
              }))
              
              return conversation
            }
            
            return null
            
          } catch (error) {
            console.error(`Failed to get conversation ${id}:`, error)
            return null
          }
        },
        
        updateConversation: (id, updates) => {
          set(state => {
            const existing = state.conversations[id]
            if (!existing) return state
            
            const updated = { ...existing, ...updates }
            
            return {
              conversations: {
                ...state.conversations,
                [id]: updated
              },
              conversationsList: {
                ...state.conversationsList,
                items: state.conversationsList.items.map(item => 
                  item.id === id ? updated : item
                )
              }
            }
          })
        },
        
        removeConversation: (id) => {
          set(state => {
            const conversations = { ...state.conversations }
            delete conversations[id]
            
            return {
              conversations,
              conversationsList: {
                ...state.conversationsList,
                items: state.conversationsList.items.filter(item => item.id !== id),
                totalCount: Math.max(0, state.conversationsList.totalCount - 1)
              },
              selection: {
                ...state.selection,
                selectedIds: new Set([...state.selection.selectedIds].filter(selectedId => selectedId !== id))
              }
            }
          })
        },
        
        deleteConversation: async (id) => {
          try {
            // Optimistic update
            get().actions.removeConversation(id)
            
            // API call
            await apiDeleteConversation(id)
            
            // Invalidate cache
            get().actions.invalidateCache(id)
            
          } catch (error) {
            console.error(`Failed to delete conversation ${id}:`, error)
            
            // Revert optimistic update by refreshing
            await get().actions.refreshConversations()
            
            throw error
          }
        },
        
        deleteMultipleConversations: async (ids) => {
          const errors: Array<{ id: number, error: Error }> = []
          
          // Process deletions in parallel with limited concurrency
          const chunks = []
          for (let i = 0; i < ids.length; i += 3) {
            chunks.push(ids.slice(i, i + 3))
          }
          
          for (const chunk of chunks) {
            await Promise.allSettled(
              chunk.map(async (id) => {
                try {
                  await get().actions.deleteConversation(id)
                } catch (error) {
                  errors.push({ id, error: error as Error })
                }
              })
            )
          }
          
          if (errors.length > 0) {
            console.error('Some deletions failed:', errors)
            throw new Error(`Failed to delete ${errors.length} conversations`)
          }
        },
        
        // ===========================
        // Upload Operations
        // ===========================
        
        uploadConversation: async (uploadData) => {
          const uploadId = `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
          
          const upload: ConversationUpload = {
            ...uploadData,
            id: uploadId,
            status: 'preparing',
            progress: 0
          }
          
          // Add to active uploads
          set(state => ({
            processing: {
              ...state.processing,
              activeUploads: {
                ...state.processing.activeUploads,
                [uploadId]: upload
              }
            }
          }))
          
          try {
            // Update status to uploading
            set(state => ({
              processing: {
                ...state.processing,
                activeUploads: {
                  ...state.processing.activeUploads,
                  [uploadId]: {
                    ...state.processing.activeUploads[uploadId],
                    status: 'uploading',
                    progress: 10
                  }
                }
              }
            }))
            
            let response: UploadTranscriptResponse
            
            if (upload.type === 'file' && upload.file) {
              response = await uploadTranscriptFile(
                upload.title,
                upload.file,
                upload.autoProcess
              )
            } else if (upload.type === 'text' && upload.content) {
              response = await uploadTranscriptText(
                upload.title,
                upload.content,
                upload.autoProcess
              )
            } else {
              throw new Error('Invalid upload configuration')
            }
            
            // Update progress
            set(state => ({
              processing: {
                ...state.processing,
                activeUploads: {
                  ...state.processing.activeUploads,
                  [uploadId]: {
                    ...state.processing.activeUploads[uploadId],
                    status: upload.autoProcess ? 'processing' : 'completed',
                    progress: upload.autoProcess ? 75 : 100,
                    result: response
                  }
                }
              }
            }))
            
            // Add to conversations
            const conversation = response as Conversation
            set(state => ({
              conversations: {
                ...state.conversations,
                [conversation.id]: conversation
              }
            }))
            
            // If auto-processing, add to processing queue
            if (upload.autoProcess) {
              set(state => ({
                processing: {
                  ...state.processing,
                  processingQueue: [...state.processing.processingQueue, conversation.id],
                  processingStatus: {
                    ...state.processing.processingStatus,
                    [conversation.id]: {
                      status: 'pending',
                      progress: 0,
                      started_at: new Date().toISOString()
                    }
                  }
                }
              }))
            }
            
            // Mark upload as completed
            setTimeout(() => {
              set(state => ({
                processing: {
                  ...state.processing,
                  activeUploads: {
                    ...state.processing.activeUploads,
                    [uploadId]: {
                      ...state.processing.activeUploads[uploadId],
                      status: 'completed',
                      progress: 100
                    }
                  }
                }
              }))
            }, 1000)
            
            // Refresh conversations list
            get().actions.invalidateCache()
            
            return uploadId
            
          } catch (error) {
            console.error('Upload failed:', error)
            
            // Update upload status
            set(state => ({
              processing: {
                ...state.processing,
                activeUploads: {
                  ...state.processing.activeUploads,
                  [uploadId]: {
                    ...state.processing.activeUploads[uploadId],
                    status: 'failed',
                    error: error instanceof Error ? error.message : 'Upload failed'
                  }
                }
              }
            }))
            
            throw error
          }
        },
        
        cancelUpload: (uploadId) => {
          set(state => {
            const uploads = { ...state.processing.activeUploads }
            delete uploads[uploadId]
            
            return {
              processing: {
                ...state.processing,
                activeUploads: uploads
              }
            }
          })
        },
        
        retryUpload: async (uploadId) => {
          const state = get()
          const upload = state.processing.activeUploads[uploadId]
          
          if (upload) {
            // Remove failed upload and create new one
            get().actions.cancelUpload(uploadId)
            
            // Create new upload with same data
            await get().actions.uploadConversation({
              type: upload.type,
              title: upload.title,
              file: upload.file,
              content: upload.content,
              autoProcess: upload.autoProcess
            })
          }
        },
        
        clearCompletedUploads: () => {
          set(state => {
            const activeUploads = { ...state.processing.activeUploads }
            
            Object.keys(activeUploads).forEach(uploadId => {
              const upload = activeUploads[uploadId]
              if (upload.status === 'completed' || upload.status === 'failed') {
                delete activeUploads[uploadId]
              }
            })
            
            return {
              processing: {
                ...state.processing,
                activeUploads
              }
            }
          })
        },
        
        // ===========================
        // Processing Operations
        // ===========================
        
        reprocessConversation: async (id) => {
          try {
            // Add to processing queue
            set(state => ({
              processing: {
                ...state.processing,
                processingQueue: [...state.processing.processingQueue, id],
                processingStatus: {
                  ...state.processing.processingStatus,
                  [id]: {
                    status: 'pending',
                    progress: 0,
                    started_at: new Date().toISOString()
                  }
                }
              }
            }))
            
            await apiReprocessConversation(id)
            
            // The processing status will be updated via WebSocket
            
          } catch (error) {
            console.error(`Failed to reprocess conversation ${id}:`, error)
            
            // Remove from processing queue
            set(state => ({
              processing: {
                ...state.processing,
                processingQueue: state.processing.processingQueue.filter(queueId => queueId !== id),
                processingStatus: {
                  ...state.processing.processingStatus,
                  [id]: {
                    ...state.processing.processingStatus[id],
                    status: 'failed',
                    message: error instanceof Error ? error.message : 'Processing failed'
                  }
                }
              }
            }))
            
            throw error
          }
        },
        
        reprocessMultipleConversations: async (ids) => {
          const errors: Array<{ id: number, error: Error }> = []
          
          for (const id of ids) {
            try {
              await get().actions.reprocessConversation(id)
            } catch (error) {
              errors.push({ id, error: error as Error })
            }
          }
          
          if (errors.length > 0) {
            console.error('Some reprocessing failed:', errors)
            throw new Error(`Failed to reprocess ${errors.length} conversations`)
          }
        },
        
        // ===========================
        // Approval Workflow
        // ===========================
        
        approveConversation: async (id, request) => {
          try {
            // Optimistic update
            get().actions.updateConversation(id, { 
              processing_status: 'approved' as any,
              last_updated: new Date().toISOString()
            })
            
            await apiApproveConversation(id, request)
            
          } catch (error) {
            console.error(`Failed to approve conversation ${id}:`, error)
            
            // Revert optimistic update
            await get().actions.refreshConversations()
            
            throw error
          }
        },
        
        rejectConversation: async (id, request) => {
          try {
            // Optimistic update
            get().actions.updateConversation(id, { 
              processing_status: 'rejected' as any,
              last_updated: new Date().toISOString()
            })
            
            await apiRejectConversation(id, request)
            
          } catch (error) {
            console.error(`Failed to reject conversation ${id}:`, error)
            
            // Revert optimistic update
            await get().actions.refreshConversations()
            
            throw error
          }
        },
        
        editConversation: async (id, request) => {
          try {
            const result = await apiEditConversation(id, request)
            
            // Update conversation with new data
            get().actions.updateConversation(id, result as Partial<Conversation>)
            
          } catch (error) {
            console.error(`Failed to edit conversation ${id}:`, error)
            throw error
          }
        },
        
        // ===========================
        // Selection Management
        // ===========================
        
        selectConversation: (id, selected, useShift = false) => {
          set(state => {
            const selectedIds = new Set(state.selection.selectedIds)
            
            if (useShift && state.selection.lastSelectedId !== null) {
              // Range selection
              const conversations = state.conversationsList.items
              const lastIndex = conversations.findIndex(c => c.id === state.selection.lastSelectedId)
              const currentIndex = conversations.findIndex(c => c.id === id)
              
              if (lastIndex !== -1 && currentIndex !== -1) {
                const start = Math.min(lastIndex, currentIndex)
                const end = Math.max(lastIndex, currentIndex)
                
                for (let i = start; i <= end; i++) {
                  if (selected) {
                    selectedIds.add(conversations[i].id)
                  } else {
                    selectedIds.delete(conversations[i].id)
                  }
                }
              }
            } else {
              // Single selection
              if (selected) {
                selectedIds.add(id)
              } else {
                selectedIds.delete(id)
              }
            }
            
            return {
              selection: {
                ...state.selection,
                selectedIds,
                lastSelectedId: id
              }
            }
          })
        },
        
        selectAllConversations: (selected) => {
          set(state => {
            const selectedIds = selected 
              ? new Set(state.conversationsList.items.map(c => c.id))
              : new Set<number>()
            
            return {
              selection: {
                ...state.selection,
                selectedIds
              }
            }
          })
        },
        
        clearSelection: () => {
          set(state => ({
            selection: {
              ...state.selection,
              selectedIds: new Set(),
              lastSelectedId: null
            }
          }))
        },
        
        toggleMultiSelectMode: () => {
          set(state => ({
            selection: {
              ...state.selection,
              isMultiSelectMode: !state.selection.isMultiSelectMode,
              selectedIds: new Set()
            }
          }))
        },
        
        // ===========================
        // Bulk Operations
        // ===========================
        
        bulkApprove: async (ids, request) => {
          const errors: Array<{ id: number, error: Error }> = []
          
          for (const id of ids) {
            try {
              await get().actions.approveConversation(id, { ...request, conversation_id: id })
            } catch (error) {
              errors.push({ id, error: error as Error })
            }
          }
          
          if (errors.length > 0) {
            throw new Error(`Failed to approve ${errors.length} conversations`)
          }
        },
        
        bulkReject: async (ids, request) => {
          const errors: Array<{ id: number, error: Error }> = []
          
          for (const id of ids) {
            try {
              await get().actions.rejectConversation(id, { ...request, conversation_id: id })
            } catch (error) {
              errors.push({ id, error: error as Error })
            }
          }
          
          if (errors.length > 0) {
            throw new Error(`Failed to reject ${errors.length} conversations`)
          }
        },
        
        bulkAssignToFolder: async (ids, folderId) => {
          // Update optimistically
          ids.forEach(id => {
            get().actions.updateConversation(id, { folder_id: folderId || undefined })
          })
          
          try {
            // In a real implementation, this would be a bulk API call
            // For now, we'll update individually
            console.log(`Bulk assigning ${ids.length} conversations to folder ${folderId}`)
            
          } catch (error) {
            console.error('Bulk folder assignment failed:', error)
            
            // Revert optimistic updates
            await get().actions.refreshConversations()
            
            throw error
          }
        },
        
        // ===========================
        // Cache Management
        // ===========================
        
        invalidateCache: (conversationId) => {
          set(state => {
            if (conversationId) {
              const conversationDetails = { ...state.cache.conversationDetails }
              delete conversationDetails[conversationId]
              
              return {
                cache: {
                  ...state.cache,
                  conversationDetails
                }
              }
            } else {
              return {
                cache: {
                  lastListRequest: null,
                  listCacheExpiry: 0,
                  conversationDetails: {}
                }
              }
            }
          })
        },
        
        clearCache: () => {
          set(state => ({
            cache: {
              lastListRequest: null,
              listCacheExpiry: 0,
              conversationDetails: {}
            }
          }))
        },
        
        // ===========================
        // Utilities
        // ===========================
        
        exportConversations: async (ids, format) => {
          const state = get()
          const conversations = ids.map(id => state.conversations[id]).filter(Boolean)
          
          if (format === 'json') {
            const data = {
              conversations,
              exported_at: new Date().toISOString(),
              total_count: conversations.length
            }
            
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = `feedme-conversations-${Date.now()}.json`
            link.click()
            URL.revokeObjectURL(url)
            
          } else if (format === 'csv') {
            const headers = ['ID', 'Title', 'Status', 'Created At', 'Updated At', 'Examples Count', 'Quality Score']
            const rows = conversations.map(conv => [
              conv.id,
              conv.title,
              conv.processing_status,
              conv.created_at,
              conv.updated_at,
              conv.examples_count || 0,
              conv.quality_score || 0
            ])
            
            const csvContent = [headers, ...rows]
              .map(row => row.map(cell => `"${cell}"`).join(','))
              .join('\n')
            
            const blob = new Blob([csvContent], { type: 'text/csv' })
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = `feedme-conversations-${Date.now()}.csv`
            link.click()
            URL.revokeObjectURL(url)
          }
        },
        
        getConversationStats: () => {
          const state = get()
          const conversations = Object.values(state.conversations)
          
          return {
            total: conversations.length,
            approved: conversations.filter(c => (c as any).processing_status === 'approved').length,
            pending: conversations.filter(c => (c as any).processing_status === 'pending').length,
            rejected: conversations.filter(c => (c as any).processing_status === 'rejected').length,
            processing: Object.keys(state.processing.processingStatus).length
          }
        }
      }
    })),
    {
      name: 'feedme-conversations-store'
    }
  )
)

// Convenience hooks
export const useConversations = () => useConversationsStore(state => state.conversationsList)

export const useConversationSelection = () => useConversationsStore(state => state.selection)

export const useProcessingState = () => useConversationsStore(state => state.processing)

export const useConversationsActions = () => useConversationsStore(state => state.actions)

export const useConversationById = (id: number) => useConversationsStore(state => state.conversations[id])