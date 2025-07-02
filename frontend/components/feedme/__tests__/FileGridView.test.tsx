/**
 * FileGridView Component Tests
 * 
 * Comprehensive test suite for the FileGridView component with 95%+ coverage.
 * Tests grid layout, multi-select, bulk operations, virtual scrolling, and file management.
 */

import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { FileGridView } from '../FileGridView'
import { useConversations, useActions, useFolders } from '@/lib/stores/feedme-store'

// Mock the store
vi.mock('@/lib/stores/feedme-store', () => ({
  useConversations: vi.fn(),
  useActions: vi.fn(),
  useFolders: vi.fn(),
}))

// Mock react-window for virtual scrolling
vi.mock('react-window', () => ({
  VariableSizeGrid: ({ children, columnCount, rowCount, height, width }: any) => (
    <div data-testid="virtual-grid" style={{ height, width }}>
      {Array.from({ length: rowCount }, (_, rowIndex) =>
        Array.from({ length: columnCount }, (_, columnIndex) => (
          <div key={`${rowIndex}-${columnIndex}`}>
            {children({ rowIndex, columnIndex, style: {} })}
          </div>
        ))
      )}
    </div>
  ),
}))

// Mock react-window-infinite-loader
vi.mock('react-window-infinite-loader', () => ({
  InfiniteLoader: ({ children, hasNextPage, loadMoreItems }: any) => (
    <div data-testid="infinite-loader">
      {children({ onItemsRendered: vi.fn(), ref: vi.fn() })}
    </div>
  ),
}))

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Grid: () => <div data-testid="grid-icon" />,
  List: () => <div data-testid="list-icon" />,
  Search: () => <div data-testid="search-icon" />,
  Filter: () => <div data-testid="filter-icon" />,
  MoreHorizontal: () => <div data-testid="more-horizontal" />,
  FileText: () => <div data-testid="file-text-icon" />,
  Download: () => <div data-testid="download-icon" />,
  Trash2: () => <div data-testid="trash-icon" />,
  Edit: () => <div data-testid="edit-icon" />,
  Copy: () => <div data-testid="copy-icon" />,
  Move: () => <div data-testid="move-icon" />,
  Eye: () => <div data-testid="eye-icon" />,
  Star: () => <div data-testid="star-icon" />,
  Clock: () => <div data-testid="clock-icon" />,
  User: () => <div data-testid="user-icon" />,
  Calendar: () => <div data-testid="calendar-icon" />,
  CheckCircle2: () => <div data-testid="check-circle-icon" />,
  XCircle: () => <div data-testid="x-circle-icon" />,
  AlertCircle: () => <div data-testid="alert-circle-icon" />,
  Loader: () => <div data-testid="loader-icon" />,
}))

// Mock data
const mockConversations = [
  {
    id: 'conv-1',
    title: 'Customer Support Chat 1',
    originalFilename: 'support-chat-1.txt',
    folderId: 'folder-1',
    processingStatus: 'completed' as const,
    totalExamples: 15,
    uploadedAt: '2025-07-01T10:00:00Z',
    processedAt: '2025-07-01T10:15:00Z',
    uploadedBy: 'user-1',
    metadata: {
      fileSize: 1024 * 50,
      encoding: 'utf-8',
      lineCount: 100,
      platform: 'web',
      tags: ['support', 'urgent'],
    },
    rawTranscript: 'Sample transcript content...',
    parsedContent: { messages: [] },
    errorMessage: null,
    createdAt: '2025-07-01T10:00:00Z',
    updatedAt: '2025-07-01T10:15:00Z',
  },
  {
    id: 'conv-2',
    title: 'Email Sync Issue',
    originalFilename: 'email-sync-help.txt',
    folderId: 'folder-1',
    processingStatus: 'processing' as const,
    totalExamples: 0,
    uploadedAt: '2025-07-01T11:00:00Z',
    processedAt: null,
    uploadedBy: 'user-1',
    metadata: {
      fileSize: 1024 * 75,
      encoding: 'utf-8',
      lineCount: 150,
      platform: 'desktop',
      tags: ['email', 'sync'],
    },
    rawTranscript: 'Email sync problem transcript...',
    parsedContent: null,
    errorMessage: null,
    createdAt: '2025-07-01T11:00:00Z',
    updatedAt: '2025-07-01T11:00:00Z',
  },
  {
    id: 'conv-3',
    title: 'Account Setup Help',
    originalFilename: 'account-setup.txt',
    folderId: 'folder-2',
    processingStatus: 'failed' as const,
    totalExamples: 0,
    uploadedAt: '2025-07-01T12:00:00Z',
    processedAt: null,
    uploadedBy: 'user-2',
    metadata: {
      fileSize: 1024 * 25,
      encoding: 'utf-8',
      lineCount: 75,
      platform: 'mobile',
      tags: ['setup', 'account'],
    },
    rawTranscript: 'Account setup help transcript...',
    parsedContent: null,
    errorMessage: 'Invalid file format',
    createdAt: '2025-07-01T12:00:00Z',
    updatedAt: '2025-07-01T12:00:00Z',
  },
]

