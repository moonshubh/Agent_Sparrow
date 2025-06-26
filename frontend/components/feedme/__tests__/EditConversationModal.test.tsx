/**
 * FeedMe v2.0 Phase 3: Edit & Version UI - Frontend Tests
 * Test-Driven Development for edit conversation modal
 * 
 * Test Coverage:
 * - Rich text editor functionality
 * - Version history display
 * - Save and reprocess workflow
 * - Diff visualization
 * - User interactions and validation
 */

import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { EditConversationModal } from '../EditConversationModal'
import { VersionHistoryPanel } from '../VersionHistoryPanel'
import { DiffViewer } from '../DiffViewer'
import * as feedmeApi from '../../../lib/feedme-api'

// Mock the API module
vi.mock('../../../lib/feedme-api', () => ({
  updateConversation: vi.fn(),
  getConversationVersions: vi.fn(),
  getVersionDiff: vi.fn(),
  revertConversation: vi.fn(),
  reprocessConversation: vi.fn(),
}))

describe('EditConversationModal', () => {
  const mockConversation = {
    id: 1,
    title: 'Customer Issue #123',
    raw_transcript: 'Customer: I need help\nSupport: How can I assist you?',
    version: 1,
    is_active: true,
    updated_by: 'agent@example.com',
    updated_at: '2025-01-01T12:00:00Z'
  }

  const mockVersions = [
    { ...mockConversation, version: 2, updated_by: 'editor@example.com' },
    { ...mockConversation, version: 1, is_active: false }
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    ;(feedmeApi.getConversationVersions as any).mockResolvedValue({
      versions: mockVersions,
      total_count: 2
    })
  })

  it('should render edit modal with conversation content', async () => {
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    expect(screen.getByText('Edit Conversation')).toBeInTheDocument()
    expect(screen.getByDisplayValue(mockConversation.title)).toBeInTheDocument()
    expect(screen.getByText(/Customer: I need help/)).toBeInTheDocument()
  })

  it('should show rich text editor for transcript editing', async () => {
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    // Should have rich text editor
    const editor = screen.getByRole('textbox', { name: /transcript/i })
    expect(editor).toBeInTheDocument()
    
    // Should have formatting toolbar
    expect(screen.getByRole('toolbar')).toBeInTheDocument()
    expect(screen.getByLabelText(/bold/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/italic/i)).toBeInTheDocument()
  })

  it('should allow editing transcript content', async () => {
    const user = userEvent.setup()
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    const editor = screen.getByRole('textbox', { name: /transcript/i })
    await user.clear(editor)
    await user.type(editor, 'Updated transcript content')

    expect(editor).toHaveValue('Updated transcript content')
  })

  it('should show version history panel', async () => {
    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    // Should show version history tab
    const historyTab = screen.getByRole('tab', { name: /version history/i })
    expect(historyTab).toBeInTheDocument()

    await userEvent.click(historyTab)

    // Should load and display versions
    await waitFor(() => {
      expect(screen.getByText('Version 2')).toBeInTheDocument()
      expect(screen.getByText('Version 1')).toBeInTheDocument()
    })
  })

  it('should save changes and create new version', async () => {
    const user = userEvent.setup()
    const mockUpdate = vi.fn().mockResolvedValue({
      ...mockConversation,
      version: 3,
      raw_transcript: 'Updated content'
    })
    ;(feedmeApi.updateConversation as any).mockImplementation(mockUpdate)

    const onClose = vi.fn()
    render(
      <EditConversationModal
        isOpen={true}
        onClose={onClose}
        conversation={mockConversation}
      />
    )

    // Edit content
    const editor = screen.getByRole('textbox', { name: /transcript/i })
    await user.clear(editor)
    await user.type(editor, 'Updated content')

    // Save changes
    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    // Should call API with updated content
    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(mockConversation.id, {
        raw_transcript: 'Updated content',
        updated_by: expect.any(String) // Would be current user
      })
    })

    // Should close modal on success
    expect(onClose).toHaveBeenCalled()
  })

  it('should show reprocess option after saving', async () => {
    const user = userEvent.setup()
    ;(feedmeApi.updateConversation as any).mockResolvedValue({
      ...mockConversation,
      version: 3
    })

    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    // Edit and save
    const editor = screen.getByRole('textbox', { name: /transcript/i })
    await user.type(editor, ' - additional content')
    
    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    // Should show reprocess option
    await waitFor(() => {
      expect(screen.getByText(/reprocess transcript/i)).toBeInTheDocument()
    })
  })

  it('should trigger reprocessing when requested', async () => {
    const user = userEvent.setup()
    const mockReprocess = vi.fn().mockResolvedValue({ task_id: 'task_123' })
    ;(feedmeApi.reprocessConversation as any).mockImplementation(mockReprocess)
    ;(feedmeApi.updateConversation as any).mockResolvedValue({
      ...mockConversation,
      version: 3
    })

    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    // Edit, save, and reprocess
    const editor = screen.getByRole('textbox', { name: /transcript/i })
    await user.type(editor, ' - additional content')
    
    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      const reprocessButton = screen.getByRole('button', { name: /reprocess/i })
      return user.click(reprocessButton)
    })

    expect(mockReprocess).toHaveBeenCalledWith(mockConversation.id)
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

    // Clear title
    const titleInput = screen.getByDisplayValue(mockConversation.title)
    await user.clear(titleInput)

    // Try to save
    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    // Should show validation error
    expect(screen.getByText(/title is required/i)).toBeInTheDocument()
  })

  it('should show loading state during save', async () => {
    const user = userEvent.setup()
    const mockUpdate = vi.fn().mockImplementation(
      () => new Promise(resolve => setTimeout(resolve, 1000))
    )
    ;(feedmeApi.updateConversation as any).mockImplementation(mockUpdate)

    render(
      <EditConversationModal
        isOpen={true}
        onClose={vi.fn()}
        conversation={mockConversation}
      />
    )

    const saveButton = screen.getByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    // Should show loading state
    expect(screen.getByText(/saving/i)).toBeInTheDocument()
    expect(saveButton).toBeDisabled()
  })
})

