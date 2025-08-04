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
  feedMeApi,
  type UploadTranscriptResponse,
  type ConversationListResponse,
  type ConversationEditRequest,
  type ApprovalRequest,
  type RejectionRequest
} from '@/lib/feedme-api'
import { useUIStore } from '@/lib/stores/ui-store'

// Constants
const UNASSIGNED_FOLDER_ID = 0

// Helper functions for error handling
interface ApiError extends Error {
  status?: number
  statusText?: string
}

function isApiError(error: unknown): error is ApiError {
  return error instanceof Error && 
    (typeof (error as any).status === 'number' || 
     typeof (error as any).statusText === 'string')
}

function getErrorStatus(error: unknown): number | undefined {
  if (isApiError(error)) {
    return error.status
  }
  return undefined
}

function isNotFoundError(error: unknown): boolean {
  const status = getErrorStatus(error)
  if (status === 404) {
    return true
  }
  
  if (error instanceof Error) {
    return error.message.toLowerCase().includes('not found') || 
           error.message.includes('404')
  }
  
  return false
}

// Types
export interface FeedMeExample {
  id: number
  uuid: string
  conversation_id: number
  question_text: string
  answer_text: string
  context_before?: string
  context_after?: string
  tags: string[]
  issue_type?: string
  resolution_type?: string
  confidence_score: number
  usefulness_score: number
  is_active: boolean
  
  // Source information
  source_page?: number
  source_format?: string
  
  // Review and approval
  review_status?: string
  reviewed_by?: string
  reviewed_at?: string
  reviewer_notes?: string
  
  // Versioning
  version?: number
  
  // AI-generated fields
  generated_by_model?: string
  
  // Additional database fields for PDF processing compatibility
  updated_by?: string
  retrieval_weight?: number
  usage_count?: number
  positive_feedback?: number
  negative_feedback?: number
  last_used_at?: string
  source_position?: string
  extraction_method?: string
  extraction_confidence?: number
  supabase_sync_status?: string
  supabase_sync_at?: string
  supabase_example_id?: string
  supabase_sync_error?: string
  
  created_at: string
  updated_at: string
}

export interface ExampleListResponse {
  examples: FeedMeExample[]
  total_examples: number
  page: number
  page_size: number
  has_next: boolean
}

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
  currentFolderId: number | null // null = show all, 0 = unassigned, >0 = specific folder
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

export interface ExamplesState {
  examplesByConversation: Record<number, FeedMeExample[]>
  examplesLoading: Record<number, boolean>
  examplesError: Record<number, string | null>
  examplesLastUpdated: Record<number, string>
  optimisticUpdates: Record<number, FeedMeExample>
}

interface ConversationsState {
  // Data State
  conversations: Record<number, Conversation>
  conversationsList: ConversationListState
  
  // Examples State
  examples: ExamplesState
  
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
  