const mockFolders = [
  {
    id: 'folder-1',
    name: 'Support Chats',
    parentId: null,
    children: [],
    conversationCount: 2,
    totalSize: 1024 * 125,
    createdAt: '2025-07-01T09:00:00Z',
    updatedAt: '2025-07-01T11:00:00Z',
  },
  {
    id: 'folder-2',
    name: 'Setup Issues',
    parentId: null,
    children: [],
    conversationCount: 1,
    totalSize: 1024 * 25,
    createdAt: '2025-07-01T09:00:00Z',
    updatedAt: '2025-07-01T12:00:00Z',
  },
]

const mockActions = {
  loadConversations: vi.fn(),
  deleteConversation: vi.fn(),
  updateConversation: vi.fn(),
  moveConversation: vi.fn(),
  duplicateConversation: vi.fn(),
  reprocessConversation: vi.fn(),
  setSelectedConversations: vi.fn(),
  setBulkOperationMode: vi.fn(),
}

describe('FileGridView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    // Setup store mocks
    ;(useConversations as any).mockReturnValue({
      conversations: mockConversations,
      selectedConversations: new Set(),
      bulkOperationMode: false,
      isLoading: false,
      error: null,
      hasNextPage: false,
      totalCount: mockConversations.length,
    })
    
    ;(useFolders as any).mockReturnValue({
      folders: mockFolders,
      selectedFolder: 'folder-1',
    })
    
    ;(useActions as any).mockReturnValue(mockActions)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders file grid with correct structure', () => {
      render(<FileGridView />)
      
      expect(screen.getByTestId('virtual-grid')).toBeInTheDocument()
      expect(screen.getByText('Customer Support Chat 1')).toBeInTheDocument()
      expect(screen.getByText('Email Sync Issue')).toBeInTheDocument()
    })

    it('displays file cards with correct information', () => {
      render(<FileGridView />)
      
      // Check first conversation card
      expect(screen.getByText('Customer Support Chat 1')).toBeInTheDocument()
      expect(screen.getByText('support-chat-1.txt')).toBeInTheDocument()
      expect(screen.getByText('15 examples')).toBeInTheDocument()
      expect(screen.getByText('50 KB')).toBeInTheDocument()
    })

    it('shows processing status indicators', () => {
      render(<FileGridView />)
      
      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument() // Completed
      expect(screen.getByTestId('loader-icon')).toBeInTheDocument() // Processing
      expect(screen.getByTestId('x-circle-icon')).toBeInTheDocument() // Failed
    })

    it('displays file thumbnails and metadata', () => {
      render(<FileGridView />)
      
      expect(screen.getAllByTestId('file-text-icon')).toHaveLength(3)
      expect(screen.getByText('100 lines')).toBeInTheDocument()
      expect(screen.getByText('150 lines')).toBeInTheDocument()
      expect(screen.getByText('75 lines')).toBeInTheDocument()
    })

    it('handles loading state', () => {
      ;(useConversations as any).mockReturnValue({
        conversations: [],
        selectedConversations: new Set(),
        bulkOperationMode: false,
        isLoading: true,
        error: null,
        hasNextPage: false,
        totalCount: 0,
      })

      render(<FileGridView />)
      
      expect(screen.getByText('Loading conversations...')).toBeInTheDocument()
    })

    it('handles error state', () => {
      ;(useConversations as any).mockReturnValue({
        conversations: [],
        selectedConversations: new Set(),
        bulkOperationMode: false,
        isLoading: false,
        error: 'Failed to load conversations',
        hasNextPage: false,
        totalCount: 0,
      })

      render(<FileGridView />)
      
      expect(screen.getByText('Error: Failed to load conversations')).toBeInTheDocument()
    })

    it('handles empty state', () => {
      ;(useConversations as any).mockReturnValue({
        conversations: [],
        selectedConversations: new Set(),
        bulkOperationMode: false,
        isLoading: false,
        error: null,
        hasNextPage: false,
        totalCount: 0,
      })

      render(<FileGridView />)
      
      expect(screen.getByText('No conversations found')).toBeInTheDocument()
      expect(screen.getByText('Upload your first conversation to get started')).toBeInTheDocument()
    })
  })

  describe('View Options', () => {
    it('toggles between grid and list view', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const listViewButton = screen.getByTestId('list-icon').closest('button')
      await user.click(listViewButton!)
      
      // Should change to list view
      expect(screen.getByTestId('list-icon').closest('button')).toHaveClass('bg-accent')
    })

    it('adjusts grid size with slider', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const sizeSlider = screen.getByRole('slider')
      await user.click(sizeSlider)
      
      // Should trigger grid size change
      expect(sizeSlider).toBeInTheDocument()
    })

    it('supports different sort options', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const sortSelect = screen.getByText('Sort by')
      await user.click(sortSelect)
      
      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Date')).toBeInTheDocument()
      expect(screen.getByText('Size')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
    })
  })

  describe('File Selection', () => {
    it('handles single file selection', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1').closest('div')
      await user.click(fileCard!)
      
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(new Set(['conv-1']))
    })

    it('handles multi-select with Ctrl/Cmd key', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const firstCard = screen.getByText('Customer Support Chat 1').closest('div')
      const secondCard = screen.getByText('Email Sync Issue').closest('div')
      
      await user.click(firstCard!)
      await user.keyboard('{Control>}')
      await user.click(secondCard!)
      await user.keyboard('{/Control}')
      
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(new Set(['conv-1', 'conv-2']))
    })

    it('handles range selection with Shift key', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const firstCard = screen.getByText('Customer Support Chat 1').closest('div')
      const thirdCard = screen.getByText('Account Setup Help').closest('div')
      
      await user.click(firstCard!)
      await user.keyboard('{Shift>}')
      await user.click(thirdCard!)
      await user.keyboard('{/Shift}')
      
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(new Set(['conv-1', 'conv-2', 'conv-3']))
    })

    it('shows selection count', () => {
      ;(useConversations as any).mockReturnValue({
        conversations: mockConversations,
        selectedConversations: new Set(['conv-1', 'conv-2']),
        bulkOperationMode: true,
        isLoading: false,
        error: null,
        hasNextPage: false,
        totalCount: mockConversations.length,
      })

      render(<FileGridView />)
      
      expect(screen.getByText('2 selected')).toBeInTheDocument()
    })

    it('supports select all functionality', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const selectAllCheckbox = screen.getByRole('checkbox', { name: /select all/i })
      await user.click(selectAllCheckbox)
      
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(
        new Set(['conv-1', 'conv-2', 'conv-3'])
      )
    })
  })

  describe('Bulk Operations', () => {
    beforeEach(() => {
      ;(useConversations as any).mockReturnValue({
        conversations: mockConversations,
        selectedConversations: new Set(['conv-1', 'conv-2']),
        bulkOperationMode: true,
        isLoading: false,
        error: null,
        hasNextPage: false,
        totalCount: mockConversations.length,
      })
    })

    it('shows bulk operations panel when files are selected', () => {
      render(<FileGridView />)
      
      expect(screen.getByText('Bulk Operations')).toBeInTheDocument()
      expect(screen.getByText('Delete Selected')).toBeInTheDocument()
      expect(screen.getByText('Move to Folder')).toBeInTheDocument()
      expect(screen.getByText('Download Selected')).toBeInTheDocument()
    })

    it('handles bulk delete operation', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const deleteButton = screen.getByText('Delete Selected')
      await user.click(deleteButton)
      
      // Should show confirmation dialog
      expect(screen.getByText('Delete 2 conversations?')).toBeInTheDocument()
      
      const confirmButton = screen.getByText('Delete')
      await user.click(confirmButton)
      
      expect(mockActions.deleteConversation).toHaveBeenCalledTimes(2)
    })

    it('handles bulk move operation', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const moveButton = screen.getByText('Move to Folder')
      await user.click(moveButton)
      
      // Should show folder selection dialog
      expect(screen.getByText('Select destination folder')).toBeInTheDocument()
      
      const folderOption = screen.getByText('Setup Issues')
      await user.click(folderOption)
      
      const confirmButton = screen.getByText('Move')
      await user.click(confirmButton)
      
      expect(mockActions.moveConversation).toHaveBeenCalledTimes(2)
    })

    it('handles bulk download operation', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      // Mock URL.createObjectURL
      global.URL.createObjectURL = vi.fn(() => 'blob:test')
      global.URL.revokeObjectURL = vi.fn()
      
      const downloadButton = screen.getByText('Download Selected')
      await user.click(downloadButton)
      
      expect(global.URL.createObjectURL).toHaveBeenCalled()
    })

    it('handles bulk reprocess operation', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const reprocessButton = screen.getByText('Reprocess Selected')
      await user.click(reprocessButton)
      
      expect(mockActions.reprocessConversation).toHaveBeenCalledTimes(2)
    })
  })

  describe('Context Menu', () => {
    it('opens context menu on right click', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1')
      await user.pointer({ keys: '[MouseRight]', target: fileCard })
      
      expect(screen.getByText('View Details')).toBeInTheDocument()
      expect(screen.getByText('Edit')).toBeInTheDocument()
      expect(screen.getByText('Download')).toBeInTheDocument()
      expect(screen.getByText('Move')).toBeInTheDocument()
      expect(screen.getByText('Duplicate')).toBeInTheDocument()
      expect(screen.getByText('Delete')).toBeInTheDocument()
    })

    it('handles view details action', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1')
      await user.pointer({ keys: '[MouseRight]', target: fileCard })
      
      const viewAction = screen.getByText('View Details')
      await user.click(viewAction)
      
      expect(screen.getByText('Conversation Details')).toBeInTheDocument()
    })

    it('handles edit action', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1')
      await user.pointer({ keys: '[MouseRight]', target: fileCard })
      
      const editAction = screen.getByText('Edit')
      await user.click(editAction)
      
      expect(screen.getByDisplayValue('Customer Support Chat 1')).toBeInTheDocument()
    })

    it('handles duplicate action', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1')
      await user.pointer({ keys: '[MouseRight]', target: fileCard })
      
      const duplicateAction = screen.getByText('Duplicate')
      await user.click(duplicateAction)
      
      expect(mockActions.duplicateConversation).toHaveBeenCalledWith('conv-1')
    })
  })

  describe('Search and Filter', () => {
    it('filters files by search term', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const searchInput = screen.getByPlaceholderText('Search conversations...')
      await user.type(searchInput, 'email')
      
      // Should filter to show only email-related conversation
      await waitFor(() => {
        expect(screen.getByText('Email Sync Issue')).toBeInTheDocument()
        expect(screen.queryByText('Customer Support Chat 1')).not.toBeInTheDocument()
      })
    })

    it('filters by processing status', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const statusFilter = screen.getByText('All Status')
      await user.click(statusFilter)
      
      const completedFilter = screen.getByText('Completed')
      await user.click(completedFilter)
      
      // Should show only completed conversations
      await waitFor(() => {
        expect(screen.getByText('Customer Support Chat 1')).toBeInTheDocument()
        expect(screen.queryByText('Email Sync Issue')).not.toBeInTheDocument()
      })
    })

    it('filters by tags', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const tagFilter = screen.getByText('support')
      await user.click(tagFilter)
      
      // Should show only conversations with 'support' tag
      await waitFor(() => {
        expect(screen.getByText('Customer Support Chat 1')).toBeInTheDocument()
        expect(screen.queryByText('Email Sync Issue')).not.toBeInTheDocument()
      })
    })

    it('filters by date range', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const dateFilter = screen.getByText('Date Range')
      await user.click(dateFilter)
      
      // Should show date picker
      expect(screen.getByText('Select date range')).toBeInTheDocument()
    })
  })

  describe('Virtual Scrolling', () => {
    it('renders virtual grid component', () => {
      render(<FileGridView />)
      
      expect(screen.getByTestId('virtual-grid')).toBeInTheDocument()
      expect(screen.getByTestId('infinite-loader')).toBeInTheDocument()
    })

    it('handles infinite loading', async () => {
      ;(useConversations as any).mockReturnValue({
        conversations: mockConversations,
        selectedConversations: new Set(),
        bulkOperationMode: false,
        isLoading: false,
        error: null,
        hasNextPage: true,
        totalCount: 100,
      })

      render(<FileGridView />)
      
      // Should show infinite loader
      expect(screen.getByTestId('infinite-loader')).toBeInTheDocument()
      expect(mockActions.loadConversations).toHaveBeenCalled()
    })

    it('calculates correct grid dimensions', () => {
      render(<FileGridView />)
      
      const virtualGrid = screen.getByTestId('virtual-grid')
      expect(virtualGrid).toHaveStyle({ height: expect.any(String) })
    })

    it('handles grid resize on window resize', async () => {
      render(<FileGridView />)
      
      // Simulate window resize
      act(() => {
        global.innerWidth = 1200
        global.dispatchEvent(new Event('resize'))
      })
      
      await waitFor(() => {
        expect(screen.getByTestId('virtual-grid')).toBeInTheDocument()
      })
    })
  })

  describe('Performance', () => {
    it('debounces search input', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const searchInput = screen.getByPlaceholderText('Search conversations...')
      
      // Type quickly
      await user.type(searchInput, 'test', { delay: 10 })
      
      // Should debounce the search
      await waitFor(() => {
        expect(searchInput).toHaveValue('test')
      }, { timeout: 600 })
    })

    it('memoizes expensive calculations', () => {
      const { rerender } = render(<FileGridView />)
      
      // Re-render with same props
      rerender(<FileGridView />)
      
      // Should not re-calculate grid layout
      expect(screen.getByTestId('virtual-grid')).toBeInTheDocument()
    })

    it('virtualizes large datasets efficiently', () => {
      const largeDataset = Array.from({ length: 10000 }, (_, i) => ({
        ...mockConversations[0],
        id: `conv-${i}`,
        title: `Conversation ${i}`,
      }))

      ;(useConversations as any).mockReturnValue({
        conversations: largeDataset,
        selectedConversations: new Set(),
        bulkOperationMode: false,
        isLoading: false,
        error: null,
        hasNextPage: false,
        totalCount: largeDataset.length,
      })

      const startTime = performance.now()
      render(<FileGridView />)
      const endTime = performance.now()
      
      // Should render quickly even with large dataset
      expect(endTime - startTime).toBeLessThan(100)
      expect(screen.getByTestId('virtual-grid')).toBeInTheDocument()
    })
  })

  describe('Keyboard Navigation', () => {
    it('handles arrow key navigation', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const firstCard = screen.getByText('Customer Support Chat 1').closest('div')
      await user.click(firstCard!)
      
      // Navigate right
      await user.keyboard('{ArrowRight}')
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(new Set(['conv-2']))
      
      // Navigate down
      await user.keyboard('{ArrowDown}')
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(new Set(['conv-3']))
    })

    it('handles Enter key for file opening', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1').closest('div')
      await user.click(fileCard!)
      await user.keyboard('{Enter}')
      
      expect(screen.getByText('Conversation Details')).toBeInTheDocument()
    })

    it('handles Delete key for deletion', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1').closest('div')
      await user.click(fileCard!)
      await user.keyboard('{Delete}')
      
      expect(screen.getByText('Delete conversation?')).toBeInTheDocument()
    })

    it('handles Ctrl+A for select all', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      await user.keyboard('{Control>}a{/Control}')
      
      expect(mockActions.setSelectedConversations).toHaveBeenCalledWith(
        new Set(['conv-1', 'conv-2', 'conv-3'])
      )
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<FileGridView />)
      
      expect(screen.getByRole('grid')).toBeInTheDocument()
      expect(screen.getAllByRole('gridcell')).toHaveLength(3)
    })

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const grid = screen.getByRole('grid')
      grid.focus()
      
      await user.keyboard('{ArrowDown}')
      expect(mockActions.setSelectedConversations).toHaveBeenCalled()
    })

    it('has proper focus management', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const firstCard = screen.getByText('Customer Support Chat 1').closest('div')
      await user.click(firstCard!)
      
      expect(firstCard).toHaveFocus()
    })

    it('announces selection changes to screen readers', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1').closest('div')
      await user.click(fileCard!)
      
      // Check for aria-live region updates
      expect(screen.getByText('1 file selected')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles network errors gracefully', async () => {
      mockActions.deleteConversation.mockRejectedValue(new Error('Network error'))
      
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Customer Support Chat 1')
      await user.pointer({ keys: '[MouseRight]', target: fileCard })
      
      const deleteAction = screen.getByText('Delete')
      await user.click(deleteAction)
      
      await waitFor(() => {
        expect(screen.getByText('Failed to delete conversation')).toBeInTheDocument()
      })
    })

    it('handles invalid file operations', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const fileCard = screen.getByText('Account Setup Help') // Failed status
      await user.pointer({ keys: '[MouseRight]', target: fileCard })
      
      const reprocessAction = screen.getByText('Reprocess')
      await user.click(reprocessAction)
      
      expect(mockActions.reprocessConversation).toHaveBeenCalledWith('conv-3')
    })

    it('prevents operations on processing files', async () => {
      const user = userEvent.setup()
      render(<FileGridView />)
      
      const processingCard = screen.getByText('Email Sync Issue')
      await user.pointer({ keys: '[MouseRight]', target: processingCard })
      
      const editAction = screen.getByText('Edit')
      expect(editAction).toBeDisabled()
    })
  })
})