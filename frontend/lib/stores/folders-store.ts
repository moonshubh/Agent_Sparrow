/**
 * Folders Store - Hierarchical Folder Management
 * 
 * Handles folder operations with hierarchical structure, drag-and-drop support,
 * and conversation assignment workflows.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import { 
  listFolders,
  createFolder as apiCreateFolder,
  updateFolder as apiUpdateFolder,
  deleteFolder as apiDeleteFolder,
  assignConversationsToFolder as apiAssignConversationsToFolder,
  type FeedMeFolder,
  type FolderListResponse,
  type CreateFolderRequest,
  type UpdateFolderRequest
} from '@/lib/feedme-api'

// Types
export interface Folder extends FeedMeFolder {
  isExpanded?: boolean
  isSelected?: boolean
  isDragOver?: boolean
  children?: Folder[]
  level?: number
  conversationCount?: number
}

interface FoldersState {
  // Data State
  folders: Record<number, Folder>
  folderTree: Folder[]
  isLoading: boolean
  lastUpdated: string | null
  
  // UI State
  selectedFolderIds: Set<number>
  expandedFolderIds: Set<number>
  dragState: {
    isDragging: boolean
    draggedFolderId: number | null
    draggedConversationIds: number[]
    dragOverFolderId: number | null
    dragOperation: 'move' | 'copy' | null
  }
  
  // Modal State
  createModalOpen: boolean
  editModalOpen: boolean
  deleteModalOpen: boolean
  targetFolderId: number | null
}

interface FoldersActions {
  // Data Operations
  loadFolders: (forceRefresh?: boolean) => Promise<void>
  refreshFolders: () => Promise<void>
  
  // CRUD Operations
  createFolder: (request: CreateFolderRequest) => Promise<Folder>
  updateFolder: (id: number, request: UpdateFolderRequest) => Promise<void>
  deleteFolder: (id: number, moveConversationsTo?: number) => Promise<void>
  
  // Tree Operations
  buildFolderTree: () => void
  expandFolder: (id: number, expanded?: boolean) => void
  expandAll: () => void
  collapseAll: () => void
  
  // Selection
  selectFolder: (id: number, selected: boolean, clearOthers?: boolean) => void
  clearSelection: () => void
  
  // Conversation Assignment
  assignConversationsToFolder: (conversationIds: number[], folderId: number | null) => Promise<void>
  moveConversationsBetweenFolders: (conversationIds: number[], fromFolderId: number | null, toFolderId: number | null) => Promise<void>
  
  // Drag and Drop
  startDragFolder: (folderId: number) => void
  startDragConversations: (conversationIds: number[]) => void
  dragOverFolder: (folderId: number | null) => void
  dropOnFolder: (targetFolderId: number | null, operation?: 'move' | 'copy') => Promise<void>
  cancelDrag: () => void
  
  // Modal Management
  openCreateModal: (parentFolderId?: number) => void
  openEditModal: (folderId: number) => void
  openDeleteModal: (folderId: number) => void
  closeModals: () => void
  
  // Utilities
  getFolderPath: (folderId: number) => Folder[]
  getFolderDepth: (folderId: number) => number
  getChildFolders: (parentId: number | null) => Folder[]
  updateConversationCounts: (counts: Record<number, number>) => void
}

export interface FoldersStore extends FoldersState {
  actions: FoldersActions
}

// Store Implementation
export const useFoldersStore = create<FoldersStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // Initial State
      folders: {},
      folderTree: [],
      isLoading: false,
      lastUpdated: null,
      
      selectedFolderIds: new Set(),
      expandedFolderIds: new Set(),
      
      dragState: {
        isDragging: false,
        draggedFolderId: null,
        draggedConversationIds: [],
        dragOverFolderId: null,
        dragOperation: null
      },
      
      createModalOpen: false,
      editModalOpen: false,
      deleteModalOpen: false,
      targetFolderId: null,
      
      actions: {
        // ===========================
        // Data Operations
        // ===========================
        
        loadFolders: async (forceRefresh = false) => {
          const state = get()
          
          if (!forceRefresh && Object.keys(state.folders).length > 0) {
            return
          }
          
          set({ isLoading: true })
          
          try {
            const response: FolderListResponse = await listFolders()
            
            const foldersMap: Record<number, Folder> = {}
            response.folders.forEach(folder => {
              foldersMap[folder.id] = {
                ...folder,
                isExpanded: state.expandedFolderIds.has(folder.id),
                isSelected: state.selectedFolderIds.has(folder.id),
                conversationCount: 0
              }
            })
            
            set({
              folders: foldersMap,
              isLoading: false,
              lastUpdated: new Date().toISOString()
            })
            
            // Build tree structure
            get().actions.buildFolderTree()
            
          } catch (error) {
            console.error('Failed to load folders:', error)
            set({ isLoading: false })
            throw error
          }
        },
        
        refreshFolders: async () => {
          await get().actions.loadFolders(true)
        },
        
        // ===========================
        // CRUD Operations
        // ===========================
        
        createFolder: async (request) => {
          try {
            const response = await apiCreateFolder(request)
            
            const newFolder: Folder = {
              ...response,
              isExpanded: true,
              isSelected: false,
              conversationCount: 0
            }
            
            set(state => ({
              folders: {
                ...state.folders,
                [newFolder.id]: newFolder
              }
            }))
            
            // Rebuild tree
            get().actions.buildFolderTree()
            
            // Expand parent if exists
            if (newFolder.parent_id) {
              get().actions.expandFolder(newFolder.parent_id, true)
            }
            
            return newFolder
            
          } catch (error) {
            console.error('Failed to create folder:', error)
            throw error
          }
        },
        
        updateFolder: async (id, request) => {
          try {
            const response = await apiUpdateFolder(id, request)
            
            set(state => ({
              folders: {
                ...state.folders,
                [id]: {
                  ...state.folders[id],
                  ...response
                }
              }
            }))
            
            // Rebuild tree if parent changed
            get().actions.buildFolderTree()
            
          } catch (error) {
            console.error(`Failed to update folder ${id}:`, error)
            throw error
          }
        },
        
        deleteFolder: async (id, moveConversationsTo) => {
          try {
            await apiDeleteFolder(id, moveConversationsTo)
            
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
                expandedFolderIds
              }
            })
            
            // Rebuild tree
            get().actions.buildFolderTree()
            
          } catch (error) {
            console.error(`Failed to delete folder ${id}:`, error)
            throw error
          }
        },
        
        // ===========================
        // Tree Operations
        // ===========================
        
        buildFolderTree: () => {
          const state = get()
          const folders = Object.values(state.folders)
          
          // Build hierarchy
          const folderMap = new Map<number, Folder>()
          const rootFolders: Folder[] = []
          
          // Initialize all folders
          folders.forEach(folder => {
            folderMap.set(folder.id, {
              ...folder,
              children: [],
              level: 0
            })
          })
          
          // Build parent-child relationships
          folders.forEach(folder => {
            const folderNode = folderMap.get(folder.id)!
            
            if (folder.parent_id && folderMap.has(folder.parent_id)) {
              const parent = folderMap.get(folder.parent_id)!
              parent.children!.push(folderNode)
              folderNode.level = (parent.level || 0) + 1
            } else {
              rootFolders.push(folderNode)
            }
          })
          
          // Sort folders by name
          const sortFolders = (folders: Folder[]) => {
            folders.sort((a, b) => a.name.localeCompare(b.name))
            folders.forEach(folder => {
              if (folder.children) {
                sortFolders(folder.children)
              }
            })
          }
          
          sortFolders(rootFolders)
          
          set({ folderTree: rootFolders })
        },
        
        expandFolder: (id, expanded) => {
          set(state => {
            const expandedFolderIds = new Set(state.expandedFolderIds)
            const newExpanded = expanded ?? !expandedFolderIds.has(id)
            
            if (newExpanded) {
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
                  isExpanded: newExpanded
                }
              }
            }
          })
        },
        
        expandAll: () => {
          set(state => {
            const expandedFolderIds = new Set(Object.keys(state.folders).map(Number))
            const folders = { ...state.folders }
            
            Object.keys(folders).forEach(id => {
              folders[Number(id)] = {
                ...folders[Number(id)],
                isExpanded: true
              }
            })
            
            return { expandedFolderIds, folders }
          })
        },
        
        collapseAll: () => {
          set(state => {
            const folders = { ...state.folders }
            
            Object.keys(folders).forEach(id => {
              folders[Number(id)] = {
                ...folders[Number(id)],
                isExpanded: false
              }
            })
            
            return {
              expandedFolderIds: new Set(),
              folders
            }
          })
        },
        
        // ===========================
        // Selection
        // ===========================
        
        selectFolder: (id, selected, clearOthers = false) => {
          set(state => {
            let selectedFolderIds = new Set(state.selectedFolderIds)
            
            if (clearOthers) {
              selectedFolderIds = new Set()
            }
            
            if (selected) {
              selectedFolderIds.add(id)
            } else {
              selectedFolderIds.delete(id)
            }
            
            const folders = { ...state.folders }
            if (folders[id]) {
              folders[id] = {
                ...folders[id],
                isSelected: selected
              }
            }
            
            return { selectedFolderIds, folders }
          })
        },
        
        clearSelection: () => {
          set(state => {
            const folders = { ...state.folders }
            
            state.selectedFolderIds.forEach(id => {
              if (folders[id]) {
                folders[id] = {
                  ...folders[id],
                  isSelected: false
                }
              }
            })
            
            return {
              selectedFolderIds: new Set(),
              folders
            }
          })
        },
        
        // ===========================
        // Conversation Assignment
        // ===========================
        
        assignConversationsToFolder: async (conversationIds, folderId) => {
          try {
            await apiAssignConversationsToFolder(conversationIds, folderId)
            
            // The conversation store will handle updating conversation folder assignments
            console.log(`Assigned ${conversationIds.length} conversations to folder ${folderId}`)
            
          } catch (error) {
            console.error('Failed to assign conversations to folder:', error)
            throw error
          }
        },
        
        moveConversationsBetweenFolders: async (conversationIds, fromFolderId, toFolderId) => {
          try {
            await get().actions.assignConversationsToFolder(conversationIds, toFolderId)
            
            // Update conversation counts
            set(state => {
              const folders = { ...state.folders }
              
              if (fromFolderId && folders[fromFolderId]) {
                folders[fromFolderId] = {
                  ...folders[fromFolderId],
                  conversationCount: Math.max(0, (folders[fromFolderId].conversationCount || 0) - conversationIds.length)
                }
              }
              
              if (toFolderId && folders[toFolderId]) {
                folders[toFolderId] = {
                  ...folders[toFolderId],
                  conversationCount: (folders[toFolderId].conversationCount || 0) + conversationIds.length
                }
              }
              
              return { folders }
            })
            
          } catch (error) {
            console.error('Failed to move conversations between folders:', error)
            throw error
          }
        },
        
        // ===========================
        // Drag and Drop
        // ===========================
        
        startDragFolder: (folderId) => {
          set({
            dragState: {
              isDragging: true,
              draggedFolderId: folderId,
              draggedConversationIds: [],
              dragOverFolderId: null,
              dragOperation: 'move'
            }
          })
        },
        
        startDragConversations: (conversationIds) => {
          set({
            dragState: {
              isDragging: true,
              draggedFolderId: null,
              draggedConversationIds: conversationIds,
              dragOverFolderId: null,
              dragOperation: 'move'
            }
          })
        },
        
        dragOverFolder: (folderId) => {
          set(state => ({
            dragState: {
              ...state.dragState,
              dragOverFolderId: folderId
            },
            folders: {
              ...state.folders,
              ...(folderId && state.folders[folderId] ? {
                [folderId]: {
                  ...state.folders[folderId],
                  isDragOver: true
                }
              } : {})
            }
          }))
        },
        
        dropOnFolder: async (targetFolderId, operation = 'move') => {
          const state = get()
          
          try {
            if (state.dragState.draggedConversationIds.length > 0) {
              // Drop conversations on folder
              await get().actions.assignConversationsToFolder(
                state.dragState.draggedConversationIds,
                targetFolderId
              )
            }
            
            // Handle folder drag-drop operations here if needed
            
          } catch (error) {
            console.error('Drop operation failed:', error)
            throw error
          } finally {
            get().actions.cancelDrag()
          }
        },
        
        cancelDrag: () => {
          set(state => {
            const folders = { ...state.folders }
            
            // Clear all drag over states
            Object.keys(folders).forEach(id => {
              if (folders[Number(id)].isDragOver) {
                folders[Number(id)] = {
                  ...folders[Number(id)],
                  isDragOver: false
                }
              }
            })
            
            return {
              dragState: {
                isDragging: false,
                draggedFolderId: null,
                draggedConversationIds: [],
                dragOverFolderId: null,
                dragOperation: null
              },
              folders
            }
          })
        },
        
        // ===========================
        // Modal Management
        // ===========================
        
        openCreateModal: (parentFolderId) => {
          set({
            createModalOpen: true,
            targetFolderId: parentFolderId || null
          })
        },
        
        openEditModal: (folderId) => {
          set({
            editModalOpen: true,
            targetFolderId: folderId
          })
        },
        
        openDeleteModal: (folderId) => {
          set({
            deleteModalOpen: true,
            targetFolderId: folderId
          })
        },
        
        closeModals: () => {
          set({
            createModalOpen: false,
            editModalOpen: false,
            deleteModalOpen: false,
            targetFolderId: null
          })
        },
        
        // ===========================
        // Utilities
        // ===========================
        
        getFolderPath: (folderId) => {
          const state = get()
          const path: Folder[] = []
          let currentId: number | null = folderId
          
          while (currentId && state.folders[currentId]) {
            const folder = state.folders[currentId]
            path.unshift(folder)
            currentId = folder.parent_id
          }
          
          return path
        },
        
        getFolderDepth: (folderId) => {
          return get().actions.getFolderPath(folderId).length
        },
        
        getChildFolders: (parentId) => {
          const state = get()
          return Object.values(state.folders).filter(folder => folder.parent_id === parentId)
        },
        
        updateConversationCounts: (counts) => {
          set(state => {
            const folders = { ...state.folders }
            
            Object.entries(counts).forEach(([folderId, count]) => {
              const id = Number(folderId)
              if (folders[id]) {
                folders[id] = {
                  ...folders[id],
                  conversationCount: count
                }
              }
            })
            
            return { folders }
          })
        }
      }
    })),
    {
      name: 'feedme-folders-store'
    }
  )
)

// Convenience hooks
export const useFolders = () => useFoldersStore(state => ({
  folders: state.folders,
  folderTree: state.folderTree,
  isLoading: state.isLoading,
  lastUpdated: state.lastUpdated
}))

export const useFolderSelection = () => useFoldersStore(state => ({
  selectedFolderIds: state.selectedFolderIds,
  expandedFolderIds: state.expandedFolderIds
}))

export const useFolderDragState = () => useFoldersStore(state => state.dragState)

export const useFolderModals = () => useFoldersStore(state => ({
  createModalOpen: state.createModalOpen,
  editModalOpen: state.editModalOpen,
  deleteModalOpen: state.deleteModalOpen,
  targetFolderId: state.targetFolderId
}))

export const useFoldersActions = () => useFoldersStore(state => state.actions)