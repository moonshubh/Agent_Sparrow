/**
 * Enhanced Folders Store - Flawless Folder Management
 * 
 * Refined implementation focusing on create, update, delete, and move operations
 * with comprehensive error handling, optimistic updates, and data consistency.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import { 
  listFolders,
  createFolder as apiCreateFolder,
  updateFolder as apiUpdateFolder,
  deleteFolder as apiDeleteFolder,
  assignConversationsToFolder as apiAssignConversationsToFolder,
  feedMeApi,
  type FeedMeFolder,
  type FolderListResponse,
  type CreateFolderRequest,
  type UpdateFolderRequest
} from '@/lib/feedme-api'

// Constants
const UNASSIGNED_FOLDER_ID = 0
const MAX_FOLDER_NAME_LENGTH = 100
const MAX_FOLDER_DEPTH = 5

// Enhanced types
export interface Folder extends FeedMeFolder {
  isExpanded?: boolean
  isSelected?: boolean
  isDragOver?: boolean
  children?: Folder[]
  level?: number
  conversationCount?: number
  isLoading?: boolean
  hasError?: boolean
  errorMessage?: string
}

export interface FolderOperation {
  id: string
  type: 'create' | 'update' | 'delete' | 'move'
  status: 'pending' | 'success' | 'error'
  folderId?: number
  conversationIds?: number[]
  errorMessage?: string
  timestamp: Date
}

interface ValidationError {
  field: string
  message: string
}

interface FoldersState {
  // Data State
  folders: Record<number, Folder>
  folderTree: Folder[]
  isLoading: boolean
  lastUpdated: string | null
  
  // Operation tracking
  pendingOperations: Map<string, FolderOperation>
  operationHistory: FolderOperation[]
  
  // UI State
  selectedFolderIds: Set<number>
  expandedFolderIds: Set<number>
  
  // Drag & Drop State
  dragState: {
    isDragging: boolean
    draggedFolderId: number | null
    draggedConversationIds: number[]
    dropTargetFolderId: number | null
    canDrop: boolean
  }
  
  // Actions
  actions: {
    // Core Operations (Enhanced)
    createFolder: (request: CreateFolderRequest) => Promise<Folder>
    updateFolder: (id: number, request: UpdateFolderRequest) => Promise<void>
    deleteFolder: (id: number, options?: { moveConversationsTo?: number, force?: boolean }) => Promise<void>
    moveConversations: (conversationIds: number[], fromFolderId: number | null, toFolderId: number | null) => Promise<void>
    
    // Data Management
    loadFolders: (force?: boolean) => Promise<void>
    refreshFolders: () => Promise<void>
    
    // Validation
    validateFolderName: (name: string, parentId?: number | null) => ValidationError[]
    validateFolderMove: (folderId: number, newParentId: number | null) => ValidationError[]
    validateConversationMove: (conversationIds: number[], targetFolderId: number | null) => ValidationError[]
    
    // Tree Management
    expandFolder: (id: number, expanded: boolean) => void
    toggleFolder: (id: number) => void
    selectFolder: (id: number, multi?: boolean) => void
    deselectAllFolders: () => void
    
    // Operation Management
    getOperationStatus: (operationId: string) => FolderOperation | null
    cancelOperation: (operationId: string) => void
    clearOperationHistory: () => void
    
    // Drag & Drop
    startDrag: (folderId?: number, conversationIds?: number[]) => void
    updateDragTarget: (targetFolderId: number | null) => void
    endDrag: (targetFolderId?: number | null) => Promise<void>
    cancelDrag: () => void
  }
}

// Validation utilities
const validateFolderName = (name: string, existingNames: string[] = []): ValidationError[] => {
  const errors: ValidationError[] = []
  
  if (!name.trim()) {
    errors.push({ field: 'name', message: 'Folder name is required' })
  } else if (name.trim().length > MAX_FOLDER_NAME_LENGTH) {
    errors.push({ field: 'name', message: `Folder name must be ${MAX_FOLDER_NAME_LENGTH} characters or less` })
  } else if (existingNames.includes(name.trim())) {
    errors.push({ field: 'name', message: 'A folder with this name already exists' })
  }
  
  // Check for invalid characters
  const invalidChars = /[<>:"/\\|?*]/
  if (invalidChars.test(name)) {
    errors.push({ field: 'name', message: 'Folder name contains invalid characters' })
  }
  
  return errors
}

const calculateFolderDepth = (folders: Record<number, Folder>, folderId: number): number => {
  let depth = 0
  let currentFolder = folders[folderId]
  
  while (currentFolder && currentFolder.parent_id && depth < MAX_FOLDER_DEPTH + 1) {
    depth++
    currentFolder = folders[currentFolder.parent_id]
  }
  
  return depth
}

const wouldCreateCycle = (folders: Record<number, Folder>, folderId: number, newParentId: number): boolean => {
  let currentId = newParentId
  
  while (currentId && currentId !== folderId) {
    const folder = folders[currentId]
    if (!folder || !folder.parent_id) break
    currentId = folder.parent_id
  }
  
  return currentId === folderId
}

// Generate unique operation ID
const generateOperationId = (): string => {
  return `op_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

// Build folder tree from flat structure
const buildFolderTree = (folders: Record<number, Folder>): Folder[] => {
  const tree: Folder[] = []
  const folderArray = Object.values(folders)
  
  // Sort by name for consistent ordering
  folderArray.sort((a, b) => a.name.localeCompare(b.name))
  
  // Add root folders first
  const rootFolders = folderArray.filter(f => !f.parent_id)
  
  const addChildren = (folder: Folder, level: number = 0): Folder => {
    const children = folderArray
      .filter(f => f.parent_id === folder.id)
      .map(child => addChildren(child, level + 1))
      .sort((a, b) => a.name.localeCompare(b.name))
    
    return {
      ...folder,
      children,
      level
    }
  }
  
  return rootFolders.map(folder => addChildren(folder))
}

export const useEnhancedFoldersStore = create<FoldersState>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial State
      folders: {},
      folderTree: [],
      isLoading: false,
      lastUpdated: null,
      pendingOperations: new Map(),
      operationHistory: [],
      selectedFolderIds: new Set(),
      expandedFolderIds: new Set(),
      dragState: {
        isDragging: false,
        draggedFolderId: null,
        draggedConversationIds: [],
        dropTargetFolderId: null,
        canDrop: false
      },
      
      actions: {
        // Enhanced Create Folder
        createFolder: async (request) => {
          const operationId = generateOperationId()
          
          try {
            // Validation
            const existingNames = Object.values(get().folders)
              .filter(f => f.parent_id === request.parent_id)
              .map(f => f.name)
            
            const validationErrors = validateFolderName(request.name, existingNames)
            if (validationErrors.length > 0) {
              throw new Error(validationErrors[0].message)
            }
            
            // Check depth limit
            if (request.parent_id) {
              const depth = calculateFolderDepth(get().folders, request.parent_id)
              if (depth >= MAX_FOLDER_DEPTH) {
                throw new Error(`Maximum folder depth of ${MAX_FOLDER_DEPTH} exceeded`)
              }
            }
            
            // Track operation
            const operation: FolderOperation = {
              id: operationId,
              type: 'create',
              status: 'pending',
              timestamp: new Date()
            }
            
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation)
            }))
            
            // Optimistic update - create temporary folder
            const tempId = Date.now() // Temporary ID
            const tempFolder: Folder = {
              id: tempId,
              name: request.name.trim(),
              description: request.description || null,
              color: request.color || '#0095ff',
              parent_id: request.parent_id || null,
              created_by: request.created_by || 'current_user',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              uuid: `temp_${tempId}`,
              conversation_count: 0,
              isExpanded: true,
              isSelected: false,
              isLoading: true
            }
            
            set(state => ({
              folders: {
                ...state.folders,
                [tempId]: tempFolder
              },
              folderTree: buildFolderTree({
                ...state.folders,
                [tempId]: tempFolder
              })
            }))
            
            // Expand parent if exists
            if (request.parent_id) {
              get().actions.expandFolder(request.parent_id, true)
            }
            
            // API call
            const response = await feedMeApi.createFolderSupabase(request)
            const newFolder: Folder = {
              ...response.folder,
              isExpanded: true,
              isSelected: false,
              conversationCount: 0,
              isLoading: false
            }
            
            // Replace temporary folder with real one
            set(state => {
              const folders = { ...state.folders }
              delete folders[tempId]
              folders[newFolder.id] = newFolder
              
              return {
                folders,
                folderTree: buildFolderTree(folders)
              }
            })
            
            // Update operation status
            operation.status = 'success'
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
              operationHistory: [...state.operationHistory, operation].slice(-50) // Keep last 50
            }))
            
            return newFolder
            
          } catch (error) {
            // Remove temporary folder on error
            set(state => {
              const folders = { ...state.folders }
              const tempFolders = Object.keys(folders).filter(id => folders[parseInt(id)]?.isLoading)
              tempFolders.forEach(id => delete folders[parseInt(id)])
              
              const operation: FolderOperation = {
                id: operationId,
                type: 'create',
                status: 'error',
                errorMessage: error instanceof Error ? error.message : 'Failed to create folder',
                timestamp: new Date()
              }
              
              return {
                folders,
                folderTree: buildFolderTree(folders),
                pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
                operationHistory: [...state.operationHistory, operation].slice(-50)
              }
            })
            
            throw error
          }
        },
        
        // Enhanced Update Folder
        updateFolder: async (id, request) => {
          const operationId = generateOperationId()
          
          try {
            const currentFolder = get().folders[id]
            if (!currentFolder) {
              throw new Error('Folder not found')
            }
            
            // Validation
            if (request.name) {
              const existingNames = Object.values(get().folders)
                .filter(f => f.parent_id === currentFolder.parent_id && f.id !== id)
                .map(f => f.name)
              
              const validationErrors = validateFolderName(request.name, existingNames)
              if (validationErrors.length > 0) {
                throw new Error(validationErrors[0].message)
              }
            }
            
            // Check for parent change cycles
            if (request.parent_id !== undefined && request.parent_id !== currentFolder.parent_id) {
              if (request.parent_id && wouldCreateCycle(get().folders, id, request.parent_id)) {
                throw new Error('Cannot move folder: would create a cycle')
              }
              
              // Check depth limit
              if (request.parent_id) {
                const depth = calculateFolderDepth(get().folders, request.parent_id)
                if (depth >= MAX_FOLDER_DEPTH) {
                  throw new Error(`Maximum folder depth of ${MAX_FOLDER_DEPTH} exceeded`)
                }
              }
            }
            
            // Track operation
            const operation: FolderOperation = {
              id: operationId,
              type: 'update',
              status: 'pending',
              folderId: id,
              timestamp: new Date()
            }
            
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation)
            }))
            
            // Optimistic update
            const updatedFolder = {
              ...currentFolder,
              ...request,
              name: request.name?.trim() || currentFolder.name,
              updated_at: new Date().toISOString(),
              isLoading: true
            }
            
            set(state => ({
              folders: {
                ...state.folders,
                [id]: updatedFolder
              },
              folderTree: buildFolderTree({
                ...state.folders,
                [id]: updatedFolder
              })
            }))
            
            // API call
            const response = await feedMeApi.updateFolderSupabase(id, request)
            
            // Update with server response
            set(state => ({
              folders: {
                ...state.folders,
                [id]: {
                  ...state.folders[id],
                  ...response.folder,
                  isLoading: false
                }
              }
            }))
            
            // Rebuild tree in case parent changed
            set(state => ({
              folderTree: buildFolderTree(state.folders)
            }))
            
            // Update operation status
            operation.status = 'success'
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
              operationHistory: [...state.operationHistory, operation].slice(-50)
            }))
            
          } catch (error) {
            // Revert optimistic update
            set(state => {
              const originalFolder = { ...state.folders[id], isLoading: false }
              
              const operation: FolderOperation = {
                id: operationId,
                type: 'update',
                status: 'error',
                folderId: id,
                errorMessage: error instanceof Error ? error.message : 'Failed to update folder',
                timestamp: new Date()
              }
              
              return {
                folders: {
                  ...state.folders,
                  [id]: originalFolder
                },
                folderTree: buildFolderTree({
                  ...state.folders,
                  [id]: originalFolder
                }),
                pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
                operationHistory: [...state.operationHistory, operation].slice(-50)
              }
            })
            
            throw error
          }
        },
        
        // Enhanced Delete Folder
        deleteFolder: async (id, options = {}) => {
          const operationId = generateOperationId()
          
          try {
            const folder = get().folders[id]
            if (!folder) {
              throw new Error('Folder not found')
            }
            
            // Check if folder has children
            const hasChildren = Object.values(get().folders).some(f => f.parent_id === id)
            if (hasChildren && !options.force) {
              throw new Error('Cannot delete folder with subfolders. Move or delete subfolders first.')
            }
            
            // Check if folder has conversations and no destination specified
            if (folder.conversation_count && folder.conversation_count > 0 && !options.moveConversationsTo && !options.force) {
              throw new Error('Cannot delete folder with conversations. Specify where to move them or use force delete.')
            }
            
            // Track operation
            const operation: FolderOperation = {
              id: operationId,
              type: 'delete',
              status: 'pending',
              folderId: id,
              timestamp: new Date()
            }
            
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation)
            }))
            
            // Optimistic update - mark as loading
            set(state => ({
              folders: {
                ...state.folders,
                [id]: {
                  ...state.folders[id],
                  isLoading: true
                }
              }
            }))
            
            // API call
            await feedMeApi.deleteFolderSupabase(id, options.moveConversationsTo)
            
            // Remove from state
            set(state => {
              const folders = { ...state.folders }
              delete folders[id]
              
              const selectedFolderIds = new Set(state.selectedFolderIds)
              selectedFolderIds.delete(id)
              
              const expandedFolderIds = new Set(state.expandedFolderIds)
              expandedFolderIds.delete(id)
              
              return {
                folders,
                selectedFolderIds,
                expandedFolderIds,
                folderTree: buildFolderTree(folders)
              }
            })
            
            // Update operation status
            operation.status = 'success'
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
              operationHistory: [...state.operationHistory, operation].slice(-50)
            }))
            
          } catch (error) {
            // Revert loading state
            set(state => {
              const operation: FolderOperation = {
                id: operationId,
                type: 'delete',
                status: 'error',
                folderId: id,
                errorMessage: error instanceof Error ? error.message : 'Failed to delete folder',
                timestamp: new Date()
              }
              
              return {
                folders: {
                  ...state.folders,
                  [id]: {
                    ...state.folders[id],
                    isLoading: false,
                    hasError: true,
                    errorMessage: operation.errorMessage
                  }
                },
                pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
                operationHistory: [...state.operationHistory, operation].slice(-50)
              }
            })
            
            throw error
          }
        },
        
        // Enhanced Move Conversations
        moveConversations: async (conversationIds, fromFolderId, toFolderId) => {
          const operationId = generateOperationId()
          
          try {
            // Validation
            if (conversationIds.length === 0) {
              throw new Error('No conversations selected to move')
            }
            
            if (fromFolderId === toFolderId) {
              throw new Error('Source and destination folders are the same')
            }
            
            if (toFolderId && !get().folders[toFolderId]) {
              throw new Error('Destination folder not found')
            }
            
            // Track operation
            const operation: FolderOperation = {
              id: operationId,
              type: 'move',
              status: 'pending',
              conversationIds,
              timestamp: new Date()
            }
            
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation)
            }))
            
            // API call
            await feedMeApi.assignConversationsToFolderSupabase(toFolderId, conversationIds)
            
            // Update conversation counts optimistically
            set(state => {
              const folders = { ...state.folders }
              
              // Decrease count in source folder
              if (fromFolderId && folders[fromFolderId]) {
                folders[fromFolderId] = {
                  ...folders[fromFolderId],
                  conversation_count: Math.max(0, (folders[fromFolderId].conversation_count || 0) - conversationIds.length)
                }
              }
              
              // Increase count in destination folder
              if (toFolderId && folders[toFolderId]) {
                folders[toFolderId] = {
                  ...folders[toFolderId],
                  conversation_count: (folders[toFolderId].conversation_count || 0) + conversationIds.length
                }
              }
              
              return {
                folders,
                folderTree: buildFolderTree(folders)
              }
            })
            
            // Update operation status
            operation.status = 'success'
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
              operationHistory: [...state.operationHistory, operation].slice(-50)
            }))
            
          } catch (error) {
            const operation: FolderOperation = {
              id: operationId,
              type: 'move',
              status: 'error',
              conversationIds,
              errorMessage: error instanceof Error ? error.message : 'Failed to move conversations',
              timestamp: new Date()
            }
            
            set(state => ({
              pendingOperations: new Map(state.pendingOperations).set(operationId, operation),
              operationHistory: [...state.operationHistory, operation].slice(-50)
            }))
            
            throw error
          }
        },
        
        // Data Management
        loadFolders: async (force = false) => {
          if (get().isLoading && !force) return
          
          set({ isLoading: true })
          
          try {
            const response = await listFolders()
            const foldersMap = response.folders.reduce((acc, folder) => {
              acc[folder.id] = {
                ...folder,
                isExpanded: get().expandedFolderIds.has(folder.id),
                isSelected: get().selectedFolderIds.has(folder.id),
                conversationCount: folder.conversation_count || 0
              }
              return acc
            }, {} as Record<number, Folder>)
            
            set({
              folders: foldersMap,
              folderTree: buildFolderTree(foldersMap),
              lastUpdated: new Date().toISOString(),
              isLoading: false
            })
            
          } catch (error) {
            console.error('Failed to load folders:', error)
            set({ isLoading: false })
            throw error
          }
        },
        
        refreshFolders: async () => {
          await get().actions.loadFolders(true)
        },
        
        // Validation Methods
        validateFolderName: (name, parentId) => {
          const existingNames = Object.values(get().folders)
            .filter(f => f.parent_id === parentId)
            .map(f => f.name)
          return validateFolderName(name, existingNames)
        },
        
        validateFolderMove: (folderId, newParentId) => {
          const errors: ValidationError[] = []
          const folders = get().folders
          
          if (!folders[folderId]) {
            errors.push({ field: 'folderId', message: 'Source folder not found' })
            return errors
          }
          
          if (newParentId && !folders[newParentId]) {
            errors.push({ field: 'parentId', message: 'Destination folder not found' })
            return errors
          }
          
          if (newParentId === folderId) {
            errors.push({ field: 'parentId', message: 'Cannot move folder to itself' })
          }
          
          if (newParentId && wouldCreateCycle(folders, folderId, newParentId)) {
            errors.push({ field: 'parentId', message: 'Cannot move folder: would create a cycle' })
          }
          
          if (newParentId) {
            const depth = calculateFolderDepth(folders, newParentId)
            if (depth >= MAX_FOLDER_DEPTH) {
              errors.push({ field: 'parentId', message: `Maximum folder depth of ${MAX_FOLDER_DEPTH} exceeded` })
            }
          }
          
          return errors
        },
        
        validateConversationMove: (conversationIds, targetFolderId) => {
          const errors: ValidationError[] = []
          
          if (conversationIds.length === 0) {
            errors.push({ field: 'conversationIds', message: 'No conversations selected' })
          }
          
          if (targetFolderId && !get().folders[targetFolderId]) {
            errors.push({ field: 'targetFolderId', message: 'Destination folder not found' })
          }
          
          return errors
        },
        
        // Tree Management
        expandFolder: (id, expanded) => {
          set(state => {
            const expandedFolderIds = new Set(state.expandedFolderIds)
            if (expanded) {
              expandedFolderIds.add(id)
            } else {
              expandedFolderIds.delete(id)
            }
            
            return {
              expandedFolderIds,
              folders: {
                ...state.folders,
                [id]: {
                  ...state.folders[id],
                  isExpanded: expanded
                }
              }
            }
          })
        },
        
        toggleFolder: (id) => {
          const isExpanded = get().expandedFolderIds.has(id)
          get().actions.expandFolder(id, !isExpanded)
        },
        
        selectFolder: (id, multi = false) => {
          set(state => {
            let selectedFolderIds = new Set(state.selectedFolderIds)
            
            if (multi) {
              if (selectedFolderIds.has(id)) {
                selectedFolderIds.delete(id)
              } else {
                selectedFolderIds.add(id)
              }
            } else {
              selectedFolderIds = new Set([id])
            }
            
            // Update folder selection state
            const folders = { ...state.folders }
            Object.keys(folders).forEach(folderId => {
              const folderIdNum = parseInt(folderId)
              folders[folderIdNum] = {
                ...folders[folderIdNum],
                isSelected: selectedFolderIds.has(folderIdNum)
              }
            })
            
            return { selectedFolderIds, folders }
          })
        },
        
        deselectAllFolders: () => {
          set(state => {
            const folders = { ...state.folders }
            Object.keys(folders).forEach(folderId => {
              const folderIdNum = parseInt(folderId)
              folders[folderIdNum] = {
                ...folders[folderIdNum],
                isSelected: false
              }
            })
            
            return {
              selectedFolderIds: new Set(),
              folders
            }
          })
        },
        
        // Operation Management
        getOperationStatus: (operationId) => {
          return get().pendingOperations.get(operationId) || null
        },
        
        cancelOperation: (operationId) => {
          set(state => {
            const pendingOperations = new Map(state.pendingOperations)
            pendingOperations.delete(operationId)
            return { pendingOperations }
          })
        },
        
        clearOperationHistory: () => {
          set({ operationHistory: [] })
        },
        
        // Drag & Drop
        startDrag: (folderId, conversationIds = []) => {
          set(state => ({
            dragState: {
              ...state.dragState,
              isDragging: true,
              draggedFolderId: folderId || null,
              draggedConversationIds: conversationIds,
              dropTargetFolderId: null,
              canDrop: false
            }
          }))
        },
        
        updateDragTarget: (targetFolderId) => {
          const state = get()
          const dragState = state.dragState
          
          let canDrop = true
          
          // Validate drop target
          if (dragState.draggedFolderId) {
            // Moving a folder
            const errors = get().actions.validateFolderMove(dragState.draggedFolderId, targetFolderId)
            canDrop = errors.length === 0
          } else if (dragState.draggedConversationIds.length > 0) {
            // Moving conversations
            const errors = get().actions.validateConversationMove(dragState.draggedConversationIds, targetFolderId)
            canDrop = errors.length === 0
          }
          
          set(state => ({
            dragState: {
              ...state.dragState,
              dropTargetFolderId: targetFolderId,
              canDrop
            },
            folders: {
              ...state.folders,
              ...(targetFolderId && state.folders[targetFolderId] ? {
                [targetFolderId]: {
                  ...state.folders[targetFolderId],
                  isDragOver: true
                }
              } : {})
            }
          }))
        },
        
        endDrag: async (targetFolderId) => {
          const state = get()
          const dragState = state.dragState
          
          try {
            if (!dragState.canDrop || !targetFolderId) {
              get().actions.cancelDrag()
              return
            }
            
            if (dragState.draggedFolderId) {
              // Move folder
              await get().actions.updateFolder(dragState.draggedFolderId, {
                parent_id: targetFolderId
              })
            } else if (dragState.draggedConversationIds.length > 0) {
              // Move conversations
              await get().actions.moveConversations(
                dragState.draggedConversationIds,
                null, // We don't track source folder in drag state
                targetFolderId
              )
            }
            
          } catch (error) {
            console.error('Drag operation failed:', error)
            throw error
          } finally {
            get().actions.cancelDrag()
          }
        },
        
        cancelDrag: () => {
          set(state => ({
            dragState: {
              isDragging: false,
              draggedFolderId: null,
              draggedConversationIds: [],
              dropTargetFolderId: null,
              canDrop: false
            },
            folders: Object.fromEntries(
              Object.entries(state.folders).map(([id, folder]) => [
                id,
                { ...folder, isDragOver: false }
              ])
            )
          }))
        }
      }
    })),
    {
      name: 'enhanced-folders-store',
      partialize: (state) => ({
        expandedFolderIds: Array.from(state.expandedFolderIds),
        selectedFolderIds: Array.from(state.selectedFolderIds)
      })
    }
  )
)

// Selectors for common use cases
export const useFolderById = (id: number) => 
  useEnhancedFoldersStore(state => state.folders[id])

export const useFolderTree = () => 
  useEnhancedFoldersStore(state => state.folderTree)

export const useSelectedFolders = () => 
  useEnhancedFoldersStore(state => 
    Array.from(state.selectedFolderIds).map(id => state.folders[id]).filter(Boolean)
  )

export const usePendingOperations = () => 
  useEnhancedFoldersStore(state => Array.from(state.pendingOperations.values()))

export const useFolderActions = () => 
  useEnhancedFoldersStore(state => state.actions)