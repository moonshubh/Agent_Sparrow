/**
 * FeedMe v2.0 Phase 3: Edit & Version UI - Frontend Tests
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'
import { EditConversationModal } from '../EditConversationModal'
import { VersionHistoryPanel } from '../VersionHistoryPanel'
import { DiffViewer } from '../DiffViewer'
import * as feedmeApi from '../../../lib/feedme-api'
import {
  type UploadTranscriptResponse,
  type ConversationVersion,
  type VersionDiff,
} from '../../../lib/feedme-api'

// Mock the API module and provide type-safe mocks
// Mock ResizeObserver for Radix UI components
const ResizeObserverMock = vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
vi.stubGlobal('ResizeObserver', ResizeObserverMock);

vi.mock('../../../lib/feedme-api')
const mockEditConversation = feedmeApi.editConversation as Mock
const mockGetConversationVersions = feedmeApi.getConversationVersions as Mock
const mockGetVersionDiff = feedmeApi.getVersionDiff as Mock
const mockRevertConversation = feedmeApi.revertConversation as Mock

// Mock Data
const mockConversation: UploadTranscriptResponse = {
  id: 1,
  title: 'Customer Issue #123',
  processing_status: 'completed',
  total_examples: 10,
  created_at: '2025-01-01T11:00:00Z',
  metadata: {
    raw_transcript: 'Customer: I need help\nSupport: How can I assist you?',
    version: 2,
    updated_by: 'editor@example.com',
    updated_at: '2025-01-01T12:00:00Z',
  },
}

const mockVersions: ConversationVersion[] = [
  {
    id: 2, conversation_id: 1, version: 2, is_active: true, title: 'Customer Issue #123',
    raw_transcript: 'Customer: I need help\nSupport: How can I assist you?',
    metadata: {}, updated_by: 'editor@example.com', created_at: '2025-01-01T12:00:00Z', updated_at: '2025-01-01T12:00:00Z',
  },
  {
    id: 1, conversation_id: 1, version: 1, is_active: false, title: 'Customer Issue #123',
    raw_transcript: 'Customer: I need help\nSupport: I am here to assist.',
    metadata: {}, updated_by: 'agent@example.com', created_at: '2025-01-01T11:00:00Z', updated_at: '2025-01-01T11:00:00Z',
  },
]

const mockDiff: VersionDiff = {
  from_version: 1, to_version: 2,
  added_lines: ['Support: How can I assist you?'],
  removed_lines: ['Support: I am here to assist.'],
  modified_lines: [], unchanged_lines: ['Customer: I need help'],
  stats: { added_count: 1, removed_count: 1, modified_count: 0, unchanged_count: 1, total_changes: 2 },
}

beforeEach(() => {
  vi.spyOn(window, 'confirm').mockImplementation(() => true);
  vi.clearAllMocks();
  mockGetConversationVersions.mockResolvedValue({
    versions: mockVersions, total_count: 2, active_version: 2,
  });
});

describe('EditConversationModal', () => {

  it('should render edit modal with conversation content', async () => {
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    // Wait for async version history to load to prevent `act` warnings
    await waitFor(() => {
      expect(mockGetConversationVersions).toHaveBeenCalled()
    })

    expect(screen.getByText(/edit conversation/i)).toBeInTheDocument()
    expect(screen.getByDisplayValue(mockConversation.title)).toBeInTheDocument()
    // The full transcript might be in a complex structure, check for a snippet
    expect(screen.getByText(/Customer: I need help/)).toBeInTheDocument()
  })

  it('should allow editing title and transcript', async () => {
    const user = userEvent.setup()
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    const titleInput = screen.getByDisplayValue(mockConversation.title)
    await user.clear(titleInput)
    await user.type(titleInput, 'New Title')
    expect(titleInput).toHaveValue('New Title')
    
    const editor = screen.getAllByRole('textbox')[1] // 0=title, 1=transcript editor
    await user.clear(editor)
    await user.type(editor, 'New transcript content')
    expect(editor).toHaveTextContent('New transcript content')
  })

  it('should save changes and call the update handler', async () => {
    const user = userEvent.setup()
    const updatedConversation = { ...mockConversation, title: 'Updated Title' }
    mockEditConversation.mockResolvedValue({
      conversation: updatedConversation,
      new_version: 3,
      reprocessing: false,
    })

    const onClose = vi.fn()
    const onConversationUpdated = vi.fn()

    render(
      <EditConversationModal
        isOpen={true}
        onClose={onClose}
        conversation={mockConversation}
        onConversationUpdated={onConversationUpdated}
      />
    )

    const titleInput = screen.getByDisplayValue(mockConversation.title)
    await user.clear(titleInput)
    await user.type(titleInput, 'Updated Title')

    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(mockEditConversation).toHaveBeenCalledWith(mockConversation.id, {
        title: 'Updated Title',
        raw_transcript: mockConversation.metadata.raw_transcript,
        reprocess: true, // default
        updated_by: expect.any(String),
      })
    })

    expect(onConversationUpdated).toHaveBeenCalledWith(updatedConversation)
  })

  it('should display an API error message if saving fails', async () => {
    const user = userEvent.setup()
    const errorMessage = 'Network Error'
    mockEditConversation.mockRejectedValue(new Error(errorMessage))

    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    const titleInput = screen.getByDisplayValue(mockConversation.title)
    await user.type(titleInput, ' - Updated')

    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(screen.getByText(`Failed to save changes: ${errorMessage}`)).toBeInTheDocument()
    })
  })

  it('should validate required fields', async () => {
    const user = userEvent.setup()
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    const titleInput = screen.getByDisplayValue(mockConversation.title)
    await user.clear(titleInput)

    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    expect(await screen.findByText(/title is required/i)).toBeInTheDocument()
    expect(mockEditConversation).not.toHaveBeenCalled()
  })

  it('should show loading state during save', async () => {
    const user = userEvent.setup()
    mockEditConversation.mockImplementation(
      () => new Promise(resolve => setTimeout(resolve, 100)),
    )

    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />,
    )

    const titleInput = screen.getByDisplayValue(mockConversation.title)
    await user.type(titleInput, ' - Updated')

    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /saving/i })).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
  })
})

describe('VersionHistoryPanel', () => {
    it('should display version list and handle interactions', async () => {
    
    const user = userEvent.setup()
    const onSelectVersion = vi.fn()
    const onRevertVersion = vi.fn()
    const onRefresh = vi.fn()

    render(
      <VersionHistoryPanel
        conversationId={1}
        versions={mockVersions}
        isLoading={false}
        onSelectVersion={onSelectVersion}
        onRevertVersion={onRevertVersion}
        onRefresh={onRefresh}
      />
    )

    expect(screen.getByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Version 1')).toBeInTheDocument()
    expect(screen.getByText('editor@example.com')).toBeInTheDocument()
    expect(screen.getByText('Current')).toBeInTheDocument()

    // Click on version 1 to select for diff
    const compareButtons = screen.getAllByRole('button', { name: /compare/i })
    await user.click(compareButtons[1]) // Version 1 is the second in the list
    expect(onSelectVersion).toHaveBeenCalledWith(1)

    // Click revert on version 1
    // Click the initial revert button
    const revertButton = screen.getByRole('button', { name: /revert to version 1/i })
    await user.click(revertButton)

    // Click the confirmation button that appears
    const confirmRevertButton = screen.getByRole('button', { name: /confirm revert/i })
    await user.click(confirmRevertButton)

    expect(onRevertVersion).toHaveBeenCalledWith(1)
  })
})

describe('DiffViewer', () => {
  it('should fetch and display diff between versions', async () => {
    mockGetVersionDiff.mockResolvedValue(mockDiff)

    render(
      <DiffViewer
        conversationId={1}
        fromVersion={1}
        toVersion={2}
        onClose={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(mockGetVersionDiff).toHaveBeenCalledWith(1, 1, 2)
    })

    expect(screen.getByRole('heading', { name: /changes from version 1 to version 2/i })).toBeInTheDocument()
    expect(screen.getByText('Support: How can I assist you?')).toBeInTheDocument()
    expect(screen.getByText('Support: I am here to assist.')).toBeInTheDocument()
  })
})