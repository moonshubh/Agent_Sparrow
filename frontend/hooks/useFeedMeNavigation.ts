/**
 * useFeedMeNavigation - Custom hook for managing FeedMe navigation state
 * 
 * Extracts navigation logic from FeedMePageManager
 * Handles tab changes, conversation selection, and folder navigation
 */

import { useConversationsActions } from '@/lib/stores/conversations-store'
import { useUIActions } from '@/lib/stores/ui-store'

export function useFeedMeNavigation() {
  const conversationsActions = useConversationsActions()
  const uiActions = useUIActions()

  // Tab and panel navigation
  const handleTabChange = (tab: string) => {
    uiActions.setActiveTab(tab as any)
    
    // Map tab changes to panel system
    switch (tab) {
      case 'conversations':
        uiActions.setRightPanel('conversations')
        break
      case 'analytics':
        uiActions.setRightPanel('analytics')
        break
      case 'folders':
        uiActions.setLeftPanel('folders')
        break
      default:
        break
    }
  }

  // Conversation navigation
  const handleConversationSelect = (conversationId: number) => {
    // Validate conversation ID before setting
    if (!conversationId || conversationId <= 0) {
      console.warn('Invalid conversation ID selected:', conversationId)
      return
    }
    uiActions.selectConversation(conversationId)
    // Ensure we use the inline editor panel, not the modal overlay
    uiActions.setRightPanel('conversations')
  }

  const handleConversationClose = () => {
    uiActions.selectConversation(null)
  }

  // Folder navigation
  const handleFolderSelect = (folderId: number | null) => {
    conversationsActions.setCurrentFolder(folderId)
    // Switch to conversations view when folder is selected
    uiActions.setRightPanel('conversations')
  }

  // Conversation operations
  const handleConversationMove = async (conversationId: number, folderId: number | null) => {
    try {
      await conversationsActions.updateConversation(conversationId, { 
        folder_id: folderId === null ? undefined : folderId 
      })
      // Refresh conversations list to reflect the move
      await conversationsActions.loadConversations()
      return true
    } catch (error) {
      console.error('Failed to move conversation:', error)
      return false
    }
  }

  // Panel-specific navigation handlers
  const handlePanelNavigation = (panelType: 'left' | 'right', panelValue: string) => {
    if (panelType === 'left') {
      uiActions.setLeftPanel(panelValue as any)
    } else {
      uiActions.setRightPanel(panelValue as any)
    }
  }

  return {
    // Tab and panel navigation
    handleTabChange,
    handlePanelNavigation,
    
    // Conversation navigation
    handleConversationSelect,
    handleConversationClose,
    handleConversationMove,
    
    // Folder navigation
    handleFolderSelect,
  }
}
