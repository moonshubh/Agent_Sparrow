import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, type Mock } from 'vitest'
import { FeedMeConversationManager } from '../FeedMeConversationManager'
import * as api from '@/lib/feedme-api'

// Mock the API module using Vitest
vi.mock('@/lib/feedme-api')

const mockedListConversations = api.listConversations as Mock

describe('FeedMeConversationManager', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    vi.clearAllMocks()
  })

  it('renders correctly when open', async () => {
    mockedListConversations.mockResolvedValue({ conversations: [], total_count: 0 })
    render(<FeedMeConversationManager isOpen={true} onClose={() => {}} />)

    // Wait for the component to finish its initial loading
    await waitFor(() => {
      // The tab text is dynamic, so we use a regex to find it.
      expect(screen.getByText(/Conversations \(\d+\)/)).toBeInTheDocument()
    })
    expect(screen.getByPlaceholderText('Search conversations...')).toBeInTheDocument()
  })

  it('loads and displays conversations', async () => {
    const conversations = [
      { id: '1', title: 'Test Conversation 1', created_at: new Date().toISOString(), total_examples: 5, processing_status: 'completed' },
      { id: '2', title: 'Test Conversation 2', created_at: new Date().toISOString(), total_examples: 3, processing_status: 'processing' },
    ]
    mockedListConversations.mockResolvedValue({ conversations, total_count: 2 })

    render(<FeedMeConversationManager isOpen={true} onClose={() => {}} />)

    // Wait for conversations to be displayed
    await waitFor(() => {
      expect(screen.getByText('Test Conversation 1')).toBeInTheDocument()
      expect(screen.getByText('Test Conversation 2')).toBeInTheDocument()
    })
  })

  it('performs a debounced search', async () => {
    mockedListConversations.mockResolvedValue({ conversations: [], total_count: 0 })
    render(<FeedMeConversationManager isOpen={true} onClose={() => {}} />)

    const searchInput = screen.getByPlaceholderText('Search conversations...')
    fireEvent.change(searchInput, { target: { value: 'test' } })

    // The first call is on mount with an empty query
    await waitFor(() => {
      expect(mockedListConversations).toHaveBeenCalledWith(1, 10, '')
    })

    // Wait for the debounce timeout and check for the call with the search term
    await waitFor(() => {
      expect(mockedListConversations).toHaveBeenCalledWith(1, 10, 'test')
    }, { timeout: 500 }) // Timeout should be longer than debounce delay (300ms)
  })

  it('handles pagination', async () => {
    const conversations = Array.from({ length: 15 }, (_, i) => (
      { id: `${i + 1}`, title: `Conversation ${i + 1}`, created_at: new Date().toISOString(), total_examples: 1, processing_status: 'completed' }
    ))
    // Mock response for the first page
    mockedListConversations.mockResolvedValue({ conversations: conversations.slice(0, 10), total_count: 15 })

    render(<FeedMeConversationManager isOpen={true} onClose={() => {}} />)

    // Wait for the first page of conversations to load
    await waitFor(() => {
      expect(screen.getByText('Conversation 1')).toBeInTheDocument()
    })

    // Mock the response for the second page
    mockedListConversations.mockResolvedValue({ conversations: conversations.slice(10, 15), total_count: 15 })

    const nextButton = screen.getByText('Next')
    fireEvent.click(nextButton)

    // Wait for the API to be called for the second page
    await waitFor(() => {
      expect(mockedListConversations).toHaveBeenCalledWith(2, 10, '')
    })
    
    // Wait for the second page of conversations to be displayed
    await waitFor(() => {
        expect(screen.getByText('Conversation 11')).toBeInTheDocument()
    })
  })
});
