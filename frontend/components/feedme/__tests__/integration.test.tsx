/**
 * FeedMe Integration Tests
 * 
 * Tests the complete integration between frontend and backend components
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useConversationsStore } from '@/lib/stores/conversations-store'
import { feedMeApi } from '@/lib/feedme-api'

// Mock API calls
vi.mock('@/lib/feedme-api', () => ({
  feedMeApi: {
    listConversations: vi.fn(),
    uploadTranscriptFile: vi.fn(),
    uploadTranscriptText: vi.fn(),
    healthCheck: vi.fn(),
    getConversation: vi.fn(),
    deleteConversation: vi.fn(),
    reprocessConversation: vi.fn(),
  },
  listConversations: vi.fn(),
  listFolders: vi.fn(),
  getApprovalWorkflowStats: vi.fn(),
  uploadTranscriptFile: vi.fn(),
  uploadTranscriptText: vi.fn(),
}))

// Mock authentication
vi.mock('@/lib/auth/feedme-auth', () => ({
  feedMeAuth: {
    isAuthenticated: () => true,
    getWebSocketUrl: (url: string) => url,
  },
  autoLogin: vi.fn(),
}))

describe('FeedMe Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should initialize store correctly', () => {
    const store = useFeedMeStore.getState()
    
    expect(store.conversations).toEqual({})
    expect(store.folders).toEqual({})
    expect(store.conversationsList.items).toEqual([])
    expect(store.ui.activeTab).toBe('conversations')
    expect(store.realtime.isConnected).toBe(false)
  })

  it('should load conversations successfully', async () => {
    const mockConversations = [
      {
        id: 1,
        title: 'Test Conversation',
        processing_status: 'completed' as const,
        total_examples: 5,
        created_at: '2025-01-01T00:00:00Z',
        metadata: {}
      }
    ]

    vi.mocked(feedMeApi.listConversations).mockResolvedValue({
      conversations: mockConversations,
      total_count: 1,
      page: 1,
      page_size: 20,
      has_next: false
    })

    const actions = useFeedMeStore.getState().actions
    await actions.loadConversations()

    const state = useFeedMeStore.getState()
    expect(state.conversationsList.items).toHaveLength(1)
    expect(state.conversations[1]).toEqual(mockConversations[0])
  })

  it('should upload conversations successfully', async () => {
    const mockResponse = {
      id: 2,
      title: 'Uploaded Conversation',
      processing_status: 'pending' as const,
      total_examples: 0,
      created_at: '2025-01-01T00:00:00Z',
      metadata: {}
    }

    vi.mocked(feedMeApi.uploadTranscriptText).mockResolvedValue(mockResponse)
    vi.mocked(feedMeApi.listConversations).mockResolvedValue({
      conversations: [mockResponse],
      total_count: 1,
      page: 1,
      page_size: 20,
      has_next: false
    })

    const actions = useFeedMeStore.getState().actions
    const result = await actions.uploadConversation(
      'Test Upload',
      undefined,
      'Test content'
    )

    expect(result).toEqual(mockResponse)
    expect(feedMeApi.uploadTranscriptText).toHaveBeenCalledWith(
      'Test Upload',
      'Test content',
      undefined,
      true
    )
  })

  it('should handle WebSocket connection', () => {
    const actions = useFeedMeStore.getState().actions
    
    // Mock WebSocket
    const mockWebSocket = {
      close: vi.fn(),
      send: vi.fn(),
      readyState: WebSocket.OPEN,
      onopen: null,
      onmessage: null,
      onclose: null,
      onerror: null,
    }
    
    global.WebSocket = vi.fn(() => mockWebSocket) as any

    actions.connectWebSocket()

    // Should attempt to create WebSocket connection
    expect(WebSocket).toHaveBeenCalled()
  })

  it('should handle search functionality', async () => {
    const mockSearchResults = [
      {
        id: 1,
        title: 'Search Result',
        processing_status: 'completed' as const,
        total_examples: 3,
        created_at: '2025-01-01T00:00:00Z',
        metadata: {}
      }
    ]

    vi.mocked(feedMeApi.listConversations).mockResolvedValue({
      conversations: mockSearchResults,
      total_count: 1,
      page: 1,
      page_size: 50,
      has_next: false
    })

    const actions = useFeedMeStore.getState().actions
    await actions.performSearch('test query')

    const state = useFeedMeStore.getState()
    expect(state.search.query).toBe('test query')
    expect(state.search.results).toHaveLength(1)
    expect(state.search.searchHistory).toContain('test query')
  })

  it('should handle conversation deletion', async () => {
    // Setup initial state with a conversation
    const store = useFeedMeStore.getState()
    store.conversations[1] = {
      id: 1,
      title: 'To Delete',
      processing_status: 'completed',
      total_examples: 0,
      created_at: '2025-01-01T00:00:00Z',
      metadata: {}
    }

    vi.mocked(feedMeApi.deleteConversation).mockResolvedValue()

    const actions = useFeedMeStore.getState().actions
    await actions.deleteConversation(1)

    expect(feedMeApi.deleteConversation).toHaveBeenCalledWith(1)
    
    const finalState = useFeedMeStore.getState()
    expect(finalState.conversations[1]).toBeUndefined()
  })

  it('should handle notifications', () => {
    const actions = useFeedMeStore.getState().actions
    
    actions.addNotification({
      type: 'success',
      title: 'Test Notification',
      message: 'This is a test'
    })

    const state = useFeedMeStore.getState()
    expect(state.realtime.notifications).toHaveLength(1)
    expect(state.realtime.notifications[0].title).toBe('Test Notification')
  })

  it('should handle folder management', async () => {
    const mockFolder = {
      id: 1,
      name: 'Test Folder',
      color: 'blue',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
      conversation_count: 0
    }

    vi.mocked(feedMeApi.createFolder).mockResolvedValue(mockFolder)

    const actions = useFeedMeStore.getState().actions
    await actions.createFolder('Test Folder', 'blue')

    const state = useFeedMeStore.getState()
    expect(state.folders[1]).toBeDefined()
    expect(state.folders[1].name).toBe('Test Folder')
  })
})

// API Health Check Integration Test
describe('FeedMe API Integration', () => {
  it('should check API health', async () => {
    vi.mocked(feedMeApi.healthCheck).mockResolvedValue(true)

    const isHealthy = await feedMeApi.healthCheck()
    expect(isHealthy).toBe(true)
  })

  it('should handle API errors gracefully', async () => {
    vi.mocked(feedMeApi.listConversations).mockRejectedValue(
      new Error('API Error')
    )

    const actions = useFeedMeStore.getState().actions
    await actions.loadConversations()

    // Should handle error gracefully and add notification
    const state = useFeedMeStore.getState()
    expect(state.realtime.notifications.some(n => n.type === 'error')).toBe(true)
  })
})