describe('VersionHistoryPanel', () => {
  const mockVersions = [
    {
      version: 2,
      is_active: true,
      updated_by: 'editor@example.com',
      updated_at: '2025-01-01T12:00:00Z',
      title: 'Customer Issue #123'
    },
    {
      version: 1,
      is_active: false,
      updated_by: 'agent@example.com',
      updated_at: '2025-01-01T10:00:00Z',
      title: 'Customer Issue #123'
    }
  ]

  it('should display version list', () => {
    render(
      <VersionHistoryPanel
        conversationId={1}
        versions={mockVersions}
        onSelectVersion={vi.fn()}
        onRevertVersion={vi.fn()}
      />
    )

    expect(screen.getByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Version 1')).toBeInTheDocument()
    expect(screen.getByText('editor@example.com')).toBeInTheDocument()
    expect(screen.getByText('(Current)')).toBeInTheDocument()
  })

  it('should allow version comparison', async () => {
    const user = userEvent.setup()
    const onSelectVersion = vi.fn()

    render(
      <VersionHistoryPanel
        conversationId={1}
        versions={mockVersions}
        onSelectVersion={onSelectVersion}
        onRevertVersion={vi.fn()}
      />
    )

    // Click on version 1
    const version1Button = screen.getByRole('button', { name: /compare version 1/i })
    await user.click(version1Button)

    expect(onSelectVersion).toHaveBeenCalledWith(1)
  })

  it('should allow version revert', async () => {
    const user = userEvent.setup()
    const onRevertVersion = vi.fn()

    render(
      <VersionHistoryPanel
        conversationId={1}
        versions={mockVersions}
        onSelectVersion={vi.fn()}
        onRevertVersion={onRevertVersion}
      />
    )

    // Click revert on version 1
    const revertButton = screen.getByRole('button', { name: /revert to version 1/i })
    await user.click(revertButton)

    expect(onRevertVersion).toHaveBeenCalledWith(1)
  })
})

describe('DiffViewer', () => {
  const mockDiff = {
    added_lines: ['+ Support: Let me check that for you'],
    removed_lines: ['- Support: I will help you'],
    modified_lines: [
      { original: 'Customer: I have an issue', modified: 'Customer: I have a problem' }
    ],
    unchanged_lines: ['Customer: Hello']
  }

  it('should display diff between versions', () => {
    render(
      <DiffViewer
        diff={mockDiff}
        fromVersion={1}
        toVersion={2}
      />
    )

    expect(screen.getByText('Changes from Version 1 to Version 2')).toBeInTheDocument()
    expect(screen.getByText('Support: Let me check that for you')).toBeInTheDocument()
    expect(screen.getByText('Support: I will help you')).toBeInTheDocument()
  })

  it('should highlight added lines in green', () => {
    render(
      <DiffViewer
        diff={mockDiff}
        fromVersion={1}
        toVersion={2}
      />
    )

    const addedLine = screen.getByText('Support: Let me check that for you')
    expect(addedLine.closest('.diff-added')).toHaveClass('bg-green-50')
  })

  it('should highlight removed lines in red', () => {
    render(
      <DiffViewer
        diff={mockDiff}
        fromVersion={1}
        toVersion={2}
      />
    )

    const removedLine = screen.getByText('Support: I will help you')
    expect(removedLine.closest('.diff-removed')).toHaveClass('bg-red-50')
  })
})