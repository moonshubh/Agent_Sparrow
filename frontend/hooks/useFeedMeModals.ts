/**
 * useFeedMeModals - Custom hook for managing FeedMe modal states
 * 
 * Extracts modal state management logic from FeedMePageManager
 * Handles upload modal and folder creation modal states and logic
 */

import { useState } from 'react'
import { useFoldersActions } from '@/lib/stores/folders-store'

export interface FolderFormData {
  name: string
  description: string
  color: string
}

export function useFeedMeModals() {
  // Modal states
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  
  // Folder creation form state
  const [folderFormData, setFolderFormData] = useState<FolderFormData>({
    name: '',
    description: '',
    color: '#0095ff'
  })

  const foldersActions = useFoldersActions()

  // Modal handlers
  const openUploadModal = () => setUploadModalOpen(true)
  const closeUploadModal = () => setUploadModalOpen(false)

  // Folder form handlers
  const updateFolderForm = (updates: Partial<FolderFormData>) => {
    setFolderFormData(prev => ({ ...prev, ...updates }))
  }

  const resetFolderForm = () => {
    setFolderFormData({
      name: '',
      description: '',
      color: '#0095ff'
    })
  }

  const handleCreateFolder = async () => {
    if (!folderFormData.name.trim()) return false
    
    try {
      await foldersActions.createFolder({
        name: folderFormData.name.trim(),
        color: folderFormData.color,
        description: folderFormData.description.trim() || undefined
      })
      
      resetFolderForm()
      foldersActions.closeModals()
      return true
    } catch (error) {
      console.error('Failed to create folder:', error)
      return false
    }
  }

  const openFolderCreateModal = () => {
    resetFolderForm()
    foldersActions.openCreateModal()
  }

  return {
    // Modal states
    uploadModalOpen,
    folderFormData,
    
    // Modal handlers
    openUploadModal,
    closeUploadModal,
    openFolderCreateModal,
    
    // Folder form handlers
    updateFolderForm,
    resetFolderForm,
    handleCreateFolder,
  }
}