  // Internal state for managing timeouts and requests
  _internal: {
    searchTimeoutId: NodeJS.Timeout | null
    activeRequests: Map<string, Promise<Conversation | null>>
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
    folderId?: number | null
    forceRefresh?: boolean
  }) => Promise<void>
  
  refreshConversations: () => Promise<void>
  setSearchQuery: (query: string) => void
  setSorting: (sortBy: ConversationListState['sortBy'], sortOrder: ConversationListState['sortOrder']) => void
  setCurrentFolder: (folderId: number | null) => Promise<void>
  
  // CRUD Operations
  getConversation: (id: number, forceRefresh?: boolean) => Promise<Conversation | null>
  updateConversation: (id: number, updates: Partial<Conversation>) => void
  removeConversation: (id: number) => void
  deleteConversation: (id: number) => Promise<void>
  deleteMultipleConversations: (ids: number[]) => Promise<void>
  
  // Examples Operations
  loadExamples: (conversationId: number, forceRefresh?: boolean) => Promise<void>
  updateExample: (exampleId: number, updates: Partial<FeedMeExample>) => Promise<void>
  deleteExample: (exampleId: number) => Promise<void>
  refreshExamples: (conversationId: number) => Promise<void>
  getExamplesByConversation: (conversationId: number) => FeedMeExample[]
  
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
  cleanup: () => void
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
        sortOrder: 'desc',
        currentFolderId: UNASSIGNED_FOLDER_ID
      },
      
      examples: {
        examplesByConversation: {},
        examplesLoading: {},
        examplesError: {},
        examplesLastUpdated: {},
        optimisticUpdates: {}
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
      
      _internal: {
        searchTimeoutId: null,
        activeRequests: new Map() // Track ongoing requests to prevent duplicates
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
            folderId = state.conversationsList.currentFolderId,
            forceRefresh = false
          } = options
          
          // Check cache
          const cacheKey = `${page}-${pageSize}-${search}-${sortBy}-${sortOrder}-${folderId}`
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
              sortOrder,
              currentFolderId: folderId
            }
          }))
          
          try {
            const response: ConversationListResponse = await listConversations(
              page,
              pageSize,
              search || undefined,
              `${sortBy}:${sortOrder}`,
              folderId !== null ? folderId : undefined
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
            
            // Check if it's a folder-related error
            if (isNotFoundError(error)) {
              
              // Reset to show all conversations if folder doesn't exist
              set(state => ({
                conversationsList: {
                  ...state.conversationsList,
                  currentFolderId: null,
                  isLoading: false,
                  items: [],
                  totalCount: 0
                }
              }))
              
              console.warn(`Folder ${folderId} not found, reset to show all conversations`)
            } else {
              set(state => ({
                conversationsList: {
                  ...state.conversationsList,
                  isLoading: false
                }
              }))
            }
            
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
          
          // Clear any existing timeout to prevent memory leaks
          const currentState = get()
          if (currentState._internal.searchTimeoutId) {
            clearTimeout(currentState._internal.searchTimeoutId)
          }
          
          // Debounce search
          const timeoutId = setTimeout(() => {
            get().actions.loadConversations({ page: 1 })
          }, 300)
          
          // Store timeout for cleanup
          set(state => ({
            _internal: {
              ...state._internal,
              searchTimeoutId: timeoutId
            }
          }))
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
        
        setCurrentFolder: async (folderId) => {
          // Clear cache when switching folders to prevent stale data
          get().actions.clearCache()
          
          // Close folder panel when folder is selected
          useUIStore.getState().actions.closeFolderPanel()
          
          set(state => ({
            conversationsList: {
              ...state.conversationsList,
              currentFolderId: folderId,
              currentPage: 1,
              isLoading: true
            }
          }))
          
          try {
            await get().actions.loadConversations({ 
              page: 1, 
              folderId, 
              forceRefresh: true 
            })
          } catch (error) {
            console.error('Failed to load conversations for folder:', folderId, error)
            
            // Reset to show all conversations on error
            set(state => ({
              conversationsList: {
                ...state.conversationsList,
                currentFolderId: null,
                isLoading: false
              }
            }))
            
            // Show error to user
            throw error
          }
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
          
          // Prevent multiple simultaneous loads for the same conversation
          const loadingKey = `conversation_${id}`
          if (state._internal.activeRequests.has(loadingKey)) {
            // Wait for the existing request to complete
            try {
              await state._internal.activeRequests.get(loadingKey)
              return get().conversations[id] || null
            } catch {
              return null
            }
          }
          
          // Create a new loading promise
          const loadPromise = (async () => {
            try {
              // Make a direct API call to fetch the specific conversation
              const response = await fetch(`/api/v1/feedme/conversations/${id}`)
              
              if (!response.ok) {
                if (response.status === 404) {
                  // Conversation doesn't exist
                  return null
                }
                throw new Error(`Failed to fetch conversation: ${response.statusText}`)
              }
              
              const conversation = await response.json()
              
              // Update the store with the fetched conversation
              set(state => ({
                conversations: {
                  ...state.conversations,
                  [id]: conversation
                },
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
              
            } catch (error) {
              console.error(`Failed to get conversation ${id}:`, error)
              
              // If it's a 404 error, don't remove from store yet
              // Let the UI handle cleanup to prevent cascading updates
              
              return null
            } finally {
              // Clean up the loading promise
              set(state => {
                const activeRequests = new Map(state._internal.activeRequests)
                activeRequests.delete(loadingKey)
                return {
                  _internal: {
                    ...state._internal,
                    activeRequests
                  }
                }
              })
            }
          })()
          
          // Store the loading promise
          set(state => ({
            _internal: {
              ...state._internal,
              activeRequests: new Map(state._internal.activeRequests).set(loadingKey, loadPromise)
            }
          }))
          
          return loadPromise
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
            const errorDetails = errors.map(({ id, error }) => 
              `Conversation ${id}: ${error.message}`
            ).join('; ')
            
            console.error('Some deletions failed:', errors)
            throw new Error(
              `Failed to delete ${errors.length} of ${ids.length} conversations. Details: ${errorDetails}`
            )
          }
        },
        
        // ===========================
        // Upload Operations
        // ===========================
        
        uploadConversation: async (uploadData) => {
          // Generate robust unique ID with crypto.randomUUID() or fallback
          const generateUploadId = (): string => {
            if (typeof crypto !== 'undefined' && crypto.randomUUID) {
              return `upload-${crypto.randomUUID()}`
            } else {
              // Fallback for environments without crypto.randomUUID
              const timestamp = Date.now().toString(36)
              const randomPart = Math.random().toString(36).substr(2, 12)
              const extraRandom = Math.random().toString(36).substr(2, 8)
              return `upload-${timestamp}-${randomPart}-${extraRandom}`
            }
          }
          
          const uploadId = generateUploadId()
          
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
                undefined,
                upload.autoProcess
              )
            } else if (upload.type === 'text' && upload.content) {
              response = await uploadTranscriptText(
                upload.title,
                upload.content,
                undefined,
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
            
            // Show success toast notification
            useUIStore.getState().actions.showToast({
              type: 'success',
              title: 'Upload queued',
              message: `${upload.title} is processing…`,
              duration: 4000
            })
            
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
            } else {
              // Show success toast for manual processing
              useUIStore.getState().actions.showToast({
                type: 'success',
                title: 'Upload complete',
                message: `${upload.title} uploaded successfully`,
                duration: 3000
              })
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
            
            // Show error toast notification
            useUIStore.getState().actions.showToast({
              type: 'error',
              title: 'Upload failed',
              message: `Failed to upload ${upload.title}: ${error instanceof Error ? error.message : 'Unknown error'}`,
              duration: 6000
            })
            
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
            
            await feedMeApi.reprocessConversation(id)
            
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
          const { showToast } = useUIStore.getState().actions
          
          try {
            // Optimistic update
            get().actions.updateConversation(id, { 
              processing_status: 'approved' as any,
              last_updated: new Date().toISOString()
            })
            
            // Get selected example IDs from the examples state if available
            const selectedExampleIds = get().examples.examplesByConversation[id]
              ?.filter(ex => ex.is_active)
              ?.map(ex => ex.id)
            
            // Use new Supabase-integrated endpoint
            const supabaseRequest = {
              approved_by: request.approved_by,
              example_ids: selectedExampleIds?.length ? selectedExampleIds : null, // null means approve all
              reviewer_notes: request.reviewer_notes
            }
            
            const response = await fetch(`/api/v1/feedme/conversations/${id}/examples/approve`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify(supabaseRequest),
            })
            
            if (!response.ok) {
              const error = await response.json()
              throw new Error(error.detail || 'Failed to approve conversation')
            }
            
            const data = await response.json()
            
            // Update conversation with sync status
            get().actions.updateConversation(id, {
              processing_status: 'approved' as any,
              metadata: {
                ...get().conversations[id]?.metadata,
                supabase_synced: true,
                approved_count: data.approved_count
              }
            })
            
            showToast({
              title: 'Conversation Approved',
              message: data.message || `Successfully approved ${data.approved_count} examples. Syncing to Supabase...`,
              type: 'success',
              duration: 5000
            })
            
            // If folder_id is present, trigger folder refresh
            const conversation = get().conversations[id]
            if (conversation?.folder_id) {
              // Import folders store dynamically to avoid circular dependencies
              import('@/lib/stores/folders-store').then(({ useFoldersStore }) => {
                useFoldersStore.getState().actions.loadFolders(true)
              })
            }
            
          } catch (error) {
            console.error(`Failed to approve conversation ${id}:`, error)
            
            // Revert optimistic update
            await get().actions.refreshConversations()
            
            showToast({
              title: 'Approval Failed',
              message: error instanceof Error ? error.message : 'Failed to approve conversation',
              type: 'error'
            })
            
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
              await get().actions.approveConversation(id, request)
            } catch (error) {
              errors.push({ id, error: error as Error })
            }
          }
          
          if (errors.length > 0) {
            const errorDetails = errors.map(({ id, error }) => 
              `Conversation ${id}: ${error.message}`
            ).join('; ')
            
            throw new Error(
              `Failed to approve ${errors.length} of ${ids.length} conversations. Details: ${errorDetails}`
            )
          }
        },
        
        bulkReject: async (ids, request) => {
          const errors: Array<{ id: number, error: Error }> = []
          
          for (const id of ids) {
            try {
              await get().actions.rejectConversation(id, request)
            } catch (error) {
              errors.push({ id, error: error as Error })
            }
          }
          
          if (errors.length > 0) {
            const errorDetails = errors.map(({ id, error }) => 
              `Conversation ${id}: ${error.message}`
            ).join('; ')
            
            throw new Error(
              `Failed to reject ${errors.length} of ${ids.length} conversations. Details: ${errorDetails}`
            )
          }
        },
        
        bulkAssignToFolder: async (ids, folderId) => {
          const state = get()
          const currentFolderId = state.conversationsList.currentFolderId
          
          // Update optimistically
          ids.forEach(id => {
            get().actions.updateConversation(id, { folder_id: folderId || undefined })
          })
          
          try {
            // Import the Supabase-enabled API function
            const { assignConversationsToFolderSupabase } = await import('@/lib/feedme-api')
            
            // Make the API call with Supabase sync
            const result = await assignConversationsToFolderSupabase(folderId, ids)
            
            console.log(`Successfully assigned ${ids.length} conversations to folder ${folderId}`)
            
            // CRITICAL: Hide-after-move logic - remove conversations from current list
            // if they were assigned to a different folder than the current view
            const shouldHideConversations = (
              currentFolderId !== folderId &&  // Different folder
              currentFolderId !== null         // Not viewing all conversations
            )
            
            if (shouldHideConversations) {
              set(state => {
                // Remove from conversations cache
                const updatedConversations = { ...state.conversations }
                ids.forEach(id => {
                  delete updatedConversations[id]
                })
                
                // Remove from current list
                return {
                  conversations: updatedConversations,
                  conversationsList: {
                    ...state.conversationsList,
                    items: state.conversationsList.items.filter(c => !ids.includes(c.id)),
                    totalCount: Math.max(0, state.conversationsList.totalCount - ids.length)
                  }
                }
              })
            }
            
            // Show success notification with Supabase sync status
            useUIStore.getState().actions.showToast({
              type: 'success',
              title: 'Conversations Assigned',
              message: result.message || `Assigned ${ids.length} conversations to folder`,
              duration: 3000
            })
            
          } catch (error) {
            console.error('Bulk folder assignment failed:', error)
            
            // Revert optimistic updates
            await get().actions.refreshConversations()
            
            throw error
          }
        },
        
        // ===========================
        // Examples Operations
        // ===========================
        
        loadExamples: async (conversationId, forceRefresh = false) => {
          const state = get()
          
          // Check if already loading
          if (state.examples.examplesLoading[conversationId]) {
            return
          }
          
          // Check cache
          const lastUpdated = state.examples.examplesLastUpdated[conversationId]
          const cacheValid = lastUpdated && (Date.now() - new Date(lastUpdated).getTime()) < 5 * 60 * 1000 // 5 minutes
          
          if (!forceRefresh && cacheValid && state.examples.examplesByConversation[conversationId]) {
            return
          }
          
          // Set loading state
          set(state => ({
            examples: {
              ...state.examples,
              examplesLoading: {
                ...state.examples.examplesLoading,
                [conversationId]: true
              },
              examplesError: {
                ...state.examples.examplesError,
                [conversationId]: null
              }
            }
          }))
          
          try {
            const response = await feedMeApi.getConversationExamples(conversationId)
            
            set(state => ({
              examples: {
                ...state.examples,
                examplesByConversation: {
                  ...state.examples.examplesByConversation,
                  [conversationId]: response.examples
                },
                examplesLoading: {
                  ...state.examples.examplesLoading,
                  [conversationId]: false
                },
                examplesLastUpdated: {
                  ...state.examples.examplesLastUpdated,
                  [conversationId]: new Date().toISOString()
                }
              }
            }))
            
          } catch (error) {
            // Handle conversation not found errors gracefully
            if (error instanceof Error && error.message.includes('Conversation not found')) {
              console.warn(`Conversation ${conversationId} no longer exists, removing from state`)
              
              // Remove the stale conversation from state
              set(state => {
                const conversations = { ...state.conversations }
                delete conversations[conversationId]
                
                return {
                  ...state,
                  conversations,
                  examples: {
                    ...state.examples,
                    examplesLoading: {
                      ...state.examples.examplesLoading,
                      [conversationId]: false
                    },
                    examplesError: {
                      ...state.examples.examplesError,
                      [conversationId]: null
                    },
                    examplesByConversation: {
                      ...state.examples.examplesByConversation,
                      [conversationId]: []
                    }
                  }
                }
              })
              
              return // Don't throw, just return silently
            }
            
            console.error(`Failed to load examples for conversation ${conversationId}:`, error)
            
            set(state => ({
              examples: {
                ...state.examples,
                examplesLoading: {
                  ...state.examples.examplesLoading,
                  [conversationId]: false
                },
                examplesError: {
                  ...state.examples.examplesError,
                  [conversationId]: error instanceof Error ? error.message : 'Failed to load examples'
                }
              }
            }))
            
            throw error
          }
        },
        
        updateExample: async (exampleId, updates) => {
          const state = get()
          
          // Find the example and conversation
          let conversationId: number | null = null
          let originalExample: FeedMeExample | null = null
          
          for (const [convId, examples] of Object.entries(state.examples.examplesByConversation)) {
            const example = examples.find(ex => ex.id === exampleId)
            if (example) {
              conversationId = parseInt(convId)
              originalExample = example
              break
            }
          }
          
          if (!conversationId || !originalExample) {
            throw new Error('Example not found')
          }
          
          // Optimistic update
          const optimisticExample = { ...originalExample, ...updates }
          
          set(state => ({
            examples: {
              ...state.examples,
              examplesByConversation: {
                ...state.examples.examplesByConversation,
                [conversationId!]: state.examples.examplesByConversation[conversationId!].map(ex =>
                  ex.id === exampleId ? optimisticExample : ex
                )
              },
              optimisticUpdates: {
                ...state.examples.optimisticUpdates,
                [exampleId]: optimisticExample
              }
            }
          }))
          
          try {
            // Make API call (to be implemented)
            await feedMeApi.updateExample(exampleId, updates)
            
            // Remove from optimistic updates on success
            set(state => {
              const optimisticUpdates = { ...state.examples.optimisticUpdates }
              delete optimisticUpdates[exampleId]
              
              return {
                examples: {
                  ...state.examples,
                  optimisticUpdates
                }
              }
            })
            
          } catch (error) {
            console.error(`Failed to update example ${exampleId}:`, error)
            
            // Revert optimistic update
            set(state => {
              const optimisticUpdates = { ...state.examples.optimisticUpdates }
              delete optimisticUpdates[exampleId]
              
              return {
                examples: {
                  ...state.examples,
                  examplesByConversation: {
                    ...state.examples.examplesByConversation,
                    [conversationId!]: state.examples.examplesByConversation[conversationId!].map(ex =>
                      ex.id === exampleId ? originalExample! : ex
                    )
                  },
                  optimisticUpdates
                }
              }
            })
            
            throw error
          }
        },
        
        deleteExample: async (exampleId) => {
          const state = get()
          
          // Find the conversation that contains this example
          let conversationId: number | null = null
          let originalExample: FeedMeExample | null = null
          
          for (const [convId, examples] of Object.entries(state.examples.examplesByConversation)) {
            const example = examples.find(ex => ex.id === exampleId)
            if (example) {
              conversationId = parseInt(convId)
              originalExample = example
              break
            }
          }
          
          if (!conversationId || !originalExample) {
            throw new Error('Example not found')
          }
          
          // Optimistic update - remove the example from the store
          set(state => ({
            examples: {
              ...state.examples,
              examplesByConversation: {
                ...state.examples.examplesByConversation,
                [conversationId!]: state.examples.examplesByConversation[conversationId!].filter(ex => ex.id !== exampleId)
              }
            }
          }))
          
          try {
            // Import and call the delete API function
            const { deleteExample } = await import('@/lib/feedme-api')
            const result = await deleteExample(exampleId)
            
            // Update conversation total_examples count if we have it
            if (state.conversations[conversationId]) {
              const currentExamples = get().examples.examplesByConversation[conversationId] || []
              set(state => ({
                conversations: {
                  ...state.conversations,
                  [conversationId!]: {
                    ...state.conversations[conversationId!],
                    total_examples: currentExamples.length
                  }
                }
              }))
            }
            
            // Show success notification
            useUIStore.getState().actions.showToast({
              type: 'success',
              title: 'Example Deleted',
              message: result.message,
              duration: 3000
            })
            
          } catch (error) {
            console.error(`Failed to delete example ${exampleId}:`, error)
            
            // Revert optimistic update by restoring the example
            set(state => ({
              examples: {
                ...state.examples,
                examplesByConversation: {
                  ...state.examples.examplesByConversation,
                  [conversationId!]: [...(state.examples.examplesByConversation[conversationId!] || []), originalExample!]
                    .sort((a, b) => a.id - b.id) // Maintain order
                }
              }
            }))
            
            // Show error notification
            useUIStore.getState().actions.showToast({
              type: 'error',
              title: 'Delete Failed',
              message: error instanceof Error ? error.message : 'Failed to delete example',
              duration: 4000
            })
            
            throw error
          }
        },
        
        refreshExamples: async (conversationId) => {
          // First, try to load examples from the server
          await get().actions.loadExamples(conversationId, true)
          
          // If no examples found, trigger reprocessing to generate them
          const state = get()
          const examples = state.examples.examplesByConversation[conversationId] || []
          
          if (examples.length === 0) {
            // Show a toast that we're reprocessing
            useUIStore.getState().actions.showToast({
              type: 'info',
              title: 'Reprocessing conversation',
              message: 'No examples found. Attempting to extract Q&A pairs...',
              duration: 4000
            })
            
            try {
              // Trigger reprocessing
              await get().actions.reprocessConversation(conversationId)
              
              // Wait a moment for processing to start
              await new Promise(resolve => setTimeout(resolve, 2000))
              
              // Reload examples after reprocessing
              await get().actions.loadExamples(conversationId, true)
              
              const updatedState = get()
              const updatedExamples = updatedState.examples.examplesByConversation[conversationId] || []
              
              if (updatedExamples.length > 0) {
                useUIStore.getState().actions.showToast({
                  type: 'success',
                  title: 'Examples generated',
                  message: `Found ${updatedExamples.length} Q&A examples after reprocessing`,
                  duration: 3000
                })
              } else {
                useUIStore.getState().actions.showToast({
                  type: 'warning',
                  title: 'No examples available',
                  message: 'This conversation does not contain extractable Q&A examples',
                  duration: 4000
                })
              }
            } catch (error) {
              console.error('Failed to reprocess conversation:', error)
              useUIStore.getState().actions.showToast({
                type: 'error',
                title: 'Reprocessing failed',
                message: 'Could not reprocess the conversation. Please try again.',
                duration: 5000
              })
            }
          }
        },
        
        getExamplesByConversation: (conversationId) => {
          const state = get()
          return state.examples.examplesByConversation[conversationId] || []
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
              conv.created_at, // Use created_at as fallback for updated_at
              conv.total_examples || 0,
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
        },
        
        cleanup: () => {
          const state = get()
          
          // Clear any active search timeout to prevent memory leaks
          if (state._internal.searchTimeoutId) {
            clearTimeout(state._internal.searchTimeoutId)
            set(currentState => ({
              _internal: {
                ...currentState._internal,
                searchTimeoutId: null
              }
            }))
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

export const useExamplesState = () => useConversationsStore(state => state.examples)

export const useExamplesByConversation = (conversationId: number) => useConversationsStore(state => state.examples.examplesByConversation[conversationId])

export const useExamplesLoading = (conversationId: number) => useConversationsStore(state => state.examples.examplesLoading[conversationId] || false)

export const useExamplesError = (conversationId: number) => useConversationsStore(state => state.examples.examplesError[conversationId] || null